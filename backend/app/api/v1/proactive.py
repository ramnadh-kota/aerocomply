from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.deps import get_db_session, require_permission
from app.core.permissions import Permission
from app.schemas.auth import CurrentUser
from app.schemas.proactive import DailyBrief, ProactiveAlert
from app.services import proactive_service

router = APIRouter(prefix="/lisa", tags=["proactive"])


@router.get("/proactive-alerts", response_model=list[ProactiveAlert])
def get_proactive_alerts(
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.AIRCRAFT_READ)),
) -> list[ProactiveAlert]:
    return proactive_service.get_proactive_alerts(
        db, organization_id=current_user.organization_id
    )


@router.get("/daily-brief", response_model=DailyBrief)
def get_daily_brief(
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.AIRCRAFT_READ)),
) -> DailyBrief:
    return proactive_service.get_daily_brief(db, organization_id=current_user.organization_id)
