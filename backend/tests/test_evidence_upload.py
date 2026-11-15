"""Evidence uploads over HTTP: caseworker POST /api/cases/{id}/evidence and tenant POST
/api/intake/{token}/files. Real Postgres, Redis and a temp blob store. Every test reseeds
(fresh_db) so uploaded rows never leak into tests that count the 7 seeded items."""

import hashlib
import io
import json
import zipfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

from fpdf import FPDF
from PIL import Image
from sqlmodel import Session, col, select

from app.config import get_settings
from app.models import CaseRow, EvidencePageRow, EvidenceRow, IntakeTokenRow, RunRow
from app.services import storage
from app.services.intake_token import hash_token

CASE = "case_demo_001"
EVIDENCE = f"/api/cases/{CASE}/evidence"
GPS_IFD = 0x8825
EXIF_IFD = 0x8769
SEEDED = 7


# --- builders and helpers -----------------------------------------------------------------


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def jpeg_with_gps(color: tuple[int, int, int] = (200, 30, 30)) -> bytes:
    """A JPEG with Make/Model/Software, a capture time with offset, and a GPS IFD.
    `color` makes each call's bytes (and so its sha256) different."""
    exif = Image.Exif()
    exif[0x010F] = "Apple"
    exif[0x0110] = "iPhone 15"
    exif[0x0131] = "Adobe Lightroom Mobile"
    sub = exif.get_ifd(EXIF_IFD)
    sub[0x9003] = "2026:08:14 21:03:12"
    sub[0x9011] = "-03:00"
    gps = exif.get_ifd(GPS_IFD)
    gps[1], gps[2], gps[3], gps[4] = "N", (45.0, 25.0, 0.0), "W", (63.0, 35.0, 0.0)
    out = io.BytesIO()
    Image.new("RGB", (40, 20), color).save(out, "JPEG", exif=exif.tobytes())
    data = out.getvalue()
    with Image.open(io.BytesIO(data)) as check:  # GPS must round-trip, or tests prove nothing
        assert check.getexif().get_ifd(GPS_IFD)
    return data


def pdf_with_text(pages: list[str], producer: str = "Acme Scanner 3") -> bytes:
    pdf = FPDF()
    pdf.set_producer(producer)
    for body in pages:
        pdf.add_page()
        pdf.set_font("Helvetica", size=12)
        pdf.cell(text=body)
    return bytes(pdf.output())


def files(*items: tuple[str, bytes, str]) -> list[tuple[str, tuple[str, bytes, str]]]:
    return [("file", item) for item in items]


def upload(client, *items: tuple[str, bytes, str]):
    return client.post(EVIDENCE, files=files(*items))


def jpg(name: str = "photo.jpg", data: bytes | None = None) -> tuple[str, bytes, str]:
    return (name, jpeg_with_gps() if data is None else data, "image/jpeg")


def evidence_rows(session: Session) -> list[EvidenceRow]:
    session.expire_all()
    return list(session.exec(
        select(EvidenceRow).where(EvidenceRow.case_id == CASE).order_by(col(EvidenceRow.position))
    ).all())


def activity(client) -> list[dict]:
    return client.get(f"/api/cases/{CASE}/activity").json()


def stored_blobs() -> set[str]:
    return {p.name for p in Path(get_settings().storage_dir).rglob("*") if p.is_file()}


def reasons_of(r) -> list[str]:
    detail = r.json()["detail"]
    assert set(detail) == {"reasons"}
    return detail["reasons"]


def pages_of(session: Session, row: EvidenceRow) -> list[tuple[str, str]]:
    """(locator, text) of the row's evidence_page rows, in order."""
    session.expire_all()
    found = session.exec(
        select(EvidencePageRow).where(EvidencePageRow.evidence_id == row.id)
        .order_by(col(EvidencePageRow.position))
    ).all()
    return [(p.locator, p.text) for p in found]


def stripped_image(row: EvidenceRow) -> tuple[Image.Image, bytes]:
    assert row.stripped_sha256
    data = storage.read(row.stripped_sha256)
    img = Image.open(io.BytesIO(data))
    img.load()
    return img, data


def intake(client) -> dict:
    return client.get(f"/api/cases/{CASE}").json()["intake"]


def set_intake_sent(session: Session) -> None:
    """The demo seed may already say files_received; reset it so the upload must change it."""
    case = session.get(CaseRow, CASE)
    assert case is not None
    case.intake_status = "sent"
    case.intake_last_upload_at = None
    session.add(case)
    session.commit()


# --- caseworker upload: the happy path ----------------------------------------------------


