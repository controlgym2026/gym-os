"""Expense tracking — new in Phase 6 (finance parity with GymOps).

Deletion is a HARD delete, unlike member/subscription (soft-deleted
everywhere else in this app). Expenses aren't a legal/business record
anyone needs an audit trail for the way a member's membership history is —
they're closer to a correction-friendly ledger line; a misentered expense
should just be removable, not left as deleted_at clutter forever. If that
turns out wrong (e.g. a future "who deleted this and when" need), it's an
easy follow-up — add deleted_at the same way member/subscription already
have it.
"""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from auth import get_admin_client, get_current_staff, require_owner
from finance_period import InvalidPeriod, resolve_period, today_ist
from payments import VALID_METHODS
from resources import get_expense_or_404

router = APIRouter(prefix="/expenses", tags=["expenses"])

# Suggested presets only — category is free text (see the migration's own
# note on this), not an enum. The frontend shows these in a datalist
# alongside whatever the gym has already typed before.
CATEGORY_PRESETS = ("Rent", "Salary", "Electricity", "Equipment", "Maintenance", "Marketing", "Other")

DEFAULT_PAGE_SIZE = 25
MAX_PAGE_SIZE = 500


class ExpenseCreate(BaseModel):
    category: str
    amount: float
    expense_date: date | None = None  # defaults to today (IST) below
    payment_mode: str = "cash"
    description: str | None = None


class ExpenseUpdate(BaseModel):
    category: str | None = None
    amount: float | None = None
    expense_date: date | None = None
    payment_mode: str | None = None
    description: str | None = None


def _validate_amount(amount: float) -> None:
    if amount <= 0:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "amount must be positive")


def _validate_mode(mode: str) -> None:
    if mode not in VALID_METHODS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"payment_mode must be one of {VALID_METHODS}")


@router.get("/categories")
def list_category_presets(staff=Depends(get_current_staff)):
    """Suggested categories for the Add Expense form's datalist — not an
    enforced set, just a starting point."""
    require_owner(staff)
    return list(CATEGORY_PRESETS)


@router.post("", status_code=201)
def create_expense(body: ExpenseCreate, staff=Depends(get_current_staff)):
    require_owner(staff)
    client = get_admin_client()
    _validate_amount(body.amount)
    _validate_mode(body.payment_mode)
    payload = {
        "tenant_id": staff["tenant_id"],
        "category": body.category.strip(),
        "amount": body.amount,
        "expense_date": (body.expense_date or today_ist()).isoformat(),
        "payment_mode": body.payment_mode,
        "description": body.description,
        "created_by": staff["id"],
    }
    result = client.table("expense").insert(payload).execute()
    return result.data[0]


@router.get("")
def list_expenses(
    period: str = "this_month",
    from_: str | None = None,
    to: str | None = None,
    category: str | None = None,
    page: int = 1,
    page_size: int = DEFAULT_PAGE_SIZE,
    staff=Depends(get_current_staff),
):
    require_owner(staff)
    client = get_admin_client()
    tenant_id = staff["tenant_id"]
    page = max(1, page)
    page_size = min(max(1, page_size), MAX_PAGE_SIZE)
    offset = (page - 1) * page_size

    try:
        custom_from = date.fromisoformat(from_) if from_ else None
        custom_to = date.fromisoformat(to) if to else None
        range_from, range_to = resolve_period(period, today_ist(), custom_from, custom_to)
    except InvalidPeriod as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    query = (
        client.table("expense")
        .select("*", count="exact")
        .eq("tenant_id", tenant_id)
        .gte("expense_date", range_from.isoformat())
        .lte("expense_date", range_to.isoformat())
    )
    if category:
        query = query.eq("category", category)
    result = query.order("expense_date", desc=True).range(offset, offset + page_size - 1).execute()

    return {
        "items": result.data,
        "total": result.count or 0,
        "page": page,
        "page_size": page_size,
    }


@router.patch("/{expense_id}")
def update_expense(expense_id: str, body: ExpenseUpdate, staff=Depends(get_current_staff)):
    require_owner(staff)
    client = get_admin_client()
    tenant_id = staff["tenant_id"]
    get_expense_or_404(client, tenant_id, expense_id)

    payload = body.model_dump(exclude_unset=True)
    if "amount" in payload and payload["amount"] is not None:
        _validate_amount(payload["amount"])
    if "payment_mode" in payload and payload["payment_mode"] is not None:
        _validate_mode(payload["payment_mode"])
    if "expense_date" in payload and payload["expense_date"] is not None:
        payload["expense_date"] = payload["expense_date"].isoformat()
    if "category" in payload and payload["category"] is not None:
        payload["category"] = payload["category"].strip()
    if not payload:
        return get_expense_or_404(client, tenant_id, expense_id)

    result = client.table("expense").update(payload).eq("tenant_id", tenant_id).eq("id", expense_id).execute()
    return result.data[0]


@router.delete("/{expense_id}", status_code=204)
def delete_expense(expense_id: str, staff=Depends(get_current_staff)):
    require_owner(staff)
    client = get_admin_client()
    tenant_id = staff["tenant_id"]
    get_expense_or_404(client, tenant_id, expense_id)
    client.table("expense").delete().eq("tenant_id", tenant_id).eq("id", expense_id).execute()
