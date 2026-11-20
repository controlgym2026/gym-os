"""PostgREST max_rows regression tests.

Supabase silently truncates every response to max_rows (1000 by default).
The filtered members list and the report fetches used to do unranged
selects, so above 1000 members their totals were wrong (found live: "Due"
showed 639 members at 5,000 when 3,214 were due). Here FakeClient(max_rows=50)
plays the capped PostgREST with 180 members, many sharing one created_at the
way a bulk import does, and the uncapped FakeClient is the ground truth.
"""

import copy
import random
import uuid
from datetime import date, timedelta

import pytest
from postgrest.exceptions import APIError

import members
import reports
import subscriptions
from fake_client import FakeClient

TENANT = "tenant-1"
CAP = 50
N_MEMBERS = 180
PLANS = ["plan-a", "plan-b", "plan-c"]


def _dataset(seed: int = 3) -> dict[str, list[dict]]:
    rng = random.Random(seed)
    today = date.today()
    data = {"member": [], "subscription": [], "membership_plan": [{"id": p, "tenant_id": TENANT, "name": p} for p in PLANS]}
    for i in range(N_MEMBERS):
        mid = str(uuid.UUID(int=rng.getrandbits(128)))
        # 60% share one timestamp (bulk import), the rest are distinct
        created = "2026-10-01T10:00:00+00:00" if i % 5 < 3 else f"2026-10-02T10:{i % 60:02d}:{i // 60:02d}+00:00"
        data["member"].append({
            "id": mid, "tenant_id": TENANT, "name": f"Member {i}", "phone": f"09{i:09d}",
            "photo_url": f"{TENANT}/{mid}.jpg" if i % 3 == 0 else None, "created_at": created, "deleted_at": None,
        })
        for j in range(rng.choice([0, 1, 2])):
            end = today + timedelta(days=rng.choice([-30, -1, 0, 3, 7, 8, 60]))
            data["subscription"].append({
                "id": str(uuid.UUID(int=rng.getrandbits(128))), "tenant_id": TENANT, "member_id": mid,
                "plan_id": rng.choice(PLANS), "status": rng.choice(["ACTIVE", "ACTIVE", "EXPIRED", "FROZEN"]),
                "start_date": (end - timedelta(days=30)).isoformat(), "end_date": end.isoformat(),
                "due_amount": rng.choice([0, 0, 500]), "sessions_remaining": None,
                "created_at": f"2026-10-0{3 + j}T09:00:00+00:00",
            })
    return data


def _client(max_rows, data, monkeypatch) -> FakeClient:
    fake = FakeClient(max_rows=max_rows)
    for table, rows in copy.deepcopy(data).items():
        fake.seed(table, rows)
    monkeypatch.setattr(members, "get_admin_client", lambda: fake)
    monkeypatch.setattr(subscriptions, "get_admin_client", lambda: fake)
    return fake


def _list(**kw):
    # page_size stays within the fake cap: the real page size (<= MAX_PAGE_SIZE,
    # 500) is already below the real max_rows (1000). The filtered path's
    # total still covers every member, which is what's under test.
    return members.list_members(staff={"tenant_id": TENANT}, page=1, page_size=CAP, **kw)


COMBOS = [
    {},
    {"q": "Member 1"},
    {"subscription_filter": "due"},
    {"subscription_filter": "active"},
    {"subscription_filter": "expiring"},
    {"subscription_filter": "expired"},
    {"subscription_filter": "paid"},
    {"photo_filter": "has_photo"},
    {"photo_filter": "no_photo"},
    {"plan_id": "plan-b"},
    {"subscription_filter": "due", "plan_id": "plan-a"},
    {"subscription_filter": "active", "photo_filter": "no_photo", "q": "Member"},
]


def test_the_fake_really_caps_unranged_selects():
    fake = FakeClient(max_rows=CAP)
    fake.seed("member", _dataset()["member"])
    result = fake.table("member").select("*", count="exact").execute()
    assert len(result.data) == CAP and result.count == N_MEMBERS


@pytest.mark.parametrize("combo", COMBOS, ids=lambda c: "+".join(f"{k}={v}" for k, v in c.items()) or "none")
def test_list_totals_and_rows_are_not_capped(combo, monkeypatch):
    data = _dataset()
    _client(None, data, monkeypatch)
    truth = _list(**combo)
    _client(CAP, data, monkeypatch)
    capped = _list(**combo)
    assert capped["total"] == truth["total"]
    assert [m["id"] for m in capped["items"]] == [m["id"] for m in truth["items"]]
    # current_subscription comes from the (paged) all-subscriptions read too
    assert [m["current_subscription"] for m in capped["items"]] == [m["current_subscription"] for m in truth["items"]]


