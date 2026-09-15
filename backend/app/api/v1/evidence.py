import hashlib
import uuid

from fastapi import APIRouter, Depends, UploadFile
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.deps import get_db_session, require_permission
from app.core.errors import AeroComplyError, ConflictError
from app.core.logging import get_logger
from app.core.permissions import Permission
from app.models.evidence import EvidenceFileStatus, EvidenceStatus
from app.schemas.auth import CurrentUser
from app.schemas.evidence import (
    EvidenceCreateRequest,
    EvidenceFileDownloadResponse,
    EvidenceFileResponse,
    EvidenceResponse,
    EvidenceTransitionRequest,
)
from app.services import evidence_file_service, evidence_service
from app.services.storage import (
    StoragePresignError,
    StorageUploadError,
    build_object_key,
    get_storage_service,
    sanitize_filename,
)

router = APIRouter(prefix="/evidence", tags=["evidence"])
logger = get_logger(__name__)

# Declared-content-type allowlist for evidence uploads. UploadFile.content_type
# is the client-declared MIME type, not verified by content inspection (magic
# bytes/antivirus scanning) -- that's a later hardening concern, not something
# this milestone claims to do. Kept deliberately small and MRO-relevant
# (inspection photos, scanned forms/PDFs); expand only if a real workflow
# needs another format.
_ALLOWED_EVIDENCE_CONTENT_TYPES = {"application/pdf", "image/jpeg", "image/png"}


@router.post("", response_model=EvidenceResponse, status_code=201)
def create_evidence(
    payload: EvidenceCreateRequest,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.EVIDENCE_WRITE)),
) -> EvidenceResponse:
    # organization_id always comes from the authenticated user, never the request body.
    evidence = evidence_service.create_evidence(
        db,
        organization_id=current_user.organization_id,
        task_id=payload.task_id,
        uploaded_by_user_id=current_user.id,
    )
    return EvidenceResponse.model_validate(evidence)


@router.get("/{evidence_id}", response_model=EvidenceResponse)
def get_evidence(
    evidence_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.EVIDENCE_READ)),
) -> EvidenceResponse:
    evidence = evidence_service.get_evidence(
        db, organization_id=current_user.organization_id, evidence_id=evidence_id
    )
    return EvidenceResponse.model_validate(evidence)


@router.post("/{evidence_id}/transition", response_model=EvidenceResponse)
def transition_evidence(
    evidence_id: uuid.UUID,
    payload: EvidenceTransitionRequest,
    db: Session = Depends(get_db_session),
    # There is no distinct EVIDENCE_REVIEW permission in the permission catalog
    # (see app/core/permissions.py); EVIDENCE_WRITE ("evidence:upload") is the
    # only write-side evidence permission today and covers both upload-side
    # (UPLOADED/SUBMITTED) and reviewer-side (ACCEPTED/REJECTED) transitions.
    current_user: CurrentUser = Depends(require_permission(Permission.EVIDENCE_WRITE)),
) -> EvidenceResponse:
    evidence = evidence_service.get_evidence(
        db, organization_id=current_user.organization_id, evidence_id=evidence_id
    )
    try:
        target_status = EvidenceStatus(payload.target_status)
    except ValueError as exc:
        raise AeroComplyError(
            f"Invalid evidence status: {payload.target_status}", code="invalid_status"
        ) from exc

    evidence = evidence_service.transition_evidence(
        db,
        evidence,
        target_status,
        actor_user_id=current_user.id,
        rejection_reason=payload.rejection_reason,
    )
    return EvidenceResponse.model_validate(evidence)


