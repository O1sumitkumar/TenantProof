from fastapi import APIRouter, HTTPException, status

from app.deps import SessionDep
from app.models import CaseRow, OrgRow
from app.schemas import IntakeView
from app.services.intake_token import find_active
from app.services.mappers import to_intake_view

router = APIRouter()


def _not_found() -> HTTPException:
    # Same answer for unknown, revoked and expired links: nothing to probe.
    return HTTPException(status.HTTP_404_NOT_FOUND, "Link not found")


@router.get("/intake/{token}", response_model=IntakeView)
def get_intake(token: str, session: SessionDep) -> IntakeView:
    row = find_active(session, token)
    case = session.get(CaseRow, row.case_id) if row else None
    if case is None:
        raise _not_found()
    org = session.get(OrgRow, case.org_id)
    assert org is not None
    return to_intake_view(session, case, org.name)
