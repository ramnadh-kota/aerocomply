from __future__ import annotations

import uuid
from sqlalchemy import Boolean, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, SoftDeleteMixin, TenantScopedMixin, TimestampMixin, UUIDPKMixin


class OrganizationStatus:
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"


class OnboardingStage:
    PROSPECT = "PROSPECT"
    CONTRACTED = "CONTRACTED"
    PROVISIONING = "PROVISIONING"
    CONFIGURATION = "CONFIGURATION"
    DATA_MIGRATION = "DATA_MIGRATION"
    INTEGRATION = "INTEGRATION"
    UAT = "UAT"
    GO_LIVE = "GO_LIVE"
    HYPERCARE = "HYPERCARE"
    ACTIVE = "ACTIVE"


class OrganizationIndustry:
    """Which aerospace vertical this tenant operates in."""

    DRONE_UAV = "DRONE_UAV"
    AIRCRAFT = "AIRCRAFT"
    HELICOPTER = "HELICOPTER"
    EVTOL_AAM = "EVTOL_AAM"


class Organization(UUIDPKMixin, TimestampMixin, SoftDeleteMixin, Base):
    """Core tenant organization entity."""

    __tablename__ = "organizations"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=OrganizationStatus.ACTIVE
    )
    industry: Mapped[str | None] = mapped_column(String(32), nullable=True)
    onboarding_stage: Mapped[str] = mapped_column(
        String(32), nullable=False, default=OnboardingStage.ACTIVE
    )
    logo_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    primary_color: Mapped[str | None] = mapped_column(String(32), nullable=True)


class TenantRetentionPolicy(UUIDPKMixin, TenantScopedMixin, TimestampMixin, Base):
    """Configurable data retention lifecycle policy per tenant and data category."""

    __tablename__ = "tenant_retention_policies"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "data_category",
            name="uq_retention_policies_org_category",
        ),
    )

    data_category: Mapped[str] = mapped_column(String(64), nullable=False)  # e.g. TELEMETRY, AUDIT_LOGS, FLIGHTS
    retention_days: Mapped[int] = mapped_column(Integer, nullable=False, default=2555)  # 7 years default
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
