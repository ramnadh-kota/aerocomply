"""Phase 1A: generic Asset foundation tests.

Covers:
  - Asset / AircraftDetail model creation and constraints
  - migration 0027's Aircraft -> Asset backfill, exercised against a
    dedicated, throwaway database created and dropped by this file (see
    `_isolated_migration_database` below) -- never against the shared
    session-scoped TEST_DATABASE_URL every other test in this suite relies
    on, including its post-backfill integrity check
  - tenant isolation on the new read-only /assets API
  - Aircraft creation now dual-writing Asset + AircraftDetail transactionally
    (Phase 1A hardening -- this closed what was previously a documented gap;
    see docs/ARCHITECTURE_ASSET_FOUNDATION.md), including that a failed
    creation (duplicate registration) leaves no orphaned Asset/AircraftDetail
  - POST/GET /aircraft response-shape backward compatibility

M17.3.2 test-isolation fix: TestMigration0027Backfill previously ran live
`alembic downgrade`/`upgrade` DDL directly against the shared
TEST_DATABASE_URL (the same database every other test's `db_session`
fixture reads/writes). Two failures resulted when run as part of the full
suite (never when this class ran alone against a freshly-migrated database):
(1) an assertion that assumed exactly one `aircraft` row existed globally,
which is only true immediately after a fresh migration and false once any
other row has ever been committed to that long-lived database by anything
outside the per-test rolled-back transaction; (2) downgrading/dropping and
recreating `assets`/`aircraft_details`/`aircraft.asset_id` out from under a
database other tests' fixtures assume is stable. Both are now impossible:
this class creates its own throwaway Postgres database per test, migrates
only that database, and drops it afterward -- it can no longer observe or
affect any row or schema state outside itself, regardless of what else has
ever run against TEST_DATABASE_URL.
"""

import os
import uuid
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, select, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import sessionmaker

from app.core.deps import get_db_session
from app.core.errors import ConflictError, NotFoundError
from app.main import app
from app.models.aircraft import Aircraft
from app.models.aircraft_detail import AircraftDetail
from app.models.asset import Asset, AssetType
from app.models.audit_event import AuditEvent
from app.models.organization import Organization
from app.schemas.aircraft import AircraftCreateRequest
from app.services import aircraft_service, asset_service

BACKEND_DIR = Path(__file__).resolve().parents[2]
TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+psycopg://aerocomply:aerocomply@localhost:5432/aerocomply_test",
)


def _alembic_config_for(database_url: str) -> Config:
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", database_url)
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    return cfg


@contextmanager
def _isolated_migration_database():
    """Create a throwaway Postgres database (same server/credentials as
    TEST_DATABASE_URL), yield its own connection URL, then drop it -- always,
    even on failure. CREATE DATABASE/DROP DATABASE cannot run inside a
    transaction block, so the maintenance connection used for both is opened
    with isolation_level="AUTOCOMMIT" (this is the standard, documented way
    to run either statement via SQLAlchemy/psycopg; it never touches
    TEST_DATABASE_URL's own database or connection).
    """
    parts = urlsplit(TEST_DATABASE_URL)
    db_name = f"aerocomply_migration_test_{uuid.uuid4().hex[:12]}"
    maintenance_url = urlunsplit(parts._replace(path="/postgres"))
    isolated_url = urlunsplit(parts._replace(path=f"/{db_name}"))

    maintenance_engine = create_engine(maintenance_url, future=True, isolation_level="AUTOCOMMIT")
    try:
        with maintenance_engine.connect() as conn:
            conn.execute(text(f'CREATE DATABASE "{db_name}"'))
        try:
            yield isolated_url
        finally:
            with maintenance_engine.connect() as conn:
                # Terminate any lingering connections (e.g. a disposed but
                # not-yet-closed engine) before DROP DATABASE, which refuses
                # to run while any session is still connected.
                conn.execute(
                    text(
                        "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                        "WHERE datname = :db AND pid <> pg_backend_pid()"
                    ),
                    {"db": db_name},
                )
                conn.execute(text(f'DROP DATABASE IF EXISTS "{db_name}"'))
    finally:
        maintenance_engine.dispose()


# ---------------------------------------------------------------------------
# Model-level tests (use the shared db_session/engine fixtures from conftest)
# ---------------------------------------------------------------------------


def _make_org(db_session):
    org = Organization(name="Test Org")
    db_session.add(org)
    db_session.commit()
    db_session.refresh(org)
    return org


