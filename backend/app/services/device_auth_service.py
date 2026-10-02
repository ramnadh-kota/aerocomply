"""C2: device credentials for companion computers / edge gateways (machine-to-cloud identity).

A device authenticates with ONE opaque credential presented in the `X-Kota-Device-Key` header:

    kdev.<edge_device_uuid>.<secret>

* the uuid is the `edge_devices.id` primary key, so the tenant is derived from the DEVICE ROW -- never from a
  caller-supplied organization header (a device can only ever write into its own tenant);
* only SHA-256(secret) is stored (`metadata_json["credential"]`); the secret is 256 bits of CSPRNG output, so a fast
  hash is appropriate (nothing to brute-force) and the plaintext is returned exactly once, at issue/rotation;
* comparison is constant-time and every failure mode returns the same 401, so the response does not reveal whether a
  device id exists, is revoked, expired or merely has the wrong secret;
* rotation keeps the previous secret valid for a short, explicit overlap (default 0) so a fleet can roll keys without a
  gap; revocation (EdgeDevice.status == REVOKED) and a suspended / deletion-pending organization fail closed;
* devices provisioned before C2 carry no `credential` object and are refused until rotated (fail closed).

Nothing here issues commands to an aircraft: a device credential only authorises read-only telemetry upload and the
device's own heartbeat.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import UnauthorizedError
from app.models.organization import Organization, OrganizationStatus
from app.models.telemetry import EdgeDevice
from app.schemas.edge_hardware import EdgeDeviceLifecycleStatus
from app.services.audit_service import record_audit_event

log = structlog.get_logger(__name__)

TOKEN_PREFIX = "kdev"
MAX_ROTATION_GRACE_SECONDS = 3600
DEFAULT_CREDENTIAL_TTL_DAYS = 365
_DENIED = "Invalid device credential"


def _hash(secret: str) -> str:
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


def _parse(presented: str | None) -> tuple[uuid.UUID, str] | None:
    if not presented or len(presented) > 256:
        return None
    parts = presented.strip().split(".")
    if len(parts) != 3 or parts[0] != TOKEN_PREFIX or not parts[2]:
        return None
    try:
        return uuid.UUID(parts[1]), parts[2]
    except ValueError:
        return None


def issue_credential(
    device: EdgeDevice, *, now: datetime | None = None, grace_seconds: int = 0,
    ttl_days: int | None = DEFAULT_CREDENTIAL_TTL_DAYS,
) -> str:
    """Mint a new credential for `device` (mutates metadata_json; caller flushes/commits). Returns the plaintext token,
    which is never stored or recoverable."""
    now = now or datetime.now(UTC)
    grace = max(0, min(int(grace_seconds), MAX_ROTATION_GRACE_SECONDS))
    secret = secrets.token_urlsafe(32)
    meta: dict[str, Any] = dict(device.metadata_json or {})
    old = dict(meta.get("credential") or {})
    cred: dict[str, Any] = {
        "hash": _hash(secret),
        "version": int(old.get("version", 0)) + 1,
        "issued_at": now.isoformat(),
        "expires_at": (now + timedelta(days=ttl_days)).isoformat() if ttl_days else None,
        "previous_hash": old.get("hash") if grace and old.get("hash") else None,
        "previous_valid_until": (now + timedelta(seconds=grace)).isoformat() if grace and old.get("hash") else None,
    }
    meta["credential"] = cred
    meta.pop("auth_token_hash", None)  # legacy, unverified field is superseded
    device.metadata_json = meta
    return f"{TOKEN_PREFIX}.{device.id}.{secret}"


def authenticate_device(db: Session, presented: str | None, *, now: datetime | None = None) -> EdgeDevice:
    """Resolve a presented credential to its (ACTIVE, non-revoked) EdgeDevice or raise UnauthorizedError."""
    now = now or datetime.now(UTC)
    parsed = _parse(presented)
    device = None
    if parsed is not None:
        device = db.execute(select(EdgeDevice).where(EdgeDevice.id == parsed[0])).scalar_one_or_none()
    secret = parsed[1] if parsed else ""
    cred = dict((device.metadata_json or {}).get("credential") or {}) if device is not None else {}

    # Always perform a comparison so timing does not distinguish "no such device" from "wrong secret".
    presented_hash = _hash(secret)
    ok = hmac.compare_digest(presented_hash, str(cred.get("hash") or "0" * 64))
    if not ok and cred.get("previous_hash") and cred.get("previous_valid_until"):
        prev_ok = hmac.compare_digest(presented_hash, str(cred["previous_hash"]))
        ok = prev_ok and now <= datetime.fromisoformat(cred["previous_valid_until"])
    if not ok or device is None:
        raise UnauthorizedError(_DENIED)

    reason: str | None = None
    if device.status == EdgeDeviceLifecycleStatus.REVOKED:
        reason = "revoked"
    elif cred.get("expires_at") and now > datetime.fromisoformat(cred["expires_at"]):
        reason = "expired"
    else:
        org = db.get(Organization, device.organization_id)
        if org is None or org.status == OrganizationStatus.SUSPENDED or org.deleted_at is not None:
            reason = "organization_unavailable"
    if reason:
        log.warning("device_auth.denied", device_pk=str(device.id), reason=reason)
        raise UnauthorizedError(_DENIED)
    return device


def rotate_credential(
    db: Session, *, organization_id: uuid.UUID, device_id: str, grace_seconds: int = 0,
    actor_user_id: uuid.UUID | None = None,
) -> tuple[EdgeDevice, str]:
    from app.core.errors import ConflictError, NotFoundError

    device = db.execute(
        select(EdgeDevice).where(EdgeDevice.organization_id == organization_id, EdgeDevice.device_id == device_id)
    ).scalar_one_or_none()
    if device is None:
        raise NotFoundError(f"EdgeDevice '{device_id}' not found in organization")
    if device.status == EdgeDeviceLifecycleStatus.REVOKED:
        raise ConflictError("Revoked devices cannot receive a new credential", code="device_revoked")
    token = issue_credential(device, grace_seconds=grace_seconds)
    db.flush()
    record_audit_event(
        db, organization_id=organization_id, user_id=actor_user_id, action="edge_device.credential_rotated",
        entity_type="edge_device", entity_id=device.id,
        metadata={"device_id": device_id, "credential_version": device.metadata_json["credential"]["version"],
                  "grace_seconds": max(0, min(int(grace_seconds), MAX_ROTATION_GRACE_SECONDS))},
    )
    return device, token


# --------------------------------------------------------------------- connectivity
DEFAULT_HEARTBEAT_INTERVAL_SECONDS = 30


def connectivity_status(device: EdgeDevice, now: datetime | None = None) -> dict[str, Any]:
    """Connectivity derived from recorded evidence only.

    ONLINE   heartbeat within `connectivity_timeout_seconds` (default 3 x heartbeat interval)
    DEGRADED heartbeat older than the timeout but within 2 x timeout, or the device reports a degraded link
    OFFLINE  older than 2 x timeout, or never heard from since provisioning, or revoked
    Telemetry freshness is reported separately: a device can heartbeat while its autopilot link is silent."""
    now = now or datetime.now(UTC)
    meta = device.metadata_json or {}
    cfg = meta.get("active_config") or {}
    interval = int(cfg.get("heartbeat_interval_sec") or DEFAULT_HEARTBEAT_INTERVAL_SECONDS)
    timeout = int(cfg.get("connectivity_timeout_seconds") or interval * 3)
    hb = meta.get("last_heartbeat_at_device_session")  # set only by real device heartbeats (see below)
    last_hb = datetime.fromisoformat(hb) if hb else None
    age = (now - last_hb).total_seconds() if last_hb else None

    if device.status == EdgeDeviceLifecycleStatus.REVOKED:
        state, reason = "REVOKED", "device credential revoked"
    elif age is None:
        state, reason = "OFFLINE", "no authenticated heartbeat received yet"
    elif age <= timeout:
        reported = (meta.get("observability") or {}).get("connectivity_state")
        state = "DEGRADED" if reported in ("DEGRADED", "CELLULAR_BACKUP") else "ONLINE"
        reason = f"link reported {reported}" if state == "DEGRADED" else "heartbeat within timeout"
    elif age <= 2 * timeout:
        state, reason = "DEGRADED", f"heartbeat {int(age)}s old (timeout {timeout}s)"
    else:
        state, reason = "OFFLINE", f"no heartbeat for {int(age)}s (timeout {timeout}s)"

    tl = meta.get("last_telemetry_at")
    t_age = (now - datetime.fromisoformat(tl)).total_seconds() if tl else None
    fresh_limit = int(cfg.get("telemetry_stale_after_seconds") or 30)
    if t_age is None:
        freshness = "NO_TELEMETRY"
    else:
        freshness = "FRESH" if t_age <= fresh_limit else ("STALE" if t_age <= 10 * fresh_limit else "LOST")
    return {
        "device_id": device.device_id,
        "connectivity": state,
        "reason": reason,
        "last_heartbeat_at": hb,
        "heartbeat_age_seconds": None if age is None else round(age, 1),
        "connectivity_timeout_seconds": timeout,
        "telemetry_freshness": freshness,
        "last_telemetry_at": tl,
        "telemetry_age_seconds": None if t_age is None else round(t_age, 1),
        "telemetry_stale_after_seconds": fresh_limit,
        "data_source_id": meta.get("data_source_id"),
        "asset_id": str(device.asset_id) if device.asset_id else None,
        "credential_version": (meta.get("credential") or {}).get("version"),
        "evaluated_at": now.isoformat(),
    }


def record_device_heartbeat(device: EdgeDevice, now: datetime | None = None) -> None:
    """Stamp an AUTHENTICATED heartbeat (kept distinct from the legacy user-posted heartbeat)."""
    now = now or datetime.now(UTC)
    meta = dict(device.metadata_json or {})
    meta["last_heartbeat_at_device_session"] = now.isoformat()
    device.metadata_json = meta


def record_device_telemetry(device: EdgeDevice, now: datetime | None = None) -> None:
    now = now or datetime.now(UTC)
    meta = dict(device.metadata_json or {})
    meta["last_telemetry_at"] = now.isoformat()
    device.metadata_json = meta


def bind_data_source(
    db: Session, *, organization_id: uuid.UUID, device_id: str, data_source_id: uuid.UUID,
    actor_user_id: uuid.UUID | None = None,
) -> EdgeDevice:
    """Map a device to the ONE approved MAVLink data source its uploads are routed into. The binding is chosen by an
    administrator; an uploading device can never name a data source itself."""
    from app.core.errors import ConflictError, NotFoundError
    from app.models.data_source import DataSource, DataSourceConnectorType

    device = db.execute(
        select(EdgeDevice).where(EdgeDevice.organization_id == organization_id, EdgeDevice.device_id == device_id)
    ).scalar_one_or_none()
    if device is None:
        raise NotFoundError(f"EdgeDevice '{device_id}' not found in organization")
    source = db.execute(
        select(DataSource).where(DataSource.id == data_source_id, DataSource.organization_id == organization_id)
    ).scalar_one_or_none()
    if source is None:
        raise NotFoundError("Data source not found")
    if source.connector_type != DataSourceConnectorType.MAVLINK:
        raise ConflictError("Only MAVLINK data sources can be bound to a drone companion device",
                            code="unsupported_connector_type")
    meta = dict(device.metadata_json or {})
    meta["data_source_id"] = str(source.id)
    device.metadata_json = meta
    db.flush()
    record_audit_event(
        db, organization_id=organization_id, user_id=actor_user_id, action="edge_device.data_source_bound",
        entity_type="edge_device", entity_id=device.id,
        metadata={"device_id": device_id, "data_source_id": str(source.id)},
    )
    return device
