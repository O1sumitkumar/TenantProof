"""API response/request shapes. Mirrors API_CONTRACT.md (v0.2) field for field,
plus the changes logged in CONTRACT_CHANGES.md."""

from typing import Literal

from pydantic import BaseModel

Language = str


class Org(BaseModel):
    id: str
    name: str


class User(BaseModel):
    id: str
    name: str
    role: Literal["caseworker"]
    org: Org


class Deadline(BaseModel):
    date: str
    label: str


class CaseSummary(BaseModel):
    id: str
    tenant_name: str
    title: str
    unit: str
    dispute_type: Literal["maintenance"]
    stage: Literal["waiting_tenant", "needs_review", "ready_to_file", "hearing_scheduled"]
    next_deadline: Deadline | None
    open_blocking: int
    pending_review: int
    tenant_language: Language
    priority: Literal["high", "normal"]
    priority_reason: str
    updated_at: str
    has_demo_data: bool | None = None


class AssignedTo(BaseModel):
    id: str
    name: str


class TenantInfo(BaseModel):
    name: str
    preferred_language: Language


class Intake(BaseModel):
    url: str
    status: Literal["not_sent", "sent", "files_received"]
    sent_at: str | None
    last_upload_at: str | None
    tenant_attested_genuine: bool
    tenant_attested_at: str | None


class Case(BaseModel):
    id: str
    dispute_type: Literal["maintenance"]
    title: str
    unit: str
    assigned_to: AssignedTo
    tenant: TenantInfo
    intake: Intake
    created_at: str
    synthetic: bool


class IntakeRequest(BaseModel):
    id: str
    message: str


class IntakeView(BaseModel):
    org_name: str
    tenant_first_name: str
    unit: str
    language: Language
    requests: list[IntakeRequest]


class FormatCheck(BaseModel):
    accepted: bool
    action: Literal["none", "converted", "will_export_pdf", "rejected"]
    note: str


class EvidenceMetadata(BaseModel):
    captured_at: str | None
    gps_present: bool
    device: str | None
    software: str | None


class EvidenceItem(BaseModel):
    id: str
    label: str
    filename: str
    kind: Literal["lease", "photo", "messages", "receipt", "letter", "other"]
    mime: str
    size_bytes: int
    sha256: str
    received_at: str
    uploaded_by: Literal["tenant", "caseworker"]
    format_check: FormatCheck
    metadata: EvidenceMetadata
    metadata_stripped_for_ai: bool
    processing: Literal["queued", "processing", "done", "failed"]
    error: str | None


class ToolCall(BaseModel):
    tool: str
    input: str
    output: str


class RunStep(BaseModel):
    key: Literal["ingest", "extract", "timeline", "rules", "gaps", "draft"]
    label: str
    status: Literal["pending", "running", "done", "failed", "needs_input"]
    summary: str | None
    tool_calls: list[ToolCall]


class RunUsage(BaseModel):
    input_tokens: int
    output_tokens: int
    est_cost_usd: float
    duration_ms: int


class Run(BaseModel):
    id: str
    case_id: str
    status: Literal["running", "needs_review", "done", "failed"]
    started_at: str
    finished_at: str | None
    steps: list[RunStep]
    stale: bool = False  # CONTRACT_CHANGES #3
    usage: RunUsage | None = None  # CONTRACT_CHANGES #5


class SourceRef(BaseModel):
    evidence_id: str
    locator: str
    excerpt: str | None


class EventDate(BaseModel):
    value: str | None
    precision: Literal["day", "month", "unknown"]
    basis: Literal["exif", "message_timestamp", "document_text", "filename", "user"]


class EventFlag(BaseModel):
    type: Literal["no_metadata", "edited_software", "date_inferred", "date_mismatch"]
    message: str


class TimelineEvent(BaseModel):
    id: str
    date: EventDate
    title: str
    description: str
    actor: Literal["tenant", "landlord", "other"]
    sources: list[SourceRef]
    strength: Literal["corroborated", "single_source", "needs_support"]
    strength_reasons: list[str]
    flags: list[EventFlag]
    review_status: Literal["pending", "accepted", "edited", "rejected"]
    caseworker_note: str | None
    reviewed_by: str | None


class GapInputText(BaseModel):
    type: Literal["text"]
    field_key: str
    placeholder: str


class GapInputChoice(BaseModel):
    type: Literal["choice"]
    field_key: str
    options: list[str]


class TenantRequest(BaseModel):
    language: Language
    message: str
    message_en: str


class Gap(BaseModel):
    id: str
    severity: Literal["blocking", "recommended"]
    title: str
    why: str
    how_to_fix: str
    source_id: str | None
    input: GapInputText | GapInputChoice | None
    tenant_request: TenantRequest | None
    status: Literal["open", "waiting_tenant", "resolved", "dismissed"]
    resolution_note: str | None


class LegalSource(BaseModel):
    id: str
    title: str
    kind: Literal["statute", "policy", "form"]
    url: str | None
    last_verified_at: str | None
    verify_status: Literal["unchanged", "changed", "unreachable", "unverified"]
    used_for: str


class FormField(BaseModel):
    key: str
    label: str
    value: str | None
    required: bool
    status: Literal["auto_filled", "needs_confirmation", "missing", "user_entered"]
    sources: list[SourceRef]
    note: str | None = None


class Narrative(BaseModel):
    text: str
    event_ids: list[str]


class FormDraft(BaseModel):
    form_name: str
    disclaimer: str
    fields: list[FormField]
    narrative: Narrative


class ActivityEntry(BaseModel):
    at: str
    actor: Literal["agent", "tenant", "caseworker"]
    actor_name: str
    action: str


class Attestations(BaseModel):
    reviewed_fields: bool
    remedy_confirmed_with_tenant: bool
    explained_not_legal_advice: bool


class PackageFile(BaseModel):
    label: str
    filename: str
    sha256: str
    note: str


class Package(BaseModel):
    built_at: str
    prepared_by: str
    files: list[PackageFile]
    reminders: list[str]


class ErrorReasons(BaseModel):
    reasons: list[str]  # CONTRACT_CHANGES #8: 409/422 body is {detail: {reasons: [...]}}