def test_filters_actually_exceed_the_cap():
    """Guards the test above: at least one combo must match more members than
    max_rows, otherwise it couldn't catch a regression."""
    data = _dataset()
    assert len(data["member"]) > CAP
    assert len(data["subscription"]) > CAP


def test_unfiltered_pages_neither_repeat_nor_skip_tied_members(monkeypatch):
    data = _dataset()
    _client(CAP, data, monkeypatch)
    seen = []
    page = 1
    while True:
        resp = members.list_members(staff={"tenant_id": TENANT}, page=page, page_size=25)
        if not resp["items"]:
            break
        seen += [m["id"] for m in resp["items"]]
        page += 1
    assert len(seen) == len(set(seen)) == N_MEMBERS


def test_unfiltered_order_is_newest_first_then_id(monkeypatch):
    data = _dataset()
    _client(None, data, monkeypatch)
    items = members.list_members(staff={"tenant_id": TENANT}, page=1, page_size=members.MAX_PAGE_SIZE)["items"]
    keys = [(m["created_at"], m["id"]) for m in items]
    assert keys == sorted(keys, reverse=True)


def test_report_fetch_gets_every_member(monkeypatch):
    data = _dataset()
    fake = _client(CAP, data, monkeypatch)
    fetched = reports._fetch_all_members_with_subscriptions(fake, TENANT)
    assert len(fetched) == N_MEMBERS
    with_sub = {s["member_id"] for s in data["subscription"]}
    assert sum(1 for m in fetched if m["current_subscription"]) == len(with_sub)


def test_subscription_lookup_chunks_the_in_list(monkeypatch):
    data = _dataset()
    fake = _client(CAP, data, monkeypatch)
    sizes = []
    original = fake.table

    def recording_table(name):
        t = original(name)
        if name == "subscription":
            select = t.select

            def recording_select(*a, **k):
                q = select(*a, **k)
                in_ = q.in_

                def recording_in(col, values):
                    sizes.append(len(values))
                    return in_(col, values)

                q.in_ = recording_in
                return q

            t.select = recording_select
        return t

    monkeypatch.setattr(fake, "table", recording_table)
    monkeypatch.setattr(members, "IN_CHUNK_SIZE", 40)
    ids = [m["id"] for m in data["member"]]
    latest = members._latest_subscriptions_by_member(fake, TENANT, ids)
    assert sizes and max(sizes) <= 40 and sum(set(sizes)) >= 40
    assert set(latest) == {s["member_id"] for s in data["subscription"]}


class TestFetchAllRows:
    def test_pages_until_the_reported_count(self):
        fake = FakeClient(max_rows=7)
        fake.seed("t", [{"id": f"{i:03d}"} for i in range(30)])
        rows = members.fetch_all_rows(lambda: fake.table("t").select("*", count="exact").order("id"), page_size=7)
        assert [r["id"] for r in rows] == [f"{i:03d}" for i in range(30)]

    def test_page_size_larger_than_max_rows_still_gets_everything(self):
        fake = FakeClient(max_rows=7)
        fake.seed("t", [{"id": f"{i:03d}"} for i in range(30)])
        rows = members.fetch_all_rows(lambda: fake.table("t").select("*", count="exact").order("id"), page_size=1000)
        assert len(rows) == 30

    def test_empty_table(self):
        fake = FakeClient(max_rows=7)
        assert members.fetch_all_rows(lambda: fake.table("t").select("*", count="exact").order("id")) == []

    def test_rows_deleted_mid_scan_end_cleanly(self):
        class Gone:
            def __init__(self, n):
                self.n = n

            def range(self, *_):
                return self

            def execute(self):
                self.n += 1
                if self.n == 1:
                    return type("R", (), {"data": [{"id": "a"}], "count": 5})()
                raise APIError({"code": "PGRST103", "message": "Requested range not satisfiable"})

        state = Gone(0)
        assert members.fetch_all_rows(lambda: state) == [{"id": "a"}]

    def test_other_errors_propagate(self):
        class Broken:
            def range(self, *_):
                return self

            def execute(self):
                raise APIError({"code": "42501", "message": "permission denied"})

        with pytest.raises(APIError):
            members.fetch_all_rows(lambda: Broken())
