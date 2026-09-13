import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.deps import get_db_session, require_permission
from app.core.permissions import Permission
from app.models.organization import OrganizationStatus
from app.models.plan import Plan
from app.schemas.auth import CurrentUser
from app.schemas.entitlement import EntitlementResolutionResponse
from app.schemas.plan import (
    PlanCreateRequest,
    PlanFeatureCreateRequest,
    PlanFeatureResponse,
    PlanFeatureUpdateRequest,
    PlanResponse,
    PlanUpdateRequest,
)
from app.schemas.platform import (
    AuditEventListResponse,
    AuditEventResponse,
    ComponentHealthResponse,
    OrganizationAdminCreateRequest,
    OrganizationCreateRequest,
    PlatformHealthResponse,
    PlatformOrganizationResponse,
)
from app.schemas.subscription import (
    SubscriptionCreateRequest,
    SubscriptionResponse,
    SubscriptionScheduleRequest,
    SubscriptionUpdateRequest,
)
from app.schemas.tenant_entitlement import (
    TenantFeatureOverrideCreateRequest,
    TenantFeatureOverrideResponse,
    TenantFeatureOverrideUpdateRequest,
    TenantUsageLimitCreateRequest,
    TenantUsageLimitResponse,
    TenantUsageLimitUpdateRequest,
)
from app.services import (
    audit_service,
    plan_service,
    platform_health_service,
    platform_service,
    subscription_service,
)
from app.services import tenant_entitlement_admin_service as tea_service
from app.services.entitlement_service import resolve_entitlements

router = APIRouter(prefix="/platform", tags=["platform"])


def _to_response(row: dict) -> PlatformOrganizationResponse:
    org = row["organization"]
    return PlatformOrganizationResponse(
        id=org.id,
        name=org.name,
        status=org.status,
        created_at=org.created_at,
        user_count=row["user_count"],
        aircraft_count=row["aircraft_count"],
    )


@router.get("/organizations", response_model=list[PlatformOrganizationResponse])
def list_organizations(
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.PLATFORM_MANAGE)),
) -> list[PlatformOrganizationResponse]:
    rows = platform_service.list_organizations(db)
    return [_to_response(r) for r in rows]


@router.post("/organizations", response_model=PlatformOrganizationResponse, status_code=201)
def create_organization(
    payload: OrganizationCreateRequest,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.PLATFORM_MANAGE)),
) -> PlatformOrganizationResponse:
    org = platform_service.create_organization(db, actor_user_id=current_user.id, name=payload.name)
    return _to_response({"organization": org, "user_count": 0, "aircraft_count": 0})


@router.get("/organizations/{organization_id}", response_model=PlatformOrganizationResponse)
def get_organization(
    organization_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.PLATFORM_MANAGE)),
) -> PlatformOrganizationResponse:
    row = platform_service.get_organization_with_counts(db, organization_id=organization_id)
    return _to_response(row)


@router.post(
    "/organizations/{organization_id}/activate", response_model=PlatformOrganizationResponse
)
def activate_organization(
    organization_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.PLATFORM_MANAGE)),
) -> PlatformOrganizationResponse:
    platform_service.set_organization_status(
        db,
        actor_user_id=current_user.id,
        organization_id=organization_id,
        status=OrganizationStatus.ACTIVE,
    )
    row = platform_service.get_organization_with_counts(db, organization_id=organization_id)
    return _to_response(row)


@router.post(
    "/organizations/{organization_id}/suspend", response_model=PlatformOrganizationResponse
)
def suspend_organization(
    organization_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.PLATFORM_MANAGE)),
) -> PlatformOrganizationResponse:
    platform_service.set_organization_status(
        db,
        actor_user_id=current_user.id,
        organization_id=organization_id,
        status=OrganizationStatus.SUSPENDED,
    )
    row = platform_service.get_organization_with_counts(db, organization_id=organization_id)
    return _to_response(row)


