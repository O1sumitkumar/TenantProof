# Security

Threat model and controls, with what is built today. The Status column says which milestone shipped each control, or what is still open.

| Threat | Control | Status |
|---|---|---|
| Prompt injection inside evidence | Evidence in delimited data blocks; system prompt treats it as data; tools read/draft only; all outputs need human approval; eval case with an injected document must pass | shipped (M3): evidence wrapped in a per-run random tag, every cited quote re-checked against the stored text, strength set by code, injection and fabricated-quote evals (also run live) |
| Tenant link guessing or leakage | `secrets.token_urlsafe(32)`, only sha256 stored, 14-day expiry, revoke on re-send, unknown/revoked/expired all 404; `/submit` rate-limited (20/min/IP) | M0, M1 (submit) |
| Malicious uploads | 25 MB cap, MIME sniffing + allowlist, re-encode images, filenames never used as paths, content-addressed storage | shipped (M2): type checked by file signature, not by name or declared type; per-file cap and body-size cap before anything is stored; the copy sent to the model is re-encoded |
| Cross-org data access | Org check on every by-id load; tests for 404 on other org's objects | M0 |
| Caseworker auth | argon2 hash (dummy verify for unknown emails, same 401 for both failures); server-side session table storing only sha256 of the cookie; httpOnly + SameSite=Lax + `COOKIE_SECURE` (default true; compose sets false for plain-http localhost, keep true in any deployed env); 12 h expiry, and expired session rows are deleted on every login and by an hourly task (#59); login 10/min/IP via slowapi on Redis; Origin check on mutations | M1, WS2 (#59) |
| Location privacy | EXIF/GPS is read for the evidence log only; the copy sent to the model has all metadata removed; in the filing package every JPG, PNG and HEIC-made JPG is a copy with its GPS data removed (capture time and orientation kept, stored originals untouched, the manifest says "location data removed"); an image whose GPS cannot be removed is left out | shipped (M2; package copies in PR #39 and later). Not covered: location in a maker note or a legacy PNG text chunk |
| File formats | The Program does not take HEIC, so a HEIC is filed only as a JPG made from it; no `.heic` is ever in the package | shipped |
| Browser hardening | Every answer carries `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY` and `Referrer-Policy: strict-origin-when-cross-origin`. No Content-Security-Policy yet: the UI is one page with inline script and style. The UI loads no third-party fonts or scripts | shipped; CSP open |
| Internal notes leaking | `caseworker_note` excluded from form, narrative, package PDFs/manifest/zip and tenant view (tested) | M0 (narrative), M1 (package) |
| Electron | contextIsolation, sandbox, no Node in renderer, no preload, http(s) only, navigation and redirects locked to the app origin, popups and permissions denied; `desktop/check.js` asserts the flags | M1 |
| Secrets and PII in logs | Env-only secrets, structured logs with redaction of names, messages and tokens | partial: secrets come from the environment, and log lines carry exception types, not text; redaction is not built |
| Accountability | Append-only activity log for agent, tenant and caseworker actions; package builds log version + zip sha256 | M1 |
| Package integrity | Zip stored content-addressed by sha256 (not in the database); each rebuild is a new version; download streams from storage; row sha256 = stored blob sha256 (tested) | M1 |
| CSRF | SameSite=Lax cookie plus an Origin check on every POST/PATCH/PUT/DELETE: a browser-sent Origin must be the app's own (`PUBLIC_BASE_URL` or the request host), else 403 | M1 |
| Brute force and abuse | slowapi limits per client IP, counters in Redis (shared across API replicas): login 10/min, tenant submit 20/min. Tests and CI run against real Redis. Behind a proxy the client IP comes from `X-Forwarded-For`, believed only from the proxies in `FORWARDED_ALLOW_IPS` (default `127.0.0.1`; the app applies it itself, #58). The proxy must set that header, not append to it; see `docs/DEPLOY.md` | M1, WS2 (#58) |
| Stale UI | UI page served with `Cache-Control: no-cache` | M1 |
| Package storage | Zips live on a `blobs` volume (`STORAGE_DIR`), content-addressed; not in the database | M1 |

## Known gaps
- **Blob storage is a local volume.** Several API replicas need shared storage (object store) behind `storage.py`.
- **Font size.** The bundled Noto Sans SC adds about 10 MB to the repo and the image.
- **Unauthenticated multipart bodies.** About 500 MB can be spooled to disk before the intake token is checked (issue #10).
- **No Content-Security-Policy.** The single-page UI uses inline script and style, so a useful policy needs the UI split first.
