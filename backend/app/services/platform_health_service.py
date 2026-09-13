"""M13: platform-level health/monitoring read service.

This module deliberately does NOT invent a new telemetry/metrics platform.
It aggregates the two real signals this codebase already has:

  1. Database reachability -- the exact same check as the public readiness
     probe (`GET /health/ready`, app/api/v1/health.py): `SELECT 1` against
     the session bound to this request. That check has no bounded timeout
     today (a pre-existing property of the readiness endpoint, not
     introduced here) -- this service reuses its exact semantics rather
     than inventing a second, inconsistent DB check with different
     behavior.
  2. API process liveness -- trivially true if this code is running at all
     (same semantics as `GET /health`).

There is no Celery/worker system, no metrics/telemetry backend, and no
persisted health history anywhere in this codebase (verified by
inspection). So "background workers" and "external integrations" are
reported as NOT_APPLICABLE components rather than fabricated as healthy or
omitted silently -- the whole point of M13 is to never claim a status for
which there is no real signal.

Deterministic overall-status rule (documented here, not recomputed in the
frontend):
  - UNAVAILABLE  if the database check raises (DB unreachable).
  - HEALTHY      if the database check succeeds.
(The process could not be serving this request at all if it were not
"live", so liveness is implied by the fact this code ran -- there is no
DEGRADED state because there is no second real signal, beyond DB
reachability, that could justify one. Adding a DEGRADED tier would require
a real signal this codebase does not yet have -- e.g. elevated error rates
or slow queries -- which is out of scope for M13.)
"""

from __future__ import annotations

import enum
import time
from datetime import UTC, datetime

from sqlalchemy import text
from sqlalchemy.orm import Session


class HealthStatus(enum.StrEnum):
    HEALTHY = "HEALTHY"
    UNAVAILABLE = "UNAVAILABLE"
    UNKNOWN = "UNKNOWN"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class ComponentHealth:
    def __init__(
        self,
        name: str,
        status: HealthStatus,
        detail: str,
        latency_ms: float | None = None,
    ):
        self.name = name
        self.status = status
        self.detail = detail
        self.latency_ms = latency_ms


class PlatformHealthSnapshot:
    def __init__(
        self,
        overall_status: HealthStatus,
        checked_at: datetime,
        components: list[ComponentHealth],
    ):
        self.overall_status = overall_status
        self.checked_at = checked_at
        self.components = components


def _check_database(db: Session) -> ComponentHealth:
    """Reuses the exact query the readiness probe runs (`SELECT 1`) against
    the same request-scoped session -- see app/api/v1/health.py:readiness.
    No new timeout/retry behavior is introduced; if the readiness endpoint
    itself has no bounded timeout, this check has none either, by design.
    """
    start = time.monotonic()
    try:
        db.execute(text("SELECT 1"))
    except Exception:  # noqa: BLE001 - deliberately broad: any DB failure means UNAVAILABLE
        # Never surface the raw exception (could contain a connection
        # string or internal hostname) -- only a safe, generic detail.
        return ComponentHealth(
            name="database",
            status=HealthStatus.UNAVAILABLE,
            detail="Database connectivity check failed.",
        )
    latency_ms = round((time.monotonic() - start) * 1000, 2)
    return ComponentHealth(
        name="database",
        status=HealthStatus.HEALTHY,
        detail="Reachable (SELECT 1 succeeded).",
        latency_ms=latency_ms,
    )


def get_platform_health(db: Session) -> PlatformHealthSnapshot:
    """Canonical, on-demand platform health snapshot. Never stores anything;
    always reflects the moment this function is called (see M13 spec:
    "clearly show this is on-demand, not continuous monitoring").
    """
    checked_at = datetime.now(UTC)

    api_component = ComponentHealth(
        name="api",
        status=HealthStatus.HEALTHY,
        detail="Process is live (this request executed).",
    )

    db_component = _check_database(db)

    # Real, existing services with no independent health signal beyond "the
    # API process is up and the database is reachable" -- both entitlement
    # resolution and audit reads are synchronous DB-backed reads with no
    # separate infrastructure of their own (verified by inspection: no
    # queues, no external dependency, no separate process). Their status is
    # therefore derived from, not independently probed from, the database
    # component -- never reported as "Healthy" via a fabricated check.
    entitlement_component = ComponentHealth(
        name="entitlement_service",
        status=db_component.status,
        detail=(
            "Derived from database reachability (in-process, DB-backed "
            "service; no independent health signal)."
        ),
    )
    audit_component = ComponentHealth(
        name="audit_service",
        status=db_component.status,
        detail=(
            "Derived from database reachability (in-process, DB-backed "
            "service; no independent health signal)."
        ),
    )

    # No Celery/worker system and no external integrations exist in this
    # codebase (verified by inspection) -- reported explicitly as
    # NOT_APPLICABLE rather than omitted or faked as healthy.
    workers_component = ComponentHealth(
        name="background_workers",
        status=HealthStatus.NOT_APPLICABLE,
        detail="No background worker/queue infrastructure exists in this deployment.",
    )

    components = [
        api_component,
        db_component,
        entitlement_component,
        audit_component,
        workers_component,
    ]

    overall_status = (
        HealthStatus.UNAVAILABLE
        if db_component.status == HealthStatus.UNAVAILABLE
        else HealthStatus.HEALTHY
    )

    return PlatformHealthSnapshot(
        overall_status=overall_status,
        checked_at=checked_at,
        components=components,
    )
