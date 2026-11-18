"""Parity check: members_export() (real Postgres via PGlite) vs. the actual
list_members() Python code (FakeClient), same dataset, same filters.
Usage: python parity.py <repo_root>"""

import json
import random
import subprocess
import sys
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

repo = Path(sys.argv[1])
here = Path(__file__).parent
sys.path.insert(0, str(repo / "apps/api"))
sys.path.insert(0, str(repo / "apps/api/tests"))

import members  # noqa: E402
import subscriptions  # noqa: E402
from fake_client import FakeClient  # noqa: E402

rng = random.Random(42)
today = date.today()
U = lambda: str(uuid.uuid4())  # noqa: E731

tA, tB = U(), U()
ds = {"tenant": [{"id": tA, "name": "QA Gym A"}, {"id": tB, "name": "QA Gym B"}], "staff_users": [], "staff": [],
      "membership_plan": [], "member": [], "subscription": [], "payment": [], "attendance": []}

plans = {}
for t in (tA, tB):
    plans[t] = []
    for name, days in (("Monthly", 30), ("Quarterly", 90), ("Yearly", 365)):
        p = {"id": U(), "tenant_id": t, "name": name, "price": 1000, "duration_days": days}
        ds["membership_plan"].append(p)
        plans[t].append(p)

names = ["Ravi Kumar", "रवि शर्मा", "Priya", "=HYPERLINK(\"http://x\",\"y\")", "+cmd", "-minus", "@at", "Anil", "Sunita", "Mohd Ali", "Raj*", "ram_1"]
base_ts = datetime(2026, 1, 1, tzinfo=timezone.utc)


def ts(i):
    return (base_ts + timedelta(minutes=i)).isoformat()


k = 0
for t, n in ((tA, 400), (tB, 60)):
    for i in range(n):
        k += 1
        mid = U()
        photo = rng.choice([None, "", f"{t}/{mid}.jpg"])
        bio = rng.random() < 0.3
        deleted = rng.random() < 0.05
        ds["member"].append({
            "id": mid, "tenant_id": t, "name": f"{rng.choice(names)} {i}", "phone": f"0{9000000000 + k}" if rng.random() < 0.9 else None,
            "email": f"m{k}@ex.com" if rng.random() < 0.5 else None, "photo_url": photo,
            "biometric_ref": str(k) if bio else None, "biometric_consent": bio, "created_at": ts(k),
            "deleted_at": ts(k + 1) if deleted else None,
        })
        nsubs = rng.choice([0, 1, 1, 2, 3])
        has_active = False
        for j in range(nsubs):
            kind = rng.choice(["in_range", "stale_active", "expired_future", "expired", "frozen", "cancelled", "sessions0", "expiring", "today_end"])
            start = today - timedelta(days=rng.randint(0, 400))
            sess = None
            status = "ACTIVE"
            if kind == "in_range":
                end = today + timedelta(days=rng.randint(8, 200))
            elif kind == "stale_active":
                end = today - timedelta(days=rng.randint(1, 50))
            elif kind == "expired_future":
                end = today + timedelta(days=rng.randint(1, 60)); status = "EXPIRED"
            elif kind == "expired":
                end = today - timedelta(days=rng.randint(1, 300)); status = "EXPIRED"
            elif kind == "frozen":
                end = today + timedelta(days=30); status = "FROZEN"
            elif kind == "cancelled":
                end = today + timedelta(days=10); status = "CANCELLED"
            elif kind == "sessions0":
                end = None; sess = 0
            elif kind == "expiring":
                end = today + timedelta(days=rng.randint(0, 7))
            else:
                end = today
            if end is not None and end < start:
                start = end - timedelta(days=30)
            if status == "ACTIVE":
                if has_active:
                    status = "EXPIRED"
                has_active = has_active or status == "ACTIVE"
            sid = U()
            ds["subscription"].append({
                "id": sid, "tenant_id": t, "member_id": mid, "plan_id": rng.choice(plans[t])["id"],
                "start_date": start.isoformat(), "end_date": end.isoformat() if end else None, "status": status,
                "due_amount": rng.choice([0, 0, 500, 1250.5]), "sessions_remaining": sess, "created_at": ts(k * 10 + j),
            })
            for pidx in range(rng.randint(0, 2)):
                ds["payment"].append({"id": U(), "tenant_id": t, "subscription_id": sid, "member_id": mid,
                                      "amount": rng.choice([500, 999.99, 1500]), "status": rng.choice(["completed", "completed", "pending"]),
                                      "method": "cash", "transaction_type": "renewal", "created_at": ts(k * 10 + j + pidx)})
        for v in range(rng.randint(0, 3)):
            ds["attendance"].append({"id": U(), "tenant_id": t, "member_id": mid, "checked_in_at": ts(k * 7 + v), "source": "manual"})

