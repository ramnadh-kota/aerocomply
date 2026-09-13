import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class OrganizationCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)


class OrganizationAdminCreateRequest(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=8, max_length=255)


class PlatformOrganizationResponse(BaseModel):
    id: uuid.UUID
    name: str
    status: str
    created_at: datetime
    user_count: int
    aircraft_count: int

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
