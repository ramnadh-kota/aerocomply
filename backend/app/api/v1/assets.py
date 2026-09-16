"""Phase 1A: minimal, read-only Asset API.

Deliberately not a full Asset CRUD surface (Step 10 of the Phase 1A design
explicitly scopes this phase to the DB/domain foundation, not a complete
API). Reuses Permission.AIRCRAFT_READ rather than introducing a new
asset:read permission -- every Asset in this phase is AIRCRAFT-typed and
already gated by that permission on the /aircraft routes, so a second
permission would grant nothing new yet and would be RBAC surface added
ahead of an actual need. Revisit once a second AssetType is real.
"""

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.deps import get_db_session, require_permission
from app.core.permissions import Permission
from app.schemas.asset import AssetResponse
from app.schemas.auth import CurrentUser
from app.services import asset_service

router = APIRouter(prefix="/assets", tags=["assets"])


@router.get("", response_model=list[AssetResponse])
def list_assets(
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.AIRCRAFT_READ)),
) -> list[AssetResponse]:
    assets = asset_service.list_assets(db, organization_id=current_user.organization_id)
    return [AssetResponse.model_validate(a) for a in assets]


@router.get("/{asset_id}", response_model=AssetResponse)
def get_asset(
    asset_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.AIRCRAFT_READ)),
) -> AssetResponse:
    asset = asset_service.get_asset(
        db, organization_id=current_user.organization_id, asset_id=asset_id
    )
    return AssetResponse.model_validate(asset)