@router.post("/organizations/{organization_id}/admins", status_code=201)
def create_organization_admin(
    organization_id: uuid.UUID,
    payload: OrganizationAdminCreateRequest,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.PLATFORM_MANAGE)),
) -> dict:
    user = platform_service.create_organization_admin(
        db,
        actor_user_id=current_user.id,
        organization_id=organization_id,
        email=payload.email,
        full_name=payload.full_name,
        password=payload.password,
    )
    return {"id": str(user.id), "email": user.email, "full_name": user.full_name}


@router.get(
    "/organizations/{organization_id}/entitlements",
    response_model=EntitlementResolutionResponse,
)
def get_organization_entitlements(
    organization_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.PLATFORM_MANAGE)),
) -> EntitlementResolutionResponse:
    platform_service.get_organization(db, organization_id=organization_id)  # 404 if missing
    result = resolve_entitlements(db, organization_id=organization_id)
    plan_name: str | None = None
    if result.plan_id is not None:
        plan = db.get(Plan, result.plan_id)
        plan_name = plan.name if plan is not None else None
    return EntitlementResolutionResponse.from_resolution(result, plan_name=plan_name)


# ---------------------------------------------------------------------------
# M5: plan / plan-feature administration (global platform catalog data --
# see app/services/plan_service.py's module docstring for the transaction,
# authorization, and audit-attribution pattern these routes follow).
# ---------------------------------------------------------------------------


@router.get("/plans", response_model=list[PlanResponse])
def list_plans(
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.PLATFORM_MANAGE)),
) -> list[PlanResponse]:
    plans = plan_service.list_plans(db)
    return [PlanResponse.model_validate(p) for p in plans]


@router.post("/plans", response_model=PlanResponse, status_code=201)
def create_plan(
    payload: PlanCreateRequest,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.PLATFORM_MANAGE)),
) -> PlanResponse:
    plan = plan_service.create_plan(
        db,
        actor_user_id=current_user.id,
        actor_organization_id=current_user.organization_id,
        name=payload.name,
        code=payload.code,
        description=payload.description,
        is_active=payload.is_active,
    )
    return PlanResponse.model_validate(plan)


@router.get("/plans/{plan_id}", response_model=PlanResponse)
def get_plan(
    plan_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.PLATFORM_MANAGE)),
) -> PlanResponse:
    plan = plan_service.get_plan(db, plan_id=plan_id)
    return PlanResponse.model_validate(plan)


@router.patch("/plans/{plan_id}", response_model=PlanResponse)
def update_plan(
    plan_id: uuid.UUID,
    payload: PlanUpdateRequest,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.PLATFORM_MANAGE)),
) -> PlanResponse:
    plan = plan_service.update_plan(
        db,
        actor_user_id=current_user.id,
        actor_organization_id=current_user.organization_id,
        plan_id=plan_id,
        name=payload.name,
        code=payload.code,
        description=payload.description,
    )
    return PlanResponse.model_validate(plan)


@router.post("/plans/{plan_id}/activate", response_model=PlanResponse)
def activate_plan(
    plan_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.PLATFORM_MANAGE)),
) -> PlanResponse:
    plan = plan_service.set_plan_active(
        db,
        actor_user_id=current_user.id,
        actor_organization_id=current_user.organization_id,
        plan_id=plan_id,
        is_active=True,
    )
    return PlanResponse.model_validate(plan)


@router.post("/plans/{plan_id}/deactivate", response_model=PlanResponse)
def deactivate_plan(
    plan_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.PLATFORM_MANAGE)),
) -> PlanResponse:
    plan = plan_service.set_plan_active(
        db,
        actor_user_id=current_user.id,
        actor_organization_id=current_user.organization_id,
        plan_id=plan_id,
        is_active=False,
    )
    return PlanResponse.model_validate(plan)


@router.get("/plans/{plan_id}/features", response_model=list[PlanFeatureResponse])
def list_plan_features(
    plan_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.PLATFORM_MANAGE)),
) -> list[PlanFeatureResponse]:
    features = plan_service.list_plan_features(db, plan_id=plan_id)
    return [PlanFeatureResponse.model_validate(f) for f in features]


