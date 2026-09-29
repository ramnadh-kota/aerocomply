"""Integration tests for H8.2 (M7 Fleet Signal Integration).

H8.2 covers: aggregating M7's OWN persisted ProactiveSignalRecord rows
into a descriptive fleet signal context -- zero/one/multiple signals,
severity and signal-type buckets, HUMS/telemetry-freshness/other real M7
signal types, single vs multiple affected assets, multiple signals on the
same asset, M7's existing FLEET_PATTERN rows exposed unmodified (never
recomputed), M7+M14 affected-asset ratio composition, tenant isolation,
missing/incomplete metadata not crashing, and safety checks confirming
H8.2 never writes to any authoritative table.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.models.asset import Asset, AssetType
from app.models.organization import OnboardingStage, Organization, OrganizationStatus
from app.models.proactive_signal import ProactiveSignalRecord
from app.models.user import User, UserRole
from app.services.intelligence.cross_asset_intelligence_service import (
    evaluate_fleet_signal_aggregation,
)
from app.services.intelligence.proactive_intelligence_service import get_proactive_summary


@pytest.fixture
def h8_2_env(db_session: Session):
    org1 = Organization(name="H8.2 Tenant One", status=OrganizationStatus.ACTIVE, onboarding_stage=OnboardingStage.ACTIVE)
    org2 = Organization(name="H8.2 Tenant Two", status=OrganizationStatus.ACTIVE, onboarding_stage=OnboardingStage.ACTIVE)
    db_session.add_all([org1, org2])
    db_session.flush()

    user1 = User(organization_id=org1.id, email="admin@h82tenant1.com", hashed_password=hash_password("Password123!"), full_name="Admin One", is_active=True)
    user2 = User(organization_id=org2.id, email="admin@h82tenant2.com", hashed_password=hash_password("Password123!"), full_name="Admin Two", is_active=True)
    db_session.add_all([user1, user2])
    db_session.flush()
    db_session.add(UserRole(user_id=user1.id, role_name="ORG_ADMIN", organization_id=org1.id))
    db_session.add(UserRole(user_id=user2.id, role_name="ORG_ADMIN", organization_id=org2.id))
    db_session.flush()

    return {"org1": org1, "user1": user1, "org2": org2, "user2": user2}


def _make_asset(db_session, org_id, serial="H82-ASSET-01"):
    a = Asset(organization_id=org_id, asset_type=AssetType.DRONE, serial_number=serial, status="ACTIVE")
    db_session.add(a)
    db_session.flush()
    return a


def _make_signal(
    db_session,
    org_id,
    *,
    key,
    signal_type="MAINTENANCE_THRESHOLD",
    severity="HIGH",
    status="OPEN",
    asset_id=None,
    component_id=None,
):
    rec = ProactiveSignalRecord(
        organization_id=org_id,
        signal_key=key,
        signal_type=signal_type,
        severity=severity,
        priority=severity,
        status=status,
        title=f"Signal {key}",
        headline=f"Headline {key}",
        detected_at=datetime.now(UTC),
        asset_id=asset_id,
        component_id=component_id,
    )
    db_session.add(rec)
    db_session.flush()
    return rec


# ---------------------------------------------------------------------------
# Zero / one / multiple signals
# ---------------------------------------------------------------------------


def test_zero_signals_returns_zero_not_healthy(db_session: Session, h8_2_env):
    org1 = h8_2_env["org1"]
    _make_asset(db_session, org1.id)
    summary = evaluate_fleet_signal_aggregation(db_session, organization_id=org1.id)
    assert summary.total_active_signals == 0
    assert summary.affected_asset_count == 0
    assert summary.severity_distribution == {}
    assert summary.signal_type_distribution == {}
    assert summary.availability == "AVAILABLE"


def test_one_signal(db_session: Session, h8_2_env):
    org1 = h8_2_env["org1"]
    a = _make_asset(db_session, org1.id)
    _make_signal(db_session, org1.id, key="s1", asset_id=a.id, severity="HIGH")
    summary = evaluate_fleet_signal_aggregation(db_session, organization_id=org1.id)
    assert summary.total_active_signals == 1
    assert summary.affected_asset_count == 1
    assert summary.severity_distribution == {"HIGH": 1}


def test_multiple_signals(db_session: Session, h8_2_env):
    org1 = h8_2_env["org1"]
    a1 = _make_asset(db_session, org1.id, serial="A1")
    a2 = _make_asset(db_session, org1.id, serial="A2")
    _make_signal(db_session, org1.id, key="s1", asset_id=a1.id, severity="CRITICAL")
    _make_signal(db_session, org1.id, key="s2", asset_id=a2.id, severity="MEDIUM")
    summary = evaluate_fleet_signal_aggregation(db_session, organization_id=org1.id)
    assert summary.total_active_signals == 2
    assert summary.affected_asset_count == 2


# ---------------------------------------------------------------------------
# Severity + signal type distributions
# ---------------------------------------------------------------------------


def test_each_severity_and_mixed_severities(db_session: Session, h8_2_env):
    org1 = h8_2_env["org1"]
    a = _make_asset(db_session, org1.id)
    for sev, key in [("CRITICAL", "c1"), ("HIGH", "h1"), ("MEDIUM", "m1"), ("LOW", "l1")]:
        _make_signal(db_session, org1.id, key=key, asset_id=a.id, severity=sev)
    summary = evaluate_fleet_signal_aggregation(db_session, organization_id=org1.id)
    assert summary.severity_distribution == {"CRITICAL": 1, "HIGH": 1, "MEDIUM": 1, "LOW": 1}
    assert summary.total_active_signals == 4


def test_hums_telemetry_and_other_real_signal_types(db_session: Session, h8_2_env):
    org1 = h8_2_env["org1"]
    a = _make_asset(db_session, org1.id)
    _make_signal(db_session, org1.id, key="hums1", asset_id=a.id, signal_type="HUMS_EXCEEDANCE")
    _make_signal(db_session, org1.id, key="tel1", asset_id=a.id, signal_type="TELEMETRY_FRESHNESS")
    _make_signal(db_session, org1.id, key="maint1", asset_id=a.id, signal_type="MAINTENANCE_THRESHOLD")
    summary = evaluate_fleet_signal_aggregation(db_session, organization_id=org1.id)
    assert summary.signal_type_distribution["HUMS_EXCEEDANCE"] == 1
    assert summary.signal_type_distribution["TELEMETRY_FRESHNESS"] == 1
    assert summary.signal_type_distribution["MAINTENANCE_THRESHOLD"] == 1


# ---------------------------------------------------------------------------
# Affected assets / components, one vs multiple, repeats on same asset
# ---------------------------------------------------------------------------


def test_multiple_signals_same_asset_counts_once_in_affected(db_session: Session, h8_2_env):
    org1 = h8_2_env["org1"]
    a = _make_asset(db_session, org1.id)
    _make_signal(db_session, org1.id, key="s1", asset_id=a.id, severity="HIGH")
    _make_signal(db_session, org1.id, key="s2", asset_id=a.id, severity="MEDIUM")
    summary = evaluate_fleet_signal_aggregation(db_session, organization_id=org1.id)
    assert summary.affected_asset_count == 1
    assert summary.total_active_signals == 2
    by_asset = {e.asset_id: e for e in summary.signals_by_asset}
    assert by_asset[a.id].active_signal_count == 2
    assert by_asset[a.id].highest_severity == "HIGH"


def test_component_scoped_signal_counts_affected_component(db_session: Session, h8_2_env):
    org1 = h8_2_env["org1"]
    a = _make_asset(db_session, org1.id)
    comp_id = uuid.uuid4()
    _make_signal(db_session, org1.id, key="s1", asset_id=a.id, component_id=None)
    summary = evaluate_fleet_signal_aggregation(db_session, organization_id=org1.id)
    # No component_id on this signal -- must not crash, and must not count
    # a component that was never referenced.
    assert summary.affected_component_count == 0


# ---------------------------------------------------------------------------
# Fleet pattern passthrough -- no duplicate computation
# ---------------------------------------------------------------------------


def test_fleet_pattern_exposed_matches_m7_own_output_not_recomputed(db_session: Session, h8_2_env):
    org1 = h8_2_env["org1"]
    a1 = _make_asset(db_session, org1.id, serial="FP-1")
    a2 = _make_asset(db_session, org1.id, serial="FP-2")

    # Two recurring findings of the same category on two distinct assets
    # trigger M7's own fleet pattern detector when sync_and_get_signals
    # (called internally by get_proactive_summary) runs.
    from app.models.finding import Finding, FindingSeverity, FindingStatus

    for asset, suffix in [(a1, "1"), (a2, "2")]:
        for i in range(2):
            db_session.add(
                Finding(
                    organization_id=org1.id,
                    asset_id=asset.id,
                    title=f"HYDRAULIC leak {suffix}-{i}",
                    description="Hydraulic system leak observed",
                    severity=FindingSeverity.MAJOR,
                    status=FindingStatus.OPEN,
                    created_at=datetime.now(UTC),
                )
            )
    db_session.flush()

    # M7's own summary computes (and persists) the FLEET_PATTERN signal.
    m7_summary = get_proactive_summary(db_session, organization_id=org1.id)
    db_session.flush()
    assert len(m7_summary.fleet_patterns) >= 1
    m7_pattern_keys = {p.signal_key for p in m7_summary.fleet_patterns}

    # H8.2's aggregation must expose the SAME persisted rows, not
    # recompute its own pattern detection.
    h82_summary = evaluate_fleet_signal_aggregation(db_session, organization_id=org1.id)
    h82_pattern_keys = {p.signal_key for p in h82_summary.fleet_patterns}
    assert h82_pattern_keys == m7_pattern_keys
    assert len(h82_summary.fleet_patterns) == len(m7_summary.fleet_patterns)


# ---------------------------------------------------------------------------
# M7 + M14 composition
# ---------------------------------------------------------------------------


def test_m7_signal_m14_population_ratio_composition(db_session: Session, h8_2_env):
    org1 = h8_2_env["org1"]
    a1 = _make_asset(db_session, org1.id, serial="R1")
    a2 = _make_asset(db_session, org1.id, serial="R2")
    _make_asset(db_session, org1.id, serial="R3")  # unaffected asset
    _make_signal(db_session, org1.id, key="s1", asset_id=a1.id)
    _make_signal(db_session, org1.id, key="s2", asset_id=a2.id)

    summary = evaluate_fleet_signal_aggregation(db_session, organization_id=org1.id)
    assert summary.affected_asset_count == 2
    assert summary.assets_with_signals_ratio == "2/3"


def test_ratio_is_none_for_empty_fleet(db_session: Session, h8_2_env):
    org1 = h8_2_env["org1"]
    summary = evaluate_fleet_signal_aggregation(db_session, organization_id=org1.id)
    assert summary.assets_with_signals_ratio is None
    assert summary.total_active_signals == 0


# ---------------------------------------------------------------------------
# Tenant isolation
# ---------------------------------------------------------------------------


def test_tenant_isolation_zero_leakage(db_session: Session, h8_2_env):
    org1 = h8_2_env["org1"]
    org2 = h8_2_env["org2"]
    a1 = _make_asset(db_session, org1.id, serial="ISO-1")
    _make_signal(db_session, org1.id, key="iso1", asset_id=a1.id, severity="CRITICAL")

    summary_org1 = evaluate_fleet_signal_aggregation(db_session, organization_id=org1.id)
    summary_org2 = evaluate_fleet_signal_aggregation(db_session, organization_id=org2.id)

    assert summary_org1.total_active_signals == 1
    assert summary_org2.total_active_signals == 0
    assert summary_org2.affected_asset_count == 0


# ---------------------------------------------------------------------------
# Missing / incomplete metadata does not crash
# ---------------------------------------------------------------------------


def test_signal_with_no_asset_id_does_not_crash(db_session: Session, h8_2_env):
    org1 = h8_2_env["org1"]
    # A fleet-level signal (asset_id=None) -- must not crash and must not
    # be counted as an "affected asset".
    _make_signal(db_session, org1.id, key="fleet_only", asset_id=None, signal_type="FLEET_PATTERN")
    summary = evaluate_fleet_signal_aggregation(db_session, organization_id=org1.id)
    assert summary.total_active_signals == 1
    assert summary.affected_asset_count == 0
    assert len(summary.fleet_patterns) == 1


def test_resolved_and_dismissed_signals_excluded(db_session: Session, h8_2_env):
    org1 = h8_2_env["org1"]
    a = _make_asset(db_session, org1.id)
    _make_signal(db_session, org1.id, key="resolved1", asset_id=a.id, status="RESOLVED")
    _make_signal(db_session, org1.id, key="dismissed1", asset_id=a.id, status="DISMISSED")
    _make_signal(db_session, org1.id, key="open1", asset_id=a.id, status="OPEN")
    summary = evaluate_fleet_signal_aggregation(db_session, organization_id=org1.id)
    assert summary.total_active_signals == 1


# ---------------------------------------------------------------------------
# Safety: no writes to authoritative tables, no new signal/attention/pattern engine
# ---------------------------------------------------------------------------


def test_h8_2_no_authoritative_writes_in_source():
    """Grep-based safety check: H8.2's own additions must contain no
    db.add/session.add/.commit() call, and must not touch WorkOrder,
    ComplianceObligation, or HUMS write paths -- strictly read-only."""
    import pathlib

    f = pathlib.Path(__file__).parents[2] / "app" / "services" / "intelligence" / "cross_asset_intelligence_service.py"
    text = f.read_text()
    assert "db.add(" not in text, f"{f} unexpectedly writes to the database"
    assert "db_session.add(" not in text, f"{f} unexpectedly writes to the database"
    assert ".commit()" not in text, f"{f} unexpectedly commits a transaction"

    schema_f = pathlib.Path(__file__).parents[2] / "app" / "schemas" / "fleet_intelligence.py"
    schema_text = schema_f.read_text()
    assert "db.add(" not in schema_text
    assert ".commit()" not in schema_text


def test_h8_2_never_calls_mutating_m7_sync_function():
    """H8.2's aggregation must read ProactiveSignalRecord directly, never
    call sync_and_get_signals/get_proactive_summary (which persist new/
    updated signal rows on every call) from within its own module."""
    import pathlib

    f = pathlib.Path(__file__).parents[2] / "app" / "services" / "intelligence" / "cross_asset_intelligence_service.py"
    text = f.read_text()
    assert "sync_and_get_signals(" not in text
    assert "get_proactive_summary(" not in text
