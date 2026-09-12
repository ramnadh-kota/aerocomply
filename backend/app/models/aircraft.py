from sqlalchemy import String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TenantScopedMixin, TimestampMixin, UUIDPKMixin


class Aircraft(UUIDPKMixin, TenantScopedMixin, TimestampMixin, Base):
    __tablename__ = "aircraft"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "registration", name="uq_aircraft_organization_id_registration"
        ),
    )

    registration: Mapped[str] = mapped_column(String(16), nullable=False)
    msn: Mapped[str] = mapped_column(String(64), nullable=False)
    aircraft_type: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="ACTIVE")
