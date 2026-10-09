"""Tests for Phase 6 income (pt/service/product, not tied to a
subscription) and the member_id refactor: create_income validation,
create_payment now setting member_id, and member_transactions covering
both payment shapes (subscription-linked and standalone) via one filter."""

from datetime import date, datetime, timezone

import pytest
from fastapi import HTTPException

from finance_period import IST
from payments import IncomeCreate, PaymentCreate, create_income, create_payment, member_transactions
from tests.fake_client import FakeClient

TENANT = "tenant-1"
STAFF = {"tenant_id": TENANT, "id": "staff-1"}


def _seed_member(client, member_id="m-1"):
    client.seed("member", [{"id": member_id, "tenant_id": TENANT, "deleted_at": None, "name": "Test Member"}])


class TestCreateIncome:
    def test_creates_a_standalone_payment_row(self, monkeypatch):
        import payments as payments_module

        client = FakeClient()
        monkeypatch.setattr(payments_module, "get_admin_client", lambda: client)
        _seed_member(client)

        result = create_income(
            IncomeCreate(category="pt", member_id="m-1", amount=1500, method="cash"), staff=STAFF
        )
        assert result["subscription_id"] is None
        assert result["member_id"] == "m-1"
        assert result["transaction_type"] == "pt"
        assert result["status"] == "completed"
        assert result["amount"] == 1500

    def test_member_id_is_optional_for_a_walk_in_sale(self, monkeypatch):
        import payments as payments_module

        client = FakeClient()
        monkeypatch.setattr(payments_module, "get_admin_client", lambda: client)

        result = create_income(IncomeCreate(category="product", amount=500, method="cash"), staff=STAFF)
        assert result["member_id"] is None

    def test_invalid_category_is_rejected(self, monkeypatch):
        import payments as payments_module

        client = FakeClient()
        monkeypatch.setattr(payments_module, "get_admin_client", lambda: client)

        with pytest.raises(HTTPException) as exc:
            create_income(IncomeCreate(category="bogus", amount=100, method="cash"), staff=STAFF)
        assert exc.value.status_code == 400

    def test_invalid_method_is_rejected(self, monkeypatch):
        import payments as payments_module

        client = FakeClient()
        monkeypatch.setattr(payments_module, "get_admin_client", lambda: client)

        with pytest.raises(HTTPException) as exc:
            create_income(IncomeCreate(category="service", amount=100, method="bogus"), staff=STAFF)
        assert exc.value.status_code == 400

    def test_zero_or_negative_amount_is_rejected(self, monkeypatch):
        import payments as payments_module

        client = FakeClient()
        monkeypatch.setattr(payments_module, "get_admin_client", lambda: client)

        for bad in (0, -50):
            with pytest.raises(HTTPException) as exc:
                create_income(IncomeCreate(category="pt", amount=bad, method="cash"), staff=STAFF)
            assert exc.value.status_code == 400

    def test_negative_discount_is_rejected(self, monkeypatch):
        import payments as payments_module

        client = FakeClient()
        monkeypatch.setattr(payments_module, "get_admin_client", lambda: client)

        with pytest.raises(HTTPException) as exc:
            create_income(
                IncomeCreate(category="pt", amount=100, discount_amount=-10, method="cash"), staff=STAFF
            )
        assert exc.value.status_code == 400

    def test_nonexistent_member_id_is_404(self, monkeypatch):
        import payments as payments_module

        client = FakeClient()
        monkeypatch.setattr(payments_module, "get_admin_client", lambda: client)

        with pytest.raises(HTTPException) as exc:
            create_income(IncomeCreate(category="pt", member_id="ghost", amount=100, method="cash"), staff=STAFF)
        assert exc.value.status_code == 404

    def test_another_tenants_member_id_is_also_404(self, monkeypatch):
        import payments as payments_module

        client = FakeClient()
        monkeypatch.setattr(payments_module, "get_admin_client", lambda: client)
        client.seed("member", [{"id": "other-m", "tenant_id": "tenant-2", "deleted_at": None, "name": "X"}])

        with pytest.raises(HTTPException) as exc:
            create_income(
                IncomeCreate(category="pt", member_id="other-m", amount=100, method="cash"), staff=STAFF
            )
        assert exc.value.status_code == 404

    def test_income_date_is_anchored_at_noon_ist_converted_to_utc(self, monkeypatch):
        import payments as payments_module

        client = FakeClient()
        monkeypatch.setattr(payments_module, "get_admin_client", lambda: client)

        result = create_income(
            IncomeCreate(category="product", amount=200, method="cash", income_date=date(2026, 10, 1)),
            staff=STAFF,
        )
        expected = datetime(2026, 10, 1, 12, 0, tzinfo=IST).astimezone(timezone.utc)
        assert datetime.fromisoformat(result["created_at"]) == expected

    def test_omitted_income_date_leaves_created_at_unset_for_the_db_default(self, monkeypatch):
        import payments as payments_module

        client = FakeClient()
        monkeypatch.setattr(payments_module, "get_admin_client", lambda: client)

        result = create_income(IncomeCreate(category="pt", amount=100, method="cash"), staff=STAFF)
        assert "created_at" not in client.tables["payment"][0]

    def test_note_is_stored_as_gateway_ref(self, monkeypatch):
        import payments as payments_module

        client = FakeClient()
        monkeypatch.setattr(payments_module, "get_admin_client", lambda: client)

        result = create_income(
            IncomeCreate(category="pt", amount=100, method="cash", note="5-session pack"), staff=STAFF
        )
        assert result["gateway_ref"] == "5-session pack"


