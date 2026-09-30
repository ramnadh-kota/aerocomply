"""Durable job queue: idempotent enqueue, race-safe claim, retry/backoff, dead-letter, stale reclaim,
tenant isolation of job status, graceful worker shutdown, and async ingest end to end."""
from __future__ import annotations

import threading
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.background_job import BackgroundJob, JobStatus
from app.models.organization import Organization
from app.models.telemetry import TelemetryEventLog
from app.services import job_handlers, job_service
from app.worker import run_worker
from tests.integration.test_acquisition_pipeline import _csv, _drone, _org, _source


def _job(db, **kw):
    kw.setdefault("job_type", "test.job")
    job, _ = job_service.enqueue(db, **kw)
    db.flush()
    return job


@pytest.fixture
def handlers():
    calls = {"n": 0}

    def ok(db, job):
        calls["n"] += 1
        return {"done": True}

    def flaky(db, job):
        calls["n"] += 1
        raise RuntimeError("boom")

    def permanent(db, job):
        raise job_service.NonRetryableJobError("bad input")

    job_service.register_handler("test.ok", ok)
    job_service.register_handler("test.flaky", flaky)
    job_service.register_handler("test.permanent", permanent)
    yield calls
    for t in ("test.ok", "test.flaky", "test.permanent"):
        job_service._HANDLERS.pop(t, None)


def test_enqueue_is_idempotent_and_scoped_per_organization(db_session):
    org_a = Organization(name=f"a-{uuid.uuid4().hex[:6]}")
    org_b = Organization(name=f"b-{uuid.uuid4().hex[:6]}")
    db_session.add_all([org_a, org_b])
    db_session.flush()
    j1, c1 = job_service.enqueue(db_session, job_type="t", organization_id=org_a.id, idempotency_key="k1")
    j2, c2 = job_service.enqueue(db_session, job_type="t", organization_id=org_a.id, idempotency_key="k1")
    j3, c3 = job_service.enqueue(db_session, job_type="t", organization_id=org_b.id, idempotency_key="k1")
    assert (c1, c2, c3) == (True, False, True)
    assert j1.id == j2.id and j3.id != j1.id          # same key in another tenant is a different job


def test_success_clears_raw_payload_and_records_result(db_session, handlers):
    job = _job(db_session, job_type="test.ok", payload_blob=b"raw-bytes")
    assert job_service.run_one(db_session, worker_id="w1") is True
    db_session.refresh(job)
    assert job.status == JobStatus.SUCCEEDED and job.result == {"done": True}
    assert job.payload_blob is None and job.attempts == 1


def test_failure_retries_with_exponential_backoff_then_dead_letters(db_session, handlers):
    job = _job(db_session, job_type="test.flaky", max_attempts=3)
    seen = []
    for expected in (JobStatus.QUEUED, JobStatus.QUEUED, JobStatus.DEAD):
        db_session.execute(BackgroundJob.__table__.update().where(BackgroundJob.id == job.id).values(
            run_after=datetime.now(UTC) - timedelta(seconds=1)))   # skip waiting for the backoff
        assert job_service.run_one(db_session, worker_id="w1")
        db_session.refresh(job)
        assert job.status == expected
        seen.append(job.run_after)
    assert job.attempts == 3 and "RuntimeError" in job.last_error and job.finished_at is not None
    assert handlers["n"] == 3
    # dead jobs are never claimed again...
    assert job_service.run_one(db_session, worker_id="w1") is False
    # ...until an operator requeues them
    job_service.requeue_dead(db_session, job)
    assert job.status == JobStatus.QUEUED and job.attempts == 0


def test_backoff_grows_and_is_capped():
    a1, a2, a4 = (job_service.backoff_seconds(n) for n in (1, 2, 4))
    assert 3.7 <= a1 <= 6.3 and 7.5 <= a2 <= 12.5 and 30 <= a4 <= 50
    assert job_service.backoff_seconds(30) <= job_service.BACKOFF_CAP_SECONDS * 1.25


def test_non_retryable_error_goes_straight_to_dead_letter(db_session, handlers):
    job = _job(db_session, job_type="test.permanent", max_attempts=5)
    job_service.run_one(db_session, worker_id="w1")
    db_session.refresh(job)
    assert job.status == JobStatus.DEAD and job.attempts == 1


def test_unknown_job_type_is_dead_lettered_not_lost(db_session):
    job = _job(db_session, job_type="nobody.handles.this")
    job_service.run_one(db_session, worker_id="w1")
    db_session.refresh(job)
    assert job.status == JobStatus.DEAD and "no handler" in job.last_error


