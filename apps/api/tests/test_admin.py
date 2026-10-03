"""Tests for the Phase 5 super-admin SaaS-billing additions:
subscription_days_remaining (pure) and record_tenant_payment's running-total
accumulation (against FakeClient)."""

from datetime import date, timedelta

import pytest
from fastapi import HTTPException

from admin import TenantPaymentRequest, record_tenant_payment, subscription_days_remaining
from tests.fake_client import FakeClient

TODAY = date(2026, 10, 3)


class _Admin:
    email = "super@livnexacare.test"


class TestSubscriptionDaysRemaining:
    def test_none_when_no_expiry_set(self):
        assert subscription_days_remaining(None, today=TODAY) is None

    def test_future_expiry_is_positive(self):
        assert subscription_days_remaining(TODAY + timedelta(days=10), today=TODAY) == 10

    def test_today_is_zero(self):
        assert subscription_days_remaining(TODAY, today=TODAY) == 0

    def test_past_expiry_is_negative(self):
        """Negative, not clamped to 0 — the caller decides how to flag a
        lapsed subscription; this is just the arithmetic."""
        assert subscription_days_remaining(TODAY - timedelta(days=5), today=TODAY) == -5


class TestRecordTenantPayment:
    def _seed_tenant(self, client, tenant_id="t-1", amount_paid=0):
        client.seed("tenant", [{"id": tenant_id, "amount_paid": amount_paid}])

    def test_first_payment_sets_the_total(self, monkeypatch):
        import admin as admin_module

        client = FakeClient()
        monkeypatch.setattr(admin_module, "get_admin_client", lambda: client)
        self._seed_tenant(client, amount_paid=0)

        result = record_tenant_payment("t-1", TenantPaymentRequest(amount=5000), admin=_Admin())
        assert result["amount_paid"] == 5000

    def test_second_payment_adds_to_the_running_total_not_replacing_it(self, monkeypatch):
        import admin as admin_module

        client = FakeClient()
        monkeypatch.setattr(admin_module, "get_admin_client", lambda: client)
        self._seed_tenant(client, amount_paid=5000)

        result = record_tenant_payment("t-1", TenantPaymentRequest(amount=1500), admin=_Admin())
        assert result["amount_paid"] == 6500

    def test_records_an_audit_log_entry_with_the_new_total(self, monkeypatch):
        import admin as admin_module

        client = FakeClient()
        monkeypatch.setattr(admin_module, "get_admin_client", lambda: client)
        self._seed_tenant(client, amount_paid=1000)

        record_tenant_payment("t-1", TenantPaymentRequest(amount=500, note="UPI transfer"), admin=_Admin())
        entries = client.tables["tenant_audit_log"]
        assert len(entries) == 1
        assert entries[0]["action"] == "payment_recorded"
        assert entries[0]["performed_by"] == "super@livnexacare.test"
        assert "1,500.00" in entries[0]["note"]
        assert "UPI transfer" in entries[0]["note"]

    def test_zero_or_negative_amount_is_rejected(self, monkeypatch):
        import admin as admin_module

        client = FakeClient()
        monkeypatch.setattr(admin_module, "get_admin_client", lambda: client)
        self._seed_tenant(client)

        for bad in (0, -100):
            with pytest.raises(HTTPException) as exc:
                record_tenant_payment("t-1", TenantPaymentRequest(amount=bad), admin=_Admin())
            assert exc.value.status_code == 400

    def test_unknown_tenant_is_404(self, monkeypatch):
        import admin as admin_module

        client = FakeClient()
        monkeypatch.setattr(admin_module, "get_admin_client", lambda: client)

        with pytest.raises(HTTPException) as exc:
            record_tenant_payment("missing", TenantPaymentRequest(amount=100), admin=_Admin())
        assert exc.value.status_code == 404
