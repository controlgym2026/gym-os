"""Live regression suite — members export (GET /members/export).

Runs against a REAL API + Supabase project using only throwaway data it
creates itself, and deletes all of it at the end (also on failure):

  * QA-EXPORT-SMALL-<run>  ~250 members, staff in every role
      - export row count == GET /members total for: no filter, search, status,
        plan, photo, two/three combined (both CSV and XLSX)
      - formula-injection member "=HYPERLINK(...)" neutralised in both formats
      - phone leading zero kept (xlsx text cell, csv ="…")
      - trainer / front_desk -> 403, owner / manager -> 200
      - audit rows in data_export_log match what was exported
      - rate limit: 11th export in an hour -> 429
  * QA-EXPORT-SCALE-<run>  5,000 members (scale timing, cross-tenant, 402)
      - full export CSV + XLSX: time, size, rows
      - cross-tenant isolation both ways
      - suspended tenant -> 402
  * members_export() RPC is not callable with the public anon key.

It never reads or writes any tenant it did not create in this run (every
delete is by the ids it created, and tenant names are checked first).

Usage (from the repo root, API venv):
  python scripts/live_regression_export.py --api https://gym-os-api-mlp9.onrender.com
  python scripts/live_regression_export.py --api http://127.0.0.1:8000 --pid <uvicorn pid>
Env: SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, SUPABASE_ANON_KEY (read from
apps/api/.env if not already set).
"""

import argparse
import csv
import io
import os
import random
import re
import secrets
import sys
import time
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import httpx
import openpyxl
from dotenv import load_dotenv
from supabase import create_client

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / "apps/api/.env")

RUN = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S") + "-" + secrets.token_hex(2)
PREFIX = "QA-EXPORT-"
INJECTION = '=HYPERLINK("http://example.com/x","click me")'
PASSWORD = secrets.token_urlsafe(18) + "aA1!"

results: list[tuple[bool, str]] = []


def check(ok: bool, label: str) -> bool:
    results.append((bool(ok), label))
    print(f"  {'PASS' if ok else 'FAIL'}  {label}", flush=True)
    return bool(ok)


def peak_working_set_mb(pid: int) -> float | None:
    """Windows: the process's peak working set (high-water RSS), via Win32."""
    if os.name != "nt":
        return None
    import ctypes
    from ctypes import wintypes

    class PMC(ctypes.Structure):
        _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD), ("PeakWorkingSetSize", ctypes.c_size_t),
                    ("WorkingSetSize", ctypes.c_size_t), ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPagedPoolUsage", ctypes.c_size_t), ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaNonPagedPoolUsage", ctypes.c_size_t), ("PagefileUsage", ctypes.c_size_t),
                    ("PeakPagefileUsage", ctypes.c_size_t)]

    h = ctypes.windll.kernel32.OpenProcess(0x0400 | 0x0010, False, pid)
    if not h:
        return None
    pmc = PMC()
    pmc.cb = ctypes.sizeof(PMC)
    ok = ctypes.windll.psapi.GetProcessMemoryInfo(h, ctypes.byref(pmc), pmc.cb)
    ctypes.windll.kernel32.CloseHandle(h)
    return pmc.PeakWorkingSetSize / 1024 / 1024 if ok else None


