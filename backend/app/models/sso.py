"""M13 Phase 4 & 5: Enterprise Identity (SSO / Microsoft Entra ID) and Operational Incident Observability models.

Architecture & Security:
- SSOConfiguration: Tenant-level OIDC/Entra ID SSO integration settings and role mapping rules.
- ExternalIdentityMapping: Deterministic linkage between external IdP subjects (Entra sub/oid) and KOTA Users.
- OperationalIncident: Operational & infrastructure incident tracking (P0-P3) for production hypercare.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TenantScopedMixin, TimestampMixin, UUIDPKMixin

if TYPE_CHECKING:
    from app.models.user import User


class SSOProviderType:
    ENTRA_ID = "ENTRA_ID"
    OIDC = "OIDC"
    SAML = "SAML"


class SSOConfiguration(UUIDPKMixin, TenantScopedMixin, TimestampMixin, Base):
    """Tenant-scoped SSO configuration for enterprise Identity Providers."""

    __tablename__ = "sso_configurations"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "provider_type",
            name="uq_sso_config_org_provider",
        ),
        Index("ix_sso_config_org", "organization_id"),
    )

    provider_type: Mapped[str] = mapped_column(
        String(64), nullable=False, default=SSOProviderType.ENTRA_ID
    )
    issuer_url: Mapped[str] = mapped_column(String(512), nullable=False)
    client_id: Mapped[str] = mapped_column(String(255), nullable=False)
    client_secret_hash: Mapped[str | None] = mapped_column(String(512), nullable=True)
    tenant_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    enforce_sso: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    default_role: Mapped[str] = mapped_column(String(64), default="VIEWER", nullable=False)
    domain_hint: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Role mapping config: e.g. {"Aviation-Admins": "ORG_ADMIN", "CAMO-Team": "CAMO_MANAGER"}
    role_mappings: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        server_default=func.now(),
    )


class ExternalIdentityMapping(UUIDPKMixin, TenantScopedMixin, TimestampMixin, Base):
    """Deterministic 1-to-1 linkage between an external IdP subject and a KOTA User."""

    __tablename__ = "external_identity_mappings"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "provider_type",
            "subject",
            name="uq_ext_identity_org_provider_subject",
        ),
        Index("ix_ext_identity_org_user", "organization_id", "user_id"),
        Index("ix_ext_identity_email", "email"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    provider_type: Mapped[str] = mapped_column(
        String(64), nullable=False, default=SSOProviderType.ENTRA_ID
    )
    issuer: Mapped[str] = mapped_column(String(512), nullable=False)
    subject: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_authenticated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        server_default=func.now(),
    )

    user: Mapped["User"] = relationship("User")


class IncidentSeverity:
    P0 = "P0"  # Critical operational blocker / safety / compliance stop
    P1 = "P1"  # High priority / degraded service
    P2 = "P2"  # Medium / non-blocking functional anomaly
    P3 = "P3"  # Low / informational / minor tracking


class IncidentStatus:
    OPEN = "OPEN"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    RESOLVED = "RESOLVED"


class OperationalIncident(UUIDPKMixin, TenantScopedMixin, TimestampMixin, Base):
    """Production hypercare & operational reliability incident tracking."""

    __tablename__ = "operational_incidents"
    __table_args__ = (
        Index("ix_op_incident_org_status", "organization_id", "status"),
        Index("ix_op_incident_org_severity", "organization_id", "severity"),
        Index("ix_op_incident_service", "service_name"),
    )

    severity: Mapped[str] = mapped_column(String(16), nullable=False, default=IncidentSeverity.P2)
    service_name: Mapped[str] = mapped_column(
        String(64), nullable=False
    )  # AUTH_SSO | TELEMETRY | HUMS | INTELLIGENCE | OPERATIONS | INFRASTRUCTURE
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=IncidentStatus.OPEN
    )
    asset_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("assets.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    first_detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC), server_default=func.now()
    )
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    acknowledged_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    details: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        server_default=func.now(),
    )
