# Project status

Single source of truth. Update the relevant section in every PR.

**Date:** 2026-11-07 (MVP due Nov 18)
**Branch:** `andi/m0-m1-backend` (draft PR into `dev`, not merged)
**Current milestone:** M1 built and checked, waiting for Lameda12 (Alamedin)'s review. M2 (WS1, WS2) and M3 (WS3, WS4) not started.

## Done

| Milestone | What | Commit |
|---|---|---|
| M0 | Skeleton, all GET endpoints on Postgres, UI served by the API, seeded demo case | `e26e881` |
| M0 review | Random hashed intake tokens, configurable DB port, Makefile | `6fa3af5` |
| M1 | Argon2 login + server-side sessions, review/gap/form mutations, package build with versions and sha256, tenant submit (attestation only), Electron shell | `b1212b4` |
| M1 hardening | Seed only when DB is empty (`make reset`), 422 for sourceless accepts, Redis in CI, test audit, concurrent-build test | `9d56e2f` |
| M1 follow-up | Electron 33 to 45.2.3 (`npm audit` clean, Node 22.12+, no install-script pin needed); Claude Code workflow and `scoper`/`implementer`/`reviewer`/`shipper` subagents; local-environment rules in AGENTS.md | PR #1 |
| M1 test fixes | From NineJZ356's Windows run: the seed reads `seed_data.json` as UTF-8 (tests and `make seed` failed on Windows code pages); tests ignore `backend/.env`, so the quickstart's `COOKIE_SECURE=false` no longer fails the Secure-cookie test | PR #1 |

Details of every deviation from `API_CONTRACT.md`: `CONTRACT_CHANGES.md` (#1 to #22).

## In progress

Nothing on `dev`. Workstreams WS1 to WS5 (table below) are unassigned.

## Known issues

- **No production guard.** The app starts with dev defaults (`SEED_PASSWORD`, compose passwords, `COOKIE_SECURE=false` in compose). It must refuse to start when `ENV=production` and `SEED_PASSWORD` or `SECRET_KEY` is unset or a dev default. Neither `ENV` nor `SECRET_KEY` exists in `config.py` yet. Tracked in WS2's "Done when".
- **Blob storage is a local volume** (`STORAGE_DIR`). Several API replicas need shared storage (WS2).
- **Rate limits behind a proxy** key on the socket IP; needs `--proxy-headers` and trusted proxy config (WS2).
- **Expired sessions are never purged** (WS2).
- **Font size:** the bundled Noto Sans SC adds about 10 MB to the repo and image.
- **`docker compose up --scale api=2` does not work yet:** the api service publishes fixed host port 8000. WS2 needs a proxy service.
- **Zip contains no evidence files yet** (only two PDFs and `manifest.json`); evidence joins in WS1.
- **Verified by an agent on 2026-11-06 (Playwright + rendered pages, see the PR #1 comments):** Chinese glyphs render in the built PDF, second-org isolation in two separate browser contexts, `?mock=1`, the empty-caseload state. **Electron 45 window (2026-11-06, Windows, against `web/index.html?mock=1` over the DevTools protocol):** the mock UI renders, the renderer has no Node, `window.open` is denied, off-origin navigation is blocked. **Electron 45 window against the real API (2026-11-07, Windows 11, NineJZ356, PR #1):** `npm install`, `node check.js` and `npm start` work, login works in the window, the renderer has no Node, `window.open` is denied. **Mac: pending Lameda12's check by eye** (`make desktop` starts the window; install and `check.js` pass).
- **Throughput work is deferred:** `WEB_CONCURRENCY` and gzip belong to WS2; the load re-benchmark (`backend/bench/load.py`, p50/p95/p99 on the compose stack) to WS5. `GET /api/cases` already runs a fixed number of queries (query-count test).
- **UI routes don't include the case id** (`#timeline`), so a case can't be deep-linked or shared.
- **Seed data has a zh-language tenant but all-English content.** The demo case needs real Chinese tenant messages and evidence text (fictional) so the video shows multilingual intake. Owner: WS5.
- **CI runs on GitHub** with Postgres and Redis service containers; both checks are green on PR #1 (re-checked after each push).
- Rate-limit counters only count requests that pass body validation.
- Two seeded demo logins share one password (`SEED_PASSWORD`, compose default `tenantproof-demo`). Local only.

## Open decisions

- Who owns each workstream (table below).
- Whether `SECRET_KEY` is needed at all: sessions are server-side random tokens, so nothing signs with it today. Either WS2 adds a real use or drops it from the guard.
- Legal sources (WS4): a human must open every URL and confirm section, form name and wording before Nov 16.
- `backend/app/config.py` is now a shared file (settings change via `schema:` PRs); workstreams may add their own dependencies to `backend/pyproject.toml`.
- Whether to keep bundling the 10 MB CJK font or fetch it at build time.

## How to verify

Prerequisites: Docker, `uv`, Node 22.12+ (desktop only).

```bash
cp backend/.env.example backend/.env
make up                      # api + Postgres + Redis, migrates, seeds an empty DB
curl localhost:8000/healthz  # {"status":"ok",...}
make test                    # starts Postgres + Redis, runs pytest (239 tests)
make lint                    # ruff + pyright
cd desktop && node check.js  # Electron security flags
```

Click-through (real API): open http://localhost:8000, sign in as `sam@example-clinic.test` (password `tenantproof-demo`), open Jordan Lee's case, review events, resolve both required items, tick the confirmations on Package, build twice, download v1 and v2. Mock mode: http://localhost:8000/?mock=1.

Reset local data: `make reset` (drops the dev database, migrates, reseeds).

## Workstreams

Prompts: `docs/NEXT_PROMPTS.md`.

| Workstream | Owner | Branch | Status | Blocked by |
|---|---|---|---|---|
| WS1 Evidence ingest + tenant uploads (M2) | opoeci6 | `opoeci6/m2-evidence-ingest` | in progress: upload routes, type check, metadata, stripped copy, text, evidence in the zip | `schema:` PR (evidence columns, upload settings) |
| WS2 Hosted deploy + infra hardening (M2) | TODO | `<github-username>/m2-deploy` | not started | none (S3 adapter test and QR demo need WS1 for uploads) |
| WS3 Agent runtime (M3) | TODO | `<github-username>/m3-agent-runtime` | not started | none for day 1 (`tools.py` and `llm.py`); full run needs WS1 |
| WS4 Legal sources, rules, gaps agent (M3) | TODO | `<github-username>/m3-legal-gaps` | not started | WS3 day-1 `tools.py` protocol |
| WS5 Evals, security, perf, demo (M3 to M4) | TODO | `<github-username>/m4-evals-security-perf` | not started | starts now; fills in as WS1 to WS4 land |