def test_caseworker_upload_of_a_geotagged_jpeg(fresh_db, client, session):
    original = jpeg_with_gps()
    assert len(evidence_rows(session)) == SEEDED

    r = upload(client, ("ceiling.jpg", original, "image/jpeg"))

    assert r.status_code == 200, r.text
    [item] = r.json()
    assert item["label"] == "E-08"
    assert item["filename"] == "ceiling.jpg"
    assert item["kind"] == "photo" and item["mime"] == "image/jpeg"
    assert item["uploaded_by"] == "caseworker"
    assert item["size_bytes"] == len(original)
    assert item["sha256"] == sha(original)
    assert item["processing"] == "done" and item["error"] is None
    assert item["metadata_stripped_for_ai"] is True
    assert item["metadata"] == {
        "captured_at": "2026-08-14T21:03:12-03:00", "gps_present": True,
        "device": "Apple iPhone 15", "software": "Adobe Lightroom Mobile",
    }
    assert item["format_check"]["accepted"] is True

    ids = [e["id"] for e in client.get(EVIDENCE).json()]
    assert len(ids) == SEEDED + 1 and ids[-1] == item["id"]


def test_original_is_stored_unchanged_and_the_ai_copy_has_no_metadata(fresh_db, client, session):
    original = jpeg_with_gps()
    upload(client, jpg(data=original))

    row = evidence_rows(session)[-1]
    assert row.sha256 == sha(original)
    assert storage.read(row.sha256) == original  # the original keeps its EXIF
    with Image.open(io.BytesIO(original)) as src:
        assert src.getexif().get_ifd(GPS_IFD)

    assert row.stripped_sha256 and row.stripped_sha256 != row.sha256
    img, data = stripped_image(row)
    assert len(img.getexif()) == 0
    assert not img.getexif().get_ifd(GPS_IFD)
    assert not {"exif", "icc_profile", "xmp"} & set(img.info)
    assert b"iPhone" not in data and b"Exif" not in data
    assert img.size == (40, 20) and img.format == "JPEG"


def test_upload_is_logged_with_the_caseworker_as_actor(fresh_db, client):
    name = client.get("/api/me").json()["name"]
    before = len(activity(client))

    upload(client, jpg("ceiling.jpg"))

    acts = activity(client)
    assert len(acts) == before + 1
    assert acts[0]["actor"] == "caseworker" and acts[0]["actor_name"] == name
    assert acts[0]["action"] == "Uploaded E-08 (ceiling.jpg)"


def test_several_files_in_one_request_get_sequential_labels(fresh_db, client, session):
    items = [jpg("a.jpg", jpeg_with_gps((1, 1, 1))), jpg("b.jpg", jpeg_with_gps((2, 2, 2))),
             ("notes.txt", b"Tenant: it leaks", "text/plain")]

    r = upload(client, *items)

    assert r.status_code == 200, r.text
    assert [i["label"] for i in r.json()] == ["E-08", "E-09", "E-10"]
    assert [i["filename"] for i in r.json()] == ["a.jpg", "b.jpg", "notes.txt"]
    assert [i["kind"] for i in r.json()] == ["photo", "photo", "messages"]
    assert [a["action"] for a in activity(client)[:3]] == [
        "Uploaded E-10 (notes.txt)", "Uploaded E-09 (b.jpg)", "Uploaded E-08 (a.jpg)"]
    assert [e.position for e in evidence_rows(session)][-3:] == [7, 8, 9]

    again = upload(client, jpg("c.jpg", jpeg_with_gps((3, 3, 3)))).json()
    assert [i["label"] for i in again] == ["E-11"]


def test_response_items_match_the_contract_shape(fresh_db, client):
    from app import schemas

    [item] = upload(client, jpg()).json()
    assert set(item) == set(schemas.EvidenceItem.model_fields)
    assert set(item["metadata"]) == set(schemas.EvidenceMetadata.model_fields)


# --- duplicates ---------------------------------------------------------------------------


def test_same_bytes_in_a_second_request_return_the_existing_row(fresh_db, client, session):
    data = jpeg_with_gps()
    first = upload(client, jpg("one.jpg", data)).json()[0]
    blobs = stored_blobs()
    acts = len(activity(client))

    second = upload(client, jpg("renamed.jpg", data))

    assert second.status_code == 200
    [again] = second.json()
    assert again["id"] == first["id"] and again["label"] == "E-08"
    assert again["filename"] == "one.jpg"
    assert len(evidence_rows(session)) == SEEDED + 1
    assert stored_blobs() == blobs
    assert len(activity(client)) == acts  # nothing new happened, nothing new is logged


def test_same_bytes_twice_in_one_request_make_one_row(fresh_db, client, session):
    data = jpeg_with_gps()
    r = upload(client, jpg("a.jpg", data), jpg("b.jpg", data))

    assert r.status_code == 200, r.text
    items = r.json()
    assert len(items) == 2 and items[0]["id"] == items[1]["id"]
    assert len(evidence_rows(session)) == SEEDED + 1
    uploaded = [a for a in activity(client) if a["action"].startswith("Uploaded")]
    assert len([a for a in uploaded if a["actor"] == "caseworker"]) >= 1
    assert sum("E-08" in a["action"] for a in uploaded) == 1


def test_a_duplicate_does_not_make_an_earlier_run_stale(fresh_db, client, session):
    data = jpeg_with_gps()
    upload(client, jpg(data=data))
    run = session.get(RunRow, "run_001")
    assert run is not None
    run.stale = False
    session.add(run)
    session.commit()

    upload(client, jpg(data=data))

    assert client.get(f"/api/cases/{CASE}/runs/latest").json()["stale"] is False


