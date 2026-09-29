"""M13: Telemetry Ingestion Service & DJI FlightHub 2 Adapter.

Architecture Invariants:
1. PostgreSQL remains authoritative; zero raw-insert bypasses.
2. Tenant isolation: All asset resolution and idempotency checks are strictly organization-scoped.
3. Domain service reuse: Flight records invoke flight_service.record_flight with double-counting protection.
4. Data quality & HUMS mapping: Sensor readings map directly into HUMSSensor / HUMSSensorReading models.
5. Deterministic idempotency: (organization_id, source_system, source_event_id) prevents duplicate processing.
"""

from __future__ import annotations

import hashlib
import hmac
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import AeroComplyError, NotFoundError
from app.models.asset import Asset
from app.models.battery import Battery, BatteryStatus
from app.models.flight import Flight
from app.models.hums import HUMSSensor, HUMSSensorReading
from app.models.telemetry import (
    ExternalAssetMapping,
    TelemetryEventLog,
    TelemetryProcessingStatus,
)
from app.schemas.telemetry import (
    DJIFlightHubWebhookPayload,
    ExternalAssetMappingCreate,
    NormalizedTelemetryEvent,
    TelemetryBatteryPayload,
    TelemetryEventResult,
    TelemetryFlightPayload,
    TelemetryIngestRequest,
    TelemetryIngestResponse,
    TelemetryReadingItem,
)
from app.services import audit_service, flight_service
import structlog

log = structlog.get_logger(__name__)


def verify_webhook_signature(raw_body: bytes, signature_header: str | None, secret: str) -> bool:
    """Verifies HMAC-SHA256 signature using constant-time comparison."""
    if not signature_header or not secret:
        return False
    try:
        # Strip optional prefix like 'sha256='
        sig = signature_header.strip()
        if sig.startswith("sha256="):
            sig = sig[7:]
        expected = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected.lower(), sig.lower())
    except Exception:
        return False


def create_asset_mapping(
    db: Session, *, organization_id: uuid.UUID, payload: ExternalAssetMappingCreate
) -> ExternalAssetMapping:
    """Registers an external device identifier to a KOTA Asset within the tenant."""
    # Verify asset belongs to organization
    asset = db.execute(
        select(Asset).where(Asset.id == payload.asset_id, Asset.organization_id == organization_id)
    ).scalar_one_or_none()
    if not asset:
        raise NotFoundError("Asset not found in organization")

    existing = db.execute(
        select(ExternalAssetMapping).where(
            ExternalAssetMapping.organization_id == organization_id,
            ExternalAssetMapping.source_system == payload.source_system,
            ExternalAssetMapping.external_asset_id == payload.external_asset_id,
        )
    ).scalar_one_or_none()

    if existing:
        existing.asset_id = payload.asset_id
        existing.device_model = payload.device_model
        existing.notes = payload.notes
        existing.is_active = True
        mapping = existing
    else:
        mapping = ExternalAssetMapping(
            organization_id=organization_id,
            source_system=payload.source_system,
            external_asset_id=payload.external_asset_id,
            asset_id=payload.asset_id,
            device_model=payload.device_model,
            notes=payload.notes,
            is_active=True,
        )
        db.add(mapping)

    db.flush()
    audit_service.record_audit_event(
        db,
        organization_id=organization_id,
        user_id=None,
        action="telemetry.asset_mapping_created",
        entity_type="ExternalAssetMapping",
        entity_id=mapping.id,
        metadata={
            "source_system": mapping.source_system,
            "external_asset_id": mapping.external_asset_id,
            "asset_id": str(mapping.asset_id),
        },
    )
    return mapping


def list_asset_mappings(
    db: Session, *, organization_id: uuid.UUID, source_system: str | None = None
) -> list[ExternalAssetMapping]:
    stmt = select(ExternalAssetMapping).where(
        ExternalAssetMapping.organization_id == organization_id
    )
    if source_system:
        stmt = stmt.where(ExternalAssetMapping.source_system == source_system)
    return list(db.execute(stmt).scalars().all())


@dataclass(frozen=True)
class AssetResolution:
    """Outcome of mapping an external identifier to exactly one KOTA asset.

    RESOLVED   exactly one asset, by an explicit mapping, an asset id, or a UNIQUE exact
               serial/registration match inside the tenant.
    UNRESOLVED nothing matches (=> quarantine).
    AMBIGUOUS  more than one asset matches (=> quarantine; never guess)."""

    outcome: str
    asset: Asset | None = None
    method: str = ""
    candidates: int = 0


