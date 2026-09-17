from datetime import datetime

from sqlalchemy import DateTime, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TenantScopedMixin, TimestampMixin, UUIDPKMixin


class FacilityType:
    """Small, closed vocabulary -- plain string constants, matching this
    codebase's established convention for small closed sets (see
    EvidenceFile.status, ProductSuite.code) rather than a DB enum type.
    OTHER exists so a real customer facility that doesn't fit the list can
    still be recorded truthfully instead of forcing a wrong classification."""

    HANGAR = "HANGAR"
    WORKSHOP = "WORKSHOP"
    WAREHOUSE = "WAREHOUSE"
    STATION = "STATION"
    OFFICE = "OFFICE"
    STORE = "STORE"
    OTHER = "OTHER"


class FacilityStatus:
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"


class Facility(UUIDPKMixin, TenantScopedMixin, TimestampMixin, Base):
    """Phase 18.4: tenant-owned physical operational site (hangar,
    workshop, warehouse, station, office, store, ...) -- the canonical
    parent for assets going forward (Organization -> Facility -> Asset),
    intentionally asset-type-agnostic so it works for aircraft, drones, and
    future asset types alike without a schema change per type.

    Deliberately NOT the same table as app.models.warehouse.Warehouse:
    Warehouse is a narrower, already-established concept scoped to the
    parts/inventory domain (gated by Permission.PART_READ/PART_WRITE, with
    its own Location/bin substructure for stock-keeping). Facility is a
    general operational-site concept for any physical location an asset
    can be based at or serviced at, gated by its own
    Permission.FACILITY_READ/FACILITY_WRITE. Merging the two would either
    weaken Warehouse's inventory-specific authorization or force every
    Facility (an office, a drone launch station) to carry inventory
    semantics it doesn't have -- both are broader, riskier changes than
    this milestone's scope justifies. A future milestone may reconsider
    consolidation once Asset Foundation Phase 1B clarifies real usage
    patterns; deferred here deliberately, not overlooked.

    No GIS/maps/geofencing/coordinates -- see this migration's own
    docstring and docs/ARCHITECTURE_ASSET_FOUNDATION.md for the explicit
    scope boundary. `code` is unique per organization only (not globally),
    matching Warehouse.code's own precedent.
    """

    __tablename__ = "facilities"
    __table_args__ = (
        UniqueConstraint("organization_id", "code", name="uq_facilities_organization_id_code"),
    )

    code: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    facility_type: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default=FacilityStatus.ACTIVE)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
