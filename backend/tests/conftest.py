"""Tests run against a real Postgres (compose locally, service container in CI).
A separate `<db>_test` database is created, migrated with Alembic and seeded."""

import os
import tempfile
from collections.abc import Iterator

import psycopg
import pytest
from psycopg import sql
from sqlalchemy.engine import make_url

_PORT = os.environ.get("POSTGRES_HOST_PORT", "5433")
BASE_URL = os.environ.get(
    "DATABASE_URL", f"postgresql+psycopg://tenantproof:tenantproof@localhost:{_PORT}/tenantproof"
)
_url = make_url(BASE_URL)
TEST_DB = f"{_url.database}_test{os.environ.get('TEST_DB_SUFFIX', '')}"  # suffix: parallel runs
TEST_URL = _url.set(database=TEST_DB).render_as_string(hide_password=False)

os.environ["DATABASE_URL"] = TEST_URL
os.environ["LLM_MODE"] = "fixture"
os.environ["SEED_PASSWORD"] = "test-password-123"
os.environ["RATE_LIMIT_STORAGE_URI"] = "memory://"  # CI has no Redis; counters are per-process
os.environ["STORAGE_DIR"] = tempfile.mkdtemp(prefix="tp-test-storage-")
os.environ.pop("COOKIE_SECURE", None)  # tests run with the secure default
CASEWORKER = "sam@example-clinic.test"
OTHER_CASEWORKER = "jo@harbourside-clinic.test"
PASSWORD = "test-password-123"


def _create_test_db() -> None:
    admin = _url.set(drivername="postgresql").render_as_string(hide_password=False)
    with psycopg.connect(admin, autocommit=True) as conn:
        name = sql.Identifier(TEST_DB)
        conn.execute(sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(name))
        conn.execute(sql.SQL("CREATE DATABASE {}").format(name))


@pytest.fixture(scope="session", autouse=True)
def database() -> Iterator[None]:
    from alembic.config import Config
    from sqlmodel import Session

    from alembic import command
    from app.db import get_engine
    from app.seed import seed

    _create_test_db()
    command.upgrade(Config("alembic.ini"), "head")
    with Session(get_engine()) as session:
        seed(session)
    yield


def _client(email: str | None):
    """https base URL so the Secure session cookie is sent back. email=None: not signed in."""
    from fastapi.testclient import TestClient
    from sqlmodel import Session, select

    from app.auth import make_session_for_tests
    from app.db import get_engine
    from app.main import app
    from app.models import UserRow

    c = TestClient(app, base_url="https://testserver")
    if email:
        with Session(get_engine()) as s:
            user = s.exec(select(UserRow).where(UserRow.email == email)).one()
            c.headers["cookie"] = f"tp_session={make_session_for_tests(s, user.id)}"
    return c


@pytest.fixture(autouse=True)
def reset_rate_limits():
    from app.ratelimit import limiter

    limiter.reset()


@pytest.fixture
def client():
    """Signed in as the seeded caseworker of the demo org."""
    return _client(CASEWORKER)


@pytest.fixture
def anon_client():
    return _client(None)


@pytest.fixture
def other_org_client():
    """Signed in as the caseworker of a different org."""
    return _client(OTHER_CASEWORKER)


@pytest.fixture
def token(client) -> str:
    """A fresh raw intake token for the demo case (revokes any earlier one)."""
    r = client.post("/api/cases/case_demo_001/intake-link")
    assert r.status_code == 200
    return r.json()["url"].rsplit("/", 1)[1]


@pytest.fixture
def session():
    from sqlmodel import Session

    from app.db import get_engine

    with Session(get_engine()) as s:
        yield s


def _reseed() -> None:
    from sqlmodel import Session

    from app.db import get_engine
    from app.seed import seed

    with Session(get_engine()) as s:
        seed(s)


@pytest.fixture
def fresh_db() -> Iterator[None]:
    """Reload the seed data. Request this BEFORE client/token fixtures: reseeding wipes
    sessions and intake tokens. Reseeds again afterwards so no state leaks to later tests."""
    _reseed()
    yield
    _reseed()
