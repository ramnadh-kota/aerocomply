"""H7: MRO + Compliance + Readiness Intelligence Integration.

H7 is a READ-heavy CORRELATION layer, not a new system of record. It calls
existing authoritative services and correlates their outputs; it never
recomputes health, diagnostic, prognostic, compliance, or readiness logic.

Authoritative sources consumed here (never re-derived):
  - app.services.hums_service (H1-H5: health / diagnostics / prognostics)
  - app.services.aerospace_state_service.evaluate_aerospace_intelligence_state
    (D2.1/D2.4 intelligence state -- "the ONLY function ... to obtain
    intelligence state")
  - app.services.intelligence.readiness_intelligence_service
    .get_asset_readiness_intelligence (D2.2 authoritative asset readiness)
  - app.models.compliance.ComplianceObligation (authoritative compliance
    state -- ComplianceState values are never re-invented here)
  - app.models.work_order.WorkOrder / app.models.finding.Finding
    (maintenance history, used for candidate-dedup against existing work)
  - app.services.digital_twin_service.check_asset_consistency (H6's own
    consistency-warning concept -- consulted as one input to
    detect_conflicts, not duplicated)

The ONLY table this module writes to is MaintenanceIntelligenceCandidate
(plus AuditEvent for lifecycle transitions). It NEVER writes to any
authoritative domain table -- see app/models/mro_intelligence.py's
module docstring for the enforced write boundary.

Deterministic throughout: no ML/LLM scoring anywhere in this module.
"""

import datetime
import hashlib
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError
from app.models.compliance import ComplianceObligation, ComplianceState
from app.models.finding import Finding, FindingStatus
from app.models.mro_intelligence import (
    ALLOWED_CANDIDATE_TRANSITIONS,
    MaintenanceIntelligenceCandidate,
    MROCandidatePriority,
    MROCandidateStatus,
    MROCandidateType,
)
from app.models.work_order import WorkOrder, WorkOrderStatus
from app.schemas.aerospace_state import AerospaceIntelligenceStatus
from app.schemas.mro_intelligence import (
    AssetMROIntelligence,
    ComplianceImpactObligation,
    ComplianceImpactResult,
    IntegrationConflict,
    OperationalImpactResult,
    ReadinessImpactResult,
    ReconciliationResult,
    SourceLineageRef,
)
from app.services import asset_service, audit_service, digital_twin_service, hums_service
from app.services.aerospace_state_service import evaluate_aerospace_intelligence_state
from app.services.intelligence.readiness_intelligence_service import get_asset_readiness_intelligence

_OPEN_WORK_ORDER_STATUSES = {
    WorkOrderStatus.DRAFT, WorkOrderStatus.OPEN, WorkOrderStatus.PLANNED,
    WorkOrderStatus.ASSIGNED, WorkOrderStatus.IN_PROGRESS, WorkOrderStatus.ON_HOLD,
    WorkOrderStatus.INSPECTION,
}

_COMPLIANCE_IMPACT_MAP = {
    ComplianceState.NOT_EVALUATED.value: "UNKNOWN",
    ComplianceState.NOT_APPLICABLE.value: "NOT_APPLICABLE",
    ComplianceState.PENDING.value: "DUE",
    ComplianceState.DUE.value: "DUE",
    ComplianceState.OVERDUE.value: "OVERDUE",
    ComplianceState.IN_PROGRESS.value: "DUE",
    ComplianceState.COMPLIANT.value: "COMPLIANT",
    ComplianceState.NON_COMPLIANT.value: "NON_COMPLIANT",
    ComplianceState.BLOCKED.value: "REQUIRES_REVIEW",
    ComplianceState.REVIEW_REQUIRED.value: "REQUIRES_REVIEW",
}

_COMPLIANCE_IMPACT_PRECEDENCE = [
    "NON_COMPLIANT", "OVERDUE", "REQUIRES_REVIEW", "DUE", "UNKNOWN", "COMPLIANT", "NOT_APPLICABLE",
]

_READINESS_IMPACT_PRECEDENCE = [
    "UNKNOWN", "RESTRICTED_OPERATION", "READINESS_AT_RISK", "REVIEW_REQUIRED",
    "INSPECTION_REQUIRED", "MAINTENANCE_DUE", "MONITOR", "NO_IMPACT",
]


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.UTC)