# --- refusals: nothing is stored ----------------------------------------------------------


def test_over_the_cap_is_413_and_stores_nothing(fresh_db, client, session, monkeypatch):
    monkeypatch.setattr(get_settings(), "max_upload_bytes", 2048)
    blobs = stored_blobs()
    acts = len(activity(client))
    big = b"a" * 2049

    r = upload(client, ("ok.txt", b"fine", "text/plain"), ("big.txt", big, "text/plain"))

    assert r.status_code == 413
    assert set(r.json()) == {"detail"}
    reasons = reasons_of(r)
    assert len(reasons) == 1 and "File 2" in reasons[0]
    assert len(evidence_rows(session)) == SEEDED
    assert stored_blobs() == blobs
    assert len(activity(client)) == acts


def test_exactly_the_cap_is_accepted(fresh_db, client, monkeypatch):
    monkeypatch.setattr(get_settings(), "max_upload_bytes", 2048)
    assert upload(client, ("ok.txt", b"a" * 2048, "text/plain")).status_code == 200


def test_413_wins_over_415(fresh_db, client, session, monkeypatch):
    monkeypatch.setattr(get_settings(), "max_upload_bytes", 2048)
    r = upload(client, ("bad.jpg", b"MZ" + b"\x00" * 10, "image/jpeg"),
               ("big.txt", b"a" * 3000, "text/plain"))
    assert r.status_code == 413
    assert len(evidence_rows(session)) == SEEDED


def test_disguised_executable_is_415_and_stores_nothing(fresh_db, client, session):
    blobs = stored_blobs()
    acts = len(activity(client))

    r = upload(client, ("photo.jpg", b"MZ\x90\x00" + b"\x00" * 60, "image/jpeg"))

    assert r.status_code == 415
    reasons = reasons_of(r)
    assert len(reasons) == 1 and "File 1" in reasons[0]
    assert len(evidence_rows(session)) == SEEDED
    assert stored_blobs() == blobs
    assert len(activity(client)) == acts


def test_a_batch_with_one_bad_file_stores_none_of_it(fresh_db, client, session):
    blobs = stored_blobs()

    r = upload(client, jpg("good.jpg"), ("evil.jpg", b"MZ\x00\x00", "image/jpeg"))

    assert r.status_code == 415
    assert "File 2" in reasons_of(r)[0]
    assert len(evidence_rows(session)) == SEEDED
    assert stored_blobs() == blobs


def test_an_empty_file_is_415(fresh_db, client, session):
    assert upload(client, ("empty.txt", b"", "text/plain")).status_code == 415
    assert len(evidence_rows(session)) == SEEDED


def test_no_file_field_is_422(fresh_db, client):
    assert client.post(EVIDENCE).status_code == 422


# --- unreadable but allowed files are kept, flagged -----------------------------------------


def test_corrupt_jpeg_is_kept_as_failed_not_a_500(fresh_db, client, session):
    data = b"\xff\xd8\xff" + b"garbage that is no jpeg" * 4

    r = upload(client, ("broken.jpg", data, "image/jpeg"))

    assert r.status_code == 200, r.text
    [item] = r.json()
    assert item["processing"] == "failed"
    assert item["error"] == "This file could not be read."
    assert item["metadata_stripped_for_ai"] is False
    assert item["metadata"] == {
        "captured_at": None, "gps_present": False, "device": None, "software": None}
    row = evidence_rows(session)[-1]
    assert row.stripped_sha256 is None  # nothing may go to the model
    assert storage.read(row.sha256) == data


def test_corrupt_pdf_is_kept_as_failed(fresh_db, client, session):
    r = upload(client, ("broken.pdf", b"%PDF-1.4\nnot really a pdf", "application/pdf"))
    assert r.status_code == 200, r.text
    assert r.json()[0]["processing"] == "failed"
    assert pages_of(session, evidence_rows(session)[-1]) == []


def test_a_pdf_that_runs_past_the_hard_limit_is_kept_as_failed(
    fresh_db, client, session, monkeypatch
):
    from app.services.evidence import text

    monkeypatch.setattr(text, "PDF_HARD_SECONDS", 0.001)  # the child can't even start in time
    data = pdf_with_text(["Notice of entry"])
    [item] = upload(client, ("notice.pdf", data, "application/pdf")).json()
    assert item["processing"] == "failed"
    [row] = [r for r in evidence_rows(session) if r.id == item["id"]]
    assert row.error == "Reading the text took too long."
    assert storage.read(row.sha256) == data  # the original is still kept
    assert pages_of(session, row) == []


def test_pdf_upload_writes_one_evidence_page_per_page(fresh_db, client, session):
    data = pdf_with_text(["Leak in the kitchen", "Landlord was told on Aug 20"])

    r = upload(client, ("letter.pdf", data, "application/pdf"))

    assert r.status_code == 200, r.text
    [item] = r.json()
    assert item["kind"] == "other" and item["mime"] == "application/pdf"
    assert item["processing"] == "done"
    assert item["metadata"]["software"] == "Acme Scanner 3"
    assert item["metadata"]["gps_present"] is False
    row = evidence_rows(session)[-1]
    pages = pages_of(session, row)
    assert [locator for locator, _ in pages] == ["page 1", "page 2"]
    assert "Leak in the kitchen" in pages[0][1]
    assert "Aug 20" in pages[1][1]
    assert row.stripped_sha256 is None


