"""Production Observability & Hypercare API endpoints (M13 Phase 5)."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, get_db_session
from app.schemas.auth import CurrentUser
from app.schemas.observability import (
    HypercareSummaryResponse,
    OperationalIncidentCreate,
    OperationalIncidentResponse,
    OperationalIncidentUpdate,
)
from app.services import hypercare_service

router = APIRouter(prefix="/hypercare", tags=["production-hypercare"])


@router.get("/summary", response_model=HypercareSummaryResponse)
def get_hypercare_summary(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db_session)],
) -> HypercareSummaryResponse:
    """Retrieve multi-subsystem production hypercare observability summary."""
    return hypercare_service.get_hypercare_summary(db, current_user.organization_id)


@router.get("/incidents", response_model=list[OperationalIncidentResponse])
def list_operational_incidents(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db_session)],
    status: str | None = Query(None, description="OPEN, ACKNOWLEDGED, RESOLVED"),
    severity: str | None = Query(None, description="P0, P1, P2, P3"),
    limit: int = Query(50, ge=1, le=200),
) -> list[OperationalIncidentResponse]:
    """List tenant operational incidents with status and severity filters."""
    incidents = hypercare_service.list_incidents(
        db, current_user.organization_id, status=status, severity=severity, limit=limit
    )
    return [OperationalIncidentResponse.model_validate(inc) for inc in incidents]


@router.post("/incidents", response_model=OperationalIncidentResponse)
def create_operational_incident(
    payload: OperationalIncidentCreate,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db_session)],
) -> OperationalIncidentResponse:
    """Create a new operational or infrastructure incident."""
    incident = hypercare_service.create_incident(
        db, current_user.organization_id, payload, user_id=current_user.id
    )
    return OperationalIncidentResponse.model_validate(incident)


@router.post("/incidents/{incident_id}/acknowledge", response_model=OperationalIncidentResponse)
def acknowledge_incident(
    incident_id: uuid.UUID,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db_session)],
) -> OperationalIncidentResponse:
    """Acknowledge an open operational incident."""
    incident = hypercare_service.acknowledge_incident(
        db, current_user.organization_id, incident_id, user_id=current_user.id
    )
    return OperationalIncidentResponse.model_validate(incident)


@router.post("/incidents/{incident_id}/resolve", response_model=OperationalIncidentResponse)
def resolve_incident(
    incident_id: uuid.UUID,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db_session)],
) -> OperationalIncidentResponse:
    """Resolve an operational incident."""
    incident = hypercare_service.resolve_incident(
        db, current_user.organization_id, incident_id, user_id=current_user.id
    )
    return OperationalIncidentResponse.model_validate(incident)
