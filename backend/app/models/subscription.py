"""Tenant subscription history.

A Subscription row is a historical fact: "organization X was on plan Y from
starts_at to ends_at (or open-ended) with status Z". Rows are never deleted
or overwritten to reflect a plan change -- a plan change creates a new
Subscription row, preserving history (this is exactly the design rejected in
docs/PLATFORM_CONTROL_PLANE_ARCHITECTURE.md Section 21: a single
organizations.plan_id column would destroy that history on every change).
"""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TenantScopedMixin, TimestampMixin, UUIDPKMixin


class SubscriptionStatus:
    TRIALING = "TRIALING"
    ACTIVE = "ACTIVE"
    PAST_DUE = "PAST_DUE"
    CANCELED = "CANCELED"
    SCHEDULED = "SCHEDULED"


class Subscription(UUIDPKMixin, TenantScopedMixin, TimestampMixin, Base):
    """M1 note on overlapping ACTIVE subscriptions: no existing migration in
    this codebase uses a Postgres partial unique index, so -- per the
    architecture doc's Phase 3 guidance -- this is NOT enforced at the
    database level here, to avoid introducing an exotic constraint pattern
    the rest of the schema doesn't already use. This is an ANNOTATED FUTURE
    RESPONSIBILITY: the entitlement-resolution service that does not exist
    yet must reject (or otherwise unambiguously resolve) more than one
    concurrently-ACTIVE Subscription for the same organization_id. See
    tests/integration/test_platform_control_plane.py for the test that
    documents this as a deliberately-unenforced invariant.
    """

    __tablename__ = "subscriptions"
    __table_args__ = (
        Index(
            "ix_subscriptions_org_status_starts_at",
            "organization_id",
            "status",
            "starts_at",
        ),
    )

    # RESTRICT: never let deleting a Plan cascade into destroying a tenant's
    # subscription history.
    plan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("plans.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # null = open-ended (no known end date yet).
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