@router.post("/{evidence_id}/files", response_model=EvidenceFileResponse, status_code=201)
async def upload_evidence_file(
    evidence_id: uuid.UUID,
    file: UploadFile,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.EVIDENCE_WRITE)),
) -> EvidenceFileResponse:
    """Upload a physical file backing an Evidence record.

    Note: uploading a file here has no effect on Evidence.status. Evidence is
    always created already in UPLOADED status (see evidence_service.create_
    evidence) and its subsequent SUBMITTED/AWAITING_REVIEW/ACCEPTED/REJECTED
    transitions are an independent reviewer workflow (transition_evidence
    above) -- there is no canonical "a file arrived" -> Evidence-status
    transition defined anywhere in this codebase, so this endpoint does not
    invent one.
    """
    # Resolving Evidence via the caller's own tenant BEFORE touching content
    # type/size/storage is what prevents a cross-tenant upload attempt from
    # ever reaching StorageService.put() -- a cross-tenant evidence_id raises
    # NotFoundError here, identical to a nonexistent one.
    evidence = evidence_service.get_evidence(
        db, organization_id=current_user.organization_id, evidence_id=evidence_id
    )

    content_type = (file.content_type or "").lower()
    if content_type not in _ALLOWED_EVIDENCE_CONTENT_TYPES:
        raise AeroComplyError(
            f"Unsupported content type: {content_type or 'unknown'}",
            code="unsupported_content_type",
            status_code=415,
        )

    # Bounded read: StorageService.put() takes bytes (M16.1's deliberately
    # simple backend-proxied design, not a streaming/multipart upload
    # architecture), so the file must be read into memory -- but never
    # unboundedly. Reading max+1 bytes and rejecting anything that reaches
    # that ceiling means memory use is capped at evidence_max_upload_bytes
    # regardless of how large the client claims (or attempts) to send.
    max_bytes = get_settings().evidence_max_upload_bytes
    content = await file.read(max_bytes + 1)
    if len(content) > max_bytes:
        raise AeroComplyError(
            f"File exceeds maximum upload size of {max_bytes} bytes",
            code="evidence_file_too_large",
            status_code=413,
        )

    # file_id here is a server-generated token used only to make the storage
    # key unique/tenant-namespaced -- it is independent of whatever primary
    # key the EvidenceFile row itself is assigned by the database. Nothing
    # ever needs to parse it back out of storage_key.
    file_id = uuid.uuid4()
    safe_filename = sanitize_filename(file.filename or "upload")
    storage_key = build_object_key(
        namespace="evidence",
        organization_id=current_user.organization_id,
        resource_id=evidence.id,
        file_id=file_id,
        filename=safe_filename,
    )
    checksum_sha256 = hashlib.sha256(content).hexdigest()

    evidence_file = evidence_file_service.create_pending_file(
        db,
        organization_id=current_user.organization_id,
        actor_user_id=current_user.id,
        evidence_id=evidence.id,
        # original_filename uses the same sanitized, length-bounded value as
        # the storage key's filename segment (sanitize_filename caps at 200
        # chars) rather than the raw client-supplied file.filename, which is
        # unbounded and would otherwise let an oversized filename reach the
        # database as a genuine DataError (String(255) column) instead of
        # being handled safely.
        original_filename=safe_filename,
        content_type=content_type,
        size_bytes=len(content),
        storage_key=storage_key,
        checksum_sha256=checksum_sha256,
    )

    storage_service = get_storage_service()
    try:
        storage_service.put(key=storage_key, body=content, content_type=content_type)
    except StorageUploadError as exc:
        logger.warning(
            "evidence_file_storage_upload_failed",
            evidence_id=str(evidence.id),
            evidence_file_id=str(evidence_file.id),
            organization_id=str(current_user.organization_id),
            error=str(exc),
        )
        evidence_file_service.mark_failed(
            db, organization_id=current_user.organization_id, evidence_file_id=evidence_file.id
        )
        # Never expose the underlying botocore/StorageUploadError message
        # (bucket name, endpoint, credentials context) to the client.
        raise AeroComplyError(
            "Failed to store the uploaded evidence file",
            code="evidence_file_storage_failed",
            status_code=502,
        ) from exc

    try:
        evidence_file = evidence_file_service.mark_stored(
            db, organization_id=current_user.organization_id, evidence_file_id=evidence_file.id
        )
    except Exception:
        # The object was successfully written to storage but the DB
        # transition to STORED failed -- an orphaned object now exists
        # (storage has the bytes; the row is still PENDING, not falsely
        # STORED). This is exactly the partial-failure case M16.8's
        # reconciliation job exists to find and resolve; M16.4 does not
        # implement that job, only logs enough to make it possible later.
        logger.error(
            "evidence_file_mark_stored_failed_after_successful_upload",
            evidence_id=str(evidence.id),
            evidence_file_id=str(evidence_file.id),
            organization_id=str(current_user.organization_id),
            storage_key=storage_key,
        )
        raise

    return EvidenceFileResponse.model_validate(evidence_file)


