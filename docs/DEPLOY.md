# Deploying TenantProof

This is the WS2 runbook: local multi-replica compose (works today) and the hosted Railway
layout (config committed, project not created yet). `API_CONTRACT.md` stays the source of
truth for the API; this file covers environment, proxy and storage.

## Topology

| Service | Image / build | Notes |
|---|---|---|
| `api` | `backend/Dockerfile`, context is the repo root | Runs uvicorn with `--proxy-headers`. Any number of replicas. |
| `proxy` | `nginx:1.29-alpine`, `deploy/nginx.conf` | The only service that publishes a host port. Overwrites `X-Forwarded-For` with the real peer address. |
| `migrate` | same build as `api` | Runs `alembic upgrade head` and the demo seed once, before the replicas start. |
| `postgres` | `postgres:16` | Railway Postgres plugin in production. |
| `redis` | `redis:7` | Railway Redis; also backs rate-limit counters. |

The arq worker is planned for M3 (`docs/STATUS.md`); there is no worker service yet.

## Environment

| Variable | Local compose | Production | Notes |
|---|---|---|---|
| `DATABASE_URL` | `postgresql+psycopg://tenantproof:tenantproof@postgres:5432/tenantproof` | Railway `DATABASE_URL` | psycopg 3 URL. |
| `REDIS_URL` | `redis://redis:6379/0` | Railway `REDIS_URL` | |
| `PUBLIC_BASE_URL` | `http://localhost:8000` | the public https URL | Used for the Origin check and intake links. |
| `COOKIE_SECURE` | `false` (plain http on localhost) | **`true`** | `true` everywhere except local http. |
| `LLM_MODE` | `fixture` unless set | `live` | `fixture` replays recordings and never calls the network. |
| `ANTHROPIC_API_KEY` | empty | set as a secret | Never commit it. |
| `LLM_MODEL` / `ANTHROPIC_BASE_URL` | optional | optional | |
| `STORAGE_DIR` | `/data/storage` | `/data/storage` on the mounted volume | Blob adapter to S3 is still a TODO (see below). |
| `FORWARDED_ALLOW_IPS` | `172.28.0.10` (the proxy) | Railway edge peer | Only this address may set `X-Forwarded-For`. |
| `SEED_PASSWORD` | `tenantproof-demo` | not set | Demo only; the production guard will refuse dev defaults (TODO). |
| `ENV` | unset | `production` once the guard exists | Not read by the app yet. |

## Start command

```bash
uv run --no-dev uvicorn app.main:app --host 0.0.0.0 --port "$PORT" --proxy-headers
```

`--proxy-headers` is what makes slowapi key its rate limits on the client address instead of
the proxy's socket address. It reads `FORWARDED_ALLOW_IPS`; a value of `*` trusts every peer,
so use it only where nothing can reach the API except the platform edge.

## Migrations

Run once per release, never per replica — `docker compose up --scale api=2` would otherwise
have two Alembic processes racing on the same database:

```bash
uv run --no-dev alembic upgrade head
```

In compose this is the `migrate` service; on Railway set it as the release/pre-deploy command.
`python -m app.seed` is demo-only and idempotent.

## Storage

`backend/app/services/storage.py` is the only module that touches blob bytes. It is
filesystem-backed today, so replicas on one Docker host share the `blobs` named volume and a
package download works from either replica. That is enough for the local WS2 check, but a
local volume is not shared across hosts: the S3-compatible adapter (Railway volume bucket or
R2) behind the same interface is the remaining WS2 item. Until it lands, run a single API
replica in production and keep the volume attached.

## Health

`GET /healthz` pings Postgres and Redis and answers `503` with
`{"status": "degraded", "db": ..., "redis": ...}` when either is down. Both compose (the
`api` healthcheck) and Railway (`railway.toml` `healthcheckPath`) use it to gate traffic.

## Upload limits (issue #10)

The two upload routes (`POST /cases/{id}/evidence`, `POST /intake/{token}/files`) can carry
20 x 25 MiB + 1 MiB, about 501 MB, and FastAPI reads a multipart body before its dependencies
run. Three layers keep that from being a cheap unauthenticated disk write:

1. nginx allows 2 concurrent uploads per client and one new upload per second (burst 4),
   answers 429 beyond that, and streams the body (`proxy_request_buffering off`) instead of
   buffering it to this proxy's disk.
2. `IntakeTokenGate` (`backend/app/services/intake_gate.py`) answers 404 for an unknown,
   revoked or expired intake link before FastAPI parses the multipart body, so a bad link
   spools nothing on a replica. The route checks the token again.
3. `UploadBodyLimit` still cuts every body at 501 MB, chunked or not.

The per-client cap keys on the address nginx sees. Locally that is the client. If another
load balancer sits in front of this proxy (for example a platform edge), configure
`set_real_ip_from` / `real_ip_header` for its ranges, or rely on the platform's own rate
limiting; layers 2 and 3 do not depend on the client address.

## Local verification

```bash
# One replica behind nginx, at http://localhost:8000 (proxy)
docker compose up -d --build

# Two replicas, still one host port
docker compose up -d --scale api=2 --build

curl -s localhost:8000/healthz          # {"status":"ok","db":"ok","redis":"ok",...}
docker compose logs -f proxy            # requests alternate between api-1 and api-2
```

A DNS name `api` with several A records is re-resolved by nginx every 10 s
(`resolver ... valid=10s` + `server api:8000 resolve`), so scaling does not need a restart.

Build context: `.dockerignore` excludes `.git`, `.tools`, `node_modules` and `.venv`. `.tools`
holds VM disks (several GB) — keep it excluded before building.

## Railway

`railway.toml` sets the Dockerfile path, the start command and the healthcheck. Create the
project, then:

1. Add a Postgres plugin and a Redis plugin; copy their URLs into the `api` service.
2. Set `PUBLIC_BASE_URL`, `COOKIE_SECURE=true`, `LLM_MODE=live`, `ANTHROPIC_API_KEY`,
   `STORAGE_DIR=/data/storage`, `FORWARDED_ALLOW_IPS=<Railway edge peer>`.
3. Mount a volume at `/data` (until the S3 adapter lands).
4. Set the release command from "Migrations" above.
5. Deploy, then open the URL on a phone: sign in, open Jordan Lee's case, and confirm the
   QR-code intake path (QR is a TODO) and a photo upload.

Production guard (TODO): the app still starts with dev defaults. The planned guard refuses to
start when `ENV=production` and `SEED_PASSWORD`/`SECRET_KEY` are unset or the dev default;
whether `SECRET_KEY` gets a real use or is dropped is an open decision in `docs/STATUS.md`.
