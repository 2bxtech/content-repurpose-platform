# Architecture

## Components

| Component | Code | Role |
|---|---|---|
| API | `backend/main.py`, `backend/app/api/routes/` | FastAPI app: auth, documents, transformations, presets, workspaces, WebSocket endpoint, operator-only provider API |
| Worker | `backend/app/tasks/` | Celery worker that runs transformations; beat runs the stuck-job sweeper |
| Executor | `backend/app/services/transformation_runner.py` | The one code path that turns a transformation row into a result (used by the worker, `/quick` and `/refine`) |
| Provider manager | `backend/app/services/ai_providers/` | Anthropic/OpenAI/mock behind one interface; priority-ordered failover, per-provider rate limits, cost tracking |
| Realtime | `backend/app/core/websocket_manager.py` | Per-process socket registry plus a Redis pub/sub listener for cross-process fan-out |
| Frontend | `frontend/src/` | React + TypeScript SPA; REST via axios, live updates via one WebSocket per session |

Postgres holds all durable state. Redis is the Celery broker and result backend, and it also stores sessions, refresh-token `jti`s and the token blacklist, holds the rate-limit counters, and carries the WebSocket fan-out channel.

## Request lifecycle: creating a transformation

```mermaid
sequenceDiagram
    participant B as Browser
    participant A as API replica
    participant R as Redis
    participant W as Celery worker
    participant P as Postgres
    participant AI as AI provider

    B->>A: POST /api/transformations (JWT)
    A->>P: check document is in caller's workspace; INSERT status=PENDING
    A->>R: enqueue process_transformation(id, workspace_id)
    A-->>B: 201 {id, status: PENDING, task_id}
    W->>P: UPDATE ... SET PROCESSING WHERE status=PENDING RETURNING id
    W->>R: publish transformation_started
    W->>P: read document text
    W->>AI: generate (manager: failover, timeouts, SDK retries)
    W->>P: UPDATE ... SET COMPLETED, result, tokens, cost WHERE status=PROCESSING
    W->>R: publish transformation_completed
    R-->>A: (every replica) pub/sub message
    A-->>B: WebSocket event to the owner's sockets
    B->>A: GET /api/transformations/{id}
```

### Failure handling

| What goes wrong | What happens |
|---|---|
| Broker unreachable at enqueue | Publishing runs off the event loop with bounded retries; the row is marked `FAILED` ("queue unavailable") and the request returns promptly |
| Same message delivered twice | The claim is a conditional `UPDATE`; the second delivery finds the row no longer `PENDING` and exits. At most one billed AI call per row |
| Provider error or rate limit | The manager fails over to the next enabled provider; if none succeed the row is `FAILED` with the provider error |
| Unexpected exception in the worker | Caught at the task boundary; the row is `FAILED` so clients stop polling |
| Task exceeds the 10 min soft limit | The coroutine is cancelled and drained so it can't resume in the next task; the row is `FAILED` ("timed out") |
| Task hits the 12 min hard limit | The process is killed without writing anything; the sweeper fails the row once it is 30 min old |
| Worker dies / message lost | Beat's sweeper fails `PENDING`/`PROCESSING` rows older than 30 minutes |
| Late result after the sweeper fired | The final write is conditional on `status = PROCESSING`, so it can't flip `FAILED` back to `COMPLETED` |
| Redis down | The broker is down too, so new work is marked `FAILED` at enqueue. Worker progress events are lost; API-originated socket messages are delivered locally; the listener keeps retrying and clients fall back to polling |

### Why the worker keeps one event loop

Celery tasks are synchronous functions. Running each task under a new `asyncio.run()` looks tidy, but the provider manager is a process-wide singleton. Its async SDK clients keep connection pools bound to the loop that created them, so from the second task on they'd be talking to a closed loop. Each worker process therefore runs coroutines on one persistent loop (`tasks/db.py: run_async`). Database connections use `NullPool` and are closed per task, so the session-level RLS setting can't leak between tasks.

