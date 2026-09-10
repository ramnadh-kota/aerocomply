import uuid

from sqlalchemy import ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TenantScopedMixin, TimestampMixin, UUIDPKMixin


class Warehouse(UUIDPKMixin, TenantScopedMixin, TimestampMixin, Base):
    """Minimal warehouse structure — deliberately not a full enterprise WMS
    (no zones/aisles/racking). A single stores/hangar location per site is
    what the existing product actually needs; this can be extended later
    without a breaking change if a real requirement for finer structure
    emerges.
    """

    __tablename__ = "warehouses"
    __table_args__ = (UniqueConstraint("organization_id", "code", name="uq_warehouse_org_code"),)

    code: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)


class Location(UUIDPKMixin, TenantScopedMixin, TimestampMixin, Base):
    """A bin/location within a warehouse (e.g. "Bay 3", "Quarantine Cage").
    Part.location_id (nullable FK) becomes authoritative over
    Part.location (free text) once set — see app/models/part.py's
    docstring on that field for the precedence rule. Part.location stays
    for parts that have never been assigned a structured location.
    """

    __tablename__ = "locations"
    __table_args__ = (
        UniqueConstraint("warehouse_id", "code", name="uq_location_warehouse_code"),
    )

    warehouse_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("warehouses.id"), nullable=False, index=True
    )
    code: Mapped[str] = mapped_column(String(32), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
