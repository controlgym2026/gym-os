#!/usr/bin/env bash
# Start the Gym OS API for local development.
# Always launched via `python -m uvicorn`, never bare `uvicorn`.
set -euo pipefail

cd "$(dirname "$0")"
python -m uvicorn main:app --reload --host 0.0.0.0 --port "${PORT:-8000}"
