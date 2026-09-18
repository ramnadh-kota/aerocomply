"""M17.3D: concurrency test for battery cycle-count accounting during
concurrent flight recording.

Same rationale as test_installation_concurrency.py (M17.2D): the shared
`db_session`/`client` fixtures wrap every test in one connection/
transaction that's rolled back at teardown, so two "concurrent" callers
sharing it can't reproduce a real cross-transaction race. This test uses
two independent, actually-committing connections instead, and cleans up
everything it creates in a `finally` block.

flight_service.record_flight increments the currently-attached battery's
cycle_count. Two flights recorded at genuinely the same time must both be
reflected in the final cycle_count -- a naive Python-side
`battery.cycle_count += cycles` read-modify-write would lose one
increment under concurrent commits (classic lost-update race), since
SQLAlchemy would UPDATE with a literal value computed from a stale read
rather than an atomic database-side increment.
"""

import threading
from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.models.asset import Asset, AssetType
from app.models.battery import Battery
from app.models.flight import Flight
from app.models.organization import Organization
from app.services import flight_service
from tests.integration.conftest import TEST_DATABASE_URL


@pytest.fixture
def concurrency_engine():
    engine = create_engine(TEST_DATABASE_URL, future=True)
    yield engine
    engine.dispose()


def test_two_concurrent_flights_both_increment_battery_cycle_count(concurrency_engine):
    Session = sessionmaker(bind=concurrency_engine, future=True)

    setup = Session()
    org = Organization(name="Flight Concurrency Test Org")
    setup.add(org)
    setup.flush()
    asset = Asset(
        organization_id=org.id,
        asset_type=AssetType.DRONE.value,
        registration="DRN-FLT-CONC-1",
        status="ACTIVE",
    )
    setup.add(asset)
    setup.flush()
    battery = Battery(
        organization_id=org.id, asset_id=asset.id, serial_number="BATT-FLT-CONC-1"
    )
    setup.add(battery)
    setup.commit()
    org_id, asset_id, battery_id = org.id, asset.id, battery.id
    setup.close()

    results: dict[str, BaseException | None] = {}
    ready = threading.Barrier(2, timeout=10)

    def attempt(name: str, cycles: int):
        session = Session()
        try:
            ready.wait()
            flight_service.record_flight(
                session,
                organization_id=org_id,
                actor_user_id=None,
                asset_id=asset_id,
                flown_at=datetime.now(UTC),
                duration_minutes=10,
                cycles=cycles,
                pilot_user_id=None,
                notes=None,
            )
            results[name] = None
        except BaseException as exc:  # noqa: BLE001 -- captured for cross-thread assertion
            session.rollback()
            results[name] = exc
        finally:
            session.close()

    t1 = threading.Thread(target=attempt, args=("t1", 3))
    t2 = threading.Thread(target=attempt, args=("t2", 4))
    t1.start()
    t2.start()
    t1.join(timeout=15)
    t2.join(timeout=15)

    try:
        outcomes = list(results.values())
        assert len(outcomes) == 2, "both threads must finish and record an outcome"
        assert all(o is None for o in outcomes), f"unexpected errors: {outcomes}"

        verify = Session()
        db_battery = verify.get(Battery, battery_id)
        flights = list(
            verify.execute(select(Flight).where(Flight.asset_id == asset_id)).scalars().all()
        )
        verify.close()

        assert len(flights) == 2
        expected_total = sum(f.cycles for f in flights)
        assert expected_total == 7  # 3 + 4, sanity-check the fixture itself
        # The real invariant: neither concurrent increment was lost.
        assert db_battery.cycle_count == expected_total
    finally:
        cleanup = Session()
        cleanup.execute(Flight.__table__.delete().where(Flight.asset_id == asset_id))
        cleanup.execute(Battery.__table__.delete().where(Battery.id == battery_id))
        cleanup.execute(Asset.__table__.delete().where(Asset.id == asset_id))
        cleanup.execute(Organization.__table__.delete().where(Organization.id == org_id))
        cleanup.commit()
        cleanup.close()
