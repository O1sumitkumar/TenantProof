from fastapi import APIRouter, File, Request, UploadFile
from sqlmodel import col, select

from app.deps import CaseDep, SessionDep, UserDep
from app.models import EvidenceRow
from app.ratelimit import limiter
from app.schemas import EvidenceItem
from app.services.evidence.http import read_uploads, upload_limit
from app.services.evidence.ingest import ingest
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


@router.post("/cases/{case_id}/evidence", response_model=list[EvidenceItem])
@limiter.limit(upload_limit)
def upload_evidence(
    request: Request, case: CaseDep, session: SessionDep, user: UserDep,
    file: list[UploadFile] = File(...),  # noqa: B008 (FastAPI's declaration style)
) -> list[EvidenceItem]:
    """Caseworker upload. Field `file`, repeatable (the UI sends every picked file at once)."""
    uploads = read_uploads(file)
    rows = ingest(session, case, uploads, "caseworker", user.name)
    session.commit()
    return [to_evidence(r) for r in rows]
