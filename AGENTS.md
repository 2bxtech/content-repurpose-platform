# Agent guide

Context for AI coding agents (and humans) working in this repo. Keep it short and current.

## Layout
- `backend/`: FastAPI app. Entry point `main.py`; routes in `app/api/routes/`; settings in `app/core/config.py`; Celery app in `app/core/celery_app.py`; tasks in `app/tasks/`.
- `backend/alembic/`: the only way to change the schema. The app never calls `create_all`.
- `frontend/`: React + TypeScript (CRA). API base from `REACT_APP_API_URL`.
- `tests/`: pytest. Integration tests use the `api_client`/`authenticated_client` fixtures and skip without `TEST_API_URL`.
- `docs/ARCHITECTURE.md`: the design and its invariants. Read it before changing the transformation pipeline, tenancy or auth.

## Commands
- `make up` / `make down`: full stack in Docker (mock AI provider when no key is set).
- `make test`: backend unit tests. `make test-integration`: full suite against an isolated, throwaway stack.
- `make lint`; frontend: `cd frontend && npx tsc --noEmit && npm test`.

## Invariants (don't break these)
- **Tenancy:** every query on tenant data filters by the `workspace_id` from the signed token, never from the request body. Cross-tenant access returns 404 (403 for workspace endpoints).
- **Transformations:** status goes `PENDING → PROCESSING → COMPLETED|FAILED`.
  - The worker claims a row with a conditional `UPDATE ... WHERE status = 'PENDING'`.
  - The final write is conditional on `PROCESSING`.
  - Keep both conditions; they are what make redelivery and the stuck-job sweeper safe.
- **Workers run coroutines via `app.tasks.db.run_async`** (one loop per process). Don't use `asyncio.run` in tasks, because the provider SDK clients are bound to that loop.
- **Redis clients get their URL from `settings.get_redis_url()`.** In async code, use `redis.asyncio`; never call the sync client on the event loop.
- **Operator-only endpoints use `require_platform_admin`** (user-ID allowlist). Don't gate on email or workspace role.
- **Errors:** don't echo exception text in API responses outside `DEBUG`. Don't log tokens.

## Conventions
- Match the surrounding code's style. Comments explain *why*, not what.
- Tests assert behaviour through the API or public functions; override FastAPI dependencies rather than patching internals.
- Commits: imperative subject, a body explaining the reason, one logical change per commit.
