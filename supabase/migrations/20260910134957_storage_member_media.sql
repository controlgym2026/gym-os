-- Gym OS — Phase 4: Supabase Storage bucket for member media
--
-- Bucket `member-media` holds member photos / biometric reference images.
-- Objects are keyed as  {tenant_id}/members/{member_id}/{filename}  — the first
-- path segment is the tenant UUID, which is what the policies below gate on.
--
-- Access model mirrors the database tables: one policy per verb, scoped to the
-- `authenticated` role, matching (storage.foldername(name))[1] against
-- public.current_tenant_id() (auth.uid() -> staff.tenant_id). The `service_role`
-- used by the FastAPI backend has BYPASSRLS and brokers uploads/downloads
-- freely; `anon` gets nothing.
--
-- RLS is already enabled on storage.objects by Supabase — not re-enabled here.

-- ---------------------------------------------------------------------------
-- Bucket (private; 5 MiB cap; images only)
-- ---------------------------------------------------------------------------
insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values (
  'member-media',
  'member-media',
  false,
  5242880,  -- 5 * 1024 * 1024
  array['image/jpeg', 'image/png', 'image/webp']
)
on conflict (id) do nothing;

-- ---------------------------------------------------------------------------
-- Policies on storage.objects — tenant_id isolation for the authenticated role
-- (drop-if-exists so this is re-runnable and supersedes any dashboard-created
--  policies of the same name)
-- ---------------------------------------------------------------------------
drop policy if exists "member-media tenant read"   on storage.objects;
drop policy if exists "member-media tenant insert" on storage.objects;
drop policy if exists "member-media tenant update" on storage.objects;
drop policy if exists "member-media tenant delete" on storage.objects;

create policy "member-media tenant read"
on storage.objects for select to authenticated
using (
  bucket_id = 'member-media'
  and (storage.foldername(name))[1] = public.current_tenant_id()::text
);

create policy "member-media tenant insert"
on storage.objects for insert to authenticated
with check (
  bucket_id = 'member-media'
  and (storage.foldername(name))[1] = public.current_tenant_id()::text
);

create policy "member-media tenant update"
on storage.objects for update to authenticated
using (
  bucket_id = 'member-media'
  and (storage.foldername(name))[1] = public.current_tenant_id()::text
)
with check (
  bucket_id = 'member-media'
  and (storage.foldername(name))[1] = public.current_tenant_id()::text
);

create policy "member-media tenant delete"
on storage.objects for delete to authenticated
using (
  bucket_id = 'member-media'
  and (storage.foldername(name))[1] = public.current_tenant_id()::text
);
