from fastapi import APIRouter, File, HTTPException, Request, UploadFile, status

from app.deps import SessionDep
from app.models import CaseRow, OrgRow
from app.ratelimit import limiter, submit_limit
from app.schemas import IntakeFilesReceived, IntakeSubmit, IntakeView, Ok
from app.services import review
from app.services.evidence.http import read_uploads, upload_limit
from app.services.evidence.ingest import ingest
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


@router.post("/intake/{token}/submit", response_model=Ok)
@limiter.limit(submit_limit)
def submit_intake(request: Request, token: str, body: IntakeSubmit, session: SessionDep) -> Ok:
    row = find_active(session, token)
    case = session.get(CaseRow, row.case_id) if row else None
    if case is None:
        raise _not_found()
    missing = [
        text
        for ok, text in (
            (body.attest_genuine, "Confirm the files are genuine"),
            (body.consent_share, "Agree to share the files"),
        )
        if not ok
    ]
    if missing:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, {"reasons": missing})
    review.record_tenant_submit(session, case)
    session.commit()
    return Ok()


@router.post("/intake/{token}/files", response_model=IntakeFilesReceived)
@limiter.limit(upload_limit)
def upload_intake_files(
    request: Request, token: str, session: SessionDep,
    file: list[UploadFile] = File(...),  # noqa: B008 (FastAPI's declaration style)
) -> IntakeFilesReceived:
    """Tenant upload through the intake link. Field `file`, repeatable."""
    row = find_active(session, token)
    case = session.get(CaseRow, row.case_id) if row else None
    if case is None:
        raise _not_found()
    uploads = read_uploads(file)
    rows = ingest(session, case, uploads, "tenant", case.tenant_name)
    session.commit()
    return IntakeFilesReceived(received=len(rows))
