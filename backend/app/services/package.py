"""Filing package: two PDFs, manifest.json and the original evidence files in a zip, stored
content-addressed. Evidence entries are named from the exhibit label (`evidence/E-01.pdf`),
never from the uploaded filename; a row whose original was never stored (seed data) is listed
in the manifest with `in_zip: null`. The tribunal doesn't take HEIC, and text messages are
filed as PDF, so the zip also carries a JPG made from each HEIC and a PDF made from each TXT
(`rendition` in the manifest), each with its own sha256. The originals stay in the zip.

Every build is a new version (never overwritten). The zip's sha256 goes on the row and in the
activity entry. `caseworker_note` is never read here. Text uses Noto Sans with Noto Sans SC as
fallback so Chinese renders (core PDF fonts cannot encode CJK)."""

import hashlib
import io
import json
import logging
import uuid
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import HTTPException, status
from fpdf import FPDF
from fpdf.enums import WrapMode
from PIL import Image
from sqlmodel import Session, col, select

from app.models import CaseRow, EvidenceRow, FormFieldRow, GapRow, PackageRow, UserRow
from app.schemas import Attestations, Package, PackageFile
from app.services import activity, storage
from app.services.evidence import sniff  # also registers the HEIC opener
from app.services.gating import MissingField, OpenGap, package_blockers
from app.services.mappers import OPEN_GAP, build_form_draft, iso_req

FONT_DIR = Path(__file__).resolve().parent.parent / "assets" / "fonts"
REMINDERS = [
    "Evidence is due 5 days before the hearing (Evidence Policy #42).",
    "This package is prepared information, not legal advice. The tenant files the form themselves.",
    "Nothing has been submitted anywhere. Check every field against the official form.",
]
EVIDENCE_EXT = {"image/jpeg": ".jpg", "image/png": ".png", "image/heic": ".heic",
                "application/pdf": ".pdf", "text/plain": ".txt"}
NOT_STORED = "Original file not in storage (seeded demo rows have none)"
log = logging.getLogger(__name__)
ATTESTATION_LABELS = {
    "reviewed_fields": "Confirm you reviewed every field and the summary",
    "remedy_confirmed_with_tenant": "Confirm the tenant has said what they are asking for",
    "explained_not_legal_advice": "Confirm you told the tenant this is information, not a decision",
}


@dataclass(frozen=True)
class BuiltZip:
    data: bytes
    sha256: str
    files: list[dict[str, str]]


def attestation_reasons(att: Attestations) -> list[str]:
    return [label for key, label in ATTESTATION_LABELS.items() if not getattr(att, key)]


def state_reasons(session: Session, case: CaseRow) -> list[str]:
    fields = session.exec(select(FormFieldRow).where(FormFieldRow.case_id == case.id)).all()
    gaps = session.exec(select(GapRow).where(GapRow.case_id == case.id)).all()
    reasons = package_blockers(
        [OpenGap(g.title, (g.input or {}).get("field_key"))
         for g in gaps if g.severity == "blocking" and g.status in OPEN_GAP],
        [MissingField(f.key, f.label) for f in fields if f.required and not f.value],
        case.tenant_attested_genuine,
    )
    if not fields:
        reasons.insert(0, "No form draft has been prepared for this case yet")
    return reasons


def new_pdf() -> FPDF:
    pdf = FPDF(format="Letter")
    pdf.add_font("NotoSans", "", FONT_DIR / "NotoSans-Regular.ttf")
    pdf.add_font("NotoSans", "B", FONT_DIR / "NotoSans-Bold.ttf")
    pdf.add_font("NotoSansSC", "", FONT_DIR / "NotoSansSC-Regular.ttf")
    pdf.set_fallback_fonts(["NotoSansSC"], exact_match=False)
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.set_font("NotoSans", size=10)
    return pdf


def _write(pdf: FPDF, text: str, *, bold: bool = False, size: int = 10, gap: float = 1.5) -> None:
    pdf.set_font("NotoSans", "B" if bold else "", size)
    # CHAR wrapping: Chinese text has no spaces to break on.
    pdf.multi_cell(0, size * 0.5 + 1.5, text, new_x="LMARGIN", new_y="NEXT", wrapmode=WrapMode.CHAR)
    pdf.ln(gap)


