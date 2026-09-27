import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.deps import get_db_session, require_any_permission
from app.core.permissions import Permission
from app.schemas.auth import CurrentUser
from app.schemas.control_center import (
    ControlCenterAircraftRow,
    ControlCenterFleetOperationRow,
    ControlCenterSummary,
    OperationalTimelineEvent,
)
from app.services import control_center_service

router = APIRouter(prefix="/control-center", tags=["control-center"])

_READ_PERMISSIONS = require_any_permission(
    Permission.AIRCRAFT_READ,
    Permission.DRONE_READ,
    Permission.COMPLIANCE_ASSESS,
)


@router.get("/fleet", response_model=list[ControlCenterAircraftRow])
def get_fleet_rows(
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(_READ_PERMISSIONS),
) -> list[ControlCenterAircraftRow]:
    return control_center_service.get_fleet_rows(
        db, organization_id=current_user.organization_id
    )


@router.get("/summary", response_model=ControlCenterSummary)
def get_summary(
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(_READ_PERMISSIONS),
) -> ControlCenterSummary:
    return control_center_service.get_summary(db, organization_id=current_user.organization_id)


@router.get("/fleet-operations", response_model=list[ControlCenterFleetOperationRow])
def get_fleet_operations(
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(_READ_PERMISSIONS),
) -> list[ControlCenterFleetOperationRow]:
    return control_center_service.get_fleet_operations(
        db, organization_id=current_user.organization_id
    )


@router.get("/timeline", response_model=list[OperationalTimelineEvent])
def get_fleet_timeline(
    asset_id: uuid.UUID | None = Query(default=None),
    event_type: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(_READ_PERMISSIONS),
) -> list[OperationalTimelineEvent]:
    return control_center_service.get_fleet_timeline(
        db,
        organization_id=current_user.organization_id,
        asset_id=asset_id,
        event_type=event_type,
        limit=limit,
        date_from=date_from,
        date_to=date_to,
    )
