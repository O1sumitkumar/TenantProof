from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlmodel import select

from app.config import Settings, get_settings
from app.deps import CaseDep, SessionDep, UserDep
from app.models import CaseRow, UserRow
from app.schemas import Case, CaseSummary
from app.services.mappers import to_case, to_summary

router = APIRouter()


@router.get("/cases", response_model=list[CaseSummary])
def list_cases(session: SessionDep, user: UserDep) -> list[CaseSummary]:
    cases = session.exec(select(CaseRow).where(CaseRow.org_id == user.org_id)).all()
    today = date.today()
    ranked = [to_summary(session, c, today) for c in cases]
    ranked.sort(key=lambda pair: pair[1])
    return [summary for summary, _ in ranked]


@router.get("/cases/{case_id}", response_model=Case)
def get_case(
    case: CaseDep, session: SessionDep, settings: Annotated[Settings, Depends(get_settings)]
) -> Case:
    assignee = session.get(UserRow, case.assigned_to_id)
    return to_case(case, assignee.name if assignee else "", settings)
