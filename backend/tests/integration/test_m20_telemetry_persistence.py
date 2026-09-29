"""M20: telemetry persistence -- identity, idempotency, corruption, tenant separation.

Exercises telemetry_service.process_normalized_event against the real database.
"""
from __future__ import annotations

import datetime as dt
import math
import uuid

import pytest
from pydantic import ValidationError
from sqlalchemy import func, select

from app.models.flight import Flight
from app.models.hums import HUMSSensorReading
from app.models.organization import Organization
from app.models.telemetry import TelemetryEventLog
from app.schemas.telemetry import (
    ExternalAssetMappingCreate,
    NormalizedTelemetryEvent,
    TelemetryFlightPayload,
    TelemetryReadingItem,
)
from app.services import drone_service, telemetry_service

SRC = "KOTA_MAVLINK_GATEWAY"


def _drone(db, org_id, registration):
    return drone_service.create_drone(
        db, organization_id=org_id, actor_user_id=None, registration=registration,
        manufacturer="DJI", model="M300", serial_number=None, facility_id=None,
    )


def _tenant(db, ext_id: str):
    org = Organization(name=f"Telem Org {uuid.uuid4().hex[:6]}")
    db.add(org)
    db.flush()
    drone = _drone(db, org.id, f"T-{uuid.uuid4().hex[:6]}")
    telemetry_service.create_asset_mapping(
        db, organization_id=org.id,
        payload=ExternalAssetMappingCreate(source_system=SRC, external_asset_id=ext_id, asset_id=drone.id),
    )
    db.flush()
    return org, drone


def _event(ext_id: str, event_id: str, *, minutes: int = 1, flown_at=None, readings=None,
           flight_number="FLT-1", ts=None):
    now = ts or dt.datetime.now(dt.UTC)
    return NormalizedTelemetryEvent(
        source_system=SRC, source_event_id=event_id, source_asset_id=ext_id,
        event_type="REALTIME_TELEMETRY", event_timestamp=now,
        flight=TelemetryFlightPayload(
            flight_number=flight_number, duration_minutes=minutes, cycles=1,
            flown_at=flown_at or now - dt.timedelta(minutes=minutes),
        ),
        readings=readings or [],
    )


def _vib(v: float) -> TelemetryReadingItem:
    return TelemetryReadingItem(sensor_code="VIB1", sensor_type="VIBRATION",
                                measurement_type="vibration", value=v, unit="mm/s")


def test_duplicate_event_is_idempotent_and_adds_no_readings(db_session):
    org, _ = _tenant(db_session, "EXT-1")
    ev = _event("EXT-1", "evt-1", readings=[_vib(1.0)])
    first = telemetry_service.process_normalized_event(db_session, organization_id=org.id, event=ev)
    again = telemetry_service.process_normalized_event(db_session, organization_id=org.id, event=ev)
    assert first.status == "PROCESSED" and again.status == "DUPLICATE"
    n = db_session.scalar(select(func.count(HUMSSensorReading.id)).where(HUMSSensorReading.organization_id == org.id))
    assert n == 1


def test_unknown_vehicle_is_quarantined_not_attached_to_any_asset(db_session):
    org, drone = _tenant(db_session, "EXT-1")
    res = telemetry_service.process_normalized_event(
        db_session, organization_id=org.id, event=_event("UNKNOWN-SYSID-9", "evt-x", readings=[_vib(9.9)]))
    assert res.status == "QUARANTINED"
    assert db_session.scalar(select(func.count(HUMSSensorReading.id)).where(HUMSSensorReading.organization_id == org.id)) == 0
    log = db_session.execute(select(TelemetryEventLog).where(TelemetryEventLog.source_event_id == "evt-x")).scalar_one()
    assert log.asset_id is None


def test_same_external_id_in_two_tenants_never_crosses(db_session):
    org_a, drone_a = _tenant(db_session, "SHARED-EXT")
    org_b, drone_b = _tenant(db_session, "SHARED-EXT")
    telemetry_service.process_normalized_event(
        db_session, organization_id=org_a.id, event=_event("SHARED-EXT", "ea", readings=[_vib(1.0)]))
    rows_b = db_session.scalar(select(func.count(HUMSSensorReading.id)).where(HUMSSensorReading.organization_id == org_b.id))
    assert rows_b == 0
    r = db_session.execute(select(HUMSSensorReading).where(HUMSSensorReading.organization_id == org_a.id)).scalar_one()
    assert r.asset_id == drone_a.id and r.asset_id != drone_b.id


