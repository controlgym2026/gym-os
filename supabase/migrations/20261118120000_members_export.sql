-- Gym OS — members data export (CSV / Excel)
--
-- 1. data_export_log: one row per export (audit trail + the rate limiter's
--    source of truth — apps/api/members_export.py counts a staff user's rows
--    in the last hour before allowing another export).
-- 2. members_export(): the export's single query. Latest subscription per
--    member + last completed payment + last check-in via LATERAL joins, the
--    same filters as GET /members, paged with limit/offset so the API can
--    stream the file in chunks (PostgREST caps a response at max_rows).
-- 3. One supporting index for the "last visit" lateral.
--
-- Additive only — no existing table or column is changed.

-- ---------------------------------------------------------------------------
-- 1. data_export_log
-- ---------------------------------------------------------------------------
create table public.data_export_log (
  id         uuid primary key default gen_random_uuid(),
  tenant_id  uuid not null references public.tenant (id) on delete cascade,
  staff_id   uuid references public.staff (id) on delete set null,
  format     text not null check (format in ('csv', 'xlsx')),
  filters    jsonb not null default '{}'::jsonb,
  row_count  integer not null check (row_count >= 0),
  created_at timestamptz not null default now()
);
create index data_export_log_tenant_id_created_at_idx on public.data_export_log (tenant_id, created_at desc);
create index data_export_log_staff_id_created_at_idx on public.data_export_log (staff_id, created_at desc);

alter table public.data_export_log enable row level security;

-- Read-only for tenant staff: an audit log nobody in the gym should be able
-- to edit or delete. Writes come only from the backend (service_role, which
-- bypasses RLS).
create policy tenant_isolation_select on public.data_export_log
  for select to authenticated
  using (tenant_id = public.current_tenant_id());

