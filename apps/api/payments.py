"""Payments — logged against a subscription. No payment-gateway integration
this phase; gateway_ref is a free-text field for a manual reference number.

transaction_type is never client-supplied directly — it's inferred:
  - is_due_payment=True on the request  -> 'due_payment' (and decrements the
    subscription's due_amount, floored at 0)
  - otherwise -> 'admission' if this is the member's first-ever subscription,
    'renewal' if they've had one before (see classify_admission_or_renewal)
"""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from auth import get_admin_client, get_current_staff
from resources import get_subscription_or_404

router = APIRouter(tags=["payments"])

VALID_METHODS = ("cash", "card", "upi", "other")
VALID_STATUSES = ("pending", "completed", "failed", "refunded")


class PaymentCreate(BaseModel):
    amount: float
    method: str
    gateway_ref: str | None = None
    status: str = "completed"
    discount_amount: float = 0
    is_due_payment: bool = False


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