def resolve_asset_detailed(
    db: Session, *, organization_id: uuid.UUID, source_system: str, external_asset_id: str
) -> AssetResolution:
    """Deterministic, tenant-scoped asset resolution. Never fuzzy, never cross-tenant.

    Order: (1) explicit active mapping for (source_system, external id); (2) the external
    id IS an asset id in this tenant; (3) exact serial_number OR registration match among
    non-deleted assets of this tenant -- accepted only if it identifies exactly ONE asset.
    Soft-deleted assets never receive telemetry."""
    mapping = db.execute(
        select(ExternalAssetMapping).where(
            ExternalAssetMapping.organization_id == organization_id,
            ExternalAssetMapping.source_system == source_system,
            ExternalAssetMapping.external_asset_id == external_asset_id,
            ExternalAssetMapping.is_active.is_(True),
        )
    ).scalar_one_or_none()
    if mapping:
        asset = db.execute(
            select(Asset).where(
                Asset.id == mapping.asset_id,
                Asset.organization_id == organization_id,
                Asset.deleted_at.is_(None),
            )
        ).scalar_one_or_none()
        if asset is None:
            return AssetResolution("UNRESOLVED", None, "mapping", 0)
        return AssetResolution("RESOLVED", asset, "mapping", 1)

    try:
        as_uuid = uuid.UUID(str(external_asset_id))
    except (ValueError, TypeError):
        as_uuid = None
    if as_uuid is not None:
        asset = db.execute(
            select(Asset).where(
                Asset.id == as_uuid,
                Asset.organization_id == organization_id,
                Asset.deleted_at.is_(None),
            )
        ).scalar_one_or_none()
        if asset is not None:
            return AssetResolution("RESOLVED", asset, "asset_id", 1)

    matches = list(
        db.execute(
            select(Asset)
            .where(
                Asset.organization_id == organization_id,
                Asset.deleted_at.is_(None),
                (Asset.serial_number == external_asset_id) | (Asset.registration == external_asset_id),
            )
            .limit(3)
        ).scalars()
    )
    if len(matches) == 1:
        return AssetResolution("RESOLVED", matches[0], "exact_identifier", 1)
    if len(matches) > 1:
        return AssetResolution("AMBIGUOUS", None, "exact_identifier", len(matches))
    return AssetResolution("UNRESOLVED", None, "exact_identifier", 0)


def resolve_asset(
    db: Session, *, organization_id: uuid.UUID, source_system: str, external_asset_id: str
) -> Asset | None:
    """Backward-compatible wrapper: the asset only when resolution is unique and safe."""
    res = resolve_asset_detailed(
        db, organization_id=organization_id, source_system=source_system,
        external_asset_id=external_asset_id,
    )
    return res.asset if res.outcome == "RESOLVED" else None


def adapt_dji_flighthub_payload(payload: DJIFlightHubWebhookPayload) -> NormalizedTelemetryEvent:
    """Adapts a DJI FlightHub 2 webhook payload into a normalized KOTA telemetry event."""
    data = payload.data or {}
    device_sn = data.get("device_sn") or data.get("sn") or "UNKNOWN_DJI_SN"

    # Convert timestamp
    raw_ts = payload.timestamp
    if isinstance(raw_ts, int | float):
        # Milliseconds or seconds
        ts = raw_ts / 1000.0 if raw_ts > 100000000000 else raw_ts
        event_ts = datetime.fromtimestamp(ts, tz=UTC)
    elif isinstance(raw_ts, str):
        try:
            event_ts = datetime.fromisoformat(raw_ts.replace("Z", "+00:00"))
        except Exception:
            event_ts = datetime.now(UTC)
    else:
        event_ts = datetime.now(UTC)

    flight_payload: TelemetryFlightPayload | None = None
    battery_payload: TelemetryBatteryPayload | None = None
    readings: list[TelemetryReadingItem] = []

    event_type = payload.event
    if "flight" in event_type or "mission" in event_type or "flight_record" in event_type:
        duration_s = int(data.get("flight_duration") or data.get("duration") or 60)
        duration_minutes = max(1, int(round(duration_s / 60.0)))
        flight_payload = TelemetryFlightPayload(
            flight_number=data.get("flight_id") or f"DJI-{payload.bid[:8]}",
            duration_minutes=duration_minutes,
            cycles=int(data.get("cycles") or 1),
            origin=data.get("takeoff_location"),
            destination=data.get("landing_location"),
            flown_at=event_ts,
            notes=f"Ingested from DJI FlightHub 2 event {payload.bid}",
        )

    # Battery telemetry
    if "battery" in data or "battery_sn" in data or "battery" in event_type:
        b_data = data.get("battery") or data
        b_sn = b_data.get("battery_sn") or b_data.get("sn") or f"BAT-{device_sn}"
        battery_payload = TelemetryBatteryPayload(
            serial_number=b_sn,
            cycle_count=b_data.get("cycle_count") or b_data.get("cycles"),
            voltage_v=float(b_data["voltage"]) / 1000.0 if "voltage" in b_data else None,
            internal_resistance_mohm=float(b_data.get("internal_resistance") or 0.0) or None,
            temperature_c=float(b_data.get("temperature") or 0.0) or None,
            health_percent=b_data.get("health_percent") or b_data.get("soh"),
        )

    # Additional OSD/Sensor readings
    if "motor_temperature" in data:
        readings.append(
            TelemetryReadingItem(
                sensor_code=f"MOT_TEMP_{device_sn[:6]}",
                measurement_type="TEMPERATURE",
                value=float(data["motor_temperature"]),
                unit="CELSIUS",
            )
        )
    if "vibration_rms" in data:
        readings.append(
            TelemetryReadingItem(
                sensor_code=f"VIB_RMS_{device_sn[:6]}",
                measurement_type="VIBRATION",
                value=float(data["vibration_rms"]),
                unit="MM_S",
            )
        )

    return NormalizedTelemetryEvent(
        source_system="DJI_FLIGHTHUB",
        source_event_id=payload.bid,
        source_asset_id=device_sn,
        event_type=event_type,
        event_timestamp=event_ts,
        flight=flight_payload,
        battery=battery_payload,
        readings=readings,
        raw_metadata=data,
    )


