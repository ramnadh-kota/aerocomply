"""Tenant-scoped metadata service for EvidenceFile.

This is the canonical application-layer path for EvidenceFile metadata
operations. It closes the gap M16.2 deliberately left open at the database
layer: nothing in the schema enforces
`evidence_files.organization_id == evidence.organization_id` (see the 0026
migration docstring), so every function here re-derives organization_id from
the tenant-scoped parent Evidence rather than ever trusting a caller-supplied
value, exactly like create_evidence() in evidence_service.py already does
for task_id.

Scope (M16.3): metadata only. No StorageService/boto3/S3 call is made from
here -- that begins in M16.4, which will call create_pending_file(),
StorageService.put(), and then mark_stored()/mark_failed() in sequence. No
audit events are recorded here (that starts once these operations represent
real uploaded content, not just metadata bookkeeping). No router exposes any
of this yet.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AeroComplyError, ConflictError, NotFoundError
from app.models.evidence import EvidenceFile, EvidenceFileStatus
from app.services import evidence_service

# The only transitions this milestone owns. STORED and FAILED are both
# terminal from this service's point of view -- STORED -> DELETED belongs to
# M16.6, and nothing here ever moves a file backwards (STORED/FAILED ->
# PENDING) or sideways (STORED <-> FAILED).
_ALLOWED_TRANSITIONS: dict[EvidenceFileStatus, set[EvidenceFileStatus]] = {
    EvidenceFileStatus.PENDING: {EvidenceFileStatus.STORED, EvidenceFileStatus.FAILED},
    EvidenceFileStatus.STORED: set(),
    EvidenceFileStatus.FAILED: set(),
    EvidenceFileStatus.DELETED: set(),
}


def can_transition_file(current: EvidenceFileStatus, target: EvidenceFileStatus) -> bool:
    """Pure rule check, mirroring evidence_service.can_transition: is
    `current -> target` a legal EvidenceFile status transition?"""
    if current == target:
        return False
    return target in _ALLOWED_TRANSITIONS.get(current, set())


def _validate_metadata(
    *, original_filename: str, content_type: str, size_bytes: int, storage_key: str
) -> None:
    # Deliberately minimal: non-emptiness and a non-negative size (the same
    # invariant the DB CHECK constraint enforces, checked early here for a
    # clean application-level error instead of an IntegrityError). No MIME
    # sniffing, no filename re-sanitization (that's app.services.storage.keys'
    # job, called by the M16.4 upload flow before this function ever sees a
    # storage_key), no checksum validation -- all explicitly out of scope
    # for this milestone.
    if not original_filename.strip():
        raise AeroComplyError("original_filename must not be empty", code="invalid_evidence_file")
    if not content_type.strip():
        raise AeroComplyError("content_type must not be empty", code="invalid_evidence_file")
    if not storage_key.strip():
        raise AeroComplyError("storage_key must not be empty", code="invalid_evidence_file")
    if size_bytes < 0:
        raise AeroComplyError("size_bytes must not be negative", code="invalid_evidence_file")


def create_pending_file(
    db: Session,
    *,
    organization_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    evidence_id: uuid.UUID,
    original_filename: str,
    content_type: str,
    size_bytes: int,
    storage_key: str,
    checksum_sha256: str | None = None,
) -> EvidenceFile:
    """Create a new EvidenceFile row in PENDING status.

    organization_id is the caller's own (authenticated-actor-derived)
    organization -- used only to verify the parent Evidence belongs to this
    tenant. The EvidenceFile row's own organization_id is never set from this
    parameter directly; it is copied from the *resolved* Evidence row, so a
    caller can never persist a file whose organization_id disagrees with its
    parent evidence_id's real tenant (the exact gap M16.2 left for this
    milestone to close). uploaded_by_user_id is always actor_user_id -- there
    is no parameter that lets a caller attribute the upload to someone else.
    status is always created as PENDING; there is no parameter to create a
    file directly as STORED/FAILED/DELETED.
    """
    # Resolving Evidence by (evidence_id, organization_id) is what makes this
    # safe: if evidence_id belongs to a different tenant, this raises
    # NotFoundError exactly like any other cross-tenant lookup in this
    # codebase (create_evidence's task_id check is the direct precedent) --
    # it never proceeds to create a mismatched row.
    evidence = evidence_service.get_evidence(
        db, organization_id=organization_id, evidence_id=evidence_id
    )

    _validate_metadata(
        original_filename=original_filename,
        content_type=content_type,
        size_bytes=size_bytes,
        storage_key=storage_key,
    )

    evidence_file = EvidenceFile(
        organization_id=evidence.organization_id,
        evidence_id=evidence.id,
        uploaded_by_user_id=actor_user_id,
        original_filename=original_filename,
        content_type=content_type,
        size_bytes=size_bytes,
        storage_key=storage_key,
        checksum_sha256=checksum_sha256,
        status=EvidenceFileStatus.PENDING.value,
    )
    db.add(evidence_file)
    db.commit()
    db.refresh(evidence_file)
    return evidence_file


def get_file(
    db: Session, *, organization_id: uuid.UUID, evidence_file_id: uuid.UUID
) -> EvidenceFile:
    """Tenant-scoped lookup by id. Never queries by id alone.

    A file belonging to a different organization is indistinguishable from a
    nonexistent one -- both raise NotFoundError -- so this never discloses
    whether a given evidence_file_id exists for another tenant (same
    safe-not-found convention as evidence_service.get_evidence).
    """
    evidence_file = db.execute(
        select(EvidenceFile).where(
            EvidenceFile.id == evidence_file_id,
            EvidenceFile.organization_id == organization_id,
        )
    ).scalar_one_or_none()
    if evidence_file is None:
        raise NotFoundError("Evidence file not found")
    return evidence_file


def list_files_for_evidence(
    db: Session, *, organization_id: uuid.UUID, evidence_id: uuid.UUID
) -> list[EvidenceFile]:
    """List files for one Evidence record, tenant-scoped at both hops.

    First resolves Evidence via (evidence_id, organization_id) -- if the
    evidence belongs to another tenant this raises NotFoundError before any
    EvidenceFile query runs. The EvidenceFile query itself is then filtered
    by both organization_id and evidence_id (not evidence_id alone), so even
    a hypothetical future data inconsistency could not surface another
    tenant's rows here.
    """
    evidence = evidence_service.get_evidence(
        db, organization_id=organization_id, evidence_id=evidence_id
    )
    return list(
        db.execute(
            select(EvidenceFile)
            .where(
                EvidenceFile.organization_id == organization_id,
                EvidenceFile.evidence_id == evidence.id,
            )
            # Deterministic ordering (created_at, then id as a tiebreaker for
            # rows created in the same instant) rather than relying on
            # Postgres's unspecified natural row order -- added here so M16.5
            # (and any future caller) gets consistent list output without
            # duplicating this query.
            .order_by(EvidenceFile.created_at.asc(), EvidenceFile.id.asc())
        ).scalars().all()
    )


def get_file_for_evidence(
    db: Session, *, organization_id: uuid.UUID, evidence_id: uuid.UUID, evidence_file_id: uuid.UUID
) -> EvidenceFile:
    """Tenant- and parent-scoped lookup: resolves Evidence first (tenant-safe),
    then requires the file to belong to both this organization AND this exact
    Evidence. A file that exists but belongs to a different Evidence -- even
    within the same organization -- is treated as not found here, exactly
    like a cross-tenant file, so a request for
    /evidence/{evidence_id}/files/{file_id} can never return a different
    Evidence's file by mismatched parent/child ids.
    """
    evidence = evidence_service.get_evidence(
        db, organization_id=organization_id, evidence_id=evidence_id
    )
    evidence_file = db.execute(
        select(EvidenceFile).where(
            EvidenceFile.id == evidence_file_id,
            EvidenceFile.organization_id == organization_id,
            EvidenceFile.evidence_id == evidence.id,
        )
    ).scalar_one_or_none()
    if evidence_file is None:
        raise NotFoundError("Evidence file not found")
    return evidence_file


def _transition_file(
    db: Session,
    *,
    organization_id: uuid.UUID,
    evidence_file_id: uuid.UUID,
    target_status: EvidenceFileStatus,
) -> EvidenceFile:
    evidence_file = get_file(db, organization_id=organization_id, evidence_file_id=evidence_file_id)
    current = EvidenceFileStatus(evidence_file.status)
    if not can_transition_file(current, target_status):
        raise ConflictError(
            f"Cannot transition evidence file from {current.value} to {target_status.value}"
        )
    evidence_file.status = target_status.value
    db.add(evidence_file)
    db.commit()
    db.refresh(evidence_file)
    return evidence_file


def mark_stored(
    db: Session, *, organization_id: uuid.UUID, evidence_file_id: uuid.UUID
) -> EvidenceFile:
    """PENDING -> STORED. No StorageService/S3 call and no audit event here --
    the caller (M16.4's upload flow) is responsible for having already made
    the real object-storage call succeed before invoking this."""
    return _transition_file(
        db,
        organization_id=organization_id,
        evidence_file_id=evidence_file_id,
        target_status=EvidenceFileStatus.STORED,
    )


def mark_failed(
    db: Session, *, organization_id: uuid.UUID, evidence_file_id: uuid.UUID
) -> EvidenceFile:
    """PENDING -> FAILED. No StorageService/S3 call and no audit event here --
    the caller (M16.4's upload flow) is responsible for invoking this only
    after a real object-storage call has actually failed."""
    return _transition_file(
        db,
        organization_id=organization_id,
        evidence_file_id=evidence_file_id,
        target_status=EvidenceFileStatus.FAILED,
    )