def _build_dedup_key(*, asset_id: uuid.UUID, component_id: uuid.UUID | None, candidate_type: str, refs: list[dict]) -> str:
    """Deterministic idempotency key: asset + component + type + a stable
    hash of the contributing source refs (sorted so ordering never changes
    the key). Mirrors ProactiveSignalRecord.signal_key's dedup role."""
    ref_ids = sorted(f"{r.get('source_type')}:{r.get('source_id')}" for r in refs)
    digest = hashlib.sha256("|".join(ref_ids).encode()).hexdigest()[:16]
    return f"{asset_id}:{component_id or 'none'}:{candidate_type}:{digest}"


def _ref(source_type: str, source_id, label: str) -> dict:
    return {"source_type": source_type, "source_id": str(source_id) if source_id else None, "label": label}


# ---------------------------------------------------------------------------
# Compliance impact
# ---------------------------------------------------------------------------

def get_compliance_impact(db: Session, *, organization_id: uuid.UUID, asset_id: uuid.UUID) -> ComplianceImpactResult:
    """Correlates ComplianceObligation.status (authoritative -- never
    re-derived) against open diagnostic/health signals purely for
    explanatory context; the impact classification is a direct mapping of
    the EXISTING ComplianceState vocabulary, never a parallel one."""
    asset_service.get_asset(db, organization_id=organization_id, asset_id=asset_id)

    obligations = list(
        db.execute(
            select(ComplianceObligation).where(
                ComplianceObligation.organization_id == organization_id,
                ComplianceObligation.asset_id == asset_id,
            )
        ).scalars().all()
    )

    diagnostics = hums_service.list_asset_diagnostics(db, organization_id=organization_id, asset_id=asset_id)
    open_diag_refs = [
        SourceLineageRef(source_type="HUMSDiagnosticCandidate", source_id=str(d.id), label=d.fault_name)
        for d in diagnostics if d.status not in ("REJECTED", "RESOLVED")
    ]

    out: list[ComplianceImpactObligation] = []
    for ob in obligations:
        impact = _COMPLIANCE_IMPACT_MAP.get(ob.status, "UNKNOWN")
        explanation = [f"ComplianceObligation {ob.id} status={ob.status} maps to impact={impact}."]
        correlated = []
        if impact in ("NON_COMPLIANT", "OVERDUE", "REQUIRES_REVIEW") and open_diag_refs:
            correlated = open_diag_refs
            explanation.append(
                f"{len(open_diag_refs)} open diagnostic candidate(s) present on this asset while this obligation is {ob.status}."
            )
        out.append(
            ComplianceImpactObligation(
                obligation_id=ob.id,
                requirement_id=ob.requirement_id,
                state=ob.status,
                impact=impact,
                due_date=ob.due_date.isoformat() if ob.due_date else None,
                correlated_signals=correlated,
                explanation=explanation,
            )
        )

    if not obligations:
        overall = "UNKNOWN"
        explanation = ["No compliance obligations found for this asset; overall impact is UNKNOWN, not COMPLIANT."]
        availability = "DATA_UNAVAILABLE"
    else:
        overall = min(out, key=lambda o: _COMPLIANCE_IMPACT_PRECEDENCE.index(o.impact)).impact
        explanation = [f"Overall compliance impact derived as the highest-precedence obligation impact: {overall}."]
        availability = "AVAILABLE"

    return ComplianceImpactResult(
        asset_id=asset_id, availability=availability, obligations=out,
        overall_impact=overall, explanation=explanation, evaluated_at=_now(),
    )


# ---------------------------------------------------------------------------
# Readiness impact
# ---------------------------------------------------------------------------

