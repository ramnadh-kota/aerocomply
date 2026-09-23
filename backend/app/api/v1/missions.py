import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.deps import get_db_session, require_feature, require_permission
from app.core.permissions import Permission
from app.schemas.auth import CurrentUser
from app.schemas.mission import (
    MissionAuthorizeRequest,
    MissionCreateRequest,
    MissionListResponse,
    MissionResponse,
    MissionUpdateRequest,
)
from app.services import mission_service

router = APIRouter(
    prefix="/missions",
    tags=["missions"],
    dependencies=[Depends(require_feature("drone_fleet_management"))],
)


@router.get("", response_model=MissionListResponse)
def list_missions(
    asset_id: uuid.UUID | None = Query(default=None),
    status: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.DRONE_READ)),
) -> MissionListResponse:
    items, total = mission_service.list_missions(
        db,
        organization_id=current_user.organization_id,
        asset_id=asset_id,
        status=status,
        limit=limit,
        offset=offset,
    )
    return MissionListResponse(
        items=[MissionResponse.model_validate(m) for m in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("", response_model=MissionResponse, status_code=201)
def create_mission(
    payload: MissionCreateRequest,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.DRONE_WRITE)),
) -> MissionResponse:
    mission = mission_service.create_mission(
        db,
        organization_id=current_user.organization_id,
        actor_user_id=current_user.id,
        payload=payload,
    )
    return MissionResponse.model_validate(mission)


@router.get("/{mission_id}", response_model=MissionResponse)
def get_mission(
    mission_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.DRONE_READ)),
) -> MissionResponse:
    mission = mission_service.get_mission(
        db, organization_id=current_user.organization_id, mission_id=mission_id
    )
    return MissionResponse.model_validate(mission)


@router.patch("/{mission_id}", response_model=MissionResponse)
def update_mission(
    mission_id: uuid.UUID,
    payload: MissionUpdateRequest,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.DRONE_WRITE)),
) -> MissionResponse:
    mission = mission_service.update_mission(
        db,
        organization_id=current_user.organization_id,
        actor_user_id=current_user.id,
        mission_id=mission_id,
        payload=payload,
    )
    return MissionResponse.model_validate(mission)


@router.post("/{mission_id}/authorize", response_model=MissionResponse)
def authorize_mission(
    mission_id: uuid.UUID,
    payload: MissionAuthorizeRequest | None = None,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.DRONE_WRITE)),
) -> MissionResponse:
    """Internal operational mission authorization gate.
    Allows an authorized platform operator/manager to authorize a mission for flight execution.
    Does NOT claim legal/civil regulatory airspace clearance.
    """
    mission = mission_service.authorize_mission(
        db,
        organization_id=current_user.organization_id,
        actor_user_id=current_user.id,
        mission_id=mission_id,
        payload=payload,
    )
    return MissionResponse.model_validate(mission)
