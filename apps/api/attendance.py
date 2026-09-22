"""Check-in (manual/QR) + attendance history.

QR is just "a scan resolves to a member_id and calls the same endpoint" —
there's no separate QR code generation/parsing here, that's frontend-side
(or a future phase); this endpoint only cares about `source`.
"""

from datetime import date, datetime, time, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from auth import get_admin_client, get_current_staff
from resources import get_member_or_404
from subscriptions import expire_if_due, get_latest_subscription

router = APIRouter(tags=["attendance"])

VALID_SOURCES = ("manual", "qr")  # 'biometric' exists in the DB enum, reserved for Phase 2


class CheckInRequest(BaseModel):
    member_id: str
    source: str = "manual"


# --- pure logic (unit-tested directly, no DB) -------------------------------


def check_in_allowed(sub: dict | None) -> tuple[bool, str]:
    """Pure decision for POST /attendance/check-in. `sub` is the member's
    most recent subscription (already run through expire_if_due), or None if
    they've never had one. Covers all 5 cases: active / frozen / expired /
    cancelled / no-subscription."""
    if sub is None:
        return False, "no active subscription"
    if sub["status"] == "ACTIVE":
        return True, "ok"
    return False, f"subscription is {sub['status'].lower()}"


# --- routes -------------------------------------------------------------------


@router.post("/attendance/check-in", status_code=201)
def check_in(body: CheckInRequest, staff=Depends(get_current_staff)):
    client = get_admin_client()
    tenant_id = staff["tenant_id"]

    if body.source not in VALID_SOURCES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"source must be one of {VALID_SOURCES}")

    get_member_or_404(client, tenant_id, body.member_id)

    sub = get_latest_subscription(client, tenant_id, body.member_id)
    if sub is not None:
        sub = expire_if_due(client, sub)

    allowed, reason = check_in_allowed(sub)
    if not allowed:
        raise HTTPException(status.HTTP_403_FORBIDDEN, f"Check-in denied: {reason}")

    attendance = (
        client.table("attendance")
        .insert(
            {
                "tenant_id": tenant_id,
                "member_id": body.member_id,
                "branch_id": staff.get("branch_id"),
                "checked_in_at": datetime.now(timezone.utc).isoformat(),
                "source": body.source,
            }
        )
        .execute()
    )

    if sub["sessions_remaining"] is not None:
        remaining = sub["sessions_remaining"] - 1
        update: dict = {"sessions_remaining": remaining}
        if remaining <= 0:
            update["status"] = "EXPIRED"
        client.table("subscription").update(update).eq("id", sub["id"]).execute()

    return attendance.data[0]


@router.get("/members/{member_id}/attendance")
def member_attendance(member_id: str, staff=Depends(get_current_staff)):
    client = get_admin_client()
    tenant_id = staff["tenant_id"]
    get_member_or_404(client, tenant_id, member_id)
    result = (
        client.table("attendance")
        .select("*")
        .eq("tenant_id", tenant_id)
        .eq("member_id", member_id)
        .order("checked_in_at", desc=True)
        .execute()
    )
    return result.data


@router.get("/attendance")
def attendance_by_date(
    date_: str | None = Query(default=None, alias="date"),
    branch_id: str | None = None,
    staff=Depends(get_current_staff),
):
    client = get_admin_client()
    query = client.table("attendance").select("*").eq("tenant_id", staff["tenant_id"])
    if branch_id:
        query = query.eq("branch_id", branch_id)
    if date_:
        day = date.fromisoformat(date_)
        start = datetime.combine(day, time.min, tzinfo=timezone.utc).isoformat()
        end = datetime.combine(day, time.max, tzinfo=timezone.utc).isoformat()
        query = query.gte("checked_in_at", start).lte("checked_in_at", end)
    return query.order("checked_in_at", desc=True).execute().data