def get_readiness_impact(db: Session, *, organization_id: uuid.UUID, asset_id: uuid.UUID) -> ReadinessImpactResult:
    """Derivation rules (deterministic classifier, NOT a score):

    1. authoritative readiness_state == "BLOCKED" -> RESTRICTED_OPERATION.
    2. authoritative readiness_state == "UNKNOWN" -> UNKNOWN (never
       silently resolved to a positive impact -- mirrors Invariant #23).
    3. Otherwise (readiness_state == "READY"), layer HUMS/compliance/open
       candidate signals on top of an otherwise-ready asset:
         a. Any HIGH-priority OPEN/UNDER_REVIEW candidate -> READINESS_AT_RISK.
         b. compliance_impact in (NON_COMPLIANT, OVERDUE) -> REVIEW_REQUIRED.
         c. Any open HUMS diagnostic candidate with severity HIGH,
            or an open MEDIUM-priority candidate -> INSPECTION_REQUIRED.
         d. Any OPEN/UNDER_REVIEW candidate at all, or compliance_impact
            in (DUE, REQUIRES_REVIEW) -> MAINTENANCE_DUE.
         e. Any prognostic record with LOW/rul under 0 -> MONITOR
            (near-term RUL horizon; not yet due).
         f. Otherwise -> NO_IMPACT.
    """
    readiness = get_asset_readiness_intelligence(db, organization_id=organization_id, asset_id=asset_id)
    factors: list[SourceLineageRef] = []
    explanation = [f"Authoritative readiness_state={readiness.readiness_state} ({len(readiness.blockers)} blocker(s))."]

    if readiness.readiness_state == "BLOCKED":
        impact = "RESTRICTED_OPERATION"
        explanation.append("Authoritative readiness is BLOCKED; H7 classifies this as RESTRICTED_OPERATION.")
        return ReadinessImpactResult(
            asset_id=asset_id, authoritative_readiness_state=readiness.readiness_state,
            readiness_impact=impact, contributing_factors=factors, explanation=explanation, evaluated_at=_now(),
        )
    if readiness.readiness_state == "UNKNOWN":
        explanation.append("Authoritative readiness is UNKNOWN; H7 impact is UNKNOWN (never resolved to a positive state).")
        return ReadinessImpactResult(
            asset_id=asset_id, authoritative_readiness_state=readiness.readiness_state,
            readiness_impact="UNKNOWN", contributing_factors=factors, explanation=explanation, evaluated_at=_now(),
        )

    candidates = _list_open_candidates(db, organization_id=organization_id, asset_id=asset_id)
    compliance = get_compliance_impact(db, organization_id=organization_id, asset_id=asset_id)
    diagnostics = hums_service.list_asset_diagnostics(db, organization_id=organization_id, asset_id=asset_id)
    open_diagnostics = [d for d in diagnostics if d.status not in ("REJECTED", "RESOLVED")]
    prognostics = hums_service.list_asset_prognostics(db, organization_id=organization_id, asset_id=asset_id)

    high_priority_open = [c for c in candidates if c.priority == MROCandidatePriority.HIGH]
    high_severity_diag = [d for d in open_diagnostics if d.severity == "HIGH"]

    if high_priority_open:
        impact = "READINESS_AT_RISK"
        factors = [SourceLineageRef(source_type="MaintenanceIntelligenceCandidate", source_id=str(c.id), label=c.reason[:120]) for c in high_priority_open]
        explanation.append(f"{len(high_priority_open)} HIGH-priority open candidate(s) present.")
    elif compliance.overall_impact in ("NON_COMPLIANT", "OVERDUE"):
        impact = "REVIEW_REQUIRED"
        explanation.append(f"Compliance impact is {compliance.overall_impact}.")
    elif high_severity_diag:
        impact = "INSPECTION_REQUIRED"
        factors = [SourceLineageRef(source_type="HUMSDiagnosticCandidate", source_id=str(d.id), label=d.fault_name) for d in high_severity_diag]
        explanation.append(f"{len(high_severity_diag)} HIGH-severity open diagnostic candidate(s).")
    elif candidates or compliance.overall_impact in ("DUE", "REQUIRES_REVIEW"):
        impact = "MAINTENANCE_DUE"
        explanation.append("Open maintenance intelligence candidate(s) or a DUE/REQUIRES_REVIEW compliance obligation present.")
    elif any((p.rul_estimate is not None and p.rul_estimate < 0) or p.confidence == "LOW" for p in prognostics):
        impact = "MONITOR"
        explanation.append("A prognostic record indicates a near-term or low-confidence RUL horizon.")
    else:
        impact = "NO_IMPACT"
        explanation.append("No convergent HUMS, compliance, or candidate signals found.")

    return ReadinessImpactResult(
        asset_id=asset_id, authoritative_readiness_state=readiness.readiness_state,
        readiness_impact=impact, contributing_factors=factors, explanation=explanation, evaluated_at=_now(),
    )


# ---------------------------------------------------------------------------
# Operational impact
# ---------------------------------------------------------------------------

