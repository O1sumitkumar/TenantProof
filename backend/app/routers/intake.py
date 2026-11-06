import hmac
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import select

from app.config import Settings, get_settings
from app.deps import SessionDep
from app.models import CaseRow, OrgRow
from app.schemas import IntakeView
from app.services.intake_token import hash_token
from app.services.mappers import intake_token, to_intake_view

router = APIRouter()


def _not_found() -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, "Link not found")


@router.get("/intake/{token}", response_model=IntakeView)
def get_intake(
    token: str, session: SessionDep, settings: Annotated[Settings, Depends(get_settings)]
) -> IntakeView:
    case = session.exec(
        select(CaseRow).where(CaseRow.intake_token_hash == hash_token(token))
    ).first()
    if case is None:
        raise _not_found()
    if not hmac.compare_digest(token, intake_token(case, settings)):
        raise _not_found()
    expires = case.intake_expires_at
    if expires is not None:
        expires = expires if expires.tzinfo else expires.replace(tzinfo=UTC)
        if expires < datetime.now(UTC):
            raise _not_found()
    org = session.get(OrgRow, case.org_id)
    assert org is not None
    return to_intake_view(session, case, org.name)
