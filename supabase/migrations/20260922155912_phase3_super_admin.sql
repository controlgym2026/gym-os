-- Gym OS — Phase 3: super-admin console
--
-- tenant.plan_tier and tenant.billing_status already exist from
-- 20260905150522_init_schema.sql, but as different types/values than this
-- phase's spec — converted here, not duplicated:
--
--   plan_tier: enum tenant_plan_tier ('trial'/'basic'/'pro'/'enterprise')
--     -> plain text, default 'trial'. Deliberately not an enum: the console
--     sets this as a free label, not a fixed set that would need a
--     migration every time a new tier name is introduced.
--
--   billing_status: enum billing_status ('trialing'/'active'/'past_due'/
--     'canceled') -> redefined to ('active'/'trial'/'suspended'/
--     'cancelled') per spec. 'past_due' has no direct equivalent with no
--     live payment gateway yet — mapped to 'suspended' as the closest
--     "needs attention" state on the way in. Only one real tenant exists
--     today, so this mapping is low-risk regardless.

alter table public.tenant alter column plan_tier drop default;
alter table public.tenant alter column plan_tier type text using plan_tier::text;
alter table public.tenant alter column plan_tier set default 'trial';
drop type public.tenant_plan_tier;

alter type public.billing_status rename to billing_status_old;
create type public.billing_status as enum ('active', 'trial', 'suspended', 'cancelled');

alter table public.tenant alter column billing_status drop default;
alter table public.tenant
  alter column billing_status type public.billing_status
  using (
    case billing_status::text
      when 'trialing' then 'trial'
      when 'active'   then 'active'
      when 'past_due' then 'suspended'
      when 'canceled' then 'cancelled'
    end
  )::public.billing_status;
alter table public.tenant alter column billing_status set default 'trial';
drop type public.billing_status_old;

-- ---------------------------------------------------------------------------
-- tenant_audit_log — every super-admin action against a tenant
-- ---------------------------------------------------------------------------
create table public.tenant_audit_log (
  id           uuid primary key default gen_random_uuid(),
  tenant_id    uuid not null references public.tenant (id) on delete cascade,
  action       text not null,          -- e.g. 'suspended', 'activated', 'plan_changed'
  performed_by text not null,          -- the super-admin's email; not an FK — a
                                        -- super-admin isn't a row in any staff table
  note         text,
  created_at   timestamptz not null default now()
);
create index tenant_audit_log_tenant_id_idx on public.tenant_audit_log (tenant_id);
create index tenant_audit_log_created_at_idx on public.tenant_audit_log (created_at);

-- RLS enabled with NO policies for `authenticated` — only service_role
-- (which bypasses RLS; used exclusively by the /admin/* backend routes) can
-- read or write this table. Deliberate: this is an operator-only trail,
-- never exposed to tenant staff via the normal authenticated path, even for
-- their own tenant's entries.
alter table public.tenant_audit_log enable row level security;
