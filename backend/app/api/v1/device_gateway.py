"""C2: device-facing (machine) endpoints for drone companion computers.

Authentication is the per-device credential in `X-Kota-Device-Key` (see device_auth_service) -- NOT a user JWT. The
tenant, the asset and the target data source are all derived from the authenticated device row; nothing in the request
can redirect data to another tenant, asset or source. Read-only: these endpoints only accept telemetry and heartbeats
and never return flight commands.
"""
from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.deps import get_db_session
from app.core.errors import ConflictError, ForbiddenError
from app.models.telemetry import EdgeDevice
from app.schemas.edge_hardware import EdgeDeviceHeartbeatRequest, EdgeDeviceHeartbeatResponse
from app.services import acquisition_service, device_auth_service, edge_hardware_service
from app.services.entitlement_service import EntitlementResolutionStatus, resolve_entitlements

router = APIRouter(prefix="/device", tags=["Device Gateway (machine auth)"])

MAX_DEVICE_UPLOAD_BYTES = 1 * 1024 * 1024


def get_authenticated_device(
    x_kota_device_key: str | None = Header(default=None, alias="X-Kota-Device-Key"),
    db: Session = Depends(get_db_session),
) -> EdgeDevice:
    return device_auth_service.authenticate_device(db, x_kota_device_key)


def _require_telemetry_entitlement(db: Session, device: EdgeDevice) -> None:
    ent = resolve_entitlements(db, organization_id=device.organization_id)
    if ent.resolution_status not in (
        EntitlementResolutionStatus.ACTIVE, EntitlementResolutionStatus.INACTIVE_PLAN,
    ) or not ent.effective_features.get("flight_telemetry", False):
        raise ForbiddenError("Organization is not entitled to flight telemetry ingestion")


@router.post("/heartbeat", response_model=EdgeDeviceHeartbeatResponse)
def device_heartbeat(
    payload: EdgeDeviceHeartbeatRequest,
    device: EdgeDevice = Depends(get_authenticated_device),
    db: Session = Depends(get_db_session),
) -> Any:
    if payload.device_id != device.device_id:
        raise ForbiddenError("Heartbeat device_id does not match the authenticated device")
    result = edge_hardware_service.process_device_heartbeat(db, organization_id=device.organization_id, payload=payload)
    device_auth_service.record_device_heartbeat(device)
    db.commit()
    return result


@router.post("/telemetry/mavlink", status_code=status.HTTP_200_OK)
async def device_mavlink_upload(
    request: Request,
    device: EdgeDevice = Depends(get_authenticated_device),
    db: Session = Depends(get_db_session),
) -> dict[str, Any]:
    """Raw MAVLink bytes -> the device's bound data source -> the existing acquisition pipeline (frame validation and
    signing, normalisation, idempotent persistence, HUMS, health evidence)."""
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > MAX_DEVICE_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Payload too large")
    raw = await request.body()
    if len(raw) > MAX_DEVICE_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Payload too large")
    if not raw:
        raise HTTPException(status_code=422, detail="Empty payload")
    _require_telemetry_entitlement(db, device)
    source_id = (device.metadata_json or {}).get("data_source_id")
    if not source_id:
        raise ConflictError("Device is not bound to a data source; an administrator must bind one",
                            code="device_not_bound")
    report = acquisition_service.ingest(
        db, organization_id=device.organization_id, data_source_id=uuid.UUID(source_id), raw=raw,
        actor_user_id=None,
    )
    if report.accepted or report.duplicates:
        device_auth_service.record_device_telemetry(device)
    db.commit()
    return report.to_dict()
