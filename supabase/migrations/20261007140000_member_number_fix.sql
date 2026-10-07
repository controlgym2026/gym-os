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

do $$
begin
  with ranked as (
    select id, row_number() over (partition by tenant_id order by name) as rn
    from public.member
    where deleted_at is null
  )
  update public.member m
  set member_number = ranked.rn
  from ranked
  where ranked.id = m.id;

  update public.member
  set member_number = null
  where deleted_at is not null;
end $$;