class TestAssetModel:
    def test_create_asset(self, db_session):
        org = _make_org(db_session)
        asset = Asset(
            organization_id=org.id,
            asset_type=AssetType.AIRCRAFT.value,
            registration="N100FD",
            status="ACTIVE",
        )
        db_session.add(asset)
        db_session.commit()
        db_session.refresh(asset)

        assert asset.id is not None
        assert asset.manufacturer is None
        assert asset.model is None
        assert asset.serial_number is None
        assert asset.acquired_at is None
        assert asset.retired_at is None

    def test_registration_unique_per_organization(self, db_session):
        org = _make_org(db_session)
        db_session.add(
            Asset(organization_id=org.id, asset_type=AssetType.AIRCRAFT.value, registration="N1DUP")
        )
        db_session.commit()

        db_session.add(
            Asset(organization_id=org.id, asset_type=AssetType.AIRCRAFT.value, registration="N1DUP")
        )
        with pytest.raises(IntegrityError):
            db_session.commit()
        db_session.rollback()

    def test_registration_may_repeat_across_organizations(self, db_session):
        org_a = _make_org(db_session)
        org_b = _make_org(db_session)

        db_session.add(
            Asset(
                organization_id=org_a.id, asset_type=AssetType.AIRCRAFT.value, registration="N1SAME"
            )
        )
        db_session.add(
            Asset(
                organization_id=org_b.id, asset_type=AssetType.AIRCRAFT.value, registration="N1SAME"
            )
        )
        db_session.commit()  # must not raise

    def test_multiple_assets_without_registration_allowed(self, db_session):
        # NULL is not equal to NULL under a standard SQL UNIQUE constraint,
        # so two registration-less assets in the same org are legal.
        org = _make_org(db_session)
        db_session.add(Asset(organization_id=org.id, asset_type=AssetType.DRONE.value))
        db_session.add(Asset(organization_id=org.id, asset_type=AssetType.DRONE.value))
        db_session.commit()  # must not raise


class TestAircraftDetailModel:
    def test_create_aircraft_detail(self, db_session):
        org = _make_org(db_session)
        asset = Asset(
            organization_id=org.id, asset_type=AssetType.AIRCRAFT.value, registration="N2AD"
        )
        db_session.add(asset)
        db_session.commit()
        db_session.refresh(asset)

        detail = AircraftDetail(asset_id=asset.id, msn="MSN-AD1", aircraft_type="B737-800")
        db_session.add(detail)
        db_session.commit()
        db_session.refresh(detail)

        assert detail.asset_id == asset.id

    def test_asset_id_must_reference_existing_asset(self, db_session):
        detail = AircraftDetail(asset_id=uuid.uuid4(), msn="MSN-X", aircraft_type="A320")
        db_session.add(detail)
        with pytest.raises(IntegrityError):
            db_session.commit()
        db_session.rollback()


class TestAircraftAssetIdColumn:
    def test_asset_id_is_unique(self, db_session):
        org = _make_org(db_session)
        asset = Asset(
            organization_id=org.id, asset_type=AssetType.AIRCRAFT.value, registration="N4UQ"
        )
        db_session.add(asset)
        db_session.commit()
        db_session.refresh(asset)

        aircraft_a = Aircraft(
            organization_id=org.id,
            registration="N4UQ-A",
            msn="M1",
            aircraft_type="A320",
            asset_id=asset.id,
        )
        db_session.add(aircraft_a)
        db_session.commit()

        aircraft_b = Aircraft(
            organization_id=org.id,
            registration="N4UQ-B",
            msn="M2",
            aircraft_type="A320",
            asset_id=asset.id,
        )
        db_session.add(aircraft_b)
        with pytest.raises(IntegrityError):
            db_session.commit()
        db_session.rollback()


# ---------------------------------------------------------------------------
# Aircraft creation dual-write (Phase 1A hardening: closes the "new Aircraft
# has no Asset" gap flagged in the Phase 1A review -- create_aircraft now
# creates Asset + AircraftDetail + Aircraft together, transactionally).
# ---------------------------------------------------------------------------


