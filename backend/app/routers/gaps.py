from fastapi import APIRouter
from sqlmodel import col, select

from app.deps import CaseDep, SessionDep, UserDep, load_owned
from app.models import CaseRow, GapRow
from app.schemas import Gap, GapPatch
from app.services import review
from app.services.mappers import to_gap

router = APIRouter()


@router.get("/cases/{case_id}/gaps", response_model=list[Gap])
def list_gaps(case: CaseDep, session: SessionDep) -> list[Gap]:
    rows = session.exec(
        select(GapRow).where(GapRow.case_id == case.id).order_by(col(GapRow.position))
    ).all()
    return [to_gap(r) for r in rows]


def _load(gap_id: str, session: SessionDep, user: UserDep) -> tuple[GapRow, CaseRow]:
    gap = load_owned(GapRow, gap_id, session, user)
    case = session.get(CaseRow, gap.case_id)
    assert case is not None
    return gap, case


@router.patch("/gaps/{gap_id}", response_model=Gap)
def patch_gap(gap_id: str, body: GapPatch, session: SessionDep, user: UserDep) -> Gap:
    gap, case = _load(gap_id, session, user)
    review.patch_gap(session, case, gap, body, user)
    session.commit()
    session.refresh(gap)
    return to_gap(gap)


@router.post("/gaps/{gap_id}/tenant-request", response_model=Gap)
def send_tenant_request(gap_id: str, session: SessionDep, user: UserDep) -> Gap:
    gap, case = _load(gap_id, session, user)
    review.request_from_tenant(session, case, gap, user)
    session.commit()
    session.refresh(gap)
    return to_gap(gap)
