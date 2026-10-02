"""M14/M15/M16: Edge Hardware & Platform Productization Service.

Provides repeatable edge device provisioning, versioned configuration management,
canonical heartbeat processing, secure command channels, revocation enforcement,
and full physical-to-KOTA audit lineage.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AeroComplyError, ConflictError, ForbiddenError, NotFoundError
from app.models.evidence import Evidence
from app.models.finding import Finding
from app.models.hums import HUMSExceedance, HUMSSensor, HUMSSensorReading
from app.models.proactive_signal import ProactiveSignalRecord
from app.models.telemetry import EdgeDevice, TelemetryEventLog, TelemetryProcessingStatus
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
    EdgeDeviceLifecycleStatus,
    EdgeDeviceProvisionRequest,
    EdgeDeviceProvisionResponse,
    EdgeDeviceResponse,
    EdgeDeviceRevokeResponse,
)
from app.services import device_auth_service, telemetry_service
from app.services.audit_service import record_audit_event


def register_edge_device(
    db: Session,
    *,
    organization_id: uuid.UUID,
    payload: EdgeDeviceCreate,
    actor_user_id: uuid.UUID | None = None,
) -> EdgeDevice:
    """Registers or updates a hardware node / gateway within a tenant."""
    existing = db.execute(
        select(EdgeDevice).where(
            EdgeDevice.organization_id == organization_id,
            EdgeDevice.device_id == payload.device_id,
        )
    ).scalar_one_or_none()

    now = datetime.now(UTC)
    if existing is not None:
        if existing.status == EdgeDeviceLifecycleStatus.REVOKED:
            raise AeroComplyError(f"Device '{payload.device_id}' is revoked and cannot be updated.")
        existing.gateway_id = payload.gateway_id
        existing.asset_id = payload.asset_id
        existing.device_type = payload.device_type
        existing.firmware_version = payload.firmware_version
        existing.metadata_json = payload.metadata_json
        existing.updated_at = now
        db.flush()
        return existing

    device = EdgeDevice(
        organization_id=organization_id,
        device_id=payload.device_id,
        gateway_id=payload.gateway_id,
        asset_id=payload.asset_id,
        device_type=payload.device_type,
        firmware_version=payload.firmware_version,
        status=EdgeDeviceLifecycleStatus.ACTIVE,
        last_heartbeat_at=now,
        metadata_json=payload.metadata_json or {},
    )
    db.add(device)
    db.flush()

    record_audit_event(
        db,
        action="edge_device.registered",
        entity_type="edge_device",
        entity_id=device.id,
        organization_id=organization_id,
        user_id=actor_user_id,
        metadata={"device_id": payload.device_id, "device_type": payload.device_type},
    )
    return device


def provision_edge_device(
    db: Session,
    *,
    organization_id: uuid.UUID,
    payload: EdgeDeviceProvisionRequest,
    actor_user_id: uuid.UUID | None = None,
) -> EdgeDeviceProvisionResponse:
    """M16: Repeatable zero-code customer device provisioning."""
    existing = db.execute(
        select(EdgeDevice).where(
            EdgeDevice.organization_id == organization_id,
            EdgeDevice.device_id == payload.device_id,
        )
    ).scalar_one_or_none()

    now = datetime.now(UTC)
    # C2: the credential is always server-generated (payload.auth_secret is ignored: a caller-chosen secret is
    # typically weak) and verified by device_auth_service on every device-facing call.

    initial_config = payload.initial_config or {
        "sampling_hz": 1000,
        "telemetry_interval_sec": 5,
        "heartbeat_interval_sec": 30,
        "buffer_capacity": 500,
        "active_channels": [s.channel or "CH1" for s in payload.sensors] if payload.sensors else ["CH1"],
    }

    config_history_entry = {
        "version": 1,
        "created_at": now.isoformat(),
        "applied_at": now.isoformat(),
        "operator_user_id": str(actor_user_id) if actor_user_id else "SYSTEM",
        "change_summary": "Initial factory provisioning configuration",
        "status": "APPLIED",
        "settings": initial_config,
    }

    sensor_inventory = [s.model_dump() for s in payload.sensors]

    meta = {
        "lifecycle_stage": EdgeDeviceLifecycleStatus.CONFIGURED,
        "active_config_version": 1,
        "active_config": initial_config,
        "config_history": [config_history_entry],
        "sensor_inventory": sensor_inventory,
        "hardware_metadata": payload.hardware_metadata or {},
        "command_queue": [],
        "observability": {
            "uptime_seconds": 0,
            "cpu_percent": 0.0,
            "memory_percent": 0.0,
            "queue_depth": 0,
            "restart_count": 0,
        },
    }

    if existing:
        if existing.status == EdgeDeviceLifecycleStatus.REVOKED:
            raise ConflictError(
                f"Device '{payload.device_id}' is revoked and cannot be re-provisioned.",
                code="device_revoked",
            )
        for kept in ("credential", "data_source_id"):  # re-provisioning must not silently drop the binding
            if (existing.metadata_json or {}).get(kept) is not None:
                meta[kept] = existing.metadata_json[kept]
        existing.device_type = payload.device_type
        existing.gateway_id = payload.gateway_id
        existing.asset_id = payload.asset_id
        existing.firmware_version = payload.firmware_version
        existing.status = EdgeDeviceLifecycleStatus.ACTIVE
        existing.metadata_json = meta
        existing.updated_at = now
        device = existing
    else:
        device = EdgeDevice(
            organization_id=organization_id,
            device_id=payload.device_id,
            gateway_id=payload.gateway_id,
            asset_id=payload.asset_id,
            device_type=payload.device_type,
            firmware_version=payload.firmware_version,
            status=EdgeDeviceLifecycleStatus.ACTIVE,
            last_heartbeat_at=now,
            metadata_json=meta,
        )
        db.add(device)

    db.flush()
    raw_token = device_auth_service.issue_credential(device)
    db.flush()

    record_audit_event(
        db,
        action="edge_device.provisioned",
        entity_type="edge_device",
        entity_id=device.id,
        organization_id=organization_id,
        user_id=actor_user_id,
        metadata={
            "device_id": payload.device_id,
            "device_type": payload.device_type,
            "sensors_count": len(payload.sensors),
            "asset_id": str(payload.asset_id) if payload.asset_id else None,
        },
    )

    return EdgeDeviceProvisionResponse(
        device=EdgeDeviceResponse.model_validate(device),
        provisioning_token=raw_token,
        config_version=1,
        lifecycle_stage=EdgeDeviceLifecycleStatus.CONFIGURED,
    )


def update_device_configuration(
    db: Session,
    *,
    organization_id: uuid.UUID,
    device_id: str,
    payload: EdgeDeviceConfigUpdate,
    actor_user_id: uuid.UUID | None = None,
) -> EdgeDeviceConfigResponse:
    """M16: Creates a new immutable version of device acquisition configuration."""
    device = db.execute(
        select(EdgeDevice).where(
            EdgeDevice.organization_id == organization_id,
            EdgeDevice.device_id == device_id,
        )
    ).scalar_one_or_none()

    if not device:
        raise NotFoundError(f"EdgeDevice '{device_id}' not found in organization")

    if device.status == EdgeDeviceLifecycleStatus.REVOKED:
        raise ConflictError(f"Cannot configure revoked device '{device_id}'", code="device_revoked")

    meta = dict(device.metadata_json or {})
    current_version = meta.get("active_config_version", 1)
    new_version = current_version + 1
    now = datetime.now(UTC)

    config_entry = {
        "version": new_version,
        "created_at": now.isoformat(),
        "applied_at": now.isoformat() if payload.apply_immediately else None,
        "operator_user_id": str(actor_user_id) if actor_user_id else "OPERATOR",
        "change_summary": payload.change_summary or f"Updated configuration to v{new_version}",
        "status": "APPLIED" if payload.apply_immediately else "DRAFT",
        "settings": payload.settings,
    }

    history = list(meta.get("config_history", []))
    history.append(config_entry)
    meta["config_history"] = history

    if payload.apply_immediately:
        meta["active_config_version"] = new_version
        meta["active_config"] = payload.settings

    device.metadata_json = meta
    device.updated_at = now
    db.flush()

    record_audit_event(
        db,
        action="edge_device.config_updated",
        entity_type="edge_device",
        entity_id=device.id,
        organization_id=organization_id,
        user_id=actor_user_id,
        metadata={"device_id": device_id, "new_version": new_version, "applied": payload.apply_immediately},
    )

    return EdgeDeviceConfigResponse(
        device_id=device.device_id,
        active_version=meta.get("active_config_version", new_version),
        applied_at=now if payload.apply_immediately else None,
        settings=meta.get("active_config", payload.settings),
        history=history,
    )


def rollback_device_configuration(
    db: Session,
    *,
    organization_id: uuid.UUID,
    device_id: str,
    target_version: int,
    actor_user_id: uuid.UUID | None = None,
) -> EdgeDeviceConfigResponse:
    """M16: Restores a previous validated configuration version."""
    device = db.execute(
        select(EdgeDevice).where(
            EdgeDevice.organization_id == organization_id,
            EdgeDevice.device_id == device_id,
        )
    ).scalar_one_or_none()

    if not device:
        raise NotFoundError(f"EdgeDevice '{device_id}' not found in organization")

    meta = dict(device.metadata_json or {})
    history = list(meta.get("config_history", []))
    target_entry = next((h for h in history if h.get("version") == target_version), None)

    if not target_entry:
        raise NotFoundError(f"Configuration version v{target_version} not found in device history")

    now = datetime.now(UTC)
    meta["active_config_version"] = target_version
    meta["active_config"] = target_entry.get("settings", {})
    device.metadata_json = meta
    device.updated_at = now
    db.flush()

    record_audit_event(
        db,
        action="edge_device.config_rolled_back",
        entity_type="edge_device",
        entity_id=device.id,
        organization_id=organization_id,
        user_id=actor_user_id,
        metadata={"device_id": device_id, "rolled_back_to": target_version},
    )

    return EdgeDeviceConfigResponse(
        device_id=device.device_id,
        active_version=target_version,
        applied_at=now,
        settings=meta["active_config"],
        history=history,
    )


def process_device_heartbeat(
    db: Session,
    *,
    organization_id: uuid.UUID,
    payload: EdgeDeviceHeartbeatRequest,
) -> EdgeDeviceHeartbeatResponse:
    """M16: Ingests canonical device heartbeat and checks config synchronicity."""
    device = db.execute(
        select(EdgeDevice).where(
            EdgeDevice.organization_id == organization_id,
            EdgeDevice.device_id == payload.device_id,
        )
    ).scalar_one_or_none()

    if not device:
        raise NotFoundError(f"EdgeDevice '{payload.device_id}' not found in organization")

    if device.status == EdgeDeviceLifecycleStatus.REVOKED:
        raise ForbiddenError(f"Heartbeat rejected: Device '{payload.device_id}' is revoked.")

    now = datetime.now(UTC)
    device.last_heartbeat_at = now
    if device.status != EdgeDeviceLifecycleStatus.ACTIVE:
        device.status = EdgeDeviceLifecycleStatus.ACTIVE

    meta = dict(device.metadata_json or {})
    meta["lifecycle_stage"] = EdgeDeviceLifecycleStatus.CONNECTED
    meta["last_heartbeat_timestamp"] = payload.timestamp.isoformat()

    # Update device observability
    obs = dict(meta.get("observability", {}))
    if payload.uptime_seconds is not None:
        obs["uptime_seconds"] = payload.uptime_seconds
    if payload.queue_depth is not None:
        obs["queue_depth"] = payload.queue_depth
    if payload.connectivity_state:
        obs["connectivity_state"] = payload.connectivity_state
    if payload.observability:
        obs.update(payload.observability)
    meta["observability"] = obs

    # Update sensor states
    if payload.sensor_states:
        meta["sensor_states"] = payload.sensor_states

    # Check config version sync
    active_version = meta.get("active_config_version", 1)
    requires_sync = payload.config_version is not None and payload.config_version < active_version

    # Pending commands in queue
    cmd_queue = list(meta.get("command_queue", []))
    pending_cmds = [c for c in cmd_queue if c.get("status") == "PENDING"]

    device.metadata_json = meta
    db.flush()

    return EdgeDeviceHeartbeatResponse(
        status="ACK",
        server_time=now,
        pending_commands_count=len(pending_cmds),
        latest_config_version=active_version,
        requires_config_sync=requires_sync,
    )


def issue_device_command(
    db: Session,
    *,
    organization_id: uuid.UUID,
    device_id: str,
    payload: EdgeDeviceCommandRequest,
    actor_user_id: uuid.UUID | None = None,
) -> EdgeDeviceCommandResponse:
    """M16: Dispatches a safe operational command to an active edge device."""
    device = db.execute(
        select(EdgeDevice).where(
            EdgeDevice.organization_id == organization_id,
            EdgeDevice.device_id == device_id,
        )
    ).scalar_one_or_none()

    if not device:
        raise NotFoundError(f"EdgeDevice '{device_id}' not found in organization")

    if device.status == EdgeDeviceLifecycleStatus.REVOKED:
        raise ForbiddenError(f"Cannot dispatch command to revoked device '{device_id}'")

    now = datetime.now(UTC)
    cmd_id = f"cmd_{secrets.token_hex(8)}"
    cmd_entry = {
        "command_id": cmd_id,
        "command_type": payload.command_type,
        "parameters": payload.parameters or {},
        "status": "PENDING",
        "issued_at": now.isoformat(),
        "issuer_user_id": str(actor_user_id) if actor_user_id else "SYSTEM",
    }

    meta = dict(device.metadata_json or {})
    queue = list(meta.get("command_queue", []))
    queue.append(cmd_entry)
    meta["command_queue"] = queue
    device.metadata_json = meta
    db.flush()

    record_audit_event(
        db,
        action="edge_device.command_issued",
        entity_type="edge_device",
        entity_id=device.id,
        organization_id=organization_id,
        user_id=actor_user_id,
        metadata={"device_id": device_id, "command_id": cmd_id, "command_type": payload.command_type},
    )

    return EdgeDeviceCommandResponse(
        command_id=cmd_id,
        device_id=device_id,
        command_type=payload.command_type,
        status="PENDING",
        issued_at=now,
    )


def submit_command_result(
    db: Session,
    *,
    organization_id: uuid.UUID,
    device_id: str,
    payload: EdgeDeviceCommandResultSubmit,
) -> EdgeDeviceCommandResponse:
    """M16: Updates command execution state upon edge device execution."""
    device = db.execute(
        select(EdgeDevice).where(
            EdgeDevice.organization_id == organization_id,
            EdgeDevice.device_id == device_id,
        )
    ).scalar_one_or_none()

    if not device:
        raise NotFoundError(f"EdgeDevice '{device_id}' not found in organization")

    meta = dict(device.metadata_json or {})
    queue = list(meta.get("command_queue", []))
    cmd = next((c for c in queue if c.get("command_id") == payload.command_id), None)

    if not cmd:
        raise NotFoundError(f"Command '{payload.command_id}' not found in device queue")

    now = datetime.now(UTC)
    cmd["status"] = payload.status
    cmd["executed_at"] = now.isoformat()
    cmd["result"] = payload.result or {}
    if payload.error_message:
        cmd["error_message"] = payload.error_message

    device.metadata_json = meta
    db.flush()

    return EdgeDeviceCommandResponse(
        command_id=cmd["command_id"],
        device_id=device_id,
        command_type=cmd["command_type"],
        status=payload.status,
        issued_at=datetime.fromisoformat(cmd["issued_at"]),
        executed_at=now,
        result=payload.result,
    )


def revoke_edge_device(
    db: Session,
    *,
    organization_id: uuid.UUID,
    device_id: str,
    reason: str,
    actor_user_id: uuid.UUID | None = None,
) -> EdgeDeviceRevokeResponse:
    """M16: Immediately revokes a compromised/decommissioned hardware device."""
    device = db.execute(
        select(EdgeDevice).where(
            EdgeDevice.organization_id == organization_id,
            EdgeDevice.device_id == device_id,
        )
    ).scalar_one_or_none()

    if not device:
        raise NotFoundError(f"EdgeDevice '{device_id}' not found in organization")

    now = datetime.now(UTC)
    device.status = EdgeDeviceLifecycleStatus.REVOKED
    meta = dict(device.metadata_json or {})
    meta["lifecycle_stage"] = EdgeDeviceLifecycleStatus.REVOKED
    meta["revocation"] = {
        "revoked_at": now.isoformat(),
        "reason": reason,
        "revoked_by_user_id": str(actor_user_id) if actor_user_id else "SYSTEM",
    }
    device.metadata_json = meta
    device.updated_at = now
    db.flush()

    record_audit_event(
        db,
        action="edge_device.revoked",
        entity_type="edge_device",
        entity_id=device.id,
        organization_id=organization_id,
        user_id=actor_user_id,
        metadata={"device_id": device_id, "reason": reason},
    )

    return EdgeDeviceRevokeResponse(
        device_id=device_id,
        status=EdgeDeviceLifecycleStatus.REVOKED,
        revoked_at=now,
        reason=reason,
    )


def list_edge_devices(
    db: Session,
    *,
    organization_id: uuid.UUID,
) -> list[EdgeDevice]:
    return list(
        db.execute(
            select(EdgeDevice)
            .where(EdgeDevice.organization_id == organization_id)
            .order_by(EdgeDevice.created_at.desc())
        ).scalars().all()
    )


def extract_primary_measurement_value(raw_values: dict[str, Any]) -> float:
    """Extracts scalar numerical value across prioritized physical sensor metrics."""
    if "rms_g" in raw_values:
        return float(raw_values["rms_g"])
    if "rms_mm_s" in raw_values:
        return float(raw_values["rms_mm_s"])
    if "temp_c" in raw_values:
        return float(raw_values["temp_c"])
    if "pressure_bar" in raw_values:
        return float(raw_values["pressure_bar"])
    if "voltage_v" in raw_values:
        return float(raw_values["voltage_v"])
    if "current_a" in raw_values:
        return float(raw_values["current_a"])
    if "value" in raw_values:
        return float(raw_values["value"])
    for k, v in raw_values.items():
        if isinstance(v, (int, float)):
            return float(v)
    return 0.0


def process_device_telemetry_envelope(
    db: Session,
    *,
    organization_id: uuid.UUID,
    envelope: DeviceTelemetryEnvelope,
) -> dict[str, Any]:
    """Ingests a canonical edge envelope, checks revocation, updates device heartbeat, and fans out to core telemetry."""
    device = db.execute(
        select(EdgeDevice).where(
            EdgeDevice.organization_id == organization_id,
            EdgeDevice.device_id == envelope.device_id,
        )
    ).scalar_one_or_none()

    # M16 Security: Reject telemetry from revoked devices
    if device is not None and device.status == EdgeDeviceLifecycleStatus.REVOKED:
        raise ForbiddenError(f"Telemetry rejected: Device '{envelope.device_id}' is REVOKED.")

    now = datetime.now(UTC)
    if device is not None:
        device.last_heartbeat_at = now
        if envelope.firmware_version:
            device.firmware_version = envelope.firmware_version
        if device.status != EdgeDeviceLifecycleStatus.ACTIVE:
            device.status = EdgeDeviceLifecycleStatus.ACTIVE
        db.flush()

    # Convert envelope measurements to telemetry ingestion format
    readings_payload = []
    for m in envelope.measurements:
        val = extract_primary_measurement_value(m.raw_values)
        readings_payload.append(
            telemetry_service.TelemetryReadingItem(
                sensor_code=m.sensor_code,
                sensor_type=m.sensor_type,
                measurement_type=m.sensor_type,
                value=float(val),
                unit=m.unit,
                data_quality=m.quality,
            )
        )

    # Deduplicate / event id based on sequence and device
    source_event_id = f"edge_{envelope.device_id}_{envelope.sequence_number}_{int(envelope.envelope_timestamp.timestamp())}"
    raw_json_str = envelope.model_dump_json()

    norm_event = telemetry_service.NormalizedTelemetryEvent(
        source_system="KOTA_EDGE_GATEWAY",
        source_event_id=source_event_id,
        source_asset_id=envelope.source_asset_id or envelope.device_id,
        event_type="SENSOR_BURST",
        event_timestamp=envelope.envelope_timestamp,
        readings=readings_payload,
        raw_metadata={
            "device_id": envelope.device_id,
            "gateway_id": envelope.gateway_id,
            "sequence_number": envelope.sequence_number,
            "signature": envelope.signature,
        },
    )

    # Ingest through core telemetry ingestion engine
    result = telemetry_service.process_normalized_event(
        db,
        organization_id=organization_id,
        event=norm_event,
        raw_payload_hash=hashlib.sha256(raw_json_str.encode("utf-8")).hexdigest(),
    )

    return {
        "status": "ACCEPTED",
        "device_id": envelope.device_id,
        "source_event_id": source_event_id,
        "processing_status": result.status,
        "readings_count": result.readings_count,
    }


def trace_telemetry_lineage(
    db: Session,
    *,
    organization_id: uuid.UUID,
    source_event_id: str,
) -> dict[str, Any]:
    """Traces full provenance from physical edge event down to HUMS readings, exceedances, findings, and signals."""
    log = db.execute(
        select(TelemetryEventLog).where(
            TelemetryEventLog.organization_id == organization_id,
            TelemetryEventLog.source_event_id == source_event_id,
        )
    ).scalar_one_or_none()

    if not log:
        raise NotFoundError(f"Telemetry event '{source_event_id}' not found in organization")

    readings = list(
        db.execute(
            select(HUMSSensorReading).where(
                HUMSSensorReading.organization_id == organization_id,
                HUMSSensorReading.ingestion_batch == source_event_id,
            )
        ).scalars().all()
    )

    sensor_ids = {r.sensor_id for r in readings}

    exceedances = []
    if sensor_ids:
        exceedances = list(
            db.execute(
                select(HUMSExceedance).where(
                    HUMSExceedance.organization_id == organization_id,
                    HUMSExceedance.sensor_id.in_(sensor_ids),
                )
            ).scalars().all()
        )

    signals = []
    if log.asset_id:
        signals = list(
            db.execute(
                select(ProactiveSignalRecord).where(
                    ProactiveSignalRecord.organization_id == organization_id,
                    ProactiveSignalRecord.asset_id == log.asset_id,
                )
            ).scalars().all()
        )

    return {
        "source_event_id": log.source_event_id,
        "source_system": log.source_system,
        "event_type": log.event_type,
        "event_timestamp": log.event_timestamp.isoformat(),
        "received_timestamp": log.received_timestamp.isoformat(),
        "payload_hash": log.payload_hash,
        "processing_status": log.processing_status,
        "asset_id": str(log.asset_id) if log.asset_id else None,
        "readings_count": len(readings),
        "readings": [
            {
                "id": str(r.id),
                "sensor_id": str(r.sensor_id),
                "value": r.value,
                "unit": r.unit,
                "data_quality": r.data_quality,
            }
            for r in readings
        ],
        "exceedances_count": len(exceedances),
        "exceedances": [
            {
                "id": str(e.id),
                "sensor_id": str(e.sensor_id),
                "severity": e.severity,
                "parameter": e.parameter,
                # HUMSExceedance has no peak_value/status columns (reading them
                # raised AttributeError); observed vs threshold is what exists.
                "peak_value": e.observed_value,
                "threshold_value": e.threshold_value,
            }
            for e in exceedances
        ],
        "signals_count": len(signals),
        "signals": [
            {
                "id": str(s.id),
                "signal_type": s.signal_type,
                "title": s.title,
                "status": s.status,
            }
            for s in signals
        ],
    }


def get_edge_device_health(
    db: Session,
    *,
    organization_id: uuid.UUID,
    device_id: str,
) -> dict[str, Any]:
    """Calculates hardware node health status based on heartbeat freshness, error rates, and lifecycle."""
    device = db.execute(
        select(EdgeDevice).where(
            EdgeDevice.organization_id == organization_id,
            EdgeDevice.device_id == device_id,
        )
    ).scalar_one_or_none()

    if not device:
        raise NotFoundError(f"Device '{device_id}' not found in organization")

    now = datetime.now(UTC)
    heartbeat_fresh = False
    minutes_since_heartbeat = None
    if device.last_heartbeat_at:
        diff = now - device.last_heartbeat_at
        minutes_since_heartbeat = round(diff.total_seconds() / 60.0, 1)
        heartbeat_fresh = minutes_since_heartbeat < 15.0

    meta = device.metadata_json or {}
    lifecycle_stage = meta.get("lifecycle_stage", device.status)

    if device.status == EdgeDeviceLifecycleStatus.REVOKED:
        health_status = "REVOKED"
    elif heartbeat_fresh:
        health_status = "HEALTHY"
    elif device.last_heartbeat_at:
        health_status = "STALE"
    else:
        health_status = "UNKNOWN"

    return {
        "device_id": device.device_id,
        "device_type": device.device_type,
        "firmware_version": device.firmware_version,
        "status": device.status,
        "lifecycle_stage": lifecycle_stage,
        "health_status": health_status,
        "last_heartbeat_at": device.last_heartbeat_at.isoformat() if device.last_heartbeat_at else None,
        "minutes_since_heartbeat": minutes_since_heartbeat,
        "bound_asset_id": str(device.asset_id) if device.asset_id else None,
        "active_config_version": meta.get("active_config_version", 1),
        "observability": meta.get("observability", {}),
    }


def get_edge_device_inventory(
    db: Session,
    *,
    organization_id: uuid.UUID,
    device_id: str,
) -> list[dict[str, Any]]:
    """Returns the inventoried physical sensors associated with this hardware node."""
    device = db.execute(
        select(EdgeDevice).where(
            EdgeDevice.organization_id == organization_id,
            EdgeDevice.device_id == device_id,
        )
    ).scalar_one_or_none()

    if not device:
        raise NotFoundError(f"EdgeDevice '{device_id}' not found in organization")

    meta = device.metadata_json or {}
    return list(meta.get("sensor_inventory", []))
