"""GET /members/export?format=csv|xlsx — download members data.

Accepts exactly the list endpoint's filters (q, filter, photo, plan_id) so
"export what I'm looking at" returns the same rows as GET /members; with no
filters it exports every member.

* Tenant-scoped via get_current_staff (which also enforces the suspended-
  tenant 402). Owner/manager only — trainer and front_desk get 403.
* Data comes from the members_export() SQL function (one query per 1000-row
  page: latest subscription, last payment and last visit via LATERAL joins —
  no per-member queries). See supabase/migrations/20261118120000_members_export.sql.
* CSV streams page by page. XLSX is written with XlsxWriter's constant_memory
  mode to a temp file (a zip can't be emitted before it's finished), then
  streamed from disk in chunks and deleted. Memory stays flat either way.
* Every export is logged in data_export_log, which is also the rate
  limiter's source of truth (EXPORT_RATE_LIMIT per staff user per hour).

Registered in main.py BEFORE the members router so /members/export is not
captured by GET /members/{member_id}.
"""

import os
import re
import tempfile
from datetime import date, datetime, timedelta, timezone
from typing import Annotated, Iterator

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse

from auth import get_admin_client, get_current_staff
from export_format import IST, CsvChunkWriter, XlsxExportWriter, export_filename
from members import _UNSAFE_FILTER_CHARS, EXPIRING_SOON_DAYS, PHOTO_FILTERS, STATUS_FILTERS

router = APIRouter(prefix="/members", tags=["members"])

EXPORT_ROLES = ("owner", "manager")
EXPORT_FORMATS = ("csv", "xlsx")
EXPORT_RATE_LIMIT = 10  # exports per staff user per rolling hour
EXPORT_RATE_WINDOW = timedelta(hours=1)
PAGE_SIZE = 1000  # = Supabase's default PostgREST max_rows; the loop below copes with a lower cap too
STREAM_CHUNK = 64 * 1024

_UUID = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")

MEDIA_TYPES = {
    "csv": "text/csv; charset=utf-8",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}

STATUS_LABELS = {
    "active": "Active",
    "expiring": f"Expiring (next {EXPIRING_SOON_DAYS} days)",
    "expired": "Expired",
    "due": "Due",
    "paid": "Paid",
}
PHOTO_LABELS = {"has_photo": "Has photo", "no_photo": "No photo"}


# --- pure helpers (unit-tested) ---------------------------------------------


def search_pattern(q: str | None) -> str | None:
    """The ILIKE pattern the list endpoint ends up sending: same stripped
    characters, wrapped in %…%, and PostgREST's `*` wildcard alias -> %."""
    if not q:
        return None
    safe = _UNSAFE_FILTER_CHARS.sub("", q)
    return f"%{safe}%".replace("*", "%")


def require_export_role(staff: dict) -> None:
    if staff.get("role") not in EXPORT_ROLES:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only owners and managers can export member data")


def describe_filters(q: str | None, filter_name: str | None, photo: str | None, plan_name: str | None) -> str:
    parts = []
    if q:
        parts.append(f'Search "{q}"')
    if filter_name:
        parts.append(f"Status: {STATUS_LABELS.get(filter_name, filter_name)}")
    if plan_name:
        parts.append(f"Plan: {plan_name}")
    if photo:
        parts.append(f"Photo: {PHOTO_LABELS.get(photo, photo)}")
    return "; ".join(parts) if parts else "None (all members)"


# --- DB helpers -----------------------------------------------------------------


def _fetch_page(tenant_id: str, today: date, params: dict, offset: int) -> list[dict]:
    # get_admin_client() per call, not captured once: the CSV generator runs
    # on Starlette's threadpool and the client is thread-local (see auth.py).
    return (
        get_admin_client()
        .rpc(
            "members_export",
            {
                "p_tenant_id": tenant_id,
                "p_today": today.isoformat(),
                "p_search": params["search"],
                "p_filter": params["filter"],
                "p_photo": params["photo"],
                "p_plan_id": params["plan_id"],
                "p_expiring_days": EXPIRING_SOON_DAYS,
                "p_limit": PAGE_SIZE,
                "p_offset": offset,
            },
        )
        .execute()
        .data
        or []
    )


def _remaining_pages(tenant_id: str, today: date, params: dict, offset: int, total: int) -> Iterator[list[dict]]:
    while offset < total:
        rows = _fetch_page(tenant_id, today, params, offset)
        if not rows:
            return
        yield rows
        offset += len(rows)


