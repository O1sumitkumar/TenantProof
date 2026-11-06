# TenantProof: rules for the coding agent

- `API_CONTRACT.md` is the source of truth; schema field names match exactly. Deviations go in `CONTRACT_CHANGES.md` with a reason.
- Keep `USE_MOCK=true` working in the UI; only change config and routing in `web/index.html`. Approved exceptions: a minimal login view (M1) and a `needs_input` answer control (M3), styled like the existing UI. Every UI change is listed in `CONTRACT_CHANGES.md`.
- No hard-coded `CASE_ID` or `INTAKE_TOKEN` in the UI when `USE_MOCK=false`; read them from the URL or the API.
- `priority.py`, `strength.py`, `dates.py`, `narrative.py`, `gating.py`, `verifier.py` are pure and unit-tested. No LLM calls in them.
- Agent tools are read-only or draft-only. No tool sends messages, deletes data or makes network calls beyond the LLM.
- Every mutation calls `activity.log(...)`. Every by-id handler checks org ownership.
- Never send unstripped files to the model. Never expose `caseworker_note` outside the caseworker workspace.
- Tests and CI use `LLM_MODE=fixture` and never hit the network. Tests run against Postgres (compose locally, service container in CI). No SQLite fallback.
- Git: this repo's root is `/Users/amadi/Documents/TenantProof`. Run `git rev-parse --show-toplevel` before git commands if unsure. Never run git commands that touch `/Users/amadi`.
- Python: type hints, `pathlib`, f-strings, no bare `except`, small functions. `ruff`, `pyright`, `pytest` pass before every commit.
- A milestone is not done on green tests alone: run `docker compose up`, click through the UI with `USE_MOCK=false`, report any erroring screen.
- Finish a milestone, commit, summarize what's demoable, then start the next.
