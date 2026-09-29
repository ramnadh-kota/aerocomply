"""H4: Orchestrates fault_signatures + diagnostic_engine into persisted
HUMSDiagnosticCandidate rows, and integrates meaningful candidates into
ProactiveSignalRecord (no second alert system).

Lifecycle safety (H4 spec sections 6/26/39): this module can only ever set
a candidate's status to CANDIDATE/SUPPORTED/WEAK — those are refreshed
freely on every re-evaluation since they're just the engine's current read
of the evidence, not a confirmation. CONFIRMED/REJECTED/RESOLVED are set
ONLY by confirm_candidate/reject_candidate/resolve_candidate, which require
an authenticated user and are only ever called from an explicit,
permission-gated API action — never automatically by evaluation. A
candidate already in one of those three states is left untouched by
re-evaluation (its score/evidence snapshot is preserved as of the human
decision).
"""

from __future__ import annotations

import datetime
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.models.hums import HUMSDiagnosticCandidate, HUMSSensor
from app.models.proactive_signal import ProactiveSignalRecord
from app.services import audit_service
from app.services.hums import health_service
from app.services.hums.diagnostic_engine import DiagnosticEvaluation, detect_sensor_fault_candidate, generate_candidates
from app.services.hums.fault_signatures import VIBRATION_SIGNATURES
from app.services.hums.health_engine import FeatureHealthResult

HUMAN_LOCKED_STATUSES = ("CONFIRMED", "REJECTED", "RESOLVED")

SENSOR_ANOMALY_FAULT_CODE = "SEN-ANOM-001"
SENSOR_ANOMALY_VERSION = "1.0"


def _evidence_entry(f: FeatureHealthResult) -> dict:
    return {
        "feature_type": f.feature_type,
        "state": f.state,
        "current_value": f.deviation.current_value if f.deviation else None,
        "baseline_value": f.deviation.baseline_value if f.deviation else None,
        "deviation_state": f.deviation.state if f.deviation else None,
        "percentage_deviation": f.deviation.percentage_deviation if f.deviation else None,
        "trend_direction": f.trend.direction if f.trend else None,
        "consecutive_deviation_count": f.consecutive_deviation_count,
    }


def _upsert_candidate(
    db: Session,
    *,
    organization_id: uuid.UUID,
    user_id: uuid.UUID | None,
    asset_id: uuid.UUID,
    component_id: uuid.UUID | None,
    sensor_ids: list[str],
    fault_code: str,
    fault_name: str,
    fault_domain: str,
    rule_version: str,
    evaluation_status: str,
    severity: str,
    score: float,
    confidence: str,
    primary_evidence: list[dict],
    supporting_evidence: list[dict],
    contradicting_evidence: list[dict],
    explanation: list[str],
) -> HUMSDiagnosticCandidate:
    existing = db.execute(
        select(HUMSDiagnosticCandidate).where(
            HUMSDiagnosticCandidate.organization_id == organization_id,
            HUMSDiagnosticCandidate.asset_id == asset_id,
            HUMSDiagnosticCandidate.component_id == component_id,
            HUMSDiagnosticCandidate.fault_code == fault_code,
        )
    ).scalar_one_or_none()

    now = datetime.datetime.now(datetime.UTC)

    if existing:
        if existing.status in HUMAN_LOCKED_STATUSES:
            return existing  # a human decision stands; evaluation never overwrites it
        existing.status = evaluation_status
        existing.severity = severity
        existing.score = score
        existing.confidence = confidence
        existing.sensor_ids = sensor_ids
        existing.primary_evidence = primary_evidence
        existing.supporting_evidence = supporting_evidence
        existing.contradicting_evidence = contradicting_evidence
        existing.explanation = explanation
        existing.rule_version = rule_version
        db.flush()
        return existing

    candidate = HUMSDiagnosticCandidate(
        organization_id=organization_id,
        asset_id=asset_id,
        component_id=component_id,
        sensor_ids=sensor_ids,
        fault_code=fault_code,
        fault_name=fault_name,
        fault_domain=fault_domain,
        diagnostic_method="rule_based_signature_matching",
        rule_version=rule_version,
        status=evaluation_status,
        severity=severity,
        score=score,
        confidence=confidence,
        primary_evidence=primary_evidence,
        supporting_evidence=supporting_evidence,
        contradicting_evidence=contradicting_evidence,
        explanation=explanation,
        detected_at=now,
    )
    db.add(candidate)
    db.flush()

    audit_service.record_audit_event(
        db, organization_id=organization_id, user_id=user_id, action="hums_diagnostic.generated",
        entity_type="HUMSDiagnosticCandidate", entity_id=candidate.id,
        metadata={"fault_code": fault_code, "asset_id": str(asset_id), "component_id": str(component_id) if component_id else None, "score": score},
    )
    _sync_diagnostic_signal(db, organization_id=organization_id, candidate=candidate)
    return candidate


