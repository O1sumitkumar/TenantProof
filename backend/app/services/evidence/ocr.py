"""Text read from images on this server (OCR), so the agent can cite what a photo of a notice or a
screenshot of a message says. The model still never sees an image: it reads this text, like the
text of a PDF or a chat export.

RapidOCR (Apache-2.0) runs locally with the PP-OCR models bundled in the wheel; nothing is
downloaded and nothing leaves the server. It reads English, Chinese, French and Spanish well. It
does not read Cyrillic or Devanagari: on Russian or Hindi text it returns punctuation or
low-confidence guesses, which the filters below drop, so a misread never becomes evidence.

Callers pass an image that is already decoded, upright and size-checked (the stripped photo, or a
scanned PDF page re-encoded by the PDF child process); this module never parses a file."""

import logging
import re
import threading
import time
from functools import cache
from typing import Any

from PIL import Image

log = logging.getLogger(__name__)

MIN_SCORE = 0.9  # misreads of scripts the model doesn't know score 0.55 to 0.87; real text 0.97+
MIN_LETTERS = 2  # a line of punctuation or one stray character is noise, not text
MAX_SIDE = 2000  # long side for OCR; phone text stays readable and a check takes ~2 s
MAX_LINES = 300
MAX_CHARS = 20_000
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0e-\x1f\x7f]")
_lock = threading.Lock()  # one OCR at a time: bounds CPU use and the engine's memory


@cache
def _engine() -> Any:
    from rapidocr import RapidOCR  # imported on first use: loading the models takes ~1 s

    return RapidOCR(params={"Global.log_level": "warning"})


def read_text(img: Image.Image) -> str:
    """The lines of text in the image, top to bottom, one per line. Empty when there is none, or
    none the model is sure of."""
    rgb = img.convert("RGB")  # a copy: the caller's image is not changed
    rgb.thumbnail((MAX_SIDE, MAX_SIDE))
    with _lock:
        result: Any = _engine()(rgb)
    lines: list[str] = []
    for raw, score in zip(result.txts or (), result.scores or (), strict=False):
        found = str(raw).strip()
        if float(score) >= MIN_SCORE and sum(ch.isalnum() for ch in found) >= MIN_LETTERS:
            lines.append(found)
    return _CONTROL.sub("", "\n".join(lines[:MAX_LINES]))[:MAX_CHARS]


class Budget:
    """Seconds of OCR one upload request may spend. 20 photos at ~2 s each would hold the
    request (and the tenant's phone) for most of a minute, and a proxy may cut it off. Images
    after the budget is spent are kept without their text, and the evidence says so."""

    def __init__(self, seconds: float) -> None:
        self._deadline = time.monotonic() + seconds

    def left(self) -> bool:
        return time.monotonic() < self._deadline
