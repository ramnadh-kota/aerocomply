"""Data retention: policy resolution, dry-run, optional archive-before-delete, tenant-scoped purge, audit trail.

Safety rules (each is tested):
* No policy row, or a disabled one => nothing is ever touched. Policies default to disabled.
* dry_run=True (the default everywhere) only counts; it never deletes or archives.
* A real purge additionally requires settings.retention_destructive_enabled (deployment-level switch).
* Floors: raw readings >= 30 days, event ledger >= 7 days, finished jobs >= 1 day. Lower values are refused.
* Readings that fall inside any recorded exceedance window are kept (they are the evidence for findings).
* Quarantined telemetry events are kept (they still await triage / replay). DEAD jobs are kept 30+ days.
* If an archive directory is configured, each batch is written (gzip JSONL) and fsynced BEFORE it is deleted;
  a failed write skips that batch. audit_events are immutable by design and never purged.
* Every purge that deletes rows writes an audit event for the tenant. Execution is per tenant, never a global sweep.
"""
from __future__ import annotations

import gzip
import json
import os
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import structlog
from sqlalchemy import and_, delete, exists, func, or_, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.background_job import BackgroundJob, JobStatus
from app.models.hums import HUMSExceedance, HUMSSensorReading
from app.models.organization import Organization
from app.models.retention import RetentionClass, RetentionPolicy
from app.models.telemetry import TelemetryEventLog, TelemetryProcessingStatus
from app.services import audit_service

log = structlog.get_logger(__name__)
settings = get_settings()

FLOOR_DAYS = {
    RetentionClass.TELEMETRY_READINGS: 30,
    RetentionClass.TELEMETRY_EVENT_LOG: 7,
    RetentionClass.BACKGROUND_JOBS: 1,
}
DEFAULT_BATCH = 5_000


class RetentionError(ValueError):
    pass


@dataclass
class ClassResult:
    organization_id: uuid.UUID
    data_class: str
    retention_days: int
    cutoff: datetime
    eligible: int = 0
    deleted: int = 0
    archived_files: list[str] = field(default_factory=list)
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"organization_id": str(self.organization_id), "data_class": self.data_class,
                "retention_days": self.retention_days, "cutoff": self.cutoff.isoformat(), "eligible": self.eligible,
                "deleted": self.deleted, "archived_files": self.archived_files, "error": self.error}


# ---------------------------------------------------------------- policies
def set_policy(db: Session, *, organization_id: uuid.UUID | None, data_class: str, retention_days: int,
               enabled: bool) -> RetentionPolicy:
    if data_class not in RetentionClass.ALL:
        raise RetentionError(f"data_class must be one of {sorted(RetentionClass.ALL)}")
    if retention_days < FLOOR_DAYS[data_class]:
        raise RetentionError(f"{data_class} retention cannot be below {FLOOR_DAYS[data_class]} days")
    if organization_id is not None and db.get(Organization, organization_id) is None:
        raise RetentionError("organization not found")
    scope = str(organization_id) if organization_id else "platform"
    row = db.execute(select(RetentionPolicy).where(
        RetentionPolicy.scope_key == scope, RetentionPolicy.data_class == data_class)).scalar_one_or_none()
    if row is None:
        row = RetentionPolicy(organization_id=organization_id, scope_key=scope, data_class=data_class,
                              retention_days=retention_days, enabled=enabled)
        db.add(row)
    else:
        row.retention_days, row.enabled = retention_days, enabled
    db.flush()
    return row


def list_policies(db: Session) -> list[RetentionPolicy]:
    return list(db.execute(select(RetentionPolicy).order_by(RetentionPolicy.scope_key, RetentionPolicy.data_class)).scalars())


def _effective(db: Session, organization_id: uuid.UUID, data_class: str) -> RetentionPolicy | None:
    rows = db.execute(select(RetentionPolicy).where(
        RetentionPolicy.data_class == data_class,
        RetentionPolicy.scope_key.in_([str(organization_id), "platform"]))).scalars().all()
    by_scope = {r.scope_key: r for r in rows}
    return by_scope.get(str(organization_id)) or by_scope.get("platform")     # tenant policy overrides the default