@router.post("/plans/{plan_id}/features", response_model=PlanFeatureResponse, status_code=201)
def create_plan_feature(
    plan_id: uuid.UUID,
    payload: PlanFeatureCreateRequest,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.PLATFORM_MANAGE)),
) -> PlanFeatureResponse:
    feature = plan_service.create_plan_feature(
        db,
        actor_user_id=current_user.id,
        actor_organization_id=current_user.organization_id,
        plan_id=plan_id,
        feature_key=payload.feature_key,
        enabled=payload.enabled,
    )
    return PlanFeatureResponse.model_validate(feature)


@router.patch("/plans/{plan_id}/features/{feature_key}", response_model=PlanFeatureResponse)
def update_plan_feature(
    plan_id: uuid.UUID,
    feature_key: str,
    payload: PlanFeatureUpdateRequest,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.PLATFORM_MANAGE)),
) -> PlanFeatureResponse:
    feature = plan_service.set_plan_feature_enabled(
        db,
        actor_user_id=current_user.id,
        actor_organization_id=current_user.organization_id,
        plan_id=plan_id,
        feature_key=feature_key,
        enabled=payload.enabled,
    )
    return PlanFeatureResponse.model_validate(feature)


# ---------------------------------------------------------------------------
# M6: subscription administration. Baseline gate is PLATFORM_MANAGE; unlike
# Plan/PlanFeature, Subscription rows carry a real organization_id already
# (TenantScopedMixin), so audit attribution targets that organization -- see
# app/services/subscription_service.py's module docstring.
# ---------------------------------------------------------------------------


@router.get(
    "/organizations/{organization_id}/subscriptions", response_model=list[SubscriptionResponse]
)
def list_org_subscriptions(
    organization_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.PLATFORM_MANAGE)),
) -> list[SubscriptionResponse]:
    subs = subscription_service.list_subscriptions_for_org(db, organization_id=organization_id)
    return [SubscriptionResponse.model_validate(s) for s in subs]


@router.post(
    "/organizations/{organization_id}/subscriptions",
    response_model=SubscriptionResponse,
    status_code=201,
)
def create_org_subscription(
    organization_id: uuid.UUID,
    payload: SubscriptionCreateRequest,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.PLATFORM_MANAGE)),
) -> SubscriptionResponse:
    sub = subscription_service.create_subscription(
        db,
        actor_user_id=current_user.id,
        organization_id=organization_id,
        plan_id=payload.plan_id,
        status=payload.status,
        starts_at=payload.starts_at,
        ends_at=payload.ends_at,
    )
    return SubscriptionResponse.model_validate(sub)


@router.post(
    "/organizations/{organization_id}/subscriptions/schedule",
    response_model=SubscriptionResponse,
    status_code=201,
)
def schedule_org_subscription(
    organization_id: uuid.UUID,
    payload: SubscriptionScheduleRequest,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.PLATFORM_MANAGE)),
) -> SubscriptionResponse:
    sub = subscription_service.schedule_subscription(
        db,
        actor_user_id=current_user.id,
        organization_id=organization_id,
        plan_id=payload.plan_id,
        starts_at=payload.starts_at,
        ends_at=payload.ends_at,
    )
    return SubscriptionResponse.model_validate(sub)


@router.get("/subscriptions/{subscription_id}", response_model=SubscriptionResponse)
def get_subscription(
    subscription_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.PLATFORM_MANAGE)),
) -> SubscriptionResponse:
    sub = subscription_service.get_subscription(db, subscription_id=subscription_id)
    return SubscriptionResponse.model_validate(sub)


@router.patch("/subscriptions/{subscription_id}", response_model=SubscriptionResponse)
def update_subscription(
    subscription_id: uuid.UUID,
    payload: SubscriptionUpdateRequest,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.PLATFORM_MANAGE)),
) -> SubscriptionResponse:
    sub = subscription_service.update_subscription(
        db,
        actor_user_id=current_user.id,
        subscription_id=subscription_id,
        status=payload.status,
        plan_id=payload.plan_id,
        starts_at=payload.starts_at,
        ends_at=payload.ends_at,
    )
    return SubscriptionResponse.model_validate(sub)


