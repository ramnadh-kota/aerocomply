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
