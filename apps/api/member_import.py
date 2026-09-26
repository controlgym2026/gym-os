"""Bulk member import from a CSV file (an export from another system).

Expected columns (case-insensitive header, any order): name, phone, email,
plan_name. Only `name` is required. `plan_name`, if given and it matches an
existing *active* plan's name (case-insensitive), also starts a subscription
for that member on that plan — reusing subscriptions.py's
build_subscription_payload, not duplicating that logic.

A bad row never aborts the whole file — it's skipped/warned about and
reported, same principle as the ADMS attendance ingestion in biometric.py
(one bad line shouldn't sink the rest of the batch).

Batched, not per-row: the first version did member-insert, then (for
plan_name rows) a duplicate-active-subscription check plus a subscription-
insert, ALL as separate round trips FOR EVERY ROW — 2-3 sequential round
trips per row, which is what made a real 300+-row import take well over a
minute (observed timing out client-side, though it did eventually finish
server-side). Every per-row decision that doesn't need to see the result of
a previous row's DB write now happens in Python first; the only DB calls are
two lookups up front and one or two batched INSERTs at the end.
"""

import csv
import io
from dataclasses import dataclass

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from auth import get_admin_client, get_current_staff
from subscriptions import build_subscription_payload

router = APIRouter(tags=["members"])

CHUNK_SIZE = 200  # keeps each INSERT request modest regardless of file size

_AMBIGUOUS = object()  # sentinel: >1 active plan shares this name


class MemberImportRequest(BaseModel):
    csv: str


# --- CSV parsing (pure, unit-tested directly) --------------------------------


@dataclass
class ImportRow:
    line: int  # 1-indexed within the data rows (header excluded), for reporting
    name: str
    phone: str | None
    email: str | None
    plan_name: str | None


def parse_member_import_csv(text: str) -> list[ImportRow]:
    raw_rows = list(csv.reader(io.StringIO(text)))
    if not raw_rows:
        return []

    header = [h.strip().lower() for h in raw_rows[0]]
    col_index = {name: i for i, name in enumerate(header)}

    def cell(row: list[str], col: str) -> str | None:
        idx = col_index.get(col)
        if idx is None or idx >= len(row):
            return None
        value = row[idx].strip()
        return value or None

    rows: list[ImportRow] = []
    for i, row in enumerate(raw_rows[1:], start=1):
        if not any(c.strip() for c in row):
            continue  # blank line
        rows.append(
            ImportRow(
                line=i,
                name=cell(row, "name") or "",
                phone=cell(row, "phone"),
                email=cell(row, "email"),
                plan_name=cell(row, "plan_name"),
            )
        )
    return rows


# --- DB-touching import logic -------------------------------------------------


def _existing_member_phones(client, tenant_id: str) -> set[str]:
    result = (
        client.table("member")
        .select("phone")
        .eq("tenant_id", tenant_id)
        .is_("deleted_at", "null")
        .execute()
    )
    return {r["phone"] for r in result.data if r.get("phone")}


def _active_plans_by_name(client, tenant_id: str) -> dict[str, dict]:
    """Lowercased plan name -> plan row, or _AMBIGUOUS if more than one
    active plan shares that name. Silently picking one in that case would
    risk mapping a CSV row to the wrong plan with no way to tell — surfaced
    as a plan_warnings entry instead, same as a name that matches nothing."""
    result = (
        client.table("membership_plan")
        .select("*")
        .eq("tenant_id", tenant_id)
        .eq("is_active", True)
        .execute()
    )
    by_name: dict[str, dict] = {}
    for p in result.data:
        key = p["name"].strip().lower()
        by_name[key] = _AMBIGUOUS if key in by_name else p
    return by_name


