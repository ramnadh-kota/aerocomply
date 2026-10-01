"""M13: Telemetry Ingestion API & DJI FlightHub 2 Webhook Router."""

from __future__ import annotations

import hashlib
import json
import uuid
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from datetime import datetime

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.deps import get_current_user, get_db_session, require_feature, require_permission
from app.core.permissions import Permission
from app.models.telemetry import ExternalAssetMapping, TelemetryEventLog
from app.schemas.auth import CurrentUser
from app.schemas.telemetry import (
    DJIFlightHubWebhookPayload,
    ExternalAssetMappingCreate,
    ExternalAssetMappingResponse,
    NormalizedTelemetryEvent,
    TelemetryEventResult,
    TelemetryFreshnessPolicyCreate,
    TelemetryFreshnessPolicyResponse,
    TelemetryIngestRequest,
    TelemetryIngestResponse,
)
from app.services import telemetry_service

# JWT routes: gated by the flight_telemetry commercial feature (in addition to RBAC).
router = APIRouter(
    prefix="/telemetry",
    tags=["telemetry"],
    dependencies=[Depends(require_feature("flight_telemetry"))],
)
# The DJI webhook is machine-to-machine (HMAC, no bearer token), so it cannot use
# the dependency above; it performs the same entitlement check against the tenant
# it routes into (see dji_flighthub_webhook).
webhook_router = APIRouter(prefix="/telemetry", tags=["telemetry"])


# FlightHub flight records are small JSON documents; anything near this size is not one.
DJI_WEBHOOK_MAX_BODY_BYTES = 1024 * 1024


@webhook_router.post("/dji/webhook", status_code=status.HTTP_200_OK)
async def dji_flighthub_webhook(
    request: Request,
    db: Session = Depends(get_db_session),
    x_organization_id: str | None = Header(None, alias="X-Organization-ID"),
    x_dji_signature: str | None = Header(None, alias="X-DJI-Signature"),
) -> dict[str, Any]:
    """DJI FlightHub 2 webhook endpoint.

    Verifies HMAC signature when configured, normalizes the event, and routes through
    authoritative domain services without creating duplicate flights or bypassing RBAC.
    """
    # Bounded read BEFORE authentication: an unauthenticated caller must not be able to make us buffer an arbitrary body.
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > DJI_WEBHOOK_MAX_BODY_BYTES:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Payload too large")
    chunks: list[bytes] = []
    received = 0
    async for chunk in request.stream():
        received += len(chunk)
        if received > DJI_WEBHOOK_MAX_BODY_BYTES:
            raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Payload too large")
        chunks.append(chunk)
    raw_body = b"".join(chunks)
    body_hash = hashlib.sha256(raw_body).hexdigest()
    settings = get_settings()

    # 1. Authenticate the caller. This endpoint has no bearer token and routes
    # into a tenant chosen by a caller-supplied header, so the HMAC signature is
    # the ONLY thing standing between the internet and any tenant's telemetry.
    # It is therefore mandatory, and the endpoint is disabled (fails closed)
    # unless a secret is configured -- there is no default/test secret.
    webhook_secret = getattr(settings, "dji_webhook_secret", None)
    if not webhook_secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="DJI FlightHub webhook is not configured",
        )
    if not telemetry_service.verify_webhook_signature(raw_body, x_dji_signature, webhook_secret):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing DJI FlightHub webhook signature",
        )

    # 2. Determine target organization
    if not x_organization_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing X-Organization-ID header for tenant routing",
        )

    try:
        org_id = uuid.UUID(x_organization_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid X-Organization-ID format"
        )

    # 2b. Commercial entitlement of the target tenant (same resolver as require_feature).
    from app.services.entitlement_service import EntitlementResolutionStatus, resolve_entitlements

    ent = resolve_entitlements(db, organization_id=org_id)
    if ent.resolution_status not in (
        EntitlementResolutionStatus.ACTIVE,
        EntitlementResolutionStatus.INACTIVE_PLAN,
    ) or not ent.effective_features.get("flight_telemetry", False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Organization is not entitled to flight telemetry ingestion",
        )

    # 3. Parse JSON payload
    try:
        payload_dict = json.loads(raw_body.decode("utf-8"))
        dji_payload = DJIFlightHubWebhookPayload(**payload_dict)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Malformed DJI webhook payload",
        )

    # 4. Normalize & Process Event
    normalized = telemetry_service.adapt_dji_flighthub_payload(dji_payload)
    result = telemetry_service.process_normalized_event(
        db, organization_id=org_id, event=normalized, raw_payload_hash=body_hash
    )
    db.commit()

    return {
        "bid": dji_payload.bid,
        "status": result.status,
        "asset_id": str(result.asset_id) if result.asset_id else None,
        "flight_id": str(result.flight_id) if result.flight_id else None,
        "readings_count": result.readings_count,
        "message": result.message,
    }


@router.post(
    "/ingest",
    response_model=TelemetryIngestResponse,
    dependencies=[Depends(require_permission(Permission.DRONE_WRITE))],
)
def ingest_telemetry_batch(
    payload: TelemetryIngestRequest,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(get_current_user),
) -> TelemetryIngestResponse:
    """Authenticated generic batch ingestion endpoint for drone / HUMS telemetry."""
    res = telemetry_service.ingest_telemetry_batch(
        db, organization_id=current_user.organization_id, request=payload
    )
    db.commit()
    return res


