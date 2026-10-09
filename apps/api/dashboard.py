"""Home dashboard + finance report — reporting over data the other modules
already collect (member/membership_plan/subscription/payment/expense).

Judgment calls, flagged as asked:
- "income"/"profit" and every bucket only count payments with
  status == 'completed'. A pending/failed/refunded payment isn't real
  income yet.
- "online" = every payment method except 'cash' (card, upi, other) — the
  method enum has no literal 'online' value, so this is the natural
  cash-vs-digital split.
- Expense is real as of Phase 6 (see expense.py) — no longer hardcoded 0.
- Aggregation runs server-side via the finance_summary() Postgres function
  (one query, not Python loops over every fetched payment row) — see that
  function's own docstring in the migration for why.
- recent_transactions stays a fixed last-20 list, unrelated to the selected
  period — the home dashboard (which has no period selector) still wants
  something to show; /finance's Income tab is the real period-scoped,
  paginated list (get_income_transactions below), not this.
- Periods resolve in IST (Asia/Kolkata), not UTC — see finance_period.py.
"""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status

from auth import get_admin_client, get_current_staff, require_owner
from finance_period import (
    InvalidPeriod,
    format_range_label,
    ist_day_bounds_to_utc,
    resolve_period,
    today_ist,
)

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

RECENT_TRANSACTIONS_LIMIT = 20
DEFAULT_PAGE_SIZE = 25
MAX_PAGE_SIZE = 500

# transaction_type values that come from a subscription (admission/renewal/
# due_payment) vs. the three standalone ones (pt/service/product) — both
# groups are "income categories" for the summary cards.
INCOME_CATEGORY_KEYS = ("admission", "renewal", "due_payment", "pt", "service", "product")


# --- pure logic (unit-tested directly, no DB) --------------------------------


def aggregate_income_breakdown(breakdown: list[dict]) -> dict:
    """Pure: finance_summary()'s `income_breakdown` (one row per
    transaction_type x method combo actually present) -> the full set of
    category/mode buckets plus income/discount totals. Small input (at most
    4 transaction_types x 4 methods = 16 rows) — this is cheap grouping in
    Python, not the "loop over every payment row" pattern that doesn't
    scale; the heavy aggregation already happened in Postgres."""
    categories = {k: {"count": 0, "amount": 0.0} for k in INCOME_CATEGORY_KEYS}
    online = {"count": 0, "amount": 0.0}
    cash = {"count": 0, "amount": 0.0}
    income = 0.0
    discount_total = 0.0

    for row in breakdown:
        ttype = row["transaction_type"]
        count = row["count"]
        amount = row["amount"]
        if ttype in categories:
            categories[ttype]["count"] += count
            categories[ttype]["amount"] += amount
        income += amount
        discount_total += row["discount"]

        mode_bucket = cash if row["method"] == "cash" else online
        mode_bucket["count"] += count
        mode_bucket["amount"] += amount

    return {
        "income": income,
        "discount_total": discount_total,
        "admissions": categories["admission"],
        "renewals": categories["renewal"],
        "due_paid": categories["due_payment"],
        "pt": categories["pt"],
        "service": categories["service"],
        "product": categories["product"],
        "online": online,
        "cash": cash,
    }


# --- DB-touching helpers ------------------------------------------------------


def _resolve_range(period: str, from_: str | None, to: str | None) -> tuple[date, date]:
    """Shared by both routes below. `from_`/`to` given without an explicit
    `period` is treated as period=custom — preserves the pre-Phase-6 API
    contract (GET /dashboard/summary?from=&to=) exactly."""
    effective_period = period
    custom_from = custom_to = None
    if from_ or to:
        effective_period = "custom"
        try:
            custom_from = date.fromisoformat(from_) if from_ else None
            custom_to = date.fromisoformat(to) if to else None
        except ValueError as exc:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"invalid date: {exc}") from exc
    try:
        return resolve_period(effective_period, today_ist(), custom_from, custom_to)
    except InvalidPeriod as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc


