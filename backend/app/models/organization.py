from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPKMixin


class OrganizationStatus:
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"


class OrganizationIndustry:
    """M21.4: which aerospace vertical this tenant operates in. A plain
    string-constant class, matching this codebase's existing convention for
    small classification concepts (OrganizationStatus above,
    SubscriptionStatus, DeferredItemStatus, etc.) rather than a Postgres/
    SQLAlchemy Enum type or a separate lookup table.

    Deliberately NOT a new table: this was considered (an `industries`
    catalog row per value, mirroring ProductSuite) and rejected because
    nothing in this codebase's real usage needs industry rows to carry their
    own metadata (description, display_order, activation state) the way
    ProductSuite genuinely does for platform-catalog administration --
    Organization.industry is a pure classification tag on the tenant, exactly
    the same shape as Organization.status, and a four-value fixed set with no
    admin-editable metadata does not warrant a table.

    Deliberately NOT modeled on ProductSuite: ProductSuite already exists in
    this codebase (app/models/product_catalog.py) but its real seeded content
    (backend/scripts/seed_product_catalog.py: code="maintenance") represents
    a WORKFLOW DOMAIN ("Maintenance"), not an aerospace asset vertical -- the
    two axes are orthogonal (e.g. a "Maintenance" suite's work-order-tracking
    module applies equally to a drone operator or a fixed-wing operator).
    Overloading ProductSuite to also mean "industry" would conflate two
    genuinely different classification axes into one field, which is exactly
    the kind of conflation docs/PLATFORM_CONTROL_PLANE_ARCHITECTURE.md
    Section 19 warns against for OrganizationStatus vs. subscription status.
    """

    DRONE_UAV = "DRONE_UAV"
    AIRCRAFT = "AIRCRAFT"
    HELICOPTER = "HELICOPTER"
    EVTOL_AAM = "EVTOL_AAM"


class Organization(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "organizations"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # Platform-managed tenant lifecycle status — never a billing/subscription
    # engine (none exists in this codebase); a plain field a platform admin
    # toggles. A SUSPENDED organization's users are refused at login (see
    # auth_service) rather than merely hidden in the UI.
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=OrganizationStatus.ACTIVE
    )
    # M21.4: nullable because every organization created before this column
    # existed has no industry on record -- there is no sensible default to
    # backfill (guessing wrong is worse than leaving it unset), so existing
    # orgs simply read back NULL until a platform admin sets one explicitly.
    # See OrganizationIndustry above for why this lives here rather than on
    # Plan or ProductSuite.
    industry: Mapped[str | None] = mapped_column(String(32), nullable=True)
