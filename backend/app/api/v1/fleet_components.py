"""Organization-wide component register (/fleet/components): every serialized component installed on, or removed from,
any of the tenant's airframes. Engines are components of type ENGINE. Read-only; creation/installation stays on the
asset-scoped routes of each fleet family. Requires an entitlement to at least one airframe family."""
from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.deps import get_db_session, require_any_feature, require_permission
from app.core.errors import NotFoundError
from app.core.permissions import Permission
from app.models.asset import Asset
from app.models.component import Component
from app.schemas.auth import CurrentUser

router = APIRouter(
    prefix="/fleet/components",
    tags=["fleet-components"],
    dependencies=[Depends(require_any_feature(
        "aircraft_fleet_management", "drone_fleet_management", "helicopter_fleet_management", "evtol_fleet_management"))],
)


def _view(c: Component, asset: Asset | None) -> dict[str, Any]:
    return {
        "id": str(c.id), "asset_id": str(c.asset_id) if c.asset_id else None,
        "asset_registration": asset.registration if asset else None, "asset_type": asset.asset_type if asset else None,
        "component_type": c.component_type, "name": c.name, "serial_number": c.serial_number,
        "manufacturer": c.manufacturer, "model": c.model, "status": c.status,
        "created_at": c.created_at.isoformat() if c.created_at else None,
    }


@router.get("")
def list_components(
    component_type: str | None = Query(default=None, max_length=32),
    asset_id: uuid.UUID | None = None,
    status: str | None = Query(default=None, max_length=16),
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db_session),
    user: CurrentUser = Depends(require_permission(Permission.AIRCRAFT_READ)),
) -> dict[str, Any]:
    conds = [Component.organization_id == user.organization_id]
    if component_type:
        conds.append(Component.component_type == component_type.upper())
    if asset_id:
        conds.append(Component.asset_id == asset_id)
    if status:
        conds.append(Component.status == status.upper())
    total = db.scalar(select(func.count(Component.id)).where(*conds)) or 0
    rows = db.execute(select(Component, Asset).outerjoin(Asset, Asset.id == Component.asset_id).where(*conds)
                      .order_by(Component.component_type, Component.name).limit(limit).offset(offset)).all()
    return {"items": [_view(c, a) for c, a in rows], "total": total, "limit": limit, "offset": offset}


@router.get("/{component_id}")
def get_component(
    component_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    user: CurrentUser = Depends(require_permission(Permission.AIRCRAFT_READ)),
) -> dict[str, Any]:
    row = db.execute(select(Component, Asset).outerjoin(Asset, Asset.id == Component.asset_id).where(
        Component.id == component_id, Component.organization_id == user.organization_id)).first()
    if row is None:
        raise NotFoundError("Component not found")
    return _view(*row)