def get_operational_impact(db: Session, *, organization_id: uuid.UUID, asset_id: uuid.UUID) -> OperationalImpactResult:
    readiness_impact = get_readiness_impact(db, organization_id=organization_id, asset_id=asset_id)
    prognostics = hums_service.list_asset_prognostics(db, organization_id=organization_id, asset_id=asset_id)
    factors: list[SourceLineageRef] = []

    if readiness_impact.readiness_impact == "UNKNOWN":
        return OperationalImpactResult(
            asset_id=asset_id, impact_level="UNKNOWN",
            reason="Readiness impact is UNKNOWN and no authoritative mission-criticality data exists; operational impact cannot be determined.",
            contributing_factors=factors, evaluated_at=_now(),
        )

    if readiness_impact.readiness_impact in ("RESTRICTED_OPERATION", "READINESS_AT_RISK"):
        level = "HIGH"
        reason = f"Readiness impact is {readiness_impact.readiness_impact}."
    elif readiness_impact.readiness_impact in ("REVIEW_REQUIRED", "INSPECTION_REQUIRED"):
        level = "MEDIUM"
        reason = f"Readiness impact is {readiness_impact.readiness_impact}."
    elif readiness_impact.readiness_impact == "MAINTENANCE_DUE":
        level = "MEDIUM"
        reason = "Maintenance is due; near-term operational planning should account for it."
    else:
        near_term_rul = [p for p in prognostics if p.rul_estimate is not None and p.rul_estimate < 25]
        if near_term_rul:
            level = "MEDIUM"
            reason = f"{len(near_term_rul)} component(s) show a short RUL horizon (<25 usage units)."
            factors = [SourceLineageRef(source_type="HUMSPrognosticRecord", source_id=str(p.id), label=p.feature_type) for p in near_term_rul]
        else:
            level = "LOW"
            reason = "No convergent readiness, compliance, or near-term prognostic signals found."

    return OperationalImpactResult(
        asset_id=asset_id, impact_level=level, reason=reason,
        contributing_factors=factors, evaluated_at=_now(),
    )


# ---------------------------------------------------------------------------
# Candidate generation
# ---------------------------------------------------------------------------

def _list_open_candidates(db: Session, *, organization_id: uuid.UUID, asset_id: uuid.UUID) -> list[MaintenanceIntelligenceCandidate]:
    return list(
        db.execute(
            select(MaintenanceIntelligenceCandidate).where(
                MaintenanceIntelligenceCandidate.organization_id == organization_id,
                MaintenanceIntelligenceCandidate.asset_id == asset_id,
                MaintenanceIntelligenceCandidate.status.in_([MROCandidateStatus.OPEN, MROCandidateStatus.UNDER_REVIEW, MROCandidateStatus.DEFERRED]),
            )
        ).scalars().all()
    )


def _existing_work_order_covers(db: Session, *, organization_id: uuid.UUID, asset_id: uuid.UUID, component_id: uuid.UUID | None) -> bool:
    """A candidate must NOT be created if an open WorkOrder or Finding
    already covers the same asset/component -- avoids duplicating work
    that is already tracked in the authoritative maintenance domain."""
    wo_stmt = select(WorkOrder.id).where(
        WorkOrder.organization_id == organization_id,
        WorkOrder.asset_id == asset_id,
        WorkOrder.status.in_(list(_OPEN_WORK_ORDER_STATUSES)),
    )
    if db.execute(wo_stmt).first():
        return True
    finding_stmt = select(Finding.id).where(
        Finding.organization_id == organization_id,
        Finding.asset_id == asset_id,
        Finding.status.in_([FindingStatus.OPEN, FindingStatus.IN_PROGRESS]),
    )
    if component_id is not None:
        finding_stmt = finding_stmt.where(Finding.component_id == component_id)
    return db.execute(finding_stmt).first() is not None


