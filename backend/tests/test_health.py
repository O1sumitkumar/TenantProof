"""WS2: /healthz checks the dependencies a request needs — Postgres and Redis — and answers
503 when either is down, so a proxy or platform keeps a broken replica out of rotation."""


def test_healthz_reports_each_dependency(anon_client):
    r = anon_client.get("/healthz")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "db": "ok", "redis": "ok", "llm_mode": "fixture"}


def test_healthz_is_503_when_postgres_is_down(anon_client, monkeypatch):
    monkeypatch.setattr("app.main._db_reachable", lambda: False)
    r = anon_client.get("/healthz")
    assert r.status_code == 503
    assert r.json() == {
        "status": "degraded",
        "db": "error",
        "redis": "ok",
        "llm_mode": "fixture",
    }


def test_healthz_is_503_when_redis_is_down(anon_client, monkeypatch):
    monkeypatch.setattr("app.main._redis_reachable", lambda: False)
    r = anon_client.get("/healthz")
    assert r.status_code == 503
    assert r.json()["status"] == "degraded"
    assert r.json()["db"] == "ok"
    assert r.json()["redis"] == "error"
