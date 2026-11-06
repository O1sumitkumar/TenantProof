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
