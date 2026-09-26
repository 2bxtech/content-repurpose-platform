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
- **#6 Tests.** The inherited suite had drifted: 55 failures and 32 errors against a live stack. The full suite now passes against a live stack, and the repair surfaced a real bug where rejected uploads returned 500 instead of 400.
- **#3 CI.** GitHub Actions for backend, integration, frontend and secret scanning.
- **#4 Frontend realtime.** The detail page refreshes as soon as the worker's WebSocket event arrives; polling remains as a fallback.
- **#8 UI polish.** Markdown tables render, and result pages have readable titles.
- **#9 Fact-check fixes.** A docs-versus-code review found the mock provider could mask a failing real one, and `.env` settings weren't reaching the containers. Both are fixed.
- **#7 Docs.** This README and the docs in `docs/`.
- **#11–#16 Hardening follow-ups.**
  - Refresh tokens are single-use, even across replicas (atomic consume).
  - Upload content sniffing actually runs: libmagic was missing from the image, and mismatches were only logged.
  - Pre-commit hooks for ruff and gitleaks.
  - Dependency refresh and a trixie base image with 0 critical CVEs.
  - An async rate limiter, removing two blocking Redis calls from every request.
  - Postgres row-level security enforced through an unprivileged app role, checked by a test inside the database.
- **#17–#21 Closing the README's "next" list**, plus a retroactive Codex review of #14–#16:
  - The worker's RLS startup guard now really refuses work (Celery swallows exceptions raised in signal handlers).
  - Per-workspace monthly AI budgets (requests and USD), enforced before work is accepted and again in the worker. Review found a concurrency overrun (fixed with an advisory lock) and that owners could raise their own limits.
  - OpenTelemetry tracing across API, queue and worker. Its first traces exposed a `PING` before every Redis command and `KEYS` on auth paths, replaced by a per-user session index.
  - Email verification, required for AI work in production.
