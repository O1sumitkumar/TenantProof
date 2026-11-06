# Security (stub; completed in M4)

Threat model and controls. Status column is updated as controls land.

| Threat | Control | Status |
|---|---|---|
| Prompt injection inside evidence | Evidence in delimited data blocks; system prompt treats it as data; tools read/draft only; all outputs need human approval; eval case with an injected document must pass | planned (M3) |
| Tenant link guessing or leakage | `secrets.token_urlsafe(32)`, only sha256 stored, 14-day expiry, revoke on re-send, rate-limited | planned (M0 schema, M2) |
| Malicious uploads | 25 MB cap, MIME sniffing + allowlist, re-encode images, filenames never used as paths, content-addressed storage | planned (M2) |
| Cross-org data access | Org check on every by-id load; tests for 404 on other org's objects | M0 |
| Caseworker auth | argon2 password hash, httpOnly + SameSite session cookie, login rate limit | planned (M1) |
| Location privacy | EXIF/GPS read for the log, stripped before any file reaches the model | planned (M2) |
| Internal notes leaking | `caseworker_note` excluded from form, narrative, package and tenant view (tested) | M0 (narrative), M1 (package) |
| Electron | contextIsolation, sandbox, no Node in renderer, navigation locked to the app origin | planned (M1) |
| Secrets and PII in logs | Env-only secrets, structured logs with redaction of names, messages and tokens | planned |
| Accountability | Append-only activity log for agent, tenant and caseworker actions | M1 |