def test_text_upload_writes_one_evidence_page_per_message(fresh_db, client, session):
    chat = "Tenant: it leaks\r\n\n房东：下周派人来修。\nTenant: thanks\n".encode()
    r = upload(client, ("chat.txt", chat, "text/plain"))
    assert r.status_code == 200, r.text
    assert r.json()[0]["kind"] == "messages"
    assert r.json()[0]["format_check"]["action"] == "will_export_pdf"
    assert pages_of(session, evidence_rows(session)[-1]) == [
        ("message 1", "Tenant: it leaks"), ("message 2", "房东：下周派人来修。"),
        ("message 3", "Tenant: thanks")]


def test_evidence_pages_go_with_their_evidence_and_case(fresh_db, client, session):
    upload(client, ("chat.txt", b"one\ntwo\n", "text/plain"))
    row = evidence_rows(session)[-1]
    pages = session.exec(
        select(EvidencePageRow).where(EvidencePageRow.evidence_id == row.id)).all()
    assert {p.case_id for p in pages} == {CASE}
    assert [p.position for p in pages] == [0, 1]


def test_a_photo_gets_one_code_written_page_with_its_capture_time(fresh_db, client, session):
    upload(client, jpg())
    pages = pages_of(session, evidence_rows(session)[-1])
    assert pages == [("photo 1", "Photo file. Capture time (EXIF): 2026-08-14T21:03:12-03:00.")]


def test_png_upload_is_stripped_to_a_png(fresh_db, client, session):
    out = io.BytesIO()
    Image.new("RGB", (12, 12), (5, 5, 5)).save(out, "PNG")

    r = upload(client, ("shot.png", out.getvalue(), "image/png"))

    assert r.status_code == 200, r.text
    assert r.json()[0]["mime"] == "image/png" and r.json()[0]["processing"] == "done"
    img, _ = stripped_image(evidence_rows(session)[-1])
    assert img.format == "PNG"


# --- hostile filenames --------------------------------------------------------------------


def test_path_traversal_filename_is_shown_as_its_last_segment_and_never_opened(
    fresh_db, client, session
):
    root = Path(get_settings().storage_dir)

    r = upload(client, ("../../etc/passwd.jpg", jpeg_with_gps(), "image/jpeg"))

    assert r.status_code == 200, r.text
    assert r.json()[0]["filename"] == "passwd.jpg"
    assert evidence_rows(session)[-1].filename == "passwd.jpg"
    # Blobs are named by hash and live only under STORAGE_DIR.
    assert all(len(p.name) == 64 for p in root.rglob("*") if p.is_file())
    assert not (root.parent / "etc").exists()
    assert not list(root.parent.glob("passwd*"))
    assert not list(root.glob("**/passwd*"))


def test_windows_path_filename_is_shown_as_its_last_segment(fresh_db, client):
    # Control characters are covered in test_evidence_services: the multipart encoder
    # percent-encodes them before they reach the server.
    r = upload(client, ("C:\\Users\\x\\photo.jpg", jpeg_with_gps(), "image/jpeg"))
    assert r.json()[0]["filename"] == "photo.jpg"


def test_the_declared_content_type_is_ignored(fresh_db, client):
    r = upload(client, ("x.pdf", jpeg_with_gps(), "application/pdf"))
    assert r.status_code == 200
    assert r.json()[0]["mime"] == "image/jpeg"


# --- auth and org isolation ---------------------------------------------------------------


def test_other_orgs_caseworker_gets_404_and_stores_nothing(
    fresh_db, other_org_client, session
):
    blobs = stored_blobs()
    r = upload(other_org_client, jpg())
    assert r.status_code == 404
    assert len(evidence_rows(session)) == SEEDED
    assert stored_blobs() == blobs


def test_unauthenticated_upload_is_401(fresh_db, anon_client, session):
    r = upload(anon_client, jpg())
    assert r.status_code == 401
    assert len(evidence_rows(session)) == SEEDED


def test_unknown_case_is_404(fresh_db, client):
    r = client.post("/api/cases/no_such_case/evidence", files=files(jpg()))
    assert r.status_code == 404


def test_caseworker_upload_is_rate_limited(fresh_db, client):
    limit = int(get_settings().upload_rate_limit.split("/")[0])
    statuses = [client.post(EVIDENCE, files=files(("n.txt", b"same", "text/plain"))).status_code
                for _ in range(limit + 1)]
    assert statuses[:limit] == [200] * limit
    assert statuses[limit] == 429


# --- staleness ----------------------------------------------------------------------------


def test_an_upload_makes_the_earlier_run_stale(fresh_db, client):
    assert client.get(f"/api/cases/{CASE}/runs/latest").json()["stale"] is False

    upload(client, jpg())

    assert client.get(f"/api/cases/{CASE}/runs/latest").json()["stale"] is True


