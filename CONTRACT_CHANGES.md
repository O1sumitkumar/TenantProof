# Contract changes

Deviations from `API_CONTRACT.md` (v0.2). Each has a reason. Source: `BUILD_PLAN.md` section 3 plus review decisions.

| # | Change | Reason |
|---|---|---|
| 1 | `narrative` is a deterministic template over `accepted`/`edited` events, rebuilt on every GET | Fast, free, stable; guarantees rejected events never reach the form |
| 2 | `PATCH /gaps/{id}` with `value`: if the gap has `input.field_key`, write the value to that form field as `user_entered` and resolve the gap | Matches prototype behaviour; one round trip |
| 3 | `Run.stale: boolean`, true when evidence arrives after `started_at` | UI can tell the caseworker to re-run |
| 4 | Run terminal status: `failed` if a step failed; `needs_review` if a step is `needs_input`, any event `pending`, or a blocking gap is open; else `done` | Contract left it undefined |
| 5 | `Run.usage: { input_tokens, output_tokens, est_cost_usd, duration_ms }` | Performance and cost evidence |
| 6 | New `POST /runs/{run_id}/answer` with `{ step_key, answer }` | Resume a run paused by `ask_caseworker` |
| 7 | `EvidenceItem.sha256` is of the original bytes; the EXIF-stripped copy is a separate derived blob | Chain of custody |
| 8 | `POST /cases/{id}/package` errors: **409** when case state blocks it (open blocking gaps, tenant not attested); **422** when the body lacks caseworker attestations. Both return `{ detail: { reasons: string[] } }` | Prototype used 400 and a string `detail`; clearer split |
| 9 | Every by-id handler checks `obj.case.org_id == user.org_id`; other orgs get 404 | Object-level authorization |
| 10 | New `POST /auth/login` returning an httpOnly session cookie. M0 uses a dev-stub user; real login in M1 | Auth |
| 11 | Intake links: `Intake.url` is `string \| null`. The raw link (`secrets.token_urlsafe(32)`) is returned only by `POST /cases/{id}/intake-link`; every GET returns `null`. The DB stores only sha256 + expiry + revoked flag (table `intake_token`). Re-sending creates a new token and revokes all earlier ones; revoked, expired and unknown tokens all return the same 404 | Tokens are not recoverable from the database or from case reads |
| 12 | `PATCH /cases/{case_id}/form-draft/fields/{key}` (was `/form-draft/fields/{key}`) | Field keys repeat per case, so the case must be in the path |
| 13 | `Package` gains `version: number` and `sha256: string` (of the zip). Every `POST /cases/{id}/package` creates a new version; rows are never overwritten. The zip is stored content-addressed (sha256) outside the database; the row keeps `sha256` + `storage_key` | Chain of custody; rebuild history |
| 14 | New `GET /cases/{id}/package/download[?version=N]`: latest version unless `N` given; 404 for unknown version or no package; org-checked; also sends `X-Package-Sha256` | Contract had no way to fetch the package |
| 15 | `POST /auth/logout` returns `{ ok: true }` and clears the cookie; `POST /auth/login` body `{ email, password }` returns `User` | Completes #10 |
| 16 | `PATCH /timeline/{id}`: an edit to title/description/date with no `review_status` sets `edited`; a date is stamped `basis: "user"` only when its value or precision actually changed; `caseworker_note: null` clears, omitting it keeps. `review_status` is optional (contract listed it as required); a no-op edit changes nothing, and a rejected event needs an explicit `review_status` to come back. `date.value` must be a valid date for its precision (422 otherwise) | UI resends the unchanged date on every edit |
| 17 | Stage rules: `POST /gaps/{id}/tenant-request` sets `waiting_tenant`; `POST /intake/{token}/submit` recomputes the stage (normally back to `needs_review`); other mutations recompute it, keeping `waiting_tenant` only while a request is outstanding and always keeping `hearing_scheduled` | Caseload shows when a case needs attention again |
| 18 | `POST /intake/{token}/submit` in M1 records the attestation only (no files); 422 `{ detail: { reasons } }` unless both `attest_genuine` and `consent_share` are true. Response `{ ok: true }` | Files arrive in M2 |
| 19 | `PATCH /gaps/{id}` reopening a resolved gap clears the form value that gap wrote (field returns to `missing`); `value` requires `status: "resolved"` and a gap with an `input.field_key` (422 otherwise) | Keeps form and gaps consistent |
| 20 | `PATCH /cases/{id}/form-draft/fields/{key}` with an empty value reopens the gap it had resolved. The stage counts empty required fields like open blocking gaps, so stage and package gating agree | Found by tests: stage said `ready_to_file` while the package refused |
| 21 | `POST /cases/{id}/package` with no body or missing attestations also answers 422 `{ detail: { reasons } }`; a narrative line with no sources has no trailing `[]` | Consistent error shape |
| 22 | `PATCH /timeline/{id}` to `accepted` or `edited` (explicit or implied by an edit) on an event with no sources returns 422 `{ detail: { reasons: ["needs at least one source"] } }`; rejecting, resetting to pending and note-only changes still work. The form narrative also leaves out any unsourced event | API_CONTRACT design rule 2: no source, no fact |

