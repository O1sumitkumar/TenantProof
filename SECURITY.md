# Security (stub; completed in M4)

Threat model and controls. Status column is updated as controls land.

| Threat | Control | Status |
|---|---|---|
| Prompt injection inside evidence | Evidence in delimited data blocks; system prompt treats it as data; tools read/draft only; all outputs need human approval; eval case with an injected document must pass | planned (M3) |
| Tenant link guessing or leakage | `secrets.token_urlsafe(32)`, only sha256 stored, 14-day expiry, revoke on re-send, unknown/revoked/expired all 404; `/submit` rate-limited (20/min/IP) | M0, M1 (submit) |
| Malicious uploads | 25 MB cap, MIME sniffing + allowlist, re-encode images, filenames never used as paths, content-addressed storage | planned (M2) |
| Cross-org data access | Org check on every by-id load; tests for 404 on other org's objects | M0 |
| Caseworker auth | argon2 hash (dummy verify for unknown emails, same 401 for both failures); server-side session table storing only sha256 of the cookie; httpOnly + SameSite=Lax + `COOKIE_SECURE` (default true; compose sets false for plain-http localhost, keep true in any deployed env); 12 h expiry, and expired session rows are deleted on every login and by an hourly task (#59); login 10/min/IP via slowapi on Redis; Origin check on mutations | M1, WS2 (#59) |
| Location privacy | EXIF/GPS read for the log, stripped before any file reaches the model | planned (M2) |
| Internal notes leaking | `caseworker_note` excluded from form, narrative, package PDFs/manifest/zip and tenant view (tested) | M0 (narrative), M1 (package) |
| Electron | contextIsolation, sandbox, no Node in renderer, no preload, http(s) only, navigation and redirects locked to the app origin, popups and permissions denied; `desktop/check.js` asserts the flags | M1 |
| Secrets and PII in logs | Env-only secrets, structured logs with redaction of names, messages and tokens | planned |
| Accountability | Append-only activity log for agent, tenant and caseworker actions; package builds log version + zip sha256 | M1 |
| Package integrity | Zip stored content-addressed by sha256 (not in the database); each rebuild is a new version; download streams from storage; row sha256 = stored blob sha256 (tested) | M1 |
| CSRF | SameSite=Lax cookie plus an Origin check on every POST/PATCH/PUT/DELETE: a browser-sent Origin must be the app's own (`PUBLIC_BASE_URL` or the request host), else 403 | M1 |
| Brute force and abuse | slowapi limits per client IP, counters in Redis (shared across API replicas): login 10/min, tenant submit 20/min. Tests and CI run against real Redis. Behind a proxy the client IP comes from `X-Forwarded-For`, believed only from the proxies in `FORWARDED_ALLOW_IPS` (default `127.0.0.1`; the app applies it itself, #58). The proxy must set that header, not append to it; see `docs/DEPLOY.md` | M1, WS2 (#58) |
| Stale UI | UI page served with `Cache-Control: no-cache` | M1 |
| Package storage | Zips live on a `blobs` volume (`STORAGE_DIR`), content-addressed; not in the database | M1 |

## Known gaps (not fixed in M1)
- **Blob storage is a local volume.** Several API replicas need shared storage (object store) behind `storage.py`.
- **Font size.** The bundled Noto Sans SC adds about 10 MB to the repo and the image.