@router.get("/{evidence_id}/files", response_model=list[EvidenceFileResponse])
def list_evidence_files(
    evidence_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    # Listing/reading file metadata is a read operation on Evidence, not a
    # modification -- EVIDENCE_READ, not EVIDENCE_WRITE, matching the same
    # read/write split already used by get_evidence above.
    current_user: CurrentUser = Depends(require_permission(Permission.EVIDENCE_READ)),
) -> list[EvidenceFileResponse]:
    # list_files_for_evidence resolves Evidence via the caller's own tenant
    # first (NotFoundError on a cross-tenant evidence_id, identical to a
    # nonexistent one), then filters EvidenceFile by that same organization_id
    # -- no direct EvidenceFile query is issued from this router.
    files = evidence_file_service.list_files_for_evidence(
        db, organization_id=current_user.organization_id, evidence_id=evidence_id
    )
    return [EvidenceFileResponse.model_validate(f) for f in files]


@router.get("/{evidence_id}/files/{file_id}/download", response_model=EvidenceFileDownloadResponse)
def download_evidence_file(
    evidence_id: uuid.UUID,
    file_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.EVIDENCE_READ)),
) -> EvidenceFileDownloadResponse:
    # get_file_for_evidence enforces both hops before this function ever sees
    # a storage_key: (1) Evidence belongs to the caller's own organization,
    # (2) the file belongs to that same organization AND that exact Evidence
    # (not just "some evidence in this org") -- so
    # /evidence/A/files/B/download can never return File B's URL if B
    # actually belongs to Evidence C, even within the same tenant.
    evidence_file = evidence_file_service.get_file_for_evidence(
        db,
        organization_id=current_user.organization_id,
        evidence_id=evidence_id,
        evidence_file_id=file_id,
    )

    if evidence_file.status != EvidenceFileStatus.STORED.value:
        # Safe-failure convention: a file that isn't actually in storage yet
        # (PENDING), failed to upload (FAILED), or has been soft-deleted
        # (DELETED) is a real, named state -- not "not found" -- so this uses
        # the same conflict semantics as evidence_file_service's own status
        # transition guard (ConflictError, 409), never inventing a new code.
        raise ConflictError(
            f"Evidence file is not downloadable in status {evidence_file.status}"
        )

    storage_service = get_storage_service()
    try:
        # No expires_in is ever passed through from the request -- the
        # endpoint has no query/body parameter for it at all, so there is no
        # way for a client to request a longer-lived URL than
        # s3_presigned_url_expire_seconds.
        url = storage_service.presign_get(key=evidence_file.storage_key)
    except StoragePresignError as exc:
        logger.warning(
            "evidence_file_presign_failed",
            evidence_id=str(evidence_id),
            evidence_file_id=str(file_id),
            organization_id=str(current_user.organization_id),
            error=str(exc),
        )
        raise AeroComplyError(
            "Failed to generate a download URL for this evidence file",
            code="evidence_file_presign_failed",
            status_code=502,
        ) from exc

    # Deliberately no info-level "issued a download URL" log here containing
    # the URL itself -- only the warning path above logs, and only
    # evidence_id/evidence_file_id/organization_id, never the signed URL.
    return EvidenceFileDownloadResponse(
        url=url, expires_in=get_settings().s3_presigned_url_expire_seconds
    )
