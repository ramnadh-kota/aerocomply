import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TenantScopedMixin, TimestampMixin, UUIDPKMixin


class TechnicianQualification(UUIDPKMixin, TenantScopedMixin, TimestampMixin, Base):
    """A real, persistent grant that one User is qualified to work a given
    aircraft_type (matching Aircraft.aircraft_type — the only aircraft
    classification that already exists in this schema; there is no separate
    variant/model table to key off). Deliberately not a full HR/training
    record system: no course history, no certificate documents, no renewal
    workflow — just the minimal fact a real authorization decision needs.

    aircraft_type is a plain string column (like Aircraft.aircraft_type
    itself), not an FK, matched by equality — the same pattern this codebase
    already uses for PartRequirementStatus/EvidenceStatus etc: a small,
    indexed, free-form value rather than a lookup table that doesn't exist
    yet.
    """

    __tablename__ = "technician_qualifications"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    aircraft_type: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    qualification_type: Mapped[str] = mapped_column(String(64), nullable=False)
    granted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    granted_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
