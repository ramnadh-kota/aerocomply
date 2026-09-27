import datetime
import uuid
from enum import StrEnum

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TenantScopedMixin, TimestampMixin, UUIDPKMixin


class EvidenceStatus(StrEnum):
    """Evidence lifecycle. Only ACCEPTED satisfies the completion/release gate —
    SUBMITTED and AWAITING_REVIEW must never be treated as equivalent to ACCEPTED
    (see app/services/evidence_service.py::satisfies_completion_gate).
    """

    REQUIRED = "REQUIRED"
    UPLOADED = "UPLOADED"
    SUBMITTED = "SUBMITTED"
    AWAITING_REVIEW = "AWAITING_REVIEW"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"


class EvidenceFileStatus(StrEnum):
    """Physical object-storage state of one uploaded file — a separate concept
    from EvidenceStatus (the review/acceptance lifecycle of the evidence
    record itself). A single Evidence row may have zero or more EvidenceFile
    rows; this status tracks whether *this particular file* actually made it
    into object storage, independent of whether the evidence has been
    reviewed/accepted. Set by the (not-yet-built) upload flow in M16.4:
    PENDING immediately after the metadata row is inserted, then STORED or
    FAILED once the actual object-storage call returns; DELETED marks a
    soft-deleted row (M16.6) without implying the underlying object was
    removed from storage.
    """

    PENDING = "PENDING"
    STORED = "STORED"
    FAILED = "FAILED"
    DELETED = "DELETED"


class Evidence(UUIDPKMixin, TenantScopedMixin, TimestampMixin, Base):
    __tablename__ = "evidence"

    # task_id is nullable: evidence can attach directly to tasks (MRO release gate)
    # or to compliance obligations, regulatory requirements, assets, aircraft, etc.
    task_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tasks.id"), nullable=True, index=True
    )
    compliance_obligation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("compliance_obligations.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    regulatory_requirement_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("regulatory_requirements.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    asset_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("assets.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    aircraft_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("aircraft.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    component_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("components.id", ondelete="SET NULL"),
        nullable=True,
    )
    inspection_requirement_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("inspection_requirements.id", ondelete="SET NULL"),
        nullable=True,
    )
    finding_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("findings.id", ondelete="SET NULL"),
        nullable=True,
    )
    work_order_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("work_orders.id", ondelete="SET NULL"),
        nullable=True,
    )

    # First-class metadata
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_type: Mapped[str] = mapped_column(
        String(64), nullable=False, default="INSPECTION_RECORD"
    )
    source: Mapped[str | None] = mapped_column(String(255), nullable=True)
    captured_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    uploaded_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=EvidenceStatus.REQUIRED.value
    )
    reviewer_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Verification workflow
    verification_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="UNVERIFIED", index=True
    )
    verified_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    verifier_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    verification_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    provenance: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # cascade="all, delete-orphan" only affects ORM-level deletion of
    # EvidenceFile *rows* if an Evidence row is ever deleted
    files: Mapped[list["EvidenceFile"]] = relationship(
        back_populates="evidence", cascade="all, delete-orphan"
    )
    obligation = relationship("ComplianceObligation", back_populates="evidence_items")
    requirement = relationship("RegulatoryRequirement")
    verifier = relationship("User", foreign_keys=[verifier_user_id])



class EvidenceFile(UUIDPKMixin, TenantScopedMixin, TimestampMixin, Base):
    """Metadata for one uploaded file backing an Evidence record.

    Schema/model only as of M16.2 — nothing yet writes to object storage or
    populates these rows; that begins in M16.4. organization_id is stored
    here in addition to being reachable via evidence_id -> evidence.
    organization_id deliberately, for the same reason every other tenant
    table in this codebase carries its own organization_id directly (see
    TenantScopedMixin): direct tenant-scoped filtering without a join, and
    defense-in-depth against a future query that forgets to join through
    Evidence. There is no DB-level constraint enforcing
    evidence_files.organization_id == evidence.organization_id (see the
    M16.2 migration docstring for why) — M16.3's service layer is
    responsible for verifying that invariant before ever writing a row.
    """

    __tablename__ = "evidence_files"
    __table_args__ = (
        CheckConstraint("size_bytes >= 0", name="ck_evidence_files_size_bytes_non_negative"),
        # Supports "active/pending/failed files for an organization" queries
        # (e.g. a future reconciliation job) without a full table scan.
        Index("ix_evidence_files_organization_id_status", "organization_id", "status"),
        # Supports a future cross-tenant reconciliation scan (M16.8) for
        # stuck PENDING/FAILED rows across all organizations.
        Index("ix_evidence_files_status", "status"),
    )

    evidence_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("evidence.id"), nullable=False, index=True
    )
    uploaded_by_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    # The original, human-readable filename as supplied by the uploader —
    # never the sanitized object-key filename segment built by
    # app.services.storage.keys.build_object_key. Length matches the
    # existing ImportJob.filename precedent (app/models/import_job.py).
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(255), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    # Server-generated object-storage key (see app.services.storage.keys) —
    # never a client-supplied path, never a URL. Sized generously for the
    # namespace/org-uuid/resource-uuid/file-uuid_filename shape that helper
    # produces.
    storage_key: Mapped[str] = mapped_column(String(512), nullable=False, unique=True)
    # Nullable: M16.2 only creates metadata rows: no upload flow exists yet
    # to compute a real digest, and fabricating one here would be worse than
    # honestly representing "not yet known". M16.4 (the actual upload flow)
    # populates this once the file is hashed.
    checksum_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Deliberately a plain String, not a native Postgres enum type, and with
    # no DB-level CHECK restricting it to EvidenceFileStatus's members —
    # matching every other status column in this codebase (Evidence.status,
    # PurchaseOrderStatus, ApprovalRequestStatus, ImportJobStatus, ...),
    # none of which use a native enum or a value-list CHECK either. Valid
    # values are enforced in the application layer via EvidenceFileStatus.
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=EvidenceFileStatus.PENDING.value
    )
    # Soft-delete marker for M16.6 — no code path sets this yet.
    deleted_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    evidence: Mapped[Evidence] = relationship(back_populates="files")
