# TenantProof

TenantProof helps caseworkers at tenant legal clinics turn a tenant's scattered evidence (photos, messages, lease) into a reviewed timeline, a draft of the official application form, and a filing package. The tenant uploads through a private link in their own language; the caseworker reviews every fact and signs off before anything is exported.
It is information, not legal advice, and it never submits anything anywhere. All data in this repo is synthetic.
Built for the Cognizant BrAInstorm Challenge (theme: Agentic AI for Good).

**Status:** M1 done (login, review, package export, tenant attestation). Evidence upload and the agent are next. See [docs/STATUS.md](docs/STATUS.md).

## Quickstart

Prerequisites: Docker (with Compose), [uv](https://docs.astral.sh/uv/), `make`. Node 20+ only for the desktop shell.

```bash
cp backend/.env.example backend/.env   # for local `uv run` commands; compose sets its own env
make up                                # builds and starts api, Postgres, Redis; migrates and seeds an empty DB
```

- App: http://localhost:8000 (API docs: http://localhost:8000/api/docs)
- Health: http://localhost:8000/healthz
- Postgres is on host port 5433 (`POSTGRES_HOST_PORT`), Redis on 6379.

**Log in** (two seeded orgs, one caseworker each; password is `tenantproof-demo` unless you set `SEED_PASSWORD` before `make up`):

| Org | Email | Has data |
|---|---|---|
| Example Community Legal Clinic | `sam@example-clinic.test` | five cases, full demo data on Jordan Lee's |
| Harbourside Tenant Legal Clinic | `jo@harbourside-clinic.test` | none (used to prove org isolation) |

**Mock mode:** open http://localhost:8000/?mock=1 (or the file `web/index.html` directly) to run the UI on built-in data with no backend.

**Tenant link:** the tenant page is `/i/{token}`. The raw link is shown only once, when it is created. Run `make link` to mint a new one for the demo case (it revokes the previous link), or send one from the Tenant view in the app. The first link is also printed in `docker compose logs api` right after the first seed.

**Data:** `make up` seeds only an empty database, so restarts keep your work. `make reset` drops the dev database and reseeds (destroys local data).

**Desktop shell:** `make desktop` runs the Electron wrapper against `APP_URL` (default http://localhost:8000).

## Tests

```bash
make test    # starts Postgres + Redis, creates a throwaway tenantproof_test database, runs pytest
make lint    # ruff + pyright
```

Tests run with `LLM_MODE=fixture`, never touch the network, and need real Postgres and Redis. CI (`.github/workflows/ci.yml`) runs the same against service containers.

## Repo layout

```
API_CONTRACT.md        endpoints and shapes (source of truth)
BUILD_PLAN.md          architecture, agent design, security, schedule
CONTRACT_CHANGES.md    every deviation from the contract, with reasons
SECURITY.md            threat model and controls
AGENTS.md              rules for coding agents and contributors (CLAUDE.md imports it)
docs/                  STATUS.md (start here), NEXT_PROMPTS.md (workstream prompts)
backend/app/           FastAPI app: routers/, services/, models.py, schemas.py, seed.py
backend/alembic/       migrations
backend/tests/         pytest suite
web/index.html         the UI (served by the API; caseworker at /, tenant at /i/{token})
desktop/               Electron shell
reference/             original prototype and contract notes
.claude/agents/        Claude Code subagents (scaffolder, test-writer, checker)
```

## Contributing

Read [AGENTS.md](AGENTS.md) first, then [docs/STATUS.md](docs/STATUS.md) and [docs/NEXT_PROMPTS.md](docs/NEXT_PROMPTS.md). Branches are named `<github-username>/<milestone>-<topic>`. Draft PRs into `main`; never push to `main`.
