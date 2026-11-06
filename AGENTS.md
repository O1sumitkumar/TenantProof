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

## Local environment

- **Python:** the backend runs in `backend/.venv`, which uv creates and keeps in sync with `backend/uv.lock` on Python 3.12. Run Python only through `uv run` from `backend/` or the `make` targets. Never `pip install` into the system Python or a hand-made venv, and never run the backend on another Python version.
- **Desktop:** Node 22.12+ (Electron 45). `npm install` in `desktop/` keeps everything in `desktop/node_modules`; Electron downloads its binary on the first `npm start`.
- **Install nothing system-wide:** no `pip install --user`, `npm -g`, `winget`, `choco`, `setx` or global `uv tool install`. If uv is missing, install it inside the repo under `.tools/` (gitignored), with its Python and cache there too:
  ```bash
  python -m venv .tools/uv-venv && .tools/uv-venv/Scripts/pip install uv   # bin/ instead of Scripts/ on macOS and Linux
  export PATH="$PWD/.tools/uv-venv/Scripts:$PATH" UV_PYTHON_INSTALL_DIR="$PWD/.tools/python" UV_CACHE_DIR="$PWD/.cache/uv"
  ```
- **Benchmarks and load tests** use the same stack as compose: Postgres, Redis, uv's Python 3.12. Numbers from MySQL or MariaDB, `memory://` rate limits or another Python are not comparable and don't go in the repo. Never commit connection strings with real hosts or passwords.

## Claude Code subagents

`.claude/agents/` has `scoper` (scopes unfamiliar tasks, read-only), `implementer` (substantial code and test changes), `scaffolder` (boilerplate from an exact spec), `test-writer` (tests under `backend/tests/`), `checker` (runs ruff, pyright, pytest), `reviewer` (independent review of risky changes) and `shipper` (commit, push, draft PR). When to use each, and the review the main session owes every subagent diff, is in `CLAUDE.md`. Codex users can ignore this section.
