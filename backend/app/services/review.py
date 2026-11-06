"""Caseworker mutations: timeline events, gaps, form fields, tenant requests, tenant submit.
Every function logs activity and refreshes the stage; the router commits."""

from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlmodel import Session, select

from app.models import CaseRow, FormFieldRow, GapRow, TimelineEventRow, UserRow
from app.schemas import FieldPatch, GapPatch, TimelineEventPatch
from app.services import activity
from app.services.stage import refresh_stage

OPEN = ("open", "waiting_tenant")
CONTENT_FIELDS = ("title", "description", "date")
VERB = {"accepted": "Accepted", "edited": "Edited", "rejected": "Rejected", "pending": "Reset"}


def _bad(detail: str) -> HTTPException:
    return HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail)


def _date_changed(event: TimelineEventRow, patch: TimelineEventPatch) -> bool:
    """The UI resends the unchanged date on every edit; only a real change becomes basis=user."""
    assert patch.date is not None
    return (event.date.get("value"), event.date.get("precision")) != (
        patch.date.value, patch.date.precision)


def patch_event(
    session: Session, case: CaseRow, event: TimelineEventRow, patch: TimelineEventPatch,
    user: UserRow,
) -> TimelineEventRow:
    sent = patch.model_fields_set
    for key in ("title", "description"):
        if key in sent and not (getattr(patch, key) or "").strip():
            raise _bad(f"{key} cannot be empty")
    edited = False
    if "title" in sent and patch.title is not None and patch.title.strip() != event.title:
        event.title, edited = patch.title.strip(), True
    if (
        "description" in sent and patch.description is not None
        and patch.description.strip() != event.description
    ):
        event.description, edited = patch.description.strip(), True
    if "date" in sent and patch.date is not None and _date_changed(event, patch):
        event.date = {**patch.date.model_dump(), "basis": "user"}
        event.sort_key = patch.date.value or "9"
        edited = True
    if "caseworker_note" in sent:
        event.caseworker_note = (patch.caseworker_note or "").strip() or None
    new_status = patch.review_status if "review_status" in sent else None
    if new_status is None and edited and event.review_status != "rejected":
        new_status = "edited"  # a rejected event needs an explicit review_status to come back
    if new_status is not None:
        event.review_status = new_status
        event.reviewed_by = None if new_status == "pending" else user.name
    session.add(event)
    verb = VERB.get(new_status or "", "Noted on")
    activity.log(session, case.id, "caseworker", user.name, f"{verb} timeline event: {event.title}")
    refresh_stage(session, case)
    return event


def _field_for_gap(session: Session, gap: GapRow) -> FormFieldRow | None:
    key = (gap.input or {}).get("field_key")
    return session.get(FormFieldRow, (gap.case_id, key)) if key else None


def patch_gap(
    session: Session, case: CaseRow, gap: GapRow, patch: GapPatch, user: UserRow
) -> GapRow:
    was_resolved = gap.status == "resolved"
    if patch.value is not None:
        field = _field_for_gap(session, gap)
        if field is None:
            raise _bad("This item has no form field to fill")
        if patch.status != "resolved":
            raise _bad("A value can only be saved when the item is resolved")
        value = patch.value.strip()
        if not value:
            raise _bad("value cannot be empty")
        field.value, field.status = value, "user_entered"
        session.add(field)
    elif patch.status in OPEN and was_resolved:
        field = _field_for_gap(session, gap)
        if field is not None and field.status == "user_entered":
            field.value, field.status = None, "missing"  # reopen clears what this gap wrote
            session.add(field)
    gap.status = patch.status
    if "resolution_note" in patch.model_fields_set:
        gap.resolution_note = patch.resolution_note
    elif patch.status in OPEN:
        gap.resolution_note = None
    session.add(gap)
    label = {"resolved": "Resolved", "dismissed": "Dismissed", "open": "Reopened",
             "waiting_tenant": "Marked waiting on tenant"}[patch.status]
    activity.log(session, case.id, "caseworker", user.name, f"{label} item: {gap.title}")
    refresh_stage(session, case)
    return gap


def request_from_tenant(session: Session, case: CaseRow, gap: GapRow, user: UserRow) -> GapRow:
    if gap.tenant_request is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "No drafted message for this item")
    if gap.status not in OPEN:
        raise HTTPException(status.HTTP_409_CONFLICT, "This item is already closed")
    gap.status = "waiting_tenant"
    session.add(gap)
    activity.log(session, case.id, "caseworker", user.name,
                 f"Sent a request to the tenant: {gap.title}")
    refresh_stage(session, case, waiting_on_tenant=True)
    return gap


def patch_field(
    session: Session, case: CaseRow, key: str, patch: FieldPatch, user: UserRow
) -> FormFieldRow:
    field = session.get(FormFieldRow, (case.id, key))
    if field is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Field not found")
    value = patch.value.strip()
    field.value = value or None
    field.status = "user_entered" if value else "missing"
    session.add(field)
    for gap in session.exec(select(GapRow).where(GapRow.case_id == case.id)).all():
        if (gap.input or {}).get("field_key") != key:
            continue
        if value and gap.status in OPEN:
            gap.status, gap.resolution_note = "resolved", f"Saved: {value}"
            session.add(gap)
        elif not value and gap.status == "resolved":
            gap.status, gap.resolution_note = "open", None  # field emptied: the item is open again
            session.add(gap)
    activity.log(session, case.id, "caseworker", user.name, f"Edited form field: {field.label}")
    refresh_stage(session, case)
    return field


def record_tenant_submit(session: Session, case: CaseRow) -> None:
    """Tenant ticked both boxes on the intake page. Attestation only (files arrive in M2)."""
    case.tenant_attested_genuine = True
    case.tenant_attested_at = datetime.now(UTC)
    activity.log(session, case.id, "tenant", case.tenant_name,
                 "Confirmed the files are genuine and agreed to share them")
    refresh_stage(session, case, waiting_on_tenant=False)
