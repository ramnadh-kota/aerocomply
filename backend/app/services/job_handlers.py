"""Job handlers. Importing this module registers them with job_service (the API and the worker both import it)."""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.core.errors import AeroComplyError
from app.models.background_job import BackgroundJob
from app.services import acquisition_service, job_service

INGEST = "acquisition.ingest"


def handle_ingest(db: Session, job: BackgroundJob) -> dict[str, Any]:
    """Run one queued raw payload through the acquisition pipeline.

    Effectively-once: telemetry events are de-duplicated by content/event id, so a retry after a crash between
    'events written' and 'job marked done' reports duplicates instead of double-counting."""
    if not job.payload_blob or job.organization_id is None or job.data_source_id is None:
        raise job_service.NonRetryableJobError("ingest job is missing its payload, organization or data source")
    try:
        report = acquisition_service.ingest(
            db,
            organization_id=job.organization_id,
            data_source_id=job.data_source_id,
            raw=job.payload_blob,
            topic=job.payload.get("topic"),
            actor_user_id=None,
        )
    except AeroComplyError as exc:  # unknown / foreign source: retrying cannot help
        raise job_service.NonRetryableJobError(str(exc)) from exc
    return report.to_dict()


job_service.register_handler(INGEST, handle_ingest)


RETENTION_SWEEP = "retention.sweep"


def handle_retention_sweep(db: Session, job: BackgroundJob) -> dict[str, Any]:
    """Platform job. Dry-run unless the deployment enabled destructive retention AND the payload asks to execute;
    only enabled policies are ever evaluated (see retention_service)."""
    from app.core.config import get_settings
    from app.services import retention_service

    execute = bool(job.payload.get("execute")) and get_settings().retention_destructive_enabled
    results = retention_service.run_retention(db, dry_run=not execute)
    failed = [r for r in results if r.error]
    if failed:  # surface as a retryable failure so an operator sees it in the queue
        raise RuntimeError(f"retention failed for {len(failed)} class(es): {failed[0].error}")
    return {"dry_run": not execute, "classes": len(results), "deleted": sum(r.deleted for r in results),
            "eligible": sum(r.eligible for r in results)}


job_service.register_handler(RETENTION_SWEEP, handle_retention_sweep)
