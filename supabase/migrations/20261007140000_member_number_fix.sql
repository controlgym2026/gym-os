-- Gym OS — fix member_number: exclude soft-deleted rows from numbering.
--
-- The previous migration (20261007130000) numbered EVERY member row,
-- including soft-deleted ones — and on Control Gym specifically, all of
-- its 301 soft-deleted rows turned out to be administrative artifacts
-- (the full-tenant "delete all members" wipe from weeks earlier, plus a
-- handful of test-member/duplicate cleanups), not real customer
-- cancellations. That polluted the numbering: a name could appear as both
-- an invisible deleted "member #1" and the real active person at #2.
--
-- member_number is now nullable: active members (deleted_at is null) get
-- a clean 1..N per tenant, alphabetical, no gaps; currently-deleted rows
-- get NULL — none of them represent real member history worth a
-- permanent number. Going forward, a real future cancellation keeps
-- whatever number it already had (soft-delete doesn't touch
-- member_number) — only this one-time historical cleanup nulls existing
-- deleted rows out. The assign_member_number() trigger needs no change:
-- SQL's max() already ignores NULLs, so new members correctly continue
-- from the active count (328 next on Control Gym), not from 628.

alter table public.member alter column member_number drop not null;

-- The unique index below enforces uniqueness per-row as this statement
-- runs (it's a bare index, not a deferrable constraint), so reshuffling
-- numbers in place collides mid-update — e.g. renumbering some member to
-- 1 while another row not yet processed still holds 1. Dropping it for
-- the duration of the renumbering and recreating it afterward sidesteps
-- that; the final state (1..N per tenant for active rows, NULL for
-- deleted ones) still can't have a real duplicate.
drop index if exists public.member_tenant_id_member_number_key;

do $$
begin
  update public.member
  set member_number = null
  where deleted_at is not null;

  with ranked as (
    select id, row_number() over (partition by tenant_id order by name) as rn
    from public.member
    where deleted_at is null
  )
  update public.member m
  set member_number = ranked.rn
  from ranked
  where ranked.id = m.id;
end $$;

create unique index member_tenant_id_member_number_key on public.member (tenant_id, member_number);
