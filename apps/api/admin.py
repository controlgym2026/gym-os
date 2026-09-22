"""Super-admin console — platform-operator routes, entirely separate from
the tenant-scoped app.

Every route here is behind get_current_super_admin (auth.py), never
get_current_staff, and vice versa — a super-admin token doesn't satisfy any
tenant-scoped route's auth, and a tenant staff token doesn't satisfy any of
these. These routes bypass the tenant-suspension check in get_current_staff
entirely (they don't use that dependency at all), so a super-admin can
always reach a suspended tenant to reactivate it.

Kept to operational data by design (spec's privacy note): counts, status,
staff role + email. No member-level PII (biometric_ref, phone, attendance
detail) — if a "drill into a tenant's data for support" capability is ever
needed, that's a separate, more tightly scoped and logged feature, not
this console.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from auth import get_admin_client, get_current_super_admin

router = APIRouter(prefix="/admin", tags=["admin"])

VALID_BILLING_STATUSES = ("active", "trial", "suspended", "cancelled")

_BILLING_ACTION_LABEL = {
    "suspended": "suspended",
    "active": "activated",
    "cancelled": "cancelled",
    "trial": "reverted_to_trial",
}


class TenantUpdateRequest(BaseModel):
    billing_status: str | None = None
    plan_tier: str | None = None
    note: str | None = None


def _member_count(client, tenant_id: str) -> int:
    r = (
        client.table("member")
        .select("id", count="exact")
        .eq("tenant_id", tenant_id)
        .is_("deleted_at", "null")
        .execute()
    )
    return r.count or 0


def _active_subscription_count(client, tenant_id: str) -> int:
    r = (
        client.table("subscription")
        .select("id", count="exact")
        .eq("tenant_id", tenant_id)
        .eq("status", "ACTIVE")
        .execute()
    )
    return r.count or 0


def _device_count(client, tenant_id: str) -> int:
    r = client.table("device").select("id", count="exact").eq("tenant_id", tenant_id).execute()
    return r.count or 0


def _with_usage_counts(client, tenant: dict) -> dict:
    tid = tenant["id"]
    return {
        **tenant,
        "member_count": _member_count(client, tid),
        "active_subscription_count": _active_subscription_count(client, tid),
        "device_count": _device_count(client, tid),
    }


def _staff_email(client, user_id: str) -> str | None:
    try:
        resp = client.auth.admin.get_user_by_id(user_id)
        return resp.user.email if resp and resp.user else None
    except Exception:
        return None


@router.get("/tenants")
def list_tenants(admin=Depends(get_current_super_admin)):
    client = get_admin_client()
    tenants = client.table("tenant").select("*").order("created_at", desc=True).execute().data
    return [_with_usage_counts(client, t) for t in tenants]


@router.get("/tenants/{tenant_id}")
def get_tenant_detail(tenant_id: str, admin=Depends(get_current_super_admin)):
    client = get_admin_client()
    tenant_result = client.table("tenant").select("*").eq("id", tenant_id).execute()
    if not tenant_result.data:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Tenant not found")
    tenant = tenant_result.data[0]

    branches = client.table("branch").select("*").eq("tenant_id", tenant_id).execute().data
    staff_rows = client.table("staff").select("*").eq("tenant_id", tenant_id).execute().data
    # staff has no name/email column (nothing in the app collects a staff
    # name yet) — email, fetched from auth.users via the Admin API, is the
    # only identifying field available; shown in place of "name" per spec.
    staff = [
        {
            "id": s["id"],
            "role": s["role"],
            "branch_id": s["branch_id"],
            "email": _staff_email(client, s["id"]),
        }
        for s in staff_rows
    ]

    audit_log = (
        client.table("tenant_audit_log")
        .select("*")
        .eq("tenant_id", tenant_id)
        .order("created_at", desc=True)
        .limit(50)
        .execute()
        .data
    )

    return {
        **_with_usage_counts(client, tenant),
        "branches": branches,
        "staff": staff,
        "audit_log": audit_log,
    }


@router.patch("/tenants/{tenant_id}")
def update_tenant(tenant_id: str, body: TenantUpdateRequest, admin=Depends(get_current_super_admin)):
    client = get_admin_client()
    existing = client.table("tenant").select("id").eq("id", tenant_id).execute()
    if not existing.data:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Tenant not found")

    updates: dict = {}
    log_actions: list[str] = []

    if body.billing_status is not None:
        if body.billing_status not in VALID_BILLING_STATUSES:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, f"billing_status must be one of {VALID_BILLING_STATUSES}"
            )
        updates["billing_status"] = body.billing_status
        log_actions.append(_BILLING_ACTION_LABEL[body.billing_status])

    if body.plan_tier is not None:
        updates["plan_tier"] = body.plan_tier
        log_actions.append("plan_changed")

    if not updates:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No changes given")

    result = client.table("tenant").update(updates).eq("id", tenant_id).execute()

    # One audit row per distinct action, all sharing the same note — a
    # single PATCH changing both billing_status and plan_tier is two
    # things worth a trail, not one blended entry.
    for action in log_actions:
        client.table("tenant_audit_log").insert(
            {
                "tenant_id": tenant_id,
                "action": action,
                "performed_by": admin.email,
                "note": body.note,
            }
        ).execute()

    return _with_usage_counts(client, result.data[0])