def test_future_jobs_are_not_claimed_and_stale_running_jobs_are_reclaimed(db_session, handlers):
    later = _job(db_session, job_type="test.ok", run_after=datetime.now(UTC) + timedelta(hours=1))
    assert job_service.run_one(db_session, worker_id="w1") is False
    stuck = _job(db_session, job_type="test.ok")
    stuck.status, stuck.locked_at, stuck.locked_by = JobStatus.RUNNING, datetime.now(UTC) - timedelta(hours=1), "dead-worker"
    db_session.flush()
    assert job_service.reclaim_stale(db_session) == 1
    db_session.refresh(stuck)
    assert stuck.status == JobStatus.QUEUED and stuck.locked_by is None
    fresh = _job(db_session, job_type="test.ok")
    fresh.status, fresh.locked_at = JobStatus.RUNNING, datetime.now(UTC)
    db_session.flush()
    assert job_service.reclaim_stale(db_session) == 0     # a live worker's job is left alone
    assert later.status == JobStatus.QUEUED


def test_concurrent_workers_never_claim_the_same_job(engine):
    """Real parallel sessions on committed rows: SKIP LOCKED must hand each job to exactly one worker."""
    tag = uuid.uuid4().hex[:8]
    with Session(engine) as s:
        for i in range(12):
            job_service.enqueue(s, job_type="race.job", idempotency_key=f"{tag}-{i}")
        s.commit()
    claimed: list[uuid.UUID] = []
    lock = threading.Lock()
    barrier = threading.Barrier(4)

    def work(n: int) -> None:
        with Session(engine) as s:
            barrier.wait(timeout=10)
            while True:
                job = job_service.claim_next(s, worker_id=f"w{n}", job_types=["race.job"])
                if job is None:
                    break
                with lock:
                    claimed.append(job.id)
                s.commit()

    threads = [threading.Thread(target=work, args=(n,)) for n in range(4)]
    [t.start() for t in threads]
    [t.join(timeout=30) for t in threads]
    assert len(claimed) == 12 and len(set(claimed)) == 12
    with Session(engine) as s:  # leave nothing claimable behind for other tests
        s.execute(BackgroundJob.__table__.update().where(BackgroundJob.job_type == "race.job").values(status=JobStatus.CANCELED))
        s.commit()


def test_worker_processes_queue_and_stops_gracefully(db_session, handlers):
    for _ in range(3):
        _job(db_session, job_type="test.ok")
    db_session.commit()
    stop = threading.Event()
    n = run_worker(stop, session_factory=lambda: _NoCloseSession(db_session), once=True, job_types=["test.ok"])
    assert n == 3 and handlers["n"] == 3
    stop.set()   # a set stop event ends the loop without touching the queue
    _job(db_session, job_type="test.ok")
    assert run_worker(stop, session_factory=lambda: _NoCloseSession(db_session), job_types=["test.ok"]) == 0


class _NoCloseSession:
    """Lets run_worker reuse the test's transaction-wrapped session (its `with` would otherwise close it)."""

    def __init__(self, s):
        self.s = s

    def __enter__(self):
        return self.s

    def __exit__(self, *a):
        return False


def test_async_ingest_enqueues_202_then_worker_ingests_idempotently(client, db_session):
    org_id, h = _org(client, db_session, "async")
    _drone(client, h, reg="ASYNC-1")
    sid = _source(client, h, "CSV_BATCH")
    body = _csv([{"asset_id": "ASYNC-1", "sensor_code": "TEMP", "value": "31.5", "unit": "C",
                  "timestamp": "2026-01-01T00:00:00Z"}])
    r = client.post(f"/api/v1/data-sources/{sid}/ingest?mode=async", headers={**h, "Idempotency-Key": "batch-1"}, content=body)
    assert r.status_code == 202, r.text
    job_id = r.json()["job_id"]
    assert client.post(f"/api/v1/data-sources/{sid}/ingest?mode=async", headers={**h, "Idempotency-Key": "batch-1"},
                       content=body).json() == {"job_id": job_id, "status": "QUEUED", "duplicate": True}
    # nothing was ingested by the API request itself
    assert db_session.execute(select(TelemetryEventLog).where(TelemetryEventLog.organization_id == org_id)).first() is None
    assert client.get(f"/api/v1/data-sources/jobs/{job_id}", headers=h).json()["status"] == "QUEUED"

    assert job_service.run_one(db_session, worker_id="w1", job_types=[job_handlers.INGEST])
    st = client.get(f"/api/v1/data-sources/jobs/{job_id}", headers=h).json()
    assert st["status"] == "SUCCEEDED" and st["result"]["accepted"] == 1
    rows = db_session.execute(select(TelemetryEventLog).where(TelemetryEventLog.organization_id == org_id)).scalars().all()
    assert len(rows) == 1 and rows[0].processing_status == "PROCESSED"


