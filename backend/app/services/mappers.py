"""Row -> contract-shape mappers. Keeps routers thin and shapes in one place."""

from datetime import UTC, date, datetime

from sqlmodel import Session, col, select

from app.models import (
    ActivityRow,
    CaseRow,
    EvidenceRow,
    FormFieldRow,
    GapRow,
    LegalSourceRow,
    RunRow,
    TimelineEventRow,
)
from app.schemas import (
    ActivityEntry,
    Case,
    CaseSummary,
    EvidenceItem,
    FormDraft,
    FormField,
    Gap,
    Intake,
    IntakeRequest,
    IntakeView,
    LegalSource,
    Run,
    TimelineEvent,
)
from app.services.narrative import build_narrative
from app.services.priority import PriorityInput, compute_priority, sort_key

OPEN_GAP = ("open", "waiting_tenant")


def iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    return (dt if dt.tzinfo else dt.replace(tzinfo=UTC)).isoformat()


def iso_req(dt: datetime) -> str:
    return iso(dt) or ""


def to_intake(case: CaseRow, url: str | None = None) -> Intake:
    return Intake.model_validate(
        {
            "url": url,
            "status": case.intake_status,
            "sent_at": iso(case.intake_sent_at),
            "last_upload_at": iso(case.intake_last_upload_at),
            "tenant_attested_genuine": case.tenant_attested_genuine,
            "tenant_attested_at": iso(case.tenant_attested_at),
        }
    )


def case_counts(session: Session, case_id: str) -> tuple[int, int]:
    gaps = session.exec(select(GapRow).where(GapRow.case_id == case_id)).all()
    blocking = sum(1 for g in gaps if g.severity == "blocking" and g.status in OPEN_GAP)
    pending = len(
        session.exec(
            select(TimelineEventRow).where(
                TimelineEventRow.case_id == case_id, TimelineEventRow.review_status == "pending"
            )
        ).all()
    )
    return blocking, pending


def to_summary(
    session: Session, case: CaseRow, today: date
) -> tuple[CaseSummary, tuple[int, int, int, int]]:
    blocking, pending = case_counts(session, case.id)
    deadline = case.next_deadline
    result = compute_priority(
        PriorityInput(
            stage=case.stage,
            next_deadline_date=date.fromisoformat(deadline["date"]) if deadline else None,
            open_blocking=blocking,
            pending_review=pending,
        ),
        today,
    )
    last = session.exec(
        select(ActivityRow)
        .where(ActivityRow.case_id == case.id)
        .order_by(col(ActivityRow.at).desc())
    ).first()
    summary = CaseSummary.model_validate(
        {
            "id": case.id,
            "tenant_name": case.tenant_name,
            "title": case.title,
            "unit": case.unit,
            "dispute_type": case.dispute_type,
            "stage": case.stage,
            "next_deadline": deadline,
            "open_blocking": blocking,
            "pending_review": pending,
            "tenant_language": case.tenant_language,
            "priority": result.priority,
            "priority_reason": result.reason,
            "updated_at": iso_req(last.at if last else case.updated_at),
            "has_demo_data": case.has_demo_data,
        }
    )
    return summary, sort_key(result.priority, result.days_to_deadline, blocking, pending)


def to_case(case: CaseRow, assignee_name: str) -> Case:
    return Case.model_validate(
        {
            "id": case.id,
            "dispute_type": case.dispute_type,
            "title": case.title,
            "unit": case.unit,
            "assigned_to": {"id": case.assigned_to_id, "name": assignee_name},
            "tenant": {"name": case.tenant_name, "preferred_language": case.tenant_language},
            "intake": to_intake(case).model_dump(),
            "created_at": iso_req(case.created_at),
            "synthetic": case.synthetic,
        }
    )


