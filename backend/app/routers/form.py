from fastapi import APIRouter

from app.deps import CaseDep, SessionDep
from app.schemas import FormDraft
from app.services.mappers import build_form_draft

router = APIRouter()


@router.get("/cases/{case_id}/form-draft", response_model=FormDraft)
def get_form_draft(case: CaseDep, session: SessionDep) -> FormDraft:
    return build_form_draft(session, case)
