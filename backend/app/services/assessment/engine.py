"""MRO Assessment & Impact Intelligence engine.

Sits ABOVE the existing operational graph and NEVER re-implements it —
every finding is derived exclusively from real data already computed by
aog_recovery_service, release_readiness_service, and
technician_qualification records. This module only scores, ranks, and
sequences what those services already return.

Materiality / complexity / impact / risk are DECISION-SUPPORT scores, not
regulatory certifications — every scoring function below is a small,
documented, deterministic formula, not a fabricated "AI score". Likelihood
for risk is always UNKNOWN (no historical failure-rate data exists in this
schema); risk_level here is impact-driven only, and that is stated
explicitly on every AssessmentRisk row rather than hidden.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AeroComplyError, NotFoundError
from app.models.assessment import (
    Assessment,
    AssessmentFinding,
    AssessmentGap,
    AssessmentMetric,
    AssessmentRecommendation,
    AssessmentRisk,
    AssessmentRoadmapItem,
    AssessmentScopeType,
    AssessmentSnapshot,
    AssessmentStatus,
)
from app.models.technician_qualification import TechnicianQualification
from app.schemas.assessment import AssessmentCreateRequest
from app.services import (
    aircraft_service,
    aog_recovery_service,
    release_readiness_service,
    work_order_service,
)
from app.services.audit_service import record_audit_event

_QUALIFICATION_EXPIRY_WINDOW_DAYS = 30

# category -> (materiality_weight, complexity note n/a, impact dimensions, effort_band)
_CATEGORY_PROFILE: dict[str, tuple[int, list[str], str]] = {
    "MATERIAL_NOT_REQUESTED": (20, ["SUPPLY_CHAIN", "OPERATIONS"], "MEDIUM"),
    "MATERIAL_AWAITING_APPROVAL": (20, ["SUPPLY_CHAIN", "OPERATIONS"], "SMALL"),
    "MATERIAL_PO_NOT_SENT": (20, ["SUPPLY_CHAIN", "OPERATIONS"], "SMALL"),
    "MATERIAL_AWAITING_RECEIPT": (18, ["SUPPLY_CHAIN", "OPERATIONS"], "MEDIUM"),
    "MATERIAL_SHORT": (18, ["SUPPLY_CHAIN", "OPERATIONS"], "MEDIUM"),
    "TASK_EXECUTION": (25, ["OPERATIONS", "RELEASE"], "SMALL"),
    "EVIDENCE": (22, ["QUALITY", "RELEASE"], "SMALL"),
    "INSPECTION": (25, ["SAFETY", "QUALITY", "RELEASE"], "MEDIUM"),
    "TECHNICIAN": (20, ["SAFETY", "OPERATIONS"], "SMALL"),
    "EVENT_BLOCKER": (15, ["OPERATIONS"], "UNKNOWN"),
}
_DEFAULT_PROFILE = (10, ["OPERATIONS"], "UNKNOWN")


def _materiality_band(score: float) -> str:
    if score >= 50:
        return "CRITICAL"
    if score >= 30:
        return "HIGH"
    if score >= 15:
        return "MODERATE"
    return "LOW"


def _complexity_band(dependency_count: int) -> str:
    if dependency_count >= 4:
        return "HIGH"
    if dependency_count >= 2:
        return "MODERATE"
    if dependency_count >= 1:
        return "LOW"
    return "LOW"


@dataclass
class _DraftFinding:
    category: str
    severity: str
    title: str
    description: str
    entity_type: str
    entity_id: str
    materiality_score: float
    dependency_count: int
    impact_dimensions: list[str]
    source: str
    expected_condition: str
    current_condition: str
    recommended_action: str
    responsible_role: str
    effort_band: str


def _severity_for_score(score: float) -> str:
    return _materiality_band(score)


def _aog_findings(db: Session, organization_id: uuid.UUID, aircraft) -> list[_DraftFinding]:
    status = aog_recovery_service.get_recovery_status(
        db, organization_id=organization_id, aircraft_id=aircraft.id
    )
    if not status.is_aog:
        return []

    dependency_count = len(status.blockers)
    drafts: list[_DraftFinding] = []
    for blocker in status.blockers:
        weight, dims, effort = _CATEGORY_PROFILE.get(blocker.category, _DEFAULT_PROFILE)
        score = min(100.0, 40 + weight)
        source = (
            f"AogEvent {status.aog_event_id} on Aircraft {status.aircraft_id} "
            f"({status.registration}) — {blocker.record_type}:{blocker.record_id}"
        )
        drafts.append(
            _DraftFinding(
                category=blocker.category,
                severity=_severity_for_score(score),
                title=f"{status.registration} AOG — {blocker.category.replace('_', ' ').title()}",
                description=blocker.description,
                entity_type=blocker.record_type or "AogEvent",
                entity_id=blocker.record_id or status.aog_event_id or str(aircraft.id),
                materiality_score=score,
                dependency_count=dependency_count,
                impact_dimensions=sorted(set(dims) | {"CUSTOMER_SERVICE"}),
                source=source,
                expected_condition=_expected_condition(blocker.category),
                current_condition=blocker.description,
                recommended_action=blocker.dependency,
                responsible_role=blocker.who_should_act,
                effort_band=effort,
            )
        )
    return drafts


def _release_findings_for_non_aog_work_orders(
    db: Session, organization_id: uuid.UUID, aog_work_order_ids: set[str]
) -> list[_DraftFinding]:
    work_orders = work_order_service.list_work_orders(db, organization_id=organization_id)
    drafts: list[_DraftFinding] = []
    for wo in work_orders:
        if str(wo.id) in aog_work_order_ids:
            continue  # already covered by the AOG-linked findings above
        readiness = release_readiness_service.get_release_readiness_for_work_order(
            db, organization_id=organization_id, work_order_id=wo.id
        )
        if readiness.status != "BLOCKED":
            continue
        dependency_count = len(readiness.blockers)
        for blocker in readiness.blockers:
            weight, dims, effort = _CATEGORY_PROFILE.get(blocker.category, _DEFAULT_PROFILE)
            score = float(weight)
            drafts.append(
                _DraftFinding(
                    category=blocker.category,
                    severity=_severity_for_score(score),
                    title=(
                        f"Work Order {wo.work_order_number} — "
                        f"{blocker.category.replace('_', ' ').title()}"
                    ),
                    description=blocker.description,
                    entity_type=blocker.category,
                    entity_id=(
                        str(blocker.related_record_id) if blocker.related_record_id else str(wo.id)
                    ),
                    materiality_score=score,
                    dependency_count=dependency_count,
                    impact_dimensions=sorted(set(dims)),
                    source=f"WorkOrder {wo.id} ({wo.work_order_number}) release-readiness blocker",
                    expected_condition=_expected_condition(blocker.category),
                    current_condition=blocker.description,
                    recommended_action=_dependency_text(blocker.category),
                    responsible_role=_actor_text(blocker.category),
                    effort_band=effort,
                )
            )
    return drafts


def _qualification_expiry_findings(
    db: Session, organization_id: uuid.UUID
) -> list[_DraftFinding]:
    now = datetime.now(UTC)
    horizon = now + timedelta(days=_QUALIFICATION_EXPIRY_WINDOW_DAYS)
    rows = list(
        db.execute(
            select(TechnicianQualification).where(
                TechnicianQualification.organization_id == organization_id,
                TechnicianQualification.revoked.is_(False),
                TechnicianQualification.expires_at.is_not(None),
                TechnicianQualification.expires_at <= horizon,
            )
        )
        .scalars()
        .all()
    )
    drafts: list[_DraftFinding] = []
    for qual in rows:
        already_expired = qual.expires_at is not None and qual.expires_at <= now
        score = 25.0 if already_expired else 15.0
        drafts.append(
            _DraftFinding(
                category="TECHNICIAN_QUALIFICATION_EXPIRY",
                severity=_severity_for_score(score),
                title=(
                    "Technician qualification "
                    + ("EXPIRED" if already_expired else "expiring soon")
                    + f" — {qual.aircraft_type}"
                ),
                description=(
                    f"Qualification {qual.id} ({qual.qualification_type}) for "
                    f"{qual.aircraft_type!r} "
                    + (
                        f"expired on {qual.expires_at}."
                        if already_expired
                        else f"expires on {qual.expires_at}."
                    )
                ),
                entity_type="TechnicianQualification",
                entity_id=str(qual.id),
                materiality_score=score,
                dependency_count=1,
                impact_dimensions=["SAFETY", "OPERATIONS"],
                source=f"TechnicianQualification {qual.id} (user {qual.user_id})",
                expected_condition=(
                    "Technician holds a currently valid qualification for this aircraft type."
                ),
                current_condition=(
                    f"Qualification {'expired' if already_expired else 'expires'} "
                    f"on {qual.expires_at}."
                ),
                recommended_action=(
                    "Renew or reissue the technician's qualification before it lapses further."
                ),
                responsible_role="Maintenance Planner",
                effort_band="SMALL",
            )
        )
    return drafts


def _expected_condition(category: str) -> str:
    return {
        "MATERIAL_NOT_REQUESTED": "A procurement request exists for the shortage.",
        "MATERIAL_AWAITING_APPROVAL": "The procurement request is approved.",
        "MATERIAL_PO_NOT_SENT": "A purchase order has been sent to the vendor.",
        "MATERIAL_AWAITING_RECEIPT": "The purchase order is fully received.",
        "MATERIAL_SHORT": "Available quantity meets the required quantity.",
        "TASK_EXECUTION": "Task execution_state is COMPLETED.",
        "EVIDENCE": "Evidence is ACCEPTED.",
        "INSPECTION": "Inspection requirement is COMPLETED or NOT_REQUIRED.",
        "TECHNICIAN": "Assigned technician holds an active, non-expired qualification.",
    }.get(category, "The blocking condition is resolved.")


def _dependency_text(category: str) -> str:
    return {
        "TASK_EXECUTION": "Complete task execution.",
        "EVIDENCE": "Submit and have evidence accepted.",
        "INSPECTION": "Complete the required inspection (RII requires an independent inspector).",
    }.get(category, "Resolve the underlying record.")


def _actor_text(category: str) -> str:
    return {
        "TASK_EXECUTION": "Assigned technician",
        "EVIDENCE": "Assigned technician",
        "INSPECTION": "Authorized inspector (independent of the executing technician)",
    }.get(category, "Maintenance")


def create_assessment(
    db: Session,
    *,
    organization_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    payload: AssessmentCreateRequest,
) -> Assessment:
    if payload.scope_type == AssessmentScopeType.AIRCRAFT:
        if payload.scope_id is None:
            raise AeroComplyError("scope_id is required for an AIRCRAFT-scoped assessment")
        aircraft_service.get_aircraft(
            db, organization_id=organization_id, aircraft_id=payload.scope_id
        )
    elif payload.scope_type == AssessmentScopeType.WORK_ORDER:
        if payload.scope_id is None:
            raise AeroComplyError("scope_id is required for a WORK_ORDER-scoped assessment")
        work_order_service.get_work_order(
            db, organization_id=organization_id, work_order_id=payload.scope_id
        )

    assessment = Assessment(
        organization_id=organization_id,
        name=payload.name,
        description=payload.description,
        scope_type=payload.scope_type,
        scope_id=payload.scope_id,
        status=AssessmentStatus.DRAFT,
        created_by_user_id=actor_user_id,
    )
    db.add(assessment)
    db.commit()
    db.refresh(assessment)
    return assessment


def list_assessments(db: Session, *, organization_id: uuid.UUID) -> list[Assessment]:
    return list(
        db.execute(select(Assessment).where(Assessment.organization_id == organization_id))
        .scalars()
        .all()
    )


def get_assessment(
    db: Session, *, organization_id: uuid.UUID, assessment_id: uuid.UUID
) -> Assessment:
    assessment = db.execute(
        select(Assessment).where(
            Assessment.id == assessment_id, Assessment.organization_id == organization_id
        )
    ).scalar_one_or_none()
    if assessment is None:
        raise NotFoundError("Assessment not found")
    return assessment


def _gather_findings(
    db: Session, *, organization_id: uuid.UUID, assessment: Assessment
) -> list[_DraftFinding]:
    if assessment.scope_type == AssessmentScopeType.AIRCRAFT:
        assert assessment.scope_id is not None  # enforced at create_assessment time
        aircraft_list = [
            aircraft_service.get_aircraft(
                db, organization_id=organization_id, aircraft_id=assessment.scope_id
            )
        ]
    else:
        aircraft_list = aircraft_service.list_aircraft(db, organization_id=organization_id)

    drafts: list[_DraftFinding] = []
    aog_work_order_ids: set[str] = set()
    for aircraft in aircraft_list:
        aog_drafts = _aog_findings(db, organization_id, aircraft)
        drafts.extend(aog_drafts)
        status = aog_recovery_service.get_recovery_status(
            db, organization_id=organization_id, aircraft_id=aircraft.id
        )
        if status.work_order_id:
            aog_work_order_ids.add(status.work_order_id)

    if assessment.scope_type != AssessmentScopeType.AIRCRAFT:
        drafts.extend(
            _release_findings_for_non_aog_work_orders(db, organization_id, aog_work_order_ids)
        )
        drafts.extend(_qualification_expiry_findings(db, organization_id))

    return drafts


def run_assessment(
    db: Session,
    *,
    organization_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    assessment_id: uuid.UUID,
) -> AssessmentSnapshot:
    assessment = get_assessment(db, organization_id=organization_id, assessment_id=assessment_id)

    drafts = _gather_findings(db, organization_id=organization_id, assessment=assessment)
    # Priority: highest materiality first, ties broken by dependency_count (more entangled first).
    drafts.sort(key=lambda d: (-d.materiality_score, -d.dependency_count))

    prior_version = (
        db.execute(
            select(AssessmentSnapshot.version)
            .where(AssessmentSnapshot.assessment_id == assessment_id)
            .order_by(AssessmentSnapshot.version.desc())
        ).scalars().first()
        or 0
    )

    critical_count = sum(1 for d in drafts if _materiality_band(d.materiality_score) == "CRITICAL")
    overall_score = (
        max(0.0, 100.0 - sum(d.materiality_score for d in drafts) / 2.0) if drafts else 100.0
    )
    maturity_band = (
        "HEALTHY" if overall_score >= 80 else "AT_RISK" if overall_score >= 50 else "DEGRADED"
    )

    snapshot = AssessmentSnapshot(
        organization_id=organization_id,
        assessment_id=assessment_id,
        version=prior_version + 1,
        overall_score=round(overall_score, 1),
        maturity_band=maturity_band,
        summary=(
            f"{len(drafts)} finding(s), {critical_count} critical, "
            f"scope={assessment.scope_type}"
        ),
        finding_count=len(drafts),
        critical_finding_count=critical_count,
    )
    db.add(snapshot)
    db.flush()

    for rank, draft in enumerate(drafts, start=1):
        finding = AssessmentFinding(
            organization_id=organization_id,
            snapshot_id=snapshot.id,
            category=draft.category,
            severity=draft.severity,
            title=draft.title,
            description=draft.description,
            entity_type=draft.entity_type,
            entity_id=draft.entity_id,
            materiality_score=draft.materiality_score,
            complexity_band=_complexity_band(draft.dependency_count),
            dependency_count=draft.dependency_count,
            impact_dimensions=draft.impact_dimensions,
            priority_rank=rank,
            source=draft.source,
        )
        db.add(finding)
        db.flush()

        db.add(
            AssessmentGap(
                organization_id=organization_id,
                snapshot_id=snapshot.id,
                finding_id=finding.id,
                category=draft.category,
                severity=draft.severity,
                entity_type=draft.entity_type,
                entity_id=draft.entity_id,
                expected_condition=draft.expected_condition,
                current_condition=draft.current_condition,
                recommended_action=draft.recommended_action,
            )
        )
        db.add(
            AssessmentRisk(
                organization_id=organization_id,
                snapshot_id=snapshot.id,
                finding_id=finding.id,
                risk_level=draft.severity,
                likelihood="UNKNOWN",
                reason=draft.description,
                entity_type=draft.entity_type,
                entity_id=draft.entity_id,
                mitigation=draft.recommended_action,
                owner_role=draft.responsible_role,
            )
        )
        db.add(
            AssessmentRecommendation(
                organization_id=organization_id,
                snapshot_id=snapshot.id,
                finding_id=finding.id,
                recommendation=draft.recommended_action,
                why=draft.description,
                priority=draft.severity,
                responsible_role=draft.responsible_role,
                entity_type=draft.entity_type,
                entity_id=draft.entity_id,
            )
        )
        db.add(
            AssessmentRoadmapItem(
                organization_id=organization_id,
                snapshot_id=snapshot.id,
                finding_id=finding.id,
                sequence=rank,
                title=draft.title,
                description=draft.recommended_action,
                category=draft.category,
                priority=draft.severity,
                entity_type=draft.entity_type,
                entity_id=draft.entity_id,
                prerequisite_sequence_numbers=[],
                owner_role=draft.responsible_role,
                estimated_effort_band=draft.effort_band,
                effort_confidence="LOW",
                expected_impact=f"Resolves: {draft.description}",
                risk_if_delayed=(
                    f"Remains {draft.severity} — "
                    f"{', '.join(draft.impact_dimensions)} impact continues."
                ),
            )
        )
        db.add(
            AssessmentMetric(
                organization_id=organization_id,
                snapshot_id=snapshot.id,
                metric_key=f"materiality:{finding.id}",
                state="VALUE",
                value=draft.materiality_score,
                unit="score_0_100",
                explanation=f"Operational Materiality Score for: {draft.title}",
            )
        )

    assessment.status = AssessmentStatus.COMPLETE
    db.add(assessment)
    record_audit_event(
        db,
        organization_id=organization_id,
        user_id=actor_user_id,
        action="assessment.run",
        entity_type="Assessment",
        entity_id=assessment.id,
        metadata={"snapshot_id": str(snapshot.id), "finding_count": len(drafts)},
    )
    db.commit()
    db.refresh(snapshot)
    return snapshot


def get_snapshot(
    db: Session, *, organization_id: uuid.UUID, snapshot_id: uuid.UUID
) -> AssessmentSnapshot:
    snapshot = db.execute(
        select(AssessmentSnapshot).where(
            AssessmentSnapshot.id == snapshot_id,
            AssessmentSnapshot.organization_id == organization_id,
        )
    ).scalar_one_or_none()
    if snapshot is None:
        raise NotFoundError("Assessment snapshot not found")
    return snapshot


def get_latest_snapshot(
    db: Session, *, organization_id: uuid.UUID, assessment_id: uuid.UUID
) -> AssessmentSnapshot | None:
    return (
        db.execute(
            select(AssessmentSnapshot)
            .where(
                AssessmentSnapshot.assessment_id == assessment_id,
                AssessmentSnapshot.organization_id == organization_id,
            )
            .order_by(AssessmentSnapshot.version.desc())
        )
        .scalars()
        .first()
    )


@dataclass
class SnapshotComparison:
    from_version: int
    to_version: int
    score_delta: float
    new_findings: list[AssessmentFinding] = field(default_factory=list)
    # descriptions of findings present in the older snapshot but gone in the newer one
    resolved_findings: list[str] = field(default_factory=list)


def compare_snapshots(
    db: Session, *, organization_id: uuid.UUID, snapshot_id_a: uuid.UUID, snapshot_id_b: uuid.UUID
) -> SnapshotComparison:
    older = get_snapshot(db, organization_id=organization_id, snapshot_id=snapshot_id_a)
    newer = get_snapshot(db, organization_id=organization_id, snapshot_id=snapshot_id_b)
    if newer.version < older.version:
        older, newer = newer, older

    older_keys = {
        (f.entity_type, f.entity_id, f.category) for f in older.findings
    }
    newer_keys = {
        (f.entity_type, f.entity_id, f.category): f for f in newer.findings
    }

    new_findings = [f for key, f in newer_keys.items() if key not in older_keys]
    resolved = [
        f"{f.entity_type}:{f.entity_id} {f.category}"
        for f in older.findings
        if (f.entity_type, f.entity_id, f.category) not in newer_keys
    ]

    return SnapshotComparison(
        from_version=older.version,
        to_version=newer.version,
        score_delta=round(newer.overall_score - older.overall_score, 1),
        new_findings=new_findings,
        resolved_findings=resolved,
    )
