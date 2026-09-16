"""Phase 1A: minimum read service for the generic Asset foundation.

Deliberately does not duplicate app/services/aircraft_service.py -- Aircraft
remains the system of record for aircraft business logic in this phase (see
docs/ARCHITECTURE_ASSET_FOUNDATION.md). These functions only expose the new
Asset/AircraftDetail rows that migration 0027 backfilled, read-only.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.models.aircraft import Aircraft
from app.models.asset import Asset


def get_asset(db: Session, *, organization_id: uuid.UUID, asset_id: uuid.UUID) -> Asset:
    asset = db.execute(
        select(Asset).where(Asset.id == asset_id, Asset.organization_id == organization_id)
    ).scalar_one_or_none()
    if asset is None:
        raise NotFoundError("Asset not found")
    return asset


def list_assets(db: Session, *, organization_id: uuid.UUID) -> list[Asset]:
    return list(
        db.execute(select(Asset).where(Asset.organization_id == organization_id)).scalars().all()
    )


def get_aircraft_asset(
    db: Session, *, organization_id: uuid.UUID, aircraft_id: uuid.UUID
) -> Asset:
    """Resolve the Asset backing a given Aircraft, via the DB-backed
    Aircraft.asset_id mapping column (not an application-level dictionary --
    see Step 7 of the Phase 1A design)."""
    aircraft = db.execute(
        select(Aircraft).where(
            Aircraft.id == aircraft_id, Aircraft.organization_id == organization_id
        )
    ).scalar_one_or_none()
    if aircraft is None or aircraft.asset_id is None:
        raise NotFoundError("Asset not found for this aircraft")
    return get_asset(db, organization_id=organization_id, asset_id=aircraft.asset_id)
