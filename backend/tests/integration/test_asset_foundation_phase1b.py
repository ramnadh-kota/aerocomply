"""Phase 18.5 (Asset Foundation Phase 1B): additive asset_id compatibility
columns on the 7 classified genuinely asset-level MRO relationships
(migration 0031) -- work_orders, aog_events, compliance_assessments,
deferred_items, maintenance_requirement_applicabilities,
maintenance_accomplishments, procurement_requests, purchase_orders.

Covers:
  - new records created via each service now populate asset_id from the
    aircraft's own asset_id (no service signature/API/schema change)
  - an aircraft with no asset mapping is handled safely (asset_id stays
    NULL, never guessed/forced)
  - existing aircraft-based read paths are unaffected
  - cross-tenant asset reference cannot be used to escape tenant scope
    (the existing aircraft_service.get_aircraft ownership check, which
    every one of these create paths already calls, is what prevents this
    -- confirmed still enforced with asset_id now also being set)
  - migration 0031 backfill correctness (isolated throwaway database, same
    pattern as TestMigration0027Backfill in test_asset_foundation.py --
    never against the shared TEST_DATABASE_URL other tests rely on)
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
from sqlalchemy.orm import sessionmaker

from app.core.errors import NotFoundError
from app.models.aircraft import Aircraft
from app.models.compliance import RegulatoryRequirement
from app.models.maintenance_requirement import (
    MaintenanceRequirement,
    MaintenanceRequirementApplicability,
)
from app.models.organization import Organization
from app.schemas.aircraft import AircraftCreateRequest
from app.schemas.aog_event import AogEventCreateRequest
from app.schemas.compliance import ComplianceAssessmentCreateRequest
from app.schemas.deferred_item import DeferredItemCreateRequest
from app.schemas.maintenance_requirement import (
    MaintenanceAccomplishmentCreateRequest,
    MaintenanceApplicabilityCreateRequest,
)
from app.schemas.procurement_request import ProcurementRequestCreateRequest
from app.schemas.purchase_order import PurchaseOrderCreateRequest, PurchaseOrderLineCreateRequest
from app.schemas.work_order import WorkOrderCreateRequest
from app.services import (
    aircraft_service,
    aog_service,
    compliance_service,
    deferred_item_service,
    maintenance_service,
    procurement_service,
    purchase_order_service,
    work_order_service,
)


def _make_org(db_session, name="Phase1B Test Org"):
    org = Organization(name=name)
    db_session.add(org)
    db_session.commit()
    return org


def _make_aircraft(db_session, org, *, registration="N50PB"):
    return aircraft_service.create_aircraft(
        db_session,
        organization_id=org.id,
        payload=AircraftCreateRequest(
            registration=registration, msn="MSN-PB", aircraft_type="A320"
        ),
    )


def _make_vendor(db_session, org):
    from app.models.vendor import Vendor

    vendor = Vendor(organization_id=org.id, name="Phase1B Vendor")
    db_session.add(vendor)
    db_session.commit()
    return vendor


class TestAssetIdPopulatedOnCreate:
    def test_work_order_gets_asset_id_from_aircraft(self, db_session):
        org = _make_org(db_session)
        aircraft = _make_aircraft(db_session, org)
        wo = work_order_service.create_work_order(
            db_session,
            organization_id=org.id,
            created_by_user_id=None,
            payload=WorkOrderCreateRequest(aircraft_id=aircraft.id, work_order_number="WO-PB-1"),
        )
        assert wo.asset_id == aircraft.asset_id
        assert wo.asset_id is not None

    def test_aog_event_gets_asset_id_from_aircraft(self, db_session):
        org = _make_org(db_session)
        aircraft = _make_aircraft(db_session, org)
        event = aog_service.declare_aog(
            db_session,
            organization_id=org.id,
            actor_user_id=None,
            payload=AogEventCreateRequest(aircraft_id=aircraft.id),
        )
        assert event.asset_id == aircraft.asset_id

    def test_compliance_assessment_gets_asset_id_from_aircraft(self, db_session):
        org = _make_org(db_session)
        aircraft = _make_aircraft(db_session, org)
        requirement = RegulatoryRequirement(
            organization_id=org.id,
            authority="FAA",
            requirement_number="AD-PB-1",
            title="Test AD",
            description="Test",
        )
        db_session.add(requirement)
        db_session.commit()

        assessment = compliance_service.create_assessment(
            db_session,
            organization_id=org.id,
            actor_user_id=None,
            payload=ComplianceAssessmentCreateRequest(
                aircraft_id=aircraft.id, requirement_id=requirement.id, evaluated_at="2026-01-01"
            ),
        )
        assert assessment.asset_id == aircraft.asset_id

    def test_deferred_item_gets_asset_id_from_aircraft(self, db_session):
        org = _make_org(db_session)
        aircraft = _make_aircraft(db_session, org)
        item = deferred_item_service.create_deferred_item(
            db_session,
            organization_id=org.id,
            actor_user_id=None,
            payload=DeferredItemCreateRequest(
                aircraft_id=aircraft.id, description="Test defect", opened_at="2026-01-01"
            ),
        )
        assert item.asset_id == aircraft.asset_id

    def test_maintenance_applicability_and_accomplishment_get_asset_id(self, db_session):
        org = _make_org(db_session)
        aircraft = _make_aircraft(db_session, org)
        requirement = MaintenanceRequirement(
            organization_id=org.id,
            description="Test requirement",
            ata_chapter="05",
            interval_type="CALENDAR",
            calendar_interval_days=365,
        )
        db_session.add(requirement)
        db_session.commit()

        maintenance_service.add_applicability(
            db_session,
            organization_id=org.id,
            actor_user_id=None,
            requirement_id=requirement.id,
            payload=MaintenanceApplicabilityCreateRequest(aircraft_id=aircraft.id),
        )
        applicability = db_session.execute(
            select(MaintenanceRequirementApplicability).where(
                MaintenanceRequirementApplicability.aircraft_id == aircraft.id
            )
        ).scalar_one()
        assert applicability.asset_id == aircraft.asset_id

        accomplishment = maintenance_service.record_accomplishment(
            db_session,
            organization_id=org.id,
            actor_user_id=None,
            requirement_id=requirement.id,
            payload=MaintenanceAccomplishmentCreateRequest(
                aircraft_id=aircraft.id, accomplished_at="2026-01-01"
            ),
        )
        assert accomplishment.asset_id == aircraft.asset_id

    def test_procurement_request_gets_asset_id_from_aircraft(self, db_session):
        org = _make_org(db_session)
        aircraft = _make_aircraft(db_session, org)
        request = procurement_service.create_request(
            db_session,
            organization_id=org.id,
            actor_user_id=None,
            payload=ProcurementRequestCreateRequest(
                aircraft_id=aircraft.id,
                part_number="PN-1",
                description="Test part",
                quantity=1,
                reason="Test replacement",
            ),
        )
        assert request.asset_id == aircraft.asset_id

    def test_purchase_order_gets_asset_id_when_aircraft_supplied(self, db_session):
        org = _make_org(db_session)
        aircraft = _make_aircraft(db_session, org)
        vendor = _make_vendor(db_session, org)
        po = purchase_order_service.create_purchase_order(
            db_session,
            organization_id=org.id,
            actor_user_id=None,
            payload=PurchaseOrderCreateRequest(
                po_number="PO-PB-1",
                vendor_id=vendor.id,
                aircraft_id=aircraft.id,
                lines=[
                    PurchaseOrderLineCreateRequest(
                        part_number="PN-1", description="Part", quantity=1
                    )
                ],
            ),
        )
        assert po.asset_id == aircraft.asset_id

    def test_purchase_order_without_aircraft_has_no_asset_id(self, db_session):
        org = _make_org(db_session)
        vendor = _make_vendor(db_session, org)
        po = purchase_order_service.create_purchase_order(
            db_session,
            organization_id=org.id,
            actor_user_id=None,
            payload=PurchaseOrderCreateRequest(
                po_number="PO-PB-2",
                vendor_id=vendor.id,
                lines=[
                    PurchaseOrderLineCreateRequest(
                        part_number="PN-2", description="Part", quantity=1
                    )
                ],
            ),
        )
        assert po.aircraft_id is None
        assert po.asset_id is None


class TestAircraftWithoutAssetMappingHandledSafely:
    def test_work_order_asset_id_is_null_when_aircraft_has_no_asset(self, db_session):
        org = _make_org(db_session)
        # Construct an Aircraft row directly with asset_id=None, bypassing
        # the dual-write service -- simulates a historical/edge-case row
        # that migration 0031's backfill would also have left NULL.
        aircraft = Aircraft(
            organization_id=org.id,
            registration="N51PB",
            msn="MSN-PB2",
            aircraft_type="A320",
            status="ACTIVE",
            asset_id=None,
        )
        db_session.add(aircraft)
        db_session.commit()

        wo = work_order_service.create_work_order(
            db_session,
            organization_id=org.id,
            created_by_user_id=None,
            payload=WorkOrderCreateRequest(aircraft_id=aircraft.id, work_order_number="WO-PB-2"),
        )
        assert wo.aircraft_id == aircraft.id
        assert wo.asset_id is None


class TestCrossTenantAircraftStillRejected:
    def test_work_order_creation_rejects_other_org_aircraft(self, db_session):
        """Confirms the existing aircraft_service.get_aircraft ownership
        check (which every asset_id-populating create path now also relies
        on for the aircraft object it derives asset_id from) still enforces
        tenant scope -- asset_id population does not create a new,
        unchecked path to reference another tenant's data."""
        org_a = _make_org(db_session, "Phase1B Org A")
        org_b = _make_org(db_session, "Phase1B Org B")
        aircraft_b = _make_aircraft(db_session, org_b, registration="N52PB")

        with pytest.raises(NotFoundError):
            work_order_service.create_work_order(
                db_session,
                organization_id=org_a.id,
                created_by_user_id=None,
                payload=WorkOrderCreateRequest(
                    aircraft_id=aircraft_b.id, work_order_number="WO-PB-HACK"
                ),
            )


TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+psycopg://aerocomply:aerocomply@localhost:5432/aerocomply_test",
)


@contextmanager
def _isolated_migration_database():
    """Same pattern as test_asset_foundation.py's own helper of the same
    name -- a throwaway database this test class alone creates, migrates,
    and drops, so it can never observe or affect TEST_DATABASE_URL."""
    parts = urlsplit(TEST_DATABASE_URL)
    maintenance_url = urlunsplit((parts.scheme, parts.netloc, "/postgres", "", ""))
    db_name = f"aerocomply_phase1b_test_{uuid.uuid4().hex[:12]}"

    maintenance_engine = create_engine(maintenance_url, isolation_level="AUTOCOMMIT", future=True)
    with maintenance_engine.connect() as conn:
        conn.execute(text(f'CREATE DATABASE "{db_name}"'))
    maintenance_engine.dispose()

    new_url = urlunsplit((parts.scheme, parts.netloc, f"/{db_name}", "", ""))
    try:
        yield new_url
    finally:
        maintenance_engine = create_engine(
            maintenance_url, isolation_level="AUTOCOMMIT", future=True
        )
        with maintenance_engine.connect() as conn:
            conn.execute(
                text(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE datname = :name AND pid <> pg_backend_pid()"
                ),
                {"name": db_name},
            )
            conn.execute(text(f'DROP DATABASE IF EXISTS "{db_name}"'))
        maintenance_engine.dispose()