def test_a_refused_upload_does_not_make_the_run_stale(fresh_db, client):
    upload(client, ("x.jpg", b"MZ\x00\x00", "image/jpeg"))
    assert client.get(f"/api/cases/{CASE}/runs/latest").json()["stale"] is False


# --- tenant upload ------------------------------------------------------------------------


def files_url(token: str) -> str:
    return f"/api/intake/{token}/files"


def test_tenant_upload_records_files_and_marks_files_received(
    fresh_db, token, client, anon_client, session
):
    set_intake_sent(session)
    assert intake(client)["status"] == "sent" and intake(client)["last_upload_at"] is None
    tenant_name = client.get(f"/api/cases/{CASE}").json()["tenant"]["name"]
    data = [jpeg_with_gps((9, 9, 9)), jpeg_with_gps((8, 8, 8))]

    r = anon_client.post(files_url(token), files=files(
        ("one.jpg", data[0], "image/jpeg"), ("two.jpg", data[1], "image/jpeg")))

    assert r.status_code == 200, r.text
    assert r.json() == {"received": 2}
    rows = evidence_rows(session)[-2:]
    assert [e.label for e in rows] == ["E-08", "E-09"]
    assert {e.uploaded_by for e in rows} == {"tenant"}
    assert [storage.read(e.sha256) for e in rows] == data
    assert all(e.processing == "done" and e.stripped_sha256 for e in rows)
    after = intake(client)
    assert after["status"] == "files_received"
    assert after["last_upload_at"] is not None
    assert after["tenant_attested_genuine"] is False  # new files: the seeded confirmation lapses
    acts = activity(client)[:3]
    assert [a["actor"] for a in acts] == ["tenant", "tenant", "tenant"]
    assert {a["actor_name"] for a in acts} == {tenant_name}
    assert [a["action"] for a in acts] == [
        "New files arrived after the confirmation, so it must be given again",
        "Uploaded E-09 (two.jpg)", "Uploaded E-08 (one.jpg)"]
    assert client.get(f"/api/cases/{CASE}/runs/latest").json()["stale"] is True


def test_tenant_duplicate_counts_as_received_but_adds_no_row(
    fresh_db, token, anon_client, session
):
    data = jpeg_with_gps()
    anon_client.post(files_url(token), files=files(("a.jpg", data, "image/jpeg")))
    r = anon_client.post(files_url(token), files=files(("a.jpg", data, "image/jpeg")))
    assert r.status_code == 200 and r.json() == {"received": 1}
    assert len(evidence_rows(session)) == SEEDED + 1


def test_tenant_upload_of_a_bad_type_is_415_and_changes_nothing(
    fresh_db, token, client, anon_client, session
):
    set_intake_sent(session)
    r = anon_client.post(files_url(token), files=files(
        jpg("good.jpg"), ("evil.jpg", b"MZ\x00\x00", "image/jpeg")))
    assert r.status_code == 415
    assert len(evidence_rows(session)) == SEEDED
    assert intake(client)["status"] == "sent"


def test_tenant_upload_of_a_big5_chat_asks_for_utf8(
    fresh_db, token, client, anon_client, session
):
    """The file is a TXT, so the reason must not send the tenant looking for another format.
    Re-saving as UTF-8 reads it back exactly."""
    set_intake_sent(session)
    r = anon_client.post(files_url(token), files=files(
        ("chat.txt", "房東說明天會來修\n".encode("big5"), "text/plain")))
    assert r.status_code == 415
    assert reasons_of(r) == [
        "File 1 is text in an encoding this app can't read. Re-save it as UTF-8"]
    assert len(evidence_rows(session)) == SEEDED
    assert intake(client)["status"] == "sent"


def test_tenant_upload_over_the_cap_is_413(fresh_db, token, anon_client, session, monkeypatch):
    monkeypatch.setattr(get_settings(), "max_upload_bytes", 2048)
    r = anon_client.post(files_url(token), files=files(("big.txt", b"a" * 4000, "text/plain")))
    assert r.status_code == 413
    assert len(evidence_rows(session)) == SEEDED


def test_tenant_upload_with_a_revoked_token_is_404(
    fresh_db, token, client, anon_client, session
):
    old = token
    new = client.post(f"/api/cases/{CASE}/intake-link").json()["url"].rsplit("/", 1)[1]
    assert new != old
    blobs = stored_blobs()

    assert anon_client.post(files_url(old), files=files(jpg())).status_code == 404

    assert len(evidence_rows(session)) == SEEDED
    assert stored_blobs() == blobs
    assert anon_client.post(files_url(new), files=files(jpg())).status_code == 200


def test_tenant_upload_with_an_expired_token_is_404(
    fresh_db, token, anon_client, session
):
    row = session.get(IntakeTokenRow, hash_token(token))
    assert row is not None
    row.expires_at = datetime.now(UTC) - timedelta(days=1)
    session.add(row)
    session.commit()
    blobs = stored_blobs()

    r = anon_client.post(files_url(token), files=files(jpg()))

    assert r.status_code == 404
    assert len(evidence_rows(session)) == SEEDED
    assert stored_blobs() == blobs


