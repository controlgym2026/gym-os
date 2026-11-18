# members_export() SQL parity check

Applies every migration in `supabase/migrations` (except the Storage one) to an
in-process Postgres (PGlite/WASM — no Docker needed), seeds a randomised
two-tenant dataset, and checks that `members_export()` returns exactly the same
members, in the same order, as the real `list_members()` code in
`apps/api/members.py` for 17 filter combinations. It also checks cross-tenant
isolation, last payment/visit and that anon/authenticated cannot EXECUTE the
function.

```bash
cd scripts/export_sql_parity
npm install --legacy-peer-deps
../../apps/api/.venv/Scripts/python.exe parity.py ../..        # parity
mkdir -p pages && node scale.mjs ../../supabase/migrations pages  # 5,000-member timing
```
