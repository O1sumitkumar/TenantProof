# Project status

Single source of truth. Update the relevant section in every PR.

**Date:** 2026-11-06 (MVP due Nov 18)
**Branch:** `andi/m0-m1-backend` (draft PR into `main`, not merged)
**Current milestone:** M1 built and checked, waiting for Andi's review. M2 (WS1, WS2) and M3 (WS3, WS4) not started.

## Done

| Milestone | What | Commit |
|---|---|---|
| M0 | Skeleton, all GET endpoints on Postgres, UI served by the API, seeded demo case | `e26e881` |
| M0 review | Random hashed intake tokens, configurable DB port, Makefile | `6fa3af5` |
| M1 | Argon2 login + server-side sessions, review/gap/form mutations, package build with versions and sha256, tenant submit (attestation only), Electron shell | `b1212b4` |
| M1 hardening | Seed only when DB is empty (`make reset`), 422 for sourceless accepts, Redis in CI, test audit, concurrent-build test | `9d56e2f` |

Details of every deviation from `API_CONTRACT.md`: `CONTRACT_CHANGES.md` (#1 to #22).

## In progress

Nothing on `main`. Workstreams WS1 to WS5 (table below) are unassigned.

## Known issues

- **Non-zh tenants see "undefined".** `web/index.html` shows `r.message_en` for tenants whose language isn't `zh`, but the intake API correctly omits `message_en`. Only the Chinese demo tenant renders correctly. (M0 bug, not fixed.)
- **No production guard.** The app starts with dev defaults (`SEED_PASSWORD`, compose passwords, `COOKIE_SECURE=false` in compose). It must refuse to start when `ENV=production` and `SEED_PASSWORD` or `SECRET_KEY` is unset or a dev default. Neither `ENV` nor `SECRET_KEY` exists in `config.py` yet. Tracked in WS2's "Done when".
- **Blob storage is a local volume** (`STORAGE_DIR`). Several API replicas need shared storage (WS2).
- **Rate limits behind a proxy** key on the socket IP; needs `--proxy-headers` and trusted proxy config (WS2).
- **Expired sessions are never purged** (WS2).
- **Font size:** the bundled Noto Sans SC adds about 10 MB to the repo and image.
- **`docker compose up --scale api=2` does not work yet:** the api service publishes fixed host port 8000. WS2 needs a proxy service.
- **Zip contains no evidence files yet** (only two PDFs and `manifest.json`); evidence joins in WS1.
- **Unverified by a human or by automation:** Chinese text in the built PDFs (checked by text extraction only, never viewed), the Electron window (only `desktop/check.js` has run), `?mock=1` after the M1 UI edits, and second-org isolation in a real browser (covered by tests).
- **CI has not run on GitHub yet.** It runs Postgres and Redis service containers; the first run is on the draft PR.
- Rate-limit counters only count requests that pass body validation.
- Two seeded demo logins share one password (`SEED_PASSWORD`, compose default `tenantproof-demo`). Local only.

## Open decisions

- Who owns each workstream (table below).
- Whether `SECRET_KEY` is needed at all: sessions are server-side random tokens, so nothing signs with it today. Either WS2 adds a real use or drops it from the guard.
- Legal sources (WS4): a human must open every URL and confirm section, form name and wording before Nov 16.
- `backend/app/config.py` is now a shared file (settings change via `schema:` PRs); workstreams may add their own dependencies to `backend/pyproject.toml`.
- Whether to keep bundling the 10 MB CJK font or fetch it at build time.

## How to verify

Prerequisites: Docker, `uv`, Node 20+ (desktop only).

```bash
cp backend/.env.example backend/.env
make up                      # api + Postgres + Redis, migrates, seeds an empty DB
curl localhost:8000/healthz  # {"status":"ok",...}
make test                    # starts Postgres + Redis, runs pytest (237 tests)
make lint                    # ruff + pyright
cd desktop && node check.js  # Electron security flags
```

Click-through (real API): open http://localhost:8000, sign in as `sam@example-clinic.test` (password `tenantproof-demo`), open Jordan Lee's case, review events, resolve both required items, tick the confirmations on Package, build twice, download v1 and v2. Mock mode: http://localhost:8000/?mock=1.

Reset local data: `make reset` (drops the dev database, migrates, reseeds).

## Workstreams

Prompts: `docs/NEXT_PROMPTS.md`.

| Workstream | Owner | Branch | Status | Blocked by |
|---|---|---|---|---|
| WS1 Evidence ingest + tenant uploads (M2) | TODO | `<name>/m2-evidence-ingest` | not started | none |
| WS2 Hosted deploy + infra hardening (M2) | TODO | `<name>/m2-deploy` | not started | none (S3 adapter test and QR demo need WS1 for uploads) |
| WS3 Agent runtime (M3) | TODO | `<name>/m3-agent-runtime` | not started | none for day 1 (`tools.py` and `llm.py`); full run needs WS1 |
| WS4 Legal sources, rules, gaps agent (M3) | TODO | `<name>/m3-legal-gaps` | not started | WS3 day-1 `tools.py` protocol |
| WS5 Evals, security, perf, demo (M3 to M4) | TODO | `<name>/m4-evals-security-perf` | not started | starts now; fills in as WS1 to WS4 land |
