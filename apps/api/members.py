"""Member management — CRUD + soft delete, all tenant-scoped.

Photos: the frontend uploads directly to the existing `member-media` Supabase
Storage bucket (its policies already scope access by tenant_id via the path's
first segment — see supabase/migrations/20260910134957_storage_member_media.sql)
and then PATCHes photo_url here with the resulting storage path. The backend
never touches the file itself.
"""

import re
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from auth import get_admin_client, get_current_staff
from resources import get_member_or_404
from subscriptions import expire_if_due

router = APIRouter(prefix="/members", tags=["members"])

# PostgREST or() filter syntax uses "," and "()" as structural characters —
# strip them from free-text search input rather than trying to escape them.
_UNSAFE_FILTER_CHARS = re.compile(r"[,()]")


class MemberCreate(BaseModel):
    name: str
    phone: str | None = None
    email: str | None = None
    branch_id: str | None = None


class MemberUpdate(BaseModel):
    name: str | None = None
    phone: str | None = None
    email: str | None = None
    branch_id: str | None = None
    photo_url: str | None = None
    # Biometric enrollment (Phase 2): device-side enrollment assigns a PIN on
    # the terminal itself; staff copies that PIN in here. biometric_ref only
    # ever holds that PIN — never a template or face image.
    biometric_ref: str | None = None
    biometric_consent: bool | None = None


@router.post("", status_code=201)
def create_member(body: MemberCreate, staff=Depends(get_current_staff)):
    client = get_admin_client()
    payload = body.model_dump(exclude_none=True)
    payload["tenant_id"] = staff["tenant_id"]
    try:
        result = client.table("member").insert(payload).execute()
    except Exception as exc:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "A member with this phone number already exists"
        ) from exc
    return result.data[0]


def _attach_current_subscriptions(client, tenant_id: str, members: list[dict]) -> list[dict]:
    """Each member's most recent subscription (same "current" convention
    used everywhere else — most recent by created_at, regardless of status),
    lazily expired first so a stale-but-still-ACTIVE row doesn't show wrong
    on the list, with its plan name attached. Powers the members list's Days
    Left/Expiry/Due/Status columns without an N+1 request per row."""
    member_ids = [m["id"] for m in members]
    if not member_ids:
        return members

    subs = (
        client.table("subscription")
        .select("*")
        .eq("tenant_id", tenant_id)
        .in_("member_id", member_ids)
        .order("created_at", desc=True)
        .execute()
        .data
    )
    latest_by_member: dict[str, dict] = {}
    for s in subs:
        latest_by_member.setdefault(s["member_id"], s)  # first seen per member = most recent (query is desc)
    latest_by_member = {mid: expire_if_due(client, s) for mid, s in latest_by_member.items()}

    plan_ids = list({s["plan_id"] for s in latest_by_member.values()})
    plans = (
        client.table("membership_plan").select("id, name").in_("id", plan_ids).execute().data if plan_ids else []
    )
    plan_name_by_id = {p["id"]: p["name"] for p in plans}

    for m in members:
        sub = latest_by_member.get(m["id"])
        m["current_subscription"] = (
            None
            if sub is None
            else {
                "id": sub["id"],
                "plan_id": sub["plan_id"],
                "plan_name": plan_name_by_id.get(sub["plan_id"], "—"),
                "status": sub["status"],
                "start_date": sub["start_date"],
                "end_date": sub["end_date"],
                "due_amount": sub["due_amount"],
                "sessions_remaining": sub["sessions_remaining"],
            }
        )
    return members


DEFAULT_PAGE_SIZE = 25
MAX_PAGE_SIZE = 500  # generous cap — attendance/unmatched.tsx's "assign to
# member" picker asks for one big page rather than a second pagination UI;
# 500 comfortably covers a single gym's member count for that use case.


@router.get("")
def list_members(q: str | None = None, page: int = 1, page_size: int = DEFAULT_PAGE_SIZE, staff=Depends(get_current_staff)):
    client = get_admin_client()
    tenant_id = staff["tenant_id"]
    page = max(1, page)
    page_size = min(max(1, page_size), MAX_PAGE_SIZE)
    offset = (page - 1) * page_size

    query = (
        client.table("member")
        .select("*", count="exact")
        .eq("tenant_id", tenant_id)
        .is_("deleted_at", "null")
    )
    if q:
        # Server-side against the full dataset, same as before pagination —
        # this filter runs before .range() below, not after.
        safe = _UNSAFE_FILTER_CHARS.sub("", q)
        query = query.or_(f"name.ilike.%{safe}%,phone.ilike.%{safe}%")
    result = query.order("created_at", desc=True).range(offset, offset + page_size - 1).execute()

    return {
        "items": _attach_current_subscriptions(client, tenant_id, result.data),
        "total": result.count or 0,
        "page": page,
        "page_size": page_size,
    }


@router.get("/{member_id}")
def get_member(member_id: str, staff=Depends(get_current_staff)):
    return get_member_or_404(get_admin_client(), staff["tenant_id"], member_id)


@router.patch("/{member_id}")
def update_member(member_id: str, body: MemberUpdate, staff=Depends(get_current_staff)):
    client = get_admin_client()
    tenant_id = staff["tenant_id"]
    get_member_or_404(client, tenant_id, member_id)
    payload = body.model_dump(exclude_unset=True)
    if not payload:
        return get_member_or_404(client, tenant_id, member_id)

    if "biometric_ref" in payload:
        if payload["biometric_ref"] is not None:
            # Same rule as the DB check constraint (member_biometric_consent_required)
            # — enforced here first for a clear 400 instead of a raw DB error.
            if not payload.get("biometric_consent"):
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST,
                    "Setting biometric_ref requires biometric_consent=true in the same request",
                )
            payload["biometric_consent_at"] = datetime.now(timezone.utc).isoformat()
        else:
            # Clearing the PIN also clears consent, so the two can't drift.
            payload["biometric_consent"] = False
            payload["biometric_consent_at"] = None

    try:
        result = (
            client.table("member")
            .update(payload)
            .eq("tenant_id", tenant_id)
            .eq("id", member_id)
            .execute()
        )
    except Exception as exc:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "A member with this phone number already exists"
        ) from exc
    return result.data[0]


@router.delete("/{member_id}", status_code=204)
def delete_member(member_id: str, staff=Depends(get_current_staff)):
    """Soft delete: sets deleted_at rather than removing the row, so
    attendance/subscription/payment history stays intact."""
    client = get_admin_client()
    tenant_id = staff["tenant_id"]
    get_member_or_404(client, tenant_id, member_id)
    client.table("member").update(
        {"deleted_at": datetime.now(timezone.utc).isoformat()}
    ).eq("tenant_id", tenant_id).eq("id", member_id).execute()