class Live:
    def __init__(self, api: str):
        self.api = api.rstrip("/")
        self.url = os.environ["SUPABASE_URL"].strip()
        self.anon = os.environ["SUPABASE_ANON_KEY"].strip()
        self.db = create_client(self.url, os.environ["SUPABASE_SERVICE_ROLE_KEY"].strip())
        self.http = httpx.Client(timeout=180)
        self.tenants: list[str] = []
        self.users: list[str] = []

    # --- setup -----------------------------------------------------------------
    def tenant(self, label: str) -> str:
        name = f"{PREFIX}{label}-{RUN}"
        tid = self.db.table("tenant").insert({"name": name, "billing_status": "active"}).execute().data[0]["id"]
        self.tenants.append(tid)
        return tid

    def staff(self, tenant_id: str, role: str) -> str:
        email = f"qa-export-{RUN}-{role}-{secrets.token_hex(2)}@example.com"
        user = self.db.auth.admin.create_user({"email": email, "password": PASSWORD, "email_confirm": True}).user
        self.users.append(user.id)
        self.db.table("staff").insert({"id": user.id, "tenant_id": tenant_id, "role": role}).execute()
        sess = create_client(self.url, self.anon).auth.sign_in_with_password({"email": email, "password": PASSWORD}).session
        return sess.access_token

    def insert(self, table: str, rows: list[dict], batch: int = 500) -> list[dict]:
        out = []
        for i in range(0, len(rows), batch):
            out += self.db.table(table).insert(rows[i : i + batch]).execute().data
        return out

    def seed_members(self, tenant_id: str, n: int, *, name_prefix: str, rng: random.Random) -> dict:
        plans = self.insert("membership_plan", [
            {"tenant_id": tenant_id, "name": nm, "price": 1000 * (i + 1), "duration_days": d}
            for i, (nm, d) in enumerate((("Monthly", 30), ("Quarterly", 90), ("Yearly", 365)))
        ])
        today = date.today()
        first_names = ["Ravi", "Priya", "रवि", "Sunita", "Anil", "Mohd", "Kavya", "Arjun"]
        members = []
        for i in range(n):
            nm = f"{name_prefix} {rng.choice(first_names)} {i}"
            if i == 0:
                nm = INJECTION
            members.append({
                "tenant_id": tenant_id, "name": nm, "phone": f"0{rng.randint(6, 9)}{i:09d}",
                "email": f"m{i}@qa.example.com" if i % 2 else None,
                "photo_url": f"{tenant_id}/qa-{i}.jpg" if i % 3 == 0 else None,
                "biometric_ref": str(10000 + i) if i % 4 == 0 else None, "biometric_consent": i % 4 == 0,
            })
        members = self.insert("member", members)
        subs = []
        for i, m in enumerate(members):
            kind = i % 7
            if kind == 6:
                continue  # no plan
            end = {0: today + timedelta(days=40), 1: today + timedelta(days=3), 2: today - timedelta(days=10),
                   3: today + timedelta(days=90), 4: today - timedelta(days=200), 5: today + timedelta(days=20)}[kind]
            subs.append({"tenant_id": tenant_id, "member_id": m["id"], "plan_id": plans[i % 3]["id"],
                         "start_date": (end - timedelta(days=30)).isoformat(), "end_date": end.isoformat(),
                         "status": "FROZEN" if kind == 5 else ("EXPIRED" if kind == 4 else "ACTIVE"),
                         "due_amount": (i % 4) * 250})
        subs = self.insert("subscription", subs)
        pays = [{"tenant_id": tenant_id, "member_id": s["member_id"], "subscription_id": s["id"], "amount": 999.5,
                 "status": "completed", "method": "cash", "transaction_type": "renewal"} for s in subs[::2]]
        self.insert("payment", pays)
        visits = [{"tenant_id": tenant_id, "member_id": m["id"], "source": "manual"} for m in members[::3]]
        self.insert("attendance", visits)
        return {"plans": plans, "members": members}

    # --- API calls ------------------------------------------------------------------
    def list_total(self, token: str, params: dict) -> int:
        r = self.http.get(f"{self.api}/members", params={**params, "page_size": 1}, headers={"Authorization": f"Bearer {token}"})
        r.raise_for_status()
        return r.json()["total"]

    def export(self, token: str, fmt: str, params: dict) -> httpx.Response:
        return self.http.get(f"{self.api}/members/export", params={**params, "format": fmt},
                             headers={"Authorization": f"Bearer {token}"})

    # --- cleanup -----------------------------------------------------------------------
    def cleanup(self):
        print("\nCleanup:")
        for tid in self.tenants:
            row = self.db.table("tenant").select("id,name").eq("id", tid).execute().data
            if row and not row[0]["name"].startswith(PREFIX):
                print(f"  REFUSING to delete non-QA tenant {tid}")
                continue
            # Explicit child-first order: subscription.plan_id is ON DELETE
            # RESTRICT, so relying on the tenant cascade alone can fail.
            for table in ("payment", "attendance", "subscription", "member", "membership_plan", "data_export_log", "staff"):
                self.db.table(table).delete().eq("tenant_id", tid).execute()
            self.db.table("tenant").delete().eq("id", tid).execute()
        for uid in self.users:
            try:
                self.db.auth.admin.delete_user(uid)
            except Exception as exc:  # noqa: BLE001
                print(f"  could not delete auth user {uid}: {exc}")
        left_t = self.db.table("tenant").select("id").in_("id", self.tenants).execute().data if self.tenants else []
        left_m = self.db.table("member").select("id").in_("tenant_id", self.tenants).limit(1).execute().data if self.tenants else []
        left_l = self.db.table("data_export_log").select("id").in_("tenant_id", self.tenants).limit(1).execute().data if self.tenants else []
        print(f"  tenants left: {len(left_t)}, members left: {len(left_m)}, export logs left: {len(left_l)}, auth users deleted: {len(self.users)}")


def csv_rows(resp: httpx.Response) -> list[list[str]]:
    return list(csv.reader(io.StringIO(resp.content.decode("utf-8-sig"))))