# --- B8: timestamp quality gate -------------------------------------------------
MAX_FUTURE_SKEW = timedelta(minutes=5)
MIN_PLAUSIBLE_TIMESTAMP = datetime(2000, 1, 1, tzinfo=UTC)


def assess_event_timestamp(ts: datetime, *, now: datetime | None = None) -> str | None:
    """Reason string when the event time cannot be trusted, else None.

    Naive timestamps are rejected: an unlabelled zone silently shifts safety data by hours.
    Future events beyond clock skew and pre-2000 values are corrupt clocks, not telemetry."""
    now = now or datetime.now(UTC)
    if ts.tzinfo is None or ts.tzinfo.utcoffset(ts) is None:
        return "event_timestamp has no timezone"
    if ts > now + MAX_FUTURE_SKEW:
        return f"event_timestamp is in the future ({ts.isoformat()})"
    if ts < MIN_PLAUSIBLE_TIMESTAMP:
        return f"event_timestamp is implausibly old ({ts.isoformat()})"
    return None


def _record_or_update_log(
    db: Session, existing: TelemetryEventLog | None, **fields: Any
) -> TelemetryEventLog:
    """One log row per (org, source, event id) -- the DB enforces it. A retried event that was
    earlier QUARANTINED/REJECTED (e.g. replayed after the asset mapping was fixed) UPDATES its
    row instead of inserting a duplicate that would violate the unique constraint."""
    if existing is not None:
        for k, v in fields.items():
            setattr(existing, k, v)
        db.add(existing)
        db.flush()
        return existing
    row = TelemetryEventLog(**fields)
    db.add(row)
    db.flush()
    return row



