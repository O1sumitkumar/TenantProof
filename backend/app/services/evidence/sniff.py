"""Decide a file's type from its bytes, never from its name or the Content-Type header.

Pure Python on purpose: python-magic needs the native libmagic library, which Windows machines
don't have without a system-wide install (AGENTS.md forbids those). Five allowed types need
only their signatures."""

from typing import BinaryIO

JPEG = "image/jpeg"
PNG = "image/png"
HEIC = "image/heic"
PDF = "application/pdf"
TEXT = "text/plain"

ALLOWED = (JPEG, PNG, HEIC, PDF, TEXT)
ALLOWED_LABEL = "JPG, PNG, HEIC, PDF or TXT"

HEAD = 16  # enough for every signature below
# ISO base media "ftyp" major brands used by HEIC/HEIF stills from phones.
_HEIC_BRANDS = {b"heic", b"heix", b"heim", b"heis", b"hevc", b"hevx", b"mif1", b"msf1"}
# Control characters allowed in a text file: tab, line feed, form feed, carriage return.
_TEXT_CONTROLS = {0x09, 0x0A, 0x0C, 0x0D}


def sniff(data: bytes) -> str | None:
    """Return the MIME type if `data` is one of the allowed types, else None."""
    return _by_signature(data[:HEAD]) or (TEXT if _is_text(data) else None)


def sniff_file(source: BinaryIO, max_bytes: int) -> str | None:
    """Like sniff(), reading only the head unless the file can only be text. Rewinds."""
    source.seek(0)
    mime = _by_signature(source.read(HEAD))
    if mime is None:
        source.seek(0)
        mime = TEXT if _is_text(source.read(max_bytes)) else None
    source.seek(0)
    return mime


def _by_signature(head: bytes) -> str | None:
    if head.startswith(b"\xff\xd8\xff"):
        return JPEG
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return PNG
    if head.startswith(b"%PDF-"):
        return PDF
    if len(head) >= 12 and head[4:8] == b"ftyp" and head[8:12] in _HEIC_BRANDS:
        return HEIC
    return None


def _is_text(data: bytes) -> bool:
    """UTF-8 text with no binary control characters. Empty files are not evidence."""
    if not data:
        return False
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return False
    return not any(ord(c) < 0x20 and ord(c) not in _TEXT_CONTROLS or c == "\x7f" for c in text)
