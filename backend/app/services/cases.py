"""Creating a case (POST /cases, issue #41, CONTRACT_CHANGES #35).

A new case starts where the live-demo case starts: no evidence, no run, the intake link not sent
yet. The org and the assignee are the signed-in caseworker's; nothing in the body can choose them.
"""

import uuid

from sqlmodel import Session

from app.models import CaseRow, UserRow
from app.schemas import CaseCreate
from app.services import activity
from app.services.agent.tools import clean_text

FORM_NAME = "Application to Director (Form J) — draft"
FORM_DISCLAIMER = (
    "Prepared with the tenant to help fill in the official form. It is information, not legal "
    "advice, and is not submitted anywhere."
)
# The CaseCreate limits, applied again after cleaning: escaping "<" can make text longer, and the
# stored value is cut to the limit.
LIMITS = {"tenant_name": 120, "unit": 200, "title": 120}


LABELS = {
    "tenant_name": "Tenant name",
    "tenant_language": "Preferred language",
    "unit": "Unit address",
    "title": "What is wrong",
}


def cleaned(body: CaseCreate) -> dict[str, str]:
    """The typed text, cleaned like any text a model reads later (the title and the tenant name go
    into the agent's prompts and the filing package): no control characters, no "<"."""
    return {key: clean_text(getattr(body, key), limit) for key, limit in LIMITS.items()}


def blank_after_cleaning(text: dict[str, str]) -> list[str]:
    """Reasons for fields that held only control characters: blank once cleaned."""
    return [f"{LABELS[key]}: enter some text" for key, value in text.items() if not value]


def create_case(session: Session, user: UserRow, body: CaseCreate) -> CaseRow:
    """The new case, in the user's org and assigned to them. Caller checks
    `blank_after_cleaning` first, and commits."""
    text = cleaned(body)
    case = CaseRow(
        id=f"case_{uuid.uuid4().hex[:10]}",
        org_id=user.org_id,
        assigned_to_id=user.id,
        dispute_type="maintenance",
        title=text["title"],
        unit=text["unit"],
        tenant_name=text["tenant_name"],
        tenant_language=body.tenant_language,
        stage="waiting_tenant",
        synthetic=True,  # every case in this prototype is synthetic demo data
        has_demo_data=True,  # it has a case view: the caseload opens it like the live-demo case
        form_name=FORM_NAME,
        form_disclaimer=FORM_DISCLAIMER,
        intake_status="not_sent",
    )
    session.add(case)
    session.flush()  # the activity row's foreign key needs the case row first
    activity.log(session, case.id, "caseworker", user.name, "Created the case")
    return case