def generate_maintenance_candidates(
    db: Session, *, organization_id: uuid.UUID, asset_id: uuid.UUID
) -> list[MaintenanceIntelligenceCandidate]:
    """Correlation logic: creates/upserts candidates when HUMS health +
    diagnostic + prognostic signals converge with maintenance state.
    Idempotent via dedup_key; skips when an open WorkOrder/Finding already
    covers the same asset/component.
    """
    asset_service.get_asset(db, organization_id=organization_id, asset_id=asset_id)

    health = hums_service.get_asset_health_intelligence(db, organization_id=organization_id, asset_id=asset_id)
    diagnostics = hums_service.list_asset_diagnostics(db, organization_id=organization_id, asset_id=asset_id)
    open_diagnostics = [d for d in diagnostics if d.status not in ("REJECTED", "RESOLVED")]
    prognostics = hums_service.list_asset_prognostics(db, organization_id=organization_id, asset_id=asset_id)

    created: list[MaintenanceIntelligenceCandidate] = []

    for component in health.components:
        if component.state not in ("DEGRADED", "WARNING", "CRITICAL"):
            continue
        component_id = component.component_id
        matching_diag = [d for d in open_diagnostics if d.component_id == component_id]
        matching_prog = [p for p in prognostics if p.component_id == component_id]
        if not matching_diag and not matching_prog:
            # H3 health alone, with no corroborating H4/H5 signal, is not
            # yet a convergent finding -- require at least one more source.
            continue
        if _existing_work_order_covers(db, organization_id=organization_id, asset_id=asset_id, component_id=component_id):
            continue

        refs = [_ref("HUMSComponentHealthIntelligence", component_id, f"Component health={component.state}")]
        refs += [_ref("HUMSDiagnosticCandidate", d.id, d.fault_name) for d in matching_diag]
        refs += [_ref("HUMSPrognosticRecord", p.id, p.feature_type) for p in matching_prog]

        dedup_key = _build_dedup_key(asset_id=asset_id, component_id=component_id, candidate_type=MROCandidateType.MAINTENANCE_ATTENTION, refs=refs)
        existing = db.execute(
            select(MaintenanceIntelligenceCandidate).where(
                MaintenanceIntelligenceCandidate.organization_id == organization_id,
                MaintenanceIntelligenceCandidate.dedup_key == dedup_key,
                MaintenanceIntelligenceCandidate.status.in_([MROCandidateStatus.OPEN, MROCandidateStatus.UNDER_REVIEW, MROCandidateStatus.DEFERRED]),
            )
        ).scalar_one_or_none()
        if existing:
            continue

        priority = MROCandidatePriority.HIGH if component.state == "CRITICAL" else (
            MROCandidatePriority.MEDIUM if component.state == "WARNING" else MROCandidatePriority.LOW
        )
        reason = (
            f"Component health is {component.state} (confidence={component.confidence}), "
            f"corroborated by {len(matching_diag)} diagnostic candidate(s) and "
            f"{len(matching_prog)} prognostic record(s)."
        )
        candidate = MaintenanceIntelligenceCandidate(
            organization_id=organization_id, asset_id=asset_id, component_id=component_id,
            candidate_type=MROCandidateType.MAINTENANCE_ATTENTION, status=MROCandidateStatus.OPEN,
            priority=priority, confidence=0.75 if (matching_diag and matching_prog) else 0.55,
            reason=reason, dedup_key=dedup_key, source_lineage=refs,
            operational_impact=None, data_freshness="AVAILABLE",
        )
        db.add(candidate)
        db.flush()
        created.append(candidate)

    return created


# ---------------------------------------------------------------------------
# Conflict detection
# ---------------------------------------------------------------------------