def application_pdf(session: Session, case: CaseRow, prepared_by: str, built_at: datetime) -> bytes:
    draft = build_form_draft(session, case)
    pdf = new_pdf()
    _write(pdf, draft.form_name or "Application draft", bold=True, size=16, gap=3)
    _write(pdf, draft.disclaimer, size=9, gap=4)
    _write(pdf, f"Case: {case.title} ({case.unit})")
    _write(pdf, f"Prepared by {prepared_by} on {built_at:%Y-%m-%d %H:%M} UTC", gap=4)
    for field in draft.fields:
        _write(pdf, field.label, bold=True, gap=0)
        _write(pdf, field.value or "(not filled in)")
    _write(pdf, "Summary of events", bold=True, size=12, gap=2)
    _write(pdf, draft.narrative.text or "(no accepted events)")
    return bytes(pdf.output())


def evidence_zip_name(ev: EvidenceRow) -> str | None:
    """Zip path for the original file, or None when its bytes were never stored."""
    if not storage.exists(ev.sha256):
        return None
    label = "".join(c for c in ev.label if c.isalnum() or c == "-") or ev.id
    return f"evidence/{label}{EVIDENCE_EXT.get(ev.mime, '.bin')}"


@dataclass(frozen=True)
class EvidenceFile:
    """One evidence entry in the zip: an original (streamed from storage) or a rendition."""

    label: str
    name: str
    sha256: str
    note: str
    data: bytes | None = None  # None: the original, read from storage by sha256


def evidence_files(ev: EvidenceRow) -> list[EvidenceFile]:
    """The original, plus a JPG (from HEIC) or PDF (from TXT) when the tribunal needs one.
    Empty when the original was never stored."""
    name = evidence_zip_name(ev)
    if name is None:
        return []
    files = [EvidenceFile(ev.label, name, ev.sha256, ev.filename)]
    made = _rendition(ev, name.rsplit(".", 1)[0])
    if made is not None:
        files.append(made)
    return files


def _rendition(ev: EvidenceRow, stem: str) -> EvidenceFile | None:
    try:
        if ev.mime == sniff.HEIC:
            data = heic_to_jpeg(storage.read(ev.sha256))
            return EvidenceFile(ev.label, f"{stem}.jpg", _sha(data),
                                f"JPG made from the HEIC original ({ev.filename})", data)
        if ev.mime == sniff.TEXT:
            data = text_to_pdf(ev, storage.read(ev.sha256).decode("utf-8-sig"))
            return EvidenceFile(ev.label, f"{stem}.pdf", _sha(data),
                                f"PDF made from the text file ({ev.filename})", data)
    except Exception as exc:  # the original is still filed; a missing copy must not block
        log.warning("could not make a filing copy of %s: %s", ev.label, type(exc).__name__)
    return None


def heic_to_jpeg(data: bytes) -> bytes:
    """Same pixels and the same EXIF as the original (it is filed as evidence, like the
    original). Not the stripped copy: that one is only for the model."""
    with Image.open(io.BytesIO(data)) as img:
        exif = img.getexif()
        out = io.BytesIO()
        img.convert("RGB").save(out, format="JPEG", quality=92, exif=exif.tobytes())
    return out.getvalue()


def text_to_pdf(ev: EvidenceRow, text: str) -> bytes:
    pdf = new_pdf()
    _write(pdf, f"{ev.label}  {ev.filename}", bold=True, size=12, gap=1)
    _write(pdf, f"Text file, sha256 {ev.sha256}", size=8, gap=4)
    _write(pdf, text or "(empty)", size=9)
    return bytes(pdf.output())


