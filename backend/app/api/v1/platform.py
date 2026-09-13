import uuid

from fastapi import APIRouter, Depends
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
    OrganizationAdminCreateRequest,
    OrganizationCreateRequest,
    PlatformOrganizationResponse,
)
from app.services import plan_service, platform_service
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
