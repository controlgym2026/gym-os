"""Tests for staff.py: owner-only staff creation (an auth user + a staff
row together), listing with email enrichment, validation, and the
rollback when the staff-row insert fails after the auth user was already
created."""

import pytest
from fastapi import HTTPException

from staff import CREATABLE_ROLES, StaffCreate, create_staff, list_staff
from tests.fake_client import FakeClient

TENANT = "tenant-1"
OWNER = {"tenant_id": TENANT, "id": "owner-1", "role": "owner"}
NON_OWNER = {"tenant_id": TENANT, "id": "staff-2", "role": "front_desk"}


def _setup(monkeypatch):
    import staff as staff_module

    client = FakeClient()
    monkeypatch.setattr(staff_module, "get_admin_client", lambda: client)
    return client


class TestCreateStaff:
    def test_creates_an_auth_user_and_a_staff_row(self, monkeypatch):
        client = _setup(monkeypatch)
        result = create_staff(
            StaffCreate(email="trainer@example.com", password="correct-horse", role="trainer"), staff=OWNER
        )
        assert result["role"] == "trainer"
        assert result["tenant_id"] == TENANT
        assert result["email"] == "trainer@example.com"
        # The auth user really exists, under the id the staff row references.
        assert client.auth.admin.get_user_by_id(result["id"]).user.email == "trainer@example.com"
        assert client.tables["staff"][0]["id"] == result["id"]

    def test_every_creatable_role_works(self, monkeypatch):
        client = _setup(monkeypatch)
        for i, role in enumerate(CREATABLE_ROLES):
            result = create_staff(
                StaffCreate(email=f"staff{i}@example.com", password="correct-horse", role=role), staff=OWNER
            )
            assert result["role"] == role

    def test_owner_role_is_not_creatable_through_this_endpoint(self, monkeypatch):
        _setup(monkeypatch)
        with pytest.raises(HTTPException) as exc:
            create_staff(StaffCreate(email="x@example.com", password="correct-horse", role="owner"), staff=OWNER)
        assert exc.value.status_code == 400

    def test_bogus_role_is_rejected(self, monkeypatch):
        _setup(monkeypatch)
        with pytest.raises(HTTPException) as exc:
            create_staff(StaffCreate(email="x@example.com", password="correct-horse", role="bogus"), staff=OWNER)
        assert exc.value.status_code == 400

    def test_short_password_is_rejected(self, monkeypatch):
        _setup(monkeypatch)
        with pytest.raises(HTTPException) as exc:
            create_staff(StaffCreate(email="x@example.com", password="short", role="trainer"), staff=OWNER)
        assert exc.value.status_code == 400

    def test_duplicate_email_is_rejected(self, monkeypatch):
        _setup(monkeypatch)
        create_staff(StaffCreate(email="dup@example.com", password="correct-horse", role="trainer"), staff=OWNER)
        with pytest.raises(HTTPException) as exc:
            create_staff(StaffCreate(email="dup@example.com", password="correct-horse", role="manager"), staff=OWNER)
        assert exc.value.status_code == 409

    def test_rejects_non_owner(self, monkeypatch):
        _setup(monkeypatch)
        with pytest.raises(HTTPException) as exc:
            create_staff(
                StaffCreate(email="x@example.com", password="correct-horse", role="trainer"), staff=NON_OWNER
            )
        assert exc.value.status_code == 403

    def test_new_staff_lands_in_the_owners_tenant(self, monkeypatch):
        client = _setup(monkeypatch)
        result = create_staff(
            StaffCreate(email="x@example.com", password="correct-horse", role="front_desk"),
            staff={"tenant_id": "tenant-xyz", "id": "owner-2", "role": "owner"},
        )
        assert result["tenant_id"] == "tenant-xyz"

    def test_rolls_back_the_auth_user_if_the_staff_insert_fails(self, monkeypatch):
        client = _setup(monkeypatch)

        class _BrokenTable:
            def insert(self, *_a, **_k):
                raise RuntimeError("DB is down")

        import staff as staff_module

        real_table = client.table
        monkeypatch.setattr(
            client, "table", lambda name: _BrokenTable() if name == "staff" else real_table(name)
        )
        with pytest.raises(RuntimeError):
            create_staff(
                StaffCreate(email="orphan@example.com", password="correct-horse", role="trainer"), staff=OWNER
            )
        # The auth user created just before the failing insert must not be left behind.
        with pytest.raises(ValueError):
            client.auth.admin.get_user_by_id("user-1")


class TestListStaff:
    def test_lists_staff_with_email_attached(self, monkeypatch):
        client = _setup(monkeypatch)
        created = create_staff(
            StaffCreate(email="trainer@example.com", password="correct-horse", role="trainer"), staff=OWNER
        )
        result = list_staff(staff=OWNER)
        by_id = {r["id"]: r for r in result}
        assert by_id[created["id"]]["email"] == "trainer@example.com"
        assert by_id[created["id"]]["role"] == "trainer"

    def test_only_this_tenants_staff_are_listed(self, monkeypatch):
        client = _setup(monkeypatch)
        create_staff(
            StaffCreate(email="mine@example.com", password="correct-horse", role="trainer"), staff=OWNER
        )
        create_staff(
            StaffCreate(email="theirs@example.com", password="correct-horse", role="trainer"),
            staff={"tenant_id": "tenant-2", "id": "owner-2", "role": "owner"},
        )
        result = list_staff(staff=OWNER)
        assert {r["email"] for r in result} == {"mine@example.com"}

    def test_rejects_non_owner(self, monkeypatch):
        _setup(monkeypatch)
        with pytest.raises(HTTPException) as exc:
            list_staff(staff=NON_OWNER)
        assert exc.value.status_code == 403
