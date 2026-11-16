"""Auth: argon2 password check + server-side session behind an httpOnly cookie
(CONTRACT_CHANGES #10). Only sha256(cookie value) is stored."""

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any, cast

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import Depends, HTTPException, Request, Response, status
from sqlalchemy import delete
from sqlalchemy.engine import CursorResult
from sqlmodel import Session, col, select

from app.config import Settings
from app.db import get_session
from app.models import LoginSessionRow, UserRow

COOKIE_NAME = "tp_session"
_hasher = PasswordHasher()
# Verified against when the email is unknown, so timing does not reveal which emails exist.
_DUMMY_HASH = _hasher.hash("not-a-real-password")


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str | None, password: str) -> bool:
    try:
        return _hasher.verify(password_hash or _DUMMY_HASH, password) and password_hash is not None
    except (VerificationError, InvalidHashError):
        return False


def _hash_cookie(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def authenticate(session: Session, email: str, password: str) -> UserRow | None:
    user = session.exec(select(UserRow).where(UserRow.email == email.strip().lower())).first()
    ok = verify_password(user.password_hash if user else None, password)
    return user if ok else None


def start_session(session: Session, user: UserRow, settings: Settings, response: Response) -> None:
    """Create the server-side session and set the cookie. Caller commits."""
    value = secrets.token_urlsafe(32)
    ttl = timedelta(hours=settings.session_ttl_hours)
    session.add(
        LoginSessionRow(
            token_hash=_hash_cookie(value), user_id=user.id, expires_at=datetime.now(UTC) + ttl
        )
    )
    response.set_cookie(
        COOKIE_NAME, value, max_age=int(ttl.total_seconds()), httponly=True, samesite="lax",
        secure=settings.cookie_secure, path="/",
    )


def end_session(session: Session, request: Request, settings: Settings, response: Response) -> None:
    value = request.cookies.get(COOKIE_NAME)
    if value:
        row = session.get(LoginSessionRow, _hash_cookie(value))
        if row is not None:
            session.delete(row)
    response.delete_cookie(
        COOKIE_NAME, httponly=True, samesite="lax", secure=settings.cookie_secure, path="/"
    )


def purge_expired_sessions(session: Session) -> int:
    """Delete every session past its expiry. Login calls this; the worker (M3) will do it on a
    timer. Caller commits."""
    result = cast(
        CursorResult[Any],
        session.execute(
            delete(LoginSessionRow).where(col(LoginSessionRow.expires_at) < datetime.now(UTC))
        ),
    )
    return result.rowcount or 0


def current_user(
    request: Request, session: Annotated[Session, Depends(get_session)]
) -> UserRow:
    value = request.cookies.get(COOKIE_NAME)
    row = session.get(LoginSessionRow, _hash_cookie(value)) if value else None
    if row is not None:
        expires = row.expires_at if row.expires_at.tzinfo else row.expires_at.replace(tzinfo=UTC)
        if expires > datetime.now(UTC):
            user = session.get(UserRow, row.user_id)
            if user is not None:
                return user
    raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not signed in")


def make_session_for_tests(session: Session, user_id: str) -> str:
    """Create a session row directly and return the cookie value (tests skip the login limiter)."""
    value = secrets.token_urlsafe(32)
    session.add(
        LoginSessionRow(
            token_hash=_hash_cookie(value), user_id=user_id,
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
    )
    session.commit()
    return value
