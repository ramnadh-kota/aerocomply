"""Recurring jobs. `tick()` is safe to call from every worker on every loop: each schedule enqueues at most ONE job
per period, because the idempotency key contains the period bucket (unique (job_type, dedupe_key))."""
from __future__ import annotations

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
    payload_fn: callable  # () -> dict


def _retention_payload() -> dict:
    return {"execute": get_settings().retention_destructive_enabled}


SCHEDULES = [Schedule("retention", job_handlers.RETENTION_SWEEP, 86_400, _retention_payload)]


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
    db.commit()
    return created
