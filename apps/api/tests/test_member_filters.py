"""Tests for member_matches_filter — the pure predicate behind
GET /members?filter=&plan_id=. Covers each filter value, the plan filter,
their combination, and the edge cases that decide who lands on a
renewal-followup list (session-based plans, boundary days)."""

from datetime import date, timedelta

from members import EXPIRING_SOON_DAYS, member_matches_filter

TODAY = date(2026, 10, 2)
TENANT = "tenant-1"


def _sub(status="ACTIVE", end_date=None, due_amount=0, plan_id="plan-1", sessions_remaining=None):
    return {
        "status": status,
        "end_date": end_date.isoformat() if isinstance(end_date, date) else end_date,
        "due_amount": due_amount,
        "plan_id": plan_id,
        "sessions_remaining": sessions_remaining,
    }


class TestNoFilter:
    def test_everything_matches_when_no_filter_is_given(self):
        assert member_matches_filter(_sub(), None, None, today=TODAY)

    def test_member_with_no_subscription_matches_when_unfiltered(self):
        assert member_matches_filter(None, None, None, today=TODAY)

    def test_member_with_no_subscription_never_matches_a_filter(self):
        for f in ("active", "expiring", "due", "paid"):
            assert not member_matches_filter(None, f, None, today=TODAY), f


class TestActiveFilter:
    def test_active_subscription_matches(self):
        assert member_matches_filter(_sub(status="ACTIVE"), "active", today=TODAY)

    def test_non_active_statuses_do_not_match(self):
        for status in ("FROZEN", "EXPIRED", "CANCELLED"):
            assert not member_matches_filter(_sub(status=status), "active", today=TODAY), status


class TestExpiringFilter:
    def test_expiring_inside_the_window_matches(self):
        assert member_matches_filter(_sub(end_date=TODAY + timedelta(days=3)), "expiring", today=TODAY)

    def test_expiring_today_matches(self):
        assert member_matches_filter(_sub(end_date=TODAY), "expiring", today=TODAY)

    def test_last_day_of_the_window_matches(self):
        end = TODAY + timedelta(days=EXPIRING_SOON_DAYS)
        assert member_matches_filter(_sub(end_date=end), "expiring", today=TODAY)

    def test_one_day_past_the_window_does_not_match(self):
        end = TODAY + timedelta(days=EXPIRING_SOON_DAYS + 1)
        assert not member_matches_filter(_sub(end_date=end), "expiring", today=TODAY)

    def test_already_expired_does_not_match(self):
        """"Expires" is a proactive follow-up list — a lapsed member isn't
        expiring, they've expired, and belongs in a different bucket."""
        assert not member_matches_filter(_sub(end_date=TODAY - timedelta(days=1)), "expiring", today=TODAY)

    def test_frozen_subscription_does_not_match_even_inside_the_window(self):
        sub = _sub(status="FROZEN", end_date=TODAY + timedelta(days=2))
        assert not member_matches_filter(sub, "expiring", today=TODAY)

    def test_session_based_plan_never_matches(self):
        """No end_date to run out — session-based plans can't be date-expiring."""
        sub = _sub(end_date=None, sessions_remaining=3)
        assert not member_matches_filter(sub, "expiring", today=TODAY)


class TestDueAndPaidFilters:
    def test_outstanding_balance_is_due(self):
        assert member_matches_filter(_sub(due_amount=500), "due", today=TODAY)

    def test_zero_balance_is_not_due(self):
        assert not member_matches_filter(_sub(due_amount=0), "due", today=TODAY)

    def test_zero_balance_is_paid(self):
        assert member_matches_filter(_sub(due_amount=0), "paid", today=TODAY)

    def test_outstanding_balance_is_not_paid(self):
        assert not member_matches_filter(_sub(due_amount=500), "paid", today=TODAY)

    def test_due_and_paid_are_exhaustive_and_mutually_exclusive(self):
        for amount in (0, 0.5, 1, 5000):
            sub = _sub(due_amount=amount)
            is_due = member_matches_filter(sub, "due", today=TODAY)
            is_paid = member_matches_filter(sub, "paid", today=TODAY)
            assert is_due != is_paid, amount

    def test_due_and_paid_ignore_subscription_status(self):
        """An expired member who still owes money should stay findable under
        "Due" — that's the collections case, not just the active roster."""
        assert member_matches_filter(_sub(status="EXPIRED", due_amount=200), "due", today=TODAY)


