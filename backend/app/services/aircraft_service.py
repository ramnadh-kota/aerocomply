import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError
from app.models.aircraft import Aircraft
from app.schemas.aircraft import AircraftCreateRequest


def create_aircraft(
    db: Session, *, organization_id: uuid.UUID, payload: AircraftCreateRequest
) -> Aircraft:
    aircraft = Aircraft(
        organization_id=organization_id,
        registration=payload.registration,
        msn=payload.msn,
        aircraft_type=payload.aircraft_type,
        status=payload.status,
    )
    db.add(aircraft)
    try:
        db.commit()
    except IntegrityError as exc:
        # Backstops the application-level duplicate checks (regular create
        # and the bulk import validator) against a genuine race — two
        # concurrent creates for the same registration can both pass an
        # in-memory uniqueness check before either commits.
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
