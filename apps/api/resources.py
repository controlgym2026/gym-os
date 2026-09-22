"""Shared tenant-scoped "fetch or 404" lookups, reused across the members /
membership-plans / subscriptions / attendance / payments routers so each
doesn't redefine its own copy.

Every lookup here filters by `tenant_id` explicitly — these run on the
service-role client (RLS-bypassing), so this filter *is* the tenant
isolation for backend-issued queries, same convention as auth.py's
get_staff_row.
"""

from fastapi import HTTPException, status


def get_member_or_404(client, tenant_id: str, member_id: str) -> dict:
    result = (
        client.table("member")
        .select("*")
        .eq("tenant_id", tenant_id)
        .eq("id", member_id)
        .is_("deleted_at", "null")
        .execute()
    )
    rows = result.data or []
    if not rows:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Member not found")
    return rows[0]


def get_plan_or_404(client, tenant_id: str, plan_id: str) -> dict:
    result = (
        client.table("membership_plan")
        .select("*")
        .eq("tenant_id", tenant_id)
        .eq("id", plan_id)
        .execute()
    )
    rows = result.data or []
    if not rows:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Plan not found")
    return rows[0]


def get_subscription_or_404(client, tenant_id: str, subscription_id: str) -> dict:
    result = (
        client.table("subscription")
        .select("*")
        .eq("tenant_id", tenant_id)
        .eq("id", subscription_id)
        .execute()
    )
    rows = result.data or []
    if not rows:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Subscription not found")
    return rows[0]
