"""Unit tests for the check-in business logic (subscriptions.is_expired,
attendance.check_in_allowed). Pure functions, plain dict fixtures, no DB.
"""

from datetime import date, timedelta

from attendance import check_in_allowed
from subscriptions import is_expired


def _sub(**overrides) -> dict:
    base = {
        "status": "ACTIVE",
        "end_date": (date.today() + timedelta(days=10)).isoformat(),
        "sessions_remaining": None,
    }
    base.update(overrides)
    return base


class TestCheckInAllowed:
    """The 5 cases the spec calls out explicitly."""

    def test_active_is_allowed(self):
        assert check_in_allowed(_sub(status="ACTIVE")) == (True, "ok")

    def test_frozen_is_denied(self):
        allowed, reason = check_in_allowed(_sub(status="FROZEN"))
        assert allowed is False
        assert "frozen" in reason

    def test_expired_is_denied(self):
        allowed, reason = check_in_allowed(_sub(status="EXPIRED"))
        assert allowed is False
        assert "expired" in reason

    def test_cancelled_is_denied(self):
        allowed, reason = check_in_allowed(_sub(status="CANCELLED"))
        assert allowed is False
        assert "cancelled" in reason

    def test_no_subscription_is_denied(self):
        allowed, reason = check_in_allowed(None)
        assert allowed is False
        assert "no active subscription" in reason


class TestIsExpired:
    """The date/session-count math behind ACTIVE -> EXPIRED auto-transition."""

    def test_future_end_date_not_expired(self):
        assert is_expired(_sub(end_date=(date.today() + timedelta(days=1)).isoformat())) is False

    def test_past_end_date_is_expired(self):
        assert is_expired(_sub(end_date=(date.today() - timedelta(days=1)).isoformat())) is True

    def test_end_date_today_not_yet_expired(self):
        # "passes" means the date has gone by, not that today == end_date.
        assert is_expired(_sub(end_date=date.today().isoformat())) is False

    def test_zero_sessions_remaining_is_expired(self):
        assert is_expired(_sub(end_date=None, sessions_remaining=0)) is True

    def test_negative_sessions_remaining_is_expired(self):
        assert is_expired(_sub(end_date=None, sessions_remaining=-1)) is True

    def test_positive_sessions_remaining_not_expired(self):
        assert is_expired(_sub(end_date=None, sessions_remaining=3)) is False

    def test_unlimited_plan_no_end_date_no_session_limit_never_expires(self):
        assert is_expired(_sub(end_date=None, sessions_remaining=None)) is False