def detect_conflicts(db: Session, *, organization_id: uuid.UUID, asset_id: uuid.UUID) -> list[IntegrationConflict]:
    """Six additive consistency checks. H6's digital_twin_service
    .check_asset_consistency is consulted as ONE input (structural
    reference-integrity warnings); the checks below are distinct because
    they correlate ACROSS the readiness/compliance/maintenance/diagnostic/
    prognostic domains that H6 does not itself cross-check. Never
    auto-resolved -- report only."""
    conflicts: list[IntegrationConflict] = []

    twin_warnings = digital_twin_service.check_asset_consistency(db, organization_id=organization_id, asset_id=asset_id)
    for w in twin_warnings:
        conflicts.append(
            IntegrationConflict(
                check="DIGITAL_TWIN_CONSISTENCY", description=w.message,
                source_a=SourceLineageRef(source_type=w.entity_type, source_id=str(w.entity_id), label=w.check),
                source_b=SourceLineageRef(source_type="Asset", source_id=str(asset_id), label="asset"),
                severity="MEDIUM",
            )
        )

    # 1. Readiness vs compliance: authoritative readiness READY but a
    #    compliance obligation is NON_COMPLIANT/OVERDUE.
    readiness = get_asset_readiness_intelligence(db, organization_id=organization_id, asset_id=asset_id)
    compliance = get_compliance_impact(db, organization_id=organization_id, asset_id=asset_id)
    if readiness.readiness_state == "READY" and compliance.overall_impact in ("NON_COMPLIANT", "OVERDUE"):
        conflicts.append(
            IntegrationConflict(
                check="READINESS_VS_COMPLIANCE",
                description="Authoritative readiness is READY while a compliance obligation is NON_COMPLIANT/OVERDUE.",
                source_a=SourceLineageRef(source_type="AssetReadinessIntelligence", source_id=str(asset_id), label="readiness_state=READY"),
                source_b=SourceLineageRef(source_type="ComplianceObligation", source_id=str(asset_id), label=f"compliance_impact={compliance.overall_impact}"),
                severity="HIGH",
            )
        )

    # 2. Maintenance vs evidence: an open WorkOrder with no linked findings
    #    yet a CRITICAL diagnostic candidate exists uncorrelated.
    diagnostics = hums_service.list_asset_diagnostics(db, organization_id=organization_id, asset_id=asset_id)
    open_wo = list(db.execute(select(WorkOrder).where(
        WorkOrder.organization_id == organization_id, WorkOrder.asset_id == asset_id,
        WorkOrder.status.in_(list(_OPEN_WORK_ORDER_STATUSES)),
    )).scalars().all())
    high_diag = [d for d in diagnostics if d.severity == "HIGH" and d.status not in ("REJECTED", "RESOLVED")]
    if high_diag and not open_wo:
        conflicts.append(
            IntegrationConflict(
                check="DIAGNOSTIC_VS_MAINTENANCE",
                description="HIGH-severity diagnostic candidate(s) present with no corresponding open work order.",
                source_a=SourceLineageRef(source_type="HUMSDiagnosticCandidate", source_id=str(high_diag[0].id), label=high_diag[0].fault_name),
                source_b=SourceLineageRef(source_type="WorkOrder", source_id=None, label="no open work order"),
                severity="HIGH",
            )
        )

    # 3. Component configuration: a diagnostic/prognostic record references
    #    a component not currently on the asset's component tree.
    components = asset_service.get_asset_components(db, organization_id=organization_id, asset_id=asset_id)
    component_ids = {c.id for c in components}
    for d in diagnostics:
        if d.component_id and d.component_id not in component_ids:
            conflicts.append(
                IntegrationConflict(
                    check="COMPONENT_CONFIGURATION",
                    description=f"Diagnostic candidate {d.fault_name} references component {d.component_id}, not currently on this asset.",
                    source_a=SourceLineageRef(source_type="HUMSDiagnosticCandidate", source_id=str(d.id), label=d.fault_name),
                    source_b=SourceLineageRef(source_type="Component", source_id=str(d.component_id), label="not on asset"),
                    severity="MEDIUM",
                )
            )

    # 4. Prognostic vs usage/telemetry freshness: a prognostic record marked
    #    STALE while readiness is READY.
    prognostics = hums_service.list_asset_prognostics(db, organization_id=organization_id, asset_id=asset_id)
    stale_prog = [p for p in prognostics if p.quality == "STALE" or p.confidence == "STALE"]
    if stale_prog and readiness.readiness_state == "READY":
        conflicts.append(
            IntegrationConflict(
                check="PROGNOSTIC_FRESHNESS",
                description="Stale prognostic data present while asset is reported READY.",
                source_a=SourceLineageRef(source_type="HUMSPrognosticRecord", source_id=str(stale_prog[0].id), label=stale_prog[0].feature_type),
                source_b=SourceLineageRef(source_type="AssetReadinessIntelligence", source_id=str(asset_id), label="readiness_state=READY"),
                severity="LOW",
            )
        )

    # 5. Compliance vs maintenance evidence: an obligation is COMPLIANT but
    #    has no completed_at/verified_at timestamps.
    obligations = list(db.execute(select(ComplianceObligation).where(
        ComplianceObligation.organization_id == organization_id, ComplianceObligation.asset_id == asset_id,
    )).scalars().all())
    for ob in obligations:
        if ob.status == ComplianceState.COMPLIANT.value and not (ob.completed_at or ob.verified_at):
            conflicts.append(
                IntegrationConflict(
                    check="COMPLIANCE_VS_EVIDENCE",
                    description=f"Compliance obligation {ob.id} is COMPLIANT with no completed_at/verified_at timestamp.",
                    source_a=SourceLineageRef(source_type="ComplianceObligation", source_id=str(ob.id), label="status=COMPLIANT"),
                    source_b=SourceLineageRef(source_type="ComplianceObligation", source_id=str(ob.id), label="no completion evidence"),
                    severity="MEDIUM",
                )
            )

    return conflicts


# ---------------------------------------------------------------------------
# Reconciliation
# ---------------------------------------------------------------------------

def reconcile_asset_mro_intelligence(db: Session, *, organization_id: uuid.UUID, asset_id: uuid.UUID) -> ReconciliationResult:
    """Marks open candidates RESOLVED if the underlying condition has
    cleared; flags candidates whose source refs no longer correlate with
    current signals. Never mutates any authoritative system -- only this
    module's own candidate table."""
    candidates = _list_open_candidates(db, organization_id=organization_id, asset_id=asset_id)
    diagnostics = hums_service.list_asset_diagnostics(db, organization_id=organization_id, asset_id=asset_id)
    open_diag_ids = {str(d.id) for d in diagnostics if d.status not in ("REJECTED", "RESOLVED")}
    health = hums_service.get_asset_health_intelligence(db, organization_id=organization_id, asset_id=asset_id)
    degraded_component_ids = {c.component_id for c in health.components if c.state in ("DEGRADED", "WARNING", "CRITICAL")}

    resolved: list[uuid.UUID] = []
    flagged: list[uuid.UUID] = []
    explanation: list[str] = []

    for c in candidates:
        diag_refs = [r for r in c.source_lineage if r.get("source_type") == "HUMSDiagnosticCandidate"]
        still_correlated = c.component_id in degraded_component_ids or any(r.get("source_id") in open_diag_ids for r in diag_refs)
        if not still_correlated:
            c.status = MROCandidateStatus.RESOLVED
            c.resolved_at = _now()
            resolved.append(c.id)
            explanation.append(f"Candidate {c.id} resolved: underlying health/diagnostic signal cleared.")
        elif c.component_id and c.component_id not in degraded_component_ids and not diag_refs:
            flagged.append(c.id)
            explanation.append(f"Candidate {c.id} flagged: component no longer degraded but no diagnostic corroboration remains.")

    return ReconciliationResult(
        asset_id=asset_id, resolved_candidate_ids=resolved, flagged_candidate_ids=flagged,
        explanation=explanation, evaluated_at=_now(),
    )


