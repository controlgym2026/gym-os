"""Auth dependencies.

Verifies a Supabase Auth JWT by asking Supabase's Auth server directly
(`auth.get_user`) rather than decoding the token locally — this works
regardless of which signing scheme the project uses (legacy HS256 shared
secret vs. the newer asymmetric keys) and means this codebase never needs a
JWT secret.

Route handlers here are sync `def`s, not `async def`s: supabase-py's client
is a blocking (httpx-sync) client under the hood, and FastAPI runs sync
dependencies/handlers in a threadpool automatically. Making them `async def`
while calling blocking code inside would block the event loop instead.
"""

import os
from functools import lru_cache

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from supabase import Client, create_client

_bearer = HTTPBearer(auto_error=False)


@lru_cache
def get_admin_client() -> Client:
    """Service-role Supabase client. Bypasses RLS — backend-only, never expose
    to the frontend. Lazy + cached so `/health` still works without Supabase
    configured; only auth-dependent routes fail if the env vars are missing.
    """
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set")
    return create_client(url, key)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
):
    """Resolve the Supabase Auth user from `Authorization: Bearer <jwt>`."""
    if credentials is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing bearer token")
    client = get_admin_client()  # misconfiguration (RuntimeError) -> 500, not masked as 401
    try:
        resp = client.auth.get_user(credentials.credentials)
    except Exception:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token")
    if resp is None or resp.user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token")
    return resp.user


def get_staff_row(user_id: str) -> dict | None:
    """The staff row for a Supabase Auth user id, or None if they haven't
    bootstrapped a tenant yet (see POST /auth/bootstrap-tenant in main.py)."""
    result = get_admin_client().table("staff").select("*").eq("id", user_id).execute()
    rows = result.data or []
    return rows[0] if rows else None


def get_current_staff(user=Depends(get_current_user)) -> dict:
    """Require a bootstrapped staff row. Use as a dependency on any
    tenant-scoped route — gives `tenant_id`, `branch_id`, `role`."""
    staff = get_staff_row(user.id)
    if staff is None:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "No staff record for this user — call POST /auth/bootstrap-tenant first",
        )
    return staff
