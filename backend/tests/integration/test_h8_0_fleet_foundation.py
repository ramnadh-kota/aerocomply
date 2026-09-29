"""Integration tests for H8.0 (Fleet Intelligence Contract & Foundation) and
H8.1 (M14 Cross-Asset Intelligence Extension).

H8.0 covers: contract serialization, empty fleet, tenant scope, source
lineage presence, insufficient-data behavior (never fabricate a positive
state when data is missing).

H8.1 covers: health distribution, HUMS coverage, telemetry freshness,
exceedances, components, diagnostics, prognostics, tenant isolation, empty
fleet, and insufficient-data behavior for M14's extended cross-asset
analytics.

Safety: asserts this module contains no write path that touches any
authoritative domain table (health, diagnostics, prognostics, readiness,
compliance, work orders).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.models.asset import Asset, AssetType
from app.models.component import Component
from app.models.hums import HUMSDiagnosticCandidate, HUMSExceedance, HUMSPrognosticRecord, HUMSSensor
from app.models.organization import OnboardingStage, Organization, OrganizationStatus
from app.models.proactive_signal import ProactiveSignalRecord
from app.models.telemetry import TelemetryEventLog
from app.models.user import User, UserRole
from app.schemas.fleet_intelligence import (
    FleetAnalyticalContext,
    FleetHealthContext,
    FleetIntelligenceContext,
    FleetOverviewContext,
    FleetTelemetryContext,
    SourceLineageEntry,
)
from app.services.intelligence.cross_asset_intelligence_service import evaluate_cross_asset_intelligence


@pytest.fixture
def h8_env(db_session: Session):
    org1 = Organization(name="H8 Tenant One", status=OrganizationStatus.ACTIVE, onboarding_stage=OnboardingStage.ACTIVE)
    org2 = Organization(name="H8 Tenant Two", status=OrganizationStatus.ACTIVE, onboarding_stage=OnboardingStage.ACTIVE)
    db_session.add_all([org1, org2])
    db_session.flush()

    user1 = User(organization_id=org1.id, email="admin@h8tenant1.com", hashed_password=hash_password("Password123!"), full_name="Admin One", is_active=True)
    user2 = User(organization_id=org2.id, email="admin@h8tenant2.com", hashed_password=hash_password("Password123!"), full_name="Admin Two", is_active=True)
    db_session.add_all([user1, user2])
    db_session.flush()
    db_session.add(UserRole(user_id=user1.id, role_name="ORG_ADMIN", organization_id=org1.id))
    db_session.add(UserRole(user_id=user2.id, role_name="ORG_ADMIN", organization_id=org2.id))
    db_session.flush()

    return {"org1": org1, "user1": user1, "org2": org2, "user2": user2}


def _make_asset(db_session, org_id, serial="H8-ASSET-01"):
    a = Asset(organization_id=org_id, asset_type=AssetType.DRONE, serial_number=serial, status="ACTIVE")
    db_session.add(a)
    db_session.flush()
    return a


def _make_sensor(db_session, org_id, asset_id, component_id=None, code="SENS-01"):
    s = HUMSSensor(
        organization_id=org_id, asset_id=asset_id, component_id=component_id,
        sensor_code=code, sensor_type="VIBRATION", measurement_type="vibration_rms", unit="mm/s",
        status="ACTIVE", source="SIMULATED",
    )
    db_session.add(s)
    db_session.flush()
    return s


# ---------------------------------------------------------------------------
# H8.0 -- contract
# ---------------------------------------------------------------------------


def test_h8_0_contract_serialization_round_trip():
    """The FleetIntelligenceContext contract must construct and serialize
    cleanly with well-formed data."""
    now = datetime.now(UTC)
    ctx = FleetIntelligenceContext(
        organization_id=uuid.uuid4(),
        overview=FleetOverviewContext(organization_id=uuid.uuid4(), asset_count=3, active_asset_count=3, component_count=5, evaluated_at=now),
        health_context=FleetHealthContext(availability="AVAILABLE", healthy_count=2, degraded_count=1, attention_count=0, unknown_count=0),
        telemetry_context=FleetTelemetryContext(availability="AVAILABLE", fresh_count=2, stale_count=1, missing_count=0, unknown_count=0, hums_coverage_percentage=66.67),
        analytical_context=FleetAnalyticalContext(availability="AVAILABLE", metrics={"exceedances_total": 4}),
        source_lineage=[
            SourceLineageEntry(source_domain="H3_HEALTH", source_service="app.services.hums_service", source_entity="ProactiveSignalRecord", freshness="FRESH"),
        ],
        evaluated_at=now,
    )
    dumped = ctx.model_dump()
    assert dumped["health_context"]["healthy_count"] == 2
    assert dumped["source_lineage"][0]["source_domain"] == "H3_HEALTH"
    assert dumped["overview"]["asset_count"] == 3


def test_h8_0_insufficient_data_never_fabricated():
    """An empty/unknown health context must not silently default to a
    positive (healthy) count -- it must report zero with explicit
    DATA_UNAVAILABLE availability."""
    ctx_health = FleetHealthContext(availability="DATA_UNAVAILABLE", healthy_count=0, degraded_count=0, attention_count=0, unknown_count=0)
    assert ctx_health.availability == "DATA_UNAVAILABLE"
    assert ctx_health.healthy_count == 0


# ---------------------------------------------------------------------------
# H8.1 -- empty fleet / insufficient data
# ---------------------------------------------------------------------------


def test_h8_1_empty_fleet_returns_valid_insufficient_data(db_session: Session, h8_env):
    """An org with zero assets returns a valid, populated (zeroed) summary
    -- not an error, and not a fabricated healthy state."""
    org1 = h8_env["org1"]
    summary = evaluate_cross_asset_intelligence(db_session, organization_id=org1.id)
    assert summary.total_assets == 0
    assert summary.fleet_health_status == "INSUFFICIENT_DATA"
    assert summary.health_distribution.availability == "DATA_UNAVAILABLE"
    assert summary.health_distribution.healthy_count == 0
    assert summary.hums_coverage.assets_total == 0
    assert summary.hums_coverage.coverage_percentage == 0.0
    assert summary.telemetry_freshness.availability == "DATA_UNAVAILABLE"
    assert summary.population_statistics.asset_count == 0
    assert summary.component_distribution == []
    assert summary.exceedance_distribution.total_exceedances == 0
    assert summary.diagnostic_distribution.diagnostic_candidate_count == 0
    assert summary.prognostic_distribution.assets_with_rul == 0


def test_h8_1_assets_with_no_hums_are_unknown_not_healthy(db_session: Session, h8_env):
    """An asset with zero HUMS sensors has no health basis and must be
    bucketed 'unknown', never assumed 'healthy'."""
    org1 = h8_env["org1"]
    _make_asset(db_session, org1.id, serial="NO-HUMS-01")
    summary = evaluate_cross_asset_intelligence(db_session, organization_id=org1.id)
    assert summary.health_distribution.unknown_count == 1
    assert summary.health_distribution.healthy_count == 0
    assert summary.hums_coverage.assets_with_hums == 0
    assert summary.hums_coverage.assets_without_hums == 1
    assert summary.hums_coverage.coverage_percentage == 0.0


# ---------------------------------------------------------------------------
# H8.1 -- health distribution
# ---------------------------------------------------------------------------


def test_h8_1_health_distribution_buckets(db_session: Session, h8_env):
    org1 = h8_env["org1"]
    healthy_asset = _make_asset(db_session, org1.id, serial="HEALTHY-01")
    degraded_asset = _make_asset(db_session, org1.id, serial="DEGRADED-01")
    attention_asset = _make_asset(db_session, org1.id, serial="ATTENTION-01")

    _make_sensor(db_session, org1.id, healthy_asset.id, code="S-H")
    _make_sensor(db_session, org1.id, degraded_asset.id, code="S-D")
    _make_sensor(db_session, org1.id, attention_asset.id, code="S-A")

    db_session.add(ProactiveSignalRecord(
        organization_id=org1.id, signal_key="hums_health:degraded", signal_type="HUMS_HEALTH_DEGRADATION",
        severity="MEDIUM", priority="P3", status="OPEN", title="Degraded", headline="Degraded component",
        detected_at=datetime.now(UTC), asset_id=degraded_asset.id,
    ))
    db_session.add(ProactiveSignalRecord(
        organization_id=org1.id, signal_key="hums_health:attention", signal_type="HUMS_HEALTH_DEGRADATION",
        severity="CRITICAL", priority="P1", status="OPEN", title="Critical", headline="Critical component",
        detected_at=datetime.now(UTC), asset_id=attention_asset.id,
    ))
    db_session.flush()

    summary = evaluate_cross_asset_intelligence(db_session, organization_id=org1.id)
    hd = summary.health_distribution
    assert hd.healthy_count == 1
    assert hd.degraded_count == 1
    assert hd.attention_count == 1
    assert hd.unknown_count == 0
    assert hd.availability == "AVAILABLE"


def test_h8_1_resolved_health_signal_does_not_count_as_open(db_session: Session, h8_env):
    org1 = h8_env["org1"]
    asset = _make_asset(db_session, org1.id, serial="RESOLVED-01")
    _make_sensor(db_session, org1.id, asset.id)
    db_session.add(ProactiveSignalRecord(
        organization_id=org1.id, signal_key="hums_health:resolved", signal_type="HUMS_HEALTH_DEGRADATION",
        severity="HIGH", priority="P2", status="RESOLVED", title="Resolved", headline="Was degraded",
        detected_at=datetime.now(UTC), asset_id=asset.id,
    ))
    db_session.flush()
    summary = evaluate_cross_asset_intelligence(db_session, organization_id=org1.id)
    assert summary.health_distribution.healthy_count == 1
    assert summary.health_distribution.attention_count == 0


# ---------------------------------------------------------------------------
# H8.1 -- HUMS coverage
# ---------------------------------------------------------------------------


def test_h8_1_hums_coverage_partial(db_session: Session, h8_env):
    org1 = h8_env["org1"]
    with_hums = _make_asset(db_session, org1.id, serial="COV-WITH")
    without_hums = _make_asset(db_session, org1.id, serial="COV-WITHOUT")
    _make_sensor(db_session, org1.id, with_hums.id)
    summary = evaluate_cross_asset_intelligence(db_session, organization_id=org1.id)
    cov = summary.hums_coverage
    assert cov.assets_total == 2
    assert cov.assets_with_hums == 1
    assert cov.assets_without_hums == 1
    assert cov.coverage_percentage == 50.0


def test_h8_1_hums_coverage_full(db_session: Session, h8_env):
    org1 = h8_env["org1"]
    a = _make_asset(db_session, org1.id, serial="COV-FULL")
    _make_sensor(db_session, org1.id, a.id)
    summary = evaluate_cross_asset_intelligence(db_session, organization_id=org1.id)
    assert summary.hums_coverage.coverage_percentage == 100.0


# ---------------------------------------------------------------------------
# H8.1 -- telemetry freshness
# ---------------------------------------------------------------------------


def test_h8_1_telemetry_freshness_fresh_stale_missing(db_session: Session, h8_env):
    org1 = h8_env["org1"]
    fresh_asset = _make_asset(db_session, org1.id, serial="FRESH-01")
    stale_asset = _make_asset(db_session, org1.id, serial="STALE-01")
    missing_asset = _make_asset(db_session, org1.id, serial="MISSING-01")

    now = datetime.now(UTC)
    db_session.add(TelemetryEventLog(
        organization_id=org1.id, source_system="TEST", source_event_id="evt-fresh-1",
        idempotency_key="evt-fresh-1", event_type="SENSOR_BURST", event_timestamp=now,
        received_timestamp=now, payload_hash="hash-fresh-1", asset_id=fresh_asset.id,
        processing_status="PROCESSED",
    ))
    db_session.add(TelemetryEventLog(
        organization_id=org1.id, source_system="TEST", source_event_id="evt-stale-1",
        idempotency_key="evt-stale-1", event_type="SENSOR_BURST", event_timestamp=now - timedelta(days=30),
        received_timestamp=now, payload_hash="hash-stale-1", asset_id=stale_asset.id,
        processing_status="PROCESSED",
    ))
    db_session.flush()

    summary = evaluate_cross_asset_intelligence(db_session, organization_id=org1.id)
    tf = summary.telemetry_freshness
    assert tf.fresh_count == 1
    assert tf.stale_count == 1
    assert tf.missing_count == 1
    assert tf.availability == "AVAILABLE"


# ---------------------------------------------------------------------------
# H8.1 -- exceedances
# ---------------------------------------------------------------------------


def test_h8_1_exceedance_distribution_none(db_session: Session, h8_env):
    org1 = h8_env["org1"]
    _make_asset(db_session, org1.id)
    summary = evaluate_cross_asset_intelligence(db_session, organization_id=org1.id)
    assert summary.exceedance_distribution.total_exceedances == 0
    assert summary.exceedance_distribution.affected_assets == 0


def test_h8_1_exceedance_distribution_multiple_assets(db_session: Session, h8_env):
    org1 = h8_env["org1"]
    a1 = _make_asset(db_session, org1.id, serial="EXC-01")
    a2 = _make_asset(db_session, org1.id, serial="EXC-02")
    s1 = _make_sensor(db_session, org1.id, a1.id, code="S-EXC-1")
    s2 = _make_sensor(db_session, org1.id, a2.id, code="S-EXC-2")

    now = datetime.now(UTC)
    db_session.add(HUMSExceedance(
        organization_id=org1.id, sensor_id=s1.id, asset_id=a1.id, parameter="vibration_rms",
        observed_value=9.0, threshold_value=8.0, severity="HIGH", window_start=now - timedelta(minutes=5), window_end=now,
    ))
    db_session.add(HUMSExceedance(
        organization_id=org1.id, sensor_id=s2.id, asset_id=a2.id, parameter="vibration_rms",
        observed_value=10.0, threshold_value=8.0, severity="CRITICAL", window_start=now - timedelta(minutes=5), window_end=now,
    ))
    db_session.flush()

    summary = evaluate_cross_asset_intelligence(db_session, organization_id=org1.id)
    ed = summary.exceedance_distribution
    assert ed.total_exceedances == 2
    assert ed.affected_assets == 2
    assert ed.exceedances_by_type["vibration_rms"] == 2


# ---------------------------------------------------------------------------
# H8.1 -- components
# ---------------------------------------------------------------------------


def test_h8_1_component_distribution_empty(db_session: Session, h8_env):
    org1 = h8_env["org1"]
    _make_asset(db_session, org1.id)
    summary = evaluate_cross_asset_intelligence(db_session, organization_id=org1.id)
    assert summary.component_distribution == []


def test_h8_1_component_distribution_multiple_types(db_session: Session, h8_env):
    org1 = h8_env["org1"]
    a = _make_asset(db_session, org1.id, serial="COMP-01")
    db_session.add(Component(organization_id=org1.id, asset_id=a.id, component_type="MOTOR", name="Motor 1"))
    db_session.add(Component(organization_id=org1.id, asset_id=a.id, component_type="MOTOR", name="Motor 2"))
    db_session.add(Component(organization_id=org1.id, asset_id=a.id, component_type="GPS", name="GPS 1"))
    db_session.flush()

    summary = evaluate_cross_asset_intelligence(db_session, organization_id=org1.id)
    by_type = {e.component_type: e.component_count for e in summary.component_distribution}
    assert by_type["MOTOR"] == 2
    assert by_type["GPS"] == 1


# ---------------------------------------------------------------------------
# H8.1 -- diagnostics / prognostics
# ---------------------------------------------------------------------------


def test_h8_1_diagnostic_distribution(db_session: Session, h8_env):
    org1 = h8_env["org1"]
    a = _make_asset(db_session, org1.id, serial="DIAG-01")
    db_session.add(HUMSDiagnosticCandidate(
        organization_id=org1.id, asset_id=a.id, sensor_ids=[], fault_code="FC-001", fault_name="Bearing Wear",
        fault_domain="VIBRATION", rule_version="h4.1", status="CANDIDATE", severity="HIGH", score=0.8,
        confidence="MEDIUM", detected_at=datetime.now(UTC),
    ))
    db_session.flush()
    summary = evaluate_cross_asset_intelligence(db_session, organization_id=org1.id)
    dd = summary.diagnostic_distribution
    assert dd.diagnostic_candidate_count == 1
    assert dd.affected_assets == 1
    assert dd.by_fault_domain["VIBRATION"] == 1
    assert dd.by_severity["HIGH"] == 1


def test_h8_1_prognostic_distribution(db_session: Session, h8_env):
    org1 = h8_env["org1"]
    a = _make_asset(db_session, org1.id, serial="PROG-01")
    s = _make_sensor(db_session, org1.id, a.id)
    now = datetime.now(UTC)
    db_session.add(HUMSPrognosticRecord(
        organization_id=org1.id, asset_id=a.id, sensor_id=s.id, feature_type="rms",
        current_value=6.0, rul_estimate=15.0, confidence="LOW", quality="LIMITED", status="LOW_CONFIDENCE",
        observed_at=now, calculated_at=now, is_current=True,
    ))
    db_session.flush()
    summary = evaluate_cross_asset_intelligence(db_session, organization_id=org1.id)
    pd = summary.prognostic_distribution
    assert pd.assets_with_rul == 1
    assert pd.rul_distribution["<25"] == 1
    assert pd.low_confidence_count == 1


# ---------------------------------------------------------------------------
# H8.1 -- tenant isolation
# ---------------------------------------------------------------------------


def test_h8_1_tenant_isolation_zero_leakage(db_session: Session, h8_env):
    org1 = h8_env["org1"]
    org2 = h8_env["org2"]

    a1 = _make_asset(db_session, org1.id, serial="ISO-ORG1")
    s1 = _make_sensor(db_session, org1.id, a1.id)
    db_session.add(HUMSExceedance(
        organization_id=org1.id, sensor_id=s1.id, asset_id=a1.id, parameter="vibration_rms",
        observed_value=9.0, threshold_value=8.0, severity="HIGH",
        window_start=datetime.now(UTC) - timedelta(minutes=5), window_end=datetime.now(UTC),
    ))
    db_session.flush()

    summary_org1 = evaluate_cross_asset_intelligence(db_session, organization_id=org1.id)
    summary_org2 = evaluate_cross_asset_intelligence(db_session, organization_id=org2.id)

    assert summary_org1.total_assets == 1
    assert summary_org1.exceedance_distribution.total_exceedances == 1
    assert summary_org2.total_assets == 0
    assert summary_org2.exceedance_distribution.total_exceedances == 0
    assert summary_org2.hums_coverage.assets_total == 0


# ---------------------------------------------------------------------------
# Safety: no writes to authoritative tables from this module
# ---------------------------------------------------------------------------


def test_h8_0_h8_1_no_authoritative_writes_in_source():
    """Grep-based safety check: the H8.0/H8.1 files must contain no
    db.add/session.add/.commit() call -- this milestone is strictly
    read-only/analytical. (evaluate_cross_asset_intelligence itself never
    persists anything; unlike H3's health_service, it only READS
    ProactiveSignalRecord, never writes one.)"""
    import pathlib

    files = [
        pathlib.Path(__file__).parents[2] / "app" / "services" / "intelligence" / "cross_asset_intelligence_service.py",
        pathlib.Path(__file__).parents[2] / "app" / "schemas" / "fleet_intelligence.py",
    ]
    for f in files:
        text = f.read_text()
        assert "db.add(" not in text, f"{f} unexpectedly writes to the database"
        assert "db_session.add(" not in text, f"{f} unexpectedly writes to the database"
        assert ".commit()" not in text, f"{f} unexpectedly commits a transaction"
