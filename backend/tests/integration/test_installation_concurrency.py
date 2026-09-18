"""M17.2D: concurrency/database-integrity test for the partial unique
index added in 0033_installation_history.py (WHERE removed_at IS NULL),
which is the actual invariant preventing two simultaneously open
installation records for the same battery/component.

This deliberately does NOT use the `db_session`/`client` fixtures from
conftest.py: those share one connection wrapped in a single transaction
that is rolled back at teardown, so two "concurrent" callers against that
one connection would never produce a real cross-transaction race -- they
would just serialize through the same uncommitted transaction. A genuine
race requires two independent connections that can each begin their own
transaction and actually commit, so the second writer really does hit the
index at the database level rather than at the app's own pre-check.

Because this test's writes are real commits (not covered by the fixture's
auto-rollback), it cleans up everything it creates in a `finally` block,
including on assertion failure.
"""

import threading
from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.models.asset import Asset, AssetType
from app.models.battery import Battery
from app.models.installation_history import BatteryInstallation
from app.models.organization import Organization
from tests.integration.conftest import TEST_DATABASE_URL


@pytest.fixture
def concurrency_engine():
    engine = create_engine(TEST_DATABASE_URL, future=True)
    yield engine
    engine.dispose()


def test_two_concurrent_open_installations_for_the_same_battery_are_rejected(concurrency_engine):
    Session = sessionmaker(bind=concurrency_engine, future=True)

    setup = Session()
    org = Organization(name="Concurrency Test Org")
    setup.add(org)
    setup.flush()
    asset = Asset(
        organization_id=org.id,
        asset_type=AssetType.DRONE.value,
        registration="DRN-CONC-1",
        status="ACTIVE",
    )
    setup.add(asset)
    setup.flush()
    battery = Battery(organization_id=org.id, serial_number="BATT-CONC-1")
    setup.add(battery)
    setup.commit()
    org_id, asset_id, battery_id = org.id, asset.id, battery.id
    setup.close()

    results: dict[str, BaseException | None] = {}
    ready = threading.Barrier(2, timeout=10)

    def attempt(name: str):
        session = Session()
        try:
            # Confirms no open installation exists yet -- same check
            # installation_service.install_battery performs -- then both
            # threads wait at the barrier so neither commits until both
            # have passed this check, maximizing the race window.
            existing = session.execute(
                select(BatteryInstallation).where(
                    BatteryInstallation.battery_id == battery_id,
                    BatteryInstallation.removed_at.is_(None),
                )
            ).scalar_one_or_none()
            assert existing is None

            ready.wait()

            session.add(
                BatteryInstallation(
                    organization_id=org_id,
                    battery_id=battery_id,
                    asset_id=asset_id,
                    installed_at=datetime.now(UTC),
                )
            )
            session.commit()
            results[name] = None
        except BaseException as exc:  # noqa: BLE001 -- captured for cross-thread assertion
            session.rollback()
            results[name] = exc
        finally:
            session.close()

    t1 = threading.Thread(target=attempt, args=("t1",))
    t2 = threading.Thread(target=attempt, args=("t2",))
    t1.start()
    t2.start()
    t1.join(timeout=15)
    t2.join(timeout=15)

    try:
        outcomes = list(results.values())
        assert len(outcomes) == 2, "both threads must finish and record an outcome"
        successes = [o for o in outcomes if o is None]
        failures = [o for o in outcomes if o is not None]
        # The invariant under test: never both succeed. Exactly one writer
        # wins; the other is rejected by the partial unique index at the
        # database level (IntegrityError), not merely by app-level logic
        # that could itself race.
        assert len(successes) == 1, f"expected exactly one success, got {len(successes)}"
        assert len(failures) == 1, f"expected exactly one rejection, got {len(failures)}"
        assert isinstance(failures[0], IntegrityError)

        verify = Session()
        open_rows = list(
            verify.execute(
                select(BatteryInstallation).where(
                    BatteryInstallation.battery_id == battery_id,
                    BatteryInstallation.removed_at.is_(None),
                )
            )
            .scalars()
            .all()
        )
        verify.close()
        assert len(open_rows) == 1
    finally:
        cleanup = Session()
        cleanup.execute(
            BatteryInstallation.__table__.delete().where(
                BatteryInstallation.battery_id == battery_id
            )
        )
        cleanup.execute(Battery.__table__.delete().where(Battery.id == battery_id))
        cleanup.execute(Asset.__table__.delete().where(Asset.id == asset_id))
        cleanup.execute(Organization.__table__.delete().where(Organization.id == org_id))
        cleanup.commit()
        cleanup.close()
