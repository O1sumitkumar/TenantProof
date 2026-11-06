from fastapi import APIRouter
from sqlmodel import select

from app.deps import CaseDep, SessionDep
from app.models import TimelineEventRow
from app.schemas import TimelineEvent
from app.services.mappers import to_event

router = APIRouter()


@router.get("/cases/{case_id}/timeline", response_model=list[TimelineEvent])
def list_timeline(case: CaseDep, session: SessionDep) -> list[TimelineEvent]:
    rows = session.exec(
        select(TimelineEventRow)
        .where(TimelineEventRow.case_id == case.id)
        .order_by(TimelineEventRow.sort_key)
    ).all()
    return [to_event(r) for r in rows]
