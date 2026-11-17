"""Issue #10: an intake upload with a bad token is refused before its body is read."""

import asyncio

from app.services import intake_gate
from app.services.intake_gate import IntakeTokenGate


def _run(path: str = "/api/intake/tok/files") -> tuple[list[dict], int, bool]:
    """Run the gate with a body of one chunk. Returns messages sent, chunks read, app ran."""
    state = {"read": 0, "app": False}
    sent: list[dict] = []

    async def receive():
        state["read"] += 1
        return {"type": "http.request", "body": b"x" * 10, "more_body": True}

    async def send(message):
        sent.append(message)

    async def app(scope, receive, send):
        state["app"] = True
        message = await receive()
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": message.get("body", b"")})

    scope = {"type": "http", "method": "POST", "path": path, "headers": []}
    asyncio.run(IntakeTokenGate(app)(scope, receive, send))
    return sent, state["read"], state["app"]


def test_a_bad_token_is_404_without_reading_the_body(monkeypatch):
    monkeypatch.setattr(intake_gate, "token_is_active", lambda token: False)

    sent, read, ran = _run()

    assert read == 0 and not ran  # nothing of a 501 MB body touches this replica
    assert sent[0]["type"] == "http.response.start" and sent[0]["status"] == 404
    assert b"Link not found" in sent[1]["body"]


def test_a_good_token_reaches_the_app(monkeypatch):
    monkeypatch.setattr(intake_gate, "token_is_active", lambda token: True)

    sent, read, ran = _run()

    assert ran and read == 1
    assert sent[0]["status"] == 200


def test_other_uploads_are_not_gated(monkeypatch):
    checked: list[str] = []

    def record(token: str) -> bool:
        checked.append(token)
        return False

    monkeypatch.setattr(intake_gate, "token_is_active", record)

    sent, _, ran = _run("/api/cases/case_demo_001/evidence")

    assert ran and checked == []
    assert sent[0]["status"] == 200
