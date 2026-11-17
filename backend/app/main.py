import logging
from pathlib import Path
from urllib.parse import urlsplit

import redis
from fastapi import FastAPI, Request, status
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from sqlalchemy import text
from sqlmodel import Session

from app.config import get_settings
from app.db import get_engine
from app.ratelimit import limiter
from app.routers import (
    activity,
    auth,
    cases,
    evidence,
    form,
    gaps,
    intake,
    me,
    package,
    runs,
    sources,
    timeline,
)
from app.services.evidence.http import UploadBodyLimit
from app.services.intake_gate import IntakeTokenGate

app = FastAPI(title="TenantProof API", version="0.1.0")
# Issue #10: an intake upload with a bad token is refused before its body is read.
app.add_middleware(IntakeTokenGate)
logger = logging.getLogger(__name__)

api = FastAPI(title="TenantProof API")
api.state.limiter = limiter
api.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)  # type: ignore[arg-type]
UNSAFE = {"POST", "PUT", "PATCH", "DELETE"}


@api.middleware("http")
async def check_origin(request: Request, call_next):
    """CSRF defence beside SameSite=Lax: a browser-sent Origin on a mutation must be ours.
    Requests without Origin (curl, server-to-server) carry no ambient cookie risk."""
    origin = request.headers.get("origin")
    if request.method in UNSAFE and origin:
        public = urlsplit(get_settings().public_base_url)
        allowed = {f"{public.scheme}://{public.netloc}", f"{request.url.scheme}://{request.url.netloc}"}
        if origin not in allowed:
            return JSONResponse({"detail": "Cross-origin request refused"}, status_code=403)
    return await call_next(request)


api.add_middleware(UploadBodyLimit)  # WS1: caps upload bodies before FastAPI reads them

for module in (
    auth, me, cases, package, evidence, runs, timeline, gaps, sources, form, activity, intake
):
    api.include_router(module.router)
app.mount("/api", api)

_web = Path(__file__).resolve().parent.parent.parent / "web"
_index = _web / "index.html"


def _db_reachable() -> bool:
    try:
        with Session(get_engine()) as session:
            session.execute(text("SELECT 1"))
        return True
    except Exception:  # any failure means the dependency is unhealthy
        logger.warning("healthz: Postgres unreachable", exc_info=True)
        return False


def _redis_reachable() -> bool:
    try:
        client = redis.Redis.from_url(
            get_settings().limiter_uri, socket_connect_timeout=2, socket_timeout=2
        )
        try:
            return bool(client.ping())
        finally:
            client.connection_pool.disconnect()
    except Exception:
        logger.warning("healthz: Redis unreachable", exc_info=True)
        return False


@app.get("/healthz")
def healthz(response: Response) -> dict[str, str]:
    """Readiness: the API is useful only when both Postgres and Redis answer."""
    db_ok = _db_reachable()
    redis_ok = _redis_reachable()
    if not (db_ok and redis_ok):
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {
        "status": "ok" if db_ok and redis_ok else "degraded",
        "db": "ok" if db_ok else "error",
        "redis": "ok" if redis_ok else "error",
        "llm_mode": get_settings().llm_mode,
    }


@app.get("/favicon.ico", include_in_schema=False)
def favicon() -> Response:
    return Response(status_code=204)


@app.get("/")
@app.get("/i/{token}")
def serve_ui(token: str | None = None) -> FileResponse:
    """The same UI serves caseworkers (/) and tenants (/i/{token})."""
    return FileResponse(_index, headers={"Cache-Control": "no-cache"})  # always revalidate


if _web.exists():
    app.mount("/static", StaticFiles(directory=_web), name="static")