def process_normalized_event(
    db: Session,
    *,
    organization_id: uuid.UUID,
    event: NormalizedTelemetryEvent,
    raw_payload_hash: str | None = None,
) -> TelemetryEventResult:
    """Processes a validated normalized telemetry event through authoritative domain services.

    Enforces:
    - Deterministic Idempotency: (org_id, source_system, source_event_id)
    - Double-counting protection on flight records
    - Tenant-isolated asset resolution
    - Provenance logging in telemetry_event_logs
    """
    idempotency_key = f"{organization_id}:{event.source_system}:{event.source_event_id}"
    payload_hash = (
        raw_payload_hash
        or hashlib.sha256(f"{event.source_system}:{event.source_event_id}".encode()).hexdigest()
    )

    # 1. Idempotency check
    existing_log = db.execute(
        select(TelemetryEventLog).where(
            TelemetryEventLog.organization_id == organization_id,
            TelemetryEventLog.source_system == event.source_system,
            TelemetryEventLog.source_event_id == event.source_event_id,
        )
    ).scalar_one_or_none()

    if existing_log and existing_log.processing_status in (
        TelemetryProcessingStatus.PROCESSED,
        TelemetryProcessingStatus.DUPLICATE,
    ):
        return TelemetryEventResult(
            source_event_id=event.source_event_id,
            status=TelemetryProcessingStatus.DUPLICATE,
            asset_id=existing_log.asset_id,
            flight_id=existing_log.flight_id,
            readings_count=existing_log.readings_count,
            message="Event already processed (idempotent ignore)",
        )

    # 1b. Timestamp quality gate (B8): corrupt clocks never enter operational analytics.
    ts_problem = assess_event_timestamp(event.event_timestamp)
    if ts_problem is not None:
        _record_or_update_log(
            db, existing_log,
            organization_id=organization_id, source_system=event.source_system,
            source_event_id=event.source_event_id, idempotency_key=idempotency_key,
            source_asset_id=event.source_asset_id, asset_id=None, event_type=event.event_type,
            event_timestamp=max(event.event_timestamp, MIN_PLAUSIBLE_TIMESTAMP)
            if event.event_timestamp.tzinfo else datetime.now(UTC),
            received_timestamp=datetime.now(UTC), payload_hash=payload_hash,
            processing_status=TelemetryProcessingStatus.REJECTED,
            rejection_reason=ts_problem, metadata_payload=event.raw_metadata,
        )
        return TelemetryEventResult(
            source_event_id=event.source_event_id,
            status=TelemetryProcessingStatus.REJECTED,
            message=ts_problem,
        )

    # 2. Asset Resolution (deterministic; ambiguous or unknown => quarantine, never guess)
    resolution = resolve_asset_detailed(
        db,
        organization_id=organization_id,
        source_system=event.source_system,
        external_asset_id=event.source_asset_id,
    )
    asset = resolution.asset

    if asset is None:
        reason = (
            f"Asset identifier '{event.source_asset_id}' is ambiguous: {resolution.candidates} "
            "assets match; add an explicit external mapping"
            if resolution.outcome == "AMBIGUOUS"
            else f"Asset '{event.source_asset_id}' cannot be resolved in tenant"
        )
        _record_or_update_log(
            db, existing_log,
            organization_id=organization_id, source_system=event.source_system,
            source_event_id=event.source_event_id, idempotency_key=idempotency_key,
            source_asset_id=event.source_asset_id, asset_id=None, event_type=event.event_type,
            event_timestamp=event.event_timestamp, received_timestamp=datetime.now(UTC),
            payload_hash=payload_hash,
            processing_status=TelemetryProcessingStatus.QUARANTINED,
            rejection_reason=reason, metadata_payload=event.raw_metadata,
        )
        return TelemetryEventResult(
            source_event_id=event.source_event_id,
            status=TelemetryProcessingStatus.QUARANTINED,
            message=(
                f"Ambiguous asset '{event.source_asset_id}'; event quarantined"
                if resolution.outcome == "AMBIGUOUS"
                else f"Unmatched asset '{event.source_asset_id}'; event quarantined"
            ),
        )

    flight_id: uuid.UUID | None = None
    readings_count = 0

    # 3. Domain Processing: Flight Operation
    if event.flight:
        flown_at = event.flight.flown_at or event.event_timestamp
        # No unique constraint can protect "one Flight per streaming session" (historical rows may
        # already contain duplicates), so resolution is serialised per (organization, asset) with a
        # transaction-scoped advisory lock: a second worker waits, then finds the first one's row.
        db.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:k, 0))"),
            {"k": f"flight:{organization_id}:{asset.id}"},
        )

        # Double-counting check: does a flight already exist with this source_row_id or exact match?
        existing_flight = db.execute(
            select(Flight).where(
                Flight.organization_id == organization_id,
                Flight.asset_id == asset.id,
                (Flight.source_row_id == event.source_event_id)
                | (
                    (Flight.flown_at == flown_at)
                    & (Flight.duration_minutes == event.flight.duration_minutes)
                    & (Flight.source == "TELEMETRY")
                )
                # A live stream re-sends the SAME flight (same number and start) with a
                # growing duration. That is one flight session, not a new Flight (and a
                # new cycle) per event.
                | (
                    (Flight.source == "TELEMETRY")
                    & (Flight.flight_number == event.flight.flight_number)
                    & (Flight.flown_at == flown_at)
                ),
            )
        ).scalars().first()

        if existing_flight:
            flight_id = existing_flight.id
            if event.flight.duration_minutes > existing_flight.duration_minutes:
                existing_flight.duration_minutes = event.flight.duration_minutes
                db.add(existing_flight)
                db.flush()
        else:
            flight = flight_service.record_flight(
                db,
                organization_id=organization_id,
                actor_user_id=None,
                asset_id=asset.id,
                flown_at=flown_at,
                duration_minutes=event.flight.duration_minutes,
                cycles=event.flight.cycles,
                flight_number=event.flight.flight_number,
                origin=event.flight.origin,
                destination=event.flight.destination,
                source="TELEMETRY",
                source_row_id=event.source_event_id,
                notes=event.flight.notes,
                commit=False,  # the event is one atomic unit; the caller commits
            )
            flight_id = flight.id

    # 4. Domain Processing: Battery & Components
    if event.battery:
        battery = db.execute(
            select(Battery).where(
                Battery.organization_id == organization_id,
                Battery.serial_number == event.battery.serial_number,
            )
        ).scalar_one_or_none()

        if battery:
            if (
                event.battery.cycle_count is not None
                and event.battery.cycle_count > battery.cycle_count
            ):
                battery.cycle_count = event.battery.cycle_count
            if event.battery.health_percent is not None:
                battery.health_percent = event.battery.health_percent
            if event.battery.voltage_v is not None:
                battery.voltage = int(round(event.battery.voltage_v * 1000))  # mV

    # 5. Domain Processing: HUMS Sensor Readings
    touched_sensor_ids: set[uuid.UUID] = set()
    for r_item in event.readings:
        # Check or create sensor
        sensor = db.execute(
            select(HUMSSensor).where(
                HUMSSensor.organization_id == organization_id,
                HUMSSensor.asset_id == asset.id,
                HUMSSensor.sensor_code == r_item.sensor_code,
            )
        ).scalar_one_or_none()

        if not sensor:
            try:
                # Two events for a brand-new sensor can arrive in parallel; the unique
                # (org, asset, sensor_code) constraint lets one create it and the other adopts it.
                with db.begin_nested():
                    sensor = HUMSSensor(
                        organization_id=organization_id,
                        asset_id=asset.id,
                        component_id=r_item.component_id,
                        sensor_code=r_item.sensor_code,
                        sensor_type=r_item.sensor_type,
                        measurement_type=r_item.measurement_type,
                        unit=r_item.unit,
                        source="TELEMETRY",
                        status="ACTIVE",
                    )
                    db.add(sensor)
                    db.flush()
            except IntegrityError:
                sensor = db.execute(
                    select(HUMSSensor).where(
                        HUMSSensor.organization_id == organization_id,
                        HUMSSensor.asset_id == asset.id,
                        HUMSSensor.sensor_code == r_item.sensor_code,
                    )
                ).scalar_one()

        reading = HUMSSensorReading(
            organization_id=organization_id,
            sensor_id=sensor.id,
            asset_id=asset.id,
            flight_id=flight_id,
            recorded_at=event.event_timestamp,
            value=r_item.value,
            unit=r_item.unit,
            data_quality=r_item.data_quality,
            source="TELEMETRY",
            ingestion_batch=event.source_event_id,
        )
        db.add(reading)
        readings_count += 1
        touched_sensor_ids.add(sensor.id)

    if touched_sensor_ids:
        db.flush()
        from app.services import hums_service

        for s_id in touched_sensor_ids:
            try:
                # SAVEPOINT: a failure here must not abort the ingestion transaction
                # (Postgres poisons the whole transaction after any statement error).
                with db.begin_nested():
                    hums_service.detect_and_record_exceedances(
                        db, organization_id=organization_id, sensor_id=s_id, user_id=None
                    )
            except Exception:
                # Non-fatal to ingestion, but never silent: an operator must be able to see it.
                log.exception(
                    "telemetry.exceedance_evaluation_failed",
                    organization_id=str(organization_id), sensor_id=str(s_id),
                )

    # 6. Record Telemetry Event Log (update the row of a previously quarantined/rejected retry)
    event_log = _record_or_update_log(
        db, existing_log,
        organization_id=organization_id, source_system=event.source_system,
        source_event_id=event.source_event_id, idempotency_key=idempotency_key,
        source_asset_id=event.source_asset_id, asset_id=asset.id, flight_id=flight_id,
        event_type=event.event_type, event_timestamp=event.event_timestamp,
        received_timestamp=datetime.now(UTC), payload_hash=payload_hash,
        processing_status=TelemetryProcessingStatus.PROCESSED,
        readings_count=readings_count, rejection_reason=None,
        metadata_payload=event.raw_metadata,
    )

    audit_service.record_audit_event(
        db,
        organization_id=organization_id,
        user_id=None,
        action="telemetry.event_processed",
        entity_type="TelemetryEventLog",
        entity_id=event_log.id,
        metadata={
            "source_system": event.source_system,
            "source_event_id": event.source_event_id,
            "asset_id": str(asset.id),
            "flight_id": str(flight_id) if flight_id else None,
            "readings_count": readings_count,
        },
    )

    return TelemetryEventResult(
        source_event_id=event.source_event_id,
        status=TelemetryProcessingStatus.PROCESSED,
        asset_id=asset.id,
        flight_id=flight_id,
        readings_count=readings_count,
        message="Telemetry event processed successfully",
    )


