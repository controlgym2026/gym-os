"""Payments — logged against a subscription. No payment-gateway integration
this phase; gateway_ref is a free-text field for a manual reference number."""

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


@router.post("/subscriptions/{subscription_id}/payments", status_code=201)
def create_payment(subscription_id: str, body: PaymentCreate, staff=Depends(get_current_staff)):
    client = get_admin_client()
    tenant_id = staff["tenant_id"]
    get_subscription_or_404(client, tenant_id, subscription_id)
    if body.method not in VALID_METHODS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"method must be one of {VALID_METHODS}")
    if body.status not in VALID_STATUSES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"status must be one of {VALID_STATUSES}")

    payload = body.model_dump()
    payload["tenant_id"] = tenant_id
    payload["subscription_id"] = subscription_id
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
