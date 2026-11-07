from fastapi import APIRouter
from sqlmodel import col, select

from app.deps import CaseDep, SessionDep
from app.models import EvidenceRow
from app.schemas import EvidenceItem
from app.services.mappers import to_evidence

router = APIRouter()


@router.get("/cases/{case_id}/evidence", response_model=list[EvidenceItem])
def list_evidence(case: CaseDep, session: SessionDep) -> list[EvidenceItem]:
    rows = session.exec(
        select(EvidenceRow)
        .where(EvidenceRow.case_id == case.id)
        .order_by(col(EvidenceRow.position))
    ).all()
    return [to_evidence(r) for r in rows]