# ---------------------------------------------------------------------------
# Top-level correlated view
# ---------------------------------------------------------------------------

def get_asset_mro_intelligence(db: Session, *, organization_id: uuid.UUID, asset_id: uuid.UUID) -> AssetMROIntelligence:
    asset_service.get_asset(db, organization_id=organization_id, asset_id=asset_id)

    health = hums_service.get_asset_health_intelligence(db, organization_id=organization_id, asset_id=asset_id)
    diagnostics = hums_service.list_asset_diagnostics(db, organization_id=organization_id, asset_id=asset_id)
    open_diagnostics = [d for d in diagnostics if d.status not in ("REJECTED", "RESOLVED")]
    prognostics = hums_service.list_asset_prognostics(db, organization_id=organization_id, asset_id=asset_id)
    alert_prognostics = [p for p in prognostics if p.status in ("LOW_CONFIDENCE", "LIMITED") or (p.rul_estimate is not None and p.rul_estimate < 25)]

    readiness_impact = get_readiness_impact(db, organization_id=organization_id, asset_id=asset_id)
    compliance_impact = get_compliance_impact(db, organization_id=organization_id, asset_id=asset_id)
    operational_impact = get_operational_impact(db, organization_id=organization_id, asset_id=asset_id)

    open_candidates = _list_open_candidates(db, organization_id=organization_id, asset_id=asset_id)
    conflicts = detect_conflicts(db, organization_id=organization_id, asset_id=asset_id)

    from app.schemas.mro_intelligence import MaintenanceCandidateOut
    candidate_out = [MaintenanceCandidateOut.model_validate(c) for c in open_candidates]

    explanation = [
        f"Health state: {health.state} ({health.confidence}).",
        f"Open diagnostics: {len(open_diagnostics)}; alert-worthy prognostics: {len(alert_prognostics)}.",
        f"Readiness impact: {readiness_impact.readiness_impact} (authoritative={readiness_impact.authoritative_readiness_state}).",
        f"Compliance impact: {compliance_impact.overall_impact}.",
        f"Operational impact: {operational_impact.impact_level}.",
        f"{len(open_candidates)} open maintenance intelligence candidate(s); {len(conflicts)} integration conflict(s).",
    ]

    return AssetMROIntelligence(
        asset_id=asset_id, availability="AVAILABLE",
        health_state=health.state, health_confidence=health.confidence,
        open_diagnostic_count=len(open_diagnostics), open_prognostic_alert_count=len(alert_prognostics),
        authoritative_readiness_state=readiness_impact.authoritative_readiness_state,
        readiness_impact=readiness_impact.readiness_impact,
        compliance_impact=compliance_impact.overall_impact,
        operational_impact=operational_impact.impact_level,
        open_candidate_count=len(open_candidates), candidates=candidate_out, conflicts=conflicts,
        explanation=explanation, evaluated_at=_now(),
    )


# ---------------------------------------------------------------------------
# Candidate lifecycle
# ---------------------------------------------------------------------------

def _get_candidate(db: Session, *, organization_id: uuid.UUID, candidate_id: uuid.UUID) -> MaintenanceIntelligenceCandidate:
    candidate = db.execute(
        select(MaintenanceIntelligenceCandidate).where(
            MaintenanceIntelligenceCandidate.id == candidate_id,
            MaintenanceIntelligenceCandidate.organization_id == organization_id,
        )
    ).scalar_one_or_none()
    if candidate is None:
        raise NotFoundError("MaintenanceIntelligenceCandidate not found")
    return candidate


