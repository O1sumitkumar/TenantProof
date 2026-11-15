"""Seeding must never wipe a database that already has data (compose runs it on every start)."""

import pytest
from sqlalchemy import delete
from sqlmodel import Session

from app import seed as seed_module
from app.config import get_settings
from app.db import get_engine
from app.models import OrgRow
from tests.conftest import CASEWORKER, _client

CASE = "case_demo_001"


def _accept(client) -> None:
    r = client.patch("/api/timeline/te_02", json={"review_status": "accepted"})
    assert r.status_code == 200


def _status(client) -> str:
    events = client.get(f"/api/cases/{CASE}/timeline").json()
    return next(e for e in events if e["id"] == "te_02")["review_status"]


def test_seed_skips_a_database_that_already_has_data(fresh_db, client, capsys):
    _accept(client)
    seed_module.main([])
    assert "not seeding" in capsys.readouterr().out
    assert _status(client) == "accepted"  # work survives a restart's seed call


def test_seed_force_wipes_and_reloads(fresh_db, client):
    _accept(client)
    seed_module.main(["--force"])
    assert _status(_client(CASEWORKER)) == "pending"  # new client: --force wipes sessions too


def test_seed_loads_an_empty_database(fresh_db, session):
    with Session(get_engine()) as s:
        for table in seed_module.CHILD_TABLES:
            s.exec(delete(table))  # type: ignore[call-overload]
        s.commit()
        assert seed_module.is_empty(s)
    seed_module.main([])
    session.expire_all()
    assert session.get(OrgRow, "org_harbourside") is not None


def test_seed_needs_a_password_only_when_it_will_seed(fresh_db, monkeypatch):
    monkeypatch.setattr(get_settings(), "seed_password", None)
    seed_module.main([])  # database has data: skipped, no password needed
    with pytest.raises(SystemExit):
        seed_module.main(["--force"])


# --- case_live_001: the synthetic, empty case for the live demo run ----------------------------

LIVE = "case_live_001"


def _live_link(capsys) -> str:
    seed_module.main(["--force"])
    out = capsys.readouterr().out
    line = next(ln for ln in out.splitlines() if ln.startswith("live intake link"))
    return line.rsplit("/", 1)[1]


def test_seed_creates_the_live_case_with_nothing_in_it(fresh_db, session):
    from sqlmodel import func, select

    from app.models import (
        ActivityRow,
        CaseRow,
        EvidencePageRow,
        EvidenceRow,
        FormFieldRow,
        GapRow,
        IntakeTokenRow,
        LegalSourceRow,
        RunRow,
        TimelineEventRow,
    )

    session.expire_all()
    case = session.get(CaseRow, LIVE)
    demo = session.get(CaseRow, CASE)
    assert case is not None and demo is not None
    assert (case.tenant_name, case.tenant_language) == ("Mei Chen", "zh")
    assert case.title == "Water leak and mould on bathroom wall"  # matches the demo photo
    assert (case.org_id, case.assigned_to_id) == (demo.org_id, demo.assigned_to_id)
    assert case.synthetic is True and case.stage == "waiting_tenant"
    assert case.next_deadline is None and case.hearing_date is None

    for table in (EvidenceRow, EvidencePageRow, TimelineEventRow, GapRow, RunRow, FormFieldRow,
                  LegalSourceRow, ActivityRow):
        count = session.exec(
            select(func.count()).select_from(table).where(table.case_id == LIVE)  # type: ignore[attr-defined]
        ).one()
        assert count == 0, table.__name__

    tokens = session.exec(select(IntakeTokenRow).where(IntakeTokenRow.case_id == LIVE)).all()
    assert [t.revoked for t in tokens] == [False]  # its own single active token


def test_the_live_case_is_in_the_caseload_with_no_evidence(fresh_db, client, capsys):
    cases = {c["id"]: c for c in client.get("/api/cases").json()}
    assert cases[LIVE]["tenant_name"] == "Mei Chen" and cases[LIVE]["has_demo_data"] is True
    assert client.get(f"/api/cases/{LIVE}/evidence").json() == []
    assert client.get(f"/api/cases/{LIVE}/timeline").json() == []
    assert client.get(f"/api/cases/{LIVE}/runs/latest").status_code == 404


def test_the_live_case_has_its_own_intake_link_that_is_not_the_demo_cases(
    fresh_db, anon_client, capsys
):
    live = _live_link(capsys)
    view = anon_client.get(f"/api/intake/{live}")
    assert view.status_code == 200 and view.json()["tenant_first_name"] == "Mei"
    assert view.json()["language"] == "zh"


def test_the_demo_case_is_unchanged_by_the_live_case(fresh_db, client):
    assert len(client.get(f"/api/cases/{CASE}/evidence").json()) == 7
    assert len(client.get(f"/api/cases/{CASE}/timeline").json()) == 9
