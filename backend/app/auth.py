"""Auth. M0: a fixed dev caseworker (settings.dev_stub_auth). M1 replaces this with
argon2 login and an httpOnly session cookie (CONTRACT_CHANGES #10)."""

from typing import Annotated

from fastapi import Depends, HTTPException, status
from sqlmodel import Session, select

from app.config import Settings, get_settings
from app.db import get_session
from app.models import UserRow


def current_user(
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> UserRow:
    if not settings.dev_stub_auth:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not signed in")
    user = session.exec(select(UserRow).where(UserRow.email == settings.dev_user_email)).first()
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Dev user not seeded")
    return user
