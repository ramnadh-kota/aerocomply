"""Real concurrency: several INDEPENDENT database sessions race on committed data.

The normal `db_session` fixture wraps one connection in a rolled-back transaction, so it cannot
express a race. These tests open their own sessions (one per thread), release them together with a
barrier and assert that the database -- not luck -- decides the outcome. Data is committed (unique
names) and deliberately left behind: audit_events is append-only, so an organization that has
audit history cannot be deleted; the whole schema is dropped at the end of the pytest session.
"""
from __future__ import annotations

import threading
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import ConflictError
from app.models.billing import Invoice
from app.models.hums import HUMSSensorReading
from app.models.organization import Organization
from app.models.plan import Plan
from app.models.product_catalog import ProductSuite
from app.models.subscription import Subscription
from app.models.telemetry import ExternalAssetMapping, TelemetryEventLog
from app.schemas.telemetry import NormalizedTelemetryEvent, TelemetryReadingItem
from app.services import billing_service as bs
from app.services import drone_service, subscription_service, telemetry_service

WORKERS = 6


def _race(engine, work):
    """Run `work(session, i)` in WORKERS threads at once; return list of ('ok', value) | ('err', exc)."""
    barrier = threading.Barrier(WORKERS)
    out: list = [None] * WORKERS

    def run(i: int) -> None:
        with Session(engine) as s:
            try:
                barrier.wait(timeout=10)
                out[i] = ("ok", work(s, i))
                s.commit()
            except Exception as exc:  # noqa: BLE001
                s.rollback()
                out[i] = ("err", exc)

    threads = [threading.Thread(target=run, args=(i,)) for i in range(WORKERS)]
    [t.start() for t in threads]
    [t.join(timeout=30) for t in threads]
    assert all(o is not None for o in out), "a worker hung"
    return out


@pytest.fixture
def committed_org(engine):
    with Session(engine) as s:
        org = Organization(name=f"race-{uuid.uuid4().hex[:8]}")
        s.add(org)
        suite = s.execute(select(ProductSuite).where(ProductSuite.code == "DRONE_UAV")).scalar_one()
        plan = Plan(suite_id=suite.id, code=f"R-{uuid.uuid4().hex[:8]}", name="Race", is_active=True)
        s.add(plan)
        s.commit()
        return org.id, plan.id


def test_concurrent_subscription_creation_yields_exactly_one_current_subscription(engine, committed_org):
    org_id, plan_id = committed_org

    def work(s, i):
        return subscription_service.create_subscription(
            s, actor_user_id=None, organization_id=org_id, plan_id=plan_id, status="ACTIVE",
            starts_at=datetime.now(UTC) - timedelta(days=1), commit=False).id

    results = _race(engine, work)
    winners = [r for r in results if r[0] == "ok"]
    losers = [r for r in results if r[0] == "err"]
    assert len(winners) == 1, results
    assert all(isinstance(e[1], ConflictError) and e[1].code == "ambiguous_subscription_state" for e in losers), losers
    with Session(engine) as s:
        assert s.scalar(select(func.count(Subscription.id)).where(Subscription.organization_id == org_id)) == 1


def test_concurrent_invoice_generation_creates_one_invoice_per_period(engine, committed_org):
    org_id, plan_id = committed_org
    with Session(engine) as s:
        bs.set_plan_price(s, actor_user_id=None, actor_organization_id=org_id, plan_id=plan_id,
                          currency="INR", billing_interval="MONTHLY", amount_minor=100)
        sub = subscription_service.create_subscription(
            s, actor_user_id=None, organization_id=org_id, plan_id=plan_id, status="ACTIVE",
            starts_at=datetime.now(UTC), commit=True)
        sub_id = sub.id
    period = datetime(2026, 6, 1, tzinfo=UTC)

    results = _race(engine, lambda s, i: bs.generate_invoice(
        s, actor_user_id=None, subscription_id=sub_id, currency="INR", billing_interval="MONTHLY",
        period_start=period, commit=False).id)
    ids = {r[1] for r in results if r[0] == "ok"}
    assert all(r[0] == "ok" for r in results), results          # nobody errors: losers adopt the winner's row
    assert len(ids) == 1
    with Session(engine) as s:
        assert s.scalar(select(func.count(Invoice.id)).where(Invoice.subscription_id == sub_id)) == 1


