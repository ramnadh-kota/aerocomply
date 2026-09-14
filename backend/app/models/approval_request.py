"""M14: governance approval requests for high-impact (expansive) tenant
entitlement mutations.

This is a small, dedicated governance model -- NOT a generic workflow
engine. It only ever wraps the two mutation kinds M6 already classifies as
EXPANSIVE (see app/services/tenant_entitlement_admin_service.py):
enabling a feature override that the tenant's plan does not already grant,
and raising/unlimiting a usage limit. Restrictive/neutral changes never go
through this table -- they continue to use the M6 mutation endpoints
directly, unchanged.

Tenant-scoped (TenantScopedMixin) like Subscription/TenantFeatureOverride/
TenantUsageLimit, because every request concerns one specific organization's
entitlements. Platform admins review across all organizations the same way
they already administer subscriptions/overrides/limits cross-tenant.

Lifecycle: PENDING -> APPROVED | REJECTED | CANCELED. No other states --
there is no asynchronous process here, so no "processing" state either
(approval executes the underlying M6 mutation synchronously, in the same
request).

Snapshot fields (request_type/feature_key/requested_enabled/limit_key/
requested_limit_value/requested_is_unlimited/reason) are typed and
validated at the service layer, not an arbitrary JSON blob -- the review
must be deterministic from these columns alone.

Four-eyes note (see docs on approval_service.approve_approval_request): as
of M15, approval_service enforces requested_by_user_id != reviewer at
approval time (403 if violated) -- requested_by_user_id and
reviewed_by_user_id remain plain, independent columns here purely as an
honest audit trail, but they can no longer end up equal for a real
approval (both non-null and identical is now blocked server-side).
"""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TenantScopedMixin, TimestampMixin, UUIDPKMixin


class ApprovalRequestStatus:
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    CANCELED = "CANCELED"


ALL_APPROVAL_STATUSES = frozenset(
    {
        ApprovalRequestStatus.PENDING,
        ApprovalRequestStatus.APPROVED,
        ApprovalRequestStatus.REJECTED,
        ApprovalRequestStatus.CANCELED,
    }
)


class ApprovalRequestType:
    FEATURE_OVERRIDE_EXPANSION = "feature_override_expansion"
    USAGE_LIMIT_EXPANSION = "usage_limit_expansion"


ALL_APPROVAL_REQUEST_TYPES = frozenset(
    {
        ApprovalRequestType.FEATURE_OVERRIDE_EXPANSION,
        ApprovalRequestType.USAGE_LIMIT_EXPANSION,
    }
)


class ApprovalRequest(UUIDPKMixin, TenantScopedMixin, TimestampMixin, Base):
    __tablename__ = "approval_requests"

    request_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=ApprovalRequestStatus.PENDING, index=True
    )

    # WHAT is requested -- typed/validated fields, never an arbitrary blob.
    feature_key: Mapped[str] = mapped_column(String(128), nullable=False)
    requested_enabled: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    limit_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    requested_limit_value: Mapped[int | None] = mapped_column(Integer, nullable=True)
    requested_is_unlimited: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    # WHO / WHEN.
    requested_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    reviewed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decision_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