def _enrich_transactions(client, tenant_id: str, payments: list[dict]) -> list[dict]:
    """payment rows -> display-ready rows with member/plan names attached.
    Handles both shapes: subscription-linked (admission/renewal/
    due_payment, plan_name resolved via subscription->membership_plan) and
    standalone (pt/service/product, no subscription — plan_name is None)."""
    sub_ids = list({p["subscription_id"] for p in payments if p["subscription_id"]})
    subs = (
        client.table("subscription").select("id, plan_id").in_("id", sub_ids).execute().data if sub_ids else []
    )
    plan_id_by_sub_id = {s["id"]: s["plan_id"] for s in subs}

    member_ids = list({p["member_id"] for p in payments if p["member_id"]})
    members = client.table("member").select("id, name").in_("id", member_ids).execute().data if member_ids else []
    member_name_by_id = {m["id"]: m["name"] for m in members}

    plan_ids = list({pid for pid in plan_id_by_sub_id.values()})
    plans = (
        client.table("membership_plan").select("id, name").in_("id", plan_ids).execute().data if plan_ids else []
    )
    plan_name_by_id = {p["id"]: p["name"] for p in plans}

    out = []
    for p in payments:
        plan_id = plan_id_by_sub_id.get(p["subscription_id"]) if p["subscription_id"] else None
        out.append(
            {
                "id": p["id"],
                "transaction_type": p["transaction_type"],
                "date": p["created_at"],
                "plan_name": plan_name_by_id.get(plan_id) if plan_id else None,
                "amount": p["amount"],
                "discount_amount": p["discount_amount"],
                "member_id": p["member_id"],
                "member_name": member_name_by_id.get(p["member_id"], "—") if p["member_id"] else "—",
                "method": p["method"],
                "gateway_ref": p["gateway_ref"],
            }
        )
    return out


# --- routes -------------------------------------------------------------------


@router.get("/summary")
def get_summary(
    period: str = "this_month",
    from_: str | None = Query(default=None, alias="from"),
    to: str | None = Query(default=None),
    staff=Depends(get_current_staff),
):
    require_owner(staff)
    client = get_admin_client()
    tenant_id = staff["tenant_id"]

    range_from, range_to = _resolve_range(period, from_, to)
    start_utc, end_utc = ist_day_bounds_to_utc(range_from, range_to)

    summary = client.rpc(
        "finance_summary",
        {
            "p_tenant_id": tenant_id,
            "p_from": start_utc.isoformat(),
            "p_to": end_utc.isoformat(),
            "p_from_date": range_from.isoformat(),
            "p_to_date": range_to.isoformat(),
        },
    ).execute().data

    agg = aggregate_income_breakdown(summary["income_breakdown"])
    expense = summary["expense_total"] or 0

    recent_raw = (
        client.table("payment")
        .select("*")
        .eq("tenant_id", tenant_id)
        .order("created_at", desc=True)
        .limit(RECENT_TRANSACTIONS_LIMIT)
        .execute()
        .data
    )

    return {
        "range": {"from": range_from.isoformat(), "to": range_to.isoformat()},
        "range_label": format_range_label(range_from, range_to),
        "profit": agg["income"] - expense,
        "income": agg["income"],
        "expense": expense,
        "discount_total": agg["discount_total"],
        "admissions": agg["admissions"],
        "renewals": agg["renewals"],
        "due_paid": agg["due_paid"],
        "pt": agg["pt"],
        "service": agg["service"],
        "product": agg["product"],
        "online": agg["online"],
        "cash": agg["cash"],
        "recent_transactions": _enrich_transactions(client, tenant_id, recent_raw),
    }


@router.get("/finance/income")
def get_income_transactions(
    period: str = "this_month",
    from_: str | None = Query(default=None, alias="from"),
    to: str | None = Query(default=None),
    page: int = 1,
    page_size: int = DEFAULT_PAGE_SIZE,
    staff=Depends(get_current_staff),
):
    """Paginated, period-scoped income transactions — the Income tab.
    Deliberately a separate endpoint from /summary's fixed recent_transactions
    (unrelated to the selected period, kept for the home dashboard)."""
    require_owner(staff)
    client = get_admin_client()
    tenant_id = staff["tenant_id"]
    page = max(1, page)
    page_size = min(max(1, page_size), MAX_PAGE_SIZE)
    offset = (page - 1) * page_size

    range_from, range_to = _resolve_range(period, from_, to)
    start_utc, end_utc = ist_day_bounds_to_utc(range_from, range_to)

    result = (
        client.table("payment")
        .select("*", count="exact")
        .eq("tenant_id", tenant_id)
        .eq("status", "completed")
        .gte("created_at", start_utc.isoformat())
        .lte("created_at", end_utc.isoformat())
        .order("created_at", desc=True)
        .range(offset, offset + page_size - 1)
        .execute()
    )

    return {
        "items": _enrich_transactions(client, tenant_id, result.data),
        "total": result.count or 0,
        "page": page,
        "page_size": page_size,
    }
