import uuid
from enum import StrEnum

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

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


class Evidence(UUIDPKMixin, TenantScopedMixin, TimestampMixin, Base):
    __tablename__ = "evidence"

    task_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tasks.id"), nullable=False, index=True
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