-- ---------------------------------------------------------------------------
-- 2. members_export()
-- ---------------------------------------------------------------------------
-- Mirrors apps/api/members.py exactly so an export returns the same rows as
-- the list for the same filters:
--   * "current" subscription = most recent by created_at, any status;
--   * effective status = the lazy-expiry rule from
--     subscriptions.reconcile_subscription_status (ACTIVE past end_date or
--     out of sessions reads as EXPIRED, and EXPIRED back in range reads as
--     ACTIVE), computed read-only here instead of written back;
--   * filters: p_filter in (active, expiring, expired, due, paid), p_photo in
--     (has_photo, no_photo), p_plan_id, p_search (an ILIKE pattern the API
--     builds the same way PostgREST does for the list) — all ANDed;
--   * order: created_at desc, except 'expired' = most recent end_date first
--     with session-based (no end_date) rows last.
-- p_today is passed in by the API (the same date.today() the list uses).
-- total_count is the full match count (window evaluated before LIMIT).
create or replace function public.members_export(
  p_tenant_id     uuid,
  p_today         date,
  p_search        text    default null,
  p_filter        text    default null,
  p_photo         text    default null,
  p_plan_id       uuid    default null,
  p_expiring_days integer default 7,
  p_limit         integer default 1000,
  p_offset        integer default 0
)
returns table (
  member_number       integer,
  name                text,
  phone               text,
  email               text,
  joined_on           date,
  plan_name           text,
  start_date          date,
  end_date            date,
  days_left           integer,
  status              text,
  due_amount          numeric,
  last_payment_at     timestamptz,
  last_payment_amount numeric,
  last_visit_at       timestamptz,
  biometric_enrolled  boolean,
  total_count         bigint
)
language sql
stable
security definer
set search_path = ''
as $$
  with base as (
    select
      m.id,
      m.member_number,
      m.name,
      m.phone,
      m.email,
      m.created_at,
      m.photo_url,
      (m.biometric_ref is not null) as biometric_enrolled,
      s.id as sub_id,
      s.plan_id,
      s.start_date,
      s.end_date,
      s.due_amount,
      case
        when s.id is null then null
        when s.status = 'ACTIVE'
             and ((s.end_date is not null and s.end_date < p_today)
                  or (s.sessions_remaining is not null and s.sessions_remaining <= 0))
          then 'EXPIRED'
        when s.status = 'EXPIRED'
             and not ((s.end_date is not null and s.end_date < p_today)
                      or (s.sessions_remaining is not null and s.sessions_remaining <= 0))
          then 'ACTIVE'
        else s.status::text
      end as eff_status
    from public.member m
    left join lateral (
      select s.id, s.plan_id, s.start_date, s.end_date, s.due_amount, s.sessions_remaining, s.status
      from public.subscription s
      where s.member_id = m.id
        and s.tenant_id = p_tenant_id
      order by s.created_at desc, s.id desc
      limit 1
    ) s on true
    where m.tenant_id = p_tenant_id
      and m.deleted_at is null
      and (p_search is null or m.name ilike p_search or m.phone ilike p_search)
  ),
  filtered as (
    select *
    from base b
    where (p_plan_id is null or b.plan_id = p_plan_id)
      and (p_photo is null
           or (p_photo = 'has_photo' and coalesce(b.photo_url, '') <> '')
           or (p_photo = 'no_photo' and coalesce(b.photo_url, '') = ''))
      and (p_filter is null
           or (p_filter = 'active'   and b.eff_status = 'ACTIVE')
           or (p_filter = 'expiring' and b.eff_status = 'ACTIVE' and b.end_date is not null
                                     and (b.end_date - p_today) between 0 and p_expiring_days)
           or (p_filter = 'expired'  and b.eff_status = 'EXPIRED')
           or (p_filter = 'due'      and b.sub_id is not null and b.due_amount > 0)
           or (p_filter = 'paid'     and b.sub_id is not null and b.due_amount <= 0))
  ),
  page as (
    select f.*, count(*) over () as total_count
    from filtered f
    order by
      case when p_filter = 'expired' then f.end_date end desc nulls last,
      f.created_at desc,
      f.id desc
    limit greatest(p_limit, 0)
    offset greatest(p_offset, 0)
  )
  select
    p.member_number,
    p.name,
    p.phone,
    p.email,
    coalesce(j.first_start, (p.created_at at time zone 'Asia/Kolkata')::date) as joined_on,
    pl.name as plan_name,
    p.start_date,
    p.end_date,
    case when p.end_date is not null then p.end_date - p_today end as days_left,
    case
      when p.sub_id is null then 'No plan'
      when p.eff_status = 'ACTIVE' and p.end_date is not null
           and (p.end_date - p_today) between 0 and p_expiring_days then 'Expiring'
      when p.eff_status = 'ACTIVE'    then 'Active'
      when p.eff_status = 'EXPIRED'   then 'Expired'
      when p.eff_status = 'FROZEN'    then 'Frozen'
      when p.eff_status = 'CANCELLED' then 'Cancelled'
      else initcap(p.eff_status)
    end as status,
    p.due_amount,
    lp.created_at as last_payment_at,
    lp.amount as last_payment_amount,
    lv.last_visit_at,
    p.biometric_enrolled,
    p.total_count
  from page p
  left join public.membership_plan pl on pl.id = p.plan_id
  left join lateral (
    select min(s2.start_date) as first_start
    from public.subscription s2
    where s2.member_id = p.id and s2.tenant_id = p_tenant_id
  ) j on true
  left join lateral (
    select pay.created_at, pay.amount
    from public.payment pay
    where pay.member_id = p.id
      and pay.tenant_id = p_tenant_id
      and pay.status = 'completed'
    order by pay.created_at desc, pay.id desc
    limit 1
  ) lp on true
  left join lateral (
    select max(a.checked_in_at) as last_visit_at
    from public.attendance a
    where a.member_id = p.id and a.tenant_id = p_tenant_id
  ) lv on true
  order by
    case when p_filter = 'expired' then p.end_date end desc nulls last,
    p.created_at desc,
    p.id desc
$$;

-- SECURITY DEFINER + an arbitrary p_tenant_id: must never be callable from
-- the browser. Supabase's default privileges grant EXECUTE on new public
-- functions to anon and authenticated directly, so revoking from PUBLIC alone
-- is not enough — revoke from both explicitly; only the backend's
-- service_role may call it.
revoke all on function public.members_export(uuid, date, text, text, text, uuid, integer, integer, integer) from public;
revoke all on function public.members_export(uuid, date, text, text, text, uuid, integer, integer, integer) from anon;
revoke all on function public.members_export(uuid, date, text, text, text, uuid, integer, integer, integer) from authenticated;
grant execute on function public.members_export(uuid, date, text, text, text, uuid, integer, integer, integer) to service_role;

-- ---------------------------------------------------------------------------
-- 3. Index for the "last visit" lateral (max(checked_in_at) per member)
-- ---------------------------------------------------------------------------
create index if not exists attendance_member_id_checked_in_at_idx
  on public.attendance (member_id, checked_in_at desc);
