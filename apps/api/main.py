"""Gym OS API — FastAPI entrypoint.

Run locally with:  python -m uvicorn main:app --reload   (see run.sh)
Never run with bare `uvicorn`.
"""

import os

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

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
