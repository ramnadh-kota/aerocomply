import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.deps import get_db_session, require_permission
from app.core.permissions import Permission
from app.schemas.auth import CurrentUser
from app.schemas.release_readiness import ReleaseReadiness
from app.services import release_readiness_service

router = APIRouter(tags=["release-readiness"])


@router.get("/work-orders/{work_order_id}/release-readiness", response_model=ReleaseReadiness)
def get_release_readiness(
    work_order_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.AIRCRAFT_READ)),
) -> ReleaseReadiness:
    return release_readiness_service.get_release_readiness_for_work_order(
        db, organization_id=current_user.organization_id, work_order_id=work_order_id
    )
