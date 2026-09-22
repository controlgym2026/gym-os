"""Device registration + admin screen backend.

Phase 2 is explicitly single-branch, and nothing in the app creates a branch
yet (no branch CRUD exists anywhere) — Device.branch_id is NOT NULL, so
registering a device auto-provisions the tenant's one default branch the
first time it's needed rather than asking staff to pick/create one. This
means the "Devices" screen has no branch selector, unlike the spec's literal
"enter serial number + label + branch" — flagged in the Phase 2 report.
"""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from auth import get_admin_client, get_current_staff

router = APIRouter(prefix="/devices", tags=["devices"])

ONLINE_THRESHOLD = timedelta(minutes=10)


class DeviceCreate(BaseModel):
    serial_number: str
    label: str
    vendor: str = "zkteco"


class DeviceUpdate(BaseModel):
    label: str | None = None
    status: str | None = None  # 'active' | 'inactive'


def get_or_create_default_branch(client, tenant_id: str) -> str:
    result = client.table("branch").select("id").eq("tenant_id", tenant_id).limit(1).execute()
    if result.data:
        return result.data[0]["id"]
    created = client.table("branch").insert({"tenant_id": tenant_id}).execute()
    return created.data[0]["id"]


def _with_online_flag(device: dict) -> dict:
    online = False
    if device.get("last_seen_at"):
        last_seen = datetime.fromisoformat(device["last_seen_at"])
        online = datetime.now(timezone.utc) - last_seen < ONLINE_THRESHOLD
    return {**device, "online": online}


@router.post("", status_code=201)
def register_device(body: DeviceCreate, staff=Depends(get_current_staff)):
    client = get_admin_client()
    tenant_id = staff["tenant_id"]
    branch_id = get_or_create_default_branch(client, tenant_id)
    try:
        result = (
            client.table("device")
            .insert(
                {
                    "tenant_id": tenant_id,
                    "branch_id": branch_id,
                    "vendor": body.vendor,
                    "serial_number": body.serial_number,
                    "label": body.label,
                }
            )
            .execute()
        )
    except Exception as exc:
        # serial_number is globally unique (see the Phase 2 migration) —
        # this is either a re-registration of the same device or, more
        # concerningly, someone else's serial. Either way, don't silently
        # attach it to this tenant.
        raise HTTPException(
            status.HTTP_409_CONFLICT, "This serial number is already registered"
        ) from exc
    return _with_online_flag(result.data[0])


@router.get("")
def list_devices(staff=Depends(get_current_staff)):
    client = get_admin_client()
    result = (
        client.table("device")
        .select("*")
        .eq("tenant_id", staff["tenant_id"])
        .order("created_at", desc=True)
        .execute()
    )
    return [_with_online_flag(d) for d in result.data]


@router.patch("/{device_id}")
def update_device(device_id: str, body: DeviceUpdate, staff=Depends(get_current_staff)):
    client = get_admin_client()
    tenant_id = staff["tenant_id"]
    existing = client.table("device").select("id").eq("tenant_id", tenant_id).eq("id", device_id).execute()
    if not existing.data:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Device not found")
    payload = body.model_dump(exclude_unset=True)
    if payload.get("status") not in (None, "active", "inactive"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "status must be 'active' or 'inactive'")
    if not payload:
        result = client.table("device").select("*").eq("id", device_id).execute()
    else:
        result = client.table("device").update(payload).eq("tenant_id", tenant_id).eq("id", device_id).execute()
    return _with_online_flag(result.data[0])
