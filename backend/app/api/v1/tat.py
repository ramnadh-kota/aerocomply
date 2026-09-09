import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.deps import get_db_session, require_permission
from app.core.permissions import Permission
from app.schemas.auth import CurrentUser
from app.schemas.tat import FleetTatSummary, TatStatus
from app.services import tat_service

router = APIRouter(tags=["tat"])


@router.get("/work-orders/{work_order_id}/tat", response_model=TatStatus)
def get_work_order_tat(
    work_order_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.AIRCRAFT_READ)),
) -> TatStatus:
    return tat_service.get_work_order_tat_status(
        db, organization_id=current_user.organization_id, work_order_id=work_order_id
    )


@router.get("/fleet/tat", response_model=FleetTatSummary)
def get_fleet_tat(
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.AIRCRAFT_READ)),
) -> FleetTatSummary:
    return tat_service.get_fleet_tat_status(db, organization_id=current_user.organization_id)
