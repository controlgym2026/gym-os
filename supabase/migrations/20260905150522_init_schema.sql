-- Gym OS — Phase 2 initial schema
--
-- Multi-tenant core: Tenant / Branch / Member / MembershipPlan / Subscription /
-- Attendance / Device / Payment / Staff.
--
-- Tenancy model
-- ------------------------------------------------------------------------------
-- Every tenant-owned table carries a denormalized `tenant_id`. This is a
-- deliberate addition to the columns listed in the spec for `subscription`,
-- `attendance`, `device` and `payment`: it lets every RLS policy be a plain
-- `tenant_id = current_tenant_id()` check with no joins, which is both the
-- documented Supabase multi-tenant pattern and far cheaper to plan.
--
-- `staff.id` IS the Supabase Auth user id (FK to auth.users). An authenticated
-- dashboard user is resolved to a tenant through their staff row.
--
-- Bootstrapping: the first tenant + its first `owner` staff row are created by
-- the FastAPI backend using the service_role key (which bypasses RLS). An
-- authenticated user with no staff row has `current_tenant_id()` = NULL and can
-- see nothing, which is intended.
--
-- `created_at timestamptz` is added to every table for basic auditing; no
-- updated_at / trigger machinery in this migration.

set check_function_bodies = off;

-- ---------------------------------------------------------------------------
-- Enums
-- ---------------------------------------------------------------------------
create type public.tenant_plan_tier   as enum ('trial', 'basic', 'pro', 'enterprise');
create type public.billing_status     as enum ('trialing', 'active', 'past_due', 'canceled');
create type public.subscription_status as enum ('pending', 'active', 'paused', 'expired', 'canceled');
create type public.attendance_source  as enum ('biometric', 'manual', 'qr', 'mobile');
create type public.payment_status     as enum ('pending', 'succeeded', 'failed', 'refunded');
create type public.staff_role         as enum ('owner', 'manager', 'trainer', 'front_desk');

-- ---------------------------------------------------------------------------
-- Tables
-- ---------------------------------------------------------------------------
create table public.tenant (
  id             uuid primary key default gen_random_uuid(),
  name           text not null,
  plan_tier      public.tenant_plan_tier not null default 'trial',
  billing_status public.billing_status   not null default 'trialing',
  created_at     timestamptz not null default now()
);

create table public.branch (
  id         uuid primary key default gen_random_uuid(),
  tenant_id  uuid not null references public.tenant (id) on delete cascade,
  address    text,
  timezone   text not null default 'Asia/Kolkata',
  created_at timestamptz not null default now()
);
create index branch_tenant_id_idx on public.branch (tenant_id);

create table public.member (
  id            uuid primary key default gen_random_uuid(),
  tenant_id     uuid not null references public.tenant (id) on delete cascade,
  branch_id     uuid references public.branch (id) on delete set null,
  name          text not null,
  phone         text,
  biometric_ref text,
  created_at    timestamptz not null default now(),
  unique (tenant_id, phone)
);
create index member_tenant_id_idx on public.member (tenant_id);
create index member_branch_id_idx on public.member (branch_id);

create table public.membership_plan (
  id            uuid primary key default gen_random_uuid(),
  tenant_id     uuid not null references public.tenant (id) on delete cascade,
  name          text not null,
  duration      interval not null,
  price         numeric(12, 2) not null check (price >= 0),
  session_limit integer check (session_limit is null or session_limit > 0),  -- null = unlimited
  created_at    timestamptz not null default now()
);
create index membership_plan_tenant_id_idx on public.membership_plan (tenant_id);

create table public.subscription (
  id         uuid primary key default gen_random_uuid(),
  tenant_id  uuid not null references public.tenant (id) on delete cascade,
  member_id  uuid not null references public.member (id) on delete cascade,
  plan_id    uuid not null references public.membership_plan (id) on delete restrict,
  start_date date not null default current_date,   -- spec "start" (renamed; "end" is a reserved word)
  end_date   date not null,                        -- spec "end"
  status     public.subscription_status not null default 'active',
  auto_renew boolean not null default false,
  created_at timestamptz not null default now(),
  check (end_date >= start_date)
);
create index subscription_tenant_id_idx on public.subscription (tenant_id);
create index subscription_member_id_idx on public.subscription (member_id);
create index subscription_plan_id_idx   on public.subscription (plan_id);

create table public.device (
  id           uuid primary key default gen_random_uuid(),
  tenant_id    uuid not null references public.tenant (id) on delete cascade,
  branch_id    uuid not null references public.branch (id) on delete cascade,
  vendor       text not null,
  serial       text not null,
  last_sync_at timestamptz,
  created_at   timestamptz not null default now(),
  unique (tenant_id, serial)
);
create index device_tenant_id_idx on public.device (tenant_id);
create index device_branch_id_idx on public.device (branch_id);

