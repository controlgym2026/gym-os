"""Membership plans — no hard delete; is_active is the toggle instead."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from auth import get_admin_client, get_current_staff
from resources import get_plan_or_404

router = APIRouter(prefix="/membership-plans", tags=["membership-plans"])


class PlanCreate(BaseModel):
    name: str
    duration_days: int
    price: float
    session_limit: int | None = None  # null = date-based plan; set = session-based PT pack


class PlanUpdate(BaseModel):
    name: str | None = None
    duration_days: int | None = None
    price: float | None = None
    session_limit: int | None = None
    is_active: bool | None = None


@router.post("", status_code=201)
def create_plan(body: PlanCreate, staff=Depends(get_current_staff)):
    client = get_admin_client()
    payload = body.model_dump()
    payload["tenant_id"] = staff["tenant_id"]
    result = client.table("membership_plan").insert(payload).execute()
    return result.data[0]


@router.get("")
def list_plans(include_inactive: bool = False, staff=Depends(get_current_staff)):
    client = get_admin_client()
    query = client.table("membership_plan").select("*").eq("tenant_id", staff["tenant_id"])
    if not include_inactive:
        query = query.eq("is_active", True)
    return query.order("created_at", desc=True).execute().data


@router.get("/{plan_id}")
def get_plan(plan_id: str, staff=Depends(get_current_staff)):
    return get_plan_or_404(get_admin_client(), staff["tenant_id"], plan_id)


@router.patch("/{plan_id}")
def update_plan(plan_id: str, body: PlanUpdate, staff=Depends(get_current_staff)):
    client = get_admin_client()
    tenant_id = staff["tenant_id"]
    get_plan_or_404(client, tenant_id, plan_id)
    payload = body.model_dump(exclude_unset=True)
    if not payload:
        return get_plan_or_404(client, tenant_id, plan_id)
    result = (
        client.table("membership_plan")
        .update(payload)
        .eq("tenant_id", tenant_id)
        .eq("id", plan_id)
        .execute()
    )
    return result.data[0]
