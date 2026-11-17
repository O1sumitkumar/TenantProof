from datetime import date

from app.services.priority import PriorityInput, compute_priority, sort_key

TODAY = date(2026, 11, 6)


def case(**kw):
    base = {"stage": "needs_review", "next_deadline_date": None, "open_blocking": 0,
            "pending_review": 0}
    return PriorityInput(**{**base, **kw})


def test_deadline_within_7_days_is_high():
    r = compute_priority(case(next_deadline_date=date(2026, 11, 8)), TODAY)
    assert r.priority == "high"
    assert r.reason == "Must be received in 2 days (5 days before hearing)"


def test_deadline_exactly_7_days_is_high_and_8_is_normal():
    assert compute_priority(case(next_deadline_date=date(2026, 11, 13)), TODAY).priority == "high"
    assert compute_priority(case(next_deadline_date=date(2026, 11, 14)), TODAY).priority == "normal"


def test_one_day_is_singular():
    r = compute_priority(case(next_deadline_date=date(2026, 11, 7)), TODAY)
    assert "1 day " in r.reason


def test_blocking_gap_with_hearing_is_high_and_reason_combines():
    r = compute_priority(
        case(stage="hearing_scheduled", open_blocking=1, next_deadline_date=date(2026, 11, 8)),
        TODAY,
    )
    assert r.priority == "high"
    assert "and 1 required item open with a hearing scheduled" in r.reason


def test_blocking_gap_without_hearing_is_normal():
    r = compute_priority(case(open_blocking=2, pending_review=7), TODAY)
    assert r.priority == "normal"
    assert r.reason == "7 events to review · 2 required items open"


def test_waiting_tenant_and_empty_reasons():
    waiting = compute_priority(case(stage="waiting_tenant"), TODAY)
    assert "No files from the tenant" in waiting.reason
    assert compute_priority(case(stage="ready_to_file"), TODAY).reason == "No open items"


def test_a_link_never_sent_is_not_called_sent():
    """A case just created (#41) waits for the tenant before any link went out."""
    unsent = compute_priority(case(stage="waiting_tenant", intake_sent=False), TODAY)
    assert unsent.reason == "Intake link not sent yet."
    # a deadline still wins, as for any waiting case
    soon = case(stage="waiting_tenant", intake_sent=False, next_deadline_date=date(2026, 11, 8))
    assert compute_priority(soon, TODAY).reason.startswith("Must be received in 2 days")


def test_overdue_deadline_is_high():
    r = compute_priority(case(next_deadline_date=date(2026, 11, 1)), TODAY)
    assert r.priority == "high"
    assert r.days_to_deadline == -5


def test_sort_order_high_then_deadline_then_blocking():
    keys = [
        ("normal-far", sort_key("normal", 10, 0, 2)),
        ("high-late", sort_key("high", 5, 0, 0)),
        ("high-soon", sort_key("high", 2, 1, 0)),
        ("normal-none-blocking", sort_key("normal", None, 3, 0)),
        ("normal-none", sort_key("normal", None, 0, 0)),
    ]
    assert [n for n, _ in sorted(keys, key=lambda x: x[1])] == [
        "high-soon", "high-late", "normal-far", "normal-none-blocking", "normal-none"]
