"""Durable background jobs: enqueue, claim, complete/fail with exponential backoff, dead-letter, stale reclaim.

Semantics (at-least-once, made effectively-once by idempotent handlers):
* enqueue(..., idempotency_key=K) twice returns the SAME job (unique (job_type, dedupe_key)); safe under races.
* claim_next uses FOR UPDATE SKIP LOCKED so concurrent workers never take the same job.
* A failing handler is retried after base * 2**(attempts-1) seconds (capped, jittered); after max_attempts, or on a
  NonRetryableJobError, the job becomes DEAD (dead-letter) and stays for an operator to inspect / requeue.
* A worker that dies mid-job leaves it RUNNING; reclaim_stale returns it to QUEUED after the visibility timeout.
* Every job carries organization_id, data_source_id and the originating correlation id; the worker binds them into
  the log context. Payloads and raw bytes are never logged.
"""
from __future__ import annotations

import random
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.core.metrics import REGISTRY, Counter, Gauge
from app.models.background_job import BackgroundJob, JobStatus

log = structlog.get_logger(__name__)

JOBS = REGISTRY.register(Counter("kota_jobs_total", "Job attempts by type and outcome (succeeded/retry/dead)"))
QUEUE_DEPTH = REGISTRY.register(Gauge("kota_job_queue", "Jobs by status (refreshed on scrape)"))

BACKOFF_BASE_SECONDS = 5.0
BACKOFF_CAP_SECONDS = 900.0
VISIBILITY_TIMEOUT = timedelta(minutes=10)
_MAX_ERROR = 512


class JobError(Exception):
    """Handler failure that carries an `after_rollback(db)` hook. A raising handler has its writes rolled back (its
    SAVEPOINT), so anything that must SURVIVE the failure (e.g. 'last_error' on a data source) goes in the hook, which
    the runner calls after the rollback and before recording the outcome."""

    def __init__(self, message: str = "", *, after_rollback: "Callable[[Session], None] | None" = None) -> None:
        super().__init__(message)
        self.after_rollback = after_rollback


class NonRetryableJobError(JobError):
    """Handler signals a permanent failure (bad input, unknown source): go straight to dead-letter."""


class RetryableJobError(JobError):
    """Transient failure: retried with backoff (like any other exception, plus the after_rollback hook)."""


Handler = Callable[[Session, BackgroundJob], "dict[str, Any] | None"]
_HANDLERS: dict[str, Handler] = {}


def register_handler(job_type: str, handler: Handler) -> None:
    _HANDLERS[job_type] = handler


def handler_for(job_type: str) -> Handler | None:
    return _HANDLERS.get(job_type)


def _now() -> datetime:
    return datetime.now(UTC)


def _dedupe(organization_id: uuid.UUID | None, idempotency_key: str | None) -> str:
    return f"{organization_id or 'platform'}:{idempotency_key or uuid.uuid4().hex}"[:200]


def enqueue(
    db: Session,
    *,
    job_type: str,
    organization_id: uuid.UUID | None = None,
    data_source_id: uuid.UUID | None = None,
    payload: dict[str, Any] | None = None,
    payload_blob: bytes | None = None,
    idempotency_key: str | None = None,
    max_attempts: int = 5,
    run_after: datetime | None = None,
    correlation_id: str | None = None,
) -> tuple[BackgroundJob, bool]:
    """Returns (job, created). `created` is False when the idempotency key already exists."""
    if correlation_id is None:
        ctx = structlog.contextvars.get_contextvars()
        correlation_id = str(ctx.get("request_id") or "")[:64] or None
    dedupe = _dedupe(organization_id, idempotency_key)
    stmt = (
        pg_insert(BackgroundJob)
        .values(
            organization_id=organization_id, data_source_id=data_source_id, job_type=job_type,
            status=JobStatus.QUEUED, payload=payload or {}, payload_blob=payload_blob, dedupe_key=dedupe,
            correlation_id=correlation_id, attempts=0, max_attempts=max_attempts, run_after=run_after or _now(),
        )
        .on_conflict_do_nothing(constraint="uq_background_jobs_type_dedupe")
        .returning(BackgroundJob.id)
    )
    new_id = db.execute(stmt).scalar_one_or_none()
    if new_id is not None:
        return db.get(BackgroundJob, new_id), True  # type: ignore[return-value]
    existing = db.execute(
        select(BackgroundJob).where(BackgroundJob.job_type == job_type, BackgroundJob.dedupe_key == dedupe)
    ).scalar_one()
    return existing, False


def reclaim_stale(db: Session, *, now: datetime | None = None) -> int:
    """Return RUNNING jobs whose worker vanished (lock older than the visibility timeout) to QUEUED."""
    now = now or _now()
    res = db.execute(
        update(BackgroundJob)
        .where(BackgroundJob.status == JobStatus.RUNNING, BackgroundJob.locked_at < now - VISIBILITY_TIMEOUT)
        .values(status=JobStatus.QUEUED, locked_at=None, locked_by=None, run_after=now,
                last_error="worker lost (visibility timeout)")
    )
    return res.rowcount or 0


