"""Outbound email via Resend's REST API — the API key has been sitting in
config since Phase 5 ("config wiring only", per that phase's explicit
scope) with nothing actually using it until now. Plain httpx POST rather
than the `resend` SDK — one more dependency for a single API call isn't
worth it.
"""

import base64
import os

import httpx

RESEND_API_URL = "https://api.resend.com/emails"

# Resend's own sandbox sender — works without verifying a custom domain,
# but in that unverified state Resend only delivers to the account owner's
# own verified address. If recipients outside that fail, the fix is
# verifying a sending domain in the Resend dashboard, not a code change.
DEFAULT_FROM = "Gym Control <onboarding@resend.dev>"


class EmailSendError(Exception):
    """Raised with Resend's own error body on a non-2xx response, so the
    caller sees exactly why (e.g. an unverified domain/recipient) instead
    of a bare status code."""


def send_email_with_attachment(
    *,
    to: list[str],
    subject: str,
    html_body: str,
    attachment_filename: str,
    attachment_bytes: bytes,
    from_address: str = DEFAULT_FROM,
) -> dict:
    api_key = os.environ.get("RESEND_API_KEY")
    if not api_key:
        raise EmailSendError("RESEND_API_KEY is not set")

    payload = {
        "from": from_address,
        "to": to,
        "subject": subject,
        "html": html_body,
        "attachments": [
            {
                "filename": attachment_filename,
                "content": base64.b64encode(attachment_bytes).decode("ascii"),
            }
        ],
    }
    r = httpx.post(
        RESEND_API_URL,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json=payload,
        timeout=30.0,
    )
    if r.status_code >= 400:
        raise EmailSendError(f"Resend {r.status_code}: {r.text}")
    return r.json()
