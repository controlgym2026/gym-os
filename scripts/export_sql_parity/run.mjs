// Applies every repo migration (except the Storage one, which needs Supabase's
// storage schema) to an in-process PGlite Postgres, loads dataset.json, runs
// members_export() for each filter combo and writes results.json.
import { PGlite } from "@electric-sql/pglite";
import { pg_trgm } from "@electric-sql/pglite/contrib/pg_trgm";
import fs from "node:fs";
import path from "node:path";

const [, , migDir, datasetPath, outPath] = process.argv;
const db = new PGlite({ extensions: { pg_trgm } });

// Minimal Supabase shims: roles, auth schema, auth.uid().
await db.exec(`
  create role anon; create role authenticated; create role service_role;
  create schema auth;
  create table auth.users (id uuid primary key, email text);
  create function auth.uid() returns uuid language sql stable as $$ select null::uuid $$;
  -- Supabase default privileges on public functions (the reason the migration revokes explicitly)
  alter default privileges in schema public grant execute on functions to anon, authenticated, service_role;
`);

const files = fs.readdirSync(migDir).filter((f) => f.endsWith(".sql")).sort();
for (const f of files) {
  if (f.includes("storage_member_media")) continue;
  try {
    await db.exec(fs.readFileSync(path.join(migDir, f), "utf8"));
  } catch (e) {
    console.error("MIGRATION FAILED:", f, e.message);
    process.exit(1);
  }
}
console.log("migrations applied:", files.length - 1);

// Privilege check: anon/authenticated must not be able to execute the function.
const priv = await db.query(`
  select r as role, has_function_privilege(r, 'public.members_export(uuid,date,text,text,text,uuid,integer,integer,integer)', 'execute') as can
  from unnest(array['anon','authenticated','service_role']) r`);
console.log("execute privilege:", JSON.stringify(priv.rows));

const ds = JSON.parse(fs.readFileSync(datasetPath, "utf8"));
const order = ["tenant", "staff_users", "staff", "membership_plan", "member", "subscription", "payment", "attendance"];
for (const t of order) {
  const rows = ds[t] || [];
  const table = t === "staff_users" ? "auth.users" : `public.${t}`;
  for (const r of rows) {
    const cols = Object.keys(r);
    const vals = cols.map((c) => r[c]);
    const ph = cols.map((_, i) => `$${i + 1}`).join(",");
    await db.query(`insert into ${table} (${cols.map((c) => `"${c}"`).join(",")}) values (${ph})`, vals);
  }
}
// member_number trigger assigns numbers; fetch them so Python can compare.
const nums = await db.query(`select id, member_number from public.member`);

const results = {};
for (const c of ds.combos) {
  const all = [];
  let offset = 0;
  let total = null;
  // page small on purpose to exercise paging
  for (;;) {
    const r = await db.query(
      `select m.id as member_id, e.* from public.members_export($1,$2,$3,$4,$5,$6,7,$7,$8) e
       left join public.member m on m.member_number = e.member_number and m.tenant_id = $1 and m.deleted_at is null`,
      [c.tenant_id, ds.today, c.search, c.filter, c.photo, c.plan_id, ds.page_size, offset],
    );
    if (r.rows.length === 0) break;
    total = Number(r.rows[0].total_count);
    all.push(...r.rows);
    offset += r.rows.length;
    if (offset >= total) break;
  }
  results[c.key] = { total: total ?? 0, rows: all };
}

// EXPLAIN on the biggest combo for the report
const ex = await db.query(`explain select * from public.members_export($1,$2,null,null,null,null,7,1000,0)`, [ds.combos[0].tenant_id, ds.today]);

fs.writeFileSync(
  outPath,
  JSON.stringify({ results, member_numbers: nums.rows, explain: ex.rows }, (k, v) => (typeof v === "bigint" ? Number(v) : v)),
);
console.log("combos run:", Object.keys(results).length);