def test_two_vehicles_same_tenant_readings_stay_on_their_own_asset(db_session):
    org, drone1 = _tenant(db_session, "UAV-1")
    drone2 = _drone(db_session, org.id, "T-second")
    telemetry_service.create_asset_mapping(
        db_session, organization_id=org.id,
        payload=ExternalAssetMappingCreate(source_system=SRC, external_asset_id="UAV-2", asset_id=drone2.id))
    telemetry_service.process_normalized_event(db_session, organization_id=org.id, event=_event("UAV-1", "e1", readings=[_vib(1.0)]))
    telemetry_service.process_normalized_event(db_session, organization_id=org.id, event=_event("UAV-2", "e2", readings=[_vib(2.0)]))
    by_asset = {r.asset_id: r.value for r in db_session.execute(select(HUMSSensorReading).where(HUMSSensorReading.organization_id == org.id)).scalars()}
    assert by_asset == {drone1.id: 1.0, drone2.id: 2.0}


def test_continuous_stream_is_one_flight_not_one_per_minute(db_session):
    """A streaming session sends the SAME flight (same number / start) with a growing
    duration. It must update that flight, not create a new Flight per minute (which
    inflated flight counts and, summed, flight hours quadratically)."""
    org, drone = _tenant(db_session, "EXT-1")
    start = dt.datetime.now(dt.UTC) - dt.timedelta(minutes=10)
    for i, minutes in enumerate((1, 2, 3, 4, 5)):
        telemetry_service.process_normalized_event(
            db_session, organization_id=org.id,
            event=_event("EXT-1", f"s-{i}", minutes=minutes, flown_at=start, flight_number="FLT-STREAM"))
    flights = db_session.execute(select(Flight).where(Flight.organization_id == org.id, Flight.asset_id == drone.id)).scalars().all()
    assert len(flights) == 1, f"{len(flights)} flights created for one stream"
    assert flights[0].duration_minutes == 5


def test_distinct_flights_with_same_number_but_different_start_stay_distinct(db_session):
    org, drone = _tenant(db_session, "EXT-1")
    t0 = dt.datetime.now(dt.UTC) - dt.timedelta(days=2)
    for i in range(2):
        telemetry_service.process_normalized_event(
            db_session, organization_id=org.id,
            event=_event("EXT-1", f"d-{i}", minutes=30, flown_at=t0 + dt.timedelta(days=i), flight_number="FLT-DAILY"))
    n = db_session.scalar(select(func.count(Flight.id)).where(Flight.organization_id == org.id, Flight.asset_id == drone.id))
    assert n == 2


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_reading_values_are_rejected(bad):
    """NaN/Infinity poison every downstream statistic (baselines, RMS, RUL). Python's
    json parser accepts the literals NaN/Infinity, so the schema must refuse them."""
    with pytest.raises(ValidationError):
        TelemetryReadingItem(sensor_code="V", measurement_type="vibration", value=bad, unit="mm/s")


def test_non_finite_value_over_http_is_422_not_stored(client, db_session):
    from app.core.security import create_access_token
    from tests.integration.conftest import grant_features

    org, drone = _tenant(db_session, "EXT-HTTP")
    grant_features(db_session, org.id, "flight_telemetry")
    tok = create_access_token(uuid.uuid4(), org.id, ["ORG_ADMIN"], "x@example.com", "X", True)
    body = ('{"source_system":"%s","source_event_id":"nan-1","source_asset_id":"EXT-HTTP",'
            '"event_type":"REALTIME_TELEMETRY","event_timestamp":"2026-01-01T00:00:00Z",'
            '"readings":[{"sensor_code":"V","measurement_type":"vibration","value":NaN,"unit":"mm/s"}]}') % SRC
    r = client.post("/api/v1/telemetry/ingest", content=body,
                    headers={"Authorization": f"Bearer {tok}", "Content-Type": "application/json"})
    assert r.status_code == 422, r.text
    assert db_session.scalar(select(func.count(HUMSSensorReading.id)).where(HUMSSensorReading.organization_id == org.id)) == 0