class TestPlanFilter:
    def test_matching_plan_matches(self):
        assert member_matches_filter(_sub(plan_id="plan-a"), None, "plan-a", today=TODAY)

    def test_other_plan_does_not_match(self):
        assert not member_matches_filter(_sub(plan_id="plan-b"), None, "plan-a", today=TODAY)

    def test_no_subscription_does_not_match_a_plan(self):
        assert not member_matches_filter(None, None, "plan-a", today=TODAY)

    def test_plan_and_filter_combine_as_and(self):
        on_plan_a_active = _sub(plan_id="plan-a", status="ACTIVE")
        on_plan_a_expired = _sub(plan_id="plan-a", status="EXPIRED")
        on_plan_b_active = _sub(plan_id="plan-b", status="ACTIVE")
        assert member_matches_filter(on_plan_a_active, "active", "plan-a", today=TODAY)
        assert not member_matches_filter(on_plan_a_expired, "active", "plan-a", today=TODAY)
        assert not member_matches_filter(on_plan_b_active, "active", "plan-a", today=TODAY)


class TestListMembersFilterPath:
    """GET /members?filter= end-to-end against FakeClient: the filtered path
    pages in Python (status/due/plan live on the subscription, not the member
    row, so PostgREST can't do it), so the slicing and totals are real logic
    worth testing rather than inspecting."""

    def _setup(self, monkeypatch):
        import members as members_module
        from tests.fake_client import FakeClient

        client = FakeClient()
        monkeypatch.setattr(members_module, "get_admin_client", lambda: client)
        return client

    def _seed(self, client, specs):
        """specs: list of (name, status, days_to_end, due, plan_id)."""
        from datetime import date as _date

        members, subs = [], []
        for i, (name, status, days_to_end, due, plan_id) in enumerate(specs):
            mid = f"m-{i}"
            members.append(
                {"id": mid, "tenant_id": TENANT, "name": name, "phone": None, "deleted_at": None,
                 "created_at": f"2026-01-{i + 1:02d}"}
            )
            if status is not None:
                end = (_date.today() + timedelta(days=days_to_end)).isoformat() if days_to_end is not None else None
                subs.append(
                    {"id": f"s-{i}", "tenant_id": TENANT, "member_id": mid, "plan_id": plan_id,
                     "status": status, "start_date": "2026-01-01", "end_date": end,
                     "due_amount": due, "sessions_remaining": None, "created_at": f"2026-02-{i + 1:02d}"}
                )
        client.seed("member", members)
        client.seed("subscription", subs)
        client.seed("membership_plan", [
            {"id": "plan-a", "tenant_id": TENANT, "name": "Monthly"},
            {"id": "plan-b", "tenant_id": TENANT, "name": "Annual"},
        ])

    SPECS = [
        ("Active far off", "ACTIVE", 60, 0, "plan-a"),
        ("Active expiring", "ACTIVE", 3, 0, "plan-a"),
        ("Active with due", "ACTIVE", 45, 500, "plan-b"),
        ("Frozen", "FROZEN", 30, 0, "plan-a"),
        ("Cancelled owing", "CANCELLED", 10, 250, "plan-b"),
        ("No plan at all", None, None, 0, None),
    ]

    def _names(self, result):
        return {m["name"] for m in result["items"]}

    def test_unfiltered_includes_everyone(self, monkeypatch):
        import members as members_module

        client = self._setup(monkeypatch)
        self._seed(client, self.SPECS)
        result = members_module.list_members(staff={"tenant_id": TENANT})
        assert result["total"] == 6
        assert "No plan at all" in self._names(result)

    def test_active_filter(self, monkeypatch):
        import members as members_module

        client = self._setup(monkeypatch)
        self._seed(client, self.SPECS)
        result = members_module.list_members(subscription_filter="active", staff={"tenant_id": TENANT})
        assert self._names(result) == {"Active far off", "Active expiring", "Active with due"}
        assert result["total"] == 3

    def test_expiring_filter(self, monkeypatch):
        import members as members_module

        client = self._setup(monkeypatch)
        self._seed(client, self.SPECS)
        result = members_module.list_members(subscription_filter="expiring", staff={"tenant_id": TENANT})
        assert self._names(result) == {"Active expiring"}

    def test_due_filter_spans_statuses(self, monkeypatch):
        import members as members_module

        client = self._setup(monkeypatch)
        self._seed(client, self.SPECS)
        result = members_module.list_members(subscription_filter="due", staff={"tenant_id": TENANT})
        assert self._names(result) == {"Active with due", "Cancelled owing"}

    def test_plan_filter(self, monkeypatch):
        import members as members_module

        client = self._setup(monkeypatch)
        self._seed(client, self.SPECS)
        result = members_module.list_members(plan_id="plan-b", staff={"tenant_id": TENANT})
        assert self._names(result) == {"Active with due", "Cancelled owing"}

    def test_filter_and_plan_combine(self, monkeypatch):
        import members as members_module

        client = self._setup(monkeypatch)
        self._seed(client, self.SPECS)
        result = members_module.list_members(
            subscription_filter="active", plan_id="plan-a", staff={"tenant_id": TENANT}
        )
        assert self._names(result) == {"Active far off", "Active expiring"}

    def test_attaches_current_subscription_with_plan_name(self, monkeypatch):
        import members as members_module

        client = self._setup(monkeypatch)
        self._seed(client, self.SPECS)
        result = members_module.list_members(subscription_filter="due", staff={"tenant_id": TENANT})
        by_name = {m["name"]: m for m in result["items"]}
        assert by_name["Active with due"]["current_subscription"]["plan_name"] == "Annual"
        assert by_name["Active with due"]["current_subscription"]["due_amount"] == 500

    def test_pagination_slices_the_filtered_set_and_totals_the_whole_match(self, monkeypatch):
        """total must count every match, not just the current page — the
        "Showing 1–25 of N" line and the Next button both depend on it."""
        import members as members_module

        client = self._setup(monkeypatch)
        self._seed(client, [(f"Member {i}", "ACTIVE", 60, 0, "plan-a") for i in range(10)])
        page1 = members_module.list_members(
            subscription_filter="active", page=1, page_size=4, staff={"tenant_id": TENANT}
        )
        page2 = members_module.list_members(
            subscription_filter="active", page=2, page_size=4, staff={"tenant_id": TENANT}
        )
        page3 = members_module.list_members(
            subscription_filter="active", page=3, page_size=4, staff={"tenant_id": TENANT}
        )
        assert [len(p["items"]) for p in (page1, page2, page3)] == [4, 4, 2]
        assert page1["total"] == page2["total"] == 10
        # No member appears on two pages and none is missed.
        seen = self._names(page1) | self._names(page2) | self._names(page3)
        assert len(seen) == 10

    def test_page_past_the_end_is_empty_not_an_error(self, monkeypatch):
        import members as members_module

        client = self._setup(monkeypatch)
        self._seed(client, self.SPECS)
        result = members_module.list_members(
            subscription_filter="active", page=99, page_size=25, staff={"tenant_id": TENANT}
        )
        assert result["items"] == []
        assert result["total"] == 3

    def test_unknown_filter_is_rejected(self, monkeypatch):
        import members as members_module
        from fastapi import HTTPException
        import pytest

        client = self._setup(monkeypatch)
        self._seed(client, self.SPECS)
        with pytest.raises(HTTPException) as exc:
            members_module.list_members(subscription_filter="bogus", staff={"tenant_id": TENANT})
        assert exc.value.status_code == 400

    def test_lazy_expiry_applies_to_the_filter(self, monkeypatch):
        """A row still marked ACTIVE but past its end_date must not show up
        under "Active" — expire_if_due runs before the predicate."""
        import members as members_module

        client = self._setup(monkeypatch)
        self._seed(client, [("Stale active", "ACTIVE", -5, 0, "plan-a")])
        result = members_module.list_members(subscription_filter="active", staff={"tenant_id": TENANT})
        assert result["items"] == []
        assert client.tables["subscription"][0]["status"] == "EXPIRED"

    def test_search_and_filter_combine(self, monkeypatch):
        """The text search runs against the whole dataset inside the filtered
        path too, not just the current page."""
        import members as members_module

        client = self._setup(monkeypatch)
        self._seed(client, self.SPECS)
        result = members_module.list_members(
            q="Active", subscription_filter="active", staff={"tenant_id": TENANT}
        )
        assert self._names(result) == {"Active far off", "Active expiring", "Active with due"}

        narrowed = members_module.list_members(
            q="expiring", subscription_filter="active", staff={"tenant_id": TENANT}
        )
        assert self._names(narrowed) == {"Active expiring"}

    def test_soft_deleted_members_are_excluded_from_filters(self, monkeypatch):
        import members as members_module

        client = self._setup(monkeypatch)
        self._seed(client, self.SPECS)
        client.tables["member"][0]["deleted_at"] = "2026-03-01T00:00:00Z"
        result = members_module.list_members(subscription_filter="active", staff={"tenant_id": TENANT})
        assert "Active far off" not in self._names(result)
        assert result["total"] == 2

    def test_another_tenants_members_are_never_returned(self, monkeypatch):
        import members as members_module

        client = self._setup(monkeypatch)
        self._seed(client, self.SPECS)
        client.seed("member", [
            {"id": "other-1", "tenant_id": "tenant-2", "name": "Someone Else",
             "phone": None, "deleted_at": None, "created_at": "2026-01-01"}
        ])
        client.seed("subscription", [
            {"id": "other-s", "tenant_id": "tenant-2", "member_id": "other-1", "plan_id": "plan-a",
             "status": "ACTIVE", "start_date": "2026-01-01", "end_date": None,
             "due_amount": 999, "sessions_remaining": None, "created_at": "2026-02-01"}
        ])
        for f in ("active", "due", None):
            result = members_module.list_members(subscription_filter=f, staff={"tenant_id": TENANT})
            assert "Someone Else" not in self._names(result), f