def _batch_insert(client, table: str, payloads: list[dict]) -> list[dict]:
    """Insert `payloads` in chunks of CHUNK_SIZE. Postgres preserves input
    order for a multi-row INSERT ... VALUES (...), (...) ... RETURNING *, so
    the returned rows line up 1:1 with `payloads` — relied on below to pair
    each inserted member back to the CSV row that created it."""
    inserted: list[dict] = []
    for i in range(0, len(payloads), CHUNK_SIZE):
        chunk = payloads[i : i + CHUNK_SIZE]
        inserted.extend(client.table(table).insert(chunk).execute().data)
    return inserted


def run_member_import(client, tenant_id: str, rows: list[ImportRow]) -> dict:
    skipped: list[dict] = []  # no member created
    plan_warnings: list[dict] = []  # member created, but no subscription started

    existing_phones = _existing_member_phones(client, tenant_id)
    plans_by_name = _active_plans_by_name(client, tenant_id)

    # Pass 1 (pure, no DB): validate + dedupe every row in Python, building
    # the final list of member-insert payloads.
    to_insert: list[dict] = []
    rows_to_insert: list[ImportRow] = []
    seen_phones_this_file: set[str] = set()

    for row in rows:
        name = row.name.strip()
        if not name:
            skipped.append({"line": row.line, "reason": "missing name"})
            continue
        if row.phone and (row.phone in existing_phones or row.phone in seen_phones_this_file):
            skipped.append({"line": row.line, "reason": "duplicate phone"})
            continue

        payload: dict = {"tenant_id": tenant_id, "name": name}
        if row.phone:
            payload["phone"] = row.phone
            seen_phones_this_file.add(row.phone)
        if row.email:
            payload["email"] = row.email

        to_insert.append(payload)
        rows_to_insert.append(row)

    if not to_insert:
        return {"imported": 0, "subscriptions_started": 0, "skipped": skipped, "plan_warnings": plan_warnings}

    # Pass 2: batch-create every valid member.
    try:
        inserted_members = _batch_insert(client, "member", to_insert)
    except Exception:
        # Rare — e.g. a phone collided with one inserted concurrently, after
        # our pre-check above but before this call landed. Report the whole
        # batch as skipped rather than losing rows or 500ing.
        for row in rows_to_insert:
            skipped.append({"line": row.line, "reason": "could not create member (concurrent duplicate?)"})
        return {"imported": 0, "subscriptions_started": 0, "skipped": skipped, "plan_warnings": plan_warnings}

    # Pass 3: batch-create every subscription for rows with a matched
    # plan_name. No duplicate-active-subscription check needed here — every
    # member in this list was just created in pass 2, so none of them can
    # already have one (that's exactly the check start_subscription() does
    # for the single-subscription HTTP path, which doesn't apply here).
    sub_payloads = []
    for member, row in zip(inserted_members, rows_to_insert):
        if not row.plan_name:
            continue
        plan = plans_by_name.get(row.plan_name.strip().lower())
        if plan is None:
            plan_warnings.append({"line": row.line, "plan_name": row.plan_name, "reason": "not found"})
        elif plan is _AMBIGUOUS:
            plan_warnings.append(
                {"line": row.line, "plan_name": row.plan_name, "reason": "multiple active plans share this name"}
            )
        else:
            sub_payloads.append(build_subscription_payload(tenant_id, member["id"], plan))

    subscriptions_started = 0
    if sub_payloads:
        try:
            _batch_insert(client, "subscription", sub_payloads)
            subscriptions_started = len(sub_payloads)
        except Exception:
            plan_warnings.append(
                {
                    "line": 0,
                    "plan_name": f"({len(sub_payloads)} subscription(s))",
                    "reason": "batch insert failed — members were still imported",
                }
            )

    return {
        "imported": len(inserted_members),
        "subscriptions_started": subscriptions_started,
        "skipped": skipped,
        "plan_warnings": plan_warnings,
    }


# --- route ---------------------------------------------------------------------


@router.post("/members/import")
def import_members(body: MemberImportRequest, staff=Depends(get_current_staff)):
    client = get_admin_client()
    rows = parse_member_import_csv(body.csv)
    return run_member_import(client, staff["tenant_id"], rows)
