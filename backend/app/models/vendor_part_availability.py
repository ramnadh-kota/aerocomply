import uuid

from sqlalchemy import Boolean, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TenantScopedMixin, TimestampMixin, UUIDPKMixin


class PartAvailabilityStatus:
    IN_STOCK = "IN_STOCK"
    LIMITED = "LIMITED"
    OUT_OF_STOCK = "OUT_OF_STOCK"
    ON_ORDER = "ON_ORDER"
    UNKNOWN = "UNKNOWN"


class PartCertificationStatus:
    VERIFIED = "VERIFIED"
    REFERENCE_UNKNOWN = "REFERENCE_UNKNOWN"
    NOT_VERIFIED = "NOT_VERIFIED"
    UNKNOWN = "UNKNOWN"


class VendorPartAvailability(UUIDPKMixin, TenantScopedMixin, TimestampMixin, Base):
    """A vendor's quoted line for a specific part — the source data
    vendor_fit_service scores against. Mirrors frontend/lib/mock/types.ts
    VendorPartAvailability, the type the canonical scoreVendorOptionsForPart
    algorithm (frontend/lib/mock/procurement.ts) already operates on.
    """

    __tablename__ = "vendor_part_availabilities"

    vendor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("vendors.id"), nullable=False, index=True
    )
    part_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("parts.id"), nullable=False, index=True
    )
    availability_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=PartAvailabilityStatus.UNKNOWN
    )
    quantity_available: Mapped[int | None] = mapped_column(Integer, nullable=True)
    lead_time_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Stored as integer cents to avoid float rounding in scoring/comparison;
    # unit_price_cents is null when no quote is on file (never 0).
    unit_price_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    currency: Mapped[str | None] = mapped_column(String(8), nullable=True)
    aog_availability: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    certification_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=PartCertificationStatus.UNKNOWN
    )
