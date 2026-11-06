# Works with both `docker compose` (plugin) and the standalone `docker-compose`.
COMPOSE := $(shell docker compose version >/dev/null 2>&1 && echo "docker compose" || echo "docker-compose")
POSTGRES_HOST_PORT ?= 5433
export POSTGRES_HOST_PORT
export DATABASE_URL ?= postgresql+psycopg://tenantproof:tenantproof@localhost:$(POSTGRES_HOST_PORT)/tenantproof
export SEED_PASSWORD ?= tenantproof-demo

.PHONY: up down test lint seed reset link desktop

up:        ## Build and start api, postgres, redis
	$(COMPOSE) up -d --build

down:      ## Stop everything (add `-v` via `make down ARGS=-v` to drop the database volume)
	$(COMPOSE) down $(ARGS)

test: db   ## Run the test suite against Postgres
	cd backend && uv run pytest -q

lint:      ## ruff + pyright
	cd backend && uv run ruff check . && uv run pyright

seed: db   ## Wipe and reload demo data into the local database (prints a fresh demo link)
	cd backend && uv run alembic upgrade head && uv run python -m app.seed --force

reset: db  ## Drop the dev database, migrate from scratch and reseed. Destroys all local data.
	$(COMPOSE) exec -T postgres psql -U tenantproof -d postgres \
		-c "DROP DATABASE IF EXISTS tenantproof WITH (FORCE)" -c "CREATE DATABASE tenantproof"
	cd backend && uv run alembic upgrade head && uv run python -m app.seed --force

link:      ## Mint a new intake link for the demo case (revokes the previous one)
	@curl -s -X POST localhost:8000/api/cases/case_demo_001/intake-link

db:
	$(COMPOSE) up -d postgres

desktop:   ## Run the Electron shell against APP_URL (default http://localhost:8000)
	cd desktop && npm install --no-audit --no-fund && node check.js && npm start
