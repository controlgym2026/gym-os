-- Gym OS — Phase 1: single-gym MVP (member management, plans, subscriptions,
-- check-in, payments)
--
-- `member`, `membership_plan`, `subscription`, `attendance` and `payment`
-- already exist from 20260905150522_init_schema.sql. This migration EXTENDS
-- them to match the Phase 1 spec rather than duplicating tables. RLS on
-- these tables (tenant_isolation policies, current_tenant_id()) already
-- covers every row regardless of column changes — nothing to touch there.

-- ---------------------------------------------------------------------------
-- member: + email, photo_url, soft delete
-- ---------------------------------------------------------------------------
alter table public.member
  add column email text,
  add column photo_url text,  -- storage path in the member-media bucket, not a public URL (bucket is private)
  add column deleted_at timestamptz;

-- Replace (tenant_id, phone) uniqueness with a version that ignores
-- soft-deleted rows, so a phone number frees up once its member is deleted.
-- Constraint name looked up rather than assumed, in case Postgres picked a
-- different auto-generated name than expected.
do $$
declare
  con text;
begin
  select conname into con
  from pg_constraint
  where conrelid = 'public.member'::regclass
    and contype = 'u'
    and conkey = (
      select array_agg(attnum order by attnum)
      from pg_attribute
      where attrelid = 'public.member'::regclass
        and attname in ('tenant_id', 'phone')
    );
  if con is not null then
    execute format('alter table public.member drop constraint %I', con);
  end if;
end $$;

create unique index member_tenant_id_phone_active_key
  on public.member (tenant_id, phone)
  where deleted_at is null;

-- ---------------------------------------------------------------------------
-- membership_plan: duration (interval) -> duration_days (integer), + is_active
-- ---------------------------------------------------------------------------
alter table public.membership_plan add column duration_days integer;

update public.membership_plan
  set duration_days = greatest(1, round(extract(epoch from duration) / 86400)::int)
  where duration_days is null;

alter table public.membership_plan alter column duration_days set not null;
alter table public.membership_plan
  add constraint membership_plan_duration_days_check check (duration_days > 0);
alter table public.membership_plan drop column duration;

alter table public.membership_plan add column is_active boolean not null default true;

-- ---------------------------------------------------------------------------
-- subscription: status enum redefined to spec (ACTIVE/FROZEN/EXPIRED/
-- CANCELLED, replacing pending/active/paused/expired/canceled), end_date
-- becomes optional (session-based plans), + sessions_remaining.
--
-- + frozen_at: NOT in the original spec's column list, but required to
-- implement "FROZEN -> ACTIVE resume shifts end_date forward by the frozen
-- duration" — there's no way to compute that duration without recording
-- when the freeze started.
-- ---------------------------------------------------------------------------
alter type public.subscription_status rename to subscription_status_old;
create type public.subscription_status as enum ('ACTIVE', 'FROZEN', 'EXPIRED', 'CANCELLED');

alter table public.subscription alter column status drop default;

alter table public.subscription
  alter column status type public.subscription_status
  using (
    case status::text
      when 'pending'  then 'ACTIVE'
      when 'active'   then 'ACTIVE'
      when 'paused'   then 'FROZEN'
      when 'expired'  then 'EXPIRED'
      when 'canceled' then 'CANCELLED'
    end
  )::public.subscription_status;

alter table public.subscription alter column status set default 'ACTIVE';
drop type public.subscription_status_old;

alter table public.subscription
  alter column end_date drop not null,
  add column sessions_remaining integer check (sessions_remaining is null or sessions_remaining >= 0),
  add column frozen_at timestamptz;

-- Application layer blocks creating a second ACTIVE subscription for a
-- member (see apps/api) — this index is the DB-level backstop against the
-- same race a check-then-insert can't fully close on its own.
create unique index subscription_one_active_per_member
  on public.subscription (member_id)
  where status = 'ACTIVE';

-- Check-in's "does this member have an active subscription" lookup.
create index subscription_member_status_idx on public.subscription (member_id, status);

-- ---------------------------------------------------------------------------
-- attendance: branch_id optional (no branch concept required this phase),
-- default source -> manual. attendance_source already has 'manual', 'qr'
-- and 'biometric' from the original migration (plus an unused 'mobile') —
-- 'biometric' can be used later with no migration needed.
-- ---------------------------------------------------------------------------
alter table public.attendance
  alter column branch_id drop not null,
  alter column source set default 'manual';

-- ---------------------------------------------------------------------------
-- payment: + method, status value succeeded -> completed (spec wording)
-- ---------------------------------------------------------------------------
create type public.payment_method as enum ('cash', 'card', 'upi', 'other');

-- No default: payment.method must always be given explicitly. Safe as a
-- plain NOT NULL add (no existing rows — payment logging didn't exist
-- before this phase).
alter table public.payment add column method public.payment_method not null;

alter type public.payment_status rename value 'succeeded' to 'completed';
