"""C5: geofence configuration API. Tenant comes from the JWT; zones are advisory operational data (never legal airspace
authorisation). Writes need DRONE_WRITE, reads DRONE_READ, and the organization must be entitled to flight telemetry."""
import uuid

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.deps import get_db_session, require_feature, require_permission
from app.core.permissions import Permission
from app.schemas.auth import CurrentUser
from app.schemas.geofence import GeofenceCreate, GeofenceResponse, GeofenceUpdate, GeofenceVersionResponse
from app.services import geofence_service as svc

router = APIRouter(prefix="/geofences", tags=["geofences"], dependencies=[Depends(require_feature("flight_telemetry"))])


class DeactivateRequest(BaseModel):
    reason: str | None = Field(None, max_length=500)


@router.get("", response_model=list[GeofenceResponse])
def list_geofences(
    include_inactive: bool = Query(False),
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.DRONE_READ)),
):
    return svc.list_geofences(db, organization_id=current_user.organization_id, include_inactive=include_inactive)


@router.post("", response_model=GeofenceResponse, status_code=status.HTTP_201_CREATED)
def create_geofence(
    payload: GeofenceCreate,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.DRONE_WRITE)),
):
    g = svc.create_geofence(db, organization_id=current_user.organization_id, user_id=current_user.id, payload=payload)
    db.commit()
    return g


@router.get("/{geofence_id}", response_model=GeofenceResponse)
def get_geofence(
    geofence_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.DRONE_READ)),
):
    return svc.get_geofence(db, organization_id=current_user.organization_id, geofence_id=geofence_id)


@router.patch("/{geofence_id}", response_model=GeofenceResponse)
def update_geofence(
    geofence_id: uuid.UUID,
    payload: GeofenceUpdate,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.DRONE_WRITE)),
):
    g = svc.update_geofence(
        db, organization_id=current_user.organization_id, user_id=current_user.id, geofence_id=geofence_id, payload=payload
    )
    db.commit()
    return g


@router.post("/{geofence_id}/deactivate", response_model=GeofenceResponse)
def deactivate_geofence(
    geofence_id: uuid.UUID,
    body: DeactivateRequest | None = None,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.DRONE_WRITE)),
):
    g = svc.deactivate_geofence(
        db, organization_id=current_user.organization_id, user_id=current_user.id, geofence_id=geofence_id,
        reason=body.reason if body else None,
    )
    db.commit()
    return g


@router.get("/{geofence_id}/history", response_model=list[GeofenceVersionResponse])
def geofence_history(
    geofence_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.DRONE_READ)),
):
    return svc.list_versions(db, organization_id=current_user.organization_id, geofence_id=geofence_id)
