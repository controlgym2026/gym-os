"""Bulk member import from a CSV file (an export from another system).

Expected columns (case-insensitive header, any order): name, phone, email,
plan_name. Only `name` is required. `plan_name`, if given and it matches an
existing *active* plan's name (case-insensitive), also starts a subscription
for that member on that plan — reusing subscriptions.py's start_subscription,
not duplicating that logic.

A bad row never aborts the whole file — it's skipped and reported, same
principle as the ADMS attendance ingestion in biometric.py (one bad line
shouldn't sink the rest of the batch).
"""

import csv
import io
from dataclasses import dataclass

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from auth import get_admin_client, get_current_staff
from subscriptions import DuplicateActiveSubscription, start_subscription

router = APIRouter(tags=["members"])


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
    result = (
        client.table("membership_plan")
        .select("*")
        .eq("tenant_id", tenant_id)
        .eq("is_active", True)
        .execute()
    )
    return {p["name"].strip().lower(): p for p in result.data}


def run_member_import(client, tenant_id: str, rows: list[ImportRow]) -> dict:
    imported = 0
    subscriptions_started = 0
    skipped: list[dict] = []  # no member created
    plan_warnings: list[dict] = []  # member created, but named plan not found

    existing_phones = _existing_member_phones(client, tenant_id)
    plans_by_name = _active_plans_by_name(client, tenant_id)

    for row in rows:
        name = row.name.strip()
        if not name:
            skipped.append({"line": row.line, "reason": "missing name"})
            continue
        if row.phone and row.phone in existing_phones:
            skipped.append({"line": row.line, "reason": "duplicate phone"})
            continue

        payload: dict = {"tenant_id": tenant_id, "name": name}
        if row.phone:
            payload["phone"] = row.phone
        if row.email:
            payload["email"] = row.email

        try:
            member = client.table("member").insert(payload).execute().data[0]
        except Exception:
            skipped.append({"line": row.line, "reason": "could not create member (likely duplicate phone)"})
            continue

        imported += 1
        if row.phone:
            existing_phones.add(row.phone)  # guard duplicate phones within the same file

        if row.plan_name:
            plan = plans_by_name.get(row.plan_name.strip().lower())
            if plan is None:
                plan_warnings.append({"line": row.line, "plan_name": row.plan_name})
            else:
                try:
                    start_subscription(client, tenant_id, member["id"], plan)
                    subscriptions_started += 1
                except DuplicateActiveSubscription:
                    # Can't happen for a just-created member in practice, but
                    # stay safe rather than let an exception abort the import.
                    plan_warnings.append({"line": row.line, "plan_name": row.plan_name})

    return {
        "imported": imported,
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
