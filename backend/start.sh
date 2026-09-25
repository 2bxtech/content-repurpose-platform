#!/usr/bin/env sh
# Railway/production start script.
#
# Why a script instead of "alembic upgrade head && uvicorn ..." inline:
#   - A migration that blocks on a lock (common when a previous deploy's
#     container still holds connections during Railway's zero-downtime swap)
#     would hang silently past the healthcheck window, so uvicorn never starts
#     and the only symptom is "service unavailable". lock_timeout/statement_timeout
#     turn that silent hang into a fast, visible error.
#   - The echo markers make it obvious in the deploy logs whether we failed
#     during migrations or after, in the app itself.
set -e

echo "[start] $(date -u) Running database migrations (lock_timeout=15s, statement_timeout=120s)..."
PGOPTIONS='-c lock_timeout=15000 -c statement_timeout=120000' alembic upgrade head
echo "[start] $(date -u) Migrations complete."

echo "[start] $(date -u) Starting uvicorn on port ${PORT:-8000}..."
exec uvicorn main:app --host 0.0.0.0 --port "${PORT:-8000}"
