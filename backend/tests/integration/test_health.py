def test_liveness(client):
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_readiness_checks_database(client):
    resp = client.get("/api/v1/health/ready")
    assert resp.status_code == 200
    assert resp.json()["database"] == "reachable"


def test_database_engine_has_a_bounded_connect_timeout():
    """Regression test for a confirmed defect found while manually
    verifying /health/ready during the production-readiness sprint: with
    no connect_timeout, a genuinely unreachable database (exactly what
    /health/ready exists to detect) made the request hang for tens of
    seconds — the platform's default TCP timeout — instead of failing
    within the few-second window most orchestrators allow a readiness
    probe. Verified manually end-to-end (stopped Postgres, confirmed
    /health/ready then returned in ~5s instead of hanging).

    SQLAlchemy doesn't expose connect_args back off an already-built
    Engine in a stable public way, so this asserts on the module source
    instead of internals — a plain, reliable guard against the line being
    accidentally removed. Deliberately does NOT connect through the
    module-level `engine` global: it's built from `settings.database_url`
    at import time, which in CI's test step is only ever the (unreachable)
    default — every other test talks to the database exclusively through
    the `db_session`/`client` fixtures' own connection instead.
    """
    import inspect

    from app.db import session as session_module

    source = inspect.getsource(session_module)
    assert "connect_timeout" in source, (
        "app/db/session.py must set a bounded connect_timeout on the engine — "
        "without it, /health/ready (and every other request needing a fresh "
        "DB connection) hangs for the platform's default TCP timeout when "
        "the database is unreachable, instead of failing fast."
    )


def test_readiness_reports_schema_and_job_health(client):
    body = client.get("/api/v1/health/ready").json()
    assert body["status"] == "ok" and body["database"] == "reachable"
    assert body["schema"]["up_to_date"] is True and body["schema"]["current"] == body["schema"]["expected"]
    assert set(body["jobs"]) == {"queued", "dead", "oldest_due_seconds"}


def test_readiness_is_503_when_the_schema_is_behind_the_release(client, monkeypatch):
    from app.api.v1 import health

    monkeypatch.setattr(health, "expected_schema_heads", lambda: ("9999",))
    r = client.get("/api/v1/health/ready")
    assert r.status_code == 503 and r.json()["status"] == "schema_mismatch" and r.json()["schema"]["up_to_date"] is False


def test_readiness_is_503_when_the_database_is_down(client, db_session, monkeypatch):
    from app.core.deps import get_db_session
    from app.main import app

    class Dead:
        def execute(self, *a, **k):
            raise RuntimeError("db down")

    def dead():
        yield Dead()

    app.dependency_overrides[get_db_session] = dead
    try:
        r = client.get("/api/v1/health/ready")
        assert r.status_code == 503 and r.json() == {"status": "unavailable", "database": "unreachable"}
    finally:
        app.dependency_overrides.pop(get_db_session, None)
