"""M14/M15/M16: Edge Hardware & Platform Management Endpoints."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.deps import (
    get_current_user,
    get_db_session,
    require_any_permission,
    require_permission,
)
from app.core.permissions import Permission
from app.schemas.auth import CurrentUser
from app.schemas.edge_hardware import (
    DeviceTelemetryEnvelope,
    EdgeDeviceCommandRequest,
    EdgeDeviceCommandResponse,
    EdgeDeviceCommandResultSubmit,
    EdgeDeviceConfigResponse,
    EdgeDeviceConfigUpdate,
    EdgeDeviceCreate,
    EdgeDeviceHeartbeatRequest,
    EdgeDeviceHeartbeatResponse,
    EdgeDeviceProvisionRequest,
    EdgeDeviceProvisionResponse,
    EdgeDeviceResponse,
    EdgeDeviceRevokeRequest,
    EdgeDeviceRevokeResponse,
)
from app.services import edge_hardware_service

router = APIRouter(prefix="/edge", tags=["Edge Hardware & Platform Management"])

# M20 forensic fix: these handlers called `current_user.require_permission(
# Permission.FLEET_MANAGE|FLEET_READ)` -- CurrentUser has no such method and
# neither permission exists, so 10 endpoints always raised AttributeError
# (HTTP 500). Device administration (provision/register/config/command/revoke)
# is tenant infrastructure management -> ORG_MANAGE; reads need an asset-read
# permission. Device-facing calls (heartbeat, command result, ingest) remain
# plain authenticated calls as before.
_EDGE_MANAGE = require_permission(Permission.ORG_MANAGE)
_EDGE_READ = require_any_permission(Permission.AIRCRAFT_READ, Permission.DRONE_READ)


@router.post("/devices/provision", response_model=EdgeDeviceProvisionResponse, status_code=status.HTTP_201_CREATED)
def provision_device(
    payload: EdgeDeviceProvisionRequest,
    current_user: CurrentUser = Depends(_EDGE_MANAGE),
    db: Session = Depends(get_db_session),
) -> Any:
    return edge_hardware_service.provision_edge_device(
        db,
        organization_id=current_user.organization_id,
        payload=payload,
        actor_user_id=current_user.id,
    )


@router.post("/devices", response_model=EdgeDeviceResponse, status_code=status.HTTP_201_CREATED)
def register_device(
    payload: EdgeDeviceCreate,
    current_user: CurrentUser = Depends(_EDGE_MANAGE),
    db: Session = Depends(get_db_session),
) -> Any:
    return edge_hardware_service.register_edge_device(
        db,
        organization_id=current_user.organization_id,
        payload=payload,
        actor_user_id=current_user.id,
    )


@router.get("/devices", response_model=list[EdgeDeviceResponse])
def list_devices(
    current_user: CurrentUser = Depends(_EDGE_READ),
    db: Session = Depends(get_db_session),
) -> Any:
    return edge_hardware_service.list_edge_devices(
        db,
        organization_id=current_user.organization_id,
    )


@router.get("/devices/{device_id}/health")
def get_device_health(
    device_id: str,
    current_user: CurrentUser = Depends(_EDGE_READ),
    db: Session = Depends(get_db_session),
) -> dict[str, Any]:
    return edge_hardware_service.get_edge_device_health(
        db,
        organization_id=current_user.organization_id,
        device_id=device_id,
    )


@router.get("/devices/{device_id}/sensors")
def get_device_sensors(
    device_id: str,
    current_user: CurrentUser = Depends(_EDGE_READ),
    db: Session = Depends(get_db_session),
) -> list[dict[str, Any]]:
    return edge_hardware_service.get_edge_device_inventory(
        db,
        organization_id=current_user.organization_id,
        device_id=device_id,
    )


@router.post("/devices/{device_id}/config", response_model=EdgeDeviceConfigResponse)
def update_device_config(
    device_id: str,
    payload: EdgeDeviceConfigUpdate,
    current_user: CurrentUser = Depends(_EDGE_MANAGE),
    db: Session = Depends(get_db_session),
) -> Any:
    return edge_hardware_service.update_device_configuration(
        db,
        organization_id=current_user.organization_id,
        device_id=device_id,
        payload=payload,
        actor_user_id=current_user.id,
    )


@router.post("/devices/{device_id}/config/rollback/{target_version}", response_model=EdgeDeviceConfigResponse)
def rollback_device_config(
    device_id: str,
    target_version: int,
    current_user: CurrentUser = Depends(_EDGE_MANAGE),
    db: Session = Depends(get_db_session),
) -> Any:
    return edge_hardware_service.rollback_device_configuration(
        db,
        organization_id=current_user.organization_id,
        device_id=device_id,
        target_version=target_version,
        actor_user_id=current_user.id,
    )


@router.post("/devices/{device_id}/heartbeat", response_model=EdgeDeviceHeartbeatResponse)
def submit_heartbeat(
    device_id: str,
    payload: EdgeDeviceHeartbeatRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db_session),
) -> Any:
    payload.device_id = device_id
    return edge_hardware_service.process_device_heartbeat(
        db,
        organization_id=current_user.organization_id,
        payload=payload,
    )


@router.post("/devices/{device_id}/commands", response_model=EdgeDeviceCommandResponse)
def send_command(
    device_id: str,
    payload: EdgeDeviceCommandRequest,
    current_user: CurrentUser = Depends(_EDGE_MANAGE),
    db: Session = Depends(get_db_session),
) -> Any:
    return edge_hardware_service.issue_device_command(
        db,
        organization_id=current_user.organization_id,
        device_id=device_id,
        payload=payload,
        actor_user_id=current_user.id,
    )


@router.post("/devices/{device_id}/commands/result", response_model=EdgeDeviceCommandResponse)
def submit_command_result(
    device_id: str,
    payload: EdgeDeviceCommandResultSubmit,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db_session),
) -> Any:
    return edge_hardware_service.submit_command_result(
        db,
        organization_id=current_user.organization_id,
        device_id=device_id,
        payload=payload,
    )


@router.post("/devices/{device_id}/revoke", response_model=EdgeDeviceRevokeResponse)
def revoke_device(
    device_id: str,
    payload: EdgeDeviceRevokeRequest,
    current_user: CurrentUser = Depends(_EDGE_MANAGE),
    db: Session = Depends(get_db_session),
) -> Any:
    return edge_hardware_service.revoke_edge_device(
        db,
        organization_id=current_user.organization_id,
        device_id=device_id,
        reason=payload.reason,
        actor_user_id=current_user.id,
    )


@router.get("/lineage/{source_event_id}")
def get_telemetry_lineage(
    source_event_id: str,
    current_user: CurrentUser = Depends(_EDGE_READ),
    db: Session = Depends(get_db_session),
) -> dict[str, Any]:
    return edge_hardware_service.trace_telemetry_lineage(
        db,
        organization_id=current_user.organization_id,
        source_event_id=source_event_id,
    )


@router.post("/ingest", status_code=status.HTTP_202_ACCEPTED)
def ingest_edge_envelope(
    payload: DeviceTelemetryEnvelope,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db_session),
) -> dict[str, Any]:
    return edge_hardware_service.process_device_telemetry_envelope(
        db,
        organization_id=current_user.organization_id,
        envelope=payload,
    )
