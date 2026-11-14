import asyncio
import logging
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlmodel import Session, col, select

from app.config import get_settings
from app.db import get_engine
from app.deps import CaseDep, SessionDep, UserDep, load_owned
from app.models import CaseRow, RunRow
from app.schemas import Run
from app.services.agent import llm, runner
from app.services.agent.evidence_text import SqlTextStore
from app.services.mappers import to_run

router = APIRouter()
log = logging.getLogger(__name__)

# A run still "running" after its whole budget (plus slack for a slow start) was cut off by a
# restart or a crash, so it no longer blocks a new one.
STALE_AFTER = timedelta(seconds=llm.RUN_BUDGET_S + 30)


def provider_dep() -> llm.LLMProvider:
    """The model provider for this deployment (`LLM_MODE`). Tests override this dependency."""
    try:
        return llm.get_provider(get_settings())
    except llm.LLMConfigError as exc:
        log.warning("analysis unavailable: %s", exc)  # the message names the env var, not a key
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "Analysis is not set up on this server"
        ) from exc


ProviderDep = Annotated[llm.LLMProvider, Depends(provider_dep)]


def _execute(run_id: str, provider: llm.LLMProvider) -> None:
    """Background task: its own session and event loop, so the API stays responsive. The
    runner records its own failures on the run; this only catches what is left."""
    with Session(get_engine()) as session:
        try:
            row = session.get(RunRow, run_id)
            if row is None:
                return
            asyncio.run(runner.execute_run(session, row, provider, SqlTextStore(session)))
        except Exception as exc:  # never leave the run "running" forever
            session.rollback()
            log.warning("run %s failed to execute: %s", run_id, type(exc).__name__)
            row = session.get(RunRow, run_id)
            if row is not None and row.status == "running":
                row.status = "failed"
                row.finished_at = datetime.now(UTC)
                session.add(row)
                session.commit()


@router.post("/cases/{case_id}/runs", response_model=Run)
def start_run(
    case: CaseDep, session: SessionDep, background: BackgroundTasks, provider: ProviderDep
) -> Run:
    """Starts the analysis and returns at once with `status: "running"`; the UI polls
    `GET /runs/{id}`. The case comes from the path and the caseworker's org, never a body."""
    # Lock the case row so two clicks cannot both pass the "already running" check.
    session.exec(select(CaseRow).where(CaseRow.id == case.id).with_for_update()).one()
    cutoff = datetime.now(UTC) - STALE_AFTER
    active = session.exec(
        select(RunRow).where(
            RunRow.case_id == case.id, RunRow.status == "running", RunRow.started_at > cutoff
        )
    ).first()
    if active is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT, {"reasons": ["An analysis is already running for this case"]}
        )
    row = runner.create_run(session, case)  # logs "Started run_..." and commits
    background.add_task(_execute, row.id, provider)
    return to_run(row)


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
