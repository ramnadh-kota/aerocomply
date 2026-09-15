import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class EvidenceCreateRequest(BaseModel):
    task_id: uuid.UUID


class EvidenceTransitionRequest(BaseModel):
    target_status: str = Field(min_length=1, max_length=32)
    rejection_reason: str | None = None


class EvidenceResponse(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    task_id: uuid.UUID
    uploaded_by_user_id: uuid.UUID | None
    status: str
    reviewer_user_id: uuid.UUID | None
    rejection_reason: str | None
    created_at: datetime

    class Config:
        from_attributes = True


class EvidenceFileResponse(BaseModel):
    """Deliberately omits storage_key, bucket, and any download URL — those
    are server-internal object-storage details. A download URL is obtained
    separately via EvidenceFileDownloadResponse (see the download endpoint),
    never embedded here."""

    id: uuid.UUID
    evidence_id: uuid.UUID
    original_filename: str
    content_type: str
    size_bytes: int
    checksum_sha256: str | None
    status: str
    created_at: datetime
    deleted_at: datetime | None

    class Config:
        from_attributes = True


class EvidenceFileDownloadResponse(BaseModel):
    """A short-lived download capability. url is a bearer credential — never
    persisted, never logged in full, never cached. expires_in reflects the
    server-configured TTL actually used (s3_presigned_url_expire_seconds),
    never a client-supplied value."""

    url: str
    expires_in: int