def _check_rate_limit(client, staff_id: str) -> None:
    since = datetime.now(timezone.utc) - EXPORT_RATE_WINDOW
    recent = (
        client.table("data_export_log")
        .select("created_at")
        .eq("staff_id", staff_id)
        .gte("created_at", since.isoformat())
        .order("created_at", desc=False)
        .execute()
        .data
        or []
    )
    if len(recent) >= EXPORT_RATE_LIMIT:
        oldest = datetime.fromisoformat(str(recent[0]["created_at"]).replace("Z", "+00:00"))
        retry_after = max(1, int((oldest + EXPORT_RATE_WINDOW - datetime.now(timezone.utc)).total_seconds()))
        minutes = max(1, round(retry_after / 60))
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            f"Export limit reached ({EXPORT_RATE_LIMIT} per hour). Try again in about {minutes} minute(s).",
            headers={"Retry-After": str(retry_after)},
        )


def _plan_name(client, tenant_id: str, plan_id: str | None) -> str | None:
    if not plan_id:
        return None
    rows = client.table("membership_plan").select("name").eq("tenant_id", tenant_id).eq("id", plan_id).execute().data
    return rows[0]["name"] if rows else "(unknown plan)"


def _gym_name(client, tenant_id: str) -> str:
    rows = client.table("tenant").select("name").eq("id", tenant_id).execute().data
    return (rows[0].get("name") if rows else None) or "Gym"


# --- route ------------------------------------------------------------------------


@router.get("/export")
def export_members(
    export_format: Annotated[str, Query(alias="format")] = "csv",
    q: str | None = None,
    subscription_filter: Annotated[str | None, Query(alias="filter")] = None,
    photo_filter: Annotated[str | None, Query(alias="photo")] = None,
    plan_id: str | None = None,
    staff=Depends(get_current_staff),
):
    require_export_role(staff)
    if export_format not in EXPORT_FORMATS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "format must be csv or xlsx")
    # Same validation (and messages) as GET /members.
    if subscription_filter and subscription_filter not in STATUS_FILTERS:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Unknown filter '{subscription_filter}' — expected one of {', '.join(STATUS_FILTERS)}",
        )
    if photo_filter and photo_filter not in PHOTO_FILTERS:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Unknown photo filter '{photo_filter}' — expected one of {', '.join(PHOTO_FILTERS)}",
        )
    if plan_id and not _UUID.match(plan_id):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "plan_id must be a UUID")

    client = get_admin_client()
    tenant_id = staff["tenant_id"]
    _check_rate_limit(client, staff["id"])

    params = {
        "search": search_pattern(q),
        "filter": subscription_filter or None,
        "photo": photo_filter or None,
        "plan_id": plan_id or None,
    }
    today = date.today()  # same "today" the list's expiry/expiring logic uses
    now_ist = datetime.now(IST)

    first = _fetch_page(tenant_id, today, params, 0)
    total = int(first[0]["total_count"]) if first else 0

    applied = {k: v for k, v in {"q": q, "filter": subscription_filter, "photo": photo_filter, "plan_id": plan_id}.items() if v}
    client.table("data_export_log").insert(
        {
            "tenant_id": tenant_id,
            "staff_id": staff["id"],
            "format": export_format,
            "filters": applied,
            "row_count": total,
        }
    ).execute()

    gym_name = _gym_name(client, tenant_id)
    filename = export_filename(gym_name, export_format, now_ist.date())
    headers = {
        "Content-Disposition": f'attachment; filename="{filename}"',
        "X-Export-Row-Count": str(total),
        "Cache-Control": "no-store",
    }

    if export_format == "csv":

        def csv_stream() -> Iterator[bytes]:
            writer = CsvChunkWriter()
            yield writer.header()
            if first:
                yield writer.rows(first)
            for page in _remaining_pages(tenant_id, today, params, len(first), total):
                yield writer.rows(page)

        return StreamingResponse(csv_stream(), media_type=MEDIA_TYPES["csv"], headers=headers)

    # xlsx — build fully before responding so a failure is a clean 500, not a
    # truncated download.
    fd, path = tempfile.mkstemp(prefix="members_export_", suffix=".xlsx")
    os.close(fd)
    try:
        writer = XlsxExportWriter(path)
        if first:
            writer.add_rows(first)
        for page in _remaining_pages(tenant_id, today, params, len(first), total):
            writer.add_rows(page)
        writer.close(
            [
                ("Gym", gym_name),
                ("Exported at", now_ist.strftime("%d-%m-%Y %H:%M IST")),
                ("Filters applied", describe_filters(q, subscription_filter, photo_filter, _plan_name(client, tenant_id, plan_id))),
                ("Rows", str(writer.row_count)),
            ]
        )
        headers["Content-Length"] = str(os.path.getsize(path))
    except Exception:
        os.unlink(path)
        raise

    def file_stream() -> Iterator[bytes]:
        try:
            with open(path, "rb") as fh:
                while chunk := fh.read(STREAM_CHUNK):
                    yield chunk
        finally:
            os.unlink(path)

    return StreamingResponse(file_stream(), media_type=MEDIA_TYPES["xlsx"], headers=headers)
