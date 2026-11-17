"""Reject a bad intake link before FastAPI parses (and spools) the multipart body.

FastAPI reads a multipart body before the route's dependencies run, so without this middleware
POST /api/intake/<anything>/files could spool MAX_FILES x MAX_UPLOAD_BYTES (about 501 MB) to
disk before find_active() answers 404 (issue #10). The middleware checks the token first and
answers 404 without touching the body; the route still checks it again for the case worker and
for requests that reach it another way. The proxy caps concurrent uploads per client as the
second layer (deploy/nginx.conf)."""

import re

from sqlmodel import Session
from starlette.concurrency import run_in_threadpool
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from app.db import get_engine
from app.models import CaseRow
from app.services.intake_token import find_active

FILES_PATH = re.compile(r"^/api/intake/(?P<token>[^/]+)/files$")
NOT_FOUND = {"detail": "Link not found"}


def token_is_active(token: str) -> bool:
    """The route's answer: unknown, revoked, expired or orphaned links are all 404."""
    with Session(get_engine()) as session:
        row = find_active(session, token)
        return row is not None and session.get(CaseRow, row.case_id) is not None


class IntakeTokenGate:
    """ASGI middleware: a bad token is a 404 before the request body is read."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["method"] != "POST":
            await self.app(scope, receive, send)
            return
        match = FILES_PATH.match(scope["path"])
        if match is None:
            await self.app(scope, receive, send)
            return
        if not await run_in_threadpool(token_is_active, match.group("token")):
            await JSONResponse(NOT_FOUND, status_code=404)(scope, receive, send)
            return
        await self.app(scope, receive, send)
