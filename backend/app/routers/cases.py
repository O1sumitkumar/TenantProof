from datetime import UTC, date, datetime
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlmodel import select

from app.config import Settings, get_settings
from app.deps import CaseDep, SessionDep, UserDep
from app.models import CaseRow, UserRow
from app.schemas import Case, CaseSummary, Intake
from app.services import activity
from app.services.intake_token import issue_token
from app.services.mappers import to_case, to_intake, to_summary

LANG_NAMES = {"en": "English", "zh": "中文", "fr": "Français", "es": "Español", "ar": "العربية"}

router = APIRouter()


@router.get("/cases", response_model=list[CaseSummary])
def list_cases(session: SessionDep, user: UserDep) -> list[CaseSummary]:
    cases = session.exec(select(CaseRow).where(CaseRow.org_id == user.org_id)).all()
    today = date.today()
    ranked = [to_summary(session, c, today) for c in cases]
    ranked.sort(key=lambda pair: pair[1])
    return [summary for summary, _ in ranked]


@router.get("/cases/{case_id}", response_model=Case)
def get_case(case: CaseDep, session: SessionDep) -> Case:
    assignee = session.get(UserRow, case.assigned_to_id)
    return to_case(case, assignee.name if assignee else "")


@router.post("/cases/{case_id}/intake-link", response_model=Intake)
def send_intake_link(
    case: CaseDep,
    session: SessionDep,
    user: UserDep,
    settings: Annotated[Settings, Depends(get_settings)],
) -> Intake:
    """Create (or re-send) the tenant link. The raw URL is returned only here; earlier links
    are revoked. Only a hash is stored."""
    first_send = case.intake_status == "not_sent"
    token = issue_token(session, case.id, settings.intake_token_ttl_days)
    case.intake_sent_at = datetime.now(UTC)
    if first_send:
        case.intake_status = "sent"
    lang = LANG_NAMES.get(case.tenant_language, case.tenant_language)
    verb = "Sent" if first_send else "Re-sent"
    activity.log(session, case.id, "caseworker", user.name, f"{verb} the intake link in {lang}")
    session.add(case)
    session.commit()
    session.refresh(case)
    return to_intake(case, url=f"{settings.public_base_url}/i/{token}")