def _sync_diagnostic_signal(db: Session, *, organization_id: uuid.UUID, candidate: HUMSDiagnosticCandidate) -> None:
    """Only SUPPORTED candidates raise a signal -- WEAK/single-feature
    hypotheses must not spam the signal feed (H4 spec section 39)."""
    if candidate.status != "SUPPORTED":
        return
    key = f"hums_diagnostic:{candidate.id}"
    existing = db.execute(
        select(ProactiveSignalRecord).where(
            ProactiveSignalRecord.organization_id == organization_id, ProactiveSignalRecord.signal_key == key
        )
    ).scalar_one_or_none()
    if existing:
        return

    record = ProactiveSignalRecord(
        organization_id=organization_id,
        signal_key=key,
        signal_type="HUMS_DIAGNOSTIC_CANDIDATE",
        severity=candidate.severity if candidate.severity != "MEDIUM" else "MEDIUM",
        priority=candidate.severity,
        status="OPEN",
        title=f"HUMS Diagnostic Candidate — {candidate.fault_name}",
        headline=f"{candidate.fault_name} (confidence: {candidate.confidence.lower()}, score {candidate.score}) — engineering review required.",
        explanation_json=candidate.explanation + ["This is a diagnostic candidate, not a confirmed fault. Requires engineering confirmation."],
        asset_id=candidate.asset_id,
        component_id=candidate.component_id,
        detected_at=datetime.datetime.now(datetime.UTC),
        evidence_json=[],
        contributing_factors_json={
            "candidate_id": str(candidate.id), "fault_code": candidate.fault_code,
            "score": candidate.score, "confidence": candidate.confidence,
        },
        recommended_actions_json=[
            {
                "action_type": "REVIEW_FINDING",
                "title": "Review Diagnostic Candidate",
                "description": f"Engineering review of candidate '{candidate.fault_name}' on asset {candidate.asset_id} is recommended.",
                "target_url": f"/assets/{candidate.asset_id}",
                "requires_authorization": True,
            }
        ],
    )
    db.add(record)


def evaluate_and_persist_diagnostics(
    db: Session, *, organization_id: uuid.UUID, user_id: uuid.UUID | None, asset_id: uuid.UUID, component_id: uuid.UUID | None, sensors: list[HUMSSensor]
) -> list[HUMSDiagnosticCandidate]:
    """Evaluates every applicable fault signature (plus the sensor-fault
    safeguard) for one component's (or the asset-level unassigned bucket's)
    sensors, and upserts the resulting candidates. Returns all candidates
    touched (including any left untouched because they're human-locked).
    """
    vibration_sensors = [s for s in sensors if s.measurement_type == "vibration"]
    if not vibration_sensors:
        return []

    sensor_features: dict[str, dict[str, FeatureHealthResult]] = {}
    for sensor in vibration_sensors:
        results = health_service.evaluate_sensor_health(db, organization_id=organization_id, sensor=sensor)
        sensor_features[str(sensor.id)] = {r.feature_type: r for r in results}

    touched: list[HUMSDiagnosticCandidate] = []

    for sensor in vibration_sensors:
        features = sensor_features[str(sensor.id)]
        evaluations = generate_candidates(VIBRATION_SIGNATURES, features)
        for ev in evaluations:
            relevant = [r.feature_type for r in ev.required_results if r.feature_type]
            primary_evidence = [_evidence_entry(features[ft]) for ft in relevant if ft in features]
            supporting_evidence = [_evidence_entry(features[r.feature_type]) for r in ev.supporting_results if r.satisfied and r.feature_type in features]
            contradicting_evidence = [_evidence_entry(features[r.feature_type]) for r in ev.contradicting_results if r.satisfied and r.feature_type in features]

            candidate = _upsert_candidate(
                db, organization_id=organization_id, user_id=user_id, asset_id=asset_id, component_id=component_id,
                sensor_ids=[str(sensor.id)], fault_code=ev.signature.fault_code, fault_name=ev.signature.fault_name,
                fault_domain=ev.signature.fault_domain, rule_version=ev.signature.version, evaluation_status=ev.status,
                severity=ev.severity, score=ev.score, confidence=ev.confidence,
                primary_evidence=primary_evidence, supporting_evidence=supporting_evidence,
                contradicting_evidence=contradicting_evidence, explanation=ev.explanation,
            )
            touched.append(candidate)

    sensor_fault = detect_sensor_fault_candidate(sensor_features)
    if sensor_fault:
        sensor_id, features = sensor_fault
        worst = max(features.values(), key=lambda f: {"HEALTHY": 0, "WATCH": 1, "DEGRADED": 2, "WARNING": 3, "CRITICAL": 4}.get(f.state, 0))
        explanation = [
            f"Only sensor {sensor_id} on this component shows abnormal readings ({worst.feature_type}: {worst.state}) "
            f"while {len(sensor_features) - 1} other sensor(s) on the same component remain healthy.",
            "Consider verifying sensor calibration, wiring, and mounting before attributing this to a physical component fault.",
        ]
        candidate = _upsert_candidate(
            db, organization_id=organization_id, user_id=user_id, asset_id=asset_id, component_id=component_id,
            sensor_ids=[sensor_id], fault_code=SENSOR_ANOMALY_FAULT_CODE, fault_name="Possible sensor anomaly (not a physical fault)",
            fault_domain="SENSOR", rule_version=SENSOR_ANOMALY_VERSION, evaluation_status="WEAK",
            severity="LOW", score=0.4, confidence="MEDIUM",
            primary_evidence=[_evidence_entry(worst)], supporting_evidence=[], contradicting_evidence=[],
            explanation=explanation,
        )
        touched.append(candidate)

    return touched


