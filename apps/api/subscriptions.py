"""Subscription lifecycle.

Status transitions (enforced by ALLOWED_TRANSITIONS below):
  ACTIVE  -> FROZEN     manual hold, pauses the end_date countdown
  FROZEN  -> ACTIVE     resume; shifts end_date forward by the frozen duration
  ACTIVE  -> EXPIRED    automatic — see is_expired()/expire_if_due() below
  ACTIVE, FROZEN -> CANCELLED   manual, terminal

`frozen_at` isn't in the original Phase 1 column spec, but resuming needs to
know how long a subscription sat frozen in order to shift end_date forward —
there's no way to compute that without recording when the freeze started, so
it was added in the migration.

"Automatic" EXPIRED is implemented as lazy expiry-on-read/use (expire_if_due),
not a background job — nothing in this phase runs on a schedule.
"""

from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from auth import get_admin_client, get_current_staff
from resources import get_member_or_404, get_plan_or_404, get_subscription_or_404

router = APIRouter(tags=["subscriptions"])

ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "ACTIVE": {"FROZEN", "CANCELLED"},
    "FROZEN": {"ACTIVE", "CANCELLED"},
    "EXPIRED": set(),
    "CANCELLED": set(),
}


class SubscriptionCreate(BaseModel):
    plan_id: str
    start_date: date | None = None
    auto_renew: bool = False
    due_amount: float = 0  # e.g. "owes 2,000 of a 5,000 plan, paying the rest later"


class SubscriptionUpdate(BaseModel):
    # Lifecycle transition (ALLOWED_TRANSITIONS state machine) — unchanged
    # behavior from Phase 1, just now one of several optional fields instead
    # of the only one.
    status: str | None = None  # "ACTIVE" (resume) | "FROZEN" (freeze) | "CANCELLED"
    # Direct field edits ("Edit Membership" — correcting a mistake, not a
    # lifecycle transition). Applied independently of `status`; either or
    # both may be present in one request.
    plan_id: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    due_amount: float | None = None
    sessions_remaining: int | None = None


# --- pure logic (unit-tested directly, no DB) -------------------------------


def is_expired(sub: dict, *, today: date | None = None) -> bool:
    """Would this ACTIVE subscription's end_date/sessions_remaining put it
    into EXPIRED as of `today`? A plan with neither set (shouldn't happen —
    every plan is date- or session-based) never expires by this check."""
    today = today or date.today()
    end_date = sub.get("end_date")
    if end_date and date.fromisoformat(end_date) < today:
        return True
    sessions_remaining = sub.get("sessions_remaining")
    if sessions_remaining is not None and sessions_remaining <= 0:
        return True
    return False


# --- DB-touching helpers -----------------------------------------------------


def expire_if_due(client, sub: dict) -> dict:
    """Flip an ACTIVE subscription to EXPIRED if is_expired() says it should
    be. Returns the (possibly updated) row."""
    if sub["status"] != "ACTIVE" or not is_expired(sub):
        return sub
    result = client.table("subscription").update({"status": "EXPIRED"}).eq("id", sub["id"]).execute()
    return result.data[0]


def get_active_subscription(client, tenant_id: str, member_id: str) -> dict | None:
    """The member's currently ACTIVE subscription, or None. Applies lazy
    expiry first, so a stale-but-still-marked-ACTIVE row never comes back as
    active here."""
    result = (
        client.table("subscription")
        .select("*")
        .eq("tenant_id", tenant_id)
        .eq("member_id", member_id)
        .eq("status", "ACTIVE")
        .execute()
    )
    rows = result.data or []
    if not rows:
        return None
    sub = expire_if_due(client, rows[0])
    return sub if sub["status"] == "ACTIVE" else None


