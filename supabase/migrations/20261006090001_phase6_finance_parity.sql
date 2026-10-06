-- Gym OS — Phase 6 finance parity, part 2 (run after 20261006090000 has
-- committed — see that file's note on why the enum values are separate).
--
-- GymOps parity for /finance: real expense tracking, PT/Service/Product
-- income not tied to a subscription, and server-side aggregation so the
-- summary is one query instead of Python loops over fetched rows (the
-- members list already taught us Render free tier can't afford that).

-- ---------------------------------------------------------------------------
-- payment: subscription_id becomes optional, + member_id
-- ---------------------------------------------------------------------------
-- A PT/Service/Product sale isn't tied to any subscription — the schema
-- decision (see the Phase 6 report) is one unified payment/income table
-- with a nullable link, not a parallel table, so every aggregation (by
-- category, by payment mode, income total) stays one code path.
alter table public.payment alter column subscription_id drop not null;

alter table public.payment add column member_id uuid references public.member (id) on delete set null;

-- Backfill: derive member_id for every existing row from its subscription
-- — this is 100% recoverable from an existing FK, not fabricated. Every
-- existing payment has a subscription_id (it was NOT NULL until the
-- statement above), so this covers 100% of current rows; new PT/Service/
-- Product rows going forward set member_id directly at insert time instead.
update public.payment p
set member_id = s.member_id
from public.subscription s
where s.id = p.subscription_id
  and p.member_id is null;

create index payment_member_id_idx on public.payment (member_id);

-- Supports the finance summary's period-range filter (tenant_id = ... AND
-- created_at BETWEEN ...) without a sequential scan over the tenant's full
-- payment history on every page load.
create index payment_tenant_id_created_at_idx on public.payment (tenant_id, created_at);

-- ---------------------------------------------------------------------------
-- expense
-- ---------------------------------------------------------------------------
-- No branch_id: payment itself carries no branch_id either (checked as part
-- of this phase's audit), so expense stays consistent with that rather than
-- inventing a branch dimension nothing else here has yet.
-- category is plain text, not an enum — the API suggests presets (Rent,
-- Salary, Electricity, Equipment, Maintenance, Marketing, Other) but a gym
-- owner typing their own category shouldn't need a migration to allow it.
-- payment_mode reuses public.payment_method (cash/card/upi/other) — the
-- same cash-vs-"online" semantics the dashboard already uses for income.
create table public.expense (
  id           uuid primary key default gen_random_uuid(),
  tenant_id    uuid not null references public.tenant (id) on delete cascade,
  category     text not null,
  amount       numeric(12, 2) not null check (amount > 0),
  expense_date date not null default current_date,
  payment_mode public.payment_method not null default 'cash',
  description  text,
  created_by   uuid references auth.users (id) on delete set null,
  created_at   timestamptz not null default now()
);
create index expense_tenant_id_idx on public.expense (tenant_id);
create index expense_tenant_id_expense_date_idx on public.expense (tenant_id, expense_date);

alter table public.expense enable row level security;
create policy tenant_isolation on public.expense
  for all to authenticated
  using (tenant_id = public.current_tenant_id())
  with check (tenant_id = public.current_tenant_id());

-- ---------------------------------------------------------------------------
-- finance_summary(): one aggregated query for the whole /finance summary
-- ---------------------------------------------------------------------------
-- Returns a single jsonb object: income_breakdown (one row per
-- transaction_type x method combo actually present, each with its own
-- count/amount/discount — small, at most 4 types x 4 methods = 16 rows,
-- cheap to sum in Python) plus expense_total for the same period.
--
-- p_from/p_to bound payment.created_at (a timestamptz instant) — the caller
-- converts the period's IST calendar boundaries to UTC instants before
-- calling this. p_from_date/p_to_date bound expense.expense_date (a plain
-- date, already an IST calendar date with no time/zone to convert) —
-- deliberately separate parameters rather than casting p_from/p_to to
-- ::date, which would silently shift by IST's +5:30 offset.
--
-- SECURITY DEFINER so it can read across RLS the same way every other
-- backend query does via the service_role client — but UNLIKE
-- current_tenant_id(), this function trusts its p_tenant_id argument rather
-- than deriving it from auth.uid(), so it must NEVER be reachable by the
-- `authenticated` role (any caller could pass another tenant's id and read
-- their finances). No GRANT to authenticated is issued — only service_role
-- (which bypasses grants entirely, same as it bypasses RLS) can call it,
-- which is exactly and only the backend.
create or replace function public.finance_summary(
  p_tenant_id uuid,
  p_from timestamptz,
  p_to timestamptz,
  p_from_date date,
  p_to_date date
)
returns jsonb
language sql
stable
security definer
set search_path = ''
as $$
  select jsonb_build_object(
    'income_breakdown', coalesce((
      select jsonb_agg(jsonb_build_object(
        'transaction_type', transaction_type,
        'method', method,
        'count', cnt,
        'amount', amt,
        'discount', disc
      ))
      from (
        select transaction_type::text as transaction_type,
               method::text as method,
               count(*) as cnt,
               coalesce(sum(amount), 0) as amt,
               coalesce(sum(discount_amount), 0) as disc
        from public.payment
        where tenant_id = p_tenant_id
          and status = 'completed'
          and created_at >= p_from
          and created_at <= p_to
        group by transaction_type, method
      ) grouped
    ), '[]'::jsonb),
    'expense_total', coalesce((
      select sum(amount)
      from public.expense
      where tenant_id = p_tenant_id
        and expense_date >= p_from_date
        and expense_date <= p_to_date
    ), 0)
  )
$$;

revoke all on function public.finance_summary(uuid, timestamptz, timestamptz, date, date) from public;
