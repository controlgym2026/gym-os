-- Gym OS — Phase 5: super-admin SaaS billing/dashboard fields
--
-- The super-admin console (Phase 3) only ever tracked a gym's billing_status
-- (active/trial/suspended/cancelled) and a free-text plan_tier — nothing
-- about Livnexa Care's own commercial relationship with that gym: when their
-- Gym OS subscription is due for renewal, what they've actually paid so far,
-- or what resource caps they've been sold. Adding that here rather than a
-- separate table — one row per tenant, edited the same way plan_tier/
-- billing_status already are, from the same admin screen.
--
-- subscription_expires_at: set manually by the super-admin (no payment
--   gateway exists to derive this automatically). Null = not tracked yet
--   (every existing tenant, including Control Gym, starts this way — no
--   fabricated renewal date).
-- amount_paid: cumulative total the gym has paid Livnexa Care for the
--   software — distinct from (and unrelated to) that gym's own member
--   payments, which already live in public.payment. Incremented via
--   POST /admin/tenants/{id}/payments rather than being directly PATCHable,
--   so the super-admin enters "they just paid X" instead of having to
--   compute the new running total themselves.
-- member_limit / device_limit / branch_limit: resource caps allocated to
--   the tenant. Display-only for now (shown as "used / limit" on the admin
--   screen) — NOT enforced against member/device/branch creation. Null =
--   unlimited/not set.

alter table public.tenant
  add column subscription_expires_at date,
  add column amount_paid numeric(12, 2) not null default 0 check (amount_paid >= 0),
  add column member_limit integer check (member_limit is null or member_limit > 0),
  add column device_limit integer check (device_limit is null or device_limit > 0),
  add column branch_limit integer check (branch_limit is null or branch_limit > 0);
