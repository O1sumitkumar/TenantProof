"""HTTP glue for the two upload routes: rate limit, early body-size refusal, rejections."""

import re

from fastapi import HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse
from starlette.middleware.base import RequestResponseEndpoint
from starlette.responses import Response

from app.config import get_settings
from app.services.evidence.ingest import MAX_FILES, Upload, UploadRejected, check

UPLOAD_PATH = re.compile(r"/cases/[^/]+/evidence$|/intake/[^/]+/files$")
MULTIPART_SLACK = 1024 * 1024  # boundaries and part headers


def upload_limit() -> str:
    return get_settings().upload_rate_limit


def read_uploads(files: list[UploadFile]) -> list[Upload]:
    """Check every file (count, size, type) before anything is stored. Raises 413 or 415.
    The files stay spooled on disk; ingest reads one at a time."""
    try:
        return check([(f.filename, f.file) for f in files], get_settings().max_upload_bytes)
    except UploadRejected as exc:
        raise HTTPException(exc.status_code, {"reasons": exc.reasons}) from exc


async def refuse_oversized_upload(request: Request, call_next: RequestResponseEndpoint
                                  ) -> Response:
    """FastAPI parses (and spools) a multipart body before any dependency runs, so the auth,
    token and per-file checks come after the whole body has arrived. Refuse a body whose
    declared length can't be valid before reading it. Chunked bodies with no Content-Length
    are bounded by the proxy (WS2)."""
    if request.method == "POST" and UPLOAD_PATH.search(request.url.path):
        limit = MAX_FILES * get_settings().max_upload_bytes + MULTIPART_SLACK
        declared = request.headers.get("content-length", "")
        if declared.isdigit() and int(declared) > limit:
            return JSONResponse(
                {"detail": {"reasons": ["The upload is too large"]}}, status_code=413
            )
    return await call_next(request)