class TestAircraftCreationDualWrite:
    def test_create_aircraft_creates_matching_asset_and_detail(self, db_session):
        org = _make_org(db_session)
        aircraft = aircraft_service.create_aircraft(
            db_session,
            organization_id=org.id,
            payload=AircraftCreateRequest(
                registration="N20DW", msn="MSN-DW1", aircraft_type="A321"
            ),
        )

        assert aircraft.asset_id is not None

        asset = db_session.get(Asset, aircraft.asset_id)
        assert asset is not None
        assert asset.asset_type == AssetType.AIRCRAFT.value
        assert asset.organization_id == org.id
        assert asset.registration == "N20DW"
        assert asset.status == aircraft.status

        detail = db_session.get(AircraftDetail, aircraft.asset_id)
        assert detail is not None
        assert detail.msn == "MSN-DW1"
        assert detail.aircraft_type == "A321"

        # Round-trip through the read-only Asset service too, since that's
        # the actual consumer-facing path for this data.
        via_service = asset_service.get_aircraft_asset(
            db_session, organization_id=org.id, aircraft_id=aircraft.id
        )
        assert via_service.id == aircraft.asset_id

    def test_create_aircraft_via_api_creates_asset(self, client):
        tokens = _register(client, "Dual Write Tenant", "admin@dualwrite.example.com")
        auth = _auth(tokens["access_token"])

        aircraft_resp = client.post(
            "/api/v1/aircraft",
            json={
                "registration": "N21DW",
                "msn": "MSN-DW2",
                "aircraft_type": "B737-800",
                "status": "ACTIVE",
            },
            headers=auth,
        )
        assert aircraft_resp.status_code == 201, aircraft_resp.text
        aircraft_body = aircraft_resp.json()

        asset_resp = client.get("/api/v1/assets", headers=auth)
        assert asset_resp.status_code == 200
        matching = [a for a in asset_resp.json() if a["registration"] == "N21DW"]
        assert len(matching) == 1
        assert matching[0]["asset_type"] == "AIRCRAFT"
        assert matching[0]["organization_id"] == aircraft_body["organization_id"]

    def test_duplicate_registration_still_rejected(self, db_session):
        """Preserves the pre-existing duplicate-registration behavior
        (ConflictError / 409) through the new three-table write path."""
        org = _make_org(db_session)
        aircraft_service.create_aircraft(
            db_session,
            organization_id=org.id,
            payload=AircraftCreateRequest(registration="N22DUP", msn="MSN-1", aircraft_type="A320"),
        )

        with pytest.raises(ConflictError):
            aircraft_service.create_aircraft(
                db_session,
                organization_id=org.id,
                payload=AircraftCreateRequest(
                    registration="N22DUP", msn="MSN-2", aircraft_type="A320"
                ),
            )

    def test_duplicate_registration_leaves_no_orphaned_asset_or_detail(self):
        """Transaction rollback test: forces a REAL failure (the existing
        duplicate-registration uniqueness constraint, not a mock/monkeypatch)
        during the Asset+AircraftDetail+Aircraft write, and proves none of
        the three tables retain a row from the failed second attempt --
        only the first, successful aircraft's trio survives.

        Uses its own dedicated engine/session (real, independently
        committed transactions -- the same production semantics
        `app.core.deps.get_db_session` provides per request), NOT the
        shared `db_session` fixture. `db_session` binds one Session to one
        pre-opened Connection/Transaction for the whole test specifically
        so the fixture's own final rollback can undo everything at once;
        under that model, ANY explicit `db.rollback()` a service calls
        mid-test (as create_aircraft's duplicate-registration handling
        does) rolls back that ONE shared transaction in its entirety --
        including an earlier, already-"successful" db.commit() in the same
        test, since neither call is a truly independent transaction. That
        is correct, intentional behavior for `db_session` (verified
        directly: even a fresh, separate connection sees zero rows after
        such a rollback, proving the first commit was never independently
        durable) -- it is simply the wrong tool for a test that needs to
        prove one operation's data survives a LATER, separate operation's
        rollback, which is exactly what this test needs to demonstrate.
        """
        engine = create_engine(TEST_DATABASE_URL, future=True)
        SessionLocal = sessionmaker(bind=engine, future=True)
        org_id = uuid.uuid4()
        try:
            session = SessionLocal()
            try:
                session.add(Organization(id=org_id, name="Dup Orphan Org"))
                session.commit()

                aircraft_service.create_aircraft(
                    session,
                    organization_id=org_id,
                    payload=AircraftCreateRequest(
                        registration="N23RB", msn="MSN-1", aircraft_type="A320"
                    ),
                )

                with pytest.raises(ConflictError):
                    aircraft_service.create_aircraft(
                        session,
                        organization_id=org_id,
                        payload=AircraftCreateRequest(
                            registration="N23RB", msn="MSN-2", aircraft_type="A320"
                        ),
                    )

                aircraft_rows = (
                    session.execute(select(Aircraft).where(Aircraft.organization_id == org_id))
                    .scalars()
                    .all()
                )
                asset_rows = (
                    session.execute(select(Asset).where(Asset.organization_id == org_id))
                    .scalars()
                    .all()
                )
                assert len(aircraft_rows) == 1
                assert len(asset_rows) == 1

                detail = session.get(AircraftDetail, asset_rows[0].id)
                assert detail is not None
                assert detail.msn == "MSN-1"  # the first (successful) attempt's data
            finally:
                session.close()
        finally:
            # Real, durable commits happened above (this test deliberately
            # does not use the rolled-back-per-test `db_session` fixture --
            # see docstring), so this cleanup is required, matching the
            # established precedent in test_inventory_concurrency.py for
            # tests that need genuinely independent transactions.
            cleanup_engine = create_engine(TEST_DATABASE_URL, future=True)
            try:
                with cleanup_engine.begin() as conn:
                    conn.execute(
                        text(
                            "DELETE FROM aircraft_details WHERE asset_id IN "
                            "(SELECT id FROM assets WHERE organization_id = :org_id)"
                        ),
                        {"org_id": org_id},
                    )
                    conn.execute(
                        text("DELETE FROM aircraft WHERE organization_id = :org_id"),
                        {"org_id": org_id},
                    )
                    conn.execute(
                        text("DELETE FROM assets WHERE organization_id = :org_id"),
                        {"org_id": org_id},
                    )
                    conn.execute(
                        text("DELETE FROM organizations WHERE id = :org_id"), {"org_id": org_id}
                    )
            finally:
                cleanup_engine.dispose()
            engine.dispose()

    def test_duplicate_registration_via_api_returns_409(self, client):
        tokens = _register(client, "Dup Reg Tenant", "admin@dupreg.example.com")
        auth = _auth(tokens["access_token"])

        payload = {
            "registration": "N24DUP",
            "msn": "MSN-1",
            "aircraft_type": "A320",
            "status": "ACTIVE",
        }
        first = client.post("/api/v1/aircraft", json=payload, headers=auth)
        assert first.status_code == 201

        second = client.post(
            "/api/v1/aircraft",
            json={**payload, "msn": "MSN-2"},
            headers=auth,
        )
        assert second.status_code == 409


