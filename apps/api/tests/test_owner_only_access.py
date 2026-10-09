"""require_owner — the shared gate behind the Owner section (Dashboard,
Finance, Devices). Called explicitly as the first line of each owner-only
route rather than wired in as its own Depends, so it's exercised the same
way every other route in this codebase is tested: by calling the function
directly with a plain `staff` dict, bypassing FastAPI's dependency
resolution entirely (see members.py/expense.py's own test files).

expense.py's and payments.py's own owner-only coverage lives in their own
test files (TestOwnerOnly / TestCreateIncomeIsOwnerOnlyButPaymentsAreNot);
this file covers require_owner itself plus devices.py (which had no test
file at all before this feature) and dashboard.py's gate."""

import pytest
from fastapi import HTTPException

from auth import require_owner

TENANT = "tenant-1"
OWNER = {"tenant_id": TENANT, "id": "staff-1", "role": "owner"}
NON_OWNER = {"tenant_id": TENANT, "id": "staff-2", "role": "front_desk"}


class TestRequireOwnerPure:
    def test_owner_passes(self):
        require_owner(OWNER)  # no exception

    def test_non_owner_roles_are_all_rejected(self):
        for role in ("manager", "trainer", "front_desk"):
            with pytest.raises(HTTPException) as exc:
                require_owner({"role": role})
            assert exc.value.status_code == 403, role

    def test_missing_role_is_rejected(self):
        with pytest.raises(HTTPException) as exc:
            require_owner({"tenant_id": TENANT})
        assert exc.value.status_code == 403


class TestDevicesAreOwnerOnly:
    def _setup(self, monkeypatch):
        import devices as devices_module
        from tests.fake_client import FakeClient

        client = FakeClient()
        monkeypatch.setattr(devices_module, "get_admin_client", lambda: client)
        return client

    def test_register_device_rejects_non_owner(self, monkeypatch):
        from devices import DeviceCreate, register_device

        self._setup(monkeypatch)
        with pytest.raises(HTTPException) as exc:
            register_device(DeviceCreate(serial_number="SN1", label="Front desk"), staff=NON_OWNER)
        assert exc.value.status_code == 403

    def test_list_devices_rejects_non_owner(self, monkeypatch):
        from devices import list_devices

        self._setup(monkeypatch)
        with pytest.raises(HTTPException) as exc:
            list_devices(staff=NON_OWNER)
        assert exc.value.status_code == 403

    def test_update_device_rejects_non_owner(self, monkeypatch):
        from devices import DeviceUpdate, update_device

        self._setup(monkeypatch)
        with pytest.raises(HTTPException) as exc:
            update_device("whatever", DeviceUpdate(label="x"), staff=NON_OWNER)
        assert exc.value.status_code == 403

    def test_register_and_list_work_for_owner(self, monkeypatch):
        from devices import DeviceCreate, list_devices, register_device

        self._setup(monkeypatch)
        created = register_device(DeviceCreate(serial_number="SN1", label="Front desk"), staff=OWNER)
        assert created["serial_number"] == "SN1"
        listed = list_devices(staff=OWNER)
        assert [d["serial_number"] for d in listed] == ["SN1"]


class TestDashboardIsOwnerOnly:
    """require_owner runs before get_admin_client() in both routes, so
    these don't need a working FakeClient/RPC stub at all — the 403 fires
    before any DB access is even attempted."""

    def test_summary_rejects_non_owner(self):
        from dashboard import get_summary

        with pytest.raises(HTTPException) as exc:
            get_summary(staff=NON_OWNER)
        assert exc.value.status_code == 403

    def test_income_transactions_rejects_non_owner(self):
        from dashboard import get_income_transactions

        with pytest.raises(HTTPException) as exc:
            get_income_transactions(staff=NON_OWNER)
        assert exc.value.status_code == 403
