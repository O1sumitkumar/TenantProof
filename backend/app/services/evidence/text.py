"""Text from PDF and TXT evidence, with locators the timeline can cite ("page 3", "message 2").
Ingest stores each one as an `evidence_page` row.

PDF parsing is bounded: at most MAX_PAGES pages, MAX_CHARS characters and PDF_SECONDS of
work (checked between pages). Pages that share one content stream are parsed once."""

import io
import re
import time
from dataclasses import dataclass

from pypdf import PdfReader
from pypdf.generic import ArrayObject, IndirectObject

MAX_PAGES = 300
MAX_CHARS = 1_000_000  # per document
MAX_MESSAGES = 5000
PDF_SECONDS = 10.0
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0e-\x1f\x7f]")

Pages = list[dict[str, str]]


@dataclass(frozen=True)
class PdfText:
    pages: Pages
    software: str | None  # Producer or Creator, shown like a photo's software
    complete: bool  # False when a limit stopped extraction early


def read_pdf(data: bytes) -> PdfText:
    reader = PdfReader(io.BytesIO(data))
    if reader.is_encrypted and not reader.decrypt(""):
        raise ValueError("PDF is password-protected")
    deadline = time.monotonic() + PDF_SECONDS
    seen: dict[tuple[int, ...], str] = {}
    pages: Pages = []
    budget = MAX_CHARS
    complete = len(reader.pages) <= MAX_PAGES
    for number, page in enumerate(reader.pages[:MAX_PAGES], start=1):
        if budget <= 0 or time.monotonic() > deadline:
            complete = False
            break
        key = _contents_key(page.raw_get("/Contents") if "/Contents" in page else None)
        text = seen.get(key) if key else None
        if text is None:
            text = _clean(page.extract_text() or "")
            if key:
                seen[key] = text
        text = text[:budget]
        budget -= len(text)
        pages.append({"locator": f"page {number}", "text": text})
    info = reader.metadata
    producer = (info.producer or info.creator) if info is not None else None
    software = _clean(str(producer)).strip()[:100] if producer else ""
    return PdfText(pages=pages, software=software or None, complete=complete)


def read_txt(data: bytes) -> Pages:
    """One locator per non-empty line ("message 1", "message 2", ...): chat exports put one
    message on each line, and the timeline cites messages by number."""
    text = _clean(data.decode("utf-8-sig"))[:MAX_CHARS]
    # Newlines only: splitlines() would also break on form feeds and U+2028 inside a message.
    lines = [line.strip() for line in re.split(r"\r\n|\r|\n", text) if line.strip()]
    return [{"locator": f"message {n}", "text": line}
            for n, line in enumerate(lines[:MAX_MESSAGES], start=1)]


def _contents_key(raw: object) -> tuple[int, ...]:
    """Identity of a page's content stream(s), so a stream shared by many pages is parsed
    once. Empty when the contents are inline (no reuse possible)."""
    if isinstance(raw, IndirectObject):
        return (raw.idnum, raw.generation)
    if isinstance(raw, ArrayObject) and all(isinstance(r, IndirectObject) for r in raw):
        return tuple(n for r in raw for n in (r.idnum, r.generation))
    return ()


def _clean(text: str) -> str:
    return _CONTROL.sub("", text)
