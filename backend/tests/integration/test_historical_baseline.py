import pytest
from datetime import datetime, timezone, timedelta
from uuid import uuid4
from sqlalchemy.orm import Session

from app.models.asset import Asset, AssetType
from app.models.asset_baseline import AssetHistoricalBaseline
from app.models.flight import Flight
from app.models.organization import Organization
from app.models.user import User
from app.services import flight_service, asset_service


@pytest.fixture
def baseline_org(db_session: Session) -> Organization:
    org = Organization(name=f"Baseline Org {uuid4().hex[:6]}")
    db_session.add(org)
    db_session.commit()
    db_session.refresh(org)
    return org


@pytest.fixture
def baseline_user(db_session: Session, baseline_org: Organization) -> User:
    user = User(
        organization_id=baseline_org.id,
        email=f"operator-{uuid4().hex[:6]}@example.com",
        full_name="Test Operator",
        hashed_password="hashed_pwd",
        is_active=True,
        email_verified=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def fixed_wing_asset(db_session: Session, baseline_org: Organization) -> Asset:
    asset = Asset(
        organization_id=baseline_org.id,
        model="SkyCourier N100KA",
        asset_type=AssetType.AIRCRAFT.value,
        status="ACTIVE",
        serial_number=f"SN-{uuid4().hex[:8]}",
        registration=f"VT-M5-{uuid4().hex[:4].upper()}",
    )
    db_session.add(asset)
    db_session.commit()
    db_session.refresh(asset)
    return asset


def test_baseline_only_accounting(db_session: Session, baseline_org: Organization, baseline_user: User, fixed_wing_asset: Asset):
    """Scenario 1: Asset has baseline only -> utilization equals baseline counters."""
    effective_date = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    baseline = flight_service.create_asset_baseline(
        db_session,
        organization_id=baseline_org.id,
        actor_user_id=baseline_user.id,
        asset_id=fixed_wing_asset.id,
        flight_hours=4281.6,
        flight_cycles=2194,
        effective_at=effective_date,
        source="Legacy Maintenance System",
        evidence_reference="DOC-HIST-2026-001",
    )
    assert baseline.flight_hours == 4281.6
    assert baseline.flight_cycles == 2194
    assert baseline.is_active is True

    util = flight_service.get_utilization(db_session, organization_id=baseline_org.id, asset_id=fixed_wing_asset.id)
    # total_minutes = 4281.6 * 60 = 256896 minutes -> 4281.6 hours
    assert util["total_cycles"] == 2194
    assert util["baseline_hours"] == 4281.6
    assert util["baseline_cycles"] == 2194
    assert util["baseline_effective_at"] is not None
    assert abs(util["total_minutes"] / 60.0 - 4281.6) < 0.01


def test_baseline_plus_post_baseline_flights(db_session: Session, baseline_org: Organization, baseline_user: User, fixed_wing_asset: Asset):
    """Scenario 2: Baseline + flights occurring after baseline effective date."""
    effective_date = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    flight_service.create_asset_baseline(
        db_session,
        organization_id=baseline_org.id,
        actor_user_id=baseline_user.id,
        asset_id=fixed_wing_asset.id,
        flight_hours=1000.0,
        flight_cycles=500,
        effective_at=effective_date,
        source="Logbook 2025 Audit",
    )

    # Add 2 post-baseline flights
    flight_service.record_flight(
        db_session,
        organization_id=baseline_org.id,
        actor_user_id=baseline_user.id,
        asset_id=fixed_wing_asset.id,
        flown_at=effective_date + timedelta(days=5),
        duration_minutes=120,
        cycles=1,
        flight_number="KA-101",
        update_battery=False,
    )
    flight_service.record_flight(
        db_session,
        organization_id=baseline_org.id,
        actor_user_id=baseline_user.id,
        asset_id=fixed_wing_asset.id,
        flown_at=effective_date + timedelta(days=10),
        duration_minutes=90,
        cycles=2,
        flight_number="KA-102",
        update_battery=False,
    )

    util = flight_service.get_utilization(db_session, organization_id=baseline_org.id, asset_id=fixed_wing_asset.id)
    # 1000.0 + (120/60 = 2.0) + (90/60 = 1.5) = 1003.5 hours = 60210 minutes
    # 500 + 1 + 2 = 503 cycles
    assert util["total_cycles"] == 503
    assert util["total_minutes"] == (1000 * 60) + 120 + 90


def test_historical_flights_before_baseline_not_double_counted(db_session: Session, baseline_org: Organization, baseline_user: User, fixed_wing_asset: Asset):
    """Scenario 3: Historical flights occurring BEFORE baseline effective date are recorded for traceability but not added to total hours."""
    effective_date = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)

    # Pre-baseline flight in 2025
    pre_flight = flight_service.record_flight(
        db_session,
        organization_id=baseline_org.id,
        actor_user_id=baseline_user.id,
        asset_id=fixed_wing_asset.id,
        flown_at=datetime(2025, 6, 15, 12, 0, 0, tzinfo=timezone.utc),
        duration_minutes=300,  # 5 hours
        cycles=3,
        flight_number="HIST-2025-01",
        update_battery=False,
    )
    assert pre_flight.id is not None

    # Baseline established on 2026-01-01 incorporating past history
    flight_service.create_asset_baseline(
        db_session,
        organization_id=baseline_org.id,
        actor_user_id=baseline_user.id,
        asset_id=fixed_wing_asset.id,
        flight_hours=500.0,
        flight_cycles=250,
        effective_at=effective_date,
        source="Audit Signoff",
    )

    # Post-baseline flight in 2026
    flight_service.record_flight(
        db_session,
        organization_id=baseline_org.id,
        actor_user_id=baseline_user.id,
        asset_id=fixed_wing_asset.id,
        flown_at=datetime(2026, 2, 1, 10, 0, 0, tzinfo=timezone.utc),
        duration_minutes=60,  # 1 hour
        cycles=1,
        flight_number="KA-201",
        update_battery=False,
    )

    util = flight_service.get_utilization(db_session, organization_id=baseline_org.id, asset_id=fixed_wing_asset.id)
    # Total hours must be 500 (baseline) + 1 (post-baseline) = 501.0, NOT 500 + 5 + 1 = 506.0!
    assert util["total_minutes"] == (500 * 60) + 60
    assert util["total_cycles"] == 251
    assert util["baseline_hours"] == 500.0

    # Ensure pre-baseline flight is still present in full history list for traceability
    flights, total = flight_service.list_flights_for_asset(db_session, organization_id=baseline_org.id, asset_id=fixed_wing_asset.id)
    assert total == 2
    assert len(flights) == 2
    flight_numbers = {f.flight_number for f in flights}
    assert "HIST-2025-01" in flight_numbers
    assert "KA-201" in flight_numbers


