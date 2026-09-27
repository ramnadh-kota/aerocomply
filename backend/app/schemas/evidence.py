import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class EvidenceCreateRequest(BaseModel):
    task_id: uuid.UUID | None = None
    compliance_obligation_id: uuid.UUID | None = None
    regulatory_requirement_id: uuid.UUID | None = None
    asset_id: uuid.UUID | None = None
    aircraft_id: uuid.UUID | None = None
    component_id: uuid.UUID | None = None
    inspection_requirement_id: uuid.UUID | None = None
    finding_id: uuid.UUID | None = None
    work_order_id: uuid.UUID | None = None
    title: str | None = Field(default=None, max_length=255)
    description: str | None = None
    evidence_type: str = Field(default="INSPECTION_RECORD", max_length=64)
    source: str | None = Field(default=None, max_length=255)
    captured_at: datetime | None = None
    provenance: dict | None = None


class EvidenceTransitionRequest(BaseModel):
    target_status: str = Field(min_length=1, max_length=32)
    rejection_reason: str | None = None


class EvidenceVerifyRequest(BaseModel):
    verification_notes: str | None = None


class EvidenceRejectRequest(BaseModel):
    rejection_reason: str = Field(min_length=1)


class EvidenceResponse(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    task_id: uuid.UUID | None = None
    compliance_obligation_id: uuid.UUID | None = None
    regulatory_requirement_id: uuid.UUID | None = None
    asset_id: uuid.UUID | None = None
    aircraft_id: uuid.UUID | None = None
    component_id: uuid.UUID | None = None
    inspection_requirement_id: uuid.UUID | None = None
    finding_id: uuid.UUID | None = None
    work_order_id: uuid.UUID | None = None
    title: str | None = None
    description: str | None = None
    evidence_type: str
    source: str | None = None
    captured_at: datetime | None = None
    uploaded_by_user_id: uuid.UUID | None = None
    status: str
    reviewer_user_id: uuid.UUID | None = None
    rejection_reason: str | None = None
    verification_status: str
    verified_at: datetime | None = None
    verifier_user_id: uuid.UUID | None = None
    verification_notes: str | None = None
    provenance: dict | None = None
    created_at: datetime
    updated_at: datetime | None = None

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