def get_latest_subscription(client, tenant_id: str, member_id: str) -> dict | None:
    """The member's most recent subscription regardless of status, or None
    if they've never had one. Used for check-in's denial-reason message."""
    result = (
        client.table("subscription")
        .select("*")
        .eq("tenant_id", tenant_id)
        .eq("member_id", member_id)
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    rows = result.data or []
    return rows[0] if rows else None


class DuplicateActiveSubscription(Exception):
    """Raised by start_subscription when the member already has one. Not an
    HTTPException — shared by the HTTP route (which turns it into a 409) and
    the CSV member-import path (which just skips starting that subscription
    and keeps going)."""


def build_subscription_payload(
    tenant_id: str,
    member_id: str,
    plan: dict,
    *,
    start_date: date | None = None,
    auto_renew: bool = False,
    due_amount: float = 0,
) -> dict:
    """Pure: the subscription insert payload for `member_id` starting
    `plan`. Shared by start_subscription (the single-subscription path,
    with the duplicate-active-check below) and member_import.py's batch
    path (which skips that check — a member just created by the same
    import can't already have a subscription, so there's nothing to
    check, and checking per-row is exactly what made large imports slow).
    """
    start = start_date or date.today()
    payload: dict = {
        "tenant_id": tenant_id,
        "member_id": member_id,
        "plan_id": plan["id"],
        "start_date": start.isoformat(),
        "auto_renew": auto_renew,
        "due_amount": due_amount,
        "status": "ACTIVE",
    }
    if plan["session_limit"] is not None:
        payload["sessions_remaining"] = plan["session_limit"]
        payload["end_date"] = None
    else:
        payload["end_date"] = (start + timedelta(days=plan["duration_days"])).isoformat()
    return payload


def start_subscription(
    client,
    tenant_id: str,
    member_id: str,
    plan: dict,
    *,
    start_date: date | None = None,
    auto_renew: bool = False,
    due_amount: float = 0,
) -> dict:
    """Core subscription-creation logic, shared by the HTTP route below and
    member_import.py. Caller is responsible for member/plan existence and
    plan.is_active checks — this only handles the duplicate-active guard and
    the actual insert."""
    # Block starting a second ACTIVE subscription (our chosen behavior —
    # cancel or let the existing one expire/complete first) rather than
    # silently superseding it. The DB has a matching partial unique index
    # as a backstop against the same race this check alone can't close.
    if get_active_subscription(client, tenant_id, member_id) is not None:
        raise DuplicateActiveSubscription()

    payload = build_subscription_payload(
        tenant_id, member_id, plan, start_date=start_date, auto_renew=auto_renew, due_amount=due_amount
    )
    try:
        result = client.table("subscription").insert(payload).execute()
    except Exception as exc:
        raise DuplicateActiveSubscription() from exc
    return result.data[0]


# --- routes -------------------------------------------------------------------


@router.post("/members/{member_id}/subscriptions", status_code=201)
def create_subscription(member_id: str, body: SubscriptionCreate, staff=Depends(get_current_staff)):
    client = get_admin_client()
    tenant_id = staff["tenant_id"]
    get_member_or_404(client, tenant_id, member_id)
    plan = get_plan_or_404(client, tenant_id, body.plan_id)
    if not plan["is_active"]:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Plan is not active")
    if body.due_amount < 0:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "due_amount cannot be negative")

    try:
        return start_subscription(
            client,
            tenant_id,
            member_id,
            plan,
            start_date=body.start_date,
            auto_renew=body.auto_renew,
            due_amount=body.due_amount,
        )
    except DuplicateActiveSubscription:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Member already has an active subscription — cancel it first",
        )


@router.get("/members/{member_id}/subscriptions")
def list_member_subscriptions(member_id: str, staff=Depends(get_current_staff)):
    client = get_admin_client()
    tenant_id = staff["tenant_id"]
    get_member_or_404(client, tenant_id, member_id)
    result = (
        client.table("subscription")
        .select("*")
        .eq("tenant_id", tenant_id)
        .eq("member_id", member_id)
        .order("created_at", desc=True)
        .execute()
    )
    return [expire_if_due(client, s) for s in result.data]


@router.patch("/subscriptions/{subscription_id}")
def update_subscription(subscription_id: str, body: SubscriptionUpdate, staff=Depends(get_current_staff)):
    client = get_admin_client()
    tenant_id = staff["tenant_id"]
    sub = get_subscription_or_404(client, tenant_id, subscription_id)

    update: dict = {}

    if body.status is not None:
        sub = expire_if_due(client, sub)
        new_status = body.status.upper()
        if new_status not in ALLOWED_TRANSITIONS:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Unknown status '{body.status}'")
        if new_status not in ALLOWED_TRANSITIONS[sub["status"]]:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                f"Cannot move subscription from {sub['status']} to {new_status}",
            )
        update["status"] = new_status
        if new_status == "FROZEN":
            update["frozen_at"] = datetime.now(timezone.utc).isoformat()
        elif new_status == "ACTIVE":  # resuming from FROZEN (the only transition into ACTIVE)
            update["frozen_at"] = None
            if sub.get("end_date") and sub.get("frozen_at"):
                frozen_since = datetime.fromisoformat(sub["frozen_at"])
                frozen_days = (datetime.now(timezone.utc) - frozen_since).days
                update["end_date"] = (date.fromisoformat(sub["end_date"]) + timedelta(days=frozen_days)).isoformat()

    if body.plan_id is not None:
        plan = get_plan_or_404(client, tenant_id, body.plan_id)
        update["plan_id"] = plan["id"]
    if body.start_date is not None:
        update["start_date"] = body.start_date.isoformat()
    if body.end_date is not None:
        update["end_date"] = body.end_date.isoformat()
    if body.due_amount is not None:
        if body.due_amount < 0:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "due_amount cannot be negative")
        update["due_amount"] = body.due_amount
    if body.sessions_remaining is not None:
        if body.sessions_remaining < 0:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "sessions_remaining cannot be negative")
        update["sessions_remaining"] = body.sessions_remaining

    if not update:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No changes given")

    result = (
        client.table("subscription")
        .update(update)
        .eq("tenant_id", tenant_id)
        .eq("id", subscription_id)
        .execute()
    )
    return result.data[0]
