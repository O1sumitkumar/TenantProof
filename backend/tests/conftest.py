"""Tests run against a real Postgres (compose locally, service container in CI).
A separate `<db>_test` database is created, migrated with Alembic and seeded."""

import os
from collections.abc import Iterator

import psycopg
import pytest
from psycopg import sql
from sqlalchemy.engine import make_url

BASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql+psycopg://tenantproof:tenantproof@localhost:5433/tenantproof"
)
_url = make_url(BASE_URL)
TEST_DB = f"{_url.database}_test"
TEST_URL = _url.set(database=TEST_DB).render_as_string(hide_password=False)

os.environ["DATABASE_URL"] = TEST_URL
os.environ["DEV_STUB_AUTH"] = "true"
os.environ["LLM_MODE"] = "fixture"


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


@pytest.fixture
def client():
    from fastapi.testclient import TestClient

    from app.main import app

    return TestClient(app)


@pytest.fixture
def session():
    from sqlmodel import Session

    from app.db import get_engine

    with Session(get_engine()) as s:
        yield s
