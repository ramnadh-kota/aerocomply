import pytest
from datetime import datetime, timezone, timedelta
from uuid import uuid4
from sqlalchemy.orm import Session

from app.models.asset import Asset, AssetType
from app.models.flight import Flight
from app.models.organization import Organization
from app.models.user import User
from app.models.audit_event import AuditEvent
from app.services import flight_service, asset_service
from app.schemas.asset import AssetFlightCreateRequest


@pytest.fixture
def ops_org(db_session: Session) -> Organization:
    org = Organization(name=f"Ops Org {uuid4().hex[:6]}")
    db_session.add(org)
    db_session.commit()
    db_session.refresh(org)
    return org


@pytest.fixture
def ops_user(db_session: Session, ops_org: Organization) -> User:
    user = User(
        organization_id=ops_org.id,
        email=f"pilot-{uuid4().hex[:6]}@example.com",
        full_name="Captain Marvel",
        hashed_password="hashed_pwd",
        is_active=True,
        email_verified=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def ops_aircraft(db_session: Session, ops_org: Organization) -> Asset:
    asset = Asset(
        organization_id=ops_org.id,
        model="Cessna Caravan 208B",
        asset_type=AssetType.AIRCRAFT.value,
        status="ACTIVE",
        serial_number=f"SN-C208-{uuid4().hex[:6]}",
        registration=f"VT-CAR-{uuid4().hex[:4].upper()}",
    )
    db_session.add(asset)
    db_session.commit()
    db_session.refresh(asset)
    return asset


@pytest.fixture
def ops_drone(db_session: Session, ops_org: Organization) -> Asset:
    asset = Asset(
        organization_id=ops_org.id,
        model="DJI Matrice 350 RTK",
        asset_type=AssetType.DRONE.value,
        status="ACTIVE",
        serial_number=f"SN-M350-{uuid4().hex[:6]}",
        registration=f"VT-UAV-{uuid4().hex[:4].upper()}",
    )
    db_session.add(asset)
    db_session.commit()
    db_session.refresh(asset)
    return asset


def test_fixed_wing_operational_flight_recording(
    db_session: Session, ops_org: Organization, ops_user: User, ops_aircraft: Asset
):
    """M5-A: Customer records a detailed fixed-wing operational flight with origin, destination, times."""
    dep_time = datetime(2026, 3, 10, 8, 30, 0, tzinfo=timezone.utc)
    arr_time = datetime(2026, 3, 10, 10, 15, 0, tzinfo=timezone.utc)
    flown_at = dep_time

    flight = flight_service.record_flight(
        db_session,
        organization_id=ops_org.id,
        actor_user_id=ops_user.id,
        asset_id=ops_aircraft.id,
        flown_at=flown_at,
        duration_minutes=105,
        cycles=1,
        flight_number="KA-301",
        origin="VOMM",
        destination="VOBL",
        departure_time=dep_time,
        arrival_time=arr_time,
        mission_type="CARGO",
        status="COMPLETED",
        source="MANUAL",
        pilot_user_id=ops_user.id,
        notes="Scheduled regional cargo run",
        update_battery=False,
    )

    assert flight.id is not None
    assert flight.flight_number == "KA-301"
    assert flight.origin == "VOMM"
    assert flight.destination == "VOBL"
    assert flight.departure_time == dep_time
    assert flight.arrival_time == arr_time
    assert flight.duration_minutes == 105
    assert flight.cycles == 1
    assert flight.mission_type == "CARGO"
    assert flight.status == "COMPLETED"
    assert flight.source == "MANUAL"
    assert flight.pilot_user_id == ops_user.id

    # Verify audit event was generated
    audit = db_session.query(AuditEvent).filter(
        AuditEvent.organization_id == ops_org.id,
        AuditEvent.action == "flight.recorded",
        AuditEvent.entity_id == flight.id,
    ).first()
    assert audit is not None
    assert audit.event_metadata["flight_number"] == "KA-301"
    assert audit.event_metadata["duration_minutes"] == 105


def test_drone_operational_flight_recording(
    db_session: Session, ops_org: Organization, ops_user: User, ops_drone: Asset
):
    """M5-A: Drone flight record with survey mission metadata."""
    flown_at = datetime(2026, 3, 11, 14, 0, 0, tzinfo=timezone.utc)

    flight = flight_service.record_flight(
        db_session,
        organization_id=ops_org.id,
        actor_user_id=ops_user.id,
        asset_id=ops_drone.id,
        flown_at=flown_at,
        duration_minutes=35,
        cycles=1,
        flight_number="SRV-042",
        origin="PAD-A",
        destination="PAD-A",
        mission_type="SURVEY",
        status="COMPLETED",
        source="MANUAL",
        pilot_user_id=ops_user.id,
        notes="Pipeline corridor aerial inspection",
        update_battery=False,
    )

    assert flight.id is not None
    assert flight.mission_type == "SURVEY"
    assert flight.origin == "PAD-A"
    assert flight.duration_minutes == 35


def test_flight_history_filtering(
    db_session: Session, ops_org: Organization, ops_user: User, ops_aircraft: Asset
):
    """M5-A: History filtering by mission_type, status, pilot, and date range."""
    d1 = datetime(2026, 1, 15, tzinfo=timezone.utc)
    d2 = datetime(2026, 2, 20, tzinfo=timezone.utc)
    d3 = datetime(2026, 3, 25, tzinfo=timezone.utc)

    # 3 flights with differing mission types and dates
    flight_service.record_flight(
        db_session,
        organization_id=ops_org.id,
        actor_user_id=ops_user.id,
        asset_id=ops_aircraft.id,
        flown_at=d1,
        duration_minutes=60,
        cycles=1,
        flight_number="F-01",
        mission_type="TRAINING",
        status="COMPLETED",
        update_battery=False,
    )
    flight_service.record_flight(
        db_session,
        organization_id=ops_org.id,
        actor_user_id=ops_user.id,
        asset_id=ops_aircraft.id,
        flown_at=d2,
        duration_minutes=90,
        cycles=1,
        flight_number="F-02",
        mission_type="CARGO",
        status="COMPLETED",
        update_battery=False,
    )
    flight_service.record_flight(
        db_session,
        organization_id=ops_org.id,
        actor_user_id=ops_user.id,
        asset_id=ops_aircraft.id,
        flown_at=d3,
        duration_minutes=45,
        cycles=1,
        flight_number="F-03",
        mission_type="TRAINING",
        status="CANCELLED",
        update_battery=False,
    )

    # Filter by mission_type TRAINING
    training_flights, count = flight_service.list_flights_for_asset(
        db_session,
        organization_id=ops_org.id,
        asset_id=ops_aircraft.id,
        mission_type="TRAINING",
    )
    assert count == 2
    assert all(f.mission_type == "TRAINING" for f in training_flights)

    # Filter by status COMPLETED
    completed_flights, count = flight_service.list_flights_for_asset(
        db_session,
        organization_id=ops_org.id,
        asset_id=ops_aircraft.id,
        status="COMPLETED",
    )
    assert count == 2
    assert all(f.status == "COMPLETED" for f in completed_flights)

    # Filter by date range (February 2026 only)
    feb_flights, count = flight_service.list_flights_for_asset(
        db_session,
        organization_id=ops_org.id,
        asset_id=ops_aircraft.id,
        date_from=datetime(2026, 2, 1, tzinfo=timezone.utc),
        date_to=datetime(2026, 2, 28, tzinfo=timezone.utc),
    )
    assert count == 1
    assert feb_flights[0].flight_number == "F-02"
