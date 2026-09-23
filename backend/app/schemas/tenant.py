import uuid
from datetime import datetime
from pydantic import BaseModel, ConfigDict, EmailStr, Field


class TenantProfileResponse(BaseModel):
    id: uuid.UUID
    name: str
    status: str
    industry: str | None = None
    created_at: datetime
    primary_contact_email: str | None = None
    primary_contact_name: str | None = None

    model_config = ConfigDict(from_attributes=True)


class TenantProfileUpdateRequest(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)
    industry: str | None = None


class TenantSettingsResponse(BaseModel):
    organization_id: uuid.UUID
    timezone: str = "UTC"
    operational_mode: str = "STANDARD"
    default_asset_type: str = "AIRCRAFT"
    notification_email: str | None = None


class TenantSettingsUpdateRequest(BaseModel):
    timezone: str | None = None
    operational_mode: str | None = None
    default_asset_type: str | None = None
    notification_email: EmailStr | None = None


class TenantUserResponse(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str
    is_active: bool
    roles: list[str] = Field(default_factory=list)
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TenantUserRoleUpdateRequest(BaseModel):
    roles: list[str] = Field(..., min_length=1)


class TenantUserStatusUpdateRequest(BaseModel):
    is_active: bool


class TenantRoleInfo(BaseModel):
    role_name: str
    display_name: str
    description: str
    permissions: list[str]
    is_system_role: bool = True


class TenantInvitationRequest(BaseModel):
    email: EmailStr
    full_name: str = Field(..., min_length=1, max_length=255)
    role: str = Field(..., min_length=1)


class TenantInvitationResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    email: str
    full_name: str
    role: str
    status: str  # PENDING, ACCEPTED, EXPIRED, CANCELLED
    created_at: datetime
    expires_at: datetime
    can_resend: bool
    can_cancel: bool


class TenantTeamMember(BaseModel):
    user_id: uuid.UUID
    full_name: str
    email: str
    role: str


class TenantTeamResponse(BaseModel):
    id: str
    name: str
    description: str
    lead_role: str
    member_count: int
    members: list[TenantTeamMember] = Field(default_factory=list)


class TenantUsageMetricItem(BaseModel):
    key: str
    label: str
    tracked: bool
    value: int | None = None
    limit: int | None = None
    is_unlimited: bool = False
    unit: str
    status: str  # TRACKED, NOT_TRACKED, AT_RISK, EXCEEDED


class TenantUsageResponse(BaseModel):
    organization_id: uuid.UUID
    metrics: list[TenantUsageMetricItem]


class TenantDashboardAttentionItem(BaseModel):
    severity: str  # INFO, WARNING, CRITICAL
    category: str
    title: str
    message: str
    link_href: str | None = None
    link_label: str | None = None


class TenantDashboardResponse(BaseModel):
    organization: TenantProfileResponse
    users_count: int
    active_users_count: int
    pending_invitations_count: int
    fleet_count: int
    aircraft_count: int
    drone_count: int
    facility_count: int
    team_count: int
    current_plan: str | None = None
    subscription_status: str | None = None
    effective_features_count: int
    attention_items: list[TenantDashboardAttentionItem] = Field(default_factory=list)
