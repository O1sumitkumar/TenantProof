"""OCR on this server (RapidOCR): text in photos and in scanned PDF pages becomes evidence text the
agent can cite, under locators that say it was machine-read. These tests run the real engine
(its models ship in the wheel; nothing is downloaded). Misreads of scripts the model doesn't know
(Russian, Hindi) are dropped, and nothing in OCR can fail an upload."""

import io
from pathlib import Path

import pytest
from PIL import Image, ImageDraw, ImageFont
from sqlmodel import Session, col, select

from app.config import get_settings
from app.models import EvidencePageRow, EvidenceRow
from app.services.evidence import exif, ingest, ocr, text

FONTS = Path(__file__).resolve().parents[1] / "app" / "assets" / "fonts"
CASE = "case_demo_001"
EVIDENCE = f"/api/cases/{CASE}/evidence"
EN = "The heater has been broken since October 3."
ZH = "暖气从十月三号就坏了，房东说下周修。"


def picture(*lines: tuple[str, str], size: tuple[int, int] = (1080, 400)) -> Image.Image:
    """Black text on white, one (font file, text) per line, like a phone screenshot."""
    img = Image.new("RGB", size, "white")
    draw = ImageDraw.Draw(img)
    for n, (font, line) in enumerate(lines):
        draw.text((30, 40 + n * 90), line, font=ImageFont.truetype(str(FONTS / font), 40),
                  fill="black")
    return img


def png(img: Image.Image) -> bytes:
    out = io.BytesIO()
    img.save(out, "PNG")
    return out.getvalue()


def scanned_pdf(*pages: Image.Image) -> bytes:
    """A PDF whose pages are images only, with no text layer: what a scanner makes."""
    out = io.BytesIO()
    pages[0].save(out, "PDF", save_all=True, append_images=list(pages[1:]), resolution=150)
    return out.getvalue()


@pytest.fixture
def ocr_on(monkeypatch):
    monkeypatch.setattr(get_settings(), "ocr_enabled", True)


def pages_of(session: Session, row_id: str) -> dict[str, str]:
    session.expire_all()
    rows = session.exec(
        select(EvidencePageRow).where(EvidencePageRow.evidence_id == row_id)
        .order_by(col(EvidencePageRow.position))
    ).all()
    return {r.locator: r.text for r in rows}


def uploaded(session: Session, filename: str) -> EvidenceRow:
    session.expire_all()
    return session.exec(
        select(EvidenceRow).where(EvidenceRow.case_id == CASE, EvidenceRow.filename == filename)
    ).one()


# --- the engine and its filters --------------------------------------------------------------


def test_reads_english_and_chinese_lines_in_order() -> None:
    img = picture(("NotoSans-Regular.ttf", EN), ("NotoSansSC-Regular.ttf", ZH))
    assert ocr.read_text(img) == f"{EN}\n{ZH}"


@pytest.mark.parametrize("line", [
    "Отопление не работает с 3 октября.",  # Cyrillic: the model returns punctuation
    "कृपया मकान मालिक का पता भेजें।",  # Devanagari: low-confidence Latin guesses
])
def test_text_the_model_cannot_read_is_dropped_not_guessed(line: str) -> None:
    assert ocr.read_text(picture(("NotoSans-Regular.ttf", line))) == ""


def test_an_image_without_text_gives_nothing() -> None:
    assert ocr.read_text(Image.new("RGB", (800, 600), (120, 160, 200))) == ""


def test_the_callers_image_is_not_changed() -> None:
    img = picture(("NotoSans-Regular.ttf", EN), size=(3000, 400))
    ocr.read_text(img)
    assert img.size == (3000, 400) and img.mode == "RGB"


def test_the_budget_runs_out() -> None:
    assert ocr.Budget(60).left()
    assert not ocr.Budget(0).left()


# --- photos ------------------------------------------------------------------------------------


