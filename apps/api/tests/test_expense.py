"""Tests for the expense module: CRUD, validation, period/category
filtering + pagination, and tenant isolation (against FakeClient)."""

from datetime import date

import pytest
from fastapi import HTTPException

from expense import (
    CATEGORY_PRESETS,
    ExpenseCreate,
    ExpenseUpdate,
    create_expense,
    delete_expense,
    list_expenses,
    update_expense,
)
from tests.fake_client import FakeClient

TENANT = "tenant-1"
STAFF = {"tenant_id": TENANT, "id": "staff-1"}


def _setup(monkeypatch):
    import expense as expense_module

    client = FakeClient()
    monkeypatch.setattr(expense_module, "get_admin_client", lambda: client)
    return client


class TestCreateExpense:
    def test_creates_an_expense_row(self, monkeypatch):
        client = _setup(monkeypatch)
        result = create_expense(
            ExpenseCreate(category="Rent", amount=15000, expense_date=date(2026, 10, 1), payment_mode="cash"),
            staff=STAFF,
        )
        assert result["category"] == "Rent"
        assert result["amount"] == 15000
        assert result["tenant_id"] == TENANT
        assert result["created_by"] == "staff-1"

    def test_defaults_expense_date_to_today_ist_when_omitted(self, monkeypatch):
        client = _setup(monkeypatch)
        result = create_expense(ExpenseCreate(category="Other", amount=100), staff=STAFF)
        assert result["expense_date"]  # set to something, not left blank

    def test_category_is_not_restricted_to_the_presets(self, monkeypatch):
        """Free text is explicitly allowed — a gym typing their own category
        shouldn't be rejected."""
        client = _setup(monkeypatch)
        result = create_expense(ExpenseCreate(category="Dog treats for the mascot", amount=50), staff=STAFF)
        assert result["category"] == "Dog treats for the mascot"

    def test_category_whitespace_is_trimmed(self, monkeypatch):
        client = _setup(monkeypatch)
        result = create_expense(ExpenseCreate(category="  Rent  ", amount=100), staff=STAFF)
        assert result["category"] == "Rent"

    def test_zero_or_negative_amount_is_rejected(self, monkeypatch):
        client = _setup(monkeypatch)
        for bad in (0, -5):
            with pytest.raises(HTTPException) as exc:
                create_expense(ExpenseCreate(category="Rent", amount=bad), staff=STAFF)
            assert exc.value.status_code == 400

    def test_invalid_payment_mode_is_rejected(self, monkeypatch):
        client = _setup(monkeypatch)
        with pytest.raises(HTTPException) as exc:
            create_expense(ExpenseCreate(category="Rent", amount=100, payment_mode="bitcoin"), staff=STAFF)
        assert exc.value.status_code == 400


class TestCategoryPresets:
    def test_presets_include_the_spec_list(self, monkeypatch):
        assert set(CATEGORY_PRESETS) == {
            "Rent", "Salary", "Electricity", "Equipment", "Maintenance", "Marketing", "Other",
        }


class TestListExpenses:
    def _seed_three(self, client):
        for i, (cat, amt, d) in enumerate(
            [("Rent", 15000, "2026-10-01"), ("Salary", 20000, "2026-10-05"), ("Rent", 2000, "2026-09-15")]
        ):
            client.seed(
                "expense",
                [{"id": f"e-{i}", "tenant_id": TENANT, "category": cat, "amount": amt,
                  "expense_date": d, "payment_mode": "cash", "description": None,
                  "created_by": "staff-1", "created_at": f"2026-01-{i + 1:02d}"}],
            )

    def test_period_filters_by_expense_date(self, monkeypatch):
        client = _setup(monkeypatch)
        self._seed_three(client)
        result = list_expenses(period="custom", from_="2026-10-01", to="2026-10-31", staff=STAFF)
        assert result["total"] == 2
        assert {e["id"] for e in result["items"]} == {"e-0", "e-1"}

    def test_category_filter(self, monkeypatch):
        client = _setup(monkeypatch)
        self._seed_three(client)
        result = list_expenses(
            period="custom", from_="2026-01-01", to="2026-12-31", category="Rent", staff=STAFF
        )
        assert {e["id"] for e in result["items"]} == {"e-0", "e-2"}

    def test_newest_first(self, monkeypatch):
        client = _setup(monkeypatch)
        self._seed_three(client)
        result = list_expenses(period="custom", from_="2026-01-01", to="2026-12-31", staff=STAFF)
        dates = [e["expense_date"] for e in result["items"]]
        assert dates == sorted(dates, reverse=True)

    def test_pagination(self, monkeypatch):
        client = _setup(monkeypatch)
        for i in range(5):
            client.seed(
                "expense",
                [{"id": f"p-{i}", "tenant_id": TENANT, "category": "Other", "amount": 100,
                  "expense_date": "2026-10-01", "payment_mode": "cash", "description": None,
                  "created_by": "staff-1", "created_at": f"2026-01-{i + 1:02d}"}],
            )
        page1 = list_expenses(period="custom", from_="2026-01-01", to="2026-12-31", page=1, page_size=2, staff=STAFF)
        assert len(page1["items"]) == 2
        assert page1["total"] == 5