def ingest_telemetry_batch(
    db: Session, *, organization_id: uuid.UUID, request: TelemetryIngestRequest
) -> TelemetryIngestResponse:
    """Ingests a batch of normalized telemetry events."""
    results: list[TelemetryEventResult] = []
    processed = 0
    duplicate = 0
    rejected = 0

    for event in request.events:
        res = process_normalized_event(db, organization_id=organization_id, event=event)
        results.append(res)
        if res.status == TelemetryProcessingStatus.PROCESSED:
            processed += 1
        elif res.status == TelemetryProcessingStatus.DUPLICATE:
            duplicate += 1
        else:
            rejected += 1

    return TelemetryIngestResponse(
        total_received=len(request.events),
        processed_count=processed,
        duplicate_count=duplicate,
        rejected_count=rejected,
        results=results,
    )


def get_asset_telemetry_status(
    db: Session, *, organization_id: uuid.UUID, asset_id: uuid.UUID
) -> dict[str, Any]:
    """Returns telemetry status, last received timestamp, and recent event logs for an asset."""
    # Find mapping if any
    mapping = db.execute(
        select(ExternalAssetMapping).where(
            ExternalAssetMapping.organization_id == organization_id,
            ExternalAssetMapping.asset_id == asset_id,
            ExternalAssetMapping.is_active.is_(True),
        )
    ).scalar_one_or_none()

    # Query recent event logs for this asset
    logs = list(
        db.execute(
            select(TelemetryEventLog)
            .where(
                TelemetryEventLog.organization_id == organization_id,
                TelemetryEventLog.asset_id == asset_id,
            )
            .order_by(TelemetryEventLog.event_timestamp.desc())
            .limit(10)
        )
        .scalars()
        .all()
    )

    now = datetime.now(UTC)
    last_event = logs[0] if logs else None
    last_received = last_event.event_timestamp if last_event else None

    # Resolve configurable freshness policy
    policy = resolve_effective_freshness_policy(
        db, organization_id, asset_id=asset_id, source_system=mapping.source_system if mapping else (last_event.source_system if last_event else None)
    )

    if not last_received:
        telemetry_state = "NO_TELEMETRY_RECORDED"
    elif not policy["is_active"]:
        telemetry_state = "ACTIVE"
    elif (now - last_received) > timedelta(days=policy["warning_threshold_days"]):
        telemetry_state = "STALE"
    else:
        telemetry_state = "ACTIVE"

    return {
        "asset_id": str(asset_id),
        "source_system": mapping.source_system if mapping else (last_event.source_system if last_event else None),
        "external_asset_id": mapping.external_asset_id if mapping else (last_event.source_asset_id if last_event else None),
        "telemetry_state": telemetry_state,
        "freshness_warning_threshold_days": policy["warning_threshold_days"],
        "freshness_critical_threshold_days": policy["critical_threshold_days"],
        "last_received_at": last_received.isoformat() if last_received else None,
        "total_recent_events": len(logs),
        "recent_events": [
            {
                "id": str(log.id),
                "source_system": log.source_system,
                "source_event_id": log.source_event_id,
                "event_type": log.event_type,
                "status": log.processing_status,
                "timestamp": log.event_timestamp.isoformat(),
                "readings_count": log.readings_count,
            }
            for log in logs
        ],
    }