class TestAircraftApiResponseBackwardCompatibility:
    """Confirms POST/GET /aircraft's response shape is unchanged by the
    dual-write hardening -- asset_id must not leak into a response schema
    that never declared it."""

    def test_create_response_shape_unchanged(self, client):
        tokens = _register(client, "Compat Tenant", "admin@compat.example.com")
        auth = _auth(tokens["access_token"])

        resp = client.post(
            "/api/v1/aircraft",
            json={
                "registration": "N25CM",
                "msn": "MSN-CM1",
                "aircraft_type": "A320",
                "status": "ACTIVE",
            },
            headers=auth,
        )
        assert resp.status_code == 201
        body = resp.json()
        assert set(body.keys()) == {
            "id",
            "organization_id",
            "registration",
            "msn",
            "aircraft_type",
            "status",
            "created_at",
        }
        assert "asset_id" not in body

    def test_get_response_shape_unchanged(self, client):
        tokens = _register(client, "Compat Tenant Get", "admin@compat-get.example.com")
        auth = _auth(tokens["access_token"])

        created = client.post(
            "/api/v1/aircraft",
            json={
                "registration": "N26CM",
                "msn": "MSN-CM2",
                "aircraft_type": "A320",
                "status": "ACTIVE",
            },
            headers=auth,
        ).json()

        resp = client.get(f"/api/v1/aircraft/{created['id']}", headers=auth)
        assert resp.status_code == 200
        body = resp.json()
        assert set(body.keys()) == {
            "id",
            "organization_id",
            "registration",
            "msn",
            "aircraft_type",
            "status",
            "created_at",
        }
        assert "asset_id" not in body


class TestAircraftCreationAudit:
    """Slice B: aircraft creation previously emitted no audit event at all,
    unlike every other asset-creation path (asset_service.create_asset,
    drone_service.create_drone). Recorded against entity_type="Asset" /
    the backing Asset's id -- same convention those other paths use -- so
    an Aircraft-typed asset's audit trail lives in one place regardless of
    which endpoint created it."""

    def test_create_aircraft_emits_audit_event(self, client, db_session):
        tokens = _register(client, "Audit Tenant", "admin@audit-aircraft.example.com")
        auth = _auth(tokens["access_token"])

        resp = client.post(
            "/api/v1/aircraft",
            json={
                "registration": "N30AU",
                "msn": "MSN-AU1",
                "aircraft_type": "A320",
                "status": "ACTIVE",
                "manufacturer": "Airbus",
            },
            headers=auth,
        )
        assert resp.status_code == 201, resp.text
        aircraft_body = resp.json()

        assets = client.get("/api/v1/assets", headers=auth).json()
        matching = [a for a in assets if a["registration"] == "N30AU"]
        assert len(matching) == 1
        asset_id = matching[0]["id"]
        # The manufacturer entered at creation now round-trips onto the
        # backing Asset row (previously always null for aircraft-created
        # assets).
        assert matching[0]["manufacturer"] == "Airbus"
        assert matching[0]["model"] == "A320"
        assert matching[0]["serial_number"] == "MSN-AU1"

        events = (
            db_session.execute(
                select(AuditEvent).where(
                    AuditEvent.entity_type == "Asset",
                    AuditEvent.entity_id == uuid.UUID(asset_id),
                    AuditEvent.action == "aircraft.created",
                )
            )
            .scalars()
            .all()
        )
        assert len(events) == 1
        assert events[0].event_metadata["aircraft_id"] == aircraft_body["id"]


