from fastapi import APIRouter, HTTPException, status
from sqlmodel import col, select

from app.deps import CaseDep, SessionDep, UserDep, load_owned
from app.models import RunRow
from app.schemas import Run
from app.services.mappers import to_run

router = APIRouter()


@router.get("/cases/{case_id}/runs/latest", response_model=Run)
def latest_run(case: CaseDep, session: SessionDep) -> Run:
    row = session.exec(
        select(RunRow).where(RunRow.case_id == case.id).order_by(col(RunRow.started_at).desc())
    ).first()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No runs")
    return to_run(row)


@router.get("/runs/{run_id}", response_model=Run)
def get_run(run_id: str, session: SessionDep, user: UserDep) -> Run:
    return to_run(load_owned(RunRow, run_id, session, user))
