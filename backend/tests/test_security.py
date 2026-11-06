"""Org isolation, intake-token hardening and internal-note leakage."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlmodel import Session, select

from app.config import get_settings
from app.db import get_engine
from app.main import api
from app.models import CaseRow, GapRow, OrgRow, TimelineEventRow, UserRow
from app.services.intake_token import hash_token, make_token

CASE = "case_demo_001"
OTHER_EMAIL = "other@other-clinic.test"


@pytest.fixture
def other_org_client(client):
    """A caseworker from a different org."""
    with Session(get_engine()) as s:
        if s.get(OrgRow, "org_other") is None:
            s.add(OrgRow(id="org_other", name="Other Clinic"))
            s.add(UserRow(id="usr_other", org_id="org_other", name="Olu", email=OTHER_EMAIL))
            s.commit()
    base = get_settings()
    api.dependency_overrides[get_settings] = lambda: base.model_copy(
        update={"dev_user_email": OTHER_EMAIL})
    yield client
    api.dependency_overrides.clear()


@pytest.mark.parametrize(
    "path",
    ["", "/evidence", "/timeline", "/gaps", "/sources", "/form-draft", "/activity",
     "/runs/latest"],
)
def test_other_org_gets_404_on_case_endpoints(other_org_client, path):
    assert other_org_client.get(f"/api/cases/{CASE}{path}").status_code == 404


def test_other_org_cannot_read_run_by_id(other_org_client):
    assert other_org_client.get("/api/runs/run_001").status_code == 404


def test_other_org_caseload_is_empty(other_org_client):
    assert other_org_client.get("/api/cases").json() == []


def test_no_auth_by_default(client):
    base = get_settings()
    api.dependency_overrides[get_settings] = lambda: base.model_copy(
        update={"dev_stub_auth": False})
    try:
        assert client.get("/api/cases").status_code == 401
        assert client.get("/api/me").status_code == 401
    finally:
        api.dependency_overrides.clear()


def test_intake_rejects_wrong_forged_and_revoked_tokens(client):
    assert client.get("/api/intake/not-a-token").status_code == 404
    settings = get_settings()
    # Token for the right case but a bumped version is not the stored one -> revoked.
    old = make_token(settings.secret_key, CASE, 1)
    with Session(get_engine()) as s:
        case = s.get(CaseRow, CASE)
        assert case is not None and case.intake_token_hash == hash_token(old)
        case.intake_token_version = 2
        s.add(case)
        s.commit()
    try:
        assert client.get(f"/api/intake/{old}").status_code == 404
    finally:
        with Session(get_engine()) as s:
            case = s.get(CaseRow, CASE)
            assert case is not None
            case.intake_token_version = 1
            s.add(case)
            s.commit()


def test_intake_token_expires(client):
    token = client.get(f"/api/cases/{CASE}").json()["intake"]["url"].rsplit("/", 1)[1]
    with Session(get_engine()) as s:
        case = s.get(CaseRow, CASE)
        assert case is not None
        original = case.intake_expires_at
        case.intake_expires_at = datetime.now(UTC) - timedelta(days=1)
        s.add(case)
        s.commit()
    try:
        assert client.get(f"/api/intake/{token}").status_code == 404
    finally:
        with Session(get_engine()) as s:
            case = s.get(CaseRow, CASE)
            assert case is not None
            case.intake_expires_at = original
            s.add(case)
            s.commit()


def test_caseworker_note_never_in_form_or_tenant_view(client, session):
    note = "INTERNAL-ONLY-NOTE-XYZ"
    ev = session.get(TimelineEventRow, "te_03")
    assert ev is not None and ev.caseworker_note  # seed has one on an accepted event
    ev.caseworker_note = note
    session.add(ev)
    session.commit()
    form = client.get(f"/api/cases/{CASE}/form-draft").text
    token = client.get(f"/api/cases/{CASE}").json()["intake"]["url"].rsplit("/", 1)[1]
    tenant = client.get(f"/api/intake/{token}").text
    assert note not in form
    assert note not in tenant
    assert "caseworker_note" not in tenant


def test_tenant_view_only_lists_waiting_tenant_requests(client, session):
    token = client.get(f"/api/cases/{CASE}").json()["intake"]["url"].rsplit("/", 1)[1]
    assert client.get(f"/api/intake/{token}").json()["requests"] == []
    gap = session.exec(select(GapRow).where(GapRow.id == "gap_01")).one()
    gap.status = "waiting_tenant"
    session.add(gap)
    session.commit()
    try:
        reqs = client.get(f"/api/intake/{token}").json()["requests"]
        assert [r["id"] for r in reqs] == ["gap_01"]
        assert set(reqs[0]) == {"id", "message"}  # no message_en: English is for the caseworker
    finally:
        gap.status = "open"
        session.add(gap)
        session.commit()