## Data model

All tables use UUID primary keys and carry `created_at`/`updated_at`, audit columns (`created_by`, `updated_by`) and soft-delete columns (`deleted_at`, `deleted_by`).

- `workspaces`: tenant boundary; plan limits (documents, transformations).
- `users`: belongs to one workspace; role (`owner`/`admin`/`member`/`viewer`); bcrypt password hash.
- `documents`: title, source (upload/text/URL), `extracted_text`, metadata.
- `transformations`: type, parameters, status, result, error, `task_id`, provider, token counts, cost, processing time.
- `transformation_presets`: reusable parameter sets per workspace, with usage counts.

Schema changes go through Alembic only (`backend/alembic/versions/`). The API never calls `create_all`, so the RLS policies defined in migrations can't be bypassed by an auto-created table.

## Multi-tenancy

1. **Application layer (enforced today).** The workspace is the authenticated user's own, looked up from the token's user ID and never taken from the request body. Every read and write filters on it, and cross-tenant lookups return 404. The WebSocket handshake rejects a `workspace_id` that doesn't match the token.
2. **Database layer (policies in place, enforcement pending).** Every tenant table has an RLS policy on `current_setting('app.workspace_id', true)`. The document routes set it with `set_config(..., true)` (transaction-scoped), and workers set it session-level on a dedicated connection. Setting it in every request handler is part of the enforcement work. Because the app currently connects as the table owner, Postgres doesn't apply the policies. Turning them on needs a non-owner role with `FORCE ROW LEVEL SECURITY`, the context set in every handler, and a bypass role for the paths that legitimately span workspaces (login by email, the stuck-job sweeper).

## Security

- **Auth.** Access token 15 min, refresh token 7 days. Refresh rotates and blacklists the old token, and sessions live in Redis and can be revoked individually or all at once.
- **Operator endpoints.** Global provider config, cost data and socket stats require a user ID listed in `PLATFORM_ADMIN_USER_IDS`. Workspace roles don't grant this, and email addresses aren't used because registration doesn't verify ownership.
- **Rate limits.** Stored in Redis, per client IP, in three classes: auth (`5/15m`), transformation writes (`30/1h`), everything else (`100/1m`). Only honour `X-Forwarded-For` when `TRUST_PROXY_HEADERS=true`.
- **Uploads.** Size limit, an extension allowlist, executable-signature rejection, and content sniffing with libmagic (installed in the image): a file whose bytes don't match its extension, such as a script renamed to `.pdf`, is rejected with 400. (Sniffing is disabled when running the API natively on Windows; see `file_processor.py`.)
- **URL ingestion.** The host is resolved and private, loopback and link-local addresses are rejected; redirects are not followed and timeouts are short. (A DNS answer could still change between check and fetch; pinning the resolved IP for the request would close that gap.)
- **Response headers.** `nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`, a deny-all CSP on JSON responses, and HSTS in production.
- **Logs.** JWTs in WebSocket query strings are redacted from uvicorn logs, and 500 responses don't echo exception text outside debug mode.

## Configuration

Everything comes from environment variables (`backend/app/core/config.py`, documented in `.env.example`). Notable ones:

| Variable | Purpose |
|---|---|
| `DATABASE_URL`, `REDIS_URL` | Hosted connection strings; component variables are used when these are empty |
| `CLAUDE_API_KEY`, `OPENAI_API_KEY` | Enable real providers; with neither set (and not production) the mock provider is used |
| `TRANSFORMATION_EXECUTION` | `celery` (default) or `inline` for a worker-less local setup |
| `PLATFORM_ADMIN_USER_IDS` | Comma-separated user IDs allowed to use operator endpoints |
| `CORS_ORIGINS`, `CORS_ORIGIN_REGEX` | Allowed browser origins (regex for preview deployments) |
| `RATE_LIMIT_*` | Rate-limit budgets |
