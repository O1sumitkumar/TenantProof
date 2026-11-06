from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.routers import activity, cases, evidence, form, gaps, intake, me, runs, sources, timeline

app = FastAPI(title="TenantProof API", version="0.1.0")

api = FastAPI(title="TenantProof API")
for module in (me, cases, evidence, runs, timeline, gaps, sources, form, activity, intake):
    api.include_router(module.router)
app.mount("/api", api)

_web = Path(__file__).resolve().parent.parent.parent / "web"
_index = _web / "index.html"


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok", "llm_mode": get_settings().llm_mode}


@app.get("/favicon.ico", include_in_schema=False)
def favicon() -> Response:
    return Response(status_code=204)


@app.get("/")
@app.get("/i/{token}")
def serve_ui(token: str | None = None) -> FileResponse:
    """The same UI serves caseworkers (/) and tenants (/i/{token})."""
    return FileResponse(_index)


if _web.exists():
    app.mount("/static", StaticFiles(directory=_web), name="static")