def resolve_effective_freshness_policy(
    db: Session,
    organization_id: uuid.UUID,
    asset_id: uuid.UUID | None = None,
    source_system: str | None = None,
) -> dict[str, Any]:
    """Resolves the most specific active telemetry freshness policy (Asset+Source -> Asset -> Tenant Default -> 7/14 standard)."""
    from app.models.telemetry import TelemetryFreshnessPolicy

    # 1. Exact match (Asset + Source)
    if asset_id and source_system:
        pol = db.execute(
            select(TelemetryFreshnessPolicy).where(
                TelemetryFreshnessPolicy.organization_id == organization_id,
                TelemetryFreshnessPolicy.asset_id == asset_id,
                TelemetryFreshnessPolicy.source_system == source_system,
            )
        ).scalar_one_or_none()
        if pol:
            return {
                "warning_threshold_days": pol.warning_threshold_days,
                "critical_threshold_days": pol.critical_threshold_days,
                "is_active": pol.is_active,
                "policy_id": pol.id,
            }

    # 2. Asset-specific match (any source)
    if asset_id:
        pol = db.execute(
            select(TelemetryFreshnessPolicy).where(
                TelemetryFreshnessPolicy.organization_id == organization_id,
                TelemetryFreshnessPolicy.asset_id == asset_id,
                TelemetryFreshnessPolicy.source_system.is_(None),
            )
        ).scalar_one_or_none()
        if pol:
            return {
                "warning_threshold_days": pol.warning_threshold_days,
                "critical_threshold_days": pol.critical_threshold_days,
                "is_active": pol.is_active,
                "policy_id": pol.id,
            }

    # 3. Source-specific match (tenant-wide)
    if source_system:
        pol = db.execute(
            select(TelemetryFreshnessPolicy).where(
                TelemetryFreshnessPolicy.organization_id == organization_id,
                TelemetryFreshnessPolicy.asset_id.is_(None),
                TelemetryFreshnessPolicy.source_system == source_system,
            )
        ).scalar_one_or_none()
        if pol:
            return {
                "warning_threshold_days": pol.warning_threshold_days,
                "critical_threshold_days": pol.critical_threshold_days,
                "is_active": pol.is_active,
                "policy_id": pol.id,
            }

    # 4. Tenant-wide default policy
    pol = db.execute(
        select(TelemetryFreshnessPolicy).where(
            TelemetryFreshnessPolicy.organization_id == organization_id,
            TelemetryFreshnessPolicy.asset_id.is_(None),
            TelemetryFreshnessPolicy.source_system.is_(None),
        )
    ).scalar_one_or_none()
    if pol:
        return {
            "warning_threshold_days": pol.warning_threshold_days,
            "critical_threshold_days": pol.critical_threshold_days,
            "is_active": pol.is_active,
            "policy_id": pol.id,
        }

    # 5. Default standard fallback
    return {
        "warning_threshold_days": 7,
        "critical_threshold_days": 14,
        "is_active": True,
        "policy_id": None,
    }


