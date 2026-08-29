import uuid
from datetime import datetime

from sqlalchemy import DateTime, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class UUIDPKMixin:
    """Primary key mixin: UUID, generated server-side."""

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TenantScopedMixin:
    """Mixin for tables owned by a single organization (tenant-isolated data).

    Global reference/catalog tables (RegulatoryAuthority, RegulatoryDocument,
    RegulatoryRequirement, ApplicabilityRule) intentionally do NOT use this mixin —
    they are shared across tenants by design (see FOUNDATION.md §9).
    """

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
