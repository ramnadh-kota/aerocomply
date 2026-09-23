import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field


class OrganizationCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)


class OrganizationIndustrySetRequest(BaseModel):
    """M21.4. `industry=None` clears the classification back to unset --
    matches app.models.organization.OrganizationIndustry's fixed value set
    (DRONE_UAV/AIRCRAFT/HELICOPTER/EVTOL_AAM); not a strict Literal here so a
    future fifth value doesn't require a schema change in lockstep with the
    model, mirroring how AuditEventResponse.action stays a plain str."""

    industry: str | None = None


class ProvisionOrganizationRequest(BaseModel):
    """Phase 18.3: tenant provisioning. Only TRIALING/ACTIVE are accepted
    here -- PAST_DUE/CANCELED/SCHEDULED describe states a subscription
    reaches later (via app/services/subscription_service.py's own
    lifecycle transitions), never a starting point for a brand-new
    organization."""

    organization_name: str = Field(min_length=1, max_length=255)
    plan_id: uuid.UUID
    subscription_status: Literal["TRIALING", "ACTIVE"] = "TRIALING"
    admin_email: EmailStr
    admin_full_name: str = Field(min_length=1, max_length=255)


class ProvisionOrganizationResponse(BaseModel):
    organization_id: uuid.UUID
    organization_name: str
    organization_status: str
    plan_id: uuid.UUID
    subscription_id: uuid.UUID
    subscription_status: str
    admin_user_id: uuid.UUID
    admin_email: str
    admin_email_verified: bool
    onboarding_email_sent: bool


class OrganizationAdminCreateRequest(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=8, max_length=255)


class OrganizationAdminInviteRequest(BaseModel):
    """Invite an ORG_ADMIN into an EXISTING organization by email -- no
    password is ever supplied by the platform admin (see
    provisioning_service.invite_organization_admin's docstring). Distinct
    from OrganizationAdminCreateRequest above, which sets a caller-supplied
    password directly and is kept for backward compatibility with existing
    callers/tests; this is the real invitation-by-email path."""

    email: EmailStr
    full_name: str = Field(min_length=1, max_length=255)


class OrganizationAdminInviteResponse(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str
    onboarding_email_sent: bool


class PlatformOrganizationResponse(BaseModel):
    id: uuid.UUID
    name: str
    status: str
    industry: str | None = None
    created_at: datetime
    user_count: int
    aircraft_count: int
    drone_count: int = 0

    class Config:
        from_attributes = True


class PlatformUserResponse(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    organization_name: str | None = None
    email: str
    full_name: str
    is_active: bool
    roles: list[str] = Field(default_factory=list)
    created_at: datetime

    class Config:
        from_attributes = True


class AuditEventResponse(BaseModel):
    """M12.0: safe, explicit projection of AuditEvent for platform-level
    audit reads. Deliberately excludes no columns beyond ORM internals --
    every column on the model is already safe for a PLATFORM_MANAGE-gated
    reader -- but is still hand-declared (never `from_attributes` on the
    ORM class blindly re-exported) so a future column added to the model
    doesn't leak here without a deliberate schema change.
    """

    id: uuid.UUID
    organization_id: uuid.UUID
    created_at: datetime
    user_id: uuid.UUID | None
    action: str
    entity_type: str
    entity_id: uuid.UUID | None
    event_metadata: dict

    class Config:
        from_attributes = True


class AuditEventListResponse(BaseModel):
    items: list[AuditEventResponse]
    total: int
    limit: int
    offset: int


class ComponentHealthResponse(BaseModel):
    """One row of app.services.platform_health_service.ComponentHealth.
    status is a plain string (HEALTHY/UNAVAILABLE/NOT_APPLICABLE/UNKNOWN)
    rather than a strict enum on the wire, so a future status value doesn't
    break API consumers.
    """

    name: str
    status: str
    detail: str
    latency_ms: float | None = None


class PlatformHealthResponse(BaseModel):
    """M13: on-demand platform health snapshot. Never persisted -- every
    call recomputes this from the live database check, same semantics as
    GET /health/ready (app/api/v1/health.py), plus a deterministic
    aggregation documented in platform_health_service.get_platform_health.
    """

    overall_status: str
    checked_at: datetime
    components: list[ComponentHealthResponse]


class PlanDistributionItem(BaseModel):
    plan_code: str
    plan_name: str
    count: int


class PlatformDashboardStatsResponse(BaseModel):
    total_organizations: int
    active_organizations: int
    suspended_organizations: int
    pending_provisioning: int
    active_subscriptions: int
    trial_subscriptions: int
    total_users: int
    total_aircraft: int
    total_drones: int
    organizations_by_plan: list[PlanDistributionItem] = Field(default_factory=list)
    recent_activity: list[AuditEventResponse] = Field(default_factory=list)