# ---------------------------------------------------------------- eligibility (one query per class)
def _eligible_ids_stmt(data_class: str, organization_id: uuid.UUID, cutoff: datetime, limit: int | None):
    if data_class == RetentionClass.TELEMETRY_READINGS:
        r = HUMSSensorReading
        q = select(r.id).where(
            r.organization_id == organization_id, r.recorded_at < cutoff,
            ~exists().where(and_(HUMSExceedance.sensor_id == r.sensor_id,
                                 HUMSExceedance.window_start <= r.recorded_at,
                                 HUMSExceedance.window_end >= r.recorded_at)),
        ).order_by(r.recorded_at)
        model = r
    elif data_class == RetentionClass.TELEMETRY_EVENT_LOG:
        e = TelemetryEventLog
        q = select(e.id).where(
            e.organization_id == organization_id, e.received_timestamp < cutoff,
            e.processing_status != TelemetryProcessingStatus.QUARANTINED,
        ).order_by(e.received_timestamp)
        model = e
    else:
        j = BackgroundJob
        dead_cutoff = min(cutoff, datetime.now(UTC) - timedelta(days=30))
        q = select(j.id).where(
            j.organization_id == organization_id,
            or_(and_(j.status.in_([JobStatus.SUCCEEDED, JobStatus.CANCELED]), j.finished_at < cutoff),
                and_(j.status == JobStatus.DEAD, j.finished_at < dead_cutoff)),
        ).order_by(j.finished_at)
        model = j
    return (q.limit(limit) if limit else q), model


def _count(db: Session, data_class: str, organization_id: uuid.UUID, cutoff: datetime) -> int:
    q, _ = _eligible_ids_stmt(data_class, organization_id, cutoff, None)
    return db.scalar(select(func.count()).select_from(q.order_by(None).subquery())) or 0


def _archive(db: Session, model: Any, ids: list[uuid.UUID], org: uuid.UUID, data_class: str) -> str | None:
    """Write rows to <archive_dir>/<org>/<class>/<timestamp>-<uuid>.jsonl.gz and fsync. Returns the path (or None)."""
    base = getattr(settings, "retention_archive_dir", None)
    if not base:
        return None
    rows = db.execute(select(model).where(model.id.in_(ids))).scalars().all()
    cols = [c.name for c in model.__table__.columns if c.name != "payload_blob"]
    folder = Path(base) / str(org) / data_class
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{datetime.now(UTC):%Y%m%dT%H%M%S}-{uuid.uuid4().hex[:8]}.jsonl.gz"
    with open(path, "wb") as raw:
        with gzip.GzipFile(fileobj=raw, mode="wb") as gz:
            for row in rows:
                line = json.dumps({c: getattr(row, c) for c in cols}, default=str)
                gz.write(line.encode("utf-8") + b"\n")
        raw.flush()
        os.fsync(raw.fileno())            # on disk before any row is deleted
    return str(path)


# ---------------------------------------------------------------- run
def run_retention(
    db: Session, *, dry_run: bool = True, organization_id: uuid.UUID | None = None, batch: int = DEFAULT_BATCH,
    now: datetime | None = None, actor_user_id: uuid.UUID | None = None,
) -> list[ClassResult]:
    """Evaluate (and, only if dry_run is False, execute) all enabled policies. Commits nothing: the caller owns the
    transaction, so a failure part-way leaves earlier batches applied only if the caller commits them."""
    if not dry_run and not getattr(settings, "retention_destructive_enabled", False):
        raise RetentionError("destructive retention is disabled (set RETENTION_DESTRUCTIVE_ENABLED=true)")
    now = now or datetime.now(UTC)
    org_ids = [organization_id] if organization_id else list(db.execute(select(Organization.id)).scalars())
    results: list[ClassResult] = []
    for org in org_ids:
        for data_class in sorted(RetentionClass.ALL):
            policy = _effective(db, org, data_class)
            if policy is None or not policy.enabled:
                continue
            days = max(policy.retention_days, FLOOR_DAYS[data_class])            # a row edited by hand can't undercut the floor
            res = ClassResult(org, data_class, days, now - timedelta(days=days))
            res.eligible = _count(db, data_class, org, res.cutoff)
            results.append(res)
            if dry_run or res.eligible == 0:
                continue
            try:
                while True:
                    q, model = _eligible_ids_stmt(data_class, org, res.cutoff, batch)
                    ids = list(db.execute(q).scalars())
                    if not ids:
                        break
                    path = _archive(db, model, ids, org, data_class)              # raises => nothing deleted for the batch
                    if path:
                        res.archived_files.append(path)
                    res.deleted += db.execute(delete(model).where(model.id.in_(ids))).rowcount or 0
                    db.flush()
            except Exception as exc:  # noqa: BLE001 - one class failing must not stop the others; recorded in the result
                res.error = f"{type(exc).__name__}: {exc}"[:300]
                log.exception("retention.failed", organization_id=str(org), data_class=data_class)
            if res.deleted:
                audit_service.record_audit_event(
                    db, organization_id=org, user_id=actor_user_id, action="retention.purged",
                    entity_type="RetentionPolicy", entity_id=policy.id,
                    metadata={"data_class": data_class, "deleted": res.deleted, "cutoff": res.cutoff.isoformat(),
                              "retention_days": days, "archived": bool(res.archived_files)},
                )
    return results