def test_a_screenshot_upload_gets_its_text_as_a_cited_page(fresh_db, client, session, ocr_on):
    data = png(picture(("NotoSansSC-Regular.ttf", ZH)))
    r = client.post(EVIDENCE, files=[("file", ("landlord_text.png", data, "image/png"))])
    assert r.status_code == 200, r.text
    row = uploaded(session, "landlord_text.png")
    pages = pages_of(session, row.id)
    assert list(pages) == [exif.PHOTO_LOCATOR, ingest.PHOTO_OCR_LOCATOR]  # capture time first
    assert pages[ingest.PHOTO_OCR_LOCATOR] == ZH
    assert row.processing == "done" and row.error is None


def test_with_ocr_off_a_photo_gets_no_text_page(fresh_db, client, session) -> None:
    data = png(picture(("NotoSans-Regular.ttf", EN)))
    client.post(EVIDENCE, files=[("file", ("off.png", data, "image/png"))])
    assert ingest.PHOTO_OCR_LOCATOR not in pages_of(session, uploaded(session, "off.png").id)


def test_photos_after_the_budget_are_kept_and_say_so() -> None:
    done = ingest._process(png(picture(("NotoSans-Regular.ttf", EN))), "image/png",
                           ocr.Budget(0))
    assert done.processing == "done" and done.error == ingest.OCR_SKIPPED
    assert [p["locator"] for p in done.pages] == [exif.PHOTO_LOCATOR]  # capture time only
    assert done.stripped_sha256 is not None


def test_an_ocr_error_never_fails_the_upload(monkeypatch) -> None:
    def broken(img: Image.Image) -> str:
        raise RuntimeError("engine crashed")

    monkeypatch.setattr(ocr, "read_text", broken)
    done = ingest._process(png(picture(("NotoSans-Regular.ttf", EN))), "image/png",
                           ocr.Budget(60))
    assert done.processing == "done" and done.error is None
    assert all(p["locator"] != ingest.PHOTO_OCR_LOCATOR for p in done.pages)


# --- scanned PDFs ------------------------------------------------------------------------------


def test_a_scanned_page_is_found_only_when_asked() -> None:
    data = scanned_pdf(picture(("NotoSans-Regular.ttf", EN)))
    assert text.read_pdf(data).scans == {}  # the legal source check doesn't want them
    scans = text.read_pdf(data, scans=True).scans
    assert list(scans) == ["page 1"]
    with Image.open(io.BytesIO(scans["page 1"])) as img:
        assert img.format == "PNG" and img.mode == "L"


def test_a_page_with_a_text_layer_is_not_a_scan() -> None:
    from fpdf import FPDF

    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=12)
    pdf.cell(text="Notice of entry: the landlord will enter on Monday at 10 a.m.")
    assert text.read_pdf(bytes(pdf.output()), scans=True).scans == {}


def test_at_most_max_scans_pages_are_taken() -> None:
    blank = picture(("NotoSans-Regular.ttf", "x"))
    data = scanned_pdf(*[blank] * (text.MAX_SCANS + 2))
    assert len(text.read_pdf(data, scans=True).scans) == text.MAX_SCANS


def test_a_scanned_pdf_upload_reads_its_pages(fresh_db, client, session, ocr_on) -> None:
    data = scanned_pdf(picture(("NotoSans-Regular.ttf", EN)),
                       picture(("NotoSansSC-Regular.ttf", ZH)))
    r = client.post(EVIDENCE, files=[("file", ("scan.pdf", data, "application/pdf"))])
    assert r.status_code == 200, r.text
    pages = pages_of(session, uploaded(session, "scan.pdf").id)
    assert pages == {"page 1 (OCR)": EN, "page 2 (OCR)": ZH}


def test_scans_after_the_budget_keep_their_empty_page_and_say_so() -> None:
    pdf = text.read_pdf(scanned_pdf(picture(("NotoSans-Regular.ttf", EN))), scans=True)
    pages, skipped = ingest._ocr_scans(pdf, ocr.Budget(0))
    assert skipped and pages == pdf.pages