def list_freshness_policies(
    db: Session,
    organization_id: uuid.UUID,
) -> list[Any]:
    from app.models.telemetry import TelemetryFreshnessPolicy

    return list(
        db.execute(
            select(TelemetryFreshnessPolicy)
            .where(TelemetryFreshnessPolicy.organization_id == organization_id)
            .order_by(TelemetryFreshnessPolicy.created_at.desc())
        )
        .scalars()
        .all()
    )


def upsert_freshness_policy(
    db: Session,
    organization_id: uuid.UUID,
    payload: Any,
) -> Any:
    from app.models.telemetry import TelemetryFreshnessPolicy

    pol = db.execute(
        select(TelemetryFreshnessPolicy).where(
            TelemetryFreshnessPolicy.organization_id == organization_id,
            TelemetryFreshnessPolicy.asset_id == payload.asset_id,
            TelemetryFreshnessPolicy.source_system == payload.source_system,
        )
    ).scalar_one_or_none()

    if not pol:
        pol = TelemetryFreshnessPolicy(
            organization_id=organization_id,
            asset_id=payload.asset_id,
            source_system=payload.source_system,
            warning_threshold_days=payload.warning_threshold_days,
            critical_threshold_days=payload.critical_threshold_days,
            is_active=payload.is_active,
            description=payload.description,
        )
        db.add(pol)
    else:
        pol.warning_threshold_days = payload.warning_threshold_days
        pol.critical_threshold_days = payload.critical_threshold_days
        pol.is_active = payload.is_active
        if payload.description is not None:
            pol.description = payload.description

    db.flush()
    return pol




# ---------------------------------------------------------------- Phase C: read side
def _require_asset(db: Session, organization_id: uuid.UUID, asset_id: uuid.UUID) -> Asset:
    asset = db.execute(
        select(Asset).where(
            Asset.id == asset_id, Asset.organization_id == organization_id, Asset.deleted_at.is_(None)
        )
    ).scalar_one_or_none()
    if asset is None:
        raise NotFoundError("Asset not found")
    return asset