class TestUpdateExpense:
    def test_partial_update(self, monkeypatch):
        client = _setup(monkeypatch)
        created = create_expense(ExpenseCreate(category="Rent", amount=15000), staff=STAFF)
        updated = update_expense(created["id"], ExpenseUpdate(amount=16000), staff=STAFF)
        assert updated["amount"] == 16000
        assert updated["category"] == "Rent"  # untouched

    def test_update_validates_amount(self, monkeypatch):
        client = _setup(monkeypatch)
        created = create_expense(ExpenseCreate(category="Rent", amount=15000), staff=STAFF)
        with pytest.raises(HTTPException) as exc:
            update_expense(created["id"], ExpenseUpdate(amount=-1), staff=STAFF)
        assert exc.value.status_code == 400

    def test_update_nonexistent_expense_is_404(self, monkeypatch):
        client = _setup(monkeypatch)
        with pytest.raises(HTTPException) as exc:
            update_expense("ghost", ExpenseUpdate(amount=100), staff=STAFF)
        assert exc.value.status_code == 404


class TestDeleteExpense:
    def test_delete_removes_the_row_entirely(self, monkeypatch):
        """Hard delete, documented in expense.py — no deleted_at column."""
        client = _setup(monkeypatch)
        created = create_expense(ExpenseCreate(category="Rent", amount=15000), staff=STAFF)
        delete_expense(created["id"], staff=STAFF)
        assert client.tables["expense"] == []

    def test_delete_nonexistent_expense_is_404(self, monkeypatch):
        client = _setup(monkeypatch)
        with pytest.raises(HTTPException) as exc:
            delete_expense("ghost", staff=STAFF)
        assert exc.value.status_code == 404


class TestTenantIsolation:
    def test_another_tenants_expenses_are_invisible_to_list(self, monkeypatch):
        client = _setup(monkeypatch)
        client.seed(
            "expense",
            [{"id": "other", "tenant_id": "tenant-2", "category": "Rent", "amount": 999,
              "expense_date": "2026-10-01", "payment_mode": "cash", "description": None,
              "created_by": "x", "created_at": "2026-01-01"}],
        )
        result = list_expenses(period="custom", from_="2026-01-01", to="2026-12-31", staff=STAFF)
        assert result["items"] == []

    def test_cannot_update_another_tenants_expense(self, monkeypatch):
        client = _setup(monkeypatch)
        client.seed(
            "expense",
            [{"id": "other", "tenant_id": "tenant-2", "category": "Rent", "amount": 999,
              "expense_date": "2026-10-01", "payment_mode": "cash", "description": None,
              "created_by": "x", "created_at": "2026-01-01"}],
        )
        with pytest.raises(HTTPException) as exc:
            update_expense("other", ExpenseUpdate(amount=1), staff=STAFF)
        assert exc.value.status_code == 404

    def test_cannot_delete_another_tenants_expense(self, monkeypatch):
        client = _setup(monkeypatch)
        client.seed(
            "expense",
            [{"id": "other", "tenant_id": "tenant-2", "category": "Rent", "amount": 999,
              "expense_date": "2026-10-01", "payment_mode": "cash", "description": None,
              "created_by": "x", "created_at": "2026-01-01"}],
        )
        with pytest.raises(HTTPException) as exc:
            delete_expense("other", staff=STAFF)
        assert exc.value.status_code == 404
        assert len(client.tables["expense"]) == 1  # untouched