create table public.attendance (
  id            uuid primary key default gen_random_uuid(),
  tenant_id     uuid not null references public.tenant (id) on delete cascade,
  member_id     uuid not null references public.member (id) on delete cascade,
  branch_id     uuid not null references public.branch (id) on delete cascade,
  device_id     uuid references public.device (id) on delete set null,
  checked_in_at timestamptz not null default now(),
  source        public.attendance_source not null default 'biometric',
  created_at    timestamptz not null default now()
);
create index attendance_tenant_id_idx     on public.attendance (tenant_id);
create index attendance_member_id_idx     on public.attendance (member_id);
create index attendance_branch_id_idx     on public.attendance (branch_id);
create index attendance_checked_in_at_idx on public.attendance (checked_in_at);

create table public.payment (
  id              uuid primary key default gen_random_uuid(),
  tenant_id       uuid not null references public.tenant (id) on delete cascade,
  subscription_id uuid not null references public.subscription (id) on delete cascade,
  amount          numeric(12, 2) not null check (amount >= 0),
  gateway_ref     text,
  status          public.payment_status not null default 'pending',
  created_at      timestamptz not null default now()
);
create index payment_tenant_id_idx       on public.payment (tenant_id);
create index payment_subscription_id_idx on public.payment (subscription_id);
create unique index payment_gateway_ref_key on public.payment (gateway_ref) where gateway_ref is not null;

create table public.staff (
  id         uuid primary key references auth.users (id) on delete cascade,  -- = auth.uid()
  tenant_id  uuid not null references public.tenant (id) on delete cascade,
  branch_id  uuid references public.branch (id) on delete set null,
  role       public.staff_role not null default 'front_desk',
  created_at timestamptz not null default now()
);
create index staff_tenant_id_idx on public.staff (tenant_id);
create index staff_branch_id_idx on public.staff (branch_id);

-- ---------------------------------------------------------------------------
-- Tenant resolution helper
-- ---------------------------------------------------------------------------
-- SECURITY DEFINER so the lookup on public.staff is not itself gated by the
-- staff RLS policy (which would recurse). STABLE: one value per statement.
create or replace function public.current_tenant_id()
returns uuid
language sql
stable
security definer
set search_path = ''
as $$
  select tenant_id from public.staff where id = (select auth.uid())
$$;

revoke all on function public.current_tenant_id() from public;
grant execute on function public.current_tenant_id() to authenticated;

-- ---------------------------------------------------------------------------
-- Row-level security — tenant_id isolation on every table
-- ---------------------------------------------------------------------------
-- One FOR ALL policy per table, scoped to the `authenticated` role. The
-- `service_role` used by the backend has BYPASSRLS and is unaffected. `anon`
-- gets no policy and therefore no access.

alter table public.tenant          enable row level security;
alter table public.branch          enable row level security;
alter table public.member          enable row level security;
alter table public.membership_plan enable row level security;
alter table public.subscription    enable row level security;
alter table public.device          enable row level security;
alter table public.attendance      enable row level security;
alter table public.payment         enable row level security;
alter table public.staff           enable row level security;

-- tenant: the row *is* the tenant, so match on id.
create policy tenant_isolation on public.tenant
  for all to authenticated
  using (id = public.current_tenant_id())
  with check (id = public.current_tenant_id());

create policy tenant_isolation on public.branch
  for all to authenticated
  using (tenant_id = public.current_tenant_id())
  with check (tenant_id = public.current_tenant_id());

create policy tenant_isolation on public.member
  for all to authenticated
  using (tenant_id = public.current_tenant_id())
  with check (tenant_id = public.current_tenant_id());

create policy tenant_isolation on public.membership_plan
  for all to authenticated
  using (tenant_id = public.current_tenant_id())
  with check (tenant_id = public.current_tenant_id());

create policy tenant_isolation on public.subscription
  for all to authenticated
  using (tenant_id = public.current_tenant_id())
  with check (tenant_id = public.current_tenant_id());

create policy tenant_isolation on public.device
  for all to authenticated
  using (tenant_id = public.current_tenant_id())
  with check (tenant_id = public.current_tenant_id());

create policy tenant_isolation on public.attendance
  for all to authenticated
  using (tenant_id = public.current_tenant_id())
  with check (tenant_id = public.current_tenant_id());

create policy tenant_isolation on public.payment
  for all to authenticated
  using (tenant_id = public.current_tenant_id())
  with check (tenant_id = public.current_tenant_id());

create policy tenant_isolation on public.staff
  for all to authenticated
  using (tenant_id = public.current_tenant_id())
  with check (tenant_id = public.current_tenant_id());
