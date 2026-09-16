import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError
from app.models.aircraft import Aircraft
from app.models.aircraft_detail import AircraftDetail
from app.models.asset import Asset, AssetType
from app.schemas.aircraft import AircraftCreateRequest


def create_aircraft(
    db: Session, *, organization_id: uuid.UUID, payload: AircraftCreateRequest
) -> Aircraft:
    """Creates an Aircraft together with its Phase 1A Asset/AircraftDetail
    counterpart, in one transaction (see docs/ARCHITECTURE_ASSET_FOUNDATION.md,
    "Closed gap: new Aircraft rows now dual-write"). asset_id is never
    client-supplied: the Asset is always created here, server-side, in the
    same organization_id the caller was already authenticated into -- there
    is no path for a caller to name or influence which Asset gets linked.

    All three inserts (Asset, AircraftDetail, Aircraft) share this single
    Session/transaction, matching how create_aircraft already committed one
    transaction before this change -- no second transaction mechanism is
    introduced. A failure at any point (including the pre-existing duplicate
    registration race, now checked against both `aircraft` and `assets`)
    rolls back all three inserts together; nothing is left partially created.
    """
    asset = Asset(
        organization_id=organization_id,
        asset_type=AssetType.AIRCRAFT.value,
        registration=payload.registration,
        status=payload.status,
    )
    aircraft = Aircraft(
        organization_id=organization_id,
        registration=payload.registration,
        msn=payload.msn,
        aircraft_type=payload.aircraft_type,
        status=payload.status,
    )
    try:
        db.add(asset)
        # Flush (not commit) to populate asset.id for AircraftDetail/Aircraft
        # -- still inside this try block and still uncommitted, so an
        # IntegrityError raised here (e.g. a duplicate-registration race
        # caught by uq_assets_organization_id_registration before
        # uq_aircraft_organization_id_registration even gets a chance to)
        # is caught by the same except below as a commit-time failure would
        # be, and rolls back the same way.
        db.flush()
        db.add(
            AircraftDetail(asset_id=asset.id, msn=payload.msn, aircraft_type=payload.aircraft_type)
        )
        aircraft.asset_id = asset.id
        db.add(aircraft)
        db.commit()
    except IntegrityError as exc:
        # Backstops the application-level duplicate checks (regular create
        # and the bulk import validator) against a genuine race — two
        # concurrent creates for the same registration can both pass an
        # in-memory uniqueness check before either commits. Rolling back
        # here discards the Asset and AircraftDetail inserts too, since all
        # three share this one transaction -- never a partially-created
        # Aircraft/Asset pair.
        db.rollback()
        raise ConflictError(
            f"Aircraft registration {payload.registration!r} already exists in this organization",
            code="duplicate_registration",
        ) from exc
    db.refresh(aircraft)
    return aircraft


def get_aircraft(db: Session, *, organization_id: uuid.UUID, aircraft_id: uuid.UUID) -> Aircraft:
    aircraft = db.execute(
        select(Aircraft).where(
            Aircraft.id == aircraft_id, Aircraft.organization_id == organization_id
        )
    ).scalar_one_or_none()
    if aircraft is None:
        raise NotFoundError("Aircraft not found")
    return aircraft


def list_aircraft(db: Session, *, organization_id: uuid.UUID) -> list[Aircraft]:
    return list(
        db.execute(
            select(Aircraft).where(Aircraft.organization_id == organization_id)
        ).scalars().all()
    )