@router.post(
    "/asset-mappings",
    response_model=ExternalAssetMappingResponse,
    dependencies=[Depends(require_permission(Permission.DRONE_WRITE))],
)
def create_external_asset_mapping(
    payload: ExternalAssetMappingCreate,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(get_current_user),
) -> ExternalAssetMappingResponse:
    """Registers an external device identifier (e.g. DJI SN) to a KOTA Asset within caller's tenant."""
    mapping = telemetry_service.create_asset_mapping(
        db, organization_id=current_user.organization_id, payload=payload
    )
    db.commit()
    return ExternalAssetMappingResponse.model_validate(mapping)


@router.get(
    "/asset-mappings",
    response_model=list[ExternalAssetMappingResponse],
    dependencies=[Depends(require_permission(Permission.DRONE_READ))],
)
def list_external_asset_mappings(
    source_system: str | None = Query(None),
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(get_current_user),
) -> list[ExternalAssetMappingResponse]:
    mappings = telemetry_service.list_asset_mappings(
        db, organization_id=current_user.organization_id, source_system=source_system
    )
    return [ExternalAssetMappingResponse.model_validate(m) for m in mappings]


@router.get(
    "/events",
    dependencies=[Depends(require_permission(Permission.DRONE_READ))],
)
def list_telemetry_event_logs(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    asset_id: uuid.UUID | None = Query(default=None),
    processing_status: str | None = Query(default=None, max_length=32),
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    conds = [TelemetryEventLog.organization_id == current_user.organization_id]
    if asset_id is not None:
        conds.append(TelemetryEventLog.asset_id == asset_id)
    if processing_status:
        conds.append(TelemetryEventLog.processing_status == processing_status.upper())
    total = db.execute(select(func.count(TelemetryEventLog.id)).where(*conds)).scalar_one()
    stmt = (
        select(TelemetryEventLog)
        .where(*conds)
        .order_by(desc(TelemetryEventLog.received_timestamp))
        .offset(offset)
        .limit(limit)
    )
    rows = db.execute(stmt).scalars().all()
    return {
        "total": total,  # previously len(page): the real total is needed for pagination
        "items": [
            {
                "id": str(r.id),
                "source_system": r.source_system,
                "source_event_id": r.source_event_id,
                "source_asset_id": r.source_asset_id,
                "asset_id": str(r.asset_id) if r.asset_id else None,
                "flight_id": str(r.flight_id) if r.flight_id else None,
                "event_type": r.event_type,
                "event_timestamp": r.event_timestamp.isoformat(),
                "received_timestamp": r.received_timestamp.isoformat(),
                "processing_status": r.processing_status,
                "readings_count": r.readings_count,
                "rejection_reason": r.rejection_reason,
            }
            for r in rows
        ],
    }


@router.get(
    "/freshness-policies",
    response_model=list[TelemetryFreshnessPolicyResponse],
    dependencies=[Depends(require_permission(Permission.DRONE_READ))],
)
def list_telemetry_freshness_policies(
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(get_current_user),
) -> list[TelemetryFreshnessPolicyResponse]:
    """List tenant-configured telemetry freshness policies."""
    policies = telemetry_service.list_freshness_policies(db, current_user.organization_id)
    return [TelemetryFreshnessPolicyResponse.model_validate(p) for p in policies]


@router.post(
    "/freshness-policies",
    response_model=TelemetryFreshnessPolicyResponse,
    dependencies=[Depends(require_permission(Permission.DRONE_WRITE))],
)
def create_or_update_telemetry_freshness_policy(
    payload: TelemetryFreshnessPolicyCreate,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(get_current_user),
) -> TelemetryFreshnessPolicyResponse:
    """Create or update a telemetry freshness threshold policy for tenant, asset, or source."""
    policy = telemetry_service.upsert_freshness_policy(db, current_user.organization_id, payload)
    return TelemetryFreshnessPolicyResponse.model_validate(policy)



@router.get(
    "/assets/{asset_id}/status",
    dependencies=[Depends(require_permission(Permission.DRONE_READ))],
    summary="Telemetry state, last received time and recent events for one asset",
)
def get_asset_telemetry_state(
    asset_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    telemetry_service._require_asset(db, current_user.organization_id, asset_id)
    return telemetry_service.get_asset_telemetry_status(
        db, organization_id=current_user.organization_id, asset_id=asset_id
    )


@router.get(
    "/assets/{asset_id}/latest",
    dependencies=[Depends(require_permission(Permission.DRONE_READ))],
    summary="Latest reading of every sensor (value, quality, age)",
)
def get_asset_latest_readings(
    asset_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    return telemetry_service.get_latest_readings(
        db, organization_id=current_user.organization_id, asset_id=asset_id
    )


@router.get(
    "/assets/{asset_id}/history",
    dependencies=[Depends(require_permission(Permission.DRONE_READ))],
    summary="Bounded telemetry history (default last 24h, max 1000 rows per page)",
)
def get_asset_reading_history(
    asset_id: uuid.UUID,
    sensor_code: str | None = Query(default=None, max_length=64),
    since: datetime | None = Query(default=None),
    until: datetime | None = Query(default=None),
    limit: int = Query(200, ge=1, le=telemetry_service.MAX_HISTORY_LIMIT),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    return telemetry_service.get_reading_history(
        db, organization_id=current_user.organization_id, asset_id=asset_id,
        sensor_code=sensor_code, since=since, until=until, limit=limit, offset=offset,
    )


@router.get(
    "/assets/{asset_id}/flights",
    dependencies=[Depends(require_permission(Permission.DRONE_READ))],
    summary="Flight records created or extended from telemetry",
)
def get_asset_telemetry_flights(
    asset_id: uuid.UUID,
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(get_current_user),
) -> list[dict[str, Any]]:
    return telemetry_service.get_asset_flights(
        db, organization_id=current_user.organization_id, asset_id=asset_id, limit=limit
    )
