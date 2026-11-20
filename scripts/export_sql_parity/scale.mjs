import { PGlite } from "@electric-sql/pglite";
import { pg_trgm } from "@electric-sql/pglite/contrib/pg_trgm";
import fs from "node:fs"; import path from "node:path";
const [, , migDir, outDir] = process.argv;
const db = new PGlite({ extensions: { pg_trgm } });
await db.exec(`create role anon; create role authenticated; create role service_role; create schema auth;
create table auth.users (id uuid primary key, email text);
create function auth.uid() returns uuid language sql stable as $$ select null::uuid $$;`);
for (const f of fs.readdirSync(migDir).filter(f=>f.endsWith(".sql")).sort()) if (!f.includes("storage")) await db.exec(fs.readFileSync(path.join(migDir,f),"utf8"));
await db.exec(`
insert into tenant(id,name) values ('aaaaaaaa-0000-0000-0000-000000000001','QA Scale Gym');
insert into membership_plan(id,tenant_id,name,price,duration_days) select gen_random_uuid(),'aaaaaaaa-0000-0000-0000-000000000001','Plan '||g,1000,30*g from generate_series(1,4) g;
insert into member(id,tenant_id,name,phone,email,created_at,biometric_ref,biometric_consent)
 select gen_random_uuid(),'aaaaaaaa-0000-0000-0000-000000000001','QA Member '||g||case when g%50=0 then ' रवि' else '' end,'09'||lpad(g::text,9,'0'),'m'||g||'@qa.test', now()-(g||' minutes')::interval, case when g%3=0 then g::text end, g%3=0 from generate_series(1,5000) g;
insert into subscription(tenant_id,member_id,plan_id,start_date,end_date,status,due_amount,created_at)
 select m.tenant_id,m.id,(select id from membership_plan order by random()+0*m.member_number limit 1),current_date-60,current_date+((m.member_number%120)-40),'ACTIVE',(m.member_number%4)*250,now()-interval '1 day' from member m;
insert into payment(tenant_id,member_id,subscription_id,amount,status,method,transaction_type,created_at)
 select s.tenant_id,s.member_id,s.id,1000,'completed','cash','renewal',now()-(g||' days')::interval from subscription s, generate_series(1,3) g;
insert into attendance(tenant_id,member_id,checked_in_at,source) select m.tenant_id,m.id,now()-(g||' days')::interval,'manual' from member m, generate_series(1,10) g;
analyze;`);
const c = await db.query(`select (select count(*) from member) m,(select count(*) from payment) p,(select count(*) from attendance) a`);
console.log("seeded", c.rows[0]);
for (const filt of [null, "expired"]) {
  const t0 = performance.now(); let off = 0, page = 0, total = 0;
  for (;;) { const r = await db.query(`select * from members_export('aaaaaaaa-0000-0000-0000-000000000001',current_date,null,$1,null,null,7,1000,$2)`, [filt, off]);
    if (!r.rows.length) break; total = Number(r.rows[0].total_count);
    if (!filt) fs.writeFileSync(path.join(outDir, `page${page++}.json`), JSON.stringify(r.rows, (k,v)=>typeof v==="bigint"?Number(v):v));
    off += r.rows.length; if (off >= total) break; }
  console.log(`members_export filter=${filt}: ${off} rows of ${total} in ${(performance.now()-t0).toFixed(0)} ms (PGlite/WASM, all pages)`);
}
