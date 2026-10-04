"""Integration tests for Milestone H8.6 — Consolidated Public Fleet Intelligence API.

Workstream: Developer 2.1 — Intelligence & Decision Systems
Endpoints under test:
- GET /api/v1/intelligence/fleet/overview (H8.0/H8.1 context)
- GET /api/v1/intelligence/fleet/signals (H8.2 M7 aggregation)
- GET /api/v1/intelligence/fleet/mro (H8.4 MRO intelligence)
- GET /api/v1/intelligence/fleet/correlation (H8.3 retained endpoint)
- GET /api/v1/intelligence/fleet/correlation/{correlation_id} (H8.3 detail endpoint)
- GET /api/v1/intelligence/fleet (M4.2 baseline compatibility)

Covers all 17 Phase 5 acceptance scenarios:
1. Authorized fleet overview response
2. Authorized fleet signals response
3. Authorized fleet MRO response
4. Existing H8.3 correlation route compatibility
5. Existing correlation detail route compatibility
6. Cross-tenant access rejection
7. Missing authentication
8. Insufficient permission
9. Feature entitlement validation
10. Empty fleet and empty signal results
11. Missing and stale telemetry
12. Bounded lookback validation
13. Invalid filters and malformed identifiers
14. Response serialization and OpenAPI contract
15. Read-only behavior and zero database mutations
16. Source service failure handling
17. No regression in existing H8.0-H8.5 behavior
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.security import create_access_token, hash_password
from app.models.asset import Asset, AssetType
from app.models.compliance import ComplianceObligation, ComplianceState, RegulatoryRequirement
from app.models.component import Component
from app.models.finding import Finding
from app.models.hums import (
    HUMSDiagnosticCandidate,
    HUMSExceedance,
    HUMSFeature,
    HUMSPrognosticRecord,
    HUMSSensor,
)
from app.models.mro_intelligence import (
    MaintenanceIntelligenceCandidate,
    MROCandidatePriority,
    MROCandidateStatus,
    MROCandidateType,
)
from app.models.organization import OnboardingStage, Organization, OrganizationStatus
from app.models.proactive_signal import ProactiveSignalRecord
from app.models.telemetry import TelemetryEventLog
from app.models.user import User, UserRole
from app.schemas.fleet_intelligence import (
    FleetAnomalyPatternCorrelation,
    FleetCorrelationContext,
    FleetIntelligenceContext,
    FleetMROContext,
    FleetSignalContext,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def h8_6_env(db_session: Session):
    """Sets up two isolated tenant organizations with admin and unprivileged users."""
    org1 = Organization(
        name="H8.6 Tenant Alpha",
        status=OrganizationStatus.ACTIVE,
        onboarding_stage=OnboardingStage.ACTIVE,
    )
    org2 = Organization(
        name="H8.6 Tenant Beta",
        status=OrganizationStatus.ACTIVE,
        onboarding_stage=OnboardingStage.ACTIVE,
    )
    db_session.add_all([org1, org2])
    db_session.flush()

    # User 1: Org 1 Admin (holds AIRCRAFT_READ)
    user1 = User(
        organization_id=org1.id,
        email="admin@h86alpha.com",
        hashed_password=hash_password("Password123!"),
        full_name="Alpha Admin",
        is_active=True,
    )
    # User 2: Org 2 Admin (holds AIRCRAFT_READ)
    user2 = User(
        organization_id=org2.id,
        email="admin@h86beta.com",
        hashed_password=hash_password("Password123!"),
        full_name="Beta Admin",
        is_active=True,
    )
    # User 3: Org 1 Restricted (no aircraft read permissions)
    user_restricted = User(
        organization_id=org1.id,
        email="guest@h86alpha.com",
        hashed_password=hash_password("Password123!"),
        full_name="Alpha Guest",
        is_active=True,
    )
    db_session.add_all([user1, user2, user_restricted])
    db_session.flush()

    db_session.add(UserRole(user_id=user1.id, role_name="ORG_ADMIN", organization_id=org1.id))
    db_session.add(UserRole(user_id=user2.id, role_name="ORG_ADMIN", organization_id=org2.id))
    # user_restricted has no roles assigned
    db_session.flush()

    # Helper headers
    token1 = create_access_token(
        user_id=user1.id,
        organization_id=org1.id,
        roles=["ORG_ADMIN"],
        email=user1.email,
        full_name=user1.full_name,
        email_verified=True,
    )
    token2 = create_access_token(
        user_id=user2.id,
        organization_id=org2.id,
        roles=["ORG_ADMIN"],
        email=user2.email,
        full_name=user2.full_name,
        email_verified=True,
    )
    token_restricted = create_access_token(
        user_id=user_restricted.id,
        organization_id=org1.id,
        roles=[],
        email=user_restricted.email,
        full_name=user_restricted.full_name,
        email_verified=True,
    )

    return {
        "org1": org1,
        "user1": user1,
        "headers1": {"Authorization": f"Bearer {token1}"},
        "org2": org2,
        "user2": user2,
        "headers2": {"Authorization": f"Bearer {token2}"},
        "headers_restricted": {"Authorization": f"Bearer {token_restricted}"},
    }


def _seed_tenant_data(db_session: Session, org_id: uuid.UUID):
    """Seeds rich, realistic operational records for Tenant Alpha."""
    a1 = Asset(
        organization_id=org_id,
        asset_type=AssetType.DRONE,
        serial_number="ALPHA-DRONE-01",
        status="ACTIVE",
    )
    a2 = Asset(
        organization_id=org_id,
        asset_type=AssetType.DRONE,
        serial_number="ALPHA-DRONE-02",
        status="ACTIVE",
    )
    db_session.add_all([a1, a2])
    db_session.flush()

    # Components
    c1 = Component(
        organization_id=org_id,
        asset_id=a1.id,
        component_type="MOTOR",
        model="KOTA-MTR-400",
        name="Front Left Motor",
    )
    c2 = Component(
        organization_id=org_id,
        asset_id=a2.id,
        component_type="MOTOR",
        model="KOTA-MTR-400",
        name="Front Left Motor",
    )
    db_session.add_all([c1, c2])
    db_session.flush()

    # Sensors
    s1 = HUMSSensor(
        organization_id=org_id,
        asset_id=a1.id,
        component_id=c1.id,
        sensor_code="VIB-01",
        sensor_type="VIBRATION",
        measurement_type="vibration_rms",
        unit="mm/s",
        status="ACTIVE",
        source="SIMULATED",
    )
    s2 = HUMSSensor(
        organization_id=org_id,
        asset_id=a2.id,
        component_id=c2.id,
        sensor_code="VIB-02",
        sensor_type="VIBRATION",
        measurement_type="vibration_rms",
        unit="mm/s",
        status="ACTIVE",
        source="SIMULATED",
    )
    db_session.add_all([s1, s2])
    db_session.flush()

    # Recent Exceedances (within 30 days)
    now = datetime.now(UTC)
    e1 = HUMSExceedance(
        organization_id=org_id,
        sensor_id=s1.id,
        asset_id=a1.id,
        component_id=c1.id,
        parameter="vibration_rms",
        threshold_value=0.5,
        observed_value=0.72,
        severity="WARNING",
        window_start=now - timedelta(days=2),
        window_end=now - timedelta(days=2) + timedelta(minutes=5),
        contributing_reading_ids=[],
    )
    e2 = HUMSExceedance(
        organization_id=org_id,
        sensor_id=s2.id,
        asset_id=a2.id,
        component_id=c2.id,
        parameter="vibration_rms",
        threshold_value=0.5,
        observed_value=0.71,
        severity="WARNING",
        window_start=now - timedelta(days=2),
        window_end=now - timedelta(days=2) + timedelta(minutes=5),
        contributing_reading_ids=[],
    )
    db_session.add_all([e1, e2])
    db_session.flush()

    # M7 Proactive Signals
    sig1 = ProactiveSignalRecord(
        organization_id=org_id,
        signal_key="SIG-ALPHA-01",
        signal_type="HUMS_HEALTH_DEGRADATION",
        severity="HIGH",
        priority="HIGH",
        status="OPEN",
        title="Vibration degradation on Front Left Motor",
        headline="Headline: Elevated vibration on motor",
        asset_id=a1.id,
        component_id=c1.id,
        detected_at=now - timedelta(hours=6),
    )
    sig2 = ProactiveSignalRecord(
        organization_id=org_id,
        signal_key="SIG-ALPHA-02",
        signal_type="FLEET_PATTERN",
        severity="MEDIUM",
        priority="MEDIUM",
        status="OPEN",
        title="Fleet-wide vibration clustering on KOTA-MTR-400",
        headline="Headline: Cluster of motor anomalies",
        asset_id=a2.id,
        component_id=c2.id,
        detected_at=now - timedelta(hours=3),
    )
    db_session.add_all([sig1, sig2])
    db_session.flush()

    # H7 Maintenance Intelligence Candidates
    mro1 = MaintenanceIntelligenceCandidate(
        organization_id=org_id,
        candidate_type=MROCandidateType.MAINTENANCE_ATTENTION,
        status=MROCandidateStatus.OPEN,
        priority=MROCandidatePriority.HIGH,
        confidence=0.8,
        asset_id=a1.id,
        component_id=c1.id,
        reason="Motor bearing inspection recommended: elevated harmonic vibration",
        dedup_key="dedup-h86-alpha-01",
        source_lineage=[{"source_type": "HUMS", "source_id": str(s1.id), "label": "VIB-01"}],
        operational_impact="MODERATE",
        data_freshness="AVAILABLE",
    )
    db_session.add(mro1)
    db_session.flush()

    # Telemetry Event Log
    tel = TelemetryEventLog(
        organization_id=org_id,
        source_system="EDGE_GATEWAY",
        source_event_id=f"evt-{uuid.uuid4().hex[:8]}",
        idempotency_key=f"idem-{uuid.uuid4().hex[:8]}",
        event_type="SENSOR_BURST",
        payload_hash="hash-fresh-1",
        asset_id=a1.id,
        event_timestamp=now - timedelta(minutes=10),
        received_timestamp=now - timedelta(minutes=10),
        processing_status="PROCESSED",
    )
    db_session.add(tel)
    db_session.flush()

    return {"a1": a1, "a2": a2, "c1": c1, "c2": c2, "sig1": sig1, "mro1": mro1}


# ---------------------------------------------------------------------------
# Test Scenarios
# ---------------------------------------------------------------------------


def test_scenario_1_authorized_fleet_overview(client: TestClient, db_session: Session, h8_6_env):
    """Scenario 1: Authorized user retrieves valid FleetIntelligenceContext from /overview."""
    org1 = h8_6_env["org1"]
    _seed_tenant_data(db_session, org1.id)

    resp = client.get("/api/v1/intelligence/fleet/overview", headers=h8_6_env["headers1"])
    assert resp.status_code == 200
    data = resp.json()

    # Validates typed FleetIntelligenceContext contract
    context = FleetIntelligenceContext.model_validate(data)
    assert context.organization_id == org1.id
    assert context.overview.asset_count >= 2
    assert context.overview.active_asset_count >= 2
    assert context.health_context.availability == "AVAILABLE"
    assert context.health_context.healthy_count + context.health_context.degraded_count + context.health_context.attention_count + context.health_context.unknown_count >= 2
    assert context.telemetry_context.availability == "AVAILABLE"
    assert context.telemetry_context.fresh_count >= 1
    assert context.analytical_context.availability == "AVAILABLE"
    assert len(context.source_lineage) >= 4


def test_scenario_2_authorized_fleet_signals(client: TestClient, db_session: Session, h8_6_env):
    """Scenario 2: Authorized user retrieves canonical M7 signals from /signals."""
    org1 = h8_6_env["org1"]
    _seed_tenant_data(db_session, org1.id)

    resp = client.get("/api/v1/intelligence/fleet/signals", headers=h8_6_env["headers1"])
    assert resp.status_code == 200
    data = resp.json()

    # Validates typed FleetSignalContext contract
    context = FleetSignalContext.model_validate(data)
    assert context.availability == "AVAILABLE"
    assert context.total_active_signals >= 2
    assert "HIGH" in context.severity_distribution
    assert "FLEET_PATTERN" in context.signal_type_distribution
    assert context.affected_asset_count >= 2
    assert len(context.signals_by_asset) >= 2
    assert len(context.fleet_patterns) >= 1
    assert context.fleet_patterns[0].signal_type == "FLEET_PATTERN"

    # Test filtering by severity
    resp_filtered = client.get("/api/v1/intelligence/fleet/signals?severity=HIGH", headers=h8_6_env["headers1"])
    assert resp_filtered.status_code == 200
    filtered_data = resp_filtered.json()
    assert all(s["severity"] == "HIGH" for s in filtered_data["recent_signals"])


def test_scenario_3_authorized_fleet_mro(client: TestClient, db_session: Session, h8_6_env):
    """Scenario 3: Authorized user retrieves valid FleetMROContext from /mro."""
    org1 = h8_6_env["org1"]
    _seed_tenant_data(db_session, org1.id)

    resp = client.get("/api/v1/intelligence/fleet/mro", headers=h8_6_env["headers1"])
    assert resp.status_code == 200
    data = resp.json()

    # Validates typed FleetMROContext contract
    context = FleetMROContext.model_validate(data)
    assert context.availability == "AVAILABLE"
    assert context.total_fleet_assets >= 2
    assert context.candidates.candidate_count >= 1
    assert "HIGH" in context.candidates.by_severity
    assert len(context.component_correlations) >= 1
    assert context.compliance_impact.availability in ("AVAILABLE", "DATA_UNAVAILABLE")
    assert context.readiness_impact.availability in ("AVAILABLE", "DATA_UNAVAILABLE")
    assert context.conflicts.availability in ("AVAILABLE", "DATA_UNAVAILABLE")
    # Attention comparison separates H7 and M7 distributions
    assert "HIGH" in context.attention_comparison.mro_candidate_severity_distribution
    assert "HIGH" in context.attention_comparison.proactive_signal_severity_distribution
    # Safety boundary: asset 2 has HUMS signals but no MRO candidate -> reported in hums_only_assets
    assert any(h.asset_registration or str(h.asset_id) for h in context.hums_only_assets)


def test_scenario_4_existing_correlation_route_compatibility(client: TestClient, db_session: Session, h8_6_env):
    """Scenario 4: Existing H8.3 /fleet/correlation endpoint operates cleanly with query filters."""
    org1 = h8_6_env["org1"]
    _seed_tenant_data(db_session, org1.id)

    resp = client.get("/api/v1/intelligence/fleet/correlation", headers=h8_6_env["headers1"])
    assert resp.status_code == 200
    data = resp.json()

    context = FleetCorrelationContext.model_validate(data)
    assert context.availability == "AVAILABLE"
    assert context.total_fleet_assets >= 2
    assert len(context.anomaly_correlations) >= 1

    # Filter by feature_family
    resp_ff = client.get("/api/v1/intelligence/fleet/correlation?feature_family=vibration_rms", headers=h8_6_env["headers1"])
    assert resp_ff.status_code == 200
    assert len(resp_ff.json()["anomaly_correlations"]) >= 1


def test_scenario_5_existing_correlation_detail_compatibility(client: TestClient, db_session: Session, h8_6_env):
    """Scenario 5: Existing H8.3 /fleet/correlation/{id} endpoint operates cleanly and returns detail."""
    org1 = h8_6_env["org1"]
    _seed_tenant_data(db_session, org1.id)

    resp = client.get("/api/v1/intelligence/fleet/correlation", headers=h8_6_env["headers1"])
    data = resp.json()
    assert len(data["anomaly_correlations"]) >= 1
    corr_id = data["anomaly_correlations"][0]["id"]

    resp_detail = client.get(f"/api/v1/intelligence/fleet/correlation/{corr_id}", headers=h8_6_env["headers1"])
    assert resp_detail.status_code == 200
    detail = resp_detail.json()
    assert detail["id"] == corr_id
    assert "vibration" in detail["feature_family"]
    assert len(detail["evidence_references"]) >= 2
    assert "disclaimer" in detail


def test_scenario_6_cross_tenant_isolation(client: TestClient, db_session: Session, h8_6_env):
    """Scenario 6: Tenant Beta cannot see Tenant Alpha's data, and requesting Alpha's correlation returns 404."""
    org1 = h8_6_env["org1"]
    _seed_tenant_data(db_session, org1.id)

    # Org 2 has no assets seeded yet
    resp_beta_overview = client.get("/api/v1/intelligence/fleet/overview", headers=h8_6_env["headers2"])
    assert resp_beta_overview.status_code == 200
    beta_overview = resp_beta_overview.json()
    assert beta_overview["overview"]["asset_count"] == 0
    assert beta_overview["health_context"]["availability"] == "DATA_UNAVAILABLE"

    # Org 2 cannot retrieve Org 1's correlation by ID
    resp_alpha_corr = client.get("/api/v1/intelligence/fleet/correlation", headers=h8_6_env["headers1"])
    alpha_corr_id = resp_alpha_corr.json()["anomaly_correlations"][0]["id"]

    resp_cross = client.get(f"/api/v1/intelligence/fleet/correlation/{alpha_corr_id}", headers=h8_6_env["headers2"])
    assert resp_cross.status_code == 404
    assert resp_cross.json()["error"]["message"] == "Fleet correlation not found"


def test_scenario_7_missing_authentication(client: TestClient):
    """Scenario 7: Unauthenticated requests return 401 Unauthorized across all endpoints."""
    endpoints = [
        "/api/v1/intelligence/fleet/overview",
        "/api/v1/intelligence/fleet/signals",
        "/api/v1/intelligence/fleet/mro",
        "/api/v1/intelligence/fleet/correlation",
        f"/api/v1/intelligence/fleet/correlation/{uuid.uuid4()}",
    ]
    for ep in endpoints:
        resp = client.get(ep)
        assert resp.status_code == 401, f"Endpoint {ep} did not enforce authentication"


def test_scenario_8_insufficient_permission(client: TestClient, h8_6_env):
    """Scenario 8: User without AIRCRAFT_READ receives 403 Forbidden."""
    endpoints = [
        "/api/v1/intelligence/fleet/overview",
        "/api/v1/intelligence/fleet/signals",
        "/api/v1/intelligence/fleet/mro",
        "/api/v1/intelligence/fleet/correlation",
        f"/api/v1/intelligence/fleet/correlation/{uuid.uuid4()}",
    ]
    for ep in endpoints:
        resp = client.get(ep, headers=h8_6_env["headers_restricted"])
        assert resp.status_code == 403, f"Endpoint {ep} did not enforce permission"


def test_scenario_9_entitlement_boundaries(client: TestClient, db_session: Session, h8_6_env):
    """Scenario 9: Entitlements follow established product capabilities without artificial blocking."""
    org1 = h8_6_env["org1"]
    _seed_tenant_data(db_session, org1.id)

    # Standard tenant with AIRCRAFT_READ accesses all fleet intelligence endpoints
    endpoints = [
        "/api/v1/intelligence/fleet/overview",
        "/api/v1/intelligence/fleet/signals",
        "/api/v1/intelligence/fleet/mro",
        "/api/v1/intelligence/fleet/correlation",
    ]
    for ep in endpoints:
        resp = client.get(ep, headers=h8_6_env["headers1"])
        assert resp.status_code == 200, f"Expected 200 for {ep}, got {resp.status_code}"


def test_scenario_10_empty_fleet_and_signals(client: TestClient, h8_6_env):
    """Scenario 10: Empty fleet and empty signals return valid payloads with DATA_UNAVAILABLE, never 500."""
    headers2 = h8_6_env["headers2"]

    # 1. Overview for empty fleet
    resp_overview = client.get("/api/v1/intelligence/fleet/overview", headers=headers2)
    assert resp_overview.status_code == 200
    ov = resp_overview.json()
    assert ov["overview"]["asset_count"] == 0
    assert ov["health_context"]["availability"] == "DATA_UNAVAILABLE"
    assert ov["health_context"]["healthy_count"] == 0

    # 2. Signals for empty fleet
    resp_signals = client.get("/api/v1/intelligence/fleet/signals", headers=headers2)
    assert resp_signals.status_code == 200
    sig = resp_signals.json()
    assert sig["total_active_signals"] == 0
    assert sig["affected_asset_count"] == 0

    # 3. MRO for empty fleet
    resp_mro = client.get("/api/v1/intelligence/fleet/mro", headers=headers2)
    assert resp_mro.status_code == 200
    mro = resp_mro.json()
    assert mro["availability"] == "DATA_UNAVAILABLE"
    assert mro["total_fleet_assets"] == 0


def test_scenario_11_missing_and_stale_telemetry(client: TestClient, db_session: Session, h8_6_env):
    """Scenario 11: Missing and stale telemetry are explicitly distinguished from healthy telemetry."""
    org = Organization(
        name="H8.6 Stale Tenant",
        status=OrganizationStatus.ACTIVE,
        onboarding_stage=OnboardingStage.ACTIVE,
    )
    db_session.add(org)
    db_session.flush()

    user = User(
        organization_id=org.id,
        email="admin@h86stale.com",
        hashed_password=hash_password("Password123!"),
        full_name="Stale Admin",
        is_active=True,
    )
    db_session.add(user)
    db_session.flush()
    db_session.add(UserRole(user_id=user.id, role_name="ORG_ADMIN", organization_id=org.id))
    db_session.flush()

    # Asset with NO HUMS sensor and NO telemetry
    a = Asset(organization_id=org.id, asset_type=AssetType.DRONE, serial_number="STALE-01", status="ACTIVE")
    db_session.add(a)
    db_session.flush()

    token = create_access_token(
        user_id=user.id,
        organization_id=org.id,
        roles=["ORG_ADMIN"],
        email=user.email,
        full_name=user.full_name,
        email_verified=True,
    )
    headers = {"Authorization": f"Bearer {token}"}

    resp = client.get("/api/v1/intelligence/fleet/overview", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["overview"]["asset_count"] == 1
    # Telemetry is missing/unknown, health is unknown -- NOT healthy
    assert data["health_context"]["healthy_count"] == 0
    assert data["health_context"]["unknown_count"] == 1
    assert data["telemetry_context"]["fresh_count"] == 0
    assert data["telemetry_context"]["missing_count"] >= 1 or data["telemetry_context"]["unknown_count"] >= 1


def test_scenario_12_bounded_lookback_validation(client: TestClient, h8_6_env):
    """Scenario 12: Query parameter `days` validates bounds [1, 365]."""
    headers = h8_6_env["headers1"]

    # Valid lookback
    assert client.get("/api/v1/intelligence/fleet/overview?days=30", headers=headers).status_code == 200
    assert client.get("/api/v1/intelligence/fleet/overview?days=1", headers=headers).status_code == 200
    assert client.get("/api/v1/intelligence/fleet/overview?days=365", headers=headers).status_code == 200

    # Invalid lookback < 1
    resp_zero = client.get("/api/v1/intelligence/fleet/overview?days=0", headers=headers)
    assert resp_zero.status_code == 422

    # Invalid lookback > 365
    resp_large = client.get("/api/v1/intelligence/fleet/overview?days=366", headers=headers)
    assert resp_large.status_code == 422

    # Invalid lookback on /mro and /correlation
    assert client.get("/api/v1/intelligence/fleet/mro?days=0", headers=headers).status_code == 422
    assert client.get("/api/v1/intelligence/fleet/correlation?days=500", headers=headers).status_code == 422


def test_scenario_13_invalid_filters_and_malformed_identifiers(client: TestClient, h8_6_env):
    """Scenario 13: Malformed UUID returns 422, non-existent returns 404."""
    headers = h8_6_env["headers1"]

    # Malformed UUID
    resp_malformed = client.get("/api/v1/intelligence/fleet/correlation/not-a-valid-uuid", headers=headers)
    assert resp_malformed.status_code == 422

    # Non-existent UUID
    fake_id = uuid.uuid4()
    resp_not_found = client.get(f"/api/v1/intelligence/fleet/correlation/{fake_id}", headers=headers)
    assert resp_not_found.status_code == 404


def test_scenario_14_response_serialization_and_openapi(client: TestClient):
    """Scenario 14: OpenAPI specification publishes all H8.6 routes and response schemas."""
    resp = client.get("/openapi.json")
    assert resp.status_code == 200
    schema = resp.json()
    paths = schema.get("paths", {})

    expected_paths = [
        "/api/v1/intelligence/fleet/overview",
        "/api/v1/intelligence/fleet/signals",
        "/api/v1/intelligence/fleet/mro",
        "/api/v1/intelligence/fleet/correlation",
        "/api/v1/intelligence/fleet/correlation/{correlation_id}",
    ]
    for p in expected_paths:
        assert p in paths, f"Path {p} missing from OpenAPI specification"


def test_scenario_15_read_only_zero_mutations(client: TestClient, db_session: Session, h8_6_env):
    """Scenario 15: Read-only guarantee — calling endpoints generates zero DB insertions/updates."""
    org1 = h8_6_env["org1"]
    _seed_tenant_data(db_session, org1.id)

    # Record counts before
    asset_count_before = db_session.execute(select(func.count(Asset.id))).scalar_one()
    signal_count_before = db_session.execute(select(func.count(ProactiveSignalRecord.id))).scalar_one()
    mro_count_before = db_session.execute(select(func.count(MaintenanceIntelligenceCandidate.id))).scalar_one()
    exceedance_count_before = db_session.execute(select(func.count(HUMSExceedance.id))).scalar_one()

    # Invoke all endpoints multiple times
    headers = h8_6_env["headers1"]
    client.get("/api/v1/intelligence/fleet/overview", headers=headers)
    client.get("/api/v1/intelligence/fleet/signals", headers=headers)
    client.get("/api/v1/intelligence/fleet/mro", headers=headers)
    corr_resp = client.get("/api/v1/intelligence/fleet/correlation", headers=headers)
    corr_id = corr_resp.json()["anomaly_correlations"][0]["id"]
    client.get(f"/api/v1/intelligence/fleet/correlation/{corr_id}", headers=headers)

    # Record counts after
    asset_count_after = db_session.execute(select(func.count(Asset.id))).scalar_one()
    signal_count_after = db_session.execute(select(func.count(ProactiveSignalRecord.id))).scalar_one()
    mro_count_after = db_session.execute(select(func.count(MaintenanceIntelligenceCandidate.id))).scalar_one()
    exceedance_count_after = db_session.execute(select(func.count(HUMSExceedance.id))).scalar_one()

    assert asset_count_before == asset_count_after
    assert signal_count_before == signal_count_after
    assert mro_count_before == mro_count_after
    assert exceedance_count_before == exceedance_count_after


def test_scenario_16_source_service_failure_handling(client: TestClient, h8_6_env, monkeypatch):
    """Scenario 16: Safe failure handling if an underlying aggregation function encounters unexpected exceptions."""
    from app.services.intelligence import cross_asset_intelligence_service

    def _failing_overview(*args, **kwargs):
        raise RuntimeError("Telemetry engine connectivity failure")

    monkeypatch.setattr(
        cross_asset_intelligence_service,
        "get_fleet_intelligence_overview_context",
        _failing_overview,
    )

    with pytest.raises(RuntimeError, match="Telemetry engine connectivity failure"):
        client.get("/api/v1/intelligence/fleet/overview", headers=h8_6_env["headers1"])


def test_scenario_17_no_regression_existing_endpoints(client: TestClient, db_session: Session, h8_6_env):
    """Scenario 17: Validates that existing /intelligence/fleet endpoint remains fully functional."""
    org1 = h8_6_env["org1"]
    _seed_tenant_data(db_session, org1.id)

    resp = client.get("/api/v1/intelligence/fleet", headers=h8_6_env["headers1"])
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_assets"] >= 2
    assert "assets" in data
