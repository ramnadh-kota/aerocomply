"""Integration tests for H8.4 (Fleet MRO Intelligence).

H8.4 aggregates existing H7 asset-level MRO intelligence
(MaintenanceIntelligenceCandidate + H7's own compliance/readiness/
operational-impact/conflict read functions) into fleet context. It never
recreates H7's candidate generation, compliance evaluation, readiness
calculation, conflict detection, or maintenance recommendation logic --
see app.services.intelligence.cross_asset_intelligence_service
.evaluate_fleet_mro_aggregation and docs/H8_FLEET_HUMS_INTELLIGENCE.md's
H8.4 section.

Coverage: candidate aggregation (zero/one/multiple, same asset, across
assets), every H7 priority/type/status value, component correlation,
compliance impact (EVIDENCE_MISSING never becomes NON_COMPLIANT),
readiness impact (authoritative vs H7 impact kept separate), operational
impact, conflicts (never auto-resolved), the critical H8.3 no-inference
boundary, tenant isolation, and safety (no writes / no lifecycle-mutation
calls).
"""

from __future__ import annotations

import inspect
import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.models.asset import Asset, AssetType
from app.models.compliance import ComplianceObligation, ComplianceState, RegulatoryRequirement
from app.models.component import Component
from app.models.hums import HUMSDiagnosticCandidate
from app.models.mro_intelligence import (
    MaintenanceIntelligenceCandidate,
    MROCandidatePriority,
    MROCandidateStatus,
    MROCandidateType,
)
from app.models.organization import OnboardingStage, Organization, OrganizationStatus
from app.models.proactive_signal import ProactiveSignalRecord
from app.models.user import User, UserRole
from app.services.intelligence.cross_asset_intelligence_service import (
    evaluate_fleet_mro_aggregation,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def h8_4_env(db_session: Session):
    org1 = Organization(name="H8.4 Tenant One", status=OrganizationStatus.ACTIVE, onboarding_stage=OnboardingStage.ACTIVE)
    org2 = Organization(name="H8.4 Tenant Two", status=OrganizationStatus.ACTIVE, onboarding_stage=OnboardingStage.ACTIVE)
    db_session.add_all([org1, org2])
    db_session.flush()

    user1 = User(organization_id=org1.id, email="admin@h84tenant1.com", hashed_password=hash_password("Password123!"), full_name="Admin One", is_active=True)
    user2 = User(organization_id=org2.id, email="admin@h84tenant2.com", hashed_password=hash_password("Password123!"), full_name="Admin Two", is_active=True)
    db_session.add_all([user1, user2])
    db_session.flush()
    db_session.add(UserRole(user_id=user1.id, role_name="ORG_ADMIN", organization_id=org1.id))
    db_session.add(UserRole(user_id=user2.id, role_name="ORG_ADMIN", organization_id=org2.id))
    db_session.flush()

    return {"org1": org1, "user1": user1, "org2": org2, "user2": user2}


def _make_asset(db_session, org_id, serial="H84-ASSET-01"):
    a = Asset(organization_id=org_id, asset_type=AssetType.DRONE, serial_number=serial, status="ACTIVE")
    db_session.add(a)
    db_session.flush()
    return a


def _make_component(db_session, org_id, asset_id, *, component_type="MOTOR", model=None, name="Component"):
    c = Component(organization_id=org_id, asset_id=asset_id, component_type=component_type, name=name, model=model)
    db_session.add(c)
    db_session.flush()
    return c


def _make_candidate(
    db_session, org_id, *, asset_id, component_id=None,
    candidate_type=MROCandidateType.MAINTENANCE_ATTENTION, status=MROCandidateStatus.OPEN,
    priority=MROCandidatePriority.MEDIUM, operational_impact=None, dedup_suffix=None,
):
    c = MaintenanceIntelligenceCandidate(
        organization_id=org_id, asset_id=asset_id, component_id=component_id,
        candidate_type=candidate_type, status=status, priority=priority, confidence=0.6,
        reason="Test candidate reason.",
        dedup_key=f"dedup-{dedup_suffix or uuid.uuid4().hex}",
        source_lineage=[{"source_type": "Test", "source_id": None, "label": "test"}],
        operational_impact=operational_impact, data_freshness="AVAILABLE",
    )
    db_session.add(c)
    db_session.flush()
    return c


def _make_signal(db_session, org_id, *, key, signal_type="MAINTENANCE_THRESHOLD", severity="HIGH", status="OPEN", asset_id=None, component_id=None):
    rec = ProactiveSignalRecord(
        organization_id=org_id, signal_key=key, signal_type=signal_type, severity=severity, priority=severity,
        status=status, title=f"Signal {key}", headline=f"Headline {key}", detected_at=datetime.now(UTC),
        asset_id=asset_id, component_id=component_id,
    )
    db_session.add(rec)
    db_session.flush()
    return rec


def _make_diagnostic(db_session, org_id, *, asset_id, component_id=None, fault_code="FC-1", status="SUPPORTED", severity="MEDIUM"):
    d = HUMSDiagnosticCandidate(
        organization_id=org_id, asset_id=asset_id, component_id=component_id, sensor_ids=[],
        fault_code=fault_code, fault_name="Sample Fault", fault_domain="VIBRATION",
        diagnostic_method="rule_based_signature_matching", rule_version="h4.1", status=status, severity=severity,
        score=0.7, confidence="MEDIUM", primary_evidence=[], supporting_evidence=[], contradicting_evidence=[],
        explanation=["Sample rule matched."], detected_at=datetime.now(UTC),
    )
    db_session.add(d)
    db_session.flush()
    return d


def _make_compliance_obligation(db_session, org_id, asset_id, *, status=ComplianceState.OVERDUE.value):
    requirement = RegulatoryRequirement(
        organization_id=org_id, authority="FAA", requirement_number=f"REQ-{uuid.uuid4().hex[:6]}",
        title="Test Requirement", description="Test requirement description.",
    )
    db_session.add(requirement)
    db_session.flush()
    obligation = ComplianceObligation(
        organization_id=org_id, requirement_id=requirement.id, asset_id=asset_id, status=status,
    )
    db_session.add(obligation)
    db_session.flush()
    return obligation


# ---------------------------------------------------------------------------
# Candidate aggregation
# ---------------------------------------------------------------------------


def test_zero_assets_returns_data_unavailable(db_session: Session, h8_4_env):
    org1 = h8_4_env["org1"]
    result = evaluate_fleet_mro_aggregation(db_session, organization_id=org1.id)
    assert result.total_fleet_assets == 0
    assert result.availability == "DATA_UNAVAILABLE"
    assert result.candidates.candidate_count == 0


def test_zero_candidates_is_available_not_unavailable(db_session: Session, h8_4_env):
    org1 = h8_4_env["org1"]
    _make_asset(db_session, org1.id)
    result = evaluate_fleet_mro_aggregation(db_session, organization_id=org1.id)
    assert result.total_fleet_assets == 1
    assert result.availability == "AVAILABLE"
    assert result.candidates.candidate_count == 0
    assert result.candidates.affected_asset_count == 0


def test_one_candidate(db_session: Session, h8_4_env):
    org1 = h8_4_env["org1"]
    a = _make_asset(db_session, org1.id)
    _make_candidate(db_session, org1.id, asset_id=a.id)
    result = evaluate_fleet_mro_aggregation(db_session, organization_id=org1.id)
    assert result.candidates.candidate_count == 1
    assert result.candidates.affected_asset_count == 1


def test_multiple_candidates_same_asset(db_session: Session, h8_4_env):
    org1 = h8_4_env["org1"]
    a = _make_asset(db_session, org1.id)
    _make_candidate(db_session, org1.id, asset_id=a.id, dedup_suffix="c1")
    _make_candidate(db_session, org1.id, asset_id=a.id, dedup_suffix="c2")
    result = evaluate_fleet_mro_aggregation(db_session, organization_id=org1.id)
    assert result.candidates.candidate_count == 2
    assert result.candidates.affected_asset_count == 1


def test_multiple_candidates_across_assets(db_session: Session, h8_4_env):
    org1 = h8_4_env["org1"]
    a1 = _make_asset(db_session, org1.id, serial="A1")
    a2 = _make_asset(db_session, org1.id, serial="A2")
    _make_asset(db_session, org1.id, serial="A3-unaffected")
    _make_candidate(db_session, org1.id, asset_id=a1.id, dedup_suffix="c1")
    _make_candidate(db_session, org1.id, asset_id=a2.id, dedup_suffix="c2")
    result = evaluate_fleet_mro_aggregation(db_session, organization_id=org1.id)
    assert result.total_fleet_assets == 3
    assert result.candidates.candidate_count == 2
    assert result.candidates.affected_asset_count == 2


def test_every_priority_value_bucketed(db_session: Session, h8_4_env):
    org1 = h8_4_env["org1"]
    a = _make_asset(db_session, org1.id)
    _make_candidate(db_session, org1.id, asset_id=a.id, priority=MROCandidatePriority.HIGH, dedup_suffix="h")
    _make_candidate(db_session, org1.id, asset_id=a.id, priority=MROCandidatePriority.MEDIUM, dedup_suffix="m")
    _make_candidate(db_session, org1.id, asset_id=a.id, priority=MROCandidatePriority.LOW, dedup_suffix="l")
    result = evaluate_fleet_mro_aggregation(db_session, organization_id=org1.id)
    assert result.candidates.by_severity == {"HIGH": 1, "MEDIUM": 1, "LOW": 1}


def test_every_candidate_type_bucketed(db_session: Session, h8_4_env):
    org1 = h8_4_env["org1"]
    a = _make_asset(db_session, org1.id)
    for i, ctype in enumerate([
        MROCandidateType.INSPECTION_REVIEW, MROCandidateType.MAINTENANCE_ATTENTION,
        MROCandidateType.COMPLIANCE_REVIEW, MROCandidateType.CONFLICT_REVIEW,
    ]):
        _make_candidate(db_session, org1.id, asset_id=a.id, candidate_type=ctype, dedup_suffix=f"t{i}")
    result = evaluate_fleet_mro_aggregation(db_session, organization_id=org1.id)
    assert set(result.candidates.by_type.keys()) == {
        "INSPECTION_REVIEW", "MAINTENANCE_ATTENTION", "COMPLIANCE_REVIEW", "CONFLICT_REVIEW",
    }
    assert all(v == 1 for v in result.candidates.by_type.values())


def test_every_lifecycle_status_bucketed(db_session: Session, h8_4_env):
    org1 = h8_4_env["org1"]
    a = _make_asset(db_session, org1.id)
    statuses = [
        MROCandidateStatus.OPEN, MROCandidateStatus.UNDER_REVIEW, MROCandidateStatus.ACCEPTED,
        MROCandidateStatus.REJECTED, MROCandidateStatus.DEFERRED, MROCandidateStatus.RESOLVED,
    ]
    for i, status in enumerate(statuses):
        _make_candidate(db_session, org1.id, asset_id=a.id, status=status, dedup_suffix=f"s{i}")
    result = evaluate_fleet_mro_aggregation(db_session, organization_id=org1.id)
    assert result.candidates.by_status == {s: 1 for s in statuses}
    # candidate_count covers ALL statuses (full lifecycle reporting).
    assert result.candidates.candidate_count == 6
    # by_severity/by_type only reflect the ACTIVE subset (OPEN/UNDER_REVIEW/DEFERRED) == 3.
    assert sum(result.candidates.by_severity.values()) == 3


# ---------------------------------------------------------------------------
# Component correlation
# ---------------------------------------------------------------------------


def test_component_correlation_same_component_across_candidates(db_session: Session, h8_4_env):
    org1 = h8_4_env["org1"]
    a = _make_asset(db_session, org1.id)
    c = _make_component(db_session, org1.id, a.id, component_type="MOTOR")
    _make_candidate(db_session, org1.id, asset_id=a.id, component_id=c.id, dedup_suffix="c1")
    _make_candidate(db_session, org1.id, asset_id=a.id, component_id=c.id, dedup_suffix="c2")
    result = evaluate_fleet_mro_aggregation(db_session, organization_id=org1.id)
    assert len(result.component_correlations) == 1
    entry = result.component_correlations[0]
    assert entry.component_id == c.id
    assert entry.component_type == "MOTOR"
    assert entry.candidate_count == 2
    assert entry.affected_asset_count == 1


def test_component_correlation_different_components(db_session: Session, h8_4_env):
    org1 = h8_4_env["org1"]
    a = _make_asset(db_session, org1.id)
    c1 = _make_component(db_session, org1.id, a.id, name="C1", component_type="MOTOR")
    c2 = _make_component(db_session, org1.id, a.id, name="C2", component_type="GPS")
    _make_candidate(db_session, org1.id, asset_id=a.id, component_id=c1.id, dedup_suffix="c1")
    _make_candidate(db_session, org1.id, asset_id=a.id, component_id=c2.id, dedup_suffix="c2")
    result = evaluate_fleet_mro_aggregation(db_session, organization_id=org1.id)
    assert len(result.component_correlations) == 2


def test_component_correlation_missing_component(db_session: Session, h8_4_env):
    org1 = h8_4_env["org1"]
    a = _make_asset(db_session, org1.id)
    _make_candidate(db_session, org1.id, asset_id=a.id, component_id=None)
    result = evaluate_fleet_mro_aggregation(db_session, organization_id=org1.id)
    assert result.component_correlations == []


# ---------------------------------------------------------------------------
# Compliance impact
# ---------------------------------------------------------------------------


def test_compliance_impact_present(db_session: Session, h8_4_env):
    org1 = h8_4_env["org1"]
    a = _make_asset(db_session, org1.id)
    _make_candidate(db_session, org1.id, asset_id=a.id)
    _make_compliance_obligation(db_session, org1.id, a.id, status=ComplianceState.OVERDUE.value)
    result = evaluate_fleet_mro_aggregation(db_session, organization_id=org1.id)
    assert result.compliance_impact.availability == "AVAILABLE"
    assert result.compliance_impact.by_impact.get("OVERDUE") == 1
    assert result.compliance_impact.evidence_missing_asset_count == 0


def test_compliance_impact_evidence_missing_never_becomes_non_compliant(db_session: Session, h8_4_env):
    org1 = h8_4_env["org1"]
    a = _make_asset(db_session, org1.id)
    _make_candidate(db_session, org1.id, asset_id=a.id)
    # No compliance obligation at all -> H7's get_compliance_impact returns
    # overall_impact=UNKNOWN (evidence missing), never NON_COMPLIANT.
    result = evaluate_fleet_mro_aggregation(db_session, organization_id=org1.id)
    assert result.compliance_impact.by_impact.get("NON_COMPLIANT", 0) == 0
    assert result.compliance_impact.by_impact.get("UNKNOWN") == 1
    assert result.compliance_impact.evidence_missing_asset_count == 1


def test_compliance_impact_mixed_states(db_session: Session, h8_4_env):
    org1 = h8_4_env["org1"]
    a1 = _make_asset(db_session, org1.id, serial="A1")
    a2 = _make_asset(db_session, org1.id, serial="A2")
    _make_candidate(db_session, org1.id, asset_id=a1.id, dedup_suffix="c1")
    _make_candidate(db_session, org1.id, asset_id=a2.id, dedup_suffix="c2")
    _make_compliance_obligation(db_session, org1.id, a1.id, status=ComplianceState.NON_COMPLIANT.value)
    # a2 has no obligation -> UNKNOWN (evidence missing).
    result = evaluate_fleet_mro_aggregation(db_session, organization_id=org1.id)
    assert result.compliance_impact.by_impact.get("NON_COMPLIANT") == 1
    assert result.compliance_impact.by_impact.get("UNKNOWN") == 1
    assert result.compliance_impact.evidence_missing_asset_count == 1


# ---------------------------------------------------------------------------
# Readiness impact -- authoritative vs H7 impact kept SEPARATE
# ---------------------------------------------------------------------------


def test_readiness_impact_never_merges_authoritative_and_h7_impact(db_session: Session, h8_4_env):
    org1 = h8_4_env["org1"]
    a = _make_asset(db_session, org1.id)
    _make_candidate(db_session, org1.id, asset_id=a.id, priority=MROCandidatePriority.HIGH)
    result = evaluate_fleet_mro_aggregation(db_session, organization_id=org1.id)
    assert result.readiness_impact.availability == "AVAILABLE"
    # Two separate distributions must both be present and independently populated.
    assert isinstance(result.readiness_impact.by_readiness_impact, dict)
    assert isinstance(result.readiness_impact.by_authoritative_readiness_state, dict)
    assert sum(result.readiness_impact.by_authoritative_readiness_state.values()) == 1
    assert sum(result.readiness_impact.by_readiness_impact.values()) == 1


# ---------------------------------------------------------------------------
# Operational impact
# ---------------------------------------------------------------------------


def test_operational_impact_categorizes_existing_values(db_session: Session, h8_4_env):
    org1 = h8_4_env["org1"]
    a = _make_asset(db_session, org1.id)
    _make_candidate(db_session, org1.id, asset_id=a.id, operational_impact="HIGH", dedup_suffix="c1")
    _make_candidate(db_session, org1.id, asset_id=a.id, operational_impact="LOW", dedup_suffix="c2")
    _make_candidate(db_session, org1.id, asset_id=a.id, operational_impact=None, dedup_suffix="c3")
    result = evaluate_fleet_mro_aggregation(db_session, organization_id=org1.id)
    assert result.operational_impact.by_impact_level == {"HIGH": 1, "LOW": 1, "NOT_SET": 1}
    assert result.operational_impact.candidate_count == 3


# ---------------------------------------------------------------------------
# Conflicts -- reported only, never auto-resolved
# ---------------------------------------------------------------------------


def test_conflicts_aggregated_and_never_mutated(db_session: Session, h8_4_env):
    org1 = h8_4_env["org1"]
    a = _make_asset(db_session, org1.id)
    _make_candidate(db_session, org1.id, asset_id=a.id)
    # READY authoritative readiness (no blockers/no HUMS setup) + a
    # NON_COMPLIANT obligation triggers H7's READINESS_VS_COMPLIANCE conflict.
    _make_compliance_obligation(db_session, org1.id, a.id, status=ComplianceState.NON_COMPLIANT.value)
    before_count = db_session.query(MaintenanceIntelligenceCandidate).count()
    result = evaluate_fleet_mro_aggregation(db_session, organization_id=org1.id)
    after_count = db_session.query(MaintenanceIntelligenceCandidate).count()
    assert after_count == before_count
    assert result.conflicts.availability == "AVAILABLE"
    if result.conflicts.conflict_count:
        assert "READINESS_VS_COMPLIANCE" in result.conflicts.by_check_type


# ---------------------------------------------------------------------------
# THE critical H8.3 no-inference safety boundary
# ---------------------------------------------------------------------------


def test_hums_evidence_without_candidate_is_context_only(db_session: Session, h8_4_env):
    """An asset with an M7 signal but NO H7 MaintenanceIntelligenceCandidate
    must appear in hums_only_assets ONLY -- never as (or implying) a
    candidate."""
    org1 = h8_4_env["org1"]
    a = _make_asset(db_session, org1.id)
    _make_signal(db_session, org1.id, key="s1", asset_id=a.id, severity="HIGH")
    result = evaluate_fleet_mro_aggregation(db_session, organization_id=org1.id)

    assert result.candidates.candidate_count == 0
    assert result.candidates.affected_asset_count == 0
    assert len(result.hums_only_assets) == 1
    entry = result.hums_only_assets[0]
    assert entry.asset_id == a.id
    assert entry.active_signal_count == 1
    assert "no maintenance candidate" in entry.note.lower() or "no h7 maintenance intelligence candidate" in entry.note.lower()

    # No MRO-suggestive affirmative language anywhere in the summary for
    # this asset (the negated "no ... candidate exists" phrasing is fine;
    # an affirmative claim that a candidate/requirement exists is not).
    forbidden = ["maintenance is required", "recommend maintenance", "maintenance candidate found"]
    note_lower = entry.note.lower()
    for phrase in forbidden:
        assert phrase not in note_lower


def test_hums_evidence_and_diagnostic_without_candidate(db_session: Session, h8_4_env):
    org1 = h8_4_env["org1"]
    a = _make_asset(db_session, org1.id)
    _make_diagnostic(db_session, org1.id, asset_id=a.id)
    result = evaluate_fleet_mro_aggregation(db_session, organization_id=org1.id)
    assert result.candidates.candidate_count == 0
    entry = {e.asset_id: e for e in result.hums_only_assets}[a.id]
    assert entry.diagnostic_candidate_count == 1
    assert entry.active_signal_count == 0


def test_candidate_with_hums_correlation_shown_separately_not_merged(db_session: Session, h8_4_env):
    """When BOTH an H7 candidate and M7/H4 evidence exist for the same
    asset, the asset must NOT appear in hums_only_assets (its H7 candidate
    is the authoritative record) -- but the H8.3 correlation data is still
    available independently via evaluate_fleet_hums_correlation, never
    fabricated into the candidate aggregation itself."""
    org1 = h8_4_env["org1"]
    a = _make_asset(db_session, org1.id)
    _make_signal(db_session, org1.id, key="s1", asset_id=a.id)
    _make_candidate(db_session, org1.id, asset_id=a.id)
    result = evaluate_fleet_mro_aggregation(db_session, organization_id=org1.id)
    assert result.candidates.candidate_count == 1
    assert a.id not in {e.asset_id for e in result.hums_only_assets}


def test_h7_candidate_without_hums_correlation_shown_alone(db_session: Session, h8_4_env):
    org1 = h8_4_env["org1"]
    a = _make_asset(db_session, org1.id)
    _make_candidate(db_session, org1.id, asset_id=a.id)
    result = evaluate_fleet_mro_aggregation(db_session, organization_id=org1.id)
    assert result.candidates.candidate_count == 1
    assert result.hums_only_assets == []


def test_resolved_candidate_still_excludes_asset_from_hums_only(db_session: Session, h8_4_env):
    """Even a non-active (e.g. RESOLVED) candidate means H7 has already
    looked at this asset -- it must not be re-surfaced as 'no candidate
    exists' HUMS-only context."""
    org1 = h8_4_env["org1"]
    a = _make_asset(db_session, org1.id)
    _make_signal(db_session, org1.id, key="s1", asset_id=a.id)
    _make_candidate(db_session, org1.id, asset_id=a.id, status=MROCandidateStatus.RESOLVED)
    result = evaluate_fleet_mro_aggregation(db_session, organization_id=org1.id)
    assert a.id not in {e.asset_id for e in result.hums_only_assets}


# ---------------------------------------------------------------------------
# Tenant isolation
# ---------------------------------------------------------------------------


def test_tenant_isolation(db_session: Session, h8_4_env):
    org1, org2 = h8_4_env["org1"], h8_4_env["org2"]
    a1 = _make_asset(db_session, org1.id, serial="T1")
    a2 = _make_asset(db_session, org2.id, serial="T2")
    _make_candidate(db_session, org1.id, asset_id=a1.id, dedup_suffix="t1")
    _make_candidate(db_session, org2.id, asset_id=a2.id, dedup_suffix="t2")

    result1 = evaluate_fleet_mro_aggregation(db_session, organization_id=org1.id)
    result2 = evaluate_fleet_mro_aggregation(db_session, organization_id=org2.id)

    assert result1.total_fleet_assets == 1
    assert result2.total_fleet_assets == 1
    assert result1.candidates.candidate_count == 1
    assert result2.candidates.candidate_count == 1


# ---------------------------------------------------------------------------
# Safety: no writes, no calls into H7 lifecycle-mutation functions
# ---------------------------------------------------------------------------


def test_no_db_mutation_calls_in_service_source():
    import app.services.intelligence.cross_asset_intelligence_service as svc

    source = inspect.getsource(svc)
    assert "db.add(" not in source
    assert "session.add(" not in source
    assert ".commit()" not in source


def test_no_calls_to_h7_lifecycle_mutation_functions():
    import app.services.intelligence.cross_asset_intelligence_service as svc

    source = inspect.getsource(svc)
    forbidden_calls = [
        "generate_maintenance_candidates(",
        "accept_candidate(",
        "reject_candidate(",
        "review_candidate(",
        "defer_candidate(",
        "reconcile_asset_mro_intelligence(",
    ]
    for call in forbidden_calls:
        assert call not in source, f"H8.4 must not call {call}"


def test_aggregation_does_not_persist_results(db_session: Session, h8_4_env):
    org1 = h8_4_env["org1"]
    a = _make_asset(db_session, org1.id)
    _make_candidate(db_session, org1.id, asset_id=a.id)
    db_session.flush()
    before_dirty = len(db_session.dirty)
    evaluate_fleet_mro_aggregation(db_session, organization_id=org1.id)
    assert len(db_session.dirty) == before_dirty