def test_async_ingest_is_tenant_isolated(client, db_session):
    _, h1 = _org(client, db_session, "iso1")
    _, h2 = _org(client, db_session, "iso2")
    sid1 = _source(client, h1, "CSV_BATCH")
    other = client.post(f"/api/v1/data-sources/{sid1}/ingest?mode=async", headers=h2, content=b"a,b\n1,2\n")
    assert other.status_code == 404                       # foreign source: refused before anything is queued
    mine = client.post(f"/api/v1/data-sources/{sid1}/ingest?mode=async", headers=h1, content=b"a,b\n1,2\n").json()
    assert client.get(f"/api/v1/data-sources/jobs/{mine['job_id']}", headers=h2).status_code == 404
    assert client.get(f"/api/v1/data-sources/jobs/{mine['job_id']}", headers=h1).status_code == 200


def test_async_ingest_to_missing_source_and_empty_payload(client, db_session):
    _, h = _org(client, db_session, "asy2")
    sid = _source(client, h, "CSV_BATCH")
    assert client.post(f"/api/v1/data-sources/{uuid.uuid4()}/ingest?mode=async", headers=h, content=b"x").status_code == 404
    assert client.post(f"/api/v1/data-sources/{sid}/ingest?mode=async", headers=h, content=b"").status_code == 422
    assert client.post(f"/api/v1/data-sources/{sid}/ingest?mode=bogus", headers=h, content=b"x").status_code == 422


def test_platform_can_inspect_dead_letters_and_requeue_but_tenants_cannot(client, db_session):
    from tests.integration.conftest import make_platform_admin_headers

    pa = make_platform_admin_headers(client, db_session)
    _, tenant = _org(client, db_session, "dlq")
    dead = _job(db_session, job_type="nobody.handles.this")
    job_service.run_one(db_session, worker_id="w1")
    db_session.refresh(dead)
    assert dead.status == JobStatus.DEAD

    listing = client.get("/api/v1/platform/jobs?status=DEAD", headers=pa).json()
    assert any(i["job_id"] == str(dead.id) for i in listing["items"]) and listing["counts"]["DEAD"] >= 1
    assert client.get("/api/v1/platform/jobs?status=NOPE", headers=pa).status_code == 422
    assert client.get("/api/v1/platform/jobs", headers=tenant).status_code == 403          # RBAC
    assert client.post(f"/api/v1/platform/jobs/{dead.id}/requeue", headers=tenant).status_code == 403

    r = client.post(f"/api/v1/platform/jobs/{dead.id}/requeue", headers=pa)
    assert r.status_code == 200 and r.json()["status"] == "QUEUED"
    assert client.post(f"/api/v1/platform/jobs/{dead.id}/requeue", headers=pa).status_code == 409   # no longer DEAD
    assert 'kota_job_queue{status="QUEUED"}' in client.get("/api/v1/platform/metrics", headers=pa).text


def test_failure_evidence_written_by_the_after_rollback_hook_survives_the_handlers_rollback(db_session):
    """A raising handler loses its own writes (SAVEPOINT), so failure evidence must go through the hook."""
    org = Organization(name=f"hook-{uuid.uuid4().hex[:6]}")
    db_session.add(org)
    db_session.flush()

    def handler(db, job):
        org.name = "written-then-rolled-back"
        db.flush()

        def hook(session):
            session.get(Organization, org.id).name = "evidence-survives"
        raise job_service.NonRetryableJobError("nope", after_rollback=hook)

    job_service.register_handler("test.hook", handler)
    try:
        job, _ = job_service.enqueue(db_session, job_type="test.hook", organization_id=org.id)
        job_service.run_one(db_session, worker_id="w", job_types=["test.hook"])
    finally:
        job_service._HANDLERS.pop("test.hook", None)
    db_session.refresh(org)
    db_session.refresh(job)
    assert org.name == "evidence-survives" and job.status == JobStatus.DEAD