class TestCreatePaymentSetsMemberId:
    def test_subscription_payment_carries_the_subscriptions_member_id(self, monkeypatch):
        import payments as payments_module

        client = FakeClient()
        monkeypatch.setattr(payments_module, "get_admin_client", lambda: client)
        client.seed(
            "subscription",
            [{"id": "sub-1", "tenant_id": TENANT, "member_id": "m-1", "due_amount": 0}],
        )

        result = create_payment(
            "sub-1", PaymentCreate(amount=1000, method="cash"), staff=STAFF
        )
        assert result["member_id"] == "m-1"


class TestMemberTransactions:
    def test_includes_both_subscription_linked_and_standalone_income(self, monkeypatch):
        import payments as payments_module

        client = FakeClient()
        monkeypatch.setattr(payments_module, "get_admin_client", lambda: client)
        _seed_member(client, "m-1")
        client.seed(
            "payment",
            [
                {
                    "id": "p-1", "tenant_id": TENANT, "subscription_id": "sub-1", "member_id": "m-1",
                    "amount": 1000, "method": "cash", "status": "completed", "transaction_type": "admission",
                    "discount_amount": 0, "gateway_ref": None, "created_at": "2026-01-01T00:00:00+00:00",
                },
                {
                    "id": "p-2", "tenant_id": TENANT, "subscription_id": None, "member_id": "m-1",
                    "amount": 500, "method": "cash", "status": "completed", "transaction_type": "pt",
                    "discount_amount": 0, "gateway_ref": None, "created_at": "2026-02-01T00:00:00+00:00",
                },
            ],
        )

        result = member_transactions("m-1", staff=STAFF)
        assert {p["id"] for p in result} == {"p-1", "p-2"}

    def test_newest_first(self, monkeypatch):
        import payments as payments_module

        client = FakeClient()
        monkeypatch.setattr(payments_module, "get_admin_client", lambda: client)
        _seed_member(client, "m-1")
        client.seed(
            "payment",
            [
                {
                    "id": "old", "tenant_id": TENANT, "subscription_id": None, "member_id": "m-1",
                    "amount": 100, "method": "cash", "status": "completed", "transaction_type": "pt",
                    "discount_amount": 0, "gateway_ref": None, "created_at": "2026-01-01T00:00:00+00:00",
                },
                {
                    "id": "new", "tenant_id": TENANT, "subscription_id": None, "member_id": "m-1",
                    "amount": 100, "method": "cash", "status": "completed", "transaction_type": "pt",
                    "discount_amount": 0, "gateway_ref": None, "created_at": "2026-06-01T00:00:00+00:00",
                },
            ],
        )

        result = member_transactions("m-1", staff=STAFF)
        assert [p["id"] for p in result] == ["new", "old"]

    def test_excludes_another_members_payments(self, monkeypatch):
        import payments as payments_module

        client = FakeClient()
        monkeypatch.setattr(payments_module, "get_admin_client", lambda: client)
        _seed_member(client, "m-1")
        _seed_member(client, "m-2")
        client.seed(
            "payment",
            [
                {
                    "id": "mine", "tenant_id": TENANT, "subscription_id": None, "member_id": "m-1",
                    "amount": 100, "method": "cash", "status": "completed", "transaction_type": "pt",
                    "discount_amount": 0, "gateway_ref": None, "created_at": "2026-01-01T00:00:00+00:00",
                },
                {
                    "id": "theirs", "tenant_id": TENANT, "subscription_id": None, "member_id": "m-2",
                    "amount": 100, "method": "cash", "status": "completed", "transaction_type": "pt",
                    "discount_amount": 0, "gateway_ref": None, "created_at": "2026-01-01T00:00:00+00:00",
                },
            ],
        )

        result = member_transactions("m-1", staff=STAFF)
        assert [p["id"] for p in result] == ["mine"]
