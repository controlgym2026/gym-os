-- Gym OS — Phase 2: biometric attendance (ZKTeco ADMS push), one branch
--
-- `device` already exists from 20260905150522_init_schema.sql — extended
-- here, not duplicated. `attendance_source` already has 'biometric' in its
-- enum from that same migration, so no enum change needed for attendance.

-- ---------------------------------------------------------------------------
-- device: serial -> serial_number (globally unique, not per-tenant — the
-- ADMS protocol identifies a device ONLY by serial number with no tenant
-- context in the request, so the serial has to resolve to exactly one
-- tenant/branch on its own), last_sync_at -> last_seen_at, + label, +status
-- ---------------------------------------------------------------------------
alter table public.device rename column serial to serial_number;
alter table public.device rename column last_sync_at to last_seen_at;

-- Drop the old (tenant_id, serial) uniqueness — name looked up rather than
-- assumed, same defensive pattern as the member phone constraint in
-- 20260922131339_phase1_member_management.sql.
do $$
declare
  con text;
begin
  select conname into con
  from pg_constraint
  where conrelid = 'public.device'::regclass
    and contype = 'u'
    and conkey = (
      select array_agg(attnum order by attnum)
      from pg_attribute
      where attrelid = 'public.device'::regclass
        and attname in ('tenant_id', 'serial_number')
    );
  if con is not null then
    execute format('alter table public.device drop constraint %I', con);
  end if;
end $$;

alter table public.device add constraint device_serial_number_key unique (serial_number);

alter table public.device add column label text;

create type public.device_status as enum ('active', 'inactive');
alter table public.device add column status public.device_status not null default 'active';

-- ---------------------------------------------------------------------------
-- member: biometric consent. biometric_ref (already exists) stores only the
-- device-assigned numeric PIN — nothing else is added here that could hold a
-- raw template or face image.
-- ---------------------------------------------------------------------------
alter table public.member
  add column biometric_consent boolean not null default false,
  add column biometric_consent_at timestamptz;

-- DB-level backstop (application also enforces this): a biometric_ref can't
-- be set without consent.
alter table public.member
  add constraint member_biometric_consent_required
  check (biometric_ref is null or biometric_consent);

-- ---------------------------------------------------------------------------
-- attendance_unmatched: push records that don't map to a known member, PLUS
-- (dual purpose, see apps/api/biometric.py) a matched member whose check-in
-- was rejected (e.g. subscription not ACTIVE) — there's no staff present at
-- a biometric terminal to see an HTTP error, so both cases need to land
-- somewhere a human can review them. `member_id` is null for the former,
-- set for the latter; `reason` distinguishes them.
-- ---------------------------------------------------------------------------
create table public.attendance_unmatched (
  id             uuid primary key default gen_random_uuid(),
  tenant_id      uuid not null references public.tenant (id) on delete cascade,
  device_id      uuid not null references public.device (id) on delete cascade,
  member_id      uuid references public.member (id) on delete set null,
  raw_pin        text not null,
  raw_timestamp  text not null,
  reason         text not null,
  received_at    timestamptz not null default now()
);
create index attendance_unmatched_tenant_id_idx on public.attendance_unmatched (tenant_id);
create index attendance_unmatched_device_id_idx on public.attendance_unmatched (device_id);
create index attendance_unmatched_received_at_idx on public.attendance_unmatched (received_at);

alter table public.attendance_unmatched enable row level security;
create policy tenant_isolation on public.attendance_unmatched
  for all to authenticated
  using (tenant_id = public.current_tenant_id())
  with check (tenant_id = public.current_tenant_id());
