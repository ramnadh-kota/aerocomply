import uuid

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError
from app.models.aircraft import Aircraft
from app.models.aircraft_detail import AircraftDetail
from app.models.asset import Asset, AssetType
from app.schemas.aircraft import AircraftCreateRequest, AircraftUpdateRequest
from app.services.audit_service import record_audit_event
from app.services.limit_enforcement_service import check_asset_creation_limit


def create_aircraft(
    db: Session,
    *,
    organization_id: uuid.UUID,
    payload: AircraftCreateRequest,
    actor_user_id: uuid.UUID | None = None,
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

    actor_user_id defaults to None (optional keyword) so the many existing
    test/service callers that predate the M4 audit-trail requirement keep
    working unchanged; the API layer always passes the authenticated user.
    """
    check_asset_creation_limit(db, organization_id=organization_id)

    asset = Asset(
        organization_id=organization_id,
        asset_type=AssetType.AIRCRAFT.value,
        registration=payload.registration,
        # manufacturer/model/serial_number are Asset-level fields (see
        # app/models/asset.py) with no equivalent on Aircraft/AircraftDetail
        # -- aircraft_type and msn are the closest analogues, so they're
        # mirrored here too. This keeps an Aircraft-typed Asset row exactly
        # as searchable/populated (GET /assets?search=...) as every other
        # asset type, instead of always showing null manufacturer/model.
        manufacturer=payload.manufacturer,
        model=payload.aircraft_type,
        serial_number=payload.msn,
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
        db.flush()
        # entity_type="Asset" (not "Aircraft"), matching every other asset
        # creation path (drone_service, asset_service) -- this Aircraft's
        # audit trail lives on its backing Asset row, the one identity every
        # asset type shares, not on a second per-type trail.
        record_audit_event(
            db,
            organization_id=organization_id,
            user_id=actor_user_id,
            action="aircraft.created",
            entity_type="Asset",
            entity_id=asset.id,
            metadata={
                "aircraft_id": str(aircraft.id),
                "registration": aircraft.registration,
                "msn": aircraft.msn,
                "aircraft_type": aircraft.aircraft_type,
            },
        )
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


def update_aircraft(
    db: Session,
    *,
    organization_id: uuid.UUID,
    aircraft_id: uuid.UUID,
    payload: AircraftUpdateRequest,
    actor_user_id: uuid.UUID | None = None,
) -> Aircraft:
    """Updates the mutable subset of an Aircraft's fields, keeping the
    backing Asset/AircraftDetail rows (when present) in sync so the three
    stay consistent regardless of which endpoint a reader later queries.
    Registration is deliberately not editable here -- same boundary as the
    generic Asset foundation's update_asset."""
    aircraft = get_aircraft(db, organization_id=organization_id, aircraft_id=aircraft_id)

    changed_fields: dict[str, object] = {}
    if payload.manufacturer is not None:
        changed_fields["manufacturer"] = payload.manufacturer
    if payload.msn is not None:
        aircraft.msn = payload.msn
        changed_fields["msn"] = payload.msn
    if payload.aircraft_type is not None:
        aircraft.aircraft_type = payload.aircraft_type
        changed_fields["aircraft_type"] = payload.aircraft_type
    if payload.status is not None:
        aircraft.status = payload.status
        changed_fields["status"] = payload.status

    if not changed_fields:
        return aircraft

    # AircraftDetail/Asset rows are nullable-linked (see Aircraft.asset_id's
    # docstring: pre-Phase-1A rows may have none). Every row created through
    # create_aircraft above always has one, but this guards the legacy case
    # rather than assuming it.
    if aircraft.asset_id is not None:
        asset = db.get(Asset, aircraft.asset_id)
        detail = db.get(AircraftDetail, aircraft.asset_id)
        if asset is not None:
            if payload.manufacturer is not None:
                asset.manufacturer = payload.manufacturer
            if payload.aircraft_type is not None:
                asset.model = payload.aircraft_type
            if payload.msn is not None:
                asset.serial_number = payload.msn
            if payload.status is not None:
                asset.status = payload.status
        if detail is not None:
            if payload.msn is not None:
                detail.msn = payload.msn
            if payload.aircraft_type is not None:
                detail.aircraft_type = payload.aircraft_type

    record_audit_event(
        db,
        organization_id=organization_id,
        user_id=actor_user_id,
        action="aircraft.updated",
        entity_type="Asset" if aircraft.asset_id is not None else "Aircraft",
        entity_id=aircraft.asset_id or aircraft.id,
        metadata=changed_fields,
    )
    db.commit()
    db.refresh(aircraft)
    return aircraft


# Aircraft has its own table (see Aircraft's docstring) separate from the
# generic Asset it dual-writes alongside -- soft-delete (Platform Control
# Plane) is implemented only on Asset (the pilot entity), not duplicated
# onto Aircraft. This outer join is what keeps the two consistent: an
# Aircraft whose backing Asset was soft-deleted must disappear from
# GET /aircraft and GET /aircraft/{id} exactly like it already disappears
# from GET /assets, without a second deleted_at column on `aircraft` itself.
# asset_id is nullable (legacy pre-Phase-1A rows), so a null asset_id always
# passes -- it has no Asset to have been soft-deleted.
_NOT_SOFT_DELETED = or_(Aircraft.asset_id.is_(None), Asset.deleted_at.is_(None))


def get_aircraft(db: Session, *, organization_id: uuid.UUID, aircraft_id: uuid.UUID) -> Aircraft:
    aircraft = db.execute(
        select(Aircraft)
        .outerjoin(Asset, Aircraft.asset_id == Asset.id)
        .where(
            Aircraft.id == aircraft_id,
            Aircraft.organization_id == organization_id,
            _NOT_SOFT_DELETED,
        )
    ).scalar_one_or_none()
    if aircraft is None:
        raise NotFoundError("Aircraft not found")
    return aircraft


def list_aircraft(db: Session, *, organization_id: uuid.UUID) -> list[Aircraft]:
    return list(
        db.execute(
            select(Aircraft)
            .outerjoin(Asset, Aircraft.asset_id == Asset.id)
            .where(Aircraft.organization_id == organization_id, _NOT_SOFT_DELETED)
        ).scalars().all()
    )
