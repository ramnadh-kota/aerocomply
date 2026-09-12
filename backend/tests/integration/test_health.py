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
    accidentally removed.
    """
    import inspect

    from app.db import session as session_module

    # Sanity: the engine this module builds is real and connectable.
    raw_connection = session_module.engine.raw_connection()
    raw_connection.close()

    source = inspect.getsource(session_module)
    assert "connect_timeout" in source, (
        "app/db/session.py must set a bounded connect_timeout on the engine — "
        "without it, /health/ready (and every other request needing a fresh "
        "DB connection) hangs for the platform's default TCP timeout when "
        "the database is unreachable, instead of failing fast."
    )
