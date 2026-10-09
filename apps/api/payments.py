"""Payments — logged against a subscription (admission/renewal/due_payment),
or standalone (pt/service/product — see create_income below). No
payment-gateway integration this phase; gateway_ref is a free-text field
for a manual reference number, reused for create_income's `note` rather
than adding a dedicated column for the same kind of free text.

transaction_type is never client-supplied directly for a subscription
payment — it's inferred:
  - is_due_payment=True on the request  -> 'due_payment' (and decrements the
    subscription's due_amount, floored at 0)
  - otherwise -> 'admission' if this is the member's first-ever subscription,
    'renewal' if they've had one before (see classify_admission_or_renewal)
create_income's category (pt/service/product) IS client-supplied — there's
no subscription to infer it from.
"""

from datetime import date, datetime, time, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from auth import get_admin_client, get_current_staff
from finance_period import IST
from resources import get_member_or_404, get_subscription_or_404

router = APIRouter(tags=["payments"])

VALID_METHODS = ("cash", "card", "upi", "other")
VALID_STATUSES = ("pending", "completed", "failed", "refunded")
# The three Phase 6 income categories not tied to any subscription — PT
# sessions, one-off services, product/merchandise sales.
INCOME_CATEGORIES = ("pt", "service", "product")


class PaymentCreate(BaseModel):
    amount: float
    method: str
    gateway_ref: str | None = None
    status: str = "completed"
    discount_amount: float = 0
    is_due_payment: bool = False


class IncomeCreate(BaseModel):
    category: str  # one of INCOME_CATEGORIES
    member_id: str | None = None  # optional — e.g. a walk-in product sale
    amount: float
    discount_amount: float = 0
    method: str
    # Named income_date, not `date` — a field named identically to its own
    # `date` type annotation breaks Pydantic's forward-ref evaluation
    # ("unsupported operand type(s) for |: 'NoneType' and 'NoneType'").
    income_date: date | None = None  # defaults to now (IST) if omitted
    note: str | None = None  # stored as gateway_ref


# --- pure logic (unit-tested directly, no DB) -------------------------------


def classify_admission_or_renewal(earliest_subscription_id: str | None, this_subscription_id: str) -> str:
    """'admission' if `this_subscription_id` is the member's earliest-ever
    subscription (by created_at), else 'renewal'. Takes the already-resolved
    earliest id rather than querying itself, so it's testable with plain
    strings — see find_earliest_subscription_id() for the DB lookup."""
    return "admission" if earliest_subscription_id == this_subscription_id else "renewal"


def apply_due_payment(due_amount: float, payment_amount: float) -> float:
    """New due_amount after a due_payment of `payment_amount` — never below 0
    (e.g. an overpayment or a rounding mismatch shouldn't produce a negative
    balance)."""
    return max(0.0, due_amount - payment_amount)


# --- DB-touching helpers -----------------------------------------------------


def find_earliest_subscription_id(client, tenant_id: str, member_id: str) -> str | None:
    result = (
        client.table("subscription")
        .select("id")
        .eq("tenant_id", tenant_id)
        .eq("member_id", member_id)
        .order("created_at", desc=False)
        .limit(1)
        .execute()
    )
    rows = result.data or []
    return rows[0]["id"] if rows else None


# --- routes -------------------------------------------------------------------


@router.post("/subscriptions/{subscription_id}/payments", status_code=201)
def create_payment(subscription_id: str, body: PaymentCreate, staff=Depends(get_current_staff)):
    client = get_admin_client()
    tenant_id = staff["tenant_id"]
    sub = get_subscription_or_404(client, tenant_id, subscription_id)
    if body.method not in VALID_METHODS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"method must be one of {VALID_METHODS}")
    if body.status not in VALID_STATUSES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"status must be one of {VALID_STATUSES}")

    if body.is_due_payment:
        transaction_type = "due_payment"
    else:
        earliest_id = find_earliest_subscription_id(client, tenant_id, sub["member_id"])
        transaction_type = classify_admission_or_renewal(earliest_id, subscription_id)

    payload = {
        "tenant_id": tenant_id,
        "subscription_id": subscription_id,
        "member_id": sub["member_id"],
        "amount": body.amount,
        "method": body.method,
        "gateway_ref": body.gateway_ref,
        "status": body.status,
        "discount_amount": body.discount_amount,
        "transaction_type": transaction_type,
    }
    result = client.table("payment").insert(payload).execute()

    if body.is_due_payment:
        new_due = apply_due_payment(sub["due_amount"], body.amount)
        client.table("subscription").update({"due_amount": new_due}).eq("id", subscription_id).execute()

    return result.data[0]


@router.post("/income", status_code=201)
def create_income(body: IncomeCreate, staff=Depends(get_current_staff)):
    """Record a PT/service/product sale — not tied to any subscription,
    unlike create_payment above. member_id is optional (e.g. a walk-in
    product sale with no member record at all)."""
    client = get_admin_client()
    tenant_id = staff["tenant_id"]

    if body.category not in INCOME_CATEGORIES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"category must be one of {INCOME_CATEGORIES}")
    if body.method not in VALID_METHODS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"method must be one of {VALID_METHODS}")
    if body.amount <= 0:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "amount must be positive")
    if body.discount_amount < 0:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "discount_amount cannot be negative")
    if body.member_id is not None:
        get_member_or_404(client, tenant_id, body.member_id)  # 404s a bogus or other-tenant id

    payload = {
        "tenant_id": tenant_id,
        "subscription_id": None,
        "member_id": body.member_id,
        "amount": body.amount,
        "discount_amount": body.discount_amount,
        "method": body.method,
        "gateway_ref": body.note,
        "status": "completed",
        "transaction_type": body.category,
    }
    if body.income_date is not None:
        # Anchored at noon IST, not midnight — sidesteps any day-boundary
        # ambiguity when this gets converted back to a UTC instant for
        # period filtering (see finance_period.ist_day_bounds_to_utc).
        anchored = datetime.combine(body.income_date, time(12, 0), tzinfo=IST).astimezone(timezone.utc)
        payload["created_at"] = anchored.isoformat()

    result = client.table("payment").insert(payload).execute()
    return result.data[0]


@router.get("/subscriptions/{subscription_id}/payments")
def list_payments(subscription_id: str, staff=Depends(get_current_staff)):
    client = get_admin_client()
    tenant_id = staff["tenant_id"]
    get_subscription_or_404(client, tenant_id, subscription_id)
    result = (
        client.table("payment")
        .select("*")
        .eq("tenant_id", tenant_id)
        .eq("subscription_id", subscription_id)
        .order("created_at", desc=True)
        .execute()
    )
    return result.data


@router.get("/members/{member_id}/transactions")
def member_transactions(member_id: str, staff=Depends(get_current_staff)):
    """A member's full payment history — membership payments across all
    their subscriptions AND any standalone pt/service/product sales
    recorded against them directly, since Phase 6. list_payments above is
    per-subscription only, which isn't enough for the member details
    modal's Transaction History panel.

    Filters on payment.member_id directly rather than joining through
    subscription_id — every payment row carries member_id now (backfilled
    for pre-Phase-6 rows in the migration, set directly by create_payment/
    create_income for everything since), so this single filter already
    covers both payment shapes without a two-step lookup.
    """
    client = get_admin_client()
    tenant_id = staff["tenant_id"]
    get_member_or_404(client, tenant_id, member_id)

    result = (
        client.table("payment")
        .select("*")
        .eq("tenant_id", tenant_id)
        .eq("member_id", member_id)
        .order("created_at", desc=True)
        .execute()
    )
    return result.data
