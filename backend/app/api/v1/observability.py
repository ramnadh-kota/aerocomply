"""Operational metrics endpoint (Prometheus text format).

Restricted to platform operators: metric names and per-route counters describe the whole deployment
and must never be readable by a tenant. Metrics carry no tenant/user/asset identifiers (see
app/core/metrics.py); those are in the structured logs.
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import metrics
from app.core.deps import get_db_session, require_permission
from app.core.permissions import Permission
from app.core.deps import get_current_user
from app.models.background_job import BackgroundJob, JobStatus
from app.models.data_source import DataSource
from app.schemas.auth import CurrentUser
from app.services import acquisition_service, audit_service, job_service, retention_service

router = APIRouter(tags=["observability"])

_MAX_SOURCES_SCANNED = 5000


@router.get("/platform/metrics", response_class=Response)
def platform_metrics(
    db: Session = Depends(get_db_session),
    _: CurrentUser = Depends(require_permission(Permission.PLATFORM_MANAGE)),
) -> Response:
    """Prometheus text exposition. Source-health gauges are derived from recorded evidence at scrape
    time (bounded scan); everything else is a live in-process counter/histogram."""
    metrics.SOURCES_BY_HEALTH.reset()
    counts: dict[str, int] = {"HEALTHY": 0, "DEGRADED": 0, "FAILED": 0, "INACTIVE": 0}
    for source in db.execute(select(DataSource).limit(_MAX_SOURCES_SCANNED)).scalars():
        counts[acquisition_service.compute_health_detail(source)["status"]] += 1
    for status, n in counts.items():
        metrics.SOURCES_BY_HEALTH.set(n, health=status)
    job_service.QUEUE_DEPTH.reset()
    counts_by_status = job_service.queue_counts(db)
    for st in JobStatus.ALL:
        job_service.QUEUE_DEPTH.set(counts_by_status.get(st, 0), status=st)
    return Response(content=metrics.REGISTRY.render(), media_type="text/plain; version=0.0.4; charset=utf-8")


def _job_view(j: BackgroundJob) -> dict[str, Any]:
    return {
        "job_id": str(j.id), "job_type": j.job_type, "status": j.status, "attempts": j.attempts,
        "max_attempts": j.max_attempts, "organization_id": str(j.organization_id) if j.organization_id else None,
        "data_source_id": str(j.data_source_id) if j.data_source_id else None, "last_error": j.last_error,
        "run_after": j.run_after.isoformat(), "correlation_id": j.correlation_id,
    }


@router.get("/platform/jobs")
def list_jobs(
    status: str | None = Query(default=None, description="e.g. DEAD for the dead-letter queue"),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db_session),
    _: CurrentUser = Depends(require_permission(Permission.PLATFORM_MANAGE)),
) -> dict[str, Any]:
    if status is not None and status not in JobStatus.ALL:
        raise HTTPException(status_code=422, detail=f"status must be one of {sorted(JobStatus.ALL)}")
    q = select(BackgroundJob).order_by(BackgroundJob.created_at.desc()).limit(limit)
    if status:
        q = q.where(BackgroundJob.status == status)
    return {"counts": job_service.queue_counts(db), "items": [_job_view(j) for j in db.execute(q).scalars()]}


@router.post("/platform/jobs/{job_id}/requeue")
def requeue_job(
    job_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    user: CurrentUser = Depends(require_permission(Permission.PLATFORM_MANAGE)),
) -> dict[str, Any]:
    job = db.get(BackgroundJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    try:
        job_service.requeue_dead(db, job)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if job.organization_id:
        audit_service.record_audit_event(
            db, organization_id=job.organization_id, user_id=user.id, action="background_job.requeued",
            entity_type="BackgroundJob", entity_id=job.id, metadata={"job_type": job.job_type},
        )
    db.commit()
    return _job_view(job)


@router.get("/platform/retention/policies")
def list_retention_policies(
    db: Session = Depends(get_db_session),
    _: CurrentUser = Depends(require_permission(Permission.PLATFORM_MANAGE)),
) -> dict[str, Any]:
    return {"floors_days": retention_service.FLOOR_DAYS, "items": [
        {"id": str(p.id), "organization_id": str(p.organization_id) if p.organization_id else None,
         "data_class": p.data_class, "retention_days": p.retention_days, "enabled": p.enabled}
        for p in retention_service.list_policies(db)]}


@router.put("/platform/retention/policies")
def put_retention_policy(
    body: dict[str, Any] = Body(...),
    db: Session = Depends(get_db_session),
    user: CurrentUser = Depends(require_permission(Permission.PLATFORM_MANAGE)),
) -> dict[str, Any]:
    try:
        org = uuid.UUID(str(body["organization_id"])) if body.get("organization_id") else None
        row = retention_service.set_policy(
            db, organization_id=org, data_class=str(body.get("data_class")),
            retention_days=int(body.get("retention_days", 0)), enabled=bool(body.get("enabled", False)))
    except (retention_service.RetentionError, ValueError, KeyError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if row.organization_id:
        audit_service.record_audit_event(
            db, organization_id=row.organization_id, user_id=user.id, action="retention.policy_set",
            entity_type="RetentionPolicy", entity_id=row.id,
            metadata={"data_class": row.data_class, "retention_days": row.retention_days, "enabled": row.enabled})
    db.commit()
    return {"id": str(row.id), "data_class": row.data_class, "retention_days": row.retention_days, "enabled": row.enabled}


@router.post("/platform/retention/run")
def run_retention(
    dry_run: bool = Query(default=True, description="true (default) only reports what WOULD be removed"),
    organization_id: uuid.UUID | None = Query(default=None),
    db: Session = Depends(get_db_session),
    user: CurrentUser = Depends(require_permission(Permission.PLATFORM_MANAGE)),
) -> dict[str, Any]:
    try:
        results = retention_service.run_retention(db, dry_run=dry_run, organization_id=organization_id,
                                                  actor_user_id=user.id)
    except retention_service.RetentionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    db.commit()
    return {"dry_run": dry_run, "results": [r.to_dict() for r in results]}
