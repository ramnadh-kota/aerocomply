import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, func
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


class SoftDeleteMixin:
    """Platform Control Plane: shared soft-delete lifecycle metadata.

    A tenant "deleting" a record covered by this mixin never issues a SQL
    DELETE — it sets deleted_at/deleted_by/deletion_reason (see
    app/services/deletion_service.py). The row still exists; tenant-facing
    reads filter it out (WHERE deleted_at IS NULL), while Platform Admin's
    deleted-records view deliberately does not, so Platform can see, restore,
    or (as a separate, privileged step) permanently delete it.

    restored_at/restored_by are only ever set by Platform Admin restoring a
    row (app/services/restoration_service.py); a never-deleted row leaves
    all five columns null. Only ONE physical DELETE path exists for a
    soft-deletable entity: Platform Admin's permanent-delete action — never
    a tenant-facing route, and never automatic.
    """

    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deleted_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    deletion_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    restored_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    restored_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
