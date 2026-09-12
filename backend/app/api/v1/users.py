from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.deps import get_db_session, require_permission
from app.core.permissions import Permission
from app.schemas.auth import CurrentUser
from app.schemas.user import OrganizationUserResponse
from app.services import user_service

router = APIRouter(prefix="/users", tags=["users"])


@router.get("", response_model=list[OrganizationUserResponse])
def list_users(
    db: Session = Depends(get_db_session),
    # Gated on TECHNICIAN_READ (not a new permission) because the only
    # current consumer is the technician roster — every role that can see
    # technician qualifications can see who the organization's people are.
    current_user: CurrentUser = Depends(require_permission(Permission.TECHNICIAN_READ)),
) -> list[OrganizationUserResponse]:
    users = user_service.list_organization_users(db, organization_id=current_user.organization_id)
    return [OrganizationUserResponse.model_validate(u) for u in users]
