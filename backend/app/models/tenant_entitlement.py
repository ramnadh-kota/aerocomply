"""Tenant-specific entitlement adjustments layered on top of a Subscription's
plan: per-tenant feature overrides and per-tenant usage limits.

Neither model implements any evaluation logic here (no "is feature X enabled
for org Y" resolver exists yet) -- that belongs to a future
entitlement-resolution service (see
docs/PLATFORM_CONTROL_PLANE_ARCHITECTURE.md, "M1 Implementation").
"""
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TenantScopedMixin, TimestampMixin, UUIDPKMixin


class TenantFeatureOverride(UUIDPKMixin, TenantScopedMixin, TimestampMixin, Base):
    """An explicit per-tenant override of a feature flag, independent of the
    tenant's plan (e.g. a support-granted trial of a feature, or a
    contractual carve-out).

    M1 note: preventing two simultaneously-*active* (non-expired) override
    rows for the same (organization_id, feature_key) is NOT enforced at the
    database level -- a partial unique index (`WHERE expires_at IS NULL OR
    expires_at > now()`) would need a non-immutable `now()` predicate that
    Postgres partial indexes cannot express directly, and no existing
    migration in this codebase uses a partial index at all (see Subscription
    in app/models/subscription.py for the same reasoning applied to
    overlapping ACTIVE subscriptions). This is an ANNOTATED FUTURE
    RESPONSIBILITY for the entitlement-resolution service.
    """

    __tablename__ = "tenant_feature_overrides"

    feature_key: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Nullable actor reference -- matches TechnicianQualification.granted_by_user_id's
    # convention (app/models/technician_qualification.py) for an optional
    # "who did this" FK that must never block the row if the user is gone.
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    # null = no expiry.
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class TenantUsageLimit(UUIDPKMixin, TenantScopedMixin, TimestampMixin, Base):
    """A per-tenant numeric usage ceiling for one (feature_key, limit_key)
    dimension, e.g. feature_key="LISA", limit_key="monthly_queries". No
    usage-metering system exists yet -- this table only stores the
    configured ceiling, not any observed usage count.
    """

    __tablename__ = "tenant_usage_limits"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "feature_key",
            "limit_key",
            name="uq_tenant_usage_limits_org_feature_limit",
        ),
    )

    feature_key: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    limit_key: Mapped[str] = mapped_column(String(128), nullable=False)
    # Ignored (should be null) when is_unlimited is True -- never a magic
    # sentinel number like -1 or 0 for "unlimited".
    limit_value: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_unlimited: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
