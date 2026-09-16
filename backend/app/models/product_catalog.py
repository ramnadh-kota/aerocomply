"""Phase 18.2: platform-level product catalog (Suite -> Module -> Page /
Feature).

This is a PLATFORM catalog, not a tenant table -- exactly like Plan/
PlanFeature (app/models/plan.py), none of these four models use
TenantScopedMixin: a suite/module/page/feature is defined once by the
platform operator and referenced (by stable `code`, never by row identity)
across every organization's commercial state, the same "global reference/
catalog table" pattern already established for Plan.

WHAT THIS IS NOT:
  - Not a second authorization system. ProductFeature.code is a plain,
    loosely-coupled string, matching the existing convention every
    commercial-entitlement table already uses (PlanFeature.feature_key,
    TenantFeatureOverride.feature_key, TenantUsageLimit.feature_key,
    app.core.deps.require_feature's feature_key parameter -- see
    app/services/entitlement_service.py). There is deliberately NO foreign
    key from plan_features.feature_key (or any of those other tables) to
    product_features.code: PlanFeature/TenantFeatureOverride/
    TenantUsageLimit already exist, are already exercised by passing M17.3
    tests, and this milestone's explicit instruction is "existing M17.3
    behavior must remain unchanged" -- adding a hard FK would require
    validating every feature_key value already in use anywhere in the
    database at migration time, which is a real behavior/compatibility risk
    for zero functional gain (the resolution engine, entitlement_service.
    resolve_entitlements, never needs to join through the catalog at all;
    it already works purely off PlanFeature/TenantFeatureOverride rows).
    ProductFeature.code is simply the recommended, documented value to use
    as a PlanFeature.feature_key / require_feature() argument when a
    feature is meant to represent a cataloged product capability.
  - Not a replacement for permission checks (app.core.permissions.Permission
    remains the only source of "can this user act").
  - Not a rollout/feature-flag system. is_active here means "this catalog
    entry currently represents a real, supported part of the product" (an
    editorial/inventory concept), not "toggle this code path on/off for a
    subset of users/orgs" -- no such mechanism exists in this codebase and
    none is introduced here.

HIERARCHY (Feature belongs to Module, not Page): every feature_key already
in real use in this codebase before this milestone (see
app/services/entitlement_service.py's own examples and
app/core/deps.py::require_feature's docstring, e.g. "drone_operations")
represents a module-granularity capability, not a specific page/screen --
there is no existing evidence anywhere in this repository of a
page-specific commercial feature. Modeling ProductFeature under
ProductModule (not ProductPage) reflects that truthfully rather than
inventing an unused finer-grained relationship; if a genuinely
page-specific feature need appears later, that is a schema-additive change
for that future milestone, not something to speculatively build now.
"""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPKMixin


class ProductSuite(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "product_suites"

    code: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    modules: Mapped[list["ProductModule"]] = relationship(
        back_populates="suite", order_by="ProductModule.display_order"
    )


class ProductModule(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "product_modules"

    # RESTRICT: a suite with existing modules must never be silently
    # destroyed by a cascading delete -- matching Plan/PlanFeature's
    # established convention (app/models/plan.py) for the same reasoning.
    suite_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("product_suites.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    code: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    suite: Mapped[ProductSuite] = relationship(back_populates="modules")
    pages: Mapped[list["ProductPage"]] = relationship(
        back_populates="module", order_by="ProductPage.display_order"
    )
    features: Mapped[list["ProductFeature"]] = relationship(
        back_populates="module", order_by="ProductFeature.code"
    )


class ProductPage(UUIDPKMixin, TimestampMixin, Base):
    """A UI/navigation screen. Deliberately NOT a security boundary (see
    module docstring) -- `route` is informational only, for admin display
    and future frontend cross-referencing, never consulted by any
    authorization check."""

    __tablename__ = "product_pages"

    module_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("product_modules.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    code: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    route: Mapped[str | None] = mapped_column(String(255), nullable=True)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    module: Mapped[ProductModule] = relationship(back_populates="pages")


class ProductFeature(UUIDPKMixin, TimestampMixin, Base):
    """The canonical catalog definition of a product capability -- what
    PlanFeature.feature_key / TenantFeatureOverride.feature_key /
    require_feature()'s feature_key argument SHOULD reference by convention
    (see module docstring for why this is a soft, code-based convention and
    not a foreign key)."""

    __tablename__ = "product_features"

    module_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("product_modules.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    # Globally unique, not per-module: this code is the same string used as
    # PlanFeature.feature_key / require_feature()'s argument (see module
    # docstring) -- the commercial-entitlement layer has no concept of
    # "module" to disambiguate two features with the same code, so the code
    # itself must be unambiguous platform-wide, exactly like
    # ProductSuite/ProductModule/ProductPage.code above.
    code: Mapped[str] = mapped_column(String(128), nullable=False, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    module: Mapped[ProductModule] = relationship(back_populates="features")