## UI changes (`web/index.html`)

| Milestone | Change |
|---|---|
| M0 | `API_BASE` becomes `/api`; `USE_MOCK` stays switchable; `fetch` sends `credentials: "include"` |
| M0 | `CASE_ID` and `INTAKE_TOKEN` removed as constants when `USE_MOCK=false`: case id comes from `GET /cases`/route, token from the `/i/{token}` URL |
| M0 | `/i/{token}` tenant mode: hides caseworker nav and skips caseworker fetches |
| M0 fix | Evidence panel shows the link only right after sending (`S.lastLink`); the caseworker Tenant view preview needs a link sent in the session, else it shows a "Send intake link" prompt |
| M0 | `request()` error parsing handles `detail` as string or `{ reasons: string[] }` |
| M1 | Minimal login view (approved exception): shown on a 401, plus a "Sign out" button in the top bar |
| M1 | `UPLOADS_ENABLED = false` config flag: tenant page needs only the two confirmations and skips `/files`; shows a "coming soon" line (flipped in M2) |
| M1 | Form field edits call `PATCH /cases/{id}/form-draft/fields/{key}` (mock route updated to match) |
| M1 | Package view shows the version and a download link (real mode only); mock `Package` gains `version`, `sha256` |
| M1 fix | Empty caseload shows a "No cases yet" state. Case-scoped loaders run only when a case is selected, so the UI never requests `/cases/null/...`; a case route with no case selected redirects to the caseload. If the selected case 404s, the UI clears it, returns to the caseload and shows a toast. A 404 on the caseworker's intake preview now means "no active link", not "case gone". No change in mock mode |
| M3 | `needs_input` answer control on the run view (approved exception) |
| M1 fix | Tenant page shows each request's `message` (already in the tenant's language; `IntakeRequest` has no `message_en`), not `message_en` for non-zh tenants, which rendered blank. The mock intake requests drop `message_en` so mock mode matches the API. Browser title is "TenantProof" (was "TenantProof Prototype (Copy)"). The "Show data contract" switch is hidden on the tenant page (`body.tenant`). |

## Implementation notes
- M0's `DEV_STUB_AUTH` is removed in M1. Seeds create two orgs with one caseworker each (`sam@example-clinic.test`, `jo@harbourside-clinic.test`); passwords come from `SEED_PASSWORD` (compose default `tenantproof-demo`, local only).
- PDFs use bundled Noto Sans (Regular, Bold) and Noto Sans SC (Regular), SIL OFL, in `backend/app/assets/fonts/` (sha256 in `FONTS.md`), so Chinese renders.
- Seeding: `python -m app.seed` loads data only into an empty database, so `docker compose up` never wipes work. `--force` (used by `make seed`) wipes and reloads; `make reset` drops the dev database, migrates and reseeds. The blob volume is not touched by either.
- Process: the timeline, gaps and form routers were written by the main session instead of `scaffolder` (the spec was as long as the code). `scaffolder` wrote only the Electron shell; `test-writer` wrote the tests, which the main session audited.
- `desktop/main.js` also blocks off-origin `will-redirect` (the scaffolded version only blocked `will-navigate`).
- The UI page is served with `Cache-Control: no-cache` so a changed `index.html` is never stale.
- Compose adds a named volume `blobs` mounted at `/data/storage` (`STORAGE_DIR`) for package zips.
- CI runs a Redis service and the tests use it for rate-limit counters (`RATE_LIMIT_STORAGE_URI=redis://localhost:6379/1`); there is no in-memory fallback.
- M1 zip contents: `application_draft.pdf`, `evidence_manifest.pdf`, `manifest.json`. Evidence files join the zip in M2.
- Postgres host port is `POSTGRES_HOST_PORT` (default 5433). The Makefile (`up`, `down`, `test`, `lint`, `seed`, `link`) uses `docker compose` if available, else `docker-compose`.
- The four summary-only cases get placeholder gap/event rows so their counts are real. `seed_data.json` marks them `synthetic_placeholder_rows: true` and the rows are titled `[Synthetic placeholder] ...`.

