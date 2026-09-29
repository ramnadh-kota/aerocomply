"""M17: End-to-End Live Telemetry to Grounded Aerospace Intelligence Integration Test.

Verifies the complete, unbroken, deterministic 9-step intelligence chain:
    Canonical Telemetry
            ↓
    Real-Time Processing
            ↓
    Feature Extraction (Time + Frequency Domain)
            ↓
    Baseline Engine (Statistical Bounds & Deviations)
            ↓
    Exceedance & Anomaly Detection
            ↓
    Finding Creation & Evidence Linkage
            ↓
    Diagnostic Engine (Fault Signature Matching)
            ↓
    Prognostics & RUL Engine (Trajectory Fitting & Safety Limits)
            ↓
    M7 Proactive Intelligence Signals
            ↓
    LISA Grounded AI Context & Tool Grounding
            ↓
    Kota Control Center

Covers:
- Step 1: Healthy baseline telemetry (zero false critical alerts)
- Step 2: Controlled rising vibration anomaly (feature trend, baseline breach, exceedance)
- Step 3: Finding creation with full evidence provenance
- Step 4: Diagnostic fault signature correlation (Bearing Degradation hypothesis)
- Step 5: Degradation trajectory fitting & RUL prognostics
- Step 6: M7 Proactive Signal generation & lifecycle
- Step 7: Grounded LISA tool query validation
- Step 8: Telemetry staleness & freshness policy enforcement (never assume healthy when silent)
- Step 9: Telemetry stream recovery
- Step 10: Deterministic idempotency, duplicate protection, and multi-tenant isolation
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.models.asset import Asset, AssetType
from app.models.component import Component
from app.models.evidence import Evidence
from app.models.finding import Finding, FindingSeverity, FindingStatus
from app.models.hums import (
    HUMSBaseline,
    HUMSDiagnosticCandidate,
    HUMSDegradationModel,
    HUMSExceedance,
    HUMSFeature,
    HUMSPrognosticRecord,
    HUMSSensor,
    HUMSSensorReading,
)
from app.models.organization import Organization
from app.models.proactive_signal import ProactiveSignalRecord
from app.models.telemetry import (
    ExternalAssetMapping,
    TelemetryEventLog,
    TelemetryFreshnessPolicy,
    TelemetryProcessingStatus,
)
from app.schemas.auth import CurrentUser
from app.schemas.telemetry import (
    NormalizedTelemetryEvent,
    TelemetryBatteryPayload,
    TelemetryFlightPayload,
    TelemetryIngestRequest,
    TelemetryReadingItem,
)
from app.services import (
    hums_service,
    telemetry_service,
)
from app.services.hums import baseline_service
from app.services.ai import tools
from app.services.edge.telemetry_simulator import (
    TelemetryScenarioType,
    build_scenario_batch,
    generate_canonical_event,
    generate_reading_burst,
)
from app.services.intelligence import proactive_intelligence_service


def _setup_test_environment(db_session):
    """Sets up a clean organization, asset, component, and sensor mapping."""
    org = Organization(name=f"M17 Aerospace Fleet {uuid.uuid4().hex[:6]}")
    db_session.add(org)
    db_session.flush()

    asset = Asset(
        organization_id=org.id,
        serial_number=f"UAV-M17-{uuid.uuid4().hex[:6]}",
        model="KOTA-HEAVY-LIFT-X8",
        asset_type=AssetType.DRONE,
        status="OPERATIONAL",
    )
    db_session.add(asset)
    db_session.flush()

    component = Component(
        organization_id=org.id,
        asset_id=asset.id,
        component_type="MOTOR",
        name="Front-Right Propulsion Unit",
        serial_number=f"PROP-FR-{uuid.uuid4().hex[:6]}",
        model="KOTA-PROP-01",
        status="INSTALLED",
    )
    db_session.add(component)
    db_session.flush()

    sensor = HUMSSensor(
        organization_id=org.id,
        asset_id=asset.id,
        component_id=component.id,
        sensor_code="VIB_FR_MOTOR",
        sensor_type="VIBRATION",
        measurement_type="vibration",
        unit="mm/s",
        status="ACTIVE",
        source="TELEMETRY",
    )
    db_session.add(sensor)
    db_session.flush()

    # External asset mapping for gateway
    mapping = ExternalAssetMapping(
        organization_id=org.id,
        source_system="KOTA_GATEWAY",
        external_asset_id=asset.serial_number,
        asset_id=asset.id,
        is_active=True,
    )
    db_session.add(mapping)
    db_session.flush()

    # Create dummy user for tool auth
    user = CurrentUser(
        id=uuid.uuid4(),
        organization_id=org.id,
        email="test-pilot@example.com",
        full_name="Test Pilot",
        roles=["ORG_ADMIN"],
    )

    from tests.integration.conftest import grant_features

    grant_features(
        db_session,
        org.id,
        "drone_fleet_management",
        "live_telemetry_streaming",
        "flight_telemetry",
        "hums",
        "hums_health_monitoring",
        "predictive_maintenance",
        "proactive_maintenance",
        "proactive_maintenance_m7",
        "ai_chat_assistant",
        suite_code="DRONE_UAV",
    )

    return org, asset, component, sensor, user


def test_m17_end_to_end_intelligence_chain(db_session):
    """Executes the full 9-step M17 deterministic intelligence validation."""
    org, asset, component, sensor, user = _setup_test_environment(db_session)
    t0 = datetime.now(UTC) - timedelta(hours=2)

    # -------------------------------------------------------------------------
    # STEP 1: Healthy Baseline Telemetry Enters Pipeline
    # -------------------------------------------------------------------------
    # Ingest 25 nominal reading points (RMS ~ 1.8 mm/s, well below warning threshold 5.0)
    for i in range(5):
        event = build_scenario_batch(
            TelemetryScenarioType.NORMAL,
            source_asset_id=asset.serial_number,
            vib_sensor_code=sensor.sensor_code,
            component_id=component.id,
            step=i + 1,
            base_time=t0 + timedelta(minutes=i * 5),
        )
        req = TelemetryIngestRequest(events=[event])
        res = telemetry_service.ingest_telemetry_batch(db_session, organization_id=org.id, request=req)
        assert res.processed_count == 1
        assert res.results[0].status == TelemetryProcessingStatus.PROCESSED

    # Verify: Feature rows created with GOOD quality
    features = db_session.execute(
        select(HUMSFeature).where(
            HUMSFeature.organization_id == org.id,
            HUMSFeature.sensor_id == sensor.id,
        )
    ).scalars().all()
    assert len(features) > 0
    rms_features = [f for f in features if f.feature_type == "rms"]
    assert len(rms_features) > 0
    assert rms_features[-1].value < hums_service.VIBRATION_WARNING_RMS

    # Verify: Baseline established
    baseline = baseline_service.get_or_compute_baseline(
        db_session,
        organization_id=org.id,
        sensor=sensor,
        feature_type="rms",
    )
    assert baseline is not None
    assert baseline.mean < 3.0

    # Verify: Zero false critical exceedances or findings
    exceedances = db_session.execute(
        select(HUMSExceedance).where(
            HUMSExceedance.organization_id == org.id,
            HUMSExceedance.sensor_id == sensor.id,
        )
    ).scalars().all()
    assert len(exceedances) == 0

    findings = db_session.execute(
        select(Finding).where(
            Finding.organization_id == org.id,
            Finding.asset_id == asset.id,
        )
    ).scalars().all()
    assert len(findings) == 0

    # -------------------------------------------------------------------------
    # STEP 2 & 3: Controlled Abnormal Vibration Introduced (Elevated & Spiky)
    # -------------------------------------------------------------------------
    # Ingest degraded vibration with impulsive kurtosis spikes (simulating bearing fault)
    deg_event = build_scenario_batch(
        TelemetryScenarioType.VIBRATION_DEGRADATION,
        source_asset_id=asset.serial_number,
        vib_sensor_code=sensor.sensor_code,
        component_id=component.id,
        step=2,  # Elevated ~ 5.6 mm/s with kurtosis spikes
        base_time=t0 + timedelta(minutes=40),
    )
    req_deg = TelemetryIngestRequest(events=[deg_event])
    res_deg = telemetry_service.ingest_telemetry_batch(db_session, organization_id=org.id, request=req_deg)
    assert res_deg.processed_count == 1

    # Ingest critical vibration step (~8.8 mm/s)
    crit_event = build_scenario_batch(
        TelemetryScenarioType.VIBRATION_DEGRADATION,
        source_asset_id=asset.serial_number,
        vib_sensor_code=sensor.sensor_code,
        component_id=component.id,
        step=3,
        base_time=t0 + timedelta(minutes=50),
    )
    req_crit = TelemetryIngestRequest(events=[crit_event])
    res_crit = telemetry_service.ingest_telemetry_batch(db_session, organization_id=org.id, request=req_crit)
    assert res_crit.processed_count == 1

    # -------------------------------------------------------------------------
    # STEP 4: Exceedance Detected & Finding + Evidence Created
    # -------------------------------------------------------------------------
    active_exceedances = db_session.execute(
        select(HUMSExceedance).where(
            HUMSExceedance.organization_id == org.id,
            HUMSExceedance.sensor_id == sensor.id,
        )
    ).scalars().all()
    assert len(active_exceedances) > 0
    latest_exc = active_exceedances[-1]
    assert latest_exc.severity in ("HIGH", "CRITICAL")
    assert latest_exc.observed_value >= hums_service.VIBRATION_WARNING_RMS
    assert latest_exc.finding_id is not None
    assert len(latest_exc.contributing_reading_ids) > 0

    # Verify Finding
    finding = db_session.execute(
        select(Finding).where(
            Finding.id == latest_exc.finding_id,
            Finding.organization_id == org.id,
        )
    ).scalar_one_or_none()
    assert finding is not None
    assert finding.asset_id == asset.id
    assert finding.component_id == component.id
    assert finding.severity in (FindingSeverity.CRITICAL, FindingSeverity.MAJOR)
    assert finding.status == FindingStatus.OPEN
    assert "Vibration Exceedance" in finding.title

    # Verify Evidence Linkage & Provenance
    evidence = db_session.execute(
        select(Evidence).where(
            Evidence.finding_id == finding.id,
            Evidence.organization_id == org.id,
        )
    ).scalar_one_or_none()
    assert evidence is not None
    assert evidence.asset_id == asset.id
    assert evidence.evidence_type == "HUMS_TELEMETRY"
    assert evidence.provenance is not None
    assert evidence.provenance["sensor_id"] == str(sensor.id)
    assert len(evidence.provenance["reading_ids"]) > 0
    assert "feature" in evidence.provenance

    # -------------------------------------------------------------------------
    # STEP 5: Diagnostics Correlates Fault Signature
    # -------------------------------------------------------------------------
    candidates = db_session.execute(
        select(HUMSDiagnosticCandidate).where(
            HUMSDiagnosticCandidate.organization_id == org.id,
            HUMSDiagnosticCandidate.asset_id == asset.id,
        )
    ).scalars().all()
    assert len(candidates) > 0
    # Bearing degradation signature should be generated / supported
    bearing_candidate = next((c for c in candidates if c.fault_code == "VIB-BRG-001"), None)
    assert bearing_candidate is not None
    assert bearing_candidate.status in ("SUPPORTED", "CANDIDATE")
    assert bearing_candidate.component_id == component.id
    assert len(bearing_candidate.explanation) > 0
    assert len(bearing_candidate.primary_evidence) > 0

    # -------------------------------------------------------------------------
    # STEP 6: Prognostics Evaluates Degradation Trajectory & RUL
    # -------------------------------------------------------------------------
    prognostics = db_session.execute(
        select(HUMSPrognosticRecord).where(
            HUMSPrognosticRecord.organization_id == org.id,
            HUMSPrognosticRecord.asset_id == asset.id,
            HUMSPrognosticRecord.sensor_id == sensor.id,
            HUMSPrognosticRecord.is_current.is_(True),
        )
    ).scalars().all()
    assert len(prognostics) > 0
    latest_prog = prognostics[0]
    assert latest_prog.status in ("AVAILABLE", "LIMITED", "LOW_CONFIDENCE", "STALE")
    assert any("ESTIMATE" in line for line in latest_prog.explanation)

    # -------------------------------------------------------------------------
    # STEP 7: M7 Proactive Intelligence Emits Signals
    # -------------------------------------------------------------------------
    proactive_summary = proactive_intelligence_service.get_proactive_summary(
        db_session, organization_id=org.id
    )
    assert proactive_summary.total_active_signals > 0
    signal_types = [s.signal_type for s in proactive_summary.signals]
    assert "HUMS_VIBRATION_EXCEEDANCE" in signal_types

    # Find the exceedance signal
    exc_signal = next(s for s in proactive_summary.signals if s.signal_type == "HUMS_VIBRATION_EXCEEDANCE")
    assert exc_signal.asset_id == asset.id
    assert exc_signal.severity in ("CRITICAL", "HIGH")
    assert len(exc_signal.explanation) > 0
    assert len(exc_signal.recommended_actions) > 0

    # -------------------------------------------------------------------------
    # STEP 8: Grounded LISA AI Query & Lineage Verification
    # -------------------------------------------------------------------------
    # Execute tools used by LISA to explain this exact asset's intelligence
    tool_status = tools.execute_tool(
        db_session, user, "get_asset_telemetry_status", {"asset_id": str(asset.id)}
    )
    assert tool_status["telemetry_state"] == "ACTIVE"
    assert tool_status["total_recent_events"] > 0

    tool_hums = tools.execute_tool(
        db_session, user, "get_asset_hums_health_intelligence", {"asset_id": str(asset.id)}
    )
    assert tool_hums["state"] in ("WARNING", "CRITICAL", "DEGRADED")
    assert len(tool_hums["components"]) > 0

    tool_diag = tools.execute_tool(
        db_session, user, "get_asset_hums_diagnostics", {"asset_id": str(asset.id)}
    )
    assert "diagnostics" in tool_diag
    assert len(tool_diag["diagnostics"]) > 0
    assert any(c["fault_code"] == "VIB-BRG-001" for c in tool_diag["diagnostics"])

    tool_signals = tools.execute_tool(
        db_session, user, "get_asset_proactive_signals", {"asset_id": str(asset.id)}
    )
    assert len(tool_signals["signals"]) > 0

    # -------------------------------------------------------------------------
    # STEP 9: Telemetry Staleness (Gap Handling) & Policy Enforcement
    # -------------------------------------------------------------------------
    # Set freshness policy: 3 days warning, 7 days critical
    telemetry_service.upsert_freshness_policy(
        db_session,
        organization_id=org.id,
        payload=type(
            "PolicyPayload",
            (),
            {
                "asset_id": asset.id,
                "source_system": None,
                "warning_threshold_days": 3,
                "critical_threshold_days": 7,
                "is_active": True,
                "description": "Strict Freshness Policy",
            },
        )(),
    )
    db_session.flush()

    # Ingest event from 10 days ago simulating missing current telemetry
    stale_event = build_scenario_batch(
        TelemetryScenarioType.TELEMETRY_STALE,
        source_asset_id=asset.serial_number,
        vib_sensor_code=sensor.sensor_code,
        component_id=component.id,
        base_time=datetime.now(UTC),
    )
    # Manually backdate the event timestamp and latest reading to simulate a dead telemetry stream
    stale_ts = datetime.now(UTC) - timedelta(days=10)
    db_session.execute(
        HUMSSensorReading.__table__.update()
        .where(HUMSSensorReading.asset_id == asset.id)
        .values(recorded_at=stale_ts)
    )
    db_session.execute(
        TelemetryEventLog.__table__.update()
        .where(TelemetryEventLog.asset_id == asset.id)
        .values(event_timestamp=stale_ts)
    )
    db_session.flush()

    # Verify: Telemetry status transitions to STALE (never assumes healthy)
    stale_status = telemetry_service.get_asset_telemetry_status(
        db_session, organization_id=org.id, asset_id=asset.id
    )
    assert stale_status["telemetry_state"] == "STALE"

    # Verify: Proactive signal includes TELEMETRY_FRESHNESS warning
    stale_summary = proactive_intelligence_service.get_proactive_summary(
        db_session, organization_id=org.id
    )
    stale_sig_types = [s.signal_type for s in stale_summary.signals]
    assert "TELEMETRY_FRESHNESS" in stale_sig_types

    # -------------------------------------------------------------------------
    # STEP 10: Stream Recovery, Idempotency & Tenant Isolation
    # -------------------------------------------------------------------------
    # Recovery: Fresh event arrives now
    recovery_event = build_scenario_batch(
        TelemetryScenarioType.TELEMETRY_RECOVERY,
        source_asset_id=asset.serial_number,
        vib_sensor_code=sensor.sensor_code,
        component_id=component.id,
        base_time=datetime.now(UTC),
    )
    recovery_req = TelemetryIngestRequest(events=[recovery_event])
    recovery_res = telemetry_service.ingest_telemetry_batch(
        db_session, organization_id=org.id, request=recovery_req
    )
    assert recovery_res.processed_count == 1

    # Recovered status
    recovered_status = telemetry_service.get_asset_telemetry_status(
        db_session, organization_id=org.id, asset_id=asset.id
    )
    assert recovered_status["telemetry_state"] == "ACTIVE"

    # Idempotency: Re-submitting the exact same recovery event returns DUPLICATE
    dup_res = telemetry_service.ingest_telemetry_batch(
        db_session, organization_id=org.id, request=recovery_req
    )
    assert dup_res.processed_count == 0
    assert dup_res.duplicate_count == 1
    assert dup_res.results[0].status == TelemetryProcessingStatus.DUPLICATE

    # Tenant Isolation: Create Org B and verify complete data boundary
    org_b = Organization(name=f"Tenant B Defense Fleet {uuid.uuid4().hex[:6]}")
    db_session.add(org_b)
    db_session.flush()

    # Querying Org B signals must return zero records from Org A
    org_b_summary = proactive_intelligence_service.get_proactive_summary(
        db_session, organization_id=org_b.id
    )
    assert org_b_summary.total_active_signals == 0
    assert len(org_b_summary.signals) == 0
