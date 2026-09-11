"""Gym OS API — FastAPI entrypoint.

Run locally with:  python -m uvicorn main:app --reload   (see run.sh)
Never run with bare `uvicorn`.
"""

import os

from dotenv import load_dotenv
from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from auth import get_admin_client, get_current_user, get_staff_row

load_dotenv()

app = FastAPI(title="Gym OS API")

# CORS -----------------------------------------------------------------------
# FRONTEND_ORIGIN is a comma-separated list of allowed browser origins.
# The Vercel production URL is wired in during Phase 5; until then this is a
# placeholder plus localhost for local development.
_default_origins = "https://gym-os-web.vercel.app,http://localhost:3000"
_origins = [
    o.strip()
    for o in os.environ.get("FRONTEND_ORIGIN", _default_origins).split(",")
    if o.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Routes -------------------------------------------------------------------------
@app.get("/health")
def health() -> dict[str, str]:
    """Liveness probe. Used by Render's health check and the web app's E2E check."""
    return {"status": "ok"}


# Auth -------------------------------------------------------------------------
# Self-serve signup model: a new Supabase Auth user has no staff row yet, so
# current_tenant_id() (used throughout the DB's RLS policies) resolves to
# NULL for them and they can see nothing. bootstrap-tenant creates their
# tenant + an 'owner' staff row, using the service_role key — RLS blocks a
# fresh user from doing this themselves, on purpose.
class BootstrapTenantRequest(BaseModel):
    gym_name: str


@app.post("/auth/bootstrap-tenant", status_code=201)
def bootstrap_tenant(body: BootstrapTenantRequest, user=Depends(get_current_user)):
    """Create a new tenant + 'owner' staff row for the calling user.

    Idempotent: a user who already has a staff row gets that row back instead
    of a second tenant. Not fully transactional — a failure between the two
    inserts below can leave an orphan tenant with no owner; acceptable for
    now, revisit with a Postgres function if it becomes a real problem.
    """
    client = get_admin_client()

    existing = get_staff_row(user.id)
    if existing is not None:
        return existing

    tenant = client.table("tenant").insert({"name": body.gym_name}).execute()
    tenant_id = tenant.data[0]["id"]

    try:
        staff = (
            client.table("staff")
            .insert({"id": user.id, "tenant_id": tenant_id, "role": "owner"})
            .execute()
        )
        return staff.data[0]
    except Exception:
        # Most likely a race with a concurrent bootstrap call for the same
        # user (staff.id is the auth user id, primary key). Fall back to
        # whatever staff row exists rather than surfacing a 500 for that case.
        existing = get_staff_row(user.id)
        if existing is not None:
            return existing
        raise


@app.get("/auth/me")
def auth_me(user=Depends(get_current_user)) -> dict:
    """Session + bootstrap-status check for the frontend. `staff` is null
    (not an error) when the user hasn't bootstrapped a tenant yet."""
    return {"user_id": user.id, "email": user.email, "staff": get_staff_row(user.id)}
