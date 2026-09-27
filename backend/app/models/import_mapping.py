import uuid

from sqlalchemy import Boolean, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TenantScopedMixin, TimestampMixin, UUIDPKMixin


class TenantImportMapping(UUIDPKMixin, TenantScopedMixin, TimestampMixin, Base):
    """M5.6: Saved column mapping configuration per organization.

    Persists customer spreadsheet header mappings (e.g., 'Reg No' -> 'registration',
    'FH' -> 'flight_hours') so subsequent imports from the same operator
    automatically resolve their standard format without manual re-mapping.
    Strictly tenant-scoped to preserve organization isolation.
    """

    __tablename__ = "tenant_import_mappings"

    domain: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    mapping: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )


__all__ = ["TenantImportMapping"]