def test_baseline_replacement_deactivates_previous(db_session: Session, baseline_org: Organization, baseline_user: User, fixed_wing_asset: Asset):
    """Scenario 4: Updating or creating a new baseline deactivates the older one."""
    eff1 = datetime(2025, 1, 1, tzinfo=timezone.utc)
    b1 = flight_service.create_asset_baseline(
        db_session,
        organization_id=baseline_org.id,
        actor_user_id=baseline_user.id,
        asset_id=fixed_wing_asset.id,
        flight_hours=2000.0,
        flight_cycles=1000,
        effective_at=eff1,
        source="V1",
    )
    assert b1.is_active is True

    eff2 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    b2 = flight_service.create_asset_baseline(
        db_session,
        organization_id=baseline_org.id,
        actor_user_id=baseline_user.id,
        asset_id=fixed_wing_asset.id,
        flight_hours=2500.0,
        flight_cycles=1200,
        effective_at=eff2,
        source="V2 Reconciliation",
    )
    db_session.refresh(b1)
    assert b1.is_active is False
    assert b2.is_active is True

    active_baseline = flight_service.get_asset_baseline(db_session, organization_id=baseline_org.id, asset_id=fixed_wing_asset.id)
    assert active_baseline.id == b2.id
    assert active_baseline.flight_hours == 2500.0

    all_baselines = flight_service.list_asset_baselines(db_session, organization_id=baseline_org.id, asset_id=fixed_wing_asset.id)
    assert len(all_baselines) == 2
