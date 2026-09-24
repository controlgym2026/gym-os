"""Home dashboard + finance report — reporting only, over data the other
modules already collect (member/membership_plan/subscription/payment).

Judgment calls, flagged as asked:
- "income"/"profit" and every bucket (admissions/renewals/due_paid/online/
  cash/discount_total) only count payments with status == 'completed'. A
  pending/failed/refunded payment isn't real income yet.
- "online" = every payment method except 'cash' (card, upi, other) — the
  method enum has no literal 'online' value, so this is the natural mapping
  for a cash-vs-digital split.
- expense is always 0 — there's no Expense tracking in this schema yet.
  Known gap, not faked.
- recent_transactions is a fixed last-20 list, not filtered by the from/to
  range (per spec) and not paginated — judged sufficient for phase 1 rather
  than adding a second endpoint; revisit if the list ever needs to scroll.
"""

from datetime import date, datetime, time, timezone

from fastapi import APIRouter, Depends, Query

from auth import get_admin_client, get_current_staff

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

RECENT_TRANSACTIONS_LIMIT = 20


def _bucket(payments: list[dict], predicate) -> dict:
    rows = [p for p in payments if predicate(p)]
    return {"count": len(rows), "amount": sum(r["amount"] for r in rows)}


def _enrich_transactions(client, tenant_id: str, payments: list[dict]) -> list[dict]:
    sub_ids = list({p["subscription_id"] for p in payments})
    subs = (
        client.table("subscription").select("id, member_id, plan_id").in_("id", sub_ids).execute().data
        if sub_ids
        else []
    )
    sub_by_id = {s["id"]: s for s in subs}

    member_ids = list({s["member_id"] for s in subs})
    members = client.table("member").select("id, name").in_("id", member_ids).execute().data if member_ids else []
    member_name_by_id = {m["id"]: m["name"] for m in members}

    plan_ids = list({s["plan_id"] for s in subs})
    plans = (
        client.table("membership_plan").select("id, name").in_("id", plan_ids).execute().data if plan_ids else []
    )
    plan_name_by_id = {p["id"]: p["name"] for p in plans}

    out = []
    for p in payments:
        sub = sub_by_id.get(p["subscription_id"], {})
        member_id = sub.get("member_id")
        out.append(
            {
                "id": p["id"],
                "transaction_type": p["transaction_type"],
                "date": p["created_at"],
                "plan_name": plan_name_by_id.get(sub.get("plan_id"), "—"),
                "amount": p["amount"],
                "member_id": member_id,
                "member_name": member_name_by_id.get(member_id, "—"),
                "method": p["method"],
            }
        )
    return out


@router.get("/summary")
def get_summary(
    from_: str | None = Query(default=None, alias="from"),
    to: str | None = Query(default=None),
    staff=Depends(get_current_staff),
):
    client = get_admin_client()
    tenant_id = staff["tenant_id"]

    today = date.today()
    range_from = date.fromisoformat(from_) if from_ else today.replace(day=1)
    range_to = date.fromisoformat(to) if to else today

    start_ts = datetime.combine(range_from, time.min, tzinfo=timezone.utc).isoformat()
    end_ts = datetime.combine(range_to, time.max, tzinfo=timezone.utc).isoformat()

    in_range = (
        client.table("payment")
        .select("*")
        .eq("tenant_id", tenant_id)
        .gte("created_at", start_ts)
        .lte("created_at", end_ts)
        .execute()
        .data
    )
    completed = [p for p in in_range if p["status"] == "completed"]

    income = sum(p["amount"] for p in completed)
    expense = 0  # no expense tracking yet — see module docstring
    discount_total = sum(p["discount_amount"] for p in completed)

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
        "profit": income - expense,
        "income": income,
        "expense": expense,
        "discount_total": discount_total,
        "admissions": _bucket(completed, lambda p: p["transaction_type"] == "admission"),
        "renewals": _bucket(completed, lambda p: p["transaction_type"] == "renewal"),
        "due_paid": _bucket(completed, lambda p: p["transaction_type"] == "due_payment"),
        "online": _bucket(completed, lambda p: p["method"] != "cash"),
        "cash": _bucket(completed, lambda p: p["method"] == "cash"),
        "recent_transactions": _enrich_transactions(client, tenant_id, recent_raw),
    }