@router.post("/subscriptions/{subscription_id}/cancel", response_model=SubscriptionResponse)
def cancel_subscription(
    subscription_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.PLATFORM_MANAGE)),
) -> SubscriptionResponse:
    sub = subscription_service.cancel_subscription(
        db, actor_user_id=current_user.id, subscription_id=subscription_id
    )
    return SubscriptionResponse.model_validate(sub)


# ---------------------------------------------------------------------------
# M6: tenant feature-override administration. PLATFORM_MANAGE is the
# baseline; an EXPANSIVE mutation (see
# tenant_entitlement_admin_service.classify_feature_override) additionally
# requires PLATFORM_ENTITLEMENT_OVERRIDE, checked at the service layer
# against the caller's full permission set (not a second stacked Depends),
# because whether a mutation is expansive can only be known after comparing
# against the org's current resolved baseline.
# ---------------------------------------------------------------------------


@router.get(
    "/organizations/{organization_id}/feature-overrides",
    response_model=list[TenantFeatureOverrideResponse],
)
def list_feature_overrides(
    organization_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.PLATFORM_MANAGE)),
) -> list[TenantFeatureOverrideResponse]:
    overrides = tea_service.list_feature_overrides(db, organization_id=organization_id)
    return [TenantFeatureOverrideResponse.model_validate(o) for o in overrides]


@router.post(
    "/organizations/{organization_id}/feature-overrides",
    response_model=TenantFeatureOverrideResponse,
    status_code=201,
)
def create_feature_override(
    organization_id: uuid.UUID,
    payload: TenantFeatureOverrideCreateRequest,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.PLATFORM_MANAGE)),
) -> TenantFeatureOverrideResponse:
    override = tea_service.create_feature_override(
        db,
        actor_user_id=current_user.id,
        caller_roles=current_user.roles,
        organization_id=organization_id,
        feature_key=payload.feature_key,
        enabled=payload.enabled,
        reason=payload.reason,
        expires_at=payload.expires_at,
    )
    return TenantFeatureOverrideResponse.model_validate(override)


@router.patch(
    "/organizations/{organization_id}/feature-overrides/{feature_key}",
    response_model=TenantFeatureOverrideResponse,
)
def update_feature_override(
    organization_id: uuid.UUID,
    feature_key: str,
    payload: TenantFeatureOverrideUpdateRequest,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.PLATFORM_MANAGE)),
) -> TenantFeatureOverrideResponse:
    override = tea_service.update_feature_override(
        db,
        actor_user_id=current_user.id,
        caller_roles=current_user.roles,
        organization_id=organization_id,
        feature_key=feature_key,
        enabled=payload.enabled,
        reason=payload.reason,
        expires_at=payload.expires_at,
    )
    return TenantFeatureOverrideResponse.model_validate(override)


@router.delete(
    "/organizations/{organization_id}/feature-overrides/{feature_key}", status_code=204
)
def remove_feature_override(
    organization_id: uuid.UUID,
    feature_key: str,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.PLATFORM_MANAGE)),
) -> None:
    tea_service.remove_feature_override(
        db,
        actor_user_id=current_user.id,
        organization_id=organization_id,
        feature_key=feature_key,
    )


# ---------------------------------------------------------------------------
# M6: tenant usage-limit administration (configuration only -- no metering).
# Same PLATFORM_MANAGE / PLATFORM_ENTITLEMENT_OVERRIDE boundary as overrides.
# ---------------------------------------------------------------------------


@router.get(
    "/organizations/{organization_id}/usage-limits",
    response_model=list[TenantUsageLimitResponse],
)
def list_usage_limits(
    organization_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.PLATFORM_MANAGE)),
) -> list[TenantUsageLimitResponse]:
    limits = tea_service.list_usage_limits(db, organization_id=organization_id)
    return [TenantUsageLimitResponse.model_validate(limit) for limit in limits]


