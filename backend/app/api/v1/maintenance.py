import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.deps import get_db_session, require_permission
from app.core.permissions import Permission
from app.schemas.auth import CurrentUser
from app.schemas.maintenance_requirement import (
    MaintenanceAccomplishmentCreateRequest,
    MaintenanceAccomplishmentResponse,
    MaintenanceApplicabilityCreateRequest,
    MaintenanceDueItem,
    MaintenanceRequirementCreateRequest,
    MaintenanceRequirementResponse,
)
from app.services import maintenance_service

router = APIRouter(tags=["maintenance-program"])


@router.post(
    "/maintenance-requirements", response_model=MaintenanceRequirementResponse, status_code=201
)
def create_requirement(
    payload: MaintenanceRequirementCreateRequest,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.AIRCRAFT_WRITE)),
) -> MaintenanceRequirementResponse:
    requirement = maintenance_service.create_requirement(
        db,
        organization_id=current_user.organization_id,
        actor_user_id=current_user.id,
        payload=payload,
    )
    return MaintenanceRequirementResponse.model_validate(requirement)


@router.get("/maintenance-requirements", response_model=list[MaintenanceRequirementResponse])
def list_requirements(
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.AIRCRAFT_READ)),
) -> list[MaintenanceRequirementResponse]:
    requirements = maintenance_service.list_requirements(
        db, organization_id=current_user.organization_id
    )
    return [MaintenanceRequirementResponse.model_validate(r) for r in requirements]


@router.get(
    "/maintenance-requirements/{requirement_id}",
    response_model=MaintenanceRequirementResponse,
)
def get_requirement(
    requirement_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.AIRCRAFT_READ)),
) -> MaintenanceRequirementResponse:
    requirement = maintenance_service.get_requirement(
        db, organization_id=current_user.organization_id, requirement_id=requirement_id
    )
    return MaintenanceRequirementResponse.model_validate(requirement)


@router.post(
    "/maintenance-requirements/{requirement_id}/applicability",
    response_model=MaintenanceRequirementResponse,
    status_code=201,
)
def add_applicability(
    requirement_id: uuid.UUID,
    payload: MaintenanceApplicabilityCreateRequest,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.AIRCRAFT_WRITE)),
) -> MaintenanceRequirementResponse:
    requirement = maintenance_service.add_applicability(
        db,
        organization_id=current_user.organization_id,
        actor_user_id=current_user.id,
        requirement_id=requirement_id,
        payload=payload,
    )
    return MaintenanceRequirementResponse.model_validate(requirement)


@router.post(
    "/maintenance-requirements/{requirement_id}/accomplishments",
    response_model=MaintenanceAccomplishmentResponse,
    status_code=201,
)
def record_accomplishment(
    requirement_id: uuid.UUID,
    payload: MaintenanceAccomplishmentCreateRequest,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.AIRCRAFT_WRITE)),
) -> MaintenanceAccomplishmentResponse:
    accomplishment = maintenance_service.record_accomplishment(
        db,
        organization_id=current_user.organization_id,
        actor_user_id=current_user.id,
        requirement_id=requirement_id,
        payload=payload,
    )
    return MaintenanceAccomplishmentResponse.model_validate(accomplishment)


@router.get("/aircraft/{aircraft_id}/maintenance-due", response_model=list[MaintenanceDueItem])
def get_maintenance_due_for_aircraft(
    aircraft_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.AIRCRAFT_READ)),
) -> list[MaintenanceDueItem]:
    return maintenance_service.get_maintenance_due_for_aircraft(
        db, organization_id=current_user.organization_id, aircraft_id=aircraft_id
    )


@router.get("/fleet/maintenance-due", response_model=list[MaintenanceDueItem])
def get_fleet_maintenance_due(
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.AIRCRAFT_READ)),
) -> list[MaintenanceDueItem]:
    return maintenance_service.get_fleet_maintenance_due(
        db, organization_id=current_user.organization_id
    )
