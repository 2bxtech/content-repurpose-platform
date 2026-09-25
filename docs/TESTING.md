# Testing

## Layers

| Layer | Command | Needs | What it covers |
|---|---|---|---|
| Backend unit | `make test` | nothing | Provider manager (failover, cost, production refuses the mock), executor state machine, file validation, auth rules, WebSocket manager, route wiring via `dependency_overrides` |
| Backend integration | `make test-integration` | Docker | The real stack: HTTP API, Postgres, Redis, Celery worker, WebSockets |
| Frontend | `cd frontend && npm test` | nothing | Services, API error mapping, realtime helpers |
| Static | `make lint`, `npx tsc --noEmit` | nothing | Ruff correctness rules, TypeScript |

CI (`.github/workflows/ci.yml`) runs every row on each pull request, plus a gitleaks scan of the full history.

## How integration runs work

`make test-integration` starts the compose stack under its own project name (`content-repurpose-it`) on separate host ports, with relaxed rate limits and the mock AI provider. It waits for health checks, runs the whole pytest suite with `TEST_API_URL` pointing at it, and tears the stack down with its volumes, even if tests fail. Your development stack and its data are never touched.

Without `TEST_API_URL`, integration tests are skipped, and the in-process app is pointed at an unreachable database. A plain `pytest` therefore can't write to whatever happens to be listening on a developer's machine. With `TEST_API_URL` set, an unreachable API is a failure, not a skip.

## Tests worth reading

- `tests/test_pipeline_integration.py`:
  - creates a transformation over HTTP, then waits on a WebSocket for the worker's completion event
  - checks that a second tenant can't read, transform or subscribe to the first tenant's data
  - checks operator-only endpoints and security headers
- `tests/test_celery.py::TestTransformationRunner`: the executor's state machine, including that a late result can't overwrite a row the stuck-job sweeper already failed.
- `tests/test_security_regressions.py`: regression tests for previously fixed auth and tenancy issues.
- `tests/test_ai_provider_production_safety.py`: production refuses to fall back to canned mock output.

## Conventions

- Integration tests take the `api_client` or `authenticated_client` fixture, so they skip cleanly when no stack is configured.
- In-process tests override FastAPI dependencies rather than patching module internals.
- Assertions on async work accept every valid in-flight state. For example, a fast worker can finish before the create response is built.
