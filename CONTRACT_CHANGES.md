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

## UI changes (`web/index.html`)

| Milestone | Change |
|---|---|
| M0 | `API_BASE` becomes `/api`; `USE_MOCK` stays switchable; `fetch` sends `credentials: "include"` |
| M0 | `CASE_ID` and `INTAKE_TOKEN` removed as constants when `USE_MOCK=false`: case id comes from `GET /cases`/route, token from the `/i/{token}` URL |
| M0 | `/i/{token}` tenant mode: hides caseworker nav and skips caseworker fetches |
| M0 fix | Evidence panel shows the link only right after sending (`S.lastLink`); the caseworker Tenant view preview needs a link sent in the session, else it shows a "Send intake link" prompt |
| M0 | `request()` error parsing handles `detail` as string or `{ reasons: string[] }` |
| M1 | Minimal login view (approved exception) |
| M3 | `needs_input` answer control on the run view (approved exception) |

## Implementation notes
- M0 auth is a dev stub gated by `DEV_STUB_AUTH` (default off).
- Postgres host port is `POSTGRES_HOST_PORT` (default 5433). The Makefile (`up`, `down`, `test`, `lint`, `seed`, `link`) uses `docker compose` if available, else `docker-compose`.
- The four summary-only cases get placeholder gap/event rows so their counts are real. `seed_data.json` marks them `synthetic_placeholder_rows: true` and the rows are titled `[Synthetic placeholder] ...`.

## Additions to track
- Package zip download endpoint (`GET /cases/{id}/package/download`): not in the contract; to be added in M1 and logged here.
