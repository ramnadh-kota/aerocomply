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
    # M21.4: optional link from the commercial Plan catalog (this file) to the
    # platform PRODUCT catalog (app/models/product_catalog.py::ProductSuite).
    # Nullable because every plan created before this column existed (and any
    # future plan that legitimately bundles no specific suite, e.g. a
    # platform-internal/testing plan) must keep working unchanged -- a
    # fail-open default here would be wrong (Section 19 of
    # docs/PLATFORM_CONTROL_PLANE_ARCHITECTURE.md warns against fail-open
    # entitlement defaults), but this FK is deliberately NOT part of
    # entitlement resolution (app/services/entitlement_service.py is
    # untouched by this column) -- it is catalog metadata only, answering
    # "which product suite is this plan for" for platform-admin UI/reporting,
    # the same soft, non-authoritative role ProductFeature.code already plays
    # relative to PlanFeature.feature_key (see product_catalog.py's module
    # docstring). One suite per plan (not a many-to-many join table): every
    # real plan surfaced by this codebase so far (STARTER/PROFESSIONAL/
    # ENTERPRISE-style tiers per the architecture doc, Section 4) is a tier
    # of ONE product line, not a bundle of several distinct suites -- a
    # multi-suite bundle would be a different Plan row per suite (or a
    # dedicated bundling concept) rather than overloading this FK, so a
    # nullable single FK is the accurately-scoped choice, not a
    # speculative join table for a multiplicity that doesn't exist yet.
    suite_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("product_suites.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
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
