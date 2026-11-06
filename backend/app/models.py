# pyright: reportAssignmentType=false
# (SQLModel declares __tablename__ as declared_attr; plain strings are the documented usage.)
"""SQLModel tables. Nested contract shapes are stored as JSON columns; the
routers validate them through the Pydantic models in schemas.py."""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    return datetime.now(UTC)


class OrgRow(SQLModel, table=True):
    __tablename__ = "org"
    id: str = Field(primary_key=True)
    name: str


class UserRow(SQLModel, table=True):
    __tablename__ = "app_user"
    id: str = Field(primary_key=True)
    org_id: str = Field(foreign_key="org.id", index=True)
    name: str
    email: str = Field(unique=True, index=True)
    role: str = "caseworker"
    password_hash: str | None = None  # M1


class CaseRow(SQLModel, table=True):
    __tablename__ = "tenant_case"
    id: str = Field(primary_key=True)
    org_id: str = Field(foreign_key="org.id", index=True)
    assigned_to_id: str = Field(foreign_key="app_user.id")
    dispute_type: str = "maintenance"
    title: str
    unit: str
    tenant_name: str
    tenant_language: str
    stage: str
    hearing_date: str | None = None  # ISO date; drives deadline + priority
    next_deadline: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON))
    synthetic: bool = True
    has_demo_data: bool = False
    form_name: str = ""
    form_disclaimer: str = ""
    intake_status: str = "not_sent"
    intake_sent_at: datetime | None = None
    intake_last_upload_at: datetime | None = None
    tenant_attested_genuine: bool = False
    tenant_attested_at: datetime | None = None
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class IntakeTokenRow(SQLModel, table=True):
    """Only sha256(token) is stored; the raw token is shown once, in the POST response.
    Re-sending the link revokes every earlier token for the case."""

    __tablename__ = "intake_token"
    token_hash: str = Field(primary_key=True)
    case_id: str = Field(foreign_key="tenant_case.id", index=True)
    created_at: datetime = Field(default_factory=utcnow)
    expires_at: datetime
    revoked: bool = False


class EvidenceRow(SQLModel, table=True):
    __tablename__ = "evidence"
    id: str = Field(primary_key=True)
    case_id: str = Field(foreign_key="tenant_case.id", index=True)
    position: int = 0
    label: str
    filename: str
    kind: str
    mime: str
    size_bytes: int
    sha256: str
    received_at: datetime
    uploaded_by: str
    format_check: dict[str, Any] = Field(sa_column=Column(JSON))
    metadata_: dict[str, Any] = Field(sa_column=Column("metadata", JSON))
    metadata_stripped_for_ai: bool = False
    processing: str = "done"
    error: str | None = None


class RunRow(SQLModel, table=True):
    __tablename__ = "run"
    id: str = Field(primary_key=True)
    case_id: str = Field(foreign_key="tenant_case.id", index=True)
    status: str
    started_at: datetime
    finished_at: datetime | None = None
    steps: list[dict[str, Any]] = Field(default_factory=list, sa_column=Column(JSON))
    stale: bool = False
    usage: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON))


class TimelineEventRow(SQLModel, table=True):
    __tablename__ = "timeline_event"
    id: str = Field(primary_key=True)
    case_id: str = Field(foreign_key="tenant_case.id", index=True)
    date: dict[str, Any] = Field(sa_column=Column(JSON))
    sort_key: str = ""  # derived from date.value; "9" sorts unknown dates last
    title: str
    description: str
    actor: str
    sources: list[dict[str, Any]] = Field(default_factory=list, sa_column=Column(JSON))
    strength: str
    strength_reasons: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    flags: list[dict[str, Any]] = Field(default_factory=list, sa_column=Column(JSON))
    review_status: str = "pending"
    caseworker_note: str | None = None
    reviewed_by: str | None = None


class GapRow(SQLModel, table=True):
    __tablename__ = "gap"
    id: str = Field(primary_key=True)
    case_id: str = Field(foreign_key="tenant_case.id", index=True)
    position: int = 0
    severity: str
    title: str
    why: str
    how_to_fix: str
    source_id: str | None = None
    input: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON))
    tenant_request: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON))
    status: str = "open"
    resolution_note: str | None = None


class LegalSourceRow(SQLModel, table=True):
    __tablename__ = "legal_source"
    id: str = Field(primary_key=True)
    case_id: str = Field(foreign_key="tenant_case.id", index=True)
    position: int = 0
    title: str
    kind: str
    url: str | None = None
    last_verified_at: datetime | None = None
    verify_status: str = "unverified"
    used_for: str = ""


class FormFieldRow(SQLModel, table=True):
    __tablename__ = "form_field"
    case_id: str = Field(foreign_key="tenant_case.id", primary_key=True)
    key: str = Field(primary_key=True)
    position: int = 0
    label: str
    value: str | None = None
    required: bool = True
    status: str = "missing"
    sources: list[dict[str, Any]] = Field(default_factory=list, sa_column=Column(JSON))
    note: str | None = None


class ActivityRow(SQLModel, table=True):
    __tablename__ = "activity"
    id: int | None = Field(default=None, primary_key=True)
    case_id: str = Field(foreign_key="tenant_case.id", index=True)
    at: datetime
    actor: str
    actor_name: str
    action: str
