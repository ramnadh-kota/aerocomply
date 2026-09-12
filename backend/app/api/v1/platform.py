import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.deps import get_db_session, require_permission
from app.core.permissions import Permission
from app.models.organization import OrganizationStatus
from app.schemas.auth import CurrentUser
from app.schemas.platform import (
    OrganizationAdminCreateRequest,
    OrganizationCreateRequest,
    PlatformOrganizationResponse,
)
from app.services import platform_service

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
