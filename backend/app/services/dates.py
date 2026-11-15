"""Date choice and date flags (BUILD_PLAN section 6). Pure: no I/O, no LLM.

The model proposes date candidates; this module picks one and decides the flags."""

from datetime import date

from app.schemas import EventDate

# Highest priority first. `user` is only ever set by a caseworker, never by the agent.
BASIS_PRIORITY = ("message_timestamp", "exif", "document_text", "filename", "user")
_PRECISION_RANK = {"day": 0, "month": 1, "unknown": 2}


def _rank(candidate: EventDate) -> tuple[int, int]:
    return BASIS_PRIORITY.index(candidate.basis), _PRECISION_RANK[candidate.precision]


def choose_date(candidates: list[EventDate]) -> EventDate:
    """The candidate with the best basis; a day beats a month on the same basis; the earlier
    listed wins a tie. Candidates with an unknown date are chosen only when nothing else is."""
    known = [c for c in candidates if c.precision != "unknown"]
    pool = known or candidates
    return min(pool, key=_rank)  # min() keeps the first of equal keys


def _as_date(candidate: EventDate) -> date | None:
    if candidate.value is None or candidate.precision != "day":
        return None
    return date.fromisoformat(candidate.value)


def _month(candidate: EventDate) -> str | None:
    return None if candidate.value is None else candidate.value[:7]


def date_mismatch(candidates: list[EventDate]) -> bool:
    """True when two known candidates disagree: day precision on both and more than 1 day
    apart, or any month precision and different months."""
    known = [c for c in candidates if c.precision != "unknown" and c.value is not None]
    for i, a in enumerate(known):
        for b in known[i + 1 :]:
            if a.precision == "day" and b.precision == "day":
                da, db = _as_date(a), _as_date(b)
                if da is not None and db is not None and abs((da - db).days) > 1:
                    return True
            elif _month(a) != _month(b):
                return True
    return False


def date_inferred(chosen: EventDate) -> bool:
    """The date comes from a filename, not from the content or metadata."""
    return chosen.basis == "filename"


def exif_matches(candidate: EventDate, captured_times: list[str]) -> bool:
    """An `exif` date must be the capture date of one of the cited files (ISO timestamps)."""
    if candidate.value is None:
        return False
    size = 10 if candidate.precision == "day" else 7
    return any(t[:size] == candidate.value for t in captured_times)