def test_tenant_upload_with_an_unknown_token_is_404(fresh_db, anon_client, session):
    r = anon_client.post(files_url("not-a-real-token"), files=files(jpg()))
    assert r.status_code == 404
    assert len(evidence_rows(session)) == SEEDED


def test_tenant_upload_is_rate_limited(fresh_db, token, anon_client):
    limit = int(get_settings().upload_rate_limit.split("/")[0])
    statuses = [
        anon_client.post(files_url(token), files=files(("n.txt", b"same", "text/plain"))
                         ).status_code
        for _ in range(limit + 1)
    ]
    assert statuses[:limit] == [200] * limit
    assert statuses[limit] == 429


def test_tenant_upload_does_not_expose_the_caseworker_note(fresh_db, token, anon_client):
    r = anon_client.post(files_url(token), files=files(jpg()))
    assert r.status_code == 200
    assert "caseworker_note" not in r.text


# --- filing package -----------------------------------------------------------------------

BUILD = f"/api/cases/{CASE}/package"
DOWNLOAD = f"/api/cases/{CASE}/package/download"
ATTESTATIONS = {"attestations": {"reviewed_fields": True, "remedy_confirmed_with_tenant": True,
                                 "explained_not_legal_advice": True}}


def make_ready(client) -> None:
    r1 = client.patch("/api/gaps/gap_01", json={"status": "resolved", "value": "12 Harbour Rd"})
    r2 = client.patch("/api/gaps/gap_02", json={"status": "resolved", "value": "Repair the leak"})
    assert r1.status_code == 200 and r2.status_code == 200


def unzip(data: bytes) -> dict[str, bytes]:
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        return {name: archive.read(name) for name in archive.namelist()}


def test_package_zip_contains_the_uploaded_originals(fresh_db, client, session):
    photo = jpeg_with_gps()
    letter = pdf_with_text(["Notice to landlord"])
    r = upload(client, ("ceiling.jpg", photo, "image/jpeg"),
               ("letter.pdf", letter, "application/pdf"))
    assert [i["label"] for i in r.json()] == ["E-08", "E-09"]
    make_ready(client)

    built = client.post(BUILD, json=ATTESTATIONS)
    assert built.status_code == 200, built.text
    zipped = client.get(DOWNLOAD)
    assert zipped.status_code == 200
    entries = unzip(zipped.content)

    assert {"application_draft.pdf", "evidence_manifest.pdf", "manifest.json"} <= set(entries)
    assert set(entries) == {"application_draft.pdf", "evidence_manifest.pdf", "manifest.json",
                            "evidence/E-08.jpg", "evidence/E-09.pdf"}
    assert entries["evidence/E-08.jpg"] == photo  # the original with its EXIF, not the AI copy
    assert entries["evidence/E-09.pdf"] == letter

    manifest = json.loads(entries["manifest.json"])
    by_label = {e["label"]: e for e in manifest["evidence"]}
    assert len(manifest["evidence"]) == SEEDED + 2
    assert by_label["E-08"]["sha256"] == sha(photo)
    assert by_label["E-08"]["in_zip"] == "evidence/E-08.jpg"
    assert by_label["E-09"]["sha256"] == sha(letter)
    assert by_label["E-09"]["in_zip"] == "evidence/E-09.pdf"
    assert sha(entries[by_label["E-08"]["in_zip"]]) == by_label["E-08"]["sha256"]
    for label in (f"E-{n:02d}" for n in range(1, SEEDED + 1)):
        assert by_label[label]["in_zip"] is None  # seed rows have no stored bytes

    body = built.json()
    listed = {f["filename"]: f for f in body["files"]}
    assert set(listed) == set(entries)
    assert listed["evidence/E-08.jpg"] == {
        "label": "E-08", "filename": "evidence/E-08.jpg", "sha256": sha(photo),
        "note": "ceiling.jpg"}
    assert listed["evidence/E-09.pdf"]["sha256"] == sha(letter)
    assert listed["evidence/E-09.pdf"]["note"] == "letter.pdf"
    for f in body["files"]:
        assert sha(entries[f["filename"]]) == f["sha256"]


def test_package_zip_names_come_from_the_label_never_the_filename(fresh_db, client):
    upload(client, ("../../evil.jpg", jpeg_with_gps(), "image/jpeg"))
    make_ready(client)
    client.post(BUILD, json=ATTESTATIONS)

    names = set(unzip(client.get(DOWNLOAD).content))

    assert "evidence/E-08.jpg" in names
    assert not any("evil" in n or ".." in n for n in names)


def test_package_with_no_uploads_is_unchanged(fresh_db, client):
    make_ready(client)
    body = client.post(BUILD, json=ATTESTATIONS).json()
    entries = unzip(client.get(DOWNLOAD).content)
    assert set(entries) == {"application_draft.pdf", "evidence_manifest.pdf", "manifest.json"}
    assert {f["filename"] for f in body["files"]} == set(entries)
    manifest = json.loads(entries["manifest.json"])
    assert all(e["in_zip"] is None for e in manifest["evidence"])


