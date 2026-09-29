"""B1: Data Source Acquisition Connector Management API.

Provides CRUD operations for managing persistent data acquisition connector configurations.
These define HOW data flows into Kota Aerospace (MAVLink, MQTT, DJI FlightHub, CSV batches, etc.)
without storing any credentials inline.

Security:
- All endpoints require active authentication (bearer token).
- Read operations require DRONE_READ.
- Write/delete operations require DRONE_WRITE.
- All operations are strictly scoped to the authenticated user's organization.
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, get_db_session, require_feature, require_permission
from app.core.permissions import Permission
from app.schemas.auth import CurrentUser
from app.schemas.data_source import (
    DataSourceAcquisitionStats,
    DataSourceCreate,
    DataSourceListResponse,
    DataSourceResponse,
    DataSourceUpdate,
)
from app.services import acquisition_service, data_source_service
from app.services.data_source_service import DataSourceError

router = APIRouter(
    prefix="/data-sources",
    tags=["data-sources"],
)


@router.post(
    "",
    response_model=DataSourceResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission(Permission.DRONE_WRITE))],
    summary="Register a new data acquisition connector",
)
def create_data_source(
    payload: DataSourceCreate,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(get_current_user),
) -> DataSourceResponse:
    """Registers a new data acquisition connector (MAVLink, MQTT, DJI, CSV/JSON batch, etc.)
    for the authenticated user's organization.

    Credentials must NOT be included in connection_config; use secret_reference to
    point to the platform secrets store.
    """
    try:
        source = data_source_service.create_data_source(
            db,
            organization_id=current_user.organization_id,
            payload=payload,
            created_by_user_id=current_user.id,
        )
        db.commit()
        return DataSourceResponse.model_validate(source)
    except DataSourceError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))


@router.get(
    "",
    response_model=DataSourceListResponse,
    dependencies=[Depends(require_permission(Permission.DRONE_READ))],
    summary="List data acquisition connectors",
)
def list_data_sources(
    connector_type: str | None = Query(None, description="Filter by connector type"),
    source_status: str | None = Query(None, alias="status", description="Filter by status"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(get_current_user),
) -> DataSourceListResponse:
    """Lists all registered data acquisition connectors for the organization."""
    total, sources = data_source_service.list_data_sources(
        db,
        organization_id=current_user.organization_id,
        connector_type=connector_type,
        status=source_status,
        limit=limit,
        offset=offset,
    )
    return DataSourceListResponse(
        total=total,
        items=[DataSourceResponse.model_validate(s) for s in sources],
    )


@router.get(
    "/{data_source_id}",
    response_model=DataSourceResponse,
    dependencies=[Depends(require_permission(Permission.DRONE_READ))],
    summary="Get a data acquisition connector",
)
def get_data_source(
    data_source_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(get_current_user),
) -> DataSourceResponse:
    """Retrieves a single data acquisition connector by ID."""
    from app.core.errors import NotFoundError

    try:
        source = data_source_service.get_data_source(
            db,
            organization_id=current_user.organization_id,
            data_source_id=data_source_id,
        )
        return DataSourceResponse.model_validate(source)
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.patch(
    "/{data_source_id}",
    response_model=DataSourceResponse,
    dependencies=[Depends(require_permission(Permission.DRONE_WRITE))],
    summary="Update a data acquisition connector",
)
def update_data_source(
    data_source_id: uuid.UUID,
    payload: DataSourceUpdate,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(get_current_user),
) -> DataSourceResponse:
    """Updates mutable fields of a data acquisition connector (name, config, status, etc.)."""
    from app.core.errors import NotFoundError

    try:
        source = data_source_service.update_data_source(
            db,
            organization_id=current_user.organization_id,
            data_source_id=data_source_id,
            payload=payload,
            updated_by_user_id=current_user.id,
        )
        db.commit()
        return DataSourceResponse.model_validate(source)
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except DataSourceError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))


@router.delete(
    "/{data_source_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_permission(Permission.DRONE_WRITE))],
    summary="Delete a data acquisition connector",
)
def delete_data_source(
    data_source_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(get_current_user),
) -> None:
    """Permanently deletes a data source configuration.

    Only DRAFT or DECOMMISSIONED sources may be deleted.
    ACTIVE/PAUSED sources must be decommissioned first.
    """
    from app.core.errors import NotFoundError

    try:
        data_source_service.delete_data_source(
            db,
            organization_id=current_user.organization_id,
            data_source_id=data_source_id,
            deleted_by_user_id=current_user.id,
        )
        db.commit()
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except DataSourceError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))


@router.get(
    "/stats/overview",
    dependencies=[Depends(require_permission(Permission.DRONE_READ))],
    summary="Get acquisition health overview",
)
def get_acquisition_stats_overview(
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    """Returns a health overview across all data sources for the organization."""
    _total, sources = data_source_service.list_data_sources(
        db,
        organization_id=current_user.organization_id,
        limit=500,
        offset=0,
    )
    stats = []
    for s in sources:
        health = data_source_service.compute_health(s)
        stats.append(
            DataSourceAcquisitionStats(
                id=s.id,
                name=s.name,
                connector_type=s.connector_type,
                status=s.status,
                last_acquisition_at=s.last_acquisition_at,
                total_events_ingested=s.total_events_ingested,
                total_events_rejected=s.total_events_rejected,
                consecutive_failures=s.consecutive_failures,
                health=health,
            )
        )

    by_health: dict[str, int] = {}
    by_type: dict[str, int] = {}
    for s_stat in stats:
        by_health[s_stat.health] = by_health.get(s_stat.health, 0) + 1
        by_type[s_stat.connector_type] = by_type.get(s_stat.connector_type, 0) + 1

    return {
        "total_sources": len(stats),
        "by_health": by_health,
        "by_connector_type": by_type,
        "sources": [s.model_dump() for s in stats],
    }


MAX_INGEST_BYTES = 25 * 1024 * 1024  # 25 MB per request; larger batches must be split


@router.post(
    "/{data_source_id}/ingest",
    dependencies=[
        Depends(require_permission(Permission.DRONE_WRITE)),
        Depends(require_feature("flight_telemetry")),
    ],
    summary="Push raw data (MAVLink bytes, MQTT payload, CSV/JSON file) into an ACTIVE data source",
)
async def ingest_into_data_source(
    data_source_id: uuid.UUID,
    request: Request,
    topic: str | None = Query(default=None, max_length=256, description="MQTT topic, when applicable"),
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    """The source's tenant comes from the authenticated user; a source id from another tenant is a 404.
    Returns accepted / duplicate / quarantined / rejected / failed counts, packet loss and warnings."""
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > MAX_INGEST_BYTES:
        raise HTTPException(status_code=413, detail="Payload too large")
    raw = await request.body()
    if len(raw) > MAX_INGEST_BYTES:
        raise HTTPException(status_code=413, detail="Payload too large")
    if not raw:
        raise HTTPException(status_code=422, detail="Empty payload")
    report = acquisition_service.ingest(
        db,
        organization_id=current_user.organization_id,
        data_source_id=data_source_id,
        raw=raw,
        topic=topic,
        actor_user_id=current_user.id,
    )
    db.commit()
    return report.to_dict()


@router.get(
    "/{data_source_id}/health",
    dependencies=[Depends(require_permission(Permission.DRONE_READ))],
    summary="Evidence-based acquisition health for one data source",
)
def get_data_source_health(
    data_source_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    return acquisition_service.get_health(
        db, organization_id=current_user.organization_id, data_source_id=data_source_id
    )
