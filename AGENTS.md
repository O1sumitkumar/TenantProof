# TenantProof: instructions for coding agents

Read by Claude Code (via `CLAUDE.md`) and Codex. Humans: the same rules apply to you.

## Start here

Read, in this order: `docs/STATUS.md`, `docs/NEXT_PROMPTS.md`, `API_CONTRACT.md`, `BUILD_PLAN.md`, `CONTRACT_CHANGES.md`.
Paste "Prompt 0" from `docs/NEXT_PROMPTS.md` at the start of every session, then use the prompt for your workstream.

- **Branches:** `<github-username>/<milestone>-<topic>`, for example `octocat/m2-evidence-ingest`.
- **PRs:** open **draft** PRs into `main`. Never push to `main`. Never force-push a shared branch. Never rewrite history that is on the remote.
- **Shared files** (`backend/app/schemas.py`, `backend/app/models.py`, `backend/app/config.py`, `backend/alembic/`, `API_CONTRACT.md`, `CONTRACT_CHANGES.md`, `.github/`) change only through a small `schema:` PR that touches only those files (a new setting in `config.py` comes with its line in `backend/.env.example`). This prevents Alembic "multiple heads" and contract drift.
- Files several workstreams touch (`web/index.html`, `docker-compose.yml`): add your own clearly delimited block and keep the edit minimal. Add your dependencies explicitly to `backend/pyproject.toml`; on a `uv.lock` conflict rebase and run `uv lock`, never hand-edit it.
- Stay inside your workstream's allowed paths (see your prompt). Update your row in `docs/STATUS.md` in every PR.
- Before every PR: `make lint` and `make test` are green.

## Rules

- `API_CONTRACT.md` is the source of truth; schema field names match exactly. Deviations go in `CONTRACT_CHANGES.md` with a reason.
- Keep `USE_MOCK=true` working in the UI (`web/index.html?mock=1`); only change config and routing in `web/index.html`. Approved exceptions: a minimal login view (M1, done) and a `needs_input` answer control (M3), styled like the existing UI. Every UI change is listed in `CONTRACT_CHANGES.md`.
- No hard-coded `CASE_ID` or `INTAKE_TOKEN` in the UI when `USE_MOCK=false`; read them from the URL or the API.
- `priority.py`, `strength.py`, `dates.py`, `narrative.py`, `gating.py`, `verifier.py` are pure and unit-tested. No LLM calls in them.
- Agent tools are read-only or draft-only. No tool sends messages, deletes data or makes network calls beyond the LLM.
- Every mutation calls `activity.log(...)`. Every by-id handler checks org ownership.
- Never send unstripped files to the model. Never expose `caseworker_note` outside the caseworker workspace.
- Tests and CI use `LLM_MODE=fixture` and never hit the network. Tests run against Postgres and Redis (compose locally, service containers in CI). No SQLite fallback, no in-memory rate-limit fallback.
- Never commit secrets, `.env` files (except `.env.example`), real credentials or real personal data. All demo data is synthetic.
- Git: run `git rev-parse --show-toplevel` before git commands if unsure. Never run git commands outside this repository.
- Python: type hints, `pathlib`, f-strings, no bare `except`, small functions. `ruff`, `pyright` and `pytest` pass before every commit.
- A milestone is not done on green tests alone: run `docker compose up` (or `make up`), click through the UI with `USE_MOCK=false`, and report any erroring screen.
- Finish a milestone, commit, summarize what's demoable, then start the next.

## Claude Code subagents

`.claude/agents/` has `scaffolder` (boilerplate from an exact spec), `test-writer` (tests under `backend/tests/`) and `checker` (runs ruff, pyright, pytest). Review every subagent diff yourself. Codex users can ignore this section.
