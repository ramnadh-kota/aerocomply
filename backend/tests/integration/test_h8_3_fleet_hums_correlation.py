"""Integration tests for H8.3 (Fleet HUMS Correlation).

H8.3 correlates existing M7 signals, M14 fleet population, H4 diagnostic
candidates, H5 prognostic/RUL records, and H6 digital-twin component
context into a descriptive, deterministic fleet correlation. It never
recomputes health, diagnoses, RUL, degradation models, signal severity,
or fleet attention -- see app.services.intelligence
.cross_asset_intelligence_service.evaluate_fleet_hums_correlation and
docs/H8_FLEET_HUMS_INTELLIGENCE.md's H8.3 section.

Coverage: M7<->H4 correlation, M7<->H5 correlation, component
correlation, signal-type/severity correlation, fleet population
(zero/one/multiple affected), digital twin context, evidence
completeness, tenant isolation, safety (no writes / no mutating-service
calls), and the correlation-is-not-causation language rule.
"""

from __future__ import annotations

import inspect
import re
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from fastapi.testclient import TestClient

from app.core.security import create_access_token, hash_password
from app.models.asset import Asset, AssetType
from app.models.component import Component
from app.models.hums import HUMSDiagnosticCandidate, HUMSExceedance, HUMSFeature, HUMSPrognosticRecord, HUMSSensor
from app.models.organization import OnboardingStage, Organization, OrganizationStatus
from app.models.proactive_signal import ProactiveSignalRecord
from app.models.user import User, UserRole
from app.services.intelligence.cross_asset_intelligence_service import (
    evaluate_fleet_hums_correlation,
    get_fleet_correlation_context,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def h8_3_env(db_session: Session):
    org1 = Organization(name="H8.3 Tenant One", status=OrganizationStatus.ACTIVE, onboarding_stage=OnboardingStage.ACTIVE)
    org2 = Organization(name="H8.3 Tenant Two", status=OrganizationStatus.ACTIVE, onboarding_stage=OnboardingStage.ACTIVE)
    db_session.add_all([org1, org2])
    db_session.flush()

    user1 = User(organization_id=org1.id, email="admin@h83tenant1.com", hashed_password=hash_password("Password123!"), full_name="Admin One", is_active=True)
    user2 = User(organization_id=org2.id, email="admin@h83tenant2.com", hashed_password=hash_password("Password123!"), full_name="Admin Two", is_active=True)
    db_session.add_all([user1, user2])
    db_session.flush()
    db_session.add(UserRole(user_id=user1.id, role_name="ORG_ADMIN", organization_id=org1.id))
    db_session.add(UserRole(user_id=user2.id, role_name="ORG_ADMIN", organization_id=org2.id))
    db_session.flush()

    return {"org1": org1, "user1": user1, "org2": org2, "user2": user2}


def _make_asset(db_session, org_id, serial="H83-ASSET-01"):
    a = Asset(organization_id=org_id, asset_type=AssetType.DRONE, serial_number=serial, status="ACTIVE")
    db_session.add(a)
    db_session.flush()
    return a


def _make_component(db_session, org_id, asset_id, *, component_type="MOTOR", model=None, name="Component"):
    c = Component(organization_id=org_id, asset_id=asset_id, component_type=component_type, name=name, model=model)
    db_session.add(c)
    db_session.flush()
    return c


def _make_signal(
    db_session, org_id, *, key, signal_type="MAINTENANCE_THRESHOLD", severity="HIGH", status="OPEN", asset_id=None, component_id=None,
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


def _make_diagnostic(db_session, org_id, *, asset_id, component_id=None, fault_code="FC-1", status="SUPPORTED", severity="MEDIUM"):
    d = HUMSDiagnosticCandidate(
        organization_id=org_id,
        asset_id=asset_id,
        component_id=component_id,
        sensor_ids=[],
        fault_code=fault_code,
        fault_name="Sample Fault",
        fault_domain="VIBRATION",
        diagnostic_method="rule_based_signature_matching",
        rule_version="h4.1",
        status=status,
        severity=severity,
        score=0.7,
        confidence="MEDIUM",
        primary_evidence=[],
        supporting_evidence=[],
        contradicting_evidence=[],
        explanation=["Sample rule matched."],
        detected_at=datetime.now(UTC),
    )
    db_session.add(d)
    db_session.flush()
    return d


def _make_sensor(
    db_session, org_id, asset_id, component_id=None, code="SEN-1", unit="g", sensor_type="VIBRATION", source="SIMULATED"
):
    s = HUMSSensor(
        organization_id=org_id,
        asset_id=asset_id,
        component_id=component_id,
        sensor_code=code,
        sensor_type=sensor_type,
        measurement_type="RMS",
        unit=unit,
        source=source,
    )
    db_session.add(s)
    db_session.flush()
    return s


def _make_exceedance(
    db_session,
    org_id,
    *,
    asset_id,
    sensor_id,
    component_id=None,
    parameter="vibration_rms",
    observed_value=0.65,
    threshold_value=0.50,
    severity="WARNING",
    contributing_reading_ids=None,
):
    now = datetime.now(UTC)
    e = HUMSExceedance(
        organization_id=org_id,
        asset_id=asset_id,
        sensor_id=sensor_id,
        component_id=component_id,
        parameter=parameter,
        observed_value=observed_value,
        threshold_value=threshold_value,
        severity=severity,
        window_start=now - timedelta(minutes=10),
        window_end=now,
        contributing_reading_ids=contributing_reading_ids or [],
    )
    db_session.add(e)
    db_session.flush()
    return e


def _make_prognostic(db_session, org_id, *, asset_id, sensor_id, component_id=None, rul_estimate=68.0, confidence="MEDIUM", status="AVAILABLE"):
    now = datetime.now(UTC)
    p = HUMSPrognosticRecord(
        organization_id=org_id, asset_id=asset_id, component_id=component_id, sensor_id=sensor_id,
        feature_type="rms", current_value=0.44, threshold_value=0.6, threshold_type="MAINTENANCE_THRESHOLD",
        rul_estimate=rul_estimate, rul_lower=40.0, rul_upper=90.0, rul_unit="FLIGHT_HOURS",
        extrapolation_distance=1.2, confidence=confidence, quality="VALID", status=status,
        explanation=["Sample degradation trend."], observed_at=now, calculated_at=now, version=1, is_current=True,
    )
    db_session.add(p)
    db_session.flush()
    return p


# ---------------------------------------------------------------------------
# Fleet population: zero / one / multiple affected assets
# ---------------------------------------------------------------------------


def test_zero_assets_returns_data_unavailable(db_session: Session, h8_3_env):
    org1 = h8_3_env["org1"]
    result = evaluate_fleet_hums_correlation(db_session, organization_id=org1.id)
    assert result.total_fleet_assets == 0
    assert result.affected_asset_count == 0
    assert result.availability == "DATA_UNAVAILABLE"


def test_assets_with_no_evidence_are_not_affected(db_session: Session, h8_3_env):
    org1 = h8_3_env["org1"]
    _make_asset(db_session, org1.id, serial="NOEV-1")
    result = evaluate_fleet_hums_correlation(db_session, organization_id=org1.id)
    assert result.total_fleet_assets == 1
    assert result.affected_asset_count == 0
    assert result.affected_asset_percentage == 0.0
    assert result.availability == "AVAILABLE"


def test_one_affected_asset(db_session: Session, h8_3_env):
    org1 = h8_3_env["org1"]
    a = _make_asset(db_session, org1.id)
    _make_signal(db_session, org1.id, key="s1", asset_id=a.id)
    result = evaluate_fleet_hums_correlation(db_session, organization_id=org1.id)
    assert result.affected_asset_count == 1
    assert result.affected_asset_percentage == 100.0


def test_multiple_affected_assets(db_session: Session, h8_3_env):
    org1 = h8_3_env["org1"]
    a1 = _make_asset(db_session, org1.id, serial="A1")
    a2 = _make_asset(db_session, org1.id, serial="A2")
    _make_asset(db_session, org1.id, serial="A3-unaffected")
    _make_signal(db_session, org1.id, key="s1", asset_id=a1.id)
    _make_diagnostic(db_session, org1.id, asset_id=a2.id)
    result = evaluate_fleet_hums_correlation(db_session, organization_id=org1.id)
    assert result.total_fleet_assets == 3
    assert result.affected_asset_count == 2
    assert result.affected_asset_percentage == pytest.approx(66.67, rel=0.01)


# ---------------------------------------------------------------------------
# M7 <-> H4 correlation
# ---------------------------------------------------------------------------


def test_signal_with_matching_diagnostic_candidate(db_session: Session, h8_3_env):
    org1 = h8_3_env["org1"]
    a = _make_asset(db_session, org1.id)
    c = _make_component(db_session, org1.id, a.id)
    sig = _make_signal(db_session, org1.id, key="s1", asset_id=a.id, component_id=c.id)
    diag = _make_diagnostic(db_session, org1.id, asset_id=a.id, component_id=c.id)
    result = evaluate_fleet_hums_correlation(db_session, organization_id=org1.id)
    assert len(result.signal_diagnostic_associations) == 1
    link = result.signal_diagnostic_associations[0]
    assert link.signal_id == sig.id
    assert link.diagnostic_candidate_id == diag.id
    assert link.basis == "SAME_ASSET_AND_COMPONENT"


def test_signal_without_matching_diagnostic_candidate(db_session: Session, h8_3_env):
    org1 = h8_3_env["org1"]
    a1 = _make_asset(db_session, org1.id, serial="A1")
    a2 = _make_asset(db_session, org1.id, serial="A2")
    _make_signal(db_session, org1.id, key="s1", asset_id=a1.id)
    _make_diagnostic(db_session, org1.id, asset_id=a2.id)
    result = evaluate_fleet_hums_correlation(db_session, organization_id=org1.id)
    assert result.signal_diagnostic_associations == []


def test_multiple_signals_same_diagnostic_candidate(db_session: Session, h8_3_env):
    org1 = h8_3_env["org1"]
    a = _make_asset(db_session, org1.id)
    _make_signal(db_session, org1.id, key="s1", asset_id=a.id)
    _make_signal(db_session, org1.id, key="s2", asset_id=a.id)
    _make_diagnostic(db_session, org1.id, asset_id=a.id)
    result = evaluate_fleet_hums_correlation(db_session, organization_id=org1.id)
    assert len(result.signal_diagnostic_associations) == 2
    for link in result.signal_diagnostic_associations:
        assert link.basis == "SAME_ASSET"


# ---------------------------------------------------------------------------
# M7 <-> H5 correlation
# ---------------------------------------------------------------------------


def test_signal_with_rul_estimate(db_session: Session, h8_3_env):
    org1 = h8_3_env["org1"]
    a = _make_asset(db_session, org1.id)
    c = _make_component(db_session, org1.id, a.id)
    sensor = _make_sensor(db_session, org1.id, a.id, component_id=c.id)
    sig = _make_signal(db_session, org1.id, key="s1", asset_id=a.id, component_id=c.id)
    prog = _make_prognostic(db_session, org1.id, asset_id=a.id, sensor_id=sensor.id, component_id=c.id)
    result = evaluate_fleet_hums_correlation(db_session, organization_id=org1.id)
    assert len(result.signal_prognostic_associations) == 1
    link = result.signal_prognostic_associations[0]
    assert link.signal_id == sig.id
    assert link.prognostic_record_id == prog.id
    asset_entry = {e.asset_id: e for e in result.asset_correlations}[a.id]
    assert asset_entry.has_rul_estimate is True


def test_signal_without_rul_estimate(db_session: Session, h8_3_env):
    org1 = h8_3_env["org1"]
    a = _make_asset(db_session, org1.id)
    _make_signal(db_session, org1.id, key="s1", asset_id=a.id)
    result = evaluate_fleet_hums_correlation(db_session, organization_id=org1.id)
    assert result.signal_prognostic_associations == []
    asset_entry = {e.asset_id: e for e in result.asset_correlations}[a.id]
    assert asset_entry.has_rul_estimate is False


def test_multiple_assets_with_rul(db_session: Session, h8_3_env):
    org1 = h8_3_env["org1"]
    a1 = _make_asset(db_session, org1.id, serial="A1")
    a2 = _make_asset(db_session, org1.id, serial="A2")
    s1 = _make_sensor(db_session, org1.id, a1.id, code="SEN-1")
    s2 = _make_sensor(db_session, org1.id, a2.id, code="SEN-2")
    _make_prognostic(db_session, org1.id, asset_id=a1.id, sensor_id=s1.id)
    _make_prognostic(db_session, org1.id, asset_id=a2.id, sensor_id=s2.id)
    result = evaluate_fleet_hums_correlation(db_session, organization_id=org1.id)
    by_asset = {e.asset_id: e for e in result.asset_correlations}
    assert by_asset[a1.id].has_rul_estimate is True
    assert by_asset[a2.id].has_rul_estimate is True
    assert result.affected_asset_count == 2


# ---------------------------------------------------------------------------
# Component correlation
# ---------------------------------------------------------------------------


def test_same_component_type_and_model_across_assets(db_session: Session, h8_3_env):
    org1 = h8_3_env["org1"]
    a1 = _make_asset(db_session, org1.id, serial="A1")
    a2 = _make_asset(db_session, org1.id, serial="A2")
    c1 = _make_component(db_session, org1.id, a1.id, component_type="MOTOR", model="X200")
    c2 = _make_component(db_session, org1.id, a2.id, component_type="MOTOR", model="X200")
    _make_signal(db_session, org1.id, key="s1", asset_id=a1.id, component_id=c1.id)
    _make_signal(db_session, org1.id, key="s2", asset_id=a2.id, component_id=c2.id)
    result = evaluate_fleet_hums_correlation(db_session, organization_id=org1.id)
    assert len(result.component_correlations) == 1
    entry = result.component_correlations[0]
    assert entry.component_type == "MOTOR"
    assert entry.model == "X200"
    assert entry.correlated_component_count == 2
    assert entry.basis == "SAME_COMPONENT_TYPE_AND_MODEL"
    assert set(entry.asset_ids) == {a1.id, a2.id}


def test_different_component_types_not_correlated(db_session: Session, h8_3_env):
    org1 = h8_3_env["org1"]
    a1 = _make_asset(db_session, org1.id, serial="A1")
    a2 = _make_asset(db_session, org1.id, serial="A2")
    c1 = _make_component(db_session, org1.id, a1.id, component_type="MOTOR")
    c2 = _make_component(db_session, org1.id, a2.id, component_type="GPS")
    _make_signal(db_session, org1.id, key="s1", asset_id=a1.id, component_id=c1.id)
    _make_signal(db_session, org1.id, key="s2", asset_id=a2.id, component_id=c2.id)
    result = evaluate_fleet_hums_correlation(db_session, organization_id=org1.id)
    assert result.component_correlations == []


def test_missing_component_id_does_not_crash_correlation(db_session: Session, h8_3_env):
    org1 = h8_3_env["org1"]
    a = _make_asset(db_session, org1.id)
    _make_signal(db_session, org1.id, key="s1", asset_id=a.id, component_id=None)
    result = evaluate_fleet_hums_correlation(db_session, organization_id=org1.id)
    assert result.component_correlations == []
    assert result.affected_asset_count == 1


# ---------------------------------------------------------------------------
# Signal correlation: same type, different types, multiple severities
# ---------------------------------------------------------------------------


def test_same_signal_type_across_assets_and_severities(db_session: Session, h8_3_env):
    org1 = h8_3_env["org1"]
    a1 = _make_asset(db_session, org1.id, serial="A1")
    a2 = _make_asset(db_session, org1.id, serial="A2")
    _make_signal(db_session, org1.id, key="s1", asset_id=a1.id, signal_type="HUMS_EXCEEDANCE", severity="CRITICAL")
    _make_signal(db_session, org1.id, key="s2", asset_id=a2.id, signal_type="HUMS_EXCEEDANCE", severity="LOW")
    _make_signal(db_session, org1.id, key="s3", asset_id=a1.id, signal_type="TELEMETRY_FRESHNESS", severity="MEDIUM")
    result = evaluate_fleet_hums_correlation(db_session, organization_id=org1.id)
    assert result.total_active_signal_count == 3
    by_asset = {e.asset_id: e for e in result.asset_correlations}
    assert by_asset[a1.id].highest_signal_severity == "CRITICAL"
    assert by_asset[a2.id].highest_signal_severity == "LOW"


# ---------------------------------------------------------------------------
# Digital twin (H6) context
# ---------------------------------------------------------------------------


def test_affected_asset_with_component_context(db_session: Session, h8_3_env):
    org1 = h8_3_env["org1"]
    a = _make_asset(db_session, org1.id)
    _make_component(db_session, org1.id, a.id, name="C1")
    _make_component(db_session, org1.id, a.id, name="C2")
    _make_signal(db_session, org1.id, key="s1", asset_id=a.id)
    result = evaluate_fleet_hums_correlation(db_session, organization_id=org1.id)
    entry = {e.asset_id: e for e in result.asset_correlations}[a.id]
    assert entry.component_context_available is True
    assert entry.component_count == 2


def test_affected_asset_without_components(db_session: Session, h8_3_env):
    org1 = h8_3_env["org1"]
    a = _make_asset(db_session, org1.id)
    _make_signal(db_session, org1.id, key="s1", asset_id=a.id)
    result = evaluate_fleet_hums_correlation(db_session, organization_id=org1.id)
    entry = {e.asset_id: e for e in result.asset_correlations}[a.id]
    assert entry.component_context_available is True
    assert entry.component_count in (None, 0)


# ---------------------------------------------------------------------------
# Evidence completeness: complete / partial / missing (never fabricated)
# ---------------------------------------------------------------------------


def test_evidence_completeness_complete_when_multiple_sources(db_session: Session, h8_3_env):
    org1 = h8_3_env["org1"]
    a = _make_asset(db_session, org1.id)
    _make_signal(db_session, org1.id, key="s1", asset_id=a.id)
    _make_diagnostic(db_session, org1.id, asset_id=a.id)
    result = evaluate_fleet_hums_correlation(db_session, organization_id=org1.id)
    entry = {e.asset_id: e for e in result.asset_correlations}[a.id]
    assert entry.evidence_completeness == "COMPLETE"


def test_evidence_completeness_partial_when_single_source(db_session: Session, h8_3_env):
    org1 = h8_3_env["org1"]
    a = _make_asset(db_session, org1.id)
    _make_signal(db_session, org1.id, key="s1", asset_id=a.id)
    result = evaluate_fleet_hums_correlation(db_session, organization_id=org1.id)
    entry = {e.asset_id: e for e in result.asset_correlations}[a.id]
    assert entry.evidence_completeness == "PARTIAL"


def test_evidence_completeness_never_fabricated_for_unaffected_asset(db_session: Session, h8_3_env):
    org1 = h8_3_env["org1"]
    _make_asset(db_session, org1.id)
    result = evaluate_fleet_hums_correlation(db_session, organization_id=org1.id)
    # Unaffected assets simply are not in asset_correlations -- never a
    # fabricated "COMPLETE"/"HEALTHY" entry for missing evidence.
    assert result.asset_correlations == []


# ---------------------------------------------------------------------------
# Tenant isolation
# ---------------------------------------------------------------------------


def test_tenant_isolation(db_session: Session, h8_3_env):
    org1, org2 = h8_3_env["org1"], h8_3_env["org2"]
    a1 = _make_asset(db_session, org1.id, serial="T1")
    a2 = _make_asset(db_session, org2.id, serial="T2")
    _make_signal(db_session, org1.id, key="s1", asset_id=a1.id)
    _make_signal(db_session, org2.id, key="s2", asset_id=a2.id)
    _make_diagnostic(db_session, org1.id, asset_id=a1.id)
    _make_diagnostic(db_session, org2.id, asset_id=a2.id)

    result1 = evaluate_fleet_hums_correlation(db_session, organization_id=org1.id)
    result2 = evaluate_fleet_hums_correlation(db_session, organization_id=org2.id)

    assert result1.total_fleet_assets == 1
    assert result2.total_fleet_assets == 1
    asset_ids_1 = {e.asset_id for e in result1.asset_correlations}
    asset_ids_2 = {e.asset_id for e in result2.asset_correlations}
    assert a1.id in asset_ids_1 and a1.id not in asset_ids_2
    assert a2.id in asset_ids_2 and a2.id not in asset_ids_1


# ---------------------------------------------------------------------------
# Safety: no writes, no calls into mutating H4/H5/M7 functions
# ---------------------------------------------------------------------------


def test_no_db_mutation_calls_in_correlation_source():
    import app.services.intelligence.cross_asset_intelligence_service as svc

    source = inspect.getsource(svc)
    # Grep the whole module for db.add/session.add/.commit() -- H8.1/H8.2
    # already established this module never writes; H8.3 must not either.
    assert "db.add(" not in source
    assert "session.add(" not in source
    assert ".commit()" not in source


def test_no_calls_to_mutating_signal_diagnostic_prognostic_services():
    import app.services.intelligence.cross_asset_intelligence_service as svc

    source = inspect.getsource(svc)
    forbidden_calls = [
        "sync_and_get_signals(",
        "get_proactive_summary(",
        "confirm_candidate(",
        "reject_candidate(",
        "fit_degradation_model(",
        "calculate_fleet_rul(",
        "diagnose_fleet(",
    ]
    for call in forbidden_calls:
        assert call not in source, f"H8.3 must not call {call}"


def test_correlation_does_not_persist_results(db_session: Session, h8_3_env):
    org1 = h8_3_env["org1"]
    a = _make_asset(db_session, org1.id)
    _make_signal(db_session, org1.id, key="s1", asset_id=a.id)
    before_dirty = len(db_session.dirty)
    evaluate_fleet_hums_correlation(db_session, organization_id=org1.id)
    assert len(db_session.dirty) == before_dirty


# ---------------------------------------------------------------------------
# Correlation != causation: no diagnosis/root-cause/airworthiness language
# ---------------------------------------------------------------------------

_FORBIDDEN_PATTERNS = [
    r"root cause",
    r"defective",
    r"\bfailure\b",
    r"unsafe",
    r"unairworthy",
    r"not airworthy",
]


def _collect_string_fields(obj) -> list[str]:
    strings: list[str] = []
    if isinstance(obj, str):
        strings.append(obj)
    elif isinstance(obj, (list, tuple, set)):
        for item in obj:
            strings.extend(_collect_string_fields(item))
    elif isinstance(obj, dict):
        for v in obj.values():
            strings.extend(_collect_string_fields(v))
    elif hasattr(obj, "__dataclass_fields__"):
        for f in obj.__dataclass_fields__:
            strings.extend(_collect_string_fields(getattr(obj, f)))
    return strings


def test_no_causation_language_in_multi_source_scenario(db_session: Session, h8_3_env):
    org1 = h8_3_env["org1"]
    a1 = _make_asset(db_session, org1.id, serial="A1")
    a2 = _make_asset(db_session, org1.id, serial="A2")
    c1 = _make_component(db_session, org1.id, a1.id, component_type="MOTOR", model="X200")
    c2 = _make_component(db_session, org1.id, a2.id, component_type="MOTOR", model="X200")
    sensor1 = _make_sensor(db_session, org1.id, a1.id, component_id=c1.id, code="S1")

    _make_signal(db_session, org1.id, key="s1", asset_id=a1.id, component_id=c1.id, severity="CRITICAL")
    _make_signal(db_session, org1.id, key="s2", asset_id=a2.id, component_id=c2.id, severity="HIGH")
    _make_diagnostic(db_session, org1.id, asset_id=a1.id, component_id=c1.id, severity="HIGH")
    _make_prognostic(db_session, org1.id, asset_id=a1.id, sensor_id=sensor1.id, component_id=c1.id)

    result = evaluate_fleet_hums_correlation(db_session, organization_id=org1.id)
    all_strings = _collect_string_fields(result)
    combined = " ".join(all_strings).lower()
    for pattern in _FORBIDDEN_PATTERNS:
        assert not re.search(pattern, combined), f"Forbidden causation language matched: {pattern!r} in {combined!r}"


# ---------------------------------------------------------------------------
# Scenarios A through H: Synthetic Multi-Asset Correlation Test Suite
# ---------------------------------------------------------------------------


def test_scenario_a_similar_patterns_supported_correlation(db_session: Session, h8_3_env):
    """Scenario A: 3 compatible assets exhibit similar vibration anomaly patterns.
    Expected: High-confidence supported correlation with traceable evidence references.
    """
    org1 = h8_3_env["org1"]
    a1 = _make_asset(db_session, org1.id, serial="SCEN-A1")
    a2 = _make_asset(db_session, org1.id, serial="SCEN-A2")
    a3 = _make_asset(db_session, org1.id, serial="SCEN-A3")

    s1 = _make_sensor(db_session, org1.id, a1.id, code="S-A1", unit="g", sensor_type="VIBRATION")
    s2 = _make_sensor(db_session, org1.id, a2.id, code="S-A2", unit="g", sensor_type="VIBRATION")
    s3 = _make_sensor(db_session, org1.id, a3.id, code="S-A3", unit="g", sensor_type="VIBRATION")

    # 2 exceedances each with close observed values (mean ~0.65)
    _make_exceedance(db_session, org1.id, asset_id=a1.id, sensor_id=s1.id, observed_value=0.64)
    _make_exceedance(db_session, org1.id, asset_id=a1.id, sensor_id=s1.id, observed_value=0.65)
    _make_exceedance(db_session, org1.id, asset_id=a2.id, sensor_id=s2.id, observed_value=0.63)
    _make_exceedance(db_session, org1.id, asset_id=a2.id, sensor_id=s2.id, observed_value=0.66)
    _make_exceedance(db_session, org1.id, asset_id=a3.id, sensor_id=s3.id, observed_value=0.64)
    _make_exceedance(db_session, org1.id, asset_id=a3.id, sensor_id=s3.id, observed_value=0.65)

    _make_signal(db_session, org1.id, key="HUMS_EXCEEDANCE_vibration_rms_1", signal_type="HUMS_EXCEEDANCE", asset_id=a1.id)
    _make_signal(db_session, org1.id, key="HUMS_EXCEEDANCE_vibration_rms_2", signal_type="HUMS_EXCEEDANCE", asset_id=a2.id)

    result = evaluate_fleet_hums_correlation(db_session, organization_id=org1.id)
    assert len(result.anomaly_correlations) == 1
    corr = result.anomaly_correlations[0]
    assert corr.feature_family == "vibration_rms"
    assert corr.participating_asset_count == 3
    assert set(corr.participating_asset_ids) == {a1.id, a2.id, a3.id}
    assert corr.observation_count == 6
    assert corr.similarity_score >= 0.85
    assert corr.confidence == "HIGH"
    assert corr.lifecycle_status == "SUPPORTED"
    assert corr.sensor_compatibility == "COMPATIBLE"
    assert corr.operating_conditions_comparable is True
    assert len(corr.evidence_references) == 6
    assert len(corr.supporting_signal_ids) == 2
    assert "Statistical correlation" in corr.disclaimer


def test_scenario_b_isolated_anomaly_no_fleet_correlation(db_session: Session, h8_3_env):
    """Scenario B: Only one asset exhibits an abnormal pattern.
    Expected: No fleet-wide correlation fabricated for an isolated asset anomaly.
    """
    org1 = h8_3_env["org1"]
    a1 = _make_asset(db_session, org1.id, serial="SCEN-B1")
    _make_asset(db_session, org1.id, serial="SCEN-B2-nominal")

    s1 = _make_sensor(db_session, org1.id, a1.id, code="S-B1")
    _make_exceedance(db_session, org1.id, asset_id=a1.id, sensor_id=s1.id, observed_value=0.88)
    _make_exceedance(db_session, org1.id, asset_id=a1.id, sensor_id=s1.id, observed_value=0.92)

    result = evaluate_fleet_hums_correlation(db_session, organization_id=org1.id)
    # Exceedance on single asset must NOT be surfaced as a fleet-level correlation
    assert result.anomaly_correlations == []


def test_scenario_c_incompatible_sensors(db_session: Session, h8_3_env):
    """Scenario C: Participating assets have incompatible sensor units (e.g., 'g' vs 'mm/s').
    Expected: Incompatible sensor flag, similarity score 0.0, and INSUFFICIENT_EVIDENCE confidence.
    """
    org1 = h8_3_env["org1"]
    a1 = _make_asset(db_session, org1.id, serial="SCEN-C1")
    a2 = _make_asset(db_session, org1.id, serial="SCEN-C2")

    s1 = _make_sensor(db_session, org1.id, a1.id, code="S-C1", unit="g", sensor_type="VIBRATION")
    s2 = _make_sensor(db_session, org1.id, a2.id, code="S-C2", unit="mm/s", sensor_type="VIBRATION")

    _make_exceedance(db_session, org1.id, asset_id=a1.id, sensor_id=s1.id, parameter="vibration_peak", observed_value=1.5)
    _make_exceedance(db_session, org1.id, asset_id=a1.id, sensor_id=s1.id, parameter="vibration_peak", observed_value=1.6)
    _make_exceedance(db_session, org1.id, asset_id=a2.id, sensor_id=s2.id, parameter="vibration_peak", observed_value=1.5)
    _make_exceedance(db_session, org1.id, asset_id=a2.id, sensor_id=s2.id, parameter="vibration_peak", observed_value=1.6)

    result = evaluate_fleet_hums_correlation(db_session, organization_id=org1.id)
    assert len(result.anomaly_correlations) == 1
    corr = result.anomaly_correlations[0]
    assert corr.sensor_compatibility == "INCOMPATIBLE_UNITS"
    assert corr.confidence == "INSUFFICIENT_EVIDENCE"
    assert corr.similarity_score == 0.0
    assert any("mismatched units" in n for n in corr.uncertainty_notes)


def test_scenario_d_sparse_data(db_session: Session, h8_3_env):
    """Scenario D: Only 2 total observations exist across 2 assets.
    Expected: Insufficient evidence status, not an over-confident finding.
    """
    org1 = h8_3_env["org1"]
    a1 = _make_asset(db_session, org1.id, serial="SCEN-D1")
    a2 = _make_asset(db_session, org1.id, serial="SCEN-D2")

    s1 = _make_sensor(db_session, org1.id, a1.id, code="S-D1", unit="g")
    s2 = _make_sensor(db_session, org1.id, a2.id, code="S-D2", unit="g")

    _make_exceedance(db_session, org1.id, asset_id=a1.id, sensor_id=s1.id, parameter="vibration_rms", observed_value=0.7)
    _make_exceedance(db_session, org1.id, asset_id=a2.id, sensor_id=s2.id, parameter="vibration_rms", observed_value=0.72)

    result = evaluate_fleet_hums_correlation(db_session, organization_id=org1.id)
    assert len(result.anomaly_correlations) == 1
    corr = result.anomaly_correlations[0]
    assert corr.confidence == "INSUFFICIENT_EVIDENCE"
    assert corr.lifecycle_status == "CANDIDATE"
    assert any("Sparse observation count" in n for n in corr.uncertainty_notes)


def test_scenario_e_different_operating_conditions(db_session: Session, h8_3_env):
    """Scenario E: Assets exhibit similar vibration anomalies but occurred in divergent regimes.
    Expected: operating_conditions_comparable is False, confidence qualified to LOW.
    """
    org1 = h8_3_env["org1"]
    a1 = _make_asset(db_session, org1.id, serial="SCEN-E1")
    a2 = _make_asset(db_session, org1.id, serial="SCEN-E2")

    s1 = _make_sensor(db_session, org1.id, a1.id, code="S-E1")
    s2 = _make_sensor(db_session, org1.id, a2.id, code="S-E2")

    _make_exceedance(db_session, org1.id, asset_id=a1.id, sensor_id=s1.id, observed_value=0.65)
    _make_exceedance(db_session, org1.id, asset_id=a1.id, sensor_id=s1.id, observed_value=0.67)
    _make_exceedance(db_session, org1.id, asset_id=a2.id, sensor_id=s2.id, observed_value=0.66)
    # Divergent operational condition flag
    _make_exceedance(
        db_session, org1.id, asset_id=a2.id, sensor_id=s2.id, observed_value=0.64,
        contributing_reading_ids=["DIFFERENT_OPERATING_CONDITIONS"],
    )

    result = evaluate_fleet_hums_correlation(db_session, organization_id=org1.id)
    assert len(result.anomaly_correlations) == 1
    corr = result.anomaly_correlations[0]
    assert corr.operating_conditions_comparable is False
    assert corr.confidence == "LOW"
    assert any("divergent operational conditions" in n for n in corr.uncertainty_notes)


def test_scenario_f_repeated_evaluation_stability_and_no_duplicate_alerts(db_session: Session, h8_3_env):
    """Scenario F: Repeated correlation evaluations produce deterministic IDs and zero duplicate alerts.
    """
    org1 = h8_3_env["org1"]
    a1 = _make_asset(db_session, org1.id, serial="SCEN-F1")
    a2 = _make_asset(db_session, org1.id, serial="SCEN-F2")
    s1 = _make_sensor(db_session, org1.id, a1.id, code="S-F1")
    s2 = _make_sensor(db_session, org1.id, a2.id, code="S-F2")

    for _ in range(2):
        _make_exceedance(db_session, org1.id, asset_id=a1.id, sensor_id=s1.id, observed_value=0.65)
        _make_exceedance(db_session, org1.id, asset_id=a2.id, sensor_id=s2.id, observed_value=0.65)

    signals_before = db_session.query(ProactiveSignalRecord).count()

    eval1 = evaluate_fleet_hums_correlation(db_session, organization_id=org1.id)
    eval2 = evaluate_fleet_hums_correlation(db_session, organization_id=org1.id)

    assert len(eval1.anomaly_correlations) == 1
    assert len(eval2.anomaly_correlations) == 1
    # Deterministic stable UUIDv5 identity
    assert eval1.anomaly_correlations[0].id == eval2.anomaly_correlations[0].id

    signals_after = db_session.query(ProactiveSignalRecord).count()
    # Zero new signals or duplicate alerts created
    assert signals_after == signals_before


def test_scenario_g_tenant_isolation(db_session: Session, h8_3_env):
    """Scenario G: Identical data across two organizations does not cross tenant boundaries.
    """
    org1, org2 = h8_3_env["org1"], h8_3_env["org2"]

    a1_org1 = _make_asset(db_session, org1.id, serial="SCEN-G1-ORG1")
    a2_org1 = _make_asset(db_session, org1.id, serial="SCEN-G2-ORG1")
    s1_org1 = _make_sensor(db_session, org1.id, a1_org1.id, code="S-G1-1")
    s2_org1 = _make_sensor(db_session, org1.id, a2_org1.id, code="S-G2-1")
    for _ in range(2):
        _make_exceedance(db_session, org1.id, asset_id=a1_org1.id, sensor_id=s1_org1.id, observed_value=0.7)
        _make_exceedance(db_session, org1.id, asset_id=a2_org1.id, sensor_id=s2_org1.id, observed_value=0.7)

    a1_org2 = _make_asset(db_session, org2.id, serial="SCEN-G1-ORG2")
    a2_org2 = _make_asset(db_session, org2.id, serial="SCEN-G2-ORG2")
    s1_org2 = _make_sensor(db_session, org2.id, a1_org2.id, code="S-G1-2")
    s2_org2 = _make_sensor(db_session, org2.id, a2_org2.id, code="S-G2-2")
    for _ in range(2):
        _make_exceedance(db_session, org2.id, asset_id=a1_org2.id, sensor_id=s1_org2.id, observed_value=0.7)
        _make_exceedance(db_session, org2.id, asset_id=a2_org2.id, sensor_id=s2_org2.id, observed_value=0.7)

    eval1 = evaluate_fleet_hums_correlation(db_session, organization_id=org1.id)
    eval2 = evaluate_fleet_hums_correlation(db_session, organization_id=org2.id)

    assert len(eval1.anomaly_correlations) == 1
    assert len(eval2.anomaly_correlations) == 1
    assert set(eval1.anomaly_correlations[0].participating_asset_ids) == {a1_org1.id, a2_org1.id}
    assert set(eval2.anomaly_correlations[0].participating_asset_ids) == {a1_org2.id, a2_org2.id}
    assert a1_org2.id not in eval1.anomaly_correlations[0].participating_asset_ids
    assert a1_org1.id not in eval2.anomaly_correlations[0].participating_asset_ids


def test_scenario_h_simulation_versus_real_telemetry(db_session: Session, h8_3_env):
    """Scenario H: Simulation status is preserved and distinct from live telemetry.
    """
    org1 = h8_3_env["org1"]
    a1 = _make_asset(db_session, org1.id, serial="SCEN-H1-SIM")
    a2 = _make_asset(db_session, org1.id, serial="SCEN-H2-SIM")
    s1 = _make_sensor(db_session, org1.id, a1.id, code="S-H1", source="SIMULATED")
    s2 = _make_sensor(db_session, org1.id, a2.id, code="S-H2", source="SIMULATED")
    for _ in range(2):
        _make_exceedance(db_session, org1.id, asset_id=a1.id, sensor_id=s1.id, parameter="sim_rms", observed_value=0.6)
        _make_exceedance(db_session, org1.id, asset_id=a2.id, sensor_id=s2.id, parameter="sim_rms", observed_value=0.6)

    a3 = _make_asset(db_session, org1.id, serial="SCEN-H3-LIVE")
    a4 = _make_asset(db_session, org1.id, serial="SCEN-H4-LIVE")
    s3 = _make_sensor(db_session, org1.id, a3.id, code="S-H3", source="LIVE")
    s4 = _make_sensor(db_session, org1.id, a4.id, code="S-H4", source="LIVE")
    for _ in range(2):
        _make_exceedance(db_session, org1.id, asset_id=a3.id, sensor_id=s3.id, parameter="live_rms", observed_value=0.6)
        _make_exceedance(db_session, org1.id, asset_id=a4.id, sensor_id=s4.id, parameter="live_rms", observed_value=0.6)

    result = evaluate_fleet_hums_correlation(db_session, organization_id=org1.id)
    by_param = {c.feature_family: c for c in result.anomaly_correlations}
    assert by_param["sim_rms"].is_simulation is True
    assert by_param["live_rms"].is_simulation is False


def test_get_fleet_correlation_context_translation(db_session: Session, h8_3_env):
    """Verifies that get_fleet_correlation_context produces a fully populated, valid FleetCorrelationContext."""
    org1 = h8_3_env["org1"]
    a1 = _make_asset(db_session, org1.id, serial="TRANS-1")
    a2 = _make_asset(db_session, org1.id, serial="TRANS-2")
    s1 = _make_sensor(db_session, org1.id, a1.id, code="S-T1")
    s2 = _make_sensor(db_session, org1.id, a2.id, code="S-T2")
    for _ in range(2):
        _make_exceedance(db_session, org1.id, asset_id=a1.id, sensor_id=s1.id, observed_value=0.6)
        _make_exceedance(db_session, org1.id, asset_id=a2.id, sensor_id=s2.id, observed_value=0.6)

    context = get_fleet_correlation_context(db_session, organization_id=org1.id)
    assert context.total_fleet_assets == 2
    assert len(context.anomaly_correlations) == 1
    assert context.anomaly_correlations[0].confidence in ("MEDIUM", "HIGH")
    assert context.anomaly_correlations[0].similarity_score >= 0.8
    assert context.availability == "AVAILABLE"


def test_api_fleet_correlation_endpoints(client: TestClient, db_session: Session, h8_3_env):
    """Verifies GET /api/v1/intelligence/fleet/correlation and detail endpoint with auth & filters."""
    org1, user1 = h8_3_env["org1"], h8_3_env["user1"]
    a1 = _make_asset(db_session, org1.id, serial="API-A1")
    a2 = _make_asset(db_session, org1.id, serial="API-A2")
    s1 = _make_sensor(db_session, org1.id, a1.id, code="S-API1")
    s2 = _make_sensor(db_session, org1.id, a2.id, code="S-API2")

    for _ in range(2):
        _make_exceedance(db_session, org1.id, asset_id=a1.id, sensor_id=s1.id, parameter="vibration_rms", observed_value=0.65)
        _make_exceedance(db_session, org1.id, asset_id=a2.id, sensor_id=s2.id, parameter="vibration_rms", observed_value=0.65)

    token = create_access_token(
        user_id=user1.id,
        organization_id=org1.id,
        roles=["ORG_ADMIN"],
        email=user1.email,
        full_name=user1.full_name,
        email_verified=True,
    )
    headers = {"Authorization": f"Bearer {token}"}

    # 1. Fetch fleet correlation list
    resp = client.get("/api/v1/intelligence/fleet/correlation", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_fleet_assets"] >= 2
    assert len(data["anomaly_correlations"]) >= 1

    corr_id = data["anomaly_correlations"][0]["id"]

    # 2. Filter by confidence
    resp_filter = client.get(
        "/api/v1/intelligence/fleet/correlation?feature_family=vibration_rms", headers=headers
    )
    assert resp_filter.status_code == 200
    filter_data = resp_filter.json()
    assert len(filter_data["anomaly_correlations"]) >= 1

    # 3. Fetch single correlation detail
    resp_detail = client.get(f"/api/v1/intelligence/fleet/correlation/{corr_id}", headers=headers)
    assert resp_detail.status_code == 200
    detail_data = resp_detail.json()
    assert detail_data["id"] == corr_id
    assert detail_data["feature_family"] == "vibration_rms"
    assert len(detail_data["evidence_references"]) >= 2
    assert "Statistical correlation" in detail_data["disclaimer"]

    # 4. Unknown ID returns 404
    fake_id = uuid.uuid4()
    resp_404 = client.get(f"/api/v1/intelligence/fleet/correlation/{fake_id}", headers=headers)
    assert resp_404.status_code == 404

