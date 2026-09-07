import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
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
    db.commit()
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