def xlsx_book(resp: httpx.Response):
    return openpyxl.load_workbook(io.BytesIO(resp.content))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", required=True)
    ap.add_argument("--members", type=int, default=5000)
    ap.add_argument("--small", type=int, default=250)
    ap.add_argument("--pid", type=int, help="local uvicorn pid, to report its peak memory")
    args = ap.parse_args()

    live = Live(args.api)
    rng = random.Random(7)
    print(f"Run {RUN} against {live.api}")
    try:
        print("\nSetup:")
        t0 = time.perf_counter()
        a = live.tenant("SMALL")
        tok = {r: live.staff(a, r) for r in ("owner", "manager", "trainer", "front_desk")}
        tok_rl = live.staff(a, "manager")  # dedicated user for the rate-limit test
        small = live.seed_members(a, args.small, name_prefix="QA-SMALL", rng=rng)
        b = live.tenant("SCALE")
        tok_b = live.staff(b, "owner")
        live.seed_members(b, args.members, name_prefix="QA-SCALE", rng=rng)
        print(f"  seeded {args.small} + {args.members} members in {time.perf_counter() - t0:.1f}s")

        print("\nAnon access to the RPC:")
        r = httpx.post(f"{live.url}/rest/v1/rpc/members_export", headers={"apikey": live.anon, "Content-Type": "application/json"},
                       json={"p_tenant_id": a, "p_today": date.today().isoformat()})
        check(r.status_code != 200, f"anon key cannot call members_export (HTTP {r.status_code})")

        print("\nRow count parity with GET /members (SMALL tenant):")
        p = small["plans"]
        combos = {
            "no filter": {},
            "search 'ravi'": {"q": "ravi"},
            "status expired": {"filter": "expired"},
            "plan Quarterly": {"plan_id": p[1]["id"]},
            "photo has_photo": {"photo": "has_photo"},
            "due + Monthly": {"filter": "due", "plan_id": p[0]["id"]},
            "expiring + search + no_photo": {"filter": "expiring", "q": "a", "photo": "no_photo"},
        }
        owner_exports = []
        files = {}
        for label, params in combos.items():
            total = live.list_total(tok["owner"], params)
            rc = live.export(tok["owner"], "csv", params)
            rows_csv = len(csv_rows(rc)) - 1 if rc.status_code == 200 else -1
            owner_exports.append((params, total))
            rx = live.export(tok["manager"], "xlsx", params)
            rows_x = xlsx_book(rx)["Members"].max_row - 1 if rx.status_code == 200 else -1
            check(rows_csv == total == rows_x == int(rc.headers.get("x-export-row-count", -1)),
                  f"{label}: list={total} csv={rows_csv} xlsx={rows_x}")
            files[label] = (rc, rx)

        print("\nFile format (SMALL, no filter):")
        rc, rx = files["no filter"]
        check(rc.content.startswith(b"\xef\xbb\xbf"), "CSV starts with UTF-8 BOM")
        cd = rc.headers.get("content-disposition", "")
        check(re.search(r'filename="members_qa-export-small-[a-z0-9-]+_\d{4}-\d{2}-\d{2}\.csv"', cd) is not None, f"CSV file name ({cd})")
        rows = csv_rows(rc)
        header, body = rows[0], rows[1:]
        check(header[:3] == ["Member ID", "Name", "Phone"] and header[-1] == "Biometric enrolled" and len(header) == 17, "CSV column order")
        inj = [r for r in body if "HYPERLINK" in r[1]]
        check(len(inj) == 1 and inj[0][1] == "'" + INJECTION, "CSV: =HYPERLINK name neutralised with leading quote")
        check(all(r[2].startswith('="0') for r in body if r[2]), "CSV: phones wrapped as =\"0…\" (leading zero safe)")
        check(all(re.fullmatch(r"\d{2}-\d{2}-\d{4}", r[9]) for r in body if r[9]), "CSV: dates DD-MM-YYYY")
        check(all(re.fullmatch(r"\d+\.\d{2}", r[12]) for r in body if r[12]), "CSV: amounts with two decimals")
        check(any("रवि" in r[1] for r in body), "CSV: non-English names intact")
        wb = xlsx_book(rx)
        ws = wb["Members"]
        check(wb.sheetnames == ["Members", "Export info"], "XLSX sheets: Members + Export info")
        check(ws.freeze_panes == "A2" and ws.auto_filter.ref is not None and ws["A1"].font.bold, "XLSX: bold frozen header + autofilter")
        cells = {row[1].value: row for row in ws.iter_rows(min_row=2)}
        ic = cells.get(INJECTION)
        check(ic is not None and ic[1].data_type == "s" and ic[1].quotePrefix, "XLSX: =HYPERLINK stored as quote-prefixed string, not a formula")
        phones = [row[2] for row in ws.iter_rows(min_row=2) if row[2].value]
        check(all(c.data_type == "s" and c.value.startswith("0") for c in phones), "XLSX: phones are text with leading zero")
        ends = [row[9] for row in ws.iter_rows(min_row=2) if row[9].value]
        check(all(isinstance(c.value, datetime) and c.number_format == "dd-mm-yyyy" for c in ends), "XLSX: real date cells, dd-mm-yyyy")
        info = {row[0].value: row[1].value for row in wb["Export info"].iter_rows()}
        check(info.get("Rows") == str(ws.max_row - 1) and "IST" in (info.get("Exported at") or ""), f"XLSX Export info: {info}")

        print("\nRoles (SMALL):")
        for role in ("trainer", "front_desk"):
            check(live.export(tok[role], "csv", {}).status_code == 403, f"{role} -> 403")
        check(files["no filter"][1].status_code == 200, "manager -> 200 (xlsx above)")

        print("\nAudit log:")
        logs = live.db.table("data_export_log").select("*").eq("tenant_id", a).execute().data
        owner_id = live.db.table("staff").select("id").eq("tenant_id", a).eq("role", "owner").execute().data[0]["id"]
        owner_logs = [l for l in logs if l["staff_id"] == owner_id]
        check(len(owner_logs) == len(combos) and all(l["format"] == "csv" for l in owner_logs), f"{len(owner_logs)} owner CSV exports logged")
        expected = sorted(t for _, t in owner_exports)
        check(sorted(l["row_count"] for l in owner_logs) == expected, "logged row_counts match the exports")
        check(any(l["filters"] == {"filter": "due", "plan_id": p[0]["id"]} for l in owner_logs), "filters stored as jsonb")

        print("\nRate limit (dedicated manager):")
        codes = [live.export(tok_rl, "csv", {"q": "no-such-member-xyz"}).status_code for _ in range(11)]
        check(codes[:10] == [200] * 10 and codes[10] == 429, f"10 allowed then 429 ({codes})")

        print(f"\nScale ({args.members} members, SCALE tenant):")
        for fmt in ("csv", "xlsx"):
            t = time.perf_counter()
            r = live.export(tok_b, fmt, {})
            dt = time.perf_counter() - t
            n = (len(csv_rows(r)) - 1) if fmt == "csv" else (openpyxl.load_workbook(io.BytesIO(r.content), read_only=True)["Members"].max_row - 1)
            check(r.status_code == 200 and n == args.members, f"{fmt}: {n} rows, {len(r.content) / 1024:.0f} KB in {dt:.2f}s")
            if fmt == "csv":
                scale_csv = r
        list_total_b = live.list_total(tok_b, {})
        check(list_total_b == args.members, f"unfiltered list total = {list_total_b}")
        # Filtered list totals above PostgREST's max_rows (1000): the list used
        # to cap these (639 vs 3,214 for "due" at 5,000 members).
        for label, params in (("due", {"filter": "due"}), ("expired", {"filter": "expired"}),
                              ("has_photo", {"photo": "has_photo"}), ("active + no_photo", {"filter": "active", "photo": "no_photo"})):
            lf = live.list_total(tok_b, params)
            ef_ = int(live.export(tok_b, "csv", params).headers["x-export-row-count"])
            check(lf == ef_, f"filtered list total at {args.members} members, {label}: list={lf} export={ef_}")
        if args.pid:
            print(f"  INFO  local API process peak working set: {peak_working_set_mb(args.pid):.0f} MB")

        print("\nCross-tenant isolation:")
        names_b = "\n".join(r[1] for r in csv_rows(scale_csv)[1:])
        check("QA-SMALL" not in names_b, "SCALE export contains no SMALL members")
        check(not any("QA-SCALE" in r[1] for r in csv_rows(files["no filter"][0])[1:]), "SMALL export contains no SCALE members")
        r = live.export(tok_b, "csv", {"plan_id": p[0]["id"]})  # SMALL's plan id from SCALE's owner
        check(r.status_code == 200 and r.headers["x-export-row-count"] == "0", "other tenant's plan_id yields 0 rows")

        print("\nSuspended tenant:")
        live.db.table("tenant").update({"billing_status": "suspended"}).eq("id", b).execute()
        check(live.export(tok_b, "csv", {}).status_code == 402, "suspended tenant -> 402")
        live.db.table("tenant").update({"billing_status": "active"}).eq("id", b).execute()
    finally:
        live.cleanup()

    failed = [l for ok, l in results if not ok]
    print(f"\n{len(results) - len(failed)}/{len(results)} checks passed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