@router.post(
    "/organizations/{organization_id}/usage-limits",
    response_model=TenantUsageLimitResponse,
    status_code=201,
)
def create_usage_limit(
    organization_id: uuid.UUID,
    payload: TenantUsageLimitCreateRequest,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.PLATFORM_MANAGE)),
) -> TenantUsageLimitResponse:
    limit = tea_service.create_usage_limit(
        db,
        actor_user_id=current_user.id,
        caller_roles=current_user.roles,
        organization_id=organization_id,
        feature_key=payload.feature_key,
        limit_key=payload.limit_key,
        limit_value=payload.limit_value,
        is_unlimited=payload.is_unlimited,
    )
    return TenantUsageLimitResponse.model_validate(limit)


@router.patch(
    "/organizations/{organization_id}/usage-limits/{feature_key}/{limit_key}",
    response_model=TenantUsageLimitResponse,
)
def update_usage_limit(
    organization_id: uuid.UUID,
    feature_key: str,
    limit_key: str,
    payload: TenantUsageLimitUpdateRequest,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.PLATFORM_MANAGE)),
) -> TenantUsageLimitResponse:
    limit = tea_service.update_usage_limit(
        db,
        actor_user_id=current_user.id,
        caller_roles=current_user.roles,
        organization_id=organization_id,
        feature_key=feature_key,
        limit_key=limit_key,
        limit_value=payload.limit_value,
        is_unlimited=payload.is_unlimited,
    )
    return TenantUsageLimitResponse.model_validate(limit)


@router.delete(
    "/organizations/{organization_id}/usage-limits/{feature_key}/{limit_key}", status_code=204
)
def remove_usage_limit(
    organization_id: uuid.UUID,
    feature_key: str,
    limit_key: str,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.PLATFORM_MANAGE)),
) -> None:
    tea_service.remove_usage_limit(
        db,
        actor_user_id=current_user.id,
        organization_id=organization_id,
        feature_key=feature_key,
        limit_key=limit_key,
    )


# ---------------------------------------------------------------------------
# M12.0: platform-wide audit read. PLATFORM_MANAGE is the only gate -- same
# precedent as GET /organizations/{organization_id}/entitlements above --
# because a platform admin's whole purpose is cross-tenant visibility. When
# organization_id is supplied it is just a WHERE clause on an already
# platform-authorized request, not a second per-org authorization check.
# Read-only: never writes an audit_events row of its own.
# ---------------------------------------------------------------------------


@router.get("/audit", response_model=AuditEventListResponse)
def list_audit_events(
    organization_id: uuid.UUID | None = None,
    action: str | None = None,
    entity_type: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    limit: int = Query(default=audit_service.AUDIT_LIST_DEFAULT_LIMIT, ge=1),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.PLATFORM_MANAGE)),
) -> AuditEventListResponse:
    events, total = audit_service.list_audit_events(
        db,
        organization_id=organization_id,
        action=action,
        entity_type=entity_type,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
        offset=offset,
    )
    effective_limit = max(1, min(limit, audit_service.AUDIT_LIST_MAX_LIMIT))
    return AuditEventListResponse(
        items=[AuditEventResponse.model_validate(e) for e in events],
        total=total,
        limit=effective_limit,
        offset=max(0, offset),
    )


# ---------------------------------------------------------------------------
# M13: on-demand platform health snapshot. PLATFORM_MANAGE-gated, same
# precedent as every other route in this file. Read-only: never writes
# anything, never persists a health record -- every call recomputes the
# snapshot live from app/services/platform_health_service.get_platform_health,
# which itself reuses the readiness probe's exact DB check
# (app/api/v1/health.py) rather than a second, possibly-inconsistent one.
# ---------------------------------------------------------------------------


@router.get("/health", response_model=PlatformHealthResponse)
def get_platform_health(
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.PLATFORM_MANAGE)),
) -> PlatformHealthResponse:
    snapshot = platform_health_service.get_platform_health(db)
    return PlatformHealthResponse(
        overall_status=snapshot.overall_status.value,
        checked_at=snapshot.checked_at,
        components=[
            ComponentHealthResponse(
                name=c.name,
                status=c.status.value,
                detail=c.detail,
                latency_ms=c.latency_ms,
            )
            for c in snapshot.components
        ],
    )
