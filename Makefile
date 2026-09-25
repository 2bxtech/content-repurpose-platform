.DEFAULT_GOAL := help
.PHONY: help env up down logs migrate api worker beat frontend install test test-integration lint build-frontend clean

PY ?= python
VENV := .venv
BIN := $(if $(filter Windows_NT,$(OS)),$(VENV)/Scripts,$(VENV)/bin)
# Integration tests get their own compose project so they never touch the dev stack's data.
IT_API_PORT ?= 18000
# AI keys are blanked so the suite always uses the mock provider and never bills a real API.
IT := CLAUDE_API_KEY= OPENAI_API_KEY= POSTGRES_HOST_PORT=15433 REDIS_HOST_PORT=16379 API_HOST_PORT=$(IT_API_PORT) RATE_LIMIT_AUTH_ATTEMPTS=1000/1m RATE_LIMIT_API_CALLS=5000/1m RATE_LIMIT_TRANSFORMATIONS=1000/1m docker compose -p content-repurpose-it

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
	$(BIN)/pre-commit install
	cd frontend && npm ci

migrate: ## Apply Alembic migrations to the local database
	cd backend && ../$(BIN)/alembic upgrade head

api: ## Run the API with reload on :8000
	cd backend && ../$(BIN)/uvicorn main:app --reload --port 8000

worker: ## Run a Celery worker
	cd backend && ../$(BIN)/celery -A app.core.celery_app worker --loglevel=info

beat: ## Run Celery beat (periodic maintenance tasks)
	cd backend && ../$(BIN)/celery -A app.core.celery_app beat --loglevel=info

frontend: ## Run the React dev server on :3000
	cd frontend && npm start

build-frontend: ## Type-check and build the frontend
	cd frontend && npx tsc --noEmit && npm run build

# --- Quality -----------------------------------------------------------------
lint: ## Ruff correctness checks
	$(BIN)/ruff check .

test: ## Unit tests (no services needed; integration tests auto-skip)
	$(BIN)/pytest

test-integration: ## Full suite against a throwaway stack (own project, ports and volumes)
	$(IT) up -d --build --wait
	TEST_API_URL=http://localhost:$(IT_API_PORT) TEST_DATABASE_URL=postgresql://postgres:postgres_dev_password@localhost:15433/content_repurpose \
		$(BIN)/pytest; status=$$?; $(IT) down -v; exit $$status

clean: ## Remove caches and build output
	rm -rf .pytest_cache .ruff_cache htmlcov coverage.xml frontend/build
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