def _alembic_config_for(database_url: str) -> Config:
    backend_dir = Path(__file__).resolve().parents[2]
    cfg = Config(str(backend_dir / "alembic.ini"))
    cfg.set_main_option("script_location", str(backend_dir / "alembic"))
    cfg.set_main_option("sqlalchemy.url", database_url)
    return cfg


class TestMigration0031Backfill:
    def test_backfill_populates_asset_id_and_upgrade_downgrade_reupgrade_succeeds(self):
        with _isolated_migration_database() as db_url:
            cfg = _alembic_config_for(db_url)
            command.upgrade(cfg, "0030")

            engine = create_engine(db_url, future=True)
            Session = sessionmaker(bind=engine, future=True)
            db = Session()
            try:
                # Raw SQL, not the Organization ORM class: this checkpoint is
                # pinned to revision 0030, which predates migration 0037's
                # Organization.industry column. Inserting via the live ORM
                # model (which maps that column) would fail against the
                # older schema -- match the pattern already used below for
                # assets/aircraft in this same test.
                org_result = db.execute(
                    text(
                        "INSERT INTO organizations (id, name, status, created_at) "
                        "VALUES (gen_random_uuid(), :name, 'ACTIVE', now()) RETURNING id"
                    ),
                    {"name": "Migration 0031 Test Org"},
                )
                org_id = org_result.scalar_one()
                db.commit()

                asset_result = db.execute(
                    text(
                        "INSERT INTO assets (id, organization_id, asset_type, status, "
                        "created_at) VALUES (gen_random_uuid(), :org_id, 'AIRCRAFT', "
                        "'ACTIVE', now()) RETURNING id"
                    ),
                    {"org_id": str(org_id)},
                )
                asset_id = asset_result.scalar_one()
                db.commit()

                aircraft_result = db.execute(
                    text(
                        "INSERT INTO aircraft (id, organization_id, registration, msn, "
                        "aircraft_type, status, asset_id, created_at) VALUES "
                        "(gen_random_uuid(), :org_id, 'N60MIG', 'MSN-MIG', 'A320', "
                        "'ACTIVE', :asset_id, now()) RETURNING id"
                    ),
                    {"org_id": str(org_id), "asset_id": str(asset_id)},
                )
                aircraft_id = aircraft_result.scalar_one()

                wo_result = db.execute(
                    text(
                        "INSERT INTO work_orders (id, organization_id, aircraft_id, "
                        "work_order_number, status, priority, created_at) VALUES "
                        "(gen_random_uuid(), :org_id, :aircraft_id, 'WO-MIG-1', 'OPEN', "
                        "'NORMAL', now()) RETURNING id"
                    ),
                    {"org_id": str(org_id), "aircraft_id": str(aircraft_id)},
                )
                work_order_id = wo_result.scalar_one()
                db.commit()
            finally:
                db.close()
                engine.dispose()

            command.upgrade(cfg, "0031")

            engine = create_engine(db_url, future=True)
            Session = sessionmaker(bind=engine, future=True)
            db = Session()
            try:
                backfilled = db.execute(
                    text("SELECT asset_id FROM work_orders WHERE id = :id"),
                    {"id": str(work_order_id)},
                ).scalar_one()
                assert str(backfilled) == str(asset_id)

                count = db.execute(text("SELECT count(*) FROM work_orders")).scalar_one()
                assert count == 1
            finally:
                db.close()
                engine.dispose()

            command.downgrade(cfg, "0030")

            engine = create_engine(db_url, future=True)
            with engine.connect() as conn:
                exists = conn.execute(
                    text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_name = 'work_orders' AND column_name = 'asset_id'"
                    )
                ).scalar_one_or_none()
                assert exists is None

                count = conn.execute(text("SELECT count(*) FROM work_orders")).scalar_one()
                assert count == 1
            engine.dispose()

            command.upgrade(cfg, "0031")

            engine = create_engine(db_url, future=True)
            with engine.connect() as conn:
                backfilled_again = conn.execute(
                    text("SELECT asset_id FROM work_orders WHERE id = :id"),
                    {"id": str(work_order_id)},
                ).scalar_one()
                assert str(backfilled_again) == str(asset_id)
            engine.dispose()
