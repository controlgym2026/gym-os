-- Gym OS — human-readable sequential Member ID.
--
-- A permanent per-gym number, distinct from the UUID primary key and the
-- 8-char id prefix the UI already shows ("#F4D6E1AD") — this is the number
-- staff actually want to call a member by. Scoped per tenant_id (each gym
-- gets its own 1, 2, 3..., not a platform-wide sequence) and assigned once,
-- never reused or reshuffled by later inserts/deletes.
--
-- One-time backfill: every existing member (including soft-deleted — a
-- cancelled membership shouldn't free up its number for reuse) gets
-- numbered 1..N alphabetically by name, per tenant, as requested. Every
-- member inserted from here on gets the next number for their tenant
-- automatically, in creation order — NOT re-sorted alphabetically, which
-- would make existing members' numbers shift every time someone new signs
-- up and defeat the point of a stable ID.

alter table public.member add column member_number integer;

do $$
begin
  with ranked as (
    select id, row_number() over (partition by tenant_id order by name) as rn
    from public.member
  )
  update public.member m
  set member_number = ranked.rn
  from ranked
  where ranked.id = m.id;
end $$;

alter table public.member alter column member_number set not null;

create unique index member_tenant_id_member_number_key on public.member (tenant_id, member_number);

-- Auto-assigns the next number for new rows that don't already specify one
-- — covers every insertion path (manual Add Member, CSV import, scripts)
-- with no application code changes, since none of them set member_number
-- today. Within one multi-row INSERT (e.g. a 200-row CSV import batch),
-- each row's trigger invocation sees the numbers already assigned earlier
-- in that same statement, so a batch numbers itself correctly in one pass.
create or replace function public.assign_member_number()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
  if new.member_number is null then
    select coalesce(max(member_number), 0) + 1 into new.member_number
    from public.member
    where tenant_id = new.tenant_id;
  end if;
  return new;
end;
$$;

create trigger member_assign_number
  before insert on public.member
  for each row
  execute function public.assign_member_number();