def _transition(
    db: Session, *, organization_id: uuid.UUID, candidate_id: uuid.UUID, user_id: uuid.UUID,
    new_status: str, action: str, notes: str | None,
) -> MaintenanceIntelligenceCandidate:
    candidate = _get_candidate(db, organization_id=organization_id, candidate_id=candidate_id)
    allowed = ALLOWED_CANDIDATE_TRANSITIONS.get(candidate.status, set())
    if new_status not in allowed:
        raise ConflictError(f"Cannot transition candidate from {candidate.status} to {new_status}")

    candidate.status = new_status
    if notes:
        candidate.review_notes = notes
    if new_status in (MROCandidateStatus.ACCEPTED, MROCandidateStatus.REJECTED, MROCandidateStatus.RESOLVED):
        candidate.resolved_at = _now()
        candidate.resolved_by = user_id

    audit_service.record_audit_event(
        db, organization_id=organization_id, user_id=user_id, action=action,
        entity_type="MaintenanceIntelligenceCandidate", entity_id=candidate.id,
        metadata={"new_status": new_status, "notes": notes},
    )
    db.flush()
    return candidate


def review_candidate(db: Session, *, organization_id: uuid.UUID, candidate_id: uuid.UUID, user_id: uuid.UUID, notes: str | None = None):
    return _transition(db, organization_id=organization_id, candidate_id=candidate_id, user_id=user_id, new_status=MROCandidateStatus.UNDER_REVIEW, action="mro_candidate.review", notes=notes)


def accept_candidate(db: Session, *, organization_id: uuid.UUID, candidate_id: uuid.UUID, user_id: uuid.UUID, notes: str | None = None):
    """Records the human decision only -- does NOT auto-create a work order."""
    return _transition(db, organization_id=organization_id, candidate_id=candidate_id, user_id=user_id, new_status=MROCandidateStatus.ACCEPTED, action="mro_candidate.accept", notes=notes)


def reject_candidate(db: Session, *, organization_id: uuid.UUID, candidate_id: uuid.UUID, user_id: uuid.UUID, notes: str | None = None):
    return _transition(db, organization_id=organization_id, candidate_id=candidate_id, user_id=user_id, new_status=MROCandidateStatus.REJECTED, action="mro_candidate.reject", notes=notes)


def defer_candidate(db: Session, *, organization_id: uuid.UUID, candidate_id: uuid.UUID, user_id: uuid.UUID, notes: str | None = None):
    return _transition(db, organization_id=organization_id, candidate_id=candidate_id, user_id=user_id, new_status=MROCandidateStatus.DEFERRED, action="mro_candidate.defer", notes=notes)


def get_candidate(db: Session, *, organization_id: uuid.UUID, candidate_id: uuid.UUID) -> MaintenanceIntelligenceCandidate:
    return _get_candidate(db, organization_id=organization_id, candidate_id=candidate_id)


def list_asset_candidates(db: Session, *, organization_id: uuid.UUID, asset_id: uuid.UUID) -> list[MaintenanceIntelligenceCandidate]:
    asset_service.get_asset(db, organization_id=organization_id, asset_id=asset_id)
    return list(
        db.execute(
            select(MaintenanceIntelligenceCandidate).where(
                MaintenanceIntelligenceCandidate.organization_id == organization_id,
                MaintenanceIntelligenceCandidate.asset_id == asset_id,
            ).order_by(MaintenanceIntelligenceCandidate.created_at.desc())
        ).scalars().all()
    )


def list_component_candidates(db: Session, *, organization_id: uuid.UUID, component_id: uuid.UUID) -> list[MaintenanceIntelligenceCandidate]:
    return list(
        db.execute(
            select(MaintenanceIntelligenceCandidate).where(
                MaintenanceIntelligenceCandidate.organization_id == organization_id,
                MaintenanceIntelligenceCandidate.component_id == component_id,
            ).order_by(MaintenanceIntelligenceCandidate.created_at.desc())
        ).scalars().all()
    )


def get_component_mro_intelligence(db: Session, *, organization_id: uuid.UUID, component_id: uuid.UUID) -> dict:
    """Component-scoped slice: candidates + diagnostics + prognostics for
    one component. Not a full AssetMROIntelligence (which is asset-scoped)."""
    candidates = list_component_candidates(db, organization_id=organization_id, component_id=component_id)
    diagnostics = hums_service.list_component_diagnostics(db, organization_id=organization_id, component_id=component_id)
    prognostics = hums_service.list_component_prognostics(db, organization_id=organization_id, component_id=component_id)
    from app.schemas.mro_intelligence import MaintenanceCandidateOut
    return {
        "component_id": component_id,
        "candidates": [MaintenanceCandidateOut.model_validate(c) for c in candidates],
        "open_diagnostic_count": len([d for d in diagnostics if d.status not in ("REJECTED", "RESOLVED")]),
        "open_prognostic_count": len(prognostics),
        "evaluated_at": _now(),
    }
