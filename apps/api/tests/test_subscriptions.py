"""Tests for reconcile_subscription_status — the bidirectional lazy status
reconciliation. Direct coverage of the function itself (test_member_filters.py
covers it indirectly through the members-list filter path); see
subscriptions.py's module docstring for the bug this fixes: a subscription
extended into the future via a direct date edit (not the normal renewal
flow) kept showing "Expired" because nothing re-checked status against the
corrected end_date."""

from datetime import date, timedelta

from subscriptions import reconcile_subscription_status
from tests.fake_client import FakeClient

TENANT = "tenant-1"


def _seed_sub(client, **overrides):
    sub = {
        "id": "sub-1", "tenant_id": TENANT, "member_id": "m-1", "plan_id": "plan-1",
        "status": "ACTIVE", "start_date": "2026-01-01", "end_date": None,
        "sessions_remaining": None, "due_amount": 0, "frozen_at": None,
    }
    sub.update(overrides)
    client.seed("subscription", [sub])
    return sub


class TestActiveToExpired:
    def test_active_past_its_end_date_flips_to_expired(self):
        client = FakeClient()
        past = (date.today() - timedelta(days=1)).isoformat()
        _seed_sub(client, status="ACTIVE", end_date=past)
        result = reconcile_subscription_status(client, client.tables["subscription"][0])
        assert result["status"] == "EXPIRED"
        assert client.tables["subscription"][0]["status"] == "EXPIRED"  # persisted, not just returned

    def test_active_not_yet_past_its_end_date_stays_active(self):
        client = FakeClient()
        future = (date.today() + timedelta(days=1)).isoformat()
        _seed_sub(client, status="ACTIVE", end_date=future)
        result = reconcile_subscription_status(client, client.tables["subscription"][0])
        assert result["status"] == "ACTIVE"

    def test_active_out_of_sessions_flips_to_expired(self):
        client = FakeClient()
        _seed_sub(client, status="ACTIVE", end_date=None, sessions_remaining=0)
        result = reconcile_subscription_status(client, client.tables["subscription"][0])
        assert result["status"] == "EXPIRED"


class TestExpiredBackToActive:
    """The fix: EXPIRED is a derived status, not a deliberate choice — if
    the facts no longer support it, it must self-correct on the next read."""

    def test_expired_with_a_now_future_end_date_revives_to_active(self):
        client = FakeClient()
        future = (date.today() + timedelta(days=30)).isoformat()
        _seed_sub(client, status="EXPIRED", end_date=future)
        result = reconcile_subscription_status(client, client.tables["subscription"][0])
        assert result["status"] == "ACTIVE"
        assert client.tables["subscription"][0]["status"] == "ACTIVE"

    def test_expired_with_sessions_added_back_revives_to_active(self):
        client = FakeClient()
        _seed_sub(client, status="EXPIRED", end_date=None, sessions_remaining=5)
        result = reconcile_subscription_status(client, client.tables["subscription"][0])
        assert result["status"] == "ACTIVE"

    def test_expired_still_in_the_past_stays_expired_no_spurious_write(self):
        client = FakeClient()
        past = (date.today() - timedelta(days=5)).isoformat()
        sub = _seed_sub(client, status="EXPIRED", end_date=past)
        result = reconcile_subscription_status(client, sub)
        assert result["status"] == "EXPIRED"


class TestCancelledIsNeverTouched:
    def test_cancelled_with_a_future_end_date_stays_cancelled(self):
        """CANCELLED is a deliberate staff action, not a date-driven state —
        unlike EXPIRED, a future end_date must never silently revive it."""
        client = FakeClient()
        future = (date.today() + timedelta(days=30)).isoformat()
        _seed_sub(client, status="CANCELLED", end_date=future)
        result = reconcile_subscription_status(client, client.tables["subscription"][0])
        assert result["status"] == "CANCELLED"

    def test_cancelled_with_a_past_end_date_stays_cancelled(self):
        client = FakeClient()
        past = (date.today() - timedelta(days=5)).isoformat()
        _seed_sub(client, status="CANCELLED", end_date=past)
        result = reconcile_subscription_status(client, client.tables["subscription"][0])
        assert result["status"] == "CANCELLED"


class TestFrozenIsNeverTouched:
    def test_frozen_with_a_past_end_date_stays_frozen(self):
        """A frozen subscription's countdown is paused — is_expired() still
        technically says "past end_date", but only ACTIVE/EXPIRED rows are
        ever reconciled; freezing is itself what stops the clock."""
        client = FakeClient()
        past = (date.today() - timedelta(days=5)).isoformat()
        _seed_sub(client, status="FROZEN", end_date=past)
        result = reconcile_subscription_status(client, client.tables["subscription"][0])
        assert result["status"] == "FROZEN"
