"""Recurring jobs. `tick()` is safe to call from every worker on every loop: each schedule enqueues at most ONE job
per period, because the idempotency key contains the period bucket (unique (job_type, dedupe_key))."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.services import job_handlers, job_service


@dataclass(frozen=True)
class Schedule:
    name: str
    job_type: str
    period_seconds: int
    payload_fn: Callable[[], dict]


def _retention_payload() -> dict:
    return {"execute": get_settings().retention_destructive_enabled}


def _dunning_payload() -> dict:
    return {"execute": get_settings().billing_enforce_grace}


SCHEDULES = [
    Schedule("retention", job_handlers.RETENTION_SWEEP, 86_400, _retention_payload),
    Schedule("dunning", job_handlers.DUNNING, 86_400, _dunning_payload),
]


def tick(db: Session, *, now: datetime | None = None) -> int:
    """Enqueue every schedule whose current period has no job yet. Returns the number of jobs created."""
    now = now or datetime.now(UTC)
    created = 0
    for s in SCHEDULES:
        bucket = int(now.timestamp() // s.period_seconds)
        _, was_created = job_service.enqueue(
            db, job_type=s.job_type, idempotency_key=f"schedule:{s.name}:{bucket}", payload=s.payload_fn(),
            max_attempts=3, correlation_id=f"schedule-{s.name}",
        )
        created += int(was_created)
    created += enqueue_polls(db, now=now)
    db.commit()
    return created


def enqueue_polls(db: Session, *, now: datetime) -> int:
    """One acquisition.poll job per ACTIVE OEM_API source per poll interval (idempotent across workers)."""
    from sqlalchemy import select

    from app.models.data_source import DataSource, DataSourceConnectorType, DataSourceStatus
    from app.services.edge import oem_poller

    created = 0
    sources = db.execute(select(DataSource).where(
        DataSource.status == DataSourceStatus.ACTIVE,
        DataSource.connector_type == DataSourceConnectorType.OEM_API)).scalars().all()
    for src in sources:
        try:
            interval = oem_poller.parse_config(src.connection_config).interval_seconds
        except oem_poller.PollConfigError:
            continue                              # misconfigured sources are surfaced when a poll is attempted/edited
        bucket = int(now.timestamp() // interval)
        _, was_created = job_service.enqueue(
            db, job_type=job_handlers.POLL, organization_id=src.organization_id, data_source_id=src.id,
            idempotency_key=f"poll:{src.id}:{bucket}", max_attempts=3, correlation_id="schedule-poll")
        created += int(was_created)
    return created
