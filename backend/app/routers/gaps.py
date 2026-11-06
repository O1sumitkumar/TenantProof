from fastapi import APIRouter
from sqlmodel import col, select

from app.deps import CaseDep, SessionDep
from app.models import GapRow
from app.schemas import Gap
from app.services.mappers import to_gap

router = APIRouter()


@router.get("/cases/{case_id}/gaps", response_model=list[Gap])
def list_gaps(case: CaseDep, session: SessionDep) -> list[Gap]:
    rows = session.exec(
        select(GapRow).where(GapRow.case_id == case.id).order_by(col(GapRow.position))
    ).all()
    return [to_gap(r) for r in rows]
