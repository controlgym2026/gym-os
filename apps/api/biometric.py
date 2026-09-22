"""ZKTeco ADMS push endpoints (/iclock/*) + attendance ingestion.

PROTOCOL ASSUMPTIONS — NOT VERIFIED AGAINST REAL HARDWARE. Exact paths,
query params, and payload/response formats vary by ZKTeco firmware/model;
this implements the commonly-documented ADMS "push" contract as a reference
shape. See the Phase 2 report for exactly what to check once a terminal is
on-site, and the module-level notes below for where each guess lives.

- GET  /iclock/cdata?SN=<serial>&options=all   — handshake. Response is a
  best-effort plain-text config block (Stamp/OpStamp/Delay/... lines) in the
  general shape ADMS docs describe. Real firmware may require different or
  additional fields — if the device doesn't accept it and keeps re-polling,
  this is the first thing to compare against a packet capture.
- POST /iclock/cdata?SN=<serial>&table=ATTLOG  — attendance push. Body
  assumed tab-delimited lines: PIN\\tDateTime\\tStatus\\tVerifyMode\\tWorkCode,
  DateTime assumed "YYYY-MM-DD HH:MM:SS". See parse_attlog_line() — isolated
  on purpose so a real format mismatch is a one-function fix.
- GET  /iclock/getrequest?SN=<serial>          — command poll. No commands
  are pushed to devices this phase; responds "OK" (no-op).
- POST /iclock/devicecmd?SN=<serial>           — command execution results.
  Logged, acknowledged "OK".

Device timestamps have no timezone offset — assumed to be the device's own
local clock in the branch's configured timezone (branch.timezone), converted
to UTC for storage/dedup. Confirm this against the real device: if it's
already sending UTC, _localize_device_timestamp needs to become a no-op.

SECURITY — deliberately not hardened further this phase, per the spec:
devices identify themselves only by an unauthenticated `SN` query string,
which anyone who can reach these endpoints can spoof. Mitigated only by (a)
rejecting any serial that isn't already a registered device and (b) a
per-serial rate limit (in-memory, per-process — resets on restart and does
not coordinate across multiple server instances; fine for Render's single
instance today, not fine if this ever scales horizontally). Follow-up
hardening not built here: an IP allowlist (works if the branch has a static
IP) or a shared-secret query param the device is configured to send.
"""

import time
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, Query, Request, status
from fastapi.responses import PlainTextResponse

from auth import get_admin_client
from attendance import CheckInDenied, perform_check_in

router = APIRouter(prefix="/iclock", tags=["biometric-adms"])

DEDUP_WINDOW = timedelta(minutes=2)

_RATE_LIMIT_WINDOW_SECONDS = 60.0
_RATE_LIMIT_MAX_REQUESTS = 60
_request_log: dict[str, deque] = defaultdict(deque)


def _check_rate_limit(serial: str) -> bool:
    """In-memory sliding-window limiter, per device serial. See the security
    note in the module docstring for its limits."""
    now = time.monotonic()
    q = _request_log[serial]
    while q and now - q[0] > _RATE_LIMIT_WINDOW_SECONDS:
        q.popleft()
    if len(q) >= _RATE_LIMIT_MAX_REQUESTS:
        return False
    q.append(now)
    return True


# --- ATTLOG parsing (pure, unit-tested directly) -----------------------------


@dataclass
class AttlogRecord:
    pin: str
    timestamp: datetime  # parsed, naive — device-local clock, no offset
    raw_timestamp: str
    raw_line: str


