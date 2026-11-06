# Works with both `docker compose` (plugin) and the standalone `docker-compose`.
COMPOSE := $(shell docker compose version >/dev/null 2>&1 && echo "docker compose" || echo "docker-compose")
POSTGRES_HOST_PORT ?= 5433
export POSTGRES_HOST_PORT
export DATABASE_URL ?= postgresql+psycopg://tenantproof:tenantproof@localhost:$(POSTGRES_HOST_PORT)/tenantproof
export DEV_STUB_AUTH ?= true

.PHONY: up down test lint seed link

up:        ## Build and start api, postgres, redis
	$(COMPOSE) up -d --build

down:      ## Stop everything (add `-v` via `make down ARGS=-v` to drop the database volume)
	$(COMPOSE) down $(ARGS)

test: db   ## Run the test suite against Postgres
	cd backend && uv run pytest -q

lint:      ## ruff + pyright
	cd backend && uv run ruff check . && uv run pyright

seed: db   ## Reload demo data into the local database and print a fresh demo link
	cd backend && uv run alembic upgrade head && uv run python -m app.seed

link:      ## Mint a new intake link for the demo case (revokes the previous one)
	@curl -s -X POST localhost:8000/api/cases/case_demo_001/intake-link

db:
	$(COMPOSE) up -d postgres