def manifest_pdf(
    evidence: list[EvidenceRow], case: CaseRow, ev_files: dict[str, list[EvidenceFile]]
) -> bytes:
    pdf = new_pdf()
    _write(pdf, "Evidence manifest", bold=True, size=16, gap=3)
    _write(pdf, f"Case: {case.title}", gap=4)
    if not evidence:
        _write(pdf, "No evidence files are listed.")
    for ev in evidence:
        _write(pdf, f"{ev.label}  {ev.filename}", bold=True, gap=0)
        _write(pdf, f"Received {iso_req(ev.received_at)} from {ev.uploaded_by}", gap=0)
        copies = ev_files[ev.id][1:]
        stored = bool(ev_files[ev.id])
        _write(pdf, f"sha256 {ev.sha256}", size=8, gap=0 if copies or not stored else 3)
        for copy in copies:
            _write(pdf, f"Also as {copy.name}, sha256 {copy.sha256}", size=8, gap=3)
        if not stored:
            _write(pdf, NOT_STORED, size=8, gap=3)
    return bytes(pdf.output())


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def build_zip(
    session: Session, case: CaseRow, prepared_by: str, att: Attestations, version: int,
    built_at: datetime,
) -> BuiltZip:
    evidence = list(session.exec(
        select(EvidenceRow)
        .where(EvidenceRow.case_id == case.id)
        .order_by(col(EvidenceRow.position))
    ).all())
    app_pdf = application_pdf(session, case, prepared_by, built_at)
    ev_files = {e.id: evidence_files(e) for e in evidence}
    man_pdf = manifest_pdf(evidence, case, ev_files)
    manifest: dict[str, Any] = {
        "case_id": case.id, "version": version, "built_at": iso_req(built_at),
        "prepared_by": prepared_by,
        "tenant_attested_genuine_at": iso_req(case.tenant_attested_at)
        if case.tenant_attested_at else None,
        "caseworker_attestations": att.model_dump(),
        "documents": {
            "application_draft.pdf": _sha(app_pdf),
            "evidence_manifest.pdf": _sha(man_pdf),
        },
        "evidence": [
            {"label": e.label, "filename": e.filename, "sha256": e.sha256,
             "received_at": iso_req(e.received_at), "uploaded_by": e.uploaded_by,
             "in_zip": ev_files[e.id][0].name if ev_files[e.id] else None,
             "rendition": {"path": ev_files[e.id][1].name, "sha256": ev_files[e.id][1].sha256}
             if len(ev_files[e.id]) > 1 else None}
            for e in evidence
        ],
    }
    man_json = json.dumps(manifest, indent=2, ensure_ascii=False).encode()
    parts = [
        ("application_draft.pdf", app_pdf, "Application draft", "From the reviewed timeline"),
        ("evidence_manifest.pdf", man_pdf, "Evidence manifest", "Each file with its hash"),
        ("manifest.json", man_json, "Machine-readable manifest", "Hashes, times, uploaders"),
    ]
    stamp = built_at.timetuple()[:6]
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data, _, _ in parts:
            archive.writestr(zipfile.ZipInfo(name, date_time=stamp), data)
        for ev in evidence:
            for item in ev_files[ev.id]:
                info = zipfile.ZipInfo(item.name, date_time=stamp)
                info.compress_type = zipfile.ZIP_DEFLATED
                with archive.open(info, "w") as out:
                    if item.data is not None:
                        out.write(item.data)
                    else:
                        for chunk in storage.open_chunks(item.sha256):
                            out.write(chunk)
    files = [{"label": lbl, "filename": n, "sha256": _sha(d), "note": note}
             for n, d, lbl, note in parts]
    # Only what is actually in the zip; unstored seed rows are in the manifests only.
    files += [{"label": f.label, "filename": f.name, "sha256": f.sha256, "note": f.note}
              for e in evidence for f in ev_files[e.id]]
    data = buffer.getvalue()
    return BuiltZip(data=data, sha256=_sha(data), files=files)


def build_package(
    session: Session, case: CaseRow, user: UserRow, att: Attestations
) -> PackageRow:
    """Caller has already checked attestations (422) and state (409). Caller commits."""
    # Lock the case row so two concurrent builds cannot take the same version number.
    session.exec(select(CaseRow).where(CaseRow.id == case.id).with_for_update()).one()
    latest = session.exec(
        select(PackageRow.version).where(PackageRow.case_id == case.id)
        .order_by(col(PackageRow.version).desc())
    ).first()
    version = (latest or 0) + 1
    built_at = datetime.now(UTC)
    built = build_zip(session, case, user.name, att, version, built_at)
    blob = storage.put(built.data)
    row = PackageRow(
        id=uuid.uuid4().hex, case_id=case.id, version=version, sha256=built.sha256,
        storage_key=blob.key, size_bytes=blob.size_bytes, prepared_by=user.name,
        built_at=built_at, attestations=att.model_dump(), files=built.files,
    )
    session.add(row)
    activity.log(session, case.id, "caseworker", user.name,
                 f"Built filing package v{version} (sha256 {built.sha256})")
    return row


def to_package(row: PackageRow) -> Package:
    return Package(
        version=row.version, sha256=row.sha256, built_at=iso_req(row.built_at),
        prepared_by=row.prepared_by, files=[PackageFile(**f) for f in row.files],
        reminders=REMINDERS,
    )


def get_package(session: Session, case: CaseRow, version: int | None) -> PackageRow:
    query = select(PackageRow).where(PackageRow.case_id == case.id)
    query = (
        query.where(PackageRow.version == version) if version is not None
        else query.order_by(col(PackageRow.version).desc())
    )
    row = session.exec(query).first()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Package not found")
    return row
