from __future__ import annotations

import uuid
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.asset import Asset, AssetType
from app.models.compliance import ComplianceObligation
from app.models.hums import HUMSExceedance
from app.models.mro_intelligence import MaintenanceIntelligenceCandidate
from app.models.organization import Organization
from app.models.proactive_signal import ProactiveSignalRecord
from app.models.telemetry import TelemetryEventLog
from app.models.user import User
from app.models.work_order import WorkOrder
from scripts.seed_m21_demo_environment import (
    DEMO_ORG_NAME,
    reset_demo_organization,
    seed_m21_demo,
)


def test_m21_demo_seeding_complete(db_session: Session):
    """Verifies that M21 demo seeding creates the full interconnected demo dataset."""
    result = seed_m21_demo(db_session, reset=True)
    assert result["status"] == "SUCCESS"
    assert result["asset_count"] == 9

    # Verify Organization
    org = db_session.execute(select(Organization).where(Organization.name == DEMO_ORG_NAME)).scalar_one_or_none()
    assert org is not None

    # Verify Users
    users = db_session.execute(select(User).where(User.organization_id == org.id)).scalars().all()
    assert len(users) >= 3
    emails = {u.email for u in users}
    assert "demo.admin@kotaaerospace.com" in emails
    assert "demo.engineer@kotaaerospace.com" in emails
    assert "demo.pilot@kotaaerospace.com" in emails

    # Verify Multi-Asset Fleet
    assets = db_session.execute(select(Asset).where(Asset.organization_id == org.id)).scalars().all()
    assert len(assets) == 9
    types = {a.asset_type for a in assets}
    assert AssetType.DRONE in types
    assert AssetType.AIRCRAFT in types
    assert AssetType.HELICOPTER in types
    assert AssetType.EVTOL in types

    # Verify Telemetry & Freshness
    events = db_session.execute(select(TelemetryEventLog).where(TelemetryEventLog.organization_id == org.id)).scalars().all()
    assert len(events) >= 8

    # Verify HUMS Exceedances (Scenario B, C, F)
    exceedances = db_session.execute(select(HUMSExceedance).where(HUMSExceedance.organization_id == org.id)).scalars().all()
    assert len(exceedances) == 3
    severities = {e.severity for e in exceedances}
    assert "WARNING" in severities
    assert "CRITICAL" in severities

    # Verify M7 Proactive Signals
    signals = db_session.execute(select(ProactiveSignalRecord).where(ProactiveSignalRecord.organization_id == org.id)).scalars().all()
    assert len(signals) == 3

    # Verify MRO Intelligence Candidates
    candidates = db_session.execute(select(MaintenanceIntelligenceCandidate).where(MaintenanceIntelligenceCandidate.organization_id == org.id)).scalars().all()
    assert len(candidates) == 3
    cand_statuses = {c.status for c in candidates}
    assert "OPEN" in cand_statuses
    assert "UNDER_REVIEW" in cand_statuses
    assert "RESOLVED" in cand_statuses

    # Verify Converted Predictive Work Order
    wos = db_session.execute(select(WorkOrder).where(WorkOrder.organization_id == org.id)).scalars().all()
    assert len(wos) >= 2
    converted_wo = next((w for w in wos if w.work_order_number == "WO-PM-CRIT05"), None)
    assert converted_wo is not None
    assert converted_wo.source_type == "PREDICTIVE_INTELLIGENCE"
    assert converted_wo.status == "DRAFT"
    assert converted_wo.priority == "CRITICAL"


def test_m21_demo_seeding_idempotence(db_session: Session):
    """Verifies that re-running seeding without reset is idempotent and does not crash."""
    result1 = seed_m21_demo(db_session, reset=True)
    assert result1["status"] == "SUCCESS"

    # Re-run without reset
    result2 = seed_m21_demo(db_session, reset=False)
    assert result2["status"] == "SUCCESS"


def test_m21_demo_reset_safety(db_session: Session):
    """Verifies that resetting only affects the demo organization and preserves customer tenants."""
    # Seed demo org
    seed_m21_demo(db_session, reset=True)
    demo_org = db_session.execute(select(Organization).where(Organization.name == DEMO_ORG_NAME)).scalar_one_or_none()
    assert demo_org is not None

    # Create a separate customer tenant
    customer_org = Organization(
        name="Real Customer Airlines",
        status="ACTIVE",
    )
    db_session.add(customer_org)
    db_session.flush()

    customer_asset = Asset(
        organization_id=customer_org.id,
        asset_type=AssetType.AIRCRAFT,
        model="Boeing 737",
        serial_number="CUST-737-01",
        status="ACTIVE",
    )
    db_session.add(customer_asset)
    db_session.commit()

    # Reset demo organization
    reset_demo_organization(db_session, demo_org.id)
    db_session.commit()

    # Customer organization and asset must remain untouched
    preserved_cust = db_session.get(Organization, customer_org.id)
    assert preserved_cust is not None
    preserved_asset = db_session.get(Asset, customer_asset.id)
    assert preserved_asset is not None
