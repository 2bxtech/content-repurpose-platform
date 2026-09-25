# Development history

The project was built incrementally over 2025–2026 in a private repository and published here with a fresh history. This is a condensed account of how it got here.

## Build phases (private repository)

1. **Auth foundation:** JWT access/refresh tokens, bcrypt, Redis sessions.
2. **Multi-tenant schema:** workspaces, UUID keys, audit and soft-delete columns, RLS policies, Alembic.
3. **Background processing:** Celery with Redis, task status tracking.
4. **Realtime:** WebSocket endpoint and a Redis pub/sub design for multiple API instances.
5. **Document ingestion:** PDF/DOCX/text extraction with validation, then URL ingestion with SSRF checks.
6. **AI provider layer:** Anthropic and OpenAI behind one interface; failover, rate limits, cost tracking.
7. **Frontend:** React + TypeScript SPA, including quick transform, presets, refine, and export to TXT/MD.
8. **Deployment:** Railway (API + worker) and Vercel, migrations on start with lock/statement timeouts, CORS for preview deployments.
9. **Hardening:** dependency CVE sweep, auth and tenant-isolation fixes, production refuses the mock AI provider.

## Public release pass (this repository)

An audit before publishing compared the README against the code and found features that existed but weren't connected, or weren't safe to connect as written. The work is in the merged pull requests:

- **#1 Tooling.** One Makefile and one compose stack replaced per-OS scripts. Integration tests run in an isolated compose project. Fixed a compose variable mismatch that left Anthropic unconfigured.
- **#2 Wiring and safety:**
  - Transformations moved onto Celery; they had been running inside the HTTP request.
  - The WebSocket router was mounted. Its Redis listener no longer blocks the event loop, and broadcast is pinned to the caller's own workspace.
  - Operator endpoints are gated by user ID.
  - Middleware was put in the right order, and about 3.6k lines of unreachable code were removed.
  - Three rounds of review (Claude and Codex) added: atomic job claims, a stuck-job sweeper, a persistent worker event loop, and token redaction in logs.
- **#6 Tests.** The inherited suite had drifted: 55 failures and 32 errors against a live stack. It now passes (217 integration / 135 unit), and it surfaced a real bug where rejected uploads returned 500 instead of 400.
- **#3 CI.** GitHub Actions for backend, integration, frontend and secret scanning.
- **#4 Frontend realtime.** The detail page updates from WebSocket events instead of 5-second polling.
