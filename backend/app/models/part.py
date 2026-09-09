from sqlalchemy import Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TenantScopedMixin, TimestampMixin, UUIDPKMixin


class Part(UUIDPKMixin, TenantScopedMixin, TimestampMixin, Base):
    __tablename__ = "parts"

    part_number: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    manufacturer: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # e.g. NEW / SERVICEABLE / OVERHAULED — free-text for now, not an enum, since
    # condition vocabularies vary by vendor/authority and M3 is persistence-only.
    condition: Mapped[str | None] = mapped_column(String(32), nullable=True)
    quantity_on_hand: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    quantity_reserved: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    @property
    def available_quantity(self) -> int:
        """Derived, not stored — always on_hand minus reserved so it can never drift."""
        return self.quantity_on_hand - self.quantity_reserved
