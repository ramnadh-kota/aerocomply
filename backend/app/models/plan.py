"""Platform-level (global, not tenant-scoped) subscription plan catalog.

Plan and PlanFeature intentionally do NOT use TenantScopedMixin — a plan is
defined once by the platform operator and referenced by many tenants'
subscriptions, the same "global reference/catalog table" pattern documented
in TenantScopedMixin's own docstring for RegulatoryAuthority etc.

No entitlement-evaluation engine exists yet (see
docs/PLATFORM_CONTROL_PLANE_ARCHITECTURE.md, "M1 Implementation" section) --
these are pure schema/domain foundation for that future work.
"""
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPKMixin


class Plan(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "plans"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    code: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class PlanFeature(UUIDPKMixin, TimestampMixin, Base):
    """A single feature_key flag attached to a Plan. `enabled=False` rows are
    kept (rather than omitted) so a plan's full feature surface is explicit
    and auditable, not inferred from absence.
    """

    __tablename__ = "plan_features"
    __table_args__ = (
        UniqueConstraint("plan_id", "feature_key", name="uq_plan_features_plan_id_feature_key"),
    )

    # RESTRICT: a plan with historical subscriptions (or feature rows) must
    # never be silently destroyed by a cascading delete -- see Subscription
    # below for the same reasoning applied to subscription history.
    plan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("plans.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    feature_key: Mapped[str] = mapped_column(String(128), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
