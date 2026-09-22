"""Member management — CRUD + soft delete, all tenant-scoped.

Photos: the frontend uploads directly to the existing `member-media` Supabase
Storage bucket (its policies already scope access by tenant_id via the path's
first segment — see supabase/migrations/20260910134957_storage_member_media.sql)
and then PATCHes photo_url here with the resulting storage path. The backend
never touches the file itself.
"""

import re
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from auth import get_admin_client, get_current_staff
from resources import get_member_or_404

router = APIRouter(prefix="/members", tags=["members"])

# PostgREST or() filter syntax uses "," and "()" as structural characters —
# strip them from free-text search input rather than trying to escape them.
_UNSAFE_FILTER_CHARS = re.compile(r"[,()]")


class MemberCreate(BaseModel):
    name: str
    phone: str | None = None
    email: str | None = None
    branch_id: str | None = None


class MemberUpdate(BaseModel):
    name: str | None = None
    phone: str | None = None
    email: str | None = None
    branch_id: str | None = None
    photo_url: str | None = None


@router.post("", status_code=201)
def create_member(body: MemberCreate, staff=Depends(get_current_staff)):
    client = get_admin_client()
    payload = body.model_dump(exclude_none=True)
    payload["tenant_id"] = staff["tenant_id"]
    try:
        result = client.table("member").insert(payload).execute()
    except Exception as exc:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "A member with this phone number already exists"
        ) from exc
    return result.data[0]


@router.get("")
def list_members(q: str | None = None, staff=Depends(get_current_staff)):
    client = get_admin_client()
    query = (
        client.table("member")
        .select("*")
        .eq("tenant_id", staff["tenant_id"])
        .is_("deleted_at", "null")
    )
    if q:
        safe = _UNSAFE_FILTER_CHARS.sub("", q)
        query = query.or_(f"name.ilike.%{safe}%,phone.ilike.%{safe}%")
    return query.order("created_at", desc=True).execute().data


@router.get("/{member_id}")
def get_member(member_id: str, staff=Depends(get_current_staff)):
    return get_member_or_404(get_admin_client(), staff["tenant_id"], member_id)


@router.patch("/{member_id}")
def update_member(member_id: str, body: MemberUpdate, staff=Depends(get_current_staff)):
    client = get_admin_client()
    tenant_id = staff["tenant_id"]
    get_member_or_404(client, tenant_id, member_id)
    payload = body.model_dump(exclude_unset=True)
    if not payload:
        return get_member_or_404(client, tenant_id, member_id)
    try:
        result = (
            client.table("member")
            .update(payload)
            .eq("tenant_id", tenant_id)
            .eq("id", member_id)
            .execute()
        )
    except Exception as exc:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "A member with this phone number already exists"
        ) from exc
    return result.data[0]


@router.delete("/{member_id}", status_code=204)
def delete_member(member_id: str, staff=Depends(get_current_staff)):
    """Soft delete: sets deleted_at rather than removing the row, so
    attendance/subscription/payment history stays intact."""
    client = get_admin_client()
    tenant_id = staff["tenant_id"]
    get_member_or_404(client, tenant_id, member_id)
    client.table("member").update(
        {"deleted_at": datetime.now(timezone.utc).isoformat()}
    ).eq("tenant_id", tenant_id).eq("id", member_id).execute()
