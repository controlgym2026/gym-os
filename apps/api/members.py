"""Member management — CRUD + soft delete, all tenant-scoped.

Photos: the frontend uploads directly to the existing `member-media` Supabase
Storage bucket (its policies already scope access by tenant_id via the path's
first segment — see supabase/migrations/20260910134957_storage_member_media.sql)
and then PATCHes photo_url here with the resulting storage path. The backend
never touches the file itself.
"""

import re
from datetime import date, datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from postgrest.exceptions import APIError
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


EXPIRING_SOON_DAYS = 7

# Values accepted by GET /members?filter= — all are predicates on the
# member's *current subscription*, not on the member row itself.
MEMBER_FILTERS = ("active", "expiring", "expired", "due", "paid")


def member_matches_filter(
    sub: dict | None,
    filter_name: str | None,
    plan_id: str | None = None,
    *,
    today: date | None = None,
) -> bool:
    """Pure: does a member whose current subscription is `sub` belong in the
    filtered list? `plan_id` and `filter_name` are independent and both are
    optional — passing both means "this filter AND this plan". A member with
    no subscription at all matches only the unfiltered case."""
    if plan_id and (sub is None or sub.get("plan_id") != plan_id):
        return False
    if not filter_name:
        return True
    if sub is None:
        return False

    if filter_name == "active":
        return sub.get("status") == "ACTIVE"
    if filter_name == "expiring":
        # "Expires" = still ACTIVE but running out within the window, i.e. a
        # renewal-followup list. Session-based plans have no end_date and so
        # never appear here.
        if sub.get("status") != "ACTIVE" or not sub.get("end_date"):
            return False
        days_left = (date.fromisoformat(sub["end_date"]) - (today or date.today())).days
        return 0 <= days_left <= EXPIRING_SOON_DAYS
    if filter_name == "expired":
        # Already lapsed, as opposed to "expiring" (still active, running
        # out soon) — lazy-expiry has already run by the time this is
        # called, so a date-based subscription past its end_date is already
        # status == "EXPIRED" here, not stale ACTIVE.
        return sub.get("status") == "EXPIRED"
    if filter_name == "due":
        return (sub.get("due_amount") or 0) > 0
    if filter_name == "paid":
        return (sub.get("due_amount") or 0) <= 0
    return True


def _latest_subscriptions_by_member(
    client, tenant_id: str, member_ids: list[str] | None = None
) -> dict[str, dict]:
    """member_id -> that member's current subscription (most recent by
    created_at regardless of status, the same "current" convention used
    everywhere else), lazily expired so a stale-but-still-ACTIVE row doesn't
    read wrong. `member_ids=None` means every member in the tenant — used by
    the filtered list path, which has to know each member's status before it
    can decide who's even on the page, and which therefore can't send an
    .in_() of every member id without blowing the URL length limit."""
    query = client.table("subscription").select("*").eq("tenant_id", tenant_id)
    if member_ids is not None:
        if not member_ids:
            return {}
        query = query.in_("member_id", member_ids)
    subs = query.order("created_at", desc=True).execute().data

    latest_by_member: dict[str, dict] = {}
    for s in subs:
        latest_by_member.setdefault(s["member_id"], s)  # first seen per member = most recent (query is desc)
    return {mid: expire_if_due(client, s) for mid, s in latest_by_member.items()}


def _attach_current_subscriptions(
    client, tenant_id: str, members: list[dict], latest_by_member: dict[str, dict] | None = None
) -> list[dict]:
    """Attaches each member's current subscription (with its plan name) as
    `current_subscription`. Powers the members list's Days Left/Expiry/Due/
    Status columns without an N+1 request per row. `latest_by_member` lets
    the filtered path pass in the map it already had to compute."""
    if not members:
        return members
    if latest_by_member is None:
        latest_by_member = _latest_subscriptions_by_member(client, tenant_id, [m["id"] for m in members])

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


def _filtered_members_query(client, tenant_id: str, q: str | None):
    query = (
        client.table("member")
        .select("*", count="exact")
        .eq("tenant_id", tenant_id)
        .is_("deleted_at", "null")
    )
    if q:
        # Server-side against the full dataset, same as before pagination —
        # this filter runs before .range() is applied, not after.
        safe = _UNSAFE_FILTER_CHARS.sub("", q)
        query = query.or_(f"name.ilike.%{safe}%,phone.ilike.%{safe}%")
    return query


@router.get("")
def list_members(
    q: str | None = None,
    # Annotated (not `= Query(...)`) so the real Python default stays None and
    # the route is directly callable in tests, not just through HTTP.
    subscription_filter: Annotated[str | None, Query(alias="filter")] = None,
    plan_id: str | None = None,
    page: int = 1,
    page_size: int = DEFAULT_PAGE_SIZE,
    staff=Depends(get_current_staff),
):
    client = get_admin_client()
    tenant_id = staff["tenant_id"]
    page = max(1, page)
    page_size = min(max(1, page_size), MAX_PAGE_SIZE)
    offset = (page - 1) * page_size

    if subscription_filter and subscription_filter not in MEMBER_FILTERS:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Unknown filter '{subscription_filter}' — expected one of {', '.join(MEMBER_FILTERS)}",
        )

    if subscription_filter or plan_id:
        # Status/due/plan live on the subscription, not the member row, so
        # PostgREST can't paginate this for us. Resolve every member's
        # current subscription (2 queries, not N) and page in Python. Bounded
        # by one gym's member count, which is what this product is scoped to.
        members = _filtered_members_query(client, tenant_id, q).order("created_at", desc=True).execute().data
        latest_by_member = _latest_subscriptions_by_member(client, tenant_id)
        matched = [
            m
            for m in members
            if member_matches_filter(latest_by_member.get(m["id"]), subscription_filter, plan_id)
        ]
        return {
            "items": _attach_current_subscriptions(
                client, tenant_id, matched[offset : offset + page_size], latest_by_member
            ),
            "total": len(matched),
            "page": page,
            "page_size": page_size,
        }

    query = _filtered_members_query(client, tenant_id, q).order("created_at", desc=True)
    try:
        result = query.range(offset, offset + page_size - 1).execute()
        items, total = result.data, result.count or 0
    except APIError as exc:
        if exc.code != "PGRST103":
            raise
        # PostgREST rejects a range whose offset is past the last row
        # (PGRST103, "Requested range not satisfiable") instead of just
        # returning an empty page — e.g. paging forward past the end, or the
        # last item on the final page got deleted between loads. Not a real
        # error; recover the count with one more (cheap, unranged) request.
        items = []
        total = _filtered_members_query(client, tenant_id, q).limit(1).execute().count or 0

    return {
        "items": _attach_current_subscriptions(client, tenant_id, items),
        "total": total,
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