def test_a_tenant_uploaded_text_file_is_in_the_package_as_txt(
    fresh_db, token, anon_client, client
):
    chat = b"Tenant: the ceiling leaks\n"
    assert anon_client.post(files_url(token), files=files(
        ("chat.txt", chat, "text/plain"))).status_code == 200
    tenant_confirms(anon_client, token)  # the intake page sends files, then the confirmation
    make_ready(client)
    client.post(BUILD, json=ATTESTATIONS)

    entries = unzip(client.get(DOWNLOAD).content)
    assert entries["evidence/E-08.txt"] == chat
    assert entries["evidence/E-08.pdf"].startswith(b"%PDF-")  # text messages are filed as PDF
    manifest = json.loads(entries["manifest.json"])
    item = next(e for e in manifest["evidence"] if e["label"] == "E-08")
    assert item["rendition"]["path"] == "evidence/E-08.pdf"


def test_a_gbk_chat_export_is_accepted_read_and_filed_as_is(fresh_db, client, session):
    chat = "房东：明天来修\nTenant: OK\n"  # landlord: fixing it tomorrow
    data = chat.encode("gbk")
    [item] = upload(client, ("wechat.txt", data, "text/plain")).json()
    assert item["mime"] == "text/plain" and item["processing"] == "done"
    [row] = [r for r in evidence_rows(session) if r.id == item["id"]]
    assert storage.read(row.sha256) == data  # the original bytes, not re-encoded
    assert pages_of(session, row) == [("message 1", "房东：明天来修"),
                                      ("message 2", "Tenant: OK")]


def test_a_gbk_chat_export_gets_a_readable_pdf_copy_in_the_package(fresh_db, client):
    from pypdf import PdfReader

    data = "房东：明天来修\nTenant: OK\n".encode("gbk")
    upload(client, ("wechat.txt", data, "text/plain"))
    make_ready(client)
    client.post(BUILD, json=ATTESTATIONS)

    entries = unzip(client.get(DOWNLOAD).content)
    assert entries["evidence/E-08.txt"] == data
    copy = PdfReader(io.BytesIO(entries["evidence/E-08.pdf"]))
    assert "房东" in "".join(page.extract_text() for page in copy.pages)
    manifest = json.loads(entries["manifest.json"])
    item = next(e for e in manifest["evidence"] if e["label"] == "E-08")
    assert item["rendition"]["path"] == "evidence/E-08.pdf"


def tenant_confirms(anon_client, token: str) -> None:
    r = anon_client.post(f"/api/intake/{token}/submit",
                         json={"attest_genuine": True, "consent_share": True})
    assert r.status_code == 200, r.text


def test_new_tenant_files_clear_an_earlier_confirmation_until_it_is_given_again(
    fresh_db, token, anon_client, client
):
    assert intake(client)["tenant_attested_genuine"] is True  # the seeded case is confirmed
    make_ready(client)
    assert anon_client.post(files_url(token), files=files(
        ("later.txt", b"Tenant: it leaked again\n", "text/plain"))).status_code == 200

    after = intake(client)
    assert after["tenant_attested_genuine"] is False and after["tenant_attested_at"] is None
    assert client.post(BUILD, json=ATTESTATIONS).status_code == 409

    tenant_confirms(anon_client, token)
    assert intake(client)["tenant_attested_genuine"] is True
    assert client.post(BUILD, json=ATTESTATIONS).status_code == 200


def test_caseworker_files_and_tenant_duplicates_keep_the_confirmation(
    fresh_db, token, anon_client, client
):
    note = ("note.txt", b"Caseworker: called the landlord\n", "text/plain")
    assert upload(client, note).status_code == 200
    assert intake(client)["tenant_attested_genuine"] is True
    # The tenant re-sending a file the case already has adds nothing, so nothing to confirm.
    assert anon_client.post(files_url(token), files=files(note)).status_code == 200
    assert intake(client)["tenant_attested_genuine"] is True


# --- HEIC (iPhone default) ----------------------------------------------------------------


def heic_with_gps() -> bytes:
    """A real HEIC (pillow-heif encodes it) with a capture time and a GPS IFD."""
    import pillow_heif

    pillow_heif.register_heif_opener()
    exif = Image.Exif()
    exif[0x010F], exif[0x0110] = "Apple", "iPhone 15"
    exif.get_ifd(EXIF_IFD)[0x9003] = "2026:08:14 21:03:12"
    gps = exif.get_ifd(GPS_IFD)
    gps[1], gps[2], gps[3], gps[4] = "N", (45.0, 25.0, 0.0), "W", (63.0, 35.0, 0.0)
    out = io.BytesIO()
    Image.new("RGB", (64, 32), (10, 200, 30)).save(out, "HEIF", exif=exif.tobytes())
    data = out.getvalue()
    with Image.open(io.BytesIO(data)) as check:
        assert check.getexif().get_ifd(GPS_IFD)
    return data


