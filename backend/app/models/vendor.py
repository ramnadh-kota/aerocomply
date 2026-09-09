from sqlalchemy import Boolean, Integer, String, Text
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
    # 0-100, nullable — null means no scoring basis exists yet. Never defaulted
    # to 0 by application code; that would fabricate a reliability judgement
    # (see vendor_fit_service, which treats a null score as a missing factor,
    # not a zero score).
    reliability_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
