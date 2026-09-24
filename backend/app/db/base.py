import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, func
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


class LifecycleMixin:
    """Soft-delete/restore lifecycle columns, reusable across entities.

    deleted_at IS NULL is the single authoritative condition for "currently
    active" -- restored_at/restored_by are set on restore but never combined
    with deleted_at in a query; a full delete/restore history lives in the
    audit trail, not in these columns (they only reflect the most recent
    transition). Actor FKs intentionally have no ondelete behavior -- they
    must never be nulled or cascaded away, preserving attribution even if a
    user is later deactivated.
    """

    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deleted_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    restored_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    restored_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