def parse_attlog_line(line: str) -> AttlogRecord | None:
    """One ATTLOG line -> AttlogRecord, or None if it can't be parsed
    (blank line, too few fields, unparseable timestamp). Never raises —
    callers skip what they can't read rather than failing the whole batch.
    """
    line = line.strip("\r\n")
    if not line.strip():
        return None
    fields = line.split("\t")
    if len(fields) < 2:
        return None
    pin = fields[0].strip()
    raw_ts = fields[1].strip()
    if not pin or not raw_ts:
        return None
    try:
        ts = datetime.strptime(raw_ts, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None
    return AttlogRecord(pin=pin, timestamp=ts, raw_timestamp=raw_ts, raw_line=line)


def parse_attlog_body(body: str) -> list[AttlogRecord]:
    return [rec for line in body.splitlines() if (rec := parse_attlog_line(line)) is not None]


def _localize_device_timestamp(naive_ts: datetime, branch_timezone: str) -> datetime:
    try:
        tz = ZoneInfo(branch_timezone)
    except Exception:
        tz = ZoneInfo("UTC")
    return naive_ts.replace(tzinfo=tz).astimezone(timezone.utc)


# --- ingestion (DB-touching; unit-tested against a fake client) -------------


def _find_member_by_pin(client, tenant_id: str, pin: str) -> dict | None:
    result = (
        client.table("member")
        .select("*")
        .eq("tenant_id", tenant_id)
        .eq("biometric_ref", pin)
        .is_("deleted_at", "null")
        .execute()
    )
    rows = result.data or []
    return rows[0] if rows else None


def _is_duplicate_checkin(client, tenant_id: str, member_id: str, device_id: str, ts: datetime) -> bool:
    lo = (ts - DEDUP_WINDOW).isoformat()
    hi = (ts + DEDUP_WINDOW).isoformat()
    result = (
        client.table("attendance")
        .select("id")
        .eq("tenant_id", tenant_id)
        .eq("member_id", member_id)
        .eq("device_id", device_id)
        .gte("checked_in_at", lo)
        .lte("checked_in_at", hi)
        .limit(1)
        .execute()
    )
    return bool(result.data)


def _log_exception(client, tenant_id: str, device_id: str, rec: AttlogRecord, *, member_id: str | None, reason: str) -> None:
    client.table("attendance_unmatched").insert(
        {
            "tenant_id": tenant_id,
            "device_id": device_id,
            "member_id": member_id,
            "raw_pin": rec.pin,
            "raw_timestamp": rec.raw_timestamp,
            "reason": reason,
        }
    ).execute()


def ingest_attlog(client, device: dict, records: list[AttlogRecord]) -> dict:
    """Process one device's parsed ATTLOG push. Never raises for a single
    bad/unmatched/rejected record — logs it and continues, since ZKTeco
    batches multiple lines per push and one bad line shouldn't sink the rest.
    Returns counts for logging.
    """
    tenant_id = device["tenant_id"]
    device_id = device["id"]
    branch_tz = (device.get("branch") or {}).get("timezone") or "UTC"

    stats = {"accepted": 0, "unmatched": 0, "rejected": 0, "duplicate": 0}

    for rec in records:
        ts = _localize_device_timestamp(rec.timestamp, branch_tz)

        member = _find_member_by_pin(client, tenant_id, rec.pin)
        if member is None:
            _log_exception(client, tenant_id, device_id, rec, member_id=None, reason="unmatched_pin")
            stats["unmatched"] += 1
            continue

        if _is_duplicate_checkin(client, tenant_id, member["id"], device_id, ts):
            stats["duplicate"] += 1
            continue

        try:
            perform_check_in(
                client,
                tenant_id,
                member["id"],
                branch_id=device["branch_id"],
                source="biometric",
                checked_in_at=ts,
                device_id=device_id,
            )
            stats["accepted"] += 1
        except CheckInDenied as exc:
            _log_exception(client, tenant_id, device_id, rec, member_id=member["id"], reason=exc.reason)
            stats["rejected"] += 1

    return stats


# --- device authentication shared by all four routes -------------------------


def _touch_last_seen(client, device_id: str) -> None:
    client.table("device").update({"last_seen_at": datetime.now(timezone.utc).isoformat()}).eq(
        "id", device_id
    ).execute()


def _authenticate_device(client, serial: str) -> dict:
    """Resolve the device by serial, touch last_seen_at, and enforce tenant
    suspension — the one funnel every ADMS route goes through. Mirrors
    get_current_staff's 402 block for the dashboard/API on the same
    tenant.billing_status == 'suspended' condition; closes the gap the
    Phase 3 report flagged (ADMS never touched get_current_staff, so a
    suspended tenant's biometric check-ins kept working). last_seen_at is
    still updated even when suspended — that's device connectivity, not
    billing, and staff still benefit from knowing the terminal is online.
    """
    result = (
        client.table("device")
        .select("*, branch(timezone), tenant(billing_status)")
        .eq("serial_number", serial)
        .execute()
    )
    rows = result.data or []
    if not rows:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Unknown device serial")
    device = rows[0]
    _touch_last_seen(client, device["id"])
    if (device.get("tenant") or {}).get("billing_status") == "suspended":
        raise HTTPException(
            status.HTTP_402_PAYMENT_REQUIRED,
            "This gym's Gym OS account is suspended, contact support",
        )
    return device


def _guard(serial: str) -> None:
    if not _check_rate_limit(serial):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Rate limited")


# --- routes ------------------------------------------------------------------


@router.get("/cdata")
def adms_handshake(SN: str = Query(...), options: str | None = None):
    _guard(SN)
    client = get_admin_client()
    _authenticate_device(client, SN)
    body = (
        f"GET OPTION FROM: {SN}\n"
        "Stamp=9999\n"
        "OpStamp=9999\n"
        "ErrorDelay=60\n"
        "Delay=30\n"
        "Realtime=1\n"
        "Encrypt=0\n"
        "TransFlag=1111000000\n"
        "TransInterval=1\n"
    )
    return PlainTextResponse(body)


@router.post("/cdata")
async def adms_push(request: Request, SN: str = Query(...), table: str | None = None):
    _guard(SN)
    client = get_admin_client()
    device = _authenticate_device(client, SN)

    if table != "ATTLOG":
        # Other push tables (OPERLOG, biophoto, ...) aren't handled this
        # phase — ack so the device doesn't retry, do nothing with the body.
        return PlainTextResponse("OK")

    body = (await request.body()).decode("utf-8", errors="replace")
    records = parse_attlog_body(body)
    stats = ingest_attlog(client, device, records)
    print(f"[adms] SN={SN} ATTLOG lines={len(records)} {stats}")
    return PlainTextResponse("OK")


@router.get("/getrequest")
def adms_getrequest(SN: str = Query(...)):
    _guard(SN)
    client = get_admin_client()
    _authenticate_device(client, SN)
    return PlainTextResponse("OK")


@router.post("/devicecmd")
async def adms_devicecmd(request: Request, SN: str = Query(...)):
    _guard(SN)
    client = get_admin_client()
    _authenticate_device(client, SN)
    body = (await request.body()).decode("utf-8", errors="replace")
    print(f"[adms] SN={SN} devicecmd result: {body[:500]!r}")
    return PlainTextResponse("OK")
