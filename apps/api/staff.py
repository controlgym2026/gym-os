"""Staff management — owner-only. Lets the gym owner create additional
staff logins (manager/trainer/front_desk) under their own tenant.

The owner account itself is created once, at signup, via
POST /auth/bootstrap-tenant (main.py) — this module is for every staff
login after that. There's no invite-link flow: the owner picks the email
and a password directly and hands those credentials to the staff member,
same "dummy credentials" pattern used for the other test logins in this
project so far.

A staff row has no email column of its own (see the init migration) —
email lives on auth.users, looked up via the service-role admin API.
list_staff does one admin.get_user_by_id call per row; fine at gym-staff
scale (a handful of rows), unlike the N+1 avoidance members.py needs for
hundreds of members.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr

from auth import get_admin_client, get_current_staff, require_owner

router = APIRouter(prefix="/staff", tags=["staff"])

# Roles creatable through this endpoint. 'owner' is deliberately excluded —
# assigned exactly once, at signup, via bootstrap-tenant.
CREATABLE_ROLES = ("manager", "trainer", "front_desk")

MIN_PASSWORD_LENGTH = 8


class StaffCreate(BaseModel):
    email: EmailStr
    password: str
    role: str  # one of CREATABLE_ROLES


@router.post("", status_code=201)
def create_staff(body: StaffCreate, staff=Depends(get_current_staff)):
    require_owner(staff)
    if body.role not in CREATABLE_ROLES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"role must be one of {CREATABLE_ROLES}")
    if len(body.password) < MIN_PASSWORD_LENGTH:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, f"password must be at least {MIN_PASSWORD_LENGTH} characters"
        )

    client = get_admin_client()
    tenant_id = staff["tenant_id"]

    try:
        created = client.auth.admin.create_user(
            {
                "email": body.email,
                "password": body.password,
                # No invite-link email — the owner hands these credentials
                # over directly, so the account must be usable immediately.
                "email_confirm": True,
            }
        )
    except Exception as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, "A user with this email already exists") from exc

    user_id = created.user.id
    try:
        row = client.table("staff").insert({"id": user_id, "tenant_id": tenant_id, "role": body.role}).execute()
    except Exception:
        # Don't leave an orphaned auth user with no staff row — that would
        # read as "hasn't bootstrapped a tenant yet" forever (see
        # get_current_staff), a confusing dead end for a login the owner
        # just handed out.
        client.auth.admin.delete_user(user_id)
        raise
    return {**row.data[0], "email": body.email}


@router.get("")
def list_staff(staff=Depends(get_current_staff)):
    require_owner(staff)
    client = get_admin_client()
    tenant_id = staff["tenant_id"]

    rows = (
        client.table("staff")
        .select("*")
        .eq("tenant_id", tenant_id)
        .order("created_at", desc=True)
        .execute()
        .data
    )

    out = []
    for row in rows:
        email = None
        try:
            email = client.auth.admin.get_user_by_id(row["id"]).user.email
        except Exception:
            pass  # an unreachable/deleted auth user shouldn't break the whole list
        out.append({**row, "email": email})
    return out