def get_candidate(db: Session, *, organization_id: uuid.UUID, candidate_id: uuid.UUID) -> HUMSDiagnosticCandidate:
    candidate = db.execute(
        select(HUMSDiagnosticCandidate).where(
            HUMSDiagnosticCandidate.id == candidate_id, HUMSDiagnosticCandidate.organization_id == organization_id
        )
    ).scalar_one_or_none()
    if not candidate:
        raise NotFoundError("Diagnostic candidate not found", code="hums_diagnostic_not_found")
    return candidate


def list_asset_candidates(db: Session, *, organization_id: uuid.UUID, asset_id: uuid.UUID) -> list[HUMSDiagnosticCandidate]:
    return list(
        db.execute(
            select(HUMSDiagnosticCandidate)
            .where(HUMSDiagnosticCandidate.organization_id == organization_id, HUMSDiagnosticCandidate.asset_id == asset_id)
            .order_by(HUMSDiagnosticCandidate.score.desc())
        )
        .scalars()
        .all()
    )


def list_component_candidates(db: Session, *, organization_id: uuid.UUID, component_id: uuid.UUID) -> list[HUMSDiagnosticCandidate]:
    return list(
        db.execute(
            select(HUMSDiagnosticCandidate)
            .where(HUMSDiagnosticCandidate.organization_id == organization_id, HUMSDiagnosticCandidate.component_id == component_id)
            .order_by(HUMSDiagnosticCandidate.score.desc())
        )
        .scalars()
        .all()
    )


def confirm_candidate(db: Session, *, organization_id: uuid.UUID, candidate_id: uuid.UUID, user_id: uuid.UUID) -> HUMSDiagnosticCandidate:
    """Authorized-human-only action. HUMS never confirms its own diagnosis."""
    candidate = get_candidate(db, organization_id=organization_id, candidate_id=candidate_id)
    candidate.status = "CONFIRMED"
    candidate.confirmed_at = datetime.datetime.now(datetime.UTC)
    candidate.confirmed_by_user_id = user_id
    db.flush()
    audit_service.record_audit_event(
        db, organization_id=organization_id, user_id=user_id, action="hums_diagnostic.confirmed",
        entity_type="HUMSDiagnosticCandidate", entity_id=candidate.id, metadata={"fault_code": candidate.fault_code},
    )
    return candidate


def reject_candidate(db: Session, *, organization_id: uuid.UUID, candidate_id: uuid.UUID, user_id: uuid.UUID, reason: str) -> HUMSDiagnosticCandidate:
    candidate = get_candidate(db, organization_id=organization_id, candidate_id=candidate_id)
    candidate.status = "REJECTED"
    candidate.rejected_at = datetime.datetime.now(datetime.UTC)
    candidate.rejected_by_user_id = user_id
    candidate.rejection_reason = reason
    db.flush()
    audit_service.record_audit_event(
        db, organization_id=organization_id, user_id=user_id, action="hums_diagnostic.rejected",
        entity_type="HUMSDiagnosticCandidate", entity_id=candidate.id, metadata={"fault_code": candidate.fault_code, "reason": reason},
    )
    return candidate


__all__ = [
    "evaluate_and_persist_diagnostics",
    "get_candidate",
    "list_asset_candidates",
    "list_component_candidates",
    "confirm_candidate",
    "reject_candidate",
    "HUMAN_LOCKED_STATUSES",
]
