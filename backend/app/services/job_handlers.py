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


POLL = "acquisition.poll"


def handle_poll(db: Session, job: BackgroundJob) -> dict[str, Any]:
    """One OEM pull for one OEM_API data source: fetch -> (skip if empty) -> the normal ingest pipeline -> save cursor.

    Permanent problems (bad config, blocked target, refused credential) dead-letter immediately and are shown on the
    data source; transient ones (network, 5xx, 429) retry with the queue's exponential backoff."""
    from datetime import UTC, datetime

    from app.models.data_source import DataSource, DataSourceConnectorType, DataSourceStatus
    from app.services.edge import oem_poller

    if job.organization_id is None or job.data_source_id is None:
        raise job_service.NonRetryableJobError("poll job is missing its organization or data source")
    source = db.get(DataSource, job.data_source_id)
    if source is None or source.organization_id != job.organization_id:
        raise job_service.NonRetryableJobError("data source not found")
    if source.status != DataSourceStatus.ACTIVE or source.connector_type != DataSourceConnectorType.OEM_API:
        return {"skipped": "source is not an ACTIVE OEM_API source"}
    meta = dict(source.metadata_json or {})
    source_id = source.id

    def _record_failure(prefix: str, reason: str):
        def hook(session: Session) -> None:
            src = session.get(DataSource, source_id)
            if src is not None:
                src.last_error = f"{prefix}: {reason}"[:512]
                src.last_failure_at = datetime.now(UTC)
                src.consecutive_failures += 1
        return hook

    try:
        fmt = oem_poller.parse_config(source.connection_config).fmt
        raw, next_cursor = oem_poller.poll_once(source.connection_config, source.secret_reference, meta.get("poll_cursor"))
    except oem_poller.PollConfigError as exc:
        raise job_service.NonRetryableJobError(str(exc), after_rollback=_record_failure("poll refused", str(exc))) from exc
    except oem_poller.PollTransientError as exc:
        raise job_service.RetryableJobError(str(exc), after_rollback=_record_failure("poll failed", str(exc))) from exc
    result: dict[str, Any] = {"empty": True}
    if oem_poller.is_empty_payload(raw, fmt):
        source.last_seen_at = datetime.now(UTC)      # alive, nothing new: not a failure
    else:
        result = acquisition_service.ingest(
            db, organization_id=job.organization_id, data_source_id=source.id, raw=raw, actor_user_id=None,
            via_poller=True,
        ).to_dict()
    if next_cursor and next_cursor != meta.get("poll_cursor"):
        source.metadata_json = {**meta, "poll_cursor": next_cursor}
    db.flush()
    return result


job_service.register_handler(POLL, handle_poll)


DUNNING = "billing.dunning"


def handle_dunning(db: Session, job: BackgroundJob) -> dict[str, Any]:
    """Daily platform job: report subscriptions past the payment grace period and, only when BILLING_ENFORCE_GRACE is
    enabled AND the job asks to execute, cancel them (audited, reversible)."""
    from app.core.config import get_settings
    from app.services import billing_service

    execute = bool(job.payload.get("execute")) and get_settings().billing_enforce_grace
    report = billing_service.enforce_grace_expiry(db, execute=execute)
    return {"executed": execute, "past_grace": len(report), "canceled": sum(1 for r in report if r.get("action_taken"))}


job_service.register_handler(DUNNING, handle_dunning)


LIVE_TELEMETRY_LOSS_SWEEP = "live.telemetry_loss_sweep"


def handle_live_telemetry_loss_sweep(db: Session, job: BackgroundJob) -> dict[str, Any]:
    """Platform job (C5): raise LIVE_TELEMETRY_LOSS for armed drones that went silent. Idempotent per silence episode."""
    from app.services import live_alert_service

    result = live_alert_service.sweep_telemetry_loss(db)
    return result


job_service.register_handler(LIVE_TELEMETRY_LOSS_SWEEP, handle_live_telemetry_loss_sweep)
