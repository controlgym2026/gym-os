-- Gym OS — indexes backing the paginated members list
--
-- member already had member_tenant_id_idx (plain tenant_id) and the
-- partial unique (tenant_id, phone) from Phase 1 — neither helps the two
-- queries GET /members actually runs:
--   1. the default (no search) list: WHERE tenant_id = ? AND deleted_at IS
--      NULL ORDER BY created_at DESC — tenant_id alone doesn't help the
--      sort; Postgres still sorts the whole matching set in memory.
--   2. search: WHERE ... AND (name ILIKE '%x%' OR phone ILIKE '%x%') — a
--      leading '%' makes a plain B-tree index on name/phone useless for
--      ILIKE no matter what; only a trigram index can accelerate this.

-- 1. Composite index for the default list query (filter + sort together).
create index member_tenant_id_created_at_idx
  on public.member (tenant_id, created_at desc)
  where deleted_at is null;

-- 2. Trigram indexes so ILIKE '%...%' on name/phone can use an index scan
-- instead of a sequential scan.
create extension if not exists pg_trgm;
create index member_name_trgm_idx on public.member using gin (name gin_trgm_ops);
create index member_phone_trgm_idx on public.member using gin (phone gin_trgm_ops);