class TestAircraftUpdate:
    def test_patch_updates_aircraft_and_backing_asset(self, client, db_session):
        tokens = _register(client, "Edit Tenant", "admin@edit-aircraft.example.com")
        auth = _auth(tokens["access_token"])

        created = client.post(
            "/api/v1/aircraft",
            json={
                "registration": "N31ED",
                "msn": "MSN-ED1",
                "aircraft_type": "A320",
                "status": "ACTIVE",
                "manufacturer": "Airbus",
            },
            headers=auth,
        ).json()

        patch_resp = client.patch(
            f"/api/v1/aircraft/{created['id']}",
            json={"status": "MAINTENANCE", "msn": "MSN-ED1-REV2", "manufacturer": "Airbus SE"},
            headers=auth,
        )
        assert patch_resp.status_code == 200, patch_resp.text
        updated = patch_resp.json()
        assert updated["status"] == "MAINTENANCE"
        assert updated["msn"] == "MSN-ED1-REV2"
        # registration is immutable -- not accepted by AircraftUpdateRequest
        assert updated["registration"] == "N31ED"

        # Refetch (simulates navigation/refresh) -- persistence survives.
        refetched = client.get(f"/api/v1/aircraft/{created['id']}", headers=auth).json()
        assert refetched["status"] == "MAINTENANCE"
        assert refetched["msn"] == "MSN-ED1-REV2"

        # The backing Asset row (and AircraftDetail) stay in sync.
        assets = client.get("/api/v1/assets", headers=auth).json()
        matching = [a for a in assets if a["registration"] == "N31ED"]
        assert len(matching) == 1
        assert matching[0]["status"] == "MAINTENANCE"
        assert matching[0]["manufacturer"] == "Airbus SE"
        assert matching[0]["serial_number"] == "MSN-ED1-REV2"

        detail = db_session.get(AircraftDetail, uuid.UUID(matching[0]["id"]))
        assert detail is not None
        assert detail.msn == "MSN-ED1-REV2"

    def test_patch_emits_audit_event(self, client, db_session):
        tokens = _register(client, "Edit Audit Tenant", "admin@edit-audit.example.com")
        auth = _auth(tokens["access_token"])

        created = client.post(
            "/api/v1/aircraft",
            json={"registration": "N32ED", "msn": "MSN-ED2", "aircraft_type": "A320"},
            headers=auth,
        ).json()

        client.patch(
            f"/api/v1/aircraft/{created['id']}",
            json={"status": "GROUNDED"},
            headers=auth,
        )

        events = (
            db_session.execute(
                select(AuditEvent).where(
                    AuditEvent.action == "aircraft.updated",
                    AuditEvent.entity_type == "Asset",
                )
            )
            .scalars()
            .all()
        )
        assert len(events) == 1
        assert events[0].event_metadata == {"status": "GROUNDED"}

    def test_patch_cross_tenant_returns_404(self, client):
        tokens_a = _register(client, "Edit Tenant A", "admin@edit-a.example.com")
        tokens_b = _register(client, "Edit Tenant B", "admin@edit-b.example.com")
        auth_a, auth_b = _auth(tokens_a["access_token"]), _auth(tokens_b["access_token"])

        created = client.post(
            "/api/v1/aircraft",
            json={"registration": "N33XT", "msn": "MSN-XT1", "aircraft_type": "A320"},
            headers=auth_a,
        ).json()

        resp = client.patch(
            f"/api/v1/aircraft/{created['id']}",
            json={"status": "GROUNDED"},
            headers=auth_b,
        )
        assert resp.status_code == 404

        # Confirms org A's aircraft was never touched.
        unchanged = client.get(f"/api/v1/aircraft/{created['id']}", headers=auth_a).json()
        assert unchanged["status"] == "ACTIVE"

    def test_patch_no_op_when_no_fields_supplied(self, client):
        tokens = _register(client, "Edit Noop Tenant", "admin@edit-noop.example.com")
        auth = _auth(tokens["access_token"])
        created = client.post(
            "/api/v1/aircraft",
            json={"registration": "N34NP", "msn": "MSN-NP1", "aircraft_type": "A320"},
            headers=auth,
        ).json()

        resp = client.patch(f"/api/v1/aircraft/{created['id']}", json={}, headers=auth)
        assert resp.status_code == 200
        assert resp.json()["status"] == "ACTIVE"


class TestAircraftRegistryConsistency:
    """Slice B objective: Add Aircraft -> Aircraft record -> AircraftDetail
    -> Asset registry -> Aircraft list -> Aircraft detail must all agree,
    and survive a refresh (re-GET)."""

    def test_created_aircraft_visible_in_both_registries_after_refresh(self, client):
        tokens = _register(client, "Registry Tenant", "admin@registry.example.com")
        auth = _auth(tokens["access_token"])

        created = client.post(
            "/api/v1/aircraft",
            json={
                "registration": "N35RG",
                "msn": "MSN-RG1",
                "aircraft_type": "B737-800",
                "manufacturer": "Boeing",
            },
            headers=auth,
        ).json()

        # Appears in the Aircraft list.
        list_resp = client.get("/api/v1/aircraft", headers=auth).json()
        assert any(a["id"] == created["id"] for a in list_resp)

        # Appears in the universal Asset registry.
        assets_resp = client.get("/api/v1/assets", headers=auth).json()
        matching = [a for a in assets_resp if a["registration"] == "N35RG"]
        assert len(matching) == 1
        assert matching[0]["asset_type"] == "AIRCRAFT"

        # Detail route resolves ("refresh" = re-GET with a fresh request).
        detail_1 = client.get(f"/api/v1/aircraft/{created['id']}", headers=auth).json()
        detail_2 = client.get(f"/api/v1/aircraft/{created['id']}", headers=auth).json()
        assert detail_1 == detail_2
        assert detail_1["registration"] == "N35RG"