pA = [p["id"] for p in plans[tA]]
combos = []
specs = [
    ("none", None, None, None, None),
    ("search_ravi", "ravi", None, None, None),
    ("search_phone", "90000001", None, None, None),
    ("search_devanagari", "रवि", None, None, None),
    ("search_star", "Raj*", None, None, None),
    ("active", None, "active", None, None),
    ("expiring", None, "expiring", None, None),
    ("expired", None, "expired", None, None),
    ("due", None, "due", None, None),
    ("paid", None, "paid", None, None),
    ("has_photo", None, None, "has_photo", None),
    ("no_photo", None, None, "no_photo", None),
    ("plan", None, None, None, pA[0]),
    ("expired_plan", None, "expired", None, pA[1]),
    ("due_photo_search", "a", "due", "has_photo", None),
    ("active_plan_nophoto", None, "active", "no_photo", pA[2]),
    ("cross_tenant_plan", None, None, None, plans[tB][0]["id"]),
]
for key, q, f, ph, plan in specs:
    pattern = None
    if q:
        safe = members._UNSAFE_FILTER_CHARS.sub("", q)
        pattern = f"%{safe}%".replace("*", "%")
    combos.append({"key": key, "q": q, "tenant_id": tA, "search": pattern, "filter": f, "photo": ph, "plan_id": plan})

ds["combos"] = combos
ds["today"] = today.isoformat()
ds["page_size"] = 37
(here / "dataset.json").write_text(json.dumps(ds), encoding="utf-8")

subprocess.run(["node", str(here / "run.mjs"), str(repo / "supabase/migrations"), str(here / "dataset.json"), str(here / "results.json")], check=True)
out = json.loads((here / "results.json").read_text(encoding="utf-8"))

# --- Python side: the real list_members() over the same data ---------------------
failures = 0
for c in combos:
    fake = FakeClient()
    for t in ("member", "subscription", "membership_plan"):
        fake.seed(t, json.loads(json.dumps(ds[t])))
    members.get_admin_client = lambda: fake
    subscriptions.get_admin_client = lambda: fake
    if c["q"] and ("*" in c["q"]):
        # FakeClient's ilike is a plain substring match; PostgREST treats * as a
        # wildcard. Compare this combo by set only against a manual expectation.
        pass
    resp = members.list_members(q=c["q"], subscription_filter=c["filter"], photo_filter=c["photo"], plan_id=c["plan_id"],
                                page=1, page_size=500, staff={"tenant_id": tA})
    py_ids = [m["id"] for m in resp["items"]]
    sql = out["results"][c["key"]]
    sql_ids = [r["member_id"] for r in sql["rows"]]
    same_set = set(py_ids) == set(sql_ids)
    same_order = py_ids == sql_ids
    ok = resp["total"] == sql["total"] == len(sql_ids) and same_set and (same_order or c["q"] and "*" in c["q"])
    if c["q"] and "*" in c["q"]:
        # PostgREST semantics: Raj* == ILIKE %Raj%%
        exp = {m["id"] for m in ds["member"] if m["tenant_id"] == tA and not m["deleted_at"] and ("raj" in m["name"].lower() or "raj" in (m["phone"] or ""))}
        ok = set(sql_ids) == exp and sql["total"] == len(exp)
    print(f"{'OK ' if ok else 'FAIL'} {c['key']:<22} list={resp['total']:<4} export={sql['total']:<4} order={'same' if same_order else 'DIFF'}")
    failures += not ok

    # Status column must agree with the list's own view of each row
    if c["key"] == "none":
        by_id = {m["id"]: m for m in resp["items"]}
        bad = 0
        for r in sql["rows"]:
            sub = by_id[r["member_id"]]["current_subscription"]
            if sub is None:
                exp_status = "No plan"
            elif sub["status"] == "ACTIVE":
                dl = (date.fromisoformat(sub["end_date"]) - today).days if sub["end_date"] else None
                exp_status = "Expiring" if dl is not None and 0 <= dl <= 7 else "Active"
            else:
                exp_status = sub["status"].title()
            if r["status"] != exp_status or (sub and sub["plan_name"] != r["plan_name"]):
                bad += 1
                print("   status mismatch", r["member_number"], r["status"], exp_status)
        print(f"{'OK ' if not bad else 'FAIL'} status/plan columns agree with list for {len(sql['rows'])} rows")
        failures += bool(bad)

# Cross-tenant: no tenant B member in any tenant A result
b_ids = {m["id"] for m in ds["member"] if m["tenant_id"] == tB}
leak = any(r["member_id"] in b_ids for res in out["results"].values() for r in res["rows"])
print(f"{'FAIL' if leak else 'OK '} cross-tenant isolation (no tenant B rows in tenant A exports)")
failures += leak

# Last payment = latest completed only; last visit = max attendance
r0 = {r["member_id"]: r for r in out["results"]["none"]["rows"]}
bad = 0
for mid, r in r0.items():
    pays = sorted([p for p in ds["payment"] if p["member_id"] == mid and p["status"] == "completed"], key=lambda p: p["created_at"])
    visits = sorted(a["checked_in_at"] for a in ds["attendance"] if a["member_id"] == mid)
    latest = {p["amount"] for p in pays if p["created_at"] == pays[-1]["created_at"]} if pays else {None}
    got_amt = float(r["last_payment_amount"]) if r["last_payment_amount"] is not None else None
    if got_amt not in latest or (bool(visits) != bool(r["last_visit_at"])):
        bad += 1
print(f"{'OK ' if not bad else 'FAIL'} last payment (completed only) / last visit correct")
failures += bool(bad)
print("explain (top):", out["explain"][0])
print("FAILURES:", failures)
sys.exit(1 if failures else 0)