def test_heic_upload_is_converted_and_its_ai_copy_is_a_clean_jpeg(fresh_db, client, session):
    original = heic_with_gps()

    [item] = upload(client, ("IMG_4412.HEIC", original, "image/heic")).json()

    assert item["mime"] == "image/heic" and item["kind"] == "photo"
    assert item["format_check"]["action"] == "converted"
    assert item["processing"] == "done"
    assert item["metadata"]["gps_present"] is True
    assert item["metadata"]["captured_at"] == "2026-08-14T21:03:12"  # no offset recorded
    assert item["metadata"]["device"] == "Apple iPhone 15"
    row = evidence_rows(session)[-1]
    assert storage.read(row.sha256) == original
    img, data = stripped_image(row)
    assert img.format == "JPEG" and img.size == (64, 32)
    assert len(img.getexif()) == 0 and b"iPhone" not in data


def test_heic_original_goes_in_the_package_as_heic(fresh_db, client):
    original = heic_with_gps()
    upload(client, ("IMG_4412.HEIC", original, "image/heic"))
    make_ready(client)
    client.post(BUILD, json=ATTESTATIONS)

    built = client.post(BUILD, json=ATTESTATIONS).json()

    entries = unzip(client.get(DOWNLOAD).content)
    assert entries["evidence/E-08.heic"] == original
    # The tribunal doesn't take HEIC: a JPG copy rides along, with the original's EXIF.
    with Image.open(io.BytesIO(entries["evidence/E-08.jpg"])) as copy:
        assert copy.format == "JPEG" and copy.size == (64, 32)
        assert copy.getexif().get_ifd(GPS_IFD)
    manifest = json.loads(entries["manifest.json"])
    item = next(e for e in manifest["evidence"] if e["label"] == "E-08")
    assert item["in_zip"] == "evidence/E-08.heic"
    assert item["rendition"] == {"path": "evidence/E-08.jpg",
                                 "sha256": sha(entries["evidence/E-08.jpg"])}
    listed = {f["filename"]: f for f in built["files"]}
    assert listed["evidence/E-08.jpg"]["sha256"] == sha(entries["evidence/E-08.jpg"])



def test_a_heic_that_failed_processing_is_filed_without_a_jpg_copy(
    fresh_db, client, session, monkeypatch
):
    """Over the pixel limit at ingest: the original is kept and filed, but the package must
    not decode it at full size to make the JPG copy."""
    from app.services import package
    from app.services.evidence import strip

    monkeypatch.setattr(strip, "MAX_PIXELS", 100)  # the 64 x 32 test HEIC is now "too big"
    original = heic_with_gps()
    [item] = upload(client, ("IMG_4412.HEIC", original, "image/heic")).json()
    assert item["processing"] == "failed"
    # No copy will be made, so none is promised: the caseworker is told to ask for a JPG.
    assert item["format_check"]["accepted"] is False
    assert item["format_check"]["action"] == "none"
    assert "Ask for the photo as a JPG" in item["format_check"]["note"]
    decoded = []
    monkeypatch.setattr(package, "heic_to_jpeg", lambda data: decoded.append(data) or b"")
    make_ready(client)

    client.post(BUILD, json=ATTESTATIONS)

    entries = unzip(client.get(DOWNLOAD).content)
    assert entries["evidence/E-08.heic"] == original
    assert "evidence/E-08.jpg" not in entries
    assert decoded == []


# --- request limits -----------------------------------------------------------------------


def test_more_than_twenty_files_in_one_request_is_413(fresh_db, client, session):
    many = [(f"{n}.txt", f"note {n}".encode(), "text/plain") for n in range(21)]
    r = client.post(EVIDENCE, files=files(*many))
    assert r.status_code == 413
    assert len(evidence_rows(session)) == SEEDED


def test_a_declared_body_over_the_limit_is_refused_before_it_is_read(fresh_db, client, token):
    huge = str(20 * get_settings().max_upload_bytes + 2 * 1024 * 1024)
    for url in (EVIDENCE, files_url(token)):
        r = client.post(url, content=b"x", headers={
            "content-type": "multipart/form-data; boundary=x", "content-length": huge})
        assert r.status_code == 413, url
        assert r.json() == {"detail": {"reasons": ["The upload is too large"]}}


def test_a_chunked_body_over_the_limit_is_stopped_before_the_token_check(
    fresh_db, client, monkeypatch
):
    """No Content-Length: the body is counted as it arrives. An unknown token still gets
    413, not 404, because the token is only checked after the body has been read."""
    monkeypatch.setattr(get_settings(), "max_upload_bytes", 2048)

    def body():
        yield b"--x\r\nContent-Disposition: form-data; name=\"file\"; filename=\"a.txt\"\r\n\r\n"
        for _ in range(64):  # 4 MB in all, well over 20 x 2 KB + 1 MB of slack
            yield b"a" * 65536

    r = client.post("/api/intake/not-a-real-token/files", content=body(),
                    headers={"content-type": "multipart/form-data; boundary=x"})
    assert r.status_code == 413
    assert r.json() == {"detail": {"reasons": ["The upload is too large"]}}
