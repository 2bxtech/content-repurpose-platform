.DEFAULT_GOAL := help
.PHONY: help env up down logs migrate api worker frontend install test test-integration lint build-frontend clean

PY ?= python
VENV := .venv
BIN := $(if $(filter Windows_NT,$(OS)),$(VENV)/Scripts,$(VENV)/bin)
API_URL ?= http://localhost:8000

help: ## List targets
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-18s %s\n", $$1, $$2}'

env: ## Create .env from .env.example (no-op if it exists)
	@test -f .env || cp .env.example .env

# --- Full stack in Docker -----------------------------------------------------
up: env ## Start postgres, redis, api (auto-migrates), worker, beat
	docker compose up -d --build --wait

down: ## Stop the stack
	docker compose down

logs: ## Tail api + worker logs
	docker compose logs -f api worker

# --- Local processes (infra in Docker, app on the host) ------------------------
install: ## Create venv and install backend + frontend dependencies
	$(PY) -m venv $(VENV)
	$(BIN)/pip install -r backend/requirements-dev.txt
	cd frontend && npm ci

migrate: ## Apply Alembic migrations to the local database
	cd backend && ../$(BIN)/alembic upgrade head

api: ## Run the API with reload on :8000
	cd backend && ../$(BIN)/uvicorn main:app --reload --port 8000

worker: ## Run a Celery worker
	cd backend && ../$(BIN)/celery -A app.core.celery_app worker --loglevel=info

frontend: ## Run the React dev server on :3000
	cd frontend && npm start

build-frontend: ## Type-check and build the frontend
	cd frontend && npx tsc --noEmit && npm run build

# --- Quality -----------------------------------------------------------------
lint: ## Ruff correctness checks
	$(BIN)/ruff check .

test: ## Unit tests (no services needed; integration tests auto-skip)
	$(BIN)/pytest

test-integration: ## Full suite against the compose stack (starts it with relaxed rate limits)
	RATE_LIMIT_AUTH_ATTEMPTS=1000/1m RATE_LIMIT_API_CALLS=5000/1m RATE_LIMIT_TRANSFORMATIONS=1000/1m docker compose up -d --build --wait
	docker compose exec -T redis redis-cli FLUSHDB >/dev/null
	TEST_API_URL=$(API_URL) $(BIN)/pytest

clean: ## Remove caches and build output
	rm -rf .pytest_cache .ruff_cache htmlcov coverage.xml frontend/build
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
