from sqlalchemy import Boolean, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TenantScopedMixin, TimestampMixin, UUIDPKMixin


class Vendor(UUIDPKMixin, TenantScopedMixin, TimestampMixin, Base):
    __tablename__ = "vendors"

    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    contact_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Comma-separated text rather than JSONB: certifications here are a small,
    # display-only free-text list (no querying/filtering by individual cert is
    # required in this slice), matching the plain-string style used elsewhere in
    # this model layer (e.g. Aircraft.status, Part.condition) rather than
    # introducing the first JSONB column in the schema for a feature not yet needed.
    certifications: Mapped[str | None] = mapped_column(Text, nullable=True)
    approved: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
