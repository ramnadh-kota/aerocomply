from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.deps import get_db_session, require_permission
from app.core.permissions import Permission
from app.schemas.auth import CurrentUser
from app.schemas.control_center import ControlCenterAircraftRow, ControlCenterSummary
from app.services import control_center_service

router = APIRouter(prefix="/control-center", tags=["control-center"])


@router.get("/fleet", response_model=list[ControlCenterAircraftRow])
def get_fleet_rows(
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.AIRCRAFT_READ)),
) -> list[ControlCenterAircraftRow]:
    return control_center_service.get_fleet_rows(
        db, organization_id=current_user.organization_id
    )


@router.get("/summary", response_model=ControlCenterSummary)
def get_summary(
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.AIRCRAFT_READ)),
) -> ControlCenterSummary:
    return control_center_service.get_summary(db, organization_id=current_user.organization_id)
