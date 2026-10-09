"""Daily Active/Expired/Due Excel digest (emailed) + on-demand member photo
directory (PDF, downloaded from the app). Both reuse members.py's existing
filtered-query and current-subscription-attachment helpers rather than
re-querying the schema a third way.
"""

import os
from concurrent.futures import ThreadPoolExecutor, as_completed

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from auth import get_admin_client, get_current_staff
from email_sender import EmailSendError, send_email_with_attachment
from excel_report import build_members_excel
from members import (
    PHOTO_FILTERS,
    STATUS_FILTERS,
    _attach_current_subscriptions,
    _filtered_members_query,
    member_matches_filter,
)

router = APIRouter(prefix="/reports", tags=["reports"])

# Hardcoded-for-now per the user's own choice (no settings UI yet) — env
# vars rather than literals so recipients/tenant can be changed from
# Render's dashboard without a code deploy, same pattern as
# SUPER_ADMIN_EMAILS/FRONTEND_ORIGIN elsewhere in this codebase.
#
# NOTE: Resend's sandbox mode (no verified domain) only allows sending to
# the Resend account's own signup address — currently just
# controlgym2026@gmail.com. livnexacare@gmail.com will 403 until a domain
# is verified in Resend and the sender address is switched to it (see
# DAILY_REPORT_RECIPIENTS override, currently set on Render to just
# controlgym2026@gmail.com for that reason).
_DEFAULT_RECIPIENTS = "controlgym2026@gmail.com,livnexacare@gmail.com"
_DEFAULT_TENANT_ID = "927a8361-3ec3-4b37-9c26-44b27044e0ab"  # Control Gym


def _daily_report_recipients() -> list[str]:
    raw = os.environ.get("DAILY_REPORT_RECIPIENTS", _DEFAULT_RECIPIENTS)
    return [e.strip() for e in raw.split(",") if e.strip()]


def _daily_report_tenant_id() -> str:
    return os.environ.get("DAILY_REPORT_TENANT_ID", _DEFAULT_TENANT_ID)


def _fetch_all_members_with_subscriptions(client, tenant_id: str, q: str | None = None) -> list[dict]:
    """Every non-deleted member for the tenant, current_subscription
    attached — unpaginated, for the two bulk-export use cases below (a
    report/directory needs everyone, not one page at a time)."""
    members = _filtered_members_query(client, tenant_id, q).execute().data
    return _attach_current_subscriptions(client, tenant_id, members)


_PHOTO_DOWNLOAD_WORKERS = 8


def _download_one_photo(member_id: str, photo_url: str) -> tuple[str, bytes | None]:
    # Each worker thread gets its OWN client via get_admin_client()'s
    # thread-local caching (see auth.py) — never share one client instance
    # across threads, the same concurrency bug fixed earlier in this
    # project (shared httpx connection pool under real parallel load).
    from pdf_directory import _downscale_photo  # deferred: only the PDF route needs Pillow/reportlab

    try:
        raw = get_admin_client().storage.from_("member-media").download(photo_url)
        # Downscale immediately so the (often multi-MB, phone-camera-resolution)
        # original is never held in memory alongside every other member's —
        # holding all originals until PDF build time OOM-crashed Render's
        # free instance on the full, unfiltered directory (335 members, 106
        # real photos): 502 with an empty body ~28s in, not a timeout.
        return member_id, _downscale_photo(raw)
    except Exception:
        return member_id, None  # missing/corrupt object — that member just gets the placeholder


def _download_member_photos(members: list[dict]) -> dict[str, bytes]:
    """member_id -> raw photo bytes, for every member that has one.
    Downloaded in parallel (a Storage download is I/O-bound, not CPU-bound)
    — sequential downloads of even a few dozen photos were slow enough to
    blow past Render's gateway timeout (measured: 16 photos, 70+ seconds,
    502) well before PDF generation itself ever started."""
    to_fetch = [(m["id"], m["photo_url"]) for m in members if m.get("photo_url")]
    photos: dict[str, bytes] = {}
    if not to_fetch:
        return photos
    with ThreadPoolExecutor(max_workers=_PHOTO_DOWNLOAD_WORKERS) as pool:
        futures = [pool.submit(_download_one_photo, mid, url) for mid, url in to_fetch]
        for future in as_completed(futures):
            member_id, data = future.result()
            if data is not None:
                photos[member_id] = data
    return photos


@router.get("/member-directory.pdf")
def member_directory_pdf(
    filter: str | None = Query(default=None),  # noqa: A002 — matches GET /members's own param name
    photo: str | None = Query(default=None),  # matches GET /members's own `photo` param — independent of `filter`, AND'ed
    plan_id: str | None = None,
    staff=Depends(get_current_staff),
):
    from pdf_directory import build_member_directory_pdf  # deferred: reportlab import cost only on actual use

    client = get_admin_client()
    tenant_id = staff["tenant_id"]

    if filter and filter not in STATUS_FILTERS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Unknown filter '{filter}' — expected one of {STATUS_FILTERS}")
    if photo and photo not in PHOTO_FILTERS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Unknown photo filter '{photo}' — expected one of {PHOTO_FILTERS}")

    members = _fetch_all_members_with_subscriptions(client, tenant_id)
    if filter or photo or plan_id:
        members = [
            m
            for m in members
            if member_matches_filter(m.get("current_subscription"), filter, plan_id, photo_url=m.get("photo_url"), photo_filter=photo)
        ]
    members.sort(key=lambda m: m["name"])

    photos = _download_member_photos(members)
    pdf_bytes = build_member_directory_pdf(members, photos)

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="member-directory.pdf"'},
    )


@router.post("/daily-digest")
def send_daily_digest(token: str = Query(...)):
    """Triggered by an external cron hitting this URL once a day (same
    pattern as the existing /health keep-alive cron) — there's no logged-in
    user to authenticate as, so this checks a shared secret instead of
    get_current_staff. See the deploy notes for the DAILY_REPORT_SECRET env
    var this compares against."""
    expected = os.environ.get("DAILY_REPORT_SECRET")
    if not expected or token != expected:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token")

    client = get_admin_client()
    tenant_id = _daily_report_tenant_id()
    members = _fetch_all_members_with_subscriptions(client, tenant_id)
    xlsx_bytes = build_members_excel(members)

    active = sum(1 for m in members if member_matches_filter(m.get("current_subscription"), "active"))
    expired = sum(1 for m in members if member_matches_filter(m.get("current_subscription"), "expired"))
    due = sum(1 for m in members if member_matches_filter(m.get("current_subscription"), "due"))

    recipients = _daily_report_recipients()
    try:
        send_email_with_attachment(
            to=recipients,
            subject="Gym Control — Daily member report",
            html_body=(
                f"<p>Today's member report is attached.</p>"
                f"<ul><li>Active: {active}</li><li>Expired: {expired}</li><li>Due: {due}</li></ul>"
            ),
            attachment_filename="gym-control-daily-report.xlsx",
            attachment_bytes=xlsx_bytes,
        )
    except EmailSendError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"Report built but email failed to send: {exc}") from exc

    return {"sent_to": recipients, "active": active, "expired": expired, "due": due}