def to_evidence(row: EvidenceRow) -> EvidenceItem:
    return EvidenceItem.model_validate(
        {
            "id": row.id,
            "label": row.label,
            "filename": row.filename,
            "kind": row.kind,
            "mime": row.mime,
            "size_bytes": row.size_bytes,
            "sha256": row.sha256,
            "received_at": iso_req(row.received_at),
            "uploaded_by": row.uploaded_by,
            "format_check": row.format_check,
            "metadata": row.metadata_,
            "metadata_stripped_for_ai": row.metadata_stripped_for_ai,
            "processing": row.processing,
            "error": row.error,
        }
    )


def to_run(row: RunRow) -> Run:
    return Run.model_validate(
        {
            "id": row.id,
            "case_id": row.case_id,
            "status": row.status,
            "started_at": iso_req(row.started_at),
            "finished_at": iso(row.finished_at),
            "steps": row.steps,
            "stale": row.stale,
            "usage": row.usage,
        }
    )


def to_event(row: TimelineEventRow) -> TimelineEvent:
    return TimelineEvent.model_validate(
        {
            "id": row.id,
            "date": row.date,
            "title": row.title,
            "description": row.description,
            "actor": row.actor,
            "sources": row.sources,
            "strength": row.strength,
            "strength_reasons": row.strength_reasons,
            "flags": row.flags,
            "review_status": row.review_status,
            "caseworker_note": row.caseworker_note,
            "reviewed_by": row.reviewed_by,
        }
    )


def to_gap(row: GapRow) -> Gap:
    return Gap.model_validate(
        {
            "id": row.id,
            "severity": row.severity,
            "title": row.title,
            "why": row.why,
            "how_to_fix": row.how_to_fix,
            "source_id": row.source_id,
            "input": row.input,
            "tenant_request": row.tenant_request,
            "status": row.status,
            "resolution_note": row.resolution_note,
        }
    )


def to_source(row: LegalSourceRow) -> LegalSource:
    return LegalSource.model_validate(
        {
            "id": row.id,
            "title": row.title,
            "kind": row.kind,
            "url": row.url,
            "last_verified_at": iso(row.last_verified_at),
            "verify_status": row.verify_status,
            "used_for": row.used_for,
        }
    )


def to_field(row: FormFieldRow) -> FormField:
    return FormField.model_validate(
        {
            "key": row.key,
            "label": row.label,
            "value": row.value,
            "required": row.required,
            "status": row.status,
            "sources": row.sources,
            "note": row.note,
        }
    )


def to_activity(row: ActivityRow) -> ActivityEntry:
    return ActivityEntry.model_validate(
        {
            "at": iso_req(row.at),
            "actor": row.actor,
            "actor_name": row.actor_name,
            "action": row.action,
        }
    )


def build_form_draft(session: Session, case: CaseRow) -> FormDraft:
    fields = session.exec(
        select(FormFieldRow)
        .where(FormFieldRow.case_id == case.id)
        .order_by(col(FormFieldRow.position))
    ).all()
    events = session.exec(
        select(TimelineEventRow)
        .where(TimelineEventRow.case_id == case.id)
        .order_by(TimelineEventRow.sort_key)
    ).all()
    labels = {
        e.id: e.label
        for e in session.exec(select(EvidenceRow).where(EvidenceRow.case_id == case.id)).all()
    }
    narrative = build_narrative(
        [
            {
                "id": e.id,
                "date": e.date,
                "description": e.description,
                "sources": e.sources,
                "review_status": e.review_status,
            }
            for e in events
        ],
        labels,
    )
    return FormDraft.model_validate(
        {
            "form_name": case.form_name,
            "disclaimer": case.form_disclaimer,
            "fields": [to_field(f).model_dump() for f in fields],
            "narrative": narrative,
        }
    )


def to_intake_view(session: Session, case: CaseRow, org_name: str) -> IntakeView:
    gaps = session.exec(
        select(GapRow).where(GapRow.case_id == case.id, GapRow.status == "waiting_tenant")
    ).all()
    return IntakeView(
        org_name=org_name,
        tenant_first_name=case.tenant_name.split(" ")[0],
        unit=case.unit,
        language=case.tenant_language,
        requests=[
            IntakeRequest(id=g.id, message=g.tenant_request["message"])
            for g in gaps
            if g.tenant_request
        ],
    )
