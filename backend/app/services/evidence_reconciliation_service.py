"""M16.8: EvidenceFile <-> object-storage consistency reconciliation.

Database metadata (EvidenceFile.status) and object storage (S3/MinIO) are
two separate systems that cannot be updated in one atomic transaction with
this codebase's architecture (see the M16.4/M16.6 "Case C" partial-failure
handling in app/api/v1/evidence.py). This module exists to find and, in a
narrow and conservative set of cases, repair the resulting drift.

This is a cross-tenant, operational/platform-maintenance capability, not a
tenant-facing feature: it is invoked via scripts/reconcile_evidence_files.py
(the same "standalone script with direct DATABASE_URL access" pattern
already established by scripts/create_platform_admin.py for the other
operation in this codebase that legitimately needs to act outside any single
tenant's authorization context and outside normal request/response HTTP
flow), never through a new HTTP endpoint, and never through a new
authentication/authorization model. There is no background-job/scheduler
infrastructure anywhere in this repository (no Celery/RQ/cron); introducing
one is explicitly out of scope for this milestone. Scheduling this script
(cron, a platform task runner, etc.) is intentionally deferred to whoever
operates a given deployment.

DISCOVERY vs REPAIR are deliberately separate: scan_evidence_files() only
ever reads (from the DB and from StorageService.object_exists(), itself a
read-only HEAD request) and never mutates anything. apply_repairs() is the
only function that can change data, and only acts on anomalies this module
has classified SAFE_TO_REPAIR -- currently exactly one case (see
_classify's docstring). Every other anomaly is MANUAL_REVIEW: this milestone
prioritizes reliability/observability over automatic destructive cleanup,
per its explicit instruction.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import StrEnum

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.models.evidence import EvidenceFile, EvidenceFileStatus
from app.services.audit_service import record_audit_event
from app.services.storage import StorageDeleteError, StorageService, StorageUnavailableError

logger = get_logger(__name__)


class ReconciliationClassification(StrEnum):
    # DB status and real object-storage state agree, and that agreement
    # represents a healthy row (STORED + object exists).
    CONSISTENT = "CONSISTENT"
    # DB status and real object-storage state agree, and no action is
    # needed even though this isn't the "actively verified good" case above
    # (e.g. a FAILED upload correctly has no object; a DELETED file's object
    # is correctly gone).
    NO_ACTION = "NO_ACTION"
    # A real, understood anomaly that this module is confident enough to fix
    # automatically via apply_repairs() -- see _classify's docstring for the
    # one current case.
    SAFE_TO_REPAIR = "SAFE_TO_REPAIR"
    # A real anomaly this module deliberately does NOT repair automatically.
    # A human must investigate; see EvidenceFileAnomaly.detail for why.
    MANUAL_REVIEW = "MANUAL_REVIEW"
    # object_exists() could not get a definitive answer (StorageUnavailableError:
    # permission failure, timeout, provider error, ...). This is NEVER
    # conflated with "object is missing" -- it is its own, distinct outcome.
    INFRASTRUCTURE_FAILURE = "INFRASTRUCTURE_FAILURE"


@dataclass(frozen=True)
class EvidenceFileAnomaly:
    """One EvidenceFile row whose classification is not a plain healthy
    CONSISTENT/NO_ACTION outcome. Deliberately carries no storage
    credentials, signed URLs, or raw provider error text -- `detail` is a
    short, safe, human-readable explanation only."""

    evidence_file_id: uuid.UUID
    organization_id: uuid.UUID
    evidence_id: uuid.UUID
    db_status: str
    object_exists: bool | None  # None only when classification is INFRASTRUCTURE_FAILURE
    classification: ReconciliationClassification
    detail: str


@dataclass(frozen=True)
class ReconciliationResult:
    scanned_count: int
    consistent_count: int
    anomaly_count: int
    repairable_count: int
    repaired_count: int
    manual_review_count: int
    infrastructure_failure_count: int
    # Safe, human-readable strings only (e.g. "storage unavailable while
    # checking <evidence_file_id>") -- never a raw exception, never a
    # storage key, never a signed URL.
    failures: list[str] = field(default_factory=list)
    anomalies: list[EvidenceFileAnomaly] = field(default_factory=list)


def _classify(
    *, db_status: EvidenceFileStatus, object_exists: bool
) -> tuple[ReconciliationClassification, str]:
    """Pure classification rule -- no I/O, no DB, no storage. Mirrors the
    repair-policy table from the M16.8 spec exactly:

        PENDING + exists  -> MANUAL_REVIEW (upload may still be in flight;
                              never assumed complete or abandoned)
        PENDING + missing -> MANUAL_REVIEW (could be genuinely in-flight, or
                              a crashed upload; never auto-marked FAILED)
        STORED  + exists  -> CONSISTENT
        STORED  + missing -> MANUAL_REVIEW (never silently marked
                              DELETED/FAILED -- this is the storage/DB "Case
                              C" desync M16.4/M16.6 already document)
        FAILED  + exists  -> MANUAL_REVIEW (a FAILED row is only supposed to
                              have no object -- an object existing here is a
                              genuine anomaly, e.g. a partial upload that
                              *did* land bytes despite reporting failure)
        FAILED  + missing -> NO_ACTION (the expected, healthy shape of a
                              FAILED row)
        DELETED + exists  -> SAFE_TO_REPAIR. This is the ONE case this
                              module repairs automatically: mark_deleted()
                              (M16.6) only ever runs after this exact
                              object's StorageService.delete() call already
                              succeeded, so a DELETED row represents an
                              already-authorized, already-executed decision
                              to permanently remove this specific object --
                              repairing here means re-issuing that same
                              already-approved delete (idempotent, no DB
                              write since status is already correct), never
                              inferring a new destructive action from
                              ambiguous state the way e.g. auto-deleting a
                              FAILED/PENDING row's object would.
        DELETED + missing -> NO_ACTION (the expected, healthy shape of a
                              DELETED row)
    """
    if db_status == EvidenceFileStatus.STORED:
        if object_exists:
            return ReconciliationClassification.CONSISTENT, "STORED row has a real stored object."
        return (
            ReconciliationClassification.MANUAL_REVIEW,
            "STORED row but the object is missing from storage -- possible storage/DB desync "
            "(see M16.4/M16.6 Case C). Never auto-repaired: could indicate a wrongly-reported "
            "upload success, an out-of-band deletion, or a storage outage that has since resolved.",
        )
    if db_status == EvidenceFileStatus.PENDING:
        if object_exists:
            return (
                ReconciliationClassification.MANUAL_REVIEW,
                "PENDING row but an object already exists at its storage key -- the upload flow "
                "may be mid-flight (mark_stored() not yet called) or may have crashed after "
                "put() succeeded. Never auto-advanced to STORED without independent confirmation.",
            )
        return (
            ReconciliationClassification.MANUAL_REVIEW,
            "PENDING row with no object in storage -- could be a genuinely in-flight upload or "
            "an abandoned/crashed one. Never auto-marked FAILED without a clear cutoff policy.",
        )
    if db_status == EvidenceFileStatus.FAILED:
        if object_exists:
            return (
                ReconciliationClassification.MANUAL_REVIEW,
                "FAILED row but an object exists in storage -- a potential orphan (bytes were "
                "written despite the upload being recorded as failed). Never auto-deleted here.",
            )
        return ReconciliationClassification.NO_ACTION, "FAILED row correctly has no stored object."
    if db_status == EvidenceFileStatus.DELETED:
        if object_exists:
            return (
                ReconciliationClassification.SAFE_TO_REPAIR,
                "DELETED row but its object still exists -- the original M16.6 delete already "
                "succeeded (that is the only way a row reaches DELETED), so this object was "
                "already, explicitly authorized for permanent removal. Repair re-issues that "
                "same delete; it does not infer a new decision.",
            )
        return ReconciliationClassification.NO_ACTION, "DELETED row correctly has no stored object."
    raise ValueError(f"Unrecognized EvidenceFileStatus: {db_status!r}")


def scan_evidence_files(
    db: Session,
    storage_service: StorageService,
    *,
    organization_id: uuid.UUID | None = None,
) -> ReconciliationResult:
    """DISCOVERY ONLY: never writes to the database or to storage.

    organization_id=None (the default) scans every organization -- this is
    a platform-operational tool, not a tenant-facing one (see module
    docstring); pass a specific organization_id to scope a run to one
    tenant instead. Either way, results for different organizations are
    never mixed into the same object identity check: each EvidenceFile row
    is only ever checked against its own storage_key.
    """
    stmt = select(EvidenceFile).order_by(EvidenceFile.created_at.asc(), EvidenceFile.id.asc())
    if organization_id is not None:
        stmt = stmt.where(EvidenceFile.organization_id == organization_id)
    rows = list(db.execute(stmt).scalars().all())

    scanned = 0
    consistent = 0
    manual_review = 0
    repairable = 0
    infra_failures = 0
    failures: list[str] = []
    anomalies: list[EvidenceFileAnomaly] = []

    for row in rows:
        scanned += 1
        db_status = EvidenceFileStatus(row.status)
        try:
            exists = storage_service.object_exists(key=row.storage_key)
        except StorageUnavailableError:
            infra_failures += 1
            failures.append(f"storage unavailable while checking evidence_file_id={row.id}")
            anomalies.append(
                EvidenceFileAnomaly(
                    evidence_file_id=row.id,
                    organization_id=row.organization_id,
                    evidence_id=row.evidence_id,
                    db_status=db_status.value,
                    object_exists=None,
                    classification=ReconciliationClassification.INFRASTRUCTURE_FAILURE,
                    detail="Could not determine object existence (storage unavailable, "
                    "permission failure, timeout, or provider error). NOT treated as missing.",
                )
            )
            continue

        classification, detail = _classify(db_status=db_status, object_exists=exists)
        if classification == ReconciliationClassification.CONSISTENT:
            consistent += 1
            continue
        if classification == ReconciliationClassification.NO_ACTION:
            consistent += 1  # healthy outcome, just for a different reason than CONSISTENT
            continue

        if classification == ReconciliationClassification.SAFE_TO_REPAIR:
            repairable += 1
        elif classification == ReconciliationClassification.MANUAL_REVIEW:
            manual_review += 1

        anomalies.append(
            EvidenceFileAnomaly(
                evidence_file_id=row.id,
                organization_id=row.organization_id,
                evidence_id=row.evidence_id,
                db_status=db_status.value,
                object_exists=exists,
                classification=classification,
                detail=detail,
            )
        )

    return ReconciliationResult(
        scanned_count=scanned,
        consistent_count=consistent,
        anomaly_count=repairable + manual_review,
        repairable_count=repairable,
        repaired_count=0,
        manual_review_count=manual_review,
        infrastructure_failure_count=infra_failures,
        failures=failures,
        anomalies=anomalies,
    )


def apply_repairs(
    db: Session,
    storage_service: StorageService,
    *,
    anomalies: list[EvidenceFileAnomaly],
    actor_user_id: uuid.UUID | None,
) -> int:
    """REPAIR: acts only on anomalies already classified SAFE_TO_REPAIR by a
    prior scan_evidence_files() call. Never re-derives its own opinion about
    what is safe -- the classification is the single source of truth, kept
    in one place (_classify) rather than duplicated here.

    actor_user_id is the platform operator who authorized this run (recorded
    on the audit event as user_id); None is accepted for an unattended/
    system-initiated run, matching AuditEvent.user_id's existing nullable
    "system-initiated" precedent.

    Returns the number of anomalies actually repaired.
    """
    repaired = 0
    for anomaly in anomalies:
        if anomaly.classification != ReconciliationClassification.SAFE_TO_REPAIR:
            continue

        # Concurrency/stale-state guard: re-fetch the row fresh right before
        # acting, and recheck it is STILL in the exact state the scan saw.
        # DELETED is a terminal state in evidence_file_service's transition
        # table today (nothing can leave it), so this can never actually
        # fire under current code -- but repair must never trust a
        # snapshot from an earlier scan over the row's current DB state,
        # regardless of what the transition table currently allows.
        current_row = db.get(EvidenceFile, anomaly.evidence_file_id)
        if current_row is None or current_row.organization_id != anomaly.organization_id:
            logger.warning(
                "evidence_reconciliation_repair_skipped_row_changed",
                evidence_file_id=str(anomaly.evidence_file_id),
                organization_id=str(anomaly.organization_id),
                reason="row no longer found for this organization",
            )
            continue
        if current_row.status != EvidenceFileStatus.DELETED.value:
            logger.warning(
                "evidence_reconciliation_repair_skipped_stale_state",
                evidence_file_id=str(anomaly.evidence_file_id),
                organization_id=str(anomaly.organization_id),
                previous_status=anomaly.db_status,
                current_status=current_row.status,
            )
            continue

        try:
            storage_service.delete(key=current_row.storage_key)
        except StorageDeleteError as exc:
            logger.warning(
                "evidence_reconciliation_repair_storage_delete_failed",
                evidence_file_id=str(anomaly.evidence_file_id),
                organization_id=str(anomaly.organization_id),
                error=str(exc),
            )
            # No audit event: nothing actually changed. Never report a false
            # repair.
            continue

        # No status/deleted_at mutation here -- the row is already correctly
        # DELETED. This audit event records that the *storage side* was
        # reconciled to match the DB's already-recorded intent, not a new
        # lifecycle transition.
        record_audit_event(
            db,
            organization_id=current_row.organization_id,
            user_id=actor_user_id,
            action="evidence_file.reconciliation_repaired",
            entity_type="EvidenceFile",
            entity_id=current_row.id,
            metadata={
                "evidence_id": str(current_row.evidence_id),
                "reconciliation_action": "retry_storage_delete",
                "db_status": current_row.status,
                "detail": anomaly.detail,
            },
        )
        db.commit()
        repaired += 1

    return repaired
