# Project status

Single source of truth. Update the relevant section in every PR.

**Date:** 2026-11-17 (MVP due Nov 18)
**Branch:** `dev` is the integration branch (`main` only for releases). Start work from `origin/dev`.
**Current milestone:** M1 is merged. M2 is half done: WS1 (evidence ingest and tenant uploads) is merged on `dev`. For WS2 (deploy), the hosted demo was set up by hand and is described in `docs/DEPLOY.md`; opoeci6 has four WS2 items open as PRs #62 to #64 (#56, #58, #59) and the rest of WS2 has no owner. M3 is merged except the worker and the `ingest` step: WS3's runtime, WS4 (corpus, `rules`, `gaps`), the `draft` step, New case, and editing the request to the tenant. Two legal sources still wait for a person to confirm them (#54). The hosted demo (https://test.8596117.xyz) runs `dev` on Haiku.

## Done

| Milestone | What | Commit |
|---|---|---|
| M0 | Skeleton, all GET endpoints on Postgres, UI served by the API, seeded demo case | `e26e881` |
| M0 review | Random hashed intake tokens, configurable DB port, Makefile | `6fa3af5` |
| M1 | Argon2 login + server-side sessions, review/gap/form mutations, package build with versions and sha256, tenant submit (attestation only), Electron shell | `b1212b4` |
| M1 hardening | Seed only when DB is empty (`make reset`), 422 for sourceless accepts, Redis in CI, test audit, concurrent-build test | `9d56e2f` |
| M1 follow-up | Electron 33 to 45.2.3 (`npm audit` clean, Node 22.12+, no install-script pin needed); Claude Code workflow and `scoper`/`implementer`/`reviewer`/`shipper` subagents; local-environment rules in AGENTS.md | PR #1 |
| M1 test fixes | From NineJZ356's Windows run: the seed reads `seed_data.json` as UTF-8 (tests and `make seed` failed on Windows code pages); tests ignore `backend/.env`, so the quickstart's `COOKIE_SECURE=false` no longer fails the Secure-cookie test | PR #1 |
| M2 (WS1) | Evidence ingest and tenant uploads: upload routes, type check by signature, metadata, stripped copy, text as `evidence_page` rows, evidence in the zip | PRs #6, #7, #8 (`24a343d`) |
| M3 (WS3) | Agent tool bodies and loop, `POST /cases/{id}/runs`, the `extract` step writing `evidence_fact`, `POST /runs/{id}/answer`, demo evals for prompt injection and fabricated quotes | PRs #5, #15, #16, #18, #19, #20 |
| M3 (WS3) | Prompt caching; `LLM_MODEL` and `ANTHROPIC_BASE_URL`; a citable page for each photo's capture date; the runner asks for the hearing date; visible conflict flags; cost priced with the model actually used | PRs #21, #26 to #30, #34 |
| M3 (demo) | Demo-honesty fixes from the usability review, neutral "Nothing yet" states, past hearing dates refused, synthetic upload files in `demo/`, the case brief PDF | PRs #23, #31 to #33, #37 |
| M3 (WS4) | Legal corpus, URL check, the `rules` step (sources and the "must be received by" deadline), the `gaps` step that drafts requests to the tenant; source check (Reg 25A, received-by wording, no HEIC in the package) | PR #35 (with #39), `569348d` |
| M3 (#40) | The `draft` step fills missing form fields from verified quotes, as `needs_confirmation`, with a Confirm button | PRs #46, #42 |
| M3 (#41) | `POST /cases` and a New case form on the caseload | PRs #46, #47 |
| M3 (#36, #38) | Locale-independent tests; the Tenant view shows the new intake link | PRs #43 to #45 (NineJZ356) |
| M3 (#49) | `RUN_BUDGET_S` setting: the whole run may take 180 s by default, one model call 60 s | PRs #50, #51 |
| M3 (#48) | The caseworker edits the request to the tenant and translates it with one model call; the tenant page shows the English too; language names in English first; English preview on the Tenant view | PRs #52, #53 (`074748a`) |
| Submission polish | README rewrite (pitch, architecture, live-mode setup, 3-minute demo, team), LICENSE, SECURITY.md statuses, security headers, system fonts, planning files moved to `docs/archive/`, API_CONTRACT rows; caseload wording ("Deadline passed (N days ago)", plurals, one "Must be received by" wording for stored labels) and seeded deadlines kept relative to today | `Lameda12/submission-polish` |

Details of every deviation from `API_CONTRACT.md`: `CONTRACT_CHANGES.md` (#1 to #38).

## In progress

Open PRs (2026-11-17), all drafts into `dev`. Merge #62 before #63 and #64; those two do not depend on each other.

| PR | Area | What |
|---|---|---|
| #55 | docs | This file brought up to date; the legal README points at #54; `docs/DEPLOY.md` (#57) |
| #62 | `schema:` | `FORWARDED_ALLOW_IPS` setting; `Intake.qr_svg`; CONTRACT_CHANGES #38 and a UI row (team approval of the UI exception asked there) |
| #63 | WS2 (#58, #59) | Rate limits count each visitor's own IP behind a trusted proxy; expired logins are deleted at each login and hourly |
| #64 | WS2 (#56) | QR code of a newly sent intake link on the Evidence page and Tenant view |

Open issues:
- **#54 (urgent):** a person must confirm two legal sources, Form J and Regulations s. 25A, before the demo. Until then both show as `unverified` on every case.
- **#9:** tell tenants that original photos go into the package. The GPS data is already removed from the package copies.
- **#10:** about 500 MB can be spooled to disk before the intake token is checked (WS2).
- **#4:** WS3 follow-ups from the PR #2 review.
- **#56, #58, #59:** fixed by #63 and #64 once merged (close them by hand: "Closes" does not fire on `dev`). **#57** is done by `docs/DEPLOY.md` in #55.
- **#60:** remove personal details from evidence text before it goes to the model (to discuss).
- **#61:** after the MVP: let the model see photos and scanned pages, with content checks first (malware, known illegal images, graphic content).

WS5 is unassigned. WS2's four items above are opoeci6's; the rest of WS2 has no owner.

## Known issues

- **No production guard.** The app starts with dev defaults (`SEED_PASSWORD`, compose passwords, `COOKIE_SECURE=false` in compose). It must refuse to start when `ENV=production` and `SEED_PASSWORD` or `SECRET_KEY` is unset or a dev default. Neither `ENV` nor `SECRET_KEY` exists in `config.py` yet. Tracked in WS2's "Done when".
- **Blob storage is a local volume** (`STORAGE_DIR`). Several API replicas need shared storage (WS2).
- **Rate limits behind a proxy** key on the socket IP unless the proxy is listed in `FORWARDED_ALLOW_IPS`. The setting and its handling are in PR #63 (issue #58), not merged yet; the hosted demo already sets it on the server.
- **Expired sessions are never purged** until PR #63 (issue #59) is merged.
- **Evidence text goes to the model as written**, names, addresses and phone numbers included (issue #60). Photos never do: the model gets only their capture time, device and editing software (issue #61 is about changing that after the MVP).
- **No malware scan or illegal-content check on uploads** (issue #61). Uploads are limited to JPG, PNG, HEIC, PDF and TXT, checked by content, and photos are re-encoded.
- **Font size:** the bundled Noto Sans SC adds about 10 MB to the repo and image.
- **`docker compose up --scale api=2` does not work yet:** the api service publishes fixed host port 8000. WS2 needs a proxy service.
- **The filing package files photos without their GPS data.** Each JPG, PNG and HEIC-made JPG in the zip is a copy with the GPS IFD (and an XMP packet carrying GPS) taken out; the capture time and orientation stay, and the stored original is untouched (`services/evidence/gps.py`). The manifest PDF says "location data removed" for each such file. Not covered: location in a maker note or in a legacy "Raw profile type exif" PNG text chunk. Issue #9's remaining part (warning the tenant on the intake page, an optional per-file "file the stripped copy instead") still waits on the open decision below.
- **An unauthenticated upload can spool about 500 MB to disk** (20 × 25 MB + 1 MB) before the intake token is checked. Needs a per-client cap at a proxy (issue #10, WS2).
- **Big5 and GBK TXT files with characters outside GB2312 answer 415** (issue #11, closed by #25: kept on purpose). The reason now says "re-save it as UTF-8", which fixes every one of them. Big5 stays refused on purpose: it decodes as GB18030 into private-use characters and no byte pattern tells the two code pages apart, so a guess would file traditional Chinese as different characters. Windows-1252 and Shift-JIS are refused for the same reason.
- **Verified by an agent on 2026-11-06 (Playwright + rendered pages, see the PR #1 comments):** Chinese glyphs render in the built PDF, second-org isolation in two separate browser contexts, `?mock=1`, the empty-caseload state. **Electron 45 window (2026-11-06, Windows, against `web/index.html?mock=1` over the DevTools protocol):** the mock UI renders, the renderer has no Node, `window.open` is denied, off-origin navigation is blocked. **Electron 45 window against the real API (2026-11-07, Windows 11, NineJZ356, PR #1):** `npm install`, `node check.js` and `npm start` work, login works in the window, the renderer has no Node, `window.open` is denied. **Mac: pending Lameda12's check by eye** (`make desktop` starts the window; install and `check.js` pass).
- **Throughput work is deferred:** `WEB_CONCURRENCY` and gzip belong to WS2; the load re-benchmark (`backend/bench/load.py`, p50/p95/p99 on the compose stack) to WS5. `GET /api/cases` already runs a fixed number of queries (query-count test).
- **UI routes don't include the case id** (`#timeline`), so a case can't be deep-linked or shared.
- **Seed data has a zh-language tenant but all-English content.** The demo case needs real Chinese tenant messages and evidence text (fictional) so the video shows multilingual intake. Owner: WS5.
- **CI runs on GitHub** with Postgres and Redis service containers; both checks are green on PR #1 (re-checked after each push).
- Rate-limit counters only count requests that pass body validation.
- Two seeded demo logins share one password (`SEED_PASSWORD`, compose default `tenantproof-demo`). Local only.

## WS3 TODO

- `schema:` PR for `config.py` and `.env.example`: `anthropic_api_key`, `record_fixtures`, `fixture_strict` (today `FIXTURE_STRICT` is read from the environment in `llm.py`; tests set it to 1). Until then `llm._live_api_key()` reads `ANTHROPIC_API_KEY` from the process environment only (not from `backend/.env`). The model is the `LLM_MODEL` setting (#26), defaulting to `llm.MODEL`.
- `RecordingProvider` (`RECORD_FIXTURES=1`) is not built yet. `Run.usage.est_cost_usd` uses the list price of the model actually used, cache reads and writes included (#34); a model not in the table gets no estimate.
- **Text and facts store:** `SqlTextStore` (`services/agent/evidence_text.py`) reads the `evidence_page` and `evidence_fact` tables (PR #6); the in-memory store stays for tests. The `extract` step (`services/agent/extract.py`, issue #14) writes the facts at the start of a run; WS1 ingest (PR #8) writes the pages. `runner.py` callers pass `SqlTextStore(session)`.
- Not built: the arq worker (a run executes as a background task in the API process), and the `ingest` step; `IMPLEMENTED_STEPS` is `extract`, `timeline`, `rules`, `draft` and `gaps`, in that order. The whole run may take `RUN_BUDGET_S` (180 s by default), one model call 60 s.
- **`draft` (#40, opoeci6, merged):** an agent loop, not deterministic as BUILD_PLAN first said (extracted facts carry no field key). Its one write tool, `fill_form_field`, fills only a `missing` field, never `remedy`; every citation must pass the verifier and the value must be words of a verified excerpt. Values land as `needs_confirmation`, and the form page has a Confirm button for them. With nothing to fill it makes no model call.
- `search_legal_sources` returns the corpus excerpt and its locator (WS4). An entry nobody has confirmed has no excerpt and returns `""`, never invented text.
- One random evidence nonce per run, saved on the steps so a resume reuses it. `request_hash` masks it, so recordings replay under any nonce.
- A photo gets one code-written page with its capture time (#28), so the agent can cite it. An `exif` date candidate must match a cited file's capture time.
- `flag_conflict` adds a `conflict` flag (contract change #30) and still appends to `strength_reasons`; the review screen shows a "Conflict" badge with the note. Case brief PDF for the caseworker (`GET /cases/{id}/case-brief`, contract change #34, merged as #37). Demo-honesty fixes from the AI usability review (merged as #31): "Not analysed yet" in the caseload and a banner, package 409 without a completed run or an accepted event (contract change #31), "Not in this prototype" for the unbuilt steps, duration and cost on the run page, Demo rows, a reason next to the disabled Send button, no Arabic link. The runner asks for the hearing date itself when the timeline step ends with none set and the model did not ask (the `ask_caseworker` pause, field `hearing_date`).

## Open decisions

- Who owns each workstream (table below).
- Whether the filed package carries stripped copies instead of originals. Originals keep GPS, but they also keep the sha256 chain and the EXIF that authenticate them. This decides issue #9.
- How tenants are told that originals are filed: #9's warning on the intake page.
- Whether `SECRET_KEY` is needed at all: sessions are server-side random tokens, so nothing signs with it today. Either WS2 adds a real use or drops it from the guard.
- Legal sources (WS4): three of the five are confirmed (NineJZ356, 2026-11-16). Form J and Regulations s. 25A still need a person to open the document and confirm the wording (issue #54, urgent). The checklist is `backend/app/services/legal/README.md`; Policy #28's URL is dead and the entry is left out, which that file explains.
- Whether to keep bundling the 10 MB CJK font or fetch it at build time.

## How to verify

Prerequisites: Docker, `uv`, Node 22.12+ (desktop only).

```bash
cp backend/.env.example backend/.env
make up                      # api + Postgres + Redis, migrates, seeds an empty DB
curl localhost:8000/healthz  # {"status":"ok",...}
make test                    # starts Postgres + Redis, runs pytest (about 2 minutes)
make lint                    # ruff + pyright
cd desktop && node check.js  # Electron security flags
```

Click-through (real API): open http://localhost:8000, sign in as `sam@example-clinic.test` (password `tenantproof-demo`), open Jordan Lee's case, review events, resolve both required items, tick the confirmations on Package, build twice, download v1 and v2. Mock mode: http://localhost:8000/?mock=1.

Reset local data: `make reset` (drops the dev database, migrates, reseeds).

## Workstreams

Prompts: `docs/NEXT_PROMPTS.md`.

| Workstream | Owner | Branch | Status | Blocked by |
|---|---|---|---|---|
| WS1 Evidence ingest + tenant uploads (M2) | opoeci6 | merged (`24a343d`) | done: upload routes, type check by signature, metadata, stripped copy, text as `evidence_page` rows, evidence in the zip (PRs #6, #7, #8). Follow-ups: #9 (#11 closed by #25) | none |
| WS2 Hosted deploy + infra hardening (M2) | opoeci6 (#56 to #59 only) | `opoeci6/m2-schema-ws2`, `opoeci6/m2-proxy-sessions`, `opoeci6/m2-intake-qr` | the hosted demo is set up by hand and described in `docs/DEPLOY.md` (#57, in #55). Draft PRs: #62 (`schema:`), #63 (#58 real client IP for the rate limits, #59 expired logins deleted), #64 (#56 QR code of the intake link). Not built and unowned: a managed host, S3 storage, the production guard, `--scale api=2`, #10 | none |
| WS3 Agent runtime (M3) | Lameda12 | merged | day 1 merged (PR #2); day 2 merged as PRs #5, #15, #18, #19, #20: the 12 tool bodies, `loop.py`, `runner.py` (one nonce per run, a whole-run deadline, `RUN_BUDGET_S`, 180 s by default since #51; pause/resume), `verifier.py`, `strength.py`, `dates.py`, refusal handling, `SqlTextStore` over the #6 tables, `POST /cases/{id}/runs` (issue #13), the `extract` step (issue #14), `POST /runs/{id}/answer` (contract in PR #19) with the run page's answer control, and the demo evals (PR #16). Prompt caching on the Anthropic provider (breakpoints on the last tool and the stable system text, the nonce in a run note after them); cache tokens are in the run's stored usage. `rules` and `gaps` came with WS4 (#35). The `draft` step (#40, opoeci6, approved by Lameda12) is merged as #42: the `fill_form_field` tool and a form agent. Next: the arq worker and the `ingest` step | nothing, for what is merged |
| WS4 Legal sources, rules, gaps agent (M3) | opoeci6 | merged (#35, `569348d`) | merged on 2026-11-16 with Lameda12's #39 inside; NineJZ356 confirmed three sources; Form J and Reg 25A are not confirmed yet (#54, urgent). PR 1: `services/legal/` with the corpus (four official sources, verbatim excerpts), the URL check and its command, excerpts in `search_legal_sources`, and the deterministic `rules` step (sources plus the evidence deadline). PR 2: the `gaps` step — deterministic checks first, then an agent that drafts requests to the tenant in their language. **A person must confirm the last two sources** (#54): `backend/app/services/legal/README.md`. A source check (fix/legal-sources) corrected the README, added the Regulations s. 25A entry, relabelled the deadline "must be received by", and keeps `.heic` out of the package. Since then: the gaps prompt skips fields the `draft` step filled (#42), and the caseworker can edit and translate each request to the tenant (#48, PRs #52 and #53) | a person for #54 |
| WS5 Evals, security, perf, demo (M3 to M4) | TODO | `<github-username>/m4-evals-security-perf` | not started | starts now; fills in as WS1 to WS4 land |