class TestGenericAssetFlightRecording:
    """Slice B: POST /assets/{id}/flights (asset_service.record_asset_flight)
    previously had zero test coverage. Covers the common-foundation path for
    non-drone assets (Aircraft/Helicopter), the DRONE guard added in this
    slice, and that utilization (SUM over flights -- Slice A's confirmed
    source of truth) reflects what was recorded."""

    def test_record_flight_and_utilization_for_aircraft(self, client):
        tokens = _register(client, "Flight Tenant", "admin@flight.example.com")
        auth = _auth(tokens["access_token"])

        asset = client.post(
            "/api/v1/assets",
            json={"asset_type": "AIRCRAFT", "registration": "N40FL"},
            headers=auth,
        ).json()

        for minutes, cycles in [(60, 1), (90, 2)]:
            resp = client.post(
                f"/api/v1/assets/{asset['id']}/flights",
                json={
                    "flown_at": "2025-01-01T00:00:00Z",
                    "duration_minutes": minutes,
                    "cycles": cycles,
                },
                headers=auth,
            )
            assert resp.status_code == 201, resp.text

        util = client.get(f"/api/v1/assets/{asset['id']}/utilization", headers=auth).json()
        assert util["total_flights"] == 2
        assert util["total_minutes"] == 150
        assert util["total_flight_hours"] == 2.5
        assert util["total_cycles"] == 3

    def test_record_flight_for_helicopter(self, client):
        tokens = _register(client, "Heli Flight Tenant", "admin@heliflight.example.com")
        auth = _auth(tokens["access_token"])

        asset = client.post(
            "/api/v1/assets",
            json={"asset_type": "HELICOPTER", "registration": "VT-HF1"},
            headers=auth,
        ).json()

        resp = client.post(
            f"/api/v1/assets/{asset['id']}/flights",
            json={"flown_at": "2025-01-01T00:00:00Z", "duration_minutes": 40, "cycles": 1},
            headers=auth,
        )
        assert resp.status_code == 201, resp.text

    def test_record_flight_rejects_drone_asset(self, client):
        tokens = _register(client, "Drone Guard Tenant", "admin@droneguard.example.com")
        auth = _auth(tokens["access_token"])

        asset = client.post(
            "/api/v1/assets",
            json={"asset_type": "DRONE", "registration": "UAV-GUARD1"},
            headers=auth,
        ).json()

        resp = client.post(
            f"/api/v1/assets/{asset['id']}/flights",
            json={"flown_at": "2025-01-01T00:00:00Z", "duration_minutes": 20, "cycles": 1},
            headers=auth,
        )
        assert resp.status_code == 400
        assert resp.json()["error"]["code"] == "use_drone_flight_endpoint"

    def test_record_flight_cross_tenant_returns_404(self, client):
        tokens_a = _register(client, "Flight Tenant A", "admin@flight-a.example.com")
        tokens_b = _register(client, "Flight Tenant B", "admin@flight-b.example.com")
        auth_a, auth_b = _auth(tokens_a["access_token"]), _auth(tokens_b["access_token"])

        asset = client.post(
            "/api/v1/assets",
            json={"asset_type": "AIRCRAFT", "registration": "N41FL"},
            headers=auth_a,
        ).json()

        resp = client.post(
            f"/api/v1/assets/{asset['id']}/flights",
            json={"flown_at": "2025-01-01T00:00:00Z", "duration_minutes": 20, "cycles": 1},
            headers=auth_b,
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Service-level tenant isolation
# ---------------------------------------------------------------------------


class TestAssetServiceTenantIsolation:
    def test_get_asset_denies_cross_tenant_access(self, db_session):
        org_a = _make_org(db_session)
        org_b = _make_org(db_session)
        asset_b = Asset(
            organization_id=org_b.id, asset_type=AssetType.AIRCRAFT.value, registration="N5XT"
        )
        db_session.add(asset_b)
        db_session.commit()
        db_session.refresh(asset_b)

        with pytest.raises(NotFoundError):
            asset_service.get_asset(db_session, organization_id=org_a.id, asset_id=asset_b.id)

        # Sanity: org_b can read its own asset.
        found = asset_service.get_asset(db_session, organization_id=org_b.id, asset_id=asset_b.id)
        assert found.id == asset_b.id

    def test_list_assets_scoped_to_organization(self, db_session):
        org_a = _make_org(db_session)
        org_b = _make_org(db_session)
        db_session.add(
            Asset(organization_id=org_a.id, asset_type=AssetType.AIRCRAFT.value, registration="N6A")
        )
        db_session.add(
            Asset(organization_id=org_b.id, asset_type=AssetType.AIRCRAFT.value, registration="N6B")
        )
        db_session.commit()

        assets_a = asset_service.list_assets(db_session, organization_id=org_a.id)
        assert {a.registration for a in assets_a} == {"N6A"}

    def test_get_aircraft_asset_denies_cross_tenant_access(self, db_session):
        org_a = _make_org(db_session)
        org_b = _make_org(db_session)
        aircraft_b = aircraft_service.create_aircraft(
            db_session,
            organization_id=org_b.id,
            payload=AircraftCreateRequest(registration="N7XT", msn="MSN-7", aircraft_type="A320"),
        )
        asset_b = Asset(
            organization_id=org_b.id, asset_type=AssetType.AIRCRAFT.value, registration="N7XT-A"
        )
        db_session.add(asset_b)
        db_session.commit()
        db_session.refresh(asset_b)
        aircraft_b.asset_id = asset_b.id
        db_session.commit()

        with pytest.raises(NotFoundError):
            asset_service.get_aircraft_asset(
                db_session, organization_id=org_a.id, aircraft_id=aircraft_b.id
            )


# ---------------------------------------------------------------------------
# API-level tenant isolation
# ---------------------------------------------------------------------------


def _register(client, org_name, email):
    from tests.integration.conftest import make_platform_admin_headers

    db_session = next(app.dependency_overrides[get_db_session]())
    headers = make_platform_admin_headers(client, db_session)
    resp = client.post(
        "/api/v1/auth/register-organization",
        json={
            "organization_name": org_name,
            "admin_email": email,
            "admin_full_name": "Admin",
            "admin_password": "supersecret123",
        },
        headers=headers,
    )
    assert resp.status_code == 201
    return resp.json()


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


class TestAssetApiTenantIsolation:
    def test_cross_tenant_cannot_get_asset(self, client, db_session):
        tokens_a = _register(client, "Asset Tenant A", "admin@asset-a.example.com")
        tokens_b = _register(client, "Asset Tenant B", "admin@asset-b.example.com")
        auth_a, auth_b = _auth(tokens_a["access_token"]), _auth(tokens_b["access_token"])

        # TokenResponse does not expose organization_id directly, so resolve
        # org B's id via a created Aircraft's response body instead.
        aircraft_b = client.post(
            "/api/v1/aircraft",
            json={
                "registration": "N8XT",
                "msn": "MSN-8",
                "aircraft_type": "A320",
                "status": "ACTIVE",
            },
            headers=auth_b,
        ).json()
        org_b_id = uuid.UUID(aircraft_b["organization_id"])

        asset_b = Asset(
            organization_id=org_b_id, asset_type=AssetType.AIRCRAFT.value, registration="N8XT-ASSET"
        )
        db_session.add(asset_b)
        db_session.commit()
        db_session.refresh(asset_b)

        resp = client.get(f"/api/v1/assets/{asset_b.id}", headers=auth_a)
        assert resp.status_code == 404

        own = client.get(f"/api/v1/assets/{asset_b.id}", headers=auth_b)
        assert own.status_code == 200
        assert own.json()["id"] == str(asset_b.id)

    def test_list_assets_does_not_leak_across_tenants(self, client, db_session):
        tokens_a = _register(client, "Asset List Tenant A", "admin@asset-list-a.example.com")
        tokens_b = _register(client, "Asset List Tenant B", "admin@asset-list-b.example.com")
        auth_a, auth_b = _auth(tokens_a["access_token"]), _auth(tokens_b["access_token"])

        aircraft_b = client.post(
            "/api/v1/aircraft",
            json={
                "registration": "N9LX",
                "msn": "MSN-9",
                "aircraft_type": "A320",
                "status": "ACTIVE",
            },
            headers=auth_b,
        ).json()
        org_b_id = uuid.UUID(aircraft_b["organization_id"])
        db_session.add(
            Asset(
                organization_id=org_b_id,
                asset_type=AssetType.AIRCRAFT.value,
                registration="N9LX-ASSET",
            )
        )
        db_session.commit()

        resp = client.get("/api/v1/assets", headers=auth_a)
        assert resp.status_code == 200
        assert resp.json() == []


# ---------------------------------------------------------------------------
# Migration 0027: backfill correctness, upgrade/downgrade safety
# ---------------------------------------------------------------------------


class TestMigration0027Backfill:
    """Each test creates its own throwaway Postgres database (see
    `_isolated_migration_database` above), migrates only that database, and
    the context manager drops it on the way out -- always, including on
    assertion failure. This is what lets an Aircraft row be inserted BEFORE
    running 0027 (proving the backfill itself, not just the resulting
    schema) without ever touching the shared TEST_DATABASE_URL every other
    test in this suite reads/writes via the `db_session` fixture. There is
    no cross-test or cross-file ordering dependency of any kind, and these
    are now safe to run in any order, in isolation, or repeatedly.
    """

    def test_backfill_creates_matching_asset_and_detail(self):
        with _isolated_migration_database() as db_url:
            cfg = _alembic_config_for(db_url)
            command.upgrade(cfg, "0026")

            engine = create_engine(db_url, future=True)
            org_id = uuid.uuid4()
            aircraft_id = uuid.uuid4()
            try:
                with engine.begin() as conn:
                    conn.execute(
                        text("INSERT INTO organizations (id, name) VALUES (:id, :name)"),
                        {"id": org_id, "name": "Backfill Org"},
                    )
                    conn.execute(
                        text(
                            """
                            INSERT INTO aircraft
                                (id, organization_id, registration, msn, aircraft_type, status)
                            VALUES (:id, :org_id, :reg, :msn, :atype, :status)
                            """
                        ),
                        {
                            "id": aircraft_id,
                            "org_id": org_id,
                            "reg": "N10BF",
                            "msn": "MSN-BF1",
                            "atype": "B777-300ER",
                            "status": "ACTIVE",
                        },
                    )

                command.upgrade(cfg, "0027")

                with engine.begin() as conn:
                    aircraft_row = (
                        conn.execute(
                            text("SELECT asset_id FROM aircraft WHERE id = :id"),
                            {"id": aircraft_id},
                        )
                        .mappings()
                        .one()
                    )
                    assert aircraft_row["asset_id"] is not None

                    asset_row = (
                        conn.execute(
                            text("SELECT * FROM assets WHERE id = :id"),
                            {"id": aircraft_row["asset_id"]},
                        )
                        .mappings()
                        .one()
                    )
                    assert asset_row["organization_id"] == org_id
                    assert asset_row["asset_type"] == "AIRCRAFT"
                    assert asset_row["registration"] == "N10BF"
                    assert asset_row["status"] == "ACTIVE"
                    assert asset_row["manufacturer"] is None
                    assert asset_row["model"] is None
                    assert asset_row["serial_number"] is None

                    detail_row = (
                        conn.execute(
                            text("SELECT * FROM aircraft_details WHERE asset_id = :id"),
                            {"id": aircraft_row["asset_id"]},
                        )
                        .mappings()
                        .one()
                    )
                    assert detail_row["msn"] == "MSN-BF1"
                    assert detail_row["aircraft_type"] == "B777-300ER"

                    # This database exists solely for this test and contains
                    # exactly the one Aircraft row inserted above -- a global
                    # count here is meaningful (unlike against the shared
                    # TEST_DATABASE_URL) because nothing else can possibly
                    # have written to it.
                    aircraft_count = conn.execute(
                        text("SELECT COUNT(*) FROM aircraft")
                    ).scalar_one()
                    asset_count = conn.execute(
                        text("SELECT COUNT(*) FROM assets WHERE asset_type = 'AIRCRAFT'")
                    ).scalar_one()
                    detail_count = conn.execute(
                        text("SELECT COUNT(*) FROM aircraft_details")
                    ).scalar_one()
                    assert aircraft_count == asset_count == detail_count == 1
            finally:
                engine.dispose()

    def test_downgrade_removes_new_objects_without_touching_aircraft_data(self):
        with _isolated_migration_database() as db_url:
            cfg = _alembic_config_for(db_url)
            command.upgrade(cfg, "head")

            engine = create_engine(db_url, future=True)
            try:
                org_id = uuid.uuid4()
                aircraft_id = uuid.uuid4()
                with engine.begin() as conn:
                    conn.execute(
                        text("INSERT INTO organizations (id, name) VALUES (:id, :name)"),
                        {"id": org_id, "name": "Downgrade Org"},
                    )
                    conn.execute(
                        text(
                            """
                            INSERT INTO aircraft
                                (id, organization_id, registration, msn, aircraft_type, status)
                            VALUES (:id, :org_id, :reg, :msn, :atype, :status)
                            """
                        ),
                        {
                            "id": aircraft_id,
                            "org_id": org_id,
                            "reg": "N11DG",
                            "msn": "MSN-DG1",
                            "atype": "A350-900",
                            "status": "ACTIVE",
                        },
                    )

                command.downgrade(cfg, "0026")

                with engine.begin() as conn:
                    # Aircraft row itself must survive untouched.
                    row = (
                        conn.execute(
                            text(
                                "SELECT registration, msn, aircraft_type, status "
                                "FROM aircraft WHERE id = :id"
                            ),
                            {"id": aircraft_id},
                        )
                        .mappings()
                        .one()
                    )
                    assert row["registration"] == "N11DG"
                    assert row["msn"] == "MSN-DG1"
                    assert row["aircraft_type"] == "A350-900"
                    assert row["status"] == "ACTIVE"

                    # New tables must be gone.
                    tables = (
                        conn.execute(
                            text(
                                "SELECT table_name FROM information_schema.tables "
                                "WHERE table_name IN ('assets', 'aircraft_details')"
                            )
                        )
                        .scalars()
                        .all()
                    )
                    assert tables == []
            finally:
                engine.dispose()

    def test_upgrade_is_idempotent_for_downgrade_then_reupgrade(self):
        with _isolated_migration_database() as db_url:
            cfg = _alembic_config_for(db_url)
            command.upgrade(cfg, "head")
            command.downgrade(cfg, "0026")
            command.upgrade(cfg, "0027")
            command.downgrade(cfg, "0026")
            command.upgrade(cfg, "head")  # must not raise


class TestMigration0027IntegrityCheckDetectsRealBreakage:
    """0027's post-backfill DO block (Phase 1A hardening) is provably
    unreachable through the migration's own backfill logic -- it derives
    every Asset/AircraftDetail field directly from an already-consistent
    Aircraft row, so the backfill itself cannot produce a violation to
    trigger it against. To prove the check logic is actually meaningful
    (not decorative), this test runs the SAME validation query the
    migration uses -- copied verbatim from
    backend/alembic/versions/0027_asset_foundation.py's organization_id
    check -- directly against a database already at `head`, after
    deliberately corrupting one Asset's organization_id out from under its
    Aircraft (something no application code path can currently do, but
    which stands in for "the invariant is violated"), and asserts the check
    raises. If this query and the migration's copy ever drift, this test
    only proves the copy here still works -- keep both in sync by hand.
    """

    _ORG_MISMATCH_CHECK_SQL = """
        DO $$
        DECLARE
            bad_count bigint;
        BEGIN
            SELECT COUNT(*) INTO bad_count
            FROM aircraft ac
            JOIN assets a ON a.id = ac.asset_id
            WHERE a.organization_id <> ac.organization_id;
            IF bad_count > 0 THEN
                RAISE EXCEPTION
                    'Asset foundation backfill failed: % aircraft row(s) whose asset belongs to a different organization',
                    bad_count;
            END IF;
        END $$;
    """

    def test_check_raises_on_organization_id_mismatch(self, db_session):
        org_a = _make_org(db_session)
        org_b = _make_org(db_session)
        aircraft = aircraft_service.create_aircraft(
            db_session,
            organization_id=org_a.id,
            payload=AircraftCreateRequest(
                registration="N30IC", msn="MSN-IC1", aircraft_type="A320"
            ),
        )

        # Sanity: the check passes on consistent data.
        db_session.execute(text(self._ORG_MISMATCH_CHECK_SQL))

        # Corrupt the linked Asset's organization_id out from under its
        # Aircraft -- not reachable through any current application code
        # path, but exactly the invariant violation the check exists for.
        db_session.execute(
            text("UPDATE assets SET organization_id = :org_b WHERE id = :asset_id"),
            {"org_b": org_b.id, "asset_id": aircraft.asset_id},
        )

        with pytest.raises(DBAPIError):
            db_session.execute(text(self._ORG_MISMATCH_CHECK_SQL))
        db_session.rollback()