def claim_next(
    db: Session, *, worker_id: str, job_types: list[str] | None = None, now: datetime | None = None
) -> BackgroundJob | None:
    now = now or _now()
    q = (
        select(BackgroundJob)
        .where(BackgroundJob.status == JobStatus.QUEUED, BackgroundJob.run_after <= now)
        .order_by(BackgroundJob.run_after, BackgroundJob.created_at)
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    if job_types:
        q = q.where(BackgroundJob.job_type.in_(job_types))
    job = db.execute(q).scalar_one_or_none()
    if job is None:
        return None
    job.status, job.locked_at, job.locked_by = JobStatus.RUNNING, now, worker_id
    job.attempts += 1
    job.started_at = job.started_at or now
    db.flush()
    return job


def complete(db: Session, job: BackgroundJob, result: dict[str, Any] | None = None) -> None:
    job.status, job.finished_at, job.result = JobStatus.SUCCEEDED, _now(), result
    job.locked_at = job.locked_by = None
    job.payload_blob = None  # raw bytes are only needed until processed
    JOBS.inc(type=job.job_type, outcome="succeeded")
    db.flush()


def backoff_seconds(attempts: int) -> float:
    base = min(BACKOFF_CAP_SECONDS, BACKOFF_BASE_SECONDS * (2 ** max(0, attempts - 1)))
    return base * (0.75 + random.random() * 0.5)  # +-25% jitter


def fail(db: Session, job: BackgroundJob, error: BaseException, *, retryable: bool = True) -> str:
    """Record a failure; returns the resulting status (QUEUED for a retry, DEAD when dead-lettered)."""
    job.last_error = f"{type(error).__name__}: {error}"[:_MAX_ERROR]
    job.locked_at = job.locked_by = None
    if not retryable or job.attempts >= job.max_attempts:
        job.status, job.finished_at = JobStatus.DEAD, _now()
        JOBS.inc(type=job.job_type, outcome="dead")
    else:
        job.status = JobStatus.QUEUED
        job.run_after = _now() + timedelta(seconds=backoff_seconds(job.attempts))
        JOBS.inc(type=job.job_type, outcome="retry")
    db.flush()
    return job.status


def requeue_dead(db: Session, job: BackgroundJob) -> None:
    """Operator action: give a dead-lettered job a fresh attempt budget."""
    if job.status != JobStatus.DEAD:
        raise ValueError("only DEAD jobs can be requeued")
    job.status, job.attempts, job.run_after, job.finished_at = JobStatus.QUEUED, 0, _now(), None
    db.flush()


def queue_counts(db: Session) -> dict[str, int]:
    rows = db.execute(select(BackgroundJob.status, func.count()).group_by(BackgroundJob.status)).all()
    return {s: n for s, n in rows}


def _run_hook(db: Session, exc: BaseException) -> None:
    hook = getattr(exc, "after_rollback", None)
    if hook is None:
        return
    try:
        with db.begin_nested():
            hook(db)
    except Exception:  # noqa: BLE001 - failure evidence is best effort; never mask the original failure
        log.exception("job.after_rollback_failed")


def run_one(db: Session, *, worker_id: str, job_types: list[str] | None = None) -> bool:
    """Claim and execute one job. Returns False when the queue is empty.

    The claim is committed before the handler runs (a crash leaves a visible RUNNING row that reclaim_stale
    recovers); the outcome is committed after. A handler exception rolls back the handler's writes (SAVEPOINT)
    and is then recorded as a retry or dead-letter."""
    job = claim_next(db, worker_id=worker_id, job_types=job_types)
    if job is None:
        return False
    db.commit()
    structlog.contextvars.bind_contextvars(
        job_id=str(job.id), job_type=job.job_type, organization_id=str(job.organization_id or ""),
        data_source_id=str(job.data_source_id or ""), request_id=job.correlation_id or "",
    )
    try:
        handler = _HANDLERS.get(job.job_type)
        if handler is None:
            raise NonRetryableJobError(f"no handler registered for job type {job.job_type!r}")
        with db.begin_nested():
            result = handler(db, job)
        complete(db, job, result)
        log.info("job.succeeded", attempts=job.attempts)
    except NonRetryableJobError as exc:
        # the handler's SAVEPOINT already discarded its partial writes; only the job row is updated here
        _run_hook(db, exc)
        fail(db, job, exc, retryable=False)
        log.warning("job.dead", error=str(exc)[:200])
    except Exception as exc:  # noqa: BLE001 - recorded, retried or dead-lettered; never crashes the worker
        _run_hook(db, exc)
        try:
            status = fail(db, job, exc)
        except Exception:  # noqa: BLE001 - session poisoned outside the handler SAVEPOINT: reset and re-record
            job_id = job.id
            db.rollback()
            job = db.get(BackgroundJob, job_id)
            status = fail(db, job, exc)
        log.warning("job.failed", status=status, attempts=job.attempts, error=type(exc).__name__)
    finally:
        db.commit()
        structlog.contextvars.unbind_contextvars("job_id", "job_type", "organization_id", "data_source_id")
    return True
