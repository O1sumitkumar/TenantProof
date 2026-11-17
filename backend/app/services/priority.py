"""Caseload priority rules (BUILD_PLAN section 6). Pure: no I/O, no LLM."""

from dataclasses import dataclass
from datetime import date

from app.services.legal.corpus import EVIDENCE_DAYS_BEFORE_HEARING

EVIDENCE_WINDOW_DAYS = 7


@dataclass(frozen=True)
class PriorityInput:
    stage: str
    next_deadline_date: date | None
    open_blocking: int
    pending_review: int


@dataclass(frozen=True)
class PriorityResult:
    priority: str
    reason: str
    days_to_deadline: int | None


def days_until(deadline: date | None, today: date) -> int | None:
    return None if deadline is None else (deadline - today).days


def _plural(n: int, word: str) -> str:
    return f"{n} {word}" if n == 1 else f"{n} {word}s"


def compute_priority(case: PriorityInput, today: date) -> PriorityResult:
    days = days_until(case.next_deadline_date, today)
    priority = "normal"
    reason: str | None = None

    if days is not None and days <= EVIDENCE_WINDOW_DAYS:
        priority = "high"
        reason = (
            f"Must be received in {_plural(days, 'day')} "
            f"({EVIDENCE_DAYS_BEFORE_HEARING} days before hearing)"
        )
    if case.open_blocking and case.stage == "hearing_scheduled":
        priority = "high"
        blocked = f"{case.open_blocking} required item open with a hearing scheduled"
        reason = f"{reason} and {blocked}" if reason else blocked

    if reason is None:
        if case.stage == "waiting_tenant":
            reason = "Intake link sent. No files from the tenant yet."
        elif days is not None:
            reason = f"Must be received in {days} days"
        elif case.open_blocking or case.pending_review:
            reason = (
                f"{case.pending_review} events to review · {case.open_blocking} required items open"
            )
        else:
            reason = "No open items"
    return PriorityResult(priority, reason, days)


def sort_key(priority: str, days: int | None, open_blocking: int, pending_review: int):
    """High first, then nearest deadline, then most blocking, then most pending."""
    return (0 if priority == "high" else 1, days if days is not None else 999,
            -open_blocking, -pending_review)