def test_concurrent_duplicate_event_is_processed_once(engine, committed_org):
    org_id, _ = committed_org
    with Session(engine) as s:
        drone = drone_service.create_drone(s, organization_id=org_id, actor_user_id=None, registration="RACE-D1",
                                           manufacturer=None, model=None, serial_number=None, facility_id=None)
        telemetry_service.create_asset_mapping(
            s, organization_id=org_id,
            payload=__import__("app.schemas.telemetry", fromlist=["ExternalAssetMappingCreate"]).ExternalAssetMappingCreate(
                source_system="RACE", external_asset_id="RACE-D1", asset_id=drone.id))
        s.commit()
    now = datetime.now(UTC)
    event = NormalizedTelemetryEvent(
        source_system="RACE", source_event_id="evt-race-1", source_asset_id="RACE-D1", event_type="PING",
        event_timestamp=now, readings=[TelemetryReadingItem(sensor_code="V", measurement_type="vibration", value=1.5, unit="mm/s")])

    from app.services import acquisition_service  # noqa: F401  (import-time sanity)

    def work(s, i):
        try:
            with s.begin_nested():
                return telemetry_service.process_normalized_event(s, organization_id=org_id, event=event).status
        except Exception as exc:  # IntegrityError from the lost race is what acquisition_service converts to DUPLICATE
            from sqlalchemy.exc import IntegrityError
            if isinstance(exc, IntegrityError) and "uq_telemetry_event_org_source_eventid" in str(exc.orig):
                return "DUPLICATE"
            raise

    results = _race(engine, work)
    assert all(r[0] == "ok" for r in results), results
    statuses = [r[1] for r in results]
    assert statuses.count("PROCESSED") == 1 and statuses.count("DUPLICATE") == WORKERS - 1, statuses
    with Session(engine) as s:
        assert s.scalar(select(func.count(TelemetryEventLog.id)).where(TelemetryEventLog.organization_id == org_id)) == 1
        assert s.scalar(select(func.count(HUMSSensorReading.id)).where(HUMSSensorReading.organization_id == org_id)) == 1


def test_concurrent_drone_registration_gives_one_asset_and_structured_conflicts(engine, committed_org):
    org_id, _ = committed_org
    results = _race(engine, lambda s, i: drone_service.create_drone(
        s, organization_id=org_id, actor_user_id=None, registration="RACE-REG",
        manufacturer=None, model=None, serial_number=None, facility_id=None).id)
    ok = [r for r in results if r[0] == "ok"]
    errs = [r[1] for r in results if r[0] == "err"]
    assert len(ok) == 1, results
    assert all(isinstance(e, ConflictError) and e.code == "duplicate_registration" for e in errs), errs
    from app.models.asset import Asset

    with Session(engine) as s:
        assert s.scalar(select(func.count(Asset.id)).where(Asset.organization_id == org_id, Asset.registration == "RACE-REG")) == 1


def test_parallel_events_of_one_streaming_flight_create_one_flight_and_one_sensor(engine, committed_org):
    """Different events, same flight session and same NEW sensor, processed at the same instant."""
    from app.models.flight import Flight
    from app.models.hums import HUMSSensor
    from app.schemas.telemetry import ExternalAssetMappingCreate, TelemetryFlightPayload

    org_id, _ = committed_org
    with Session(engine) as s:
        drone = drone_service.create_drone(s, organization_id=org_id, actor_user_id=None, registration="RACE-F1",
                                           manufacturer=None, model=None, serial_number=None, facility_id=None)
        telemetry_service.create_asset_mapping(s, organization_id=org_id, payload=ExternalAssetMappingCreate(
            source_system="RACE", external_asset_id="RACE-F1", asset_id=drone.id))
        s.commit()
        drone_id = drone.id
    start = datetime.now(UTC) - timedelta(minutes=10)

    def work(s, i):
        ev = NormalizedTelemetryEvent(
            source_system="RACE", source_event_id=f"flt-{i}", source_asset_id="RACE-F1", event_type="PING",
            event_timestamp=datetime.now(UTC) + timedelta(microseconds=i),
            flight=TelemetryFlightPayload(flight_number="FLT-RACE", duration_minutes=i + 1, cycles=1, flown_at=start),
            readings=[TelemetryReadingItem(sensor_code="NEWSENSOR", measurement_type="vibration", value=1.0 + i, unit="mm/s")])
        return telemetry_service.process_normalized_event(s, organization_id=org_id, event=ev).status

    results = _race(engine, work)
    assert all(r[0] == "ok" and r[1] == "PROCESSED" for r in results), results
    with Session(engine) as s:
        assert s.scalar(select(func.count(Flight.id)).where(Flight.asset_id == drone_id)) == 1
        assert s.scalar(select(func.count(HUMSSensor.id)).where(HUMSSensor.asset_id == drone_id)) == 1
        assert s.scalar(select(func.count(HUMSSensorReading.id)).where(HUMSSensorReading.asset_id == drone_id)) == WORKERS
        assert s.scalar(select(Flight.duration_minutes).where(Flight.asset_id == drone_id)) == WORKERS   # grew to the max
