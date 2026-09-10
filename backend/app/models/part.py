from sqlalchemy import Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TenantScopedMixin, TimestampMixin, UUIDPKMixin


class PartServiceabilityStatus:
    """Distinct from quantity tracking — this is the disposition of the part
    itself. Never auto-transitioned by a receiving event (see
    inventory_transaction_service.receive_part): a received part stays
    whatever status it already had until a human/inspection workflow
    explicitly changes it. Only quarantine_part/release_quarantine in this
    slice actually move a part between statuses.
    """

    SERVICEABLE = "SERVICEABLE"
    UNSERVICEABLE = "UNSERVICEABLE"
    QUARANTINED = "QUARANTINED"
    INCOMING = "INCOMING"
    RESERVED = "RESERVED"
    INSTALLED = "INSTALLED"
    CONSUMED = "CONSUMED"
    SCRAPPED = "SCRAPPED"


class Part(UUIDPKMixin, TenantScopedMixin, TimestampMixin, Base):
    __tablename__ = "parts"

    part_number: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    manufacturer: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # e.g. NEW / SERVICEABLE / OVERHAULED — free-text for now, not an enum, since
    # condition vocabularies vary by vendor/authority and M3 is persistence-only.
    condition: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # Traceability fields — nullable because genuinely unknown/not-applicable
    # for many parts (e.g. batch-tracked parts have no serial_number; see the
    # same UNKNOWN vs NOT_APPLICABLE distinction the frontend type documents
    # for this exact field, frontend/lib/mock/types.ts Part.serialNumber).
    serial_number: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    batch_or_lot: Mapped[str | None] = mapped_column(String(128), nullable=True)
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    serviceability_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=PartServiceabilityStatus.SERVICEABLE
    )
    # Only meaningful when serviceability_status == QUARANTINED; null otherwise.
    quarantine_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    quantity_on_hand: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    quantity_reserved: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    quantity_quarantined: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    @property
    def available_quantity(self) -> int:
        """Derived, not stored — on_hand minus reserved minus quarantined, so
        it can never drift and quarantined stock is never silently issuable.
        """
        return self.quantity_on_hand - self.quantity_reserved - self.quantity_quarantined