def get_latest_readings(
    db: Session, *, organization_id: uuid.UUID, asset_id: uuid.UUID, now: datetime | None = None
) -> dict[str, Any]:
    """Most recent reading of every sensor of an asset, with its age and quality.

    Nothing is inferred: a sensor that never reported has no row; `age_seconds` is measured from
    the reading's own timestamp so a stalled feed is visible as growing age, not as 'latest'."""
    _require_asset(db, organization_id, asset_id)
    now = now or datetime.now(UTC)
    latest_ts = (
        select(
            HUMSSensorReading.sensor_id,
            func.max(HUMSSensorReading.recorded_at).label("ts"),
        )
        .where(
            HUMSSensorReading.organization_id == organization_id,
            HUMSSensorReading.asset_id == asset_id,
        )
        .group_by(HUMSSensorReading.sensor_id)
        .subquery()
    )
    rows = db.execute(
        select(HUMSSensorReading, HUMSSensor)
        .join(latest_ts, (HUMSSensorReading.sensor_id == latest_ts.c.sensor_id)
              & (HUMSSensorReading.recorded_at == latest_ts.c.ts))
        .join(HUMSSensor, HUMSSensor.id == HUMSSensorReading.sensor_id)
        .where(
            HUMSSensorReading.organization_id == organization_id,
            HUMSSensorReading.asset_id == asset_id,
        )
        .order_by(HUMSSensor.sensor_code)
    ).all()
    seen: set[uuid.UUID] = set()
    items = []
    for reading, sensor in rows:  # ties on the same timestamp: keep one row per sensor
        if sensor.id in seen:
            continue
        seen.add(sensor.id)
        items.append(
            {
                "sensor_id": str(sensor.id),
                "sensor_code": sensor.sensor_code,
                "sensor_type": sensor.sensor_type,
                "measurement_type": sensor.measurement_type,
                "unit": reading.unit,
                "value": reading.value,
                "data_quality": reading.data_quality,
                "recorded_at": reading.recorded_at.isoformat(),
                "age_seconds": max(0, int((now - reading.recorded_at).total_seconds())),
                "flight_id": str(reading.flight_id) if reading.flight_id else None,
            }
        )
    return {"asset_id": str(asset_id), "as_of": now.isoformat(), "sensor_count": len(items), "sensors": items}


MAX_HISTORY_LIMIT = 1000


def get_reading_history(
    db: Session,
    *,
    organization_id: uuid.UUID,
    asset_id: uuid.UUID,
    sensor_code: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    limit: int = 200,
    offset: int = 0,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Bounded, tenant- and asset-scoped history (newest first). Default window: last 24 hours."""
    _require_asset(db, organization_id, asset_id)
    now = now or datetime.now(UTC)
    limit = max(1, min(limit, MAX_HISTORY_LIMIT))
    since = since or (now - timedelta(hours=24))
    conds = [
        HUMSSensorReading.organization_id == organization_id,
        HUMSSensorReading.asset_id == asset_id,
        HUMSSensorReading.recorded_at >= since,
    ]
    if until is not None:
        conds.append(HUMSSensorReading.recorded_at <= until)
    if sensor_code:
        conds.append(HUMSSensor.sensor_code == sensor_code)
    base = (
        select(HUMSSensorReading, HUMSSensor)
        .join(HUMSSensor, HUMSSensor.id == HUMSSensorReading.sensor_id)
        .where(*conds)
    )
    total = db.execute(
        select(func.count()).select_from(
            select(HUMSSensorReading.id)
            .join(HUMSSensor, HUMSSensor.id == HUMSSensorReading.sensor_id)
            .where(*conds)
            .subquery()
        )
    ).scalar_one()
    rows = db.execute(
        base.order_by(HUMSSensorReading.recorded_at.desc(), HUMSSensorReading.id).offset(offset).limit(limit)
    ).all()
    return {
        "asset_id": str(asset_id),
        "since": since.isoformat(),
        "until": until.isoformat() if until else None,
        "total": total,
        "limit": limit,
        "offset": offset,
        "items": [
            {
                "sensor_code": sensor.sensor_code,
                "measurement_type": sensor.measurement_type,
                "unit": reading.unit,
                "value": reading.value,
                "data_quality": reading.data_quality,
                "recorded_at": reading.recorded_at.isoformat(),
                "source": reading.source,
                "flight_id": str(reading.flight_id) if reading.flight_id else None,
            }
            for reading, sensor in rows
        ],
    }


def get_asset_flights(
    db: Session, *, organization_id: uuid.UUID, asset_id: uuid.UUID, limit: int = 50
) -> list[dict[str, Any]]:
    """Flight records that were created or extended by telemetry for this asset."""
    _require_asset(db, organization_id, asset_id)
    rows = db.execute(
        select(Flight)
        .where(
            Flight.organization_id == organization_id,
            Flight.asset_id == asset_id,
            Flight.source == "TELEMETRY",
        )
        .order_by(Flight.flown_at.desc())
        .limit(max(1, min(limit, 200)))
    ).scalars()
    return [
        {
            "flight_id": str(f.id),
            "flight_number": f.flight_number,
            "flown_at": f.flown_at.isoformat(),
            "duration_minutes": f.duration_minutes,
            "cycles": f.cycles,
            "status": f.status,
        }
        for f in rows
    ]
