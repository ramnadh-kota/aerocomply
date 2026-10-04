"""Tool registry for the Lisa agent.

Every tool wraps an EXISTING backend service — nothing here recomputes or
reimplements business logic. Every handler takes organization_id from the
authenticated caller ONLY (never from model/tool input), exactly like every
existing v1 endpoint.

Domain boundary (read before adding a tool): as of M3.1-M3.14, this backend
has real, database-backed Aircraft / WorkOrder / Task / Evidence /
InspectionRequirement / TAT / ReleaseReadiness / Part / PartRequirement /
InventoryTransaction / Vendor / VendorPartAvailability (vendor fit) /
ProcurementRequest / PurchaseOrder / AogEvent / MaintenanceRequirement /
DeferredItem / ComplianceAssessment / RegulatoryDocument / MRO Control
Center domains — tools below cover all of them. Regulatory *applicability
rules* (condition-tree evaluation) and aircraft flight-hour/cycle
utilization remain NOT backend-resident (see compliance.py/
maintenance_service.py docstrings) — do not add tools that would let the
model answer as if those existed.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AeroComplyError, ForbiddenError, NotFoundError
from app.core.feature_keys import (
    canonicalize_feature_key,
    is_default_on_feature,
)
from app.core.permissions import Permission, permissions_for_roles
from app.models.aircraft import Aircraft
from app.schemas.auth import CurrentUser
from app.services import (
    aircraft_service,
    aog_recovery_service,
    aog_service,
    compliance_service,
    control_center_service,
    deferred_item_service,
    evidence_service,
    inspection_service,
    inventory_transaction_service,
    maintenance_service,
    part_requirement_service,
    part_service,
    proactive_service,
    procurement_service,
    purchase_order_service,
    regulatory_service,
    release_readiness_service,
    tat_service,
    technician_service,
    vendor_fit_service,
    vendor_service,
    work_order_service,
    mro_intelligence_service,
)
from app.services.assessment import engine as assessment_engine
from app.services.entitlement_service import (
    EntitlementResolutionStatus,
    is_feature_allowed_for_suite,
    resolve_entitlements,
)
from app.services.intelligence import context_service as intelligence_context_service
from app.services.intelligence import cross_asset_intelligence_service
from app.services.intelligence import fleet_intelligence_service
from app.services.intelligence import proactive_intelligence_service


ToolHandler = Callable[[Session, CurrentUser, dict[str, Any]], dict[str, Any]]


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    input_schema: dict[str, Any]
    handler: ToolHandler
    # Every tool maps to the SAME permission its equivalent REST endpoint
    # requires (see the matching app/api/v1/*.py router) — Lisa never grants
    # a caller access to data their role couldn't already read directly.
    required_permission: Permission
    required_feature: str | None = None
    required_suite: str | None = None


def _require_permission(user: Any, permission: Permission) -> None:
    roles = getattr(user, "roles", None)
    if not roles:
        user_roles = getattr(user, "role_links", None) or getattr(user, "user_roles", None)
        if user_roles:
            roles = [ur.role_name if hasattr(ur, "role_name") else str(ur) for ur in user_roles]
        else:
            roles = []
    if not roles or permission.value not in permissions_for_roles(roles):
        raise ForbiddenError(
            f"Role does not have permission {permission.value}", code="forbidden"
        )


def _require_entitlement(db: Session, user: CurrentUser, spec: ToolSpec) -> None:
    org_id = getattr(user, "organization_id", None)
    if not org_id:
        raise ForbiddenError("User has no organization context", code="forbidden")

    result = resolve_entitlements(db, organization_id=org_id)
    _GRANTING_STATUSES = frozenset(
        {EntitlementResolutionStatus.ACTIVE, EntitlementResolutionStatus.INACTIVE_PLAN}
    )
    if result.resolution_status not in _GRANTING_STATUSES:
        raise ForbiddenError(
            f"Organization subscription is not active (status: {result.resolution_status.value})",
            code="SUITE_ENTITLEMENT_REQUIRED" if result.resolution_status == EntitlementResolutionStatus.NO_SUBSCRIPTION else "forbidden",
        )

    if spec.required_suite:
        allowed_suites = {s.strip().upper() for s in spec.required_suite.split(",")}
        # A multi-suite organization reports suite_code MULTI_SUITE; the suites it actually holds are in active_suites.
        held = {(x.get("suite_code") or "").strip().upper() for x in getattr(result, "active_suites", []) if x.get("suite_code")}
        if result.suite_code and result.suite_code != "MULTI_SUITE":
            held.add(result.suite_code.strip().upper())
        if held and not (held & allowed_suites):
            raise ForbiddenError(
                f"Organization product suite ({', '.join(sorted(held))}) is not entitled to use tool '{spec.name}'. Required: {spec.required_suite}",
                code="SUITE_ENTITLEMENT_REQUIRED",
            )

    if spec.required_feature:
        # "a,b,c" means ANY of the listed features entitles the tool (e.g. any fleet-family feature).
        candidates = [f.strip() for f in spec.required_feature.split(",") if f.strip()]

        def _entitled(feature_key: str) -> bool:
            canonical = canonicalize_feature_key(feature_key)
            configured = [
                v for v in (
                    result.effective_features.get(feature_key),
                    result.effective_features.get(canonical),
                ) if v is not None
            ]
            return any(configured) if configured else is_default_on_feature(canonical)

        if not any(_entitled(f) for f in candidates):
            feature_key = candidates[0]
            outside_suite = bool(result.suite_code) and result.suite_code != "MULTI_SUITE" and not any(
                is_feature_allowed_for_suite(result.suite_code, f) for f in candidates
            )
            raise ForbiddenError(
                f"Organization is not entitled to feature '{spec.required_feature}' required by tool '{spec.name}'",
                code="SUITE_ENTITLEMENT_REQUIRED" if outside_suite else "forbidden",
            )


def _uuid(raw: Any, field: str) -> uuid.UUID:
    try:
        return uuid.UUID(str(raw))
    except (ValueError, TypeError) as exc:
        raise AeroComplyError(
            f"Invalid UUID for {field}: {raw!r}", code="invalid_tool_input"
        ) from exc


def _try_uuid(raw: Any) -> uuid.UUID | None:
    try:
        return uuid.UUID(str(raw))
    except (ValueError, TypeError):
        return None


def _assessment_to_dict(a: Any) -> dict[str, Any]:
    return {
        "id": str(a.id),
        "name": a.name,
        "scope_type": a.scope_type,
        "scope_id": str(a.scope_id) if a.scope_id else None,
        "status": a.status,
        "created_at": a.created_at.isoformat() if a.created_at else None,
    }


def _snapshot_to_dict(s: Any) -> dict[str, Any]:
    return {
        "id": str(s.id),
        "assessment_id": str(s.assessment_id),
        "version": s.version,
        "overall_score": s.overall_score,
        "maturity_band": s.maturity_band,
        "summary": s.summary,
        "finding_count": s.finding_count,
        "critical_finding_count": s.critical_finding_count,
    }


def _finding_to_dict(f: Any) -> dict[str, Any]:
    return {
        "id": str(f.id),
        "category": f.category,
        "severity": f.severity,
        "title": f.title,
        "description": f.description,
        "entity_type": f.entity_type,
        "entity_id": f.entity_id,
        "materiality_score": f.materiality_score,
        "complexity_band": f.complexity_band,
        "dependency_count": f.dependency_count,
        "impact_dimensions": list(f.impact_dimensions),
        "priority_rank": f.priority_rank,
        "source": f.source,
        "resolved": f.resolved,
    }


def _risk_to_dict(r: Any) -> dict[str, Any]:
    return {
        "id": str(r.id),
        "finding_id": str(r.finding_id) if r.finding_id else None,
        "risk_level": r.risk_level,
        "likelihood": r.likelihood,
        "reason": r.reason,
        "entity_type": r.entity_type,
        "entity_id": r.entity_id,
        "mitigation": r.mitigation,
        "owner_role": r.owner_role,
    }


def _gap_to_dict(g: Any) -> dict[str, Any]:
    return {
        "id": str(g.id),
        "finding_id": str(g.finding_id) if g.finding_id else None,
        "category": g.category,
        "severity": g.severity,
        "entity_type": g.entity_type,
        "entity_id": g.entity_id,
        "expected_condition": g.expected_condition,
        "current_condition": g.current_condition,
        "recommended_action": g.recommended_action,
    }


def _recommendation_to_dict(r: Any) -> dict[str, Any]:
    return {
        "id": str(r.id),
        "finding_id": str(r.finding_id) if r.finding_id else None,
        "recommendation": r.recommendation,
        "why": r.why,
        "priority": r.priority,
        "responsible_role": r.responsible_role,
        "entity_type": r.entity_type,
        "entity_id": r.entity_id,
        "status": r.status,
    }


def _roadmap_item_to_dict(r: Any) -> dict[str, Any]:
    return {
        "id": str(r.id),
        "finding_id": str(r.finding_id) if r.finding_id else None,
        "sequence": r.sequence,
        "title": r.title,
        "description": r.description,
        "category": r.category,
        "priority": r.priority,
        "status": r.status,
        "entity_type": r.entity_type,
        "entity_id": r.entity_id,
        "prerequisite_sequence_numbers": list(r.prerequisite_sequence_numbers),
        "owner_role": r.owner_role,
        "estimated_effort_band": r.estimated_effort_band,
        "effort_confidence": r.effort_confidence,
        "expected_impact": r.expected_impact,
        "risk_if_delayed": r.risk_if_delayed,
    }


def _handle_get_assessments(db: Session, user: CurrentUser, args: dict[str, Any]) -> dict[str, Any]:
    assessments = assessment_engine.list_assessments(db, organization_id=user.organization_id)
    return {"assessments": [_assessment_to_dict(a) for a in assessments]}


def _handle_get_assessment(db: Session, user: CurrentUser, args: dict[str, Any]) -> dict[str, Any]:
    assessment_id = _uuid(args["assessment_id"], "assessment_id")
    assessment = assessment_engine.get_assessment(
        db, organization_id=user.organization_id, assessment_id=assessment_id
    )
    snapshot = assessment_engine.get_latest_snapshot(
        db, organization_id=user.organization_id, assessment_id=assessment_id
    )
    return {
        "assessment": _assessment_to_dict(assessment),
        "latest_snapshot": _snapshot_to_dict(snapshot) if snapshot else None,
    }


def _handle_run_assessment(db: Session, user: CurrentUser, args: dict[str, Any]) -> dict[str, Any]:
    assessment_id = _uuid(args["assessment_id"], "assessment_id")
    snapshot = assessment_engine.run_assessment(
        db,
        organization_id=user.organization_id,
        actor_user_id=user.id,
        assessment_id=assessment_id,
    )
    return {"snapshot": _snapshot_to_dict(snapshot)}


def _handle_get_assessment_findings(
    db: Session, user: CurrentUser, args: dict[str, Any]
) -> dict[str, Any]:
    assessment_id = _uuid(args["assessment_id"], "assessment_id")
    assessment_engine.get_assessment(
        db, organization_id=user.organization_id, assessment_id=assessment_id
    )
    snapshot = assessment_engine.get_latest_snapshot(
        db, organization_id=user.organization_id, assessment_id=assessment_id
    )
    if snapshot is None:
        return {"findings": [], "note": "This assessment has not been run yet."}
    return {"findings": [_finding_to_dict(f) for f in snapshot.findings]}


def _handle_get_assessment_risks(
    db: Session, user: CurrentUser, args: dict[str, Any]
) -> dict[str, Any]:
    assessment_id = _uuid(args["assessment_id"], "assessment_id")
    assessment_engine.get_assessment(
        db, organization_id=user.organization_id, assessment_id=assessment_id
    )
    snapshot = assessment_engine.get_latest_snapshot(
        db, organization_id=user.organization_id, assessment_id=assessment_id
    )
    if snapshot is None:
        return {"risks": [], "note": "This assessment has not been run yet."}
    return {"risks": [_risk_to_dict(r) for r in snapshot.risks]}


def _handle_get_assessment_gaps(
    db: Session, user: CurrentUser, args: dict[str, Any]
) -> dict[str, Any]:
    assessment_id = _uuid(args["assessment_id"], "assessment_id")
    assessment_engine.get_assessment(
        db, organization_id=user.organization_id, assessment_id=assessment_id
    )
    snapshot = assessment_engine.get_latest_snapshot(
        db, organization_id=user.organization_id, assessment_id=assessment_id
    )
    if snapshot is None:
        return {"gaps": [], "note": "This assessment has not been run yet."}
    return {"gaps": [_gap_to_dict(g) for g in snapshot.gaps]}


def _handle_get_assessment_recommendations(
    db: Session, user: CurrentUser, args: dict[str, Any]
) -> dict[str, Any]:
    assessment_id = _uuid(args["assessment_id"], "assessment_id")
    assessment_engine.get_assessment(
        db, organization_id=user.organization_id, assessment_id=assessment_id
    )
    snapshot = assessment_engine.get_latest_snapshot(
        db, organization_id=user.organization_id, assessment_id=assessment_id
    )
    if snapshot is None:
        return {"recommendations": [], "note": "This assessment has not been run yet."}
    return {"recommendations": [_recommendation_to_dict(r) for r in snapshot.recommendations]}


def _handle_get_assessment_roadmap(
    db: Session, user: CurrentUser, args: dict[str, Any]
) -> dict[str, Any]:
    assessment_id = _uuid(args["assessment_id"], "assessment_id")
    assessment_engine.get_assessment(
        db, organization_id=user.organization_id, assessment_id=assessment_id
    )
    snapshot = assessment_engine.get_latest_snapshot(
        db, organization_id=user.organization_id, assessment_id=assessment_id
    )
    if snapshot is None:
        return {"roadmap": [], "note": "This assessment has not been run yet."}
    items = sorted(snapshot.roadmap_items, key=lambda r: r.sequence)
    return {"roadmap": [_roadmap_item_to_dict(r) for r in items]}


def _handle_compare_assessment_snapshots(
    db: Session, user: CurrentUser, args: dict[str, Any]
) -> dict[str, Any]:
    snapshot_id_a = _uuid(args["snapshot_id_a"], "snapshot_id_a")
    snapshot_id_b = _uuid(args["snapshot_id_b"], "snapshot_id_b")
    comparison = assessment_engine.compare_snapshots(
        db,
        organization_id=user.organization_id,
        snapshot_id_a=snapshot_id_a,
        snapshot_id_b=snapshot_id_b,
    )
    return {
        "from_version": comparison.from_version,
        "to_version": comparison.to_version,
        "score_delta": comparison.score_delta,
        "new_findings": [_finding_to_dict(f) for f in comparison.new_findings],
        "resolved_findings": comparison.resolved_findings,
    }


def _aircraft_to_dict(a: Any) -> dict[str, Any]:
    return {
        "id": str(a.id),
        "registration": a.registration,
        "msn": a.msn,
        "aircraft_type": a.aircraft_type,
        "status": a.status,
    }


def _work_order_to_dict(w: Any) -> dict[str, Any]:
    return {
        "id": str(w.id),
        "aircraft_id": str(w.aircraft_id),
        "work_order_number": w.work_order_number,
        "status": w.status,
        "priority": w.priority,
    }


def _task_to_dict(t: Any) -> dict[str, Any]:
    return {
        "id": str(t.id),
        "work_order_id": str(t.work_order_id),
        # Task has no "status" column — execution_state is the real field
        # (see app/models/task.py). The previous version of this function
        # read a nonexistent "status" attribute and always returned None.
        "execution_state": getattr(t, "execution_state", None),
        "description": getattr(t, "description", None),
        "assigned_technician_user_id": (
            str(t.assigned_technician_user_id)
            if getattr(t, "assigned_technician_user_id", None)
            else None
        ),
    }


def _evidence_to_dict(e: Any) -> dict[str, Any]:
    return {
        "id": str(e.id),
        "task_id": str(e.task_id),
        "status": e.status,
        "uploaded_by_user_id": str(e.uploaded_by_user_id) if e.uploaded_by_user_id else None,
    }


def _inspection_to_dict(i: Any) -> dict[str, Any]:
    return {
        "id": str(i.id),
        "task_id": str(i.task_id),
        "work_order_id": str(i.work_order_id),
        "required": i.required,
        "status": i.status,
    }


def _handle_get_aircraft(db: Session, user: CurrentUser, args: dict[str, Any]) -> dict[str, Any]:
    aircraft_id = _uuid(args["aircraft_id"], "aircraft_id")
    aircraft = aircraft_service.get_aircraft(
        db, organization_id=user.organization_id, aircraft_id=aircraft_id
    )
    return _aircraft_to_dict(aircraft)


def _handle_list_aircraft(db: Session, user: CurrentUser, args: dict[str, Any]) -> dict[str, Any]:
    items = aircraft_service.list_aircraft(db, organization_id=user.organization_id)
    return {"aircraft": [_aircraft_to_dict(a) for a in items]}


def _handle_get_work_order(db: Session, user: CurrentUser, args: dict[str, Any]) -> dict[str, Any]:
    work_order_id = _uuid(args["work_order_id"], "work_order_id")
    wo = work_order_service.get_work_order(
        db, organization_id=user.organization_id, work_order_id=work_order_id
    )
    return _work_order_to_dict(wo)


def _handle_get_work_order_tasks(
    db: Session, user: CurrentUser, args: dict[str, Any]
) -> dict[str, Any]:
    work_order_id = _uuid(args["work_order_id"], "work_order_id")
    tasks = work_order_service.list_tasks_for_work_order(
        db, organization_id=user.organization_id, work_order_id=work_order_id
    )
    return {"tasks": [_task_to_dict(t) for t in tasks]}


def _handle_get_task(db: Session, user: CurrentUser, args: dict[str, Any]) -> dict[str, Any]:
    task_id = _uuid(args["task_id"], "task_id")
    task = work_order_service.get_task(db, organization_id=user.organization_id, task_id=task_id)
    return _task_to_dict(task)


def _handle_get_evidence(db: Session, user: CurrentUser, args: dict[str, Any]) -> dict[str, Any]:
    evidence_id = _uuid(args["evidence_id"], "evidence_id")
    evidence = evidence_service.get_evidence(
        db, organization_id=user.organization_id, evidence_id=evidence_id
    )
    return _evidence_to_dict(evidence)


def _handle_list_evidence_for_task(
    db: Session, user: CurrentUser, args: dict[str, Any]
) -> dict[str, Any]:
    task_id = _uuid(args["task_id"], "task_id")
    items = evidence_service.list_evidence_for_task(
        db, organization_id=user.organization_id, task_id=task_id
    )
    return {"evidence": [_evidence_to_dict(e) for e in items]}


def _handle_get_inspection(db: Session, user: CurrentUser, args: dict[str, Any]) -> dict[str, Any]:
    inspection_id = _uuid(args["inspection_id"], "inspection_id")
    requirement = inspection_service.get_inspection_requirement(
        db, organization_id=user.organization_id, requirement_id=inspection_id
    )
    return _inspection_to_dict(requirement)


def _handle_list_inspections_for_work_order(
    db: Session, user: CurrentUser, args: dict[str, Any]
) -> dict[str, Any]:
    work_order_id = _uuid(args["work_order_id"], "work_order_id")
    items = inspection_service.list_inspection_requirements_for_work_order(
        db, organization_id=user.organization_id, work_order_id=work_order_id
    )
    return {"inspections": [_inspection_to_dict(i) for i in items]}


def _handle_get_tat(db: Session, user: CurrentUser, args: dict[str, Any]) -> dict[str, Any]:
    work_order_id = _uuid(args["work_order_id"], "work_order_id")
    status = tat_service.get_work_order_tat_status(
        db, organization_id=user.organization_id, work_order_id=work_order_id
    )
    return {
        "work_order_id": str(work_order_id),
        "status": status.status,
        "due_date": status.due_date.isoformat() if status.due_date else None,
        "reason": status.reason,
    }


def _handle_get_fleet_tat(db: Session, user: CurrentUser, args: dict[str, Any]) -> dict[str, Any]:
    summary = tat_service.get_fleet_tat_status(db, organization_id=user.organization_id)
    return {
        "on_track_count": summary.on_track_count,
        "at_risk_count": summary.at_risk_count,
        "delayed_count": summary.delayed_count,
        "unknown_count": summary.unknown_count,
        "total_work_orders": summary.total_work_orders,
        "reason": summary.reason,
    }


def _handle_get_intelligence_context(
    db: Session, user: CurrentUser, args: dict[str, Any]
) -> dict[str, Any]:
    """M5.1 -- the deterministic D2.2 intelligence chain (readiness, risk,
    priority, decision, recommendation) plus D2.1's Aerospace Intelligence
    State, for one asset. This is the ONLY source Lisa may use to answer a
    question about an asset's readiness/risk/priority/decision/
    recommendation -- never computed by the model itself (see
    _SYSTEM_PROMPT in agent_service.py). Returns the IntelligenceContext
    contract (app/schemas/intelligence.py) unchanged, serialized to JSON --
    nothing here is recalculated, relabeled, or filtered.
    """
    asset_id = _uuid(args["asset_id"], "asset_id")
    context = intelligence_context_service.get_asset_intelligence_context(
        db, organization_id=user.organization_id, asset_id=asset_id
    )
    data = context.model_dump(mode="json")
    # D2.1's disclaimer field is fixed legal boilerplate ("...does not
    # constitute an electronic Release to Service (RTS) signature...") that
    # trips the deterministic safety layer's "release to service" guard
    # pattern (app/services/ai/safety.py) on every single call, regardless
    # of its own negation -- withholding the entire tool result every time
    # (confirmed by test). The system prompt already tells the model the
    # same non-authoritative boundary directly, so this field carries no
    # decision-relevant information the model needs; it is dropped here
    # rather than weakening the shared safety filter for every tool.
    data["aerospace_state"].pop("disclaimer", None)
    return data


_ATTENTION_DECISION_STATES = {
    "ACTION_REQUIRED",
    "IMMEDIATE_ACTION_REQUIRED",
    "MONITOR",
    "INSUFFICIENT_DATA",
}
_ATTENTION_PRIORITY_LEVELS = {"CRITICAL", "HIGH"}


def _fleet_blocker_to_dict(b: Any) -> dict[str, Any]:
    return {
        "source_domain": b.source_domain,
        "category": b.category,
        "description": b.description,
        "related_record_id": str(b.related_record_id) if b.related_record_id else None,
        "related_record_type": b.related_record_type,
        "required_action": b.required_action,
        "resolution_action": b.resolution_action,
        "regulatory_reference": b.regulatory_reference,
    }


def _fleet_asset_to_dict(a: Any, *, requires_attention: bool) -> dict[str, Any]:
    return {
        "asset_id": str(a.asset_id),
        "registration": a.registration,
        "asset_type": a.asset_type,
        "operational_state": a.operational_state,
        "aerospace_intelligence_status": a.aerospace_intelligence_status,
        "readiness_state": a.readiness_state,
        "risk_level": a.risk_level,
        "priority_level": a.priority_level,
        "decision_state": a.decision_state,
        "decision_reason": a.decision_reason,
        "top_recommendation_action": a.top_recommendation_action,
        "blocker_count": a.blocker_count,
        "warning_count": a.warning_count,
        "blockers": [_fleet_blocker_to_dict(b) for b in a.blockers],
        "requires_attention": requires_attention,
    }


def _handle_get_fleet_attention_summary(
    db: Session, user: CurrentUser, args: dict[str, Any]
) -> dict[str, Any]:
    """M5.2/M5.3 -- grounded fleet question support (attention, state, risk,
    readiness, blockers, recommendations, brief, and multi-asset
    comparison), reusing M4.2's fleet_intelligence_service exactly as the
    frontend Control Center already does -- no new fleet calculation,
    purely a presentation-layer filter/tally/reshape over the same
    already-computed FleetIntelligenceSummary values. One tool, one fleet
    call, regardless of which of these questions is asked -- never N assets
    x 5 endpoints, and never a second overlapping fleet tool.

    M5.3 additively extends the M5.2 payload (every M5.2 key is unchanged;
    existing M5.2 tests keep passing) with the FULL per-asset list (not
    just the attention subset -- needed for state/risk/readiness/blocker/
    comparison questions), each asset's full blocker detail (source_domain,
    category, description, related_record_id/type, required_action,
    resolution_action, regulatory_reference -- the same
    ReadinessIntelligenceBlocker fields M4.5/M5.1 already expose per-asset,
    not a new traceability vocabulary), and simple count distributions by
    operational_state/aerospace_intelligence_status/readiness_state/
    risk_level/priority_level/decision_state (pure tallying, identical in
    spirit to the M4.2 frontend Control Center's own client-side tallies --
    never a new fleet metric).
    """
    summary = fleet_intelligence_service.get_fleet_intelligence_summary(
        db, organization_id=user.organization_id
    )
    attention_ids = {
        a.asset_id
        for a in summary.assets
        if a.priority_level in _ATTENTION_PRIORITY_LEVELS
        or a.decision_state in _ATTENTION_DECISION_STATES
    }
    attention = [a for a in summary.assets if a.asset_id in attention_ids]

    def _tally(field: str) -> dict[str, int]:
        counts: dict[str, int] = {}
        for a in summary.assets:
            value = getattr(a, field)
            counts[value] = counts.get(value, 0) + 1
        return counts

    return {
        "contract_version": "1.0",
        "total_assets": summary.total_assets,
        "assets_requiring_attention_count": len(attention),
        "assets_requiring_attention": [
            {
                "asset_id": str(a.asset_id),
                "registration": a.registration,
                "asset_type": a.asset_type,
                "priority_level": a.priority_level,
                "decision_state": a.decision_state,
                "decision_reason": a.decision_reason,
                "blocker_count": a.blocker_count,
            }
            for a in attention
        ],
        # M5.3 additions below -- additive only, nothing above changed shape.
        "assets": [
            _fleet_asset_to_dict(a, requires_attention=a.asset_id in attention_ids)
            for a in summary.assets
        ],
        "distribution": {
            "operational_state": _tally("operational_state"),
            "aerospace_intelligence_status": _tally("aerospace_intelligence_status"),
            "readiness_state": _tally("readiness_state"),
            "risk_level": _tally("risk_level"),
            "priority_level": _tally("priority_level"),
            "decision_state": _tally("decision_state"),
        },
        "evaluated_at": summary.evaluated_at.isoformat(),
    }


def _handle_get_release_readiness(
    db: Session, user: CurrentUser, args: dict[str, Any]
) -> dict[str, Any]:
    work_order_id = _uuid(args["work_order_id"], "work_order_id")
    readiness = release_readiness_service.get_release_readiness_for_work_order(
        db, organization_id=user.organization_id, work_order_id=work_order_id
    )
    return {
        "work_order_id": str(work_order_id),
        "status": readiness.status,
        "blockers": [
            {
                "category": b.category,
                "description": b.description,
                "related_record_id": str(b.related_record_id) if b.related_record_id else None,
            }
            for b in readiness.blockers
        ],
        "data_completeness": readiness.data_completeness,
    }


def _handle_get_parts(db: Session, user: CurrentUser, args: dict[str, Any]) -> dict[str, Any]:
    parts = part_service.list_parts(db, organization_id=user.organization_id)
    return {
        "parts": [
            {
                "id": str(p.id),
                "part_number": p.part_number,
                "description": p.description,
                "serviceability_status": p.serviceability_status,
                "quantity_on_hand": p.quantity_on_hand,
                "quantity_reserved": p.quantity_reserved,
                "quantity_quarantined": p.quantity_quarantined,
                "available_quantity": p.available_quantity,
            }
            for p in parts
        ]
    }


def _handle_get_shortages_for_work_order(
    db: Session, user: CurrentUser, args: dict[str, Any]
) -> dict[str, Any]:
    work_order_id = _uuid(args["work_order_id"], "work_order_id")
    requirements = part_requirement_service.list_part_requirements_for_work_order(
        db, organization_id=user.organization_id, work_order_id=work_order_id
    )
    return {
        "requirements": [
            {
                "id": str(r.id),
                "part_id": str(r.part_id),
                "required_quantity": r.required_quantity,
                "fulfilled_quantity": r.fulfilled_quantity,
                "status": r.status,
            }
            for r in requirements
        ]
    }


def _handle_get_inventory_transactions(
    db: Session, user: CurrentUser, args: dict[str, Any]
) -> dict[str, Any]:
    part_id = _uuid(args["part_id"], "part_id")
    transactions = inventory_transaction_service.list_transactions_for_part(
        db, organization_id=user.organization_id, part_id=part_id
    )
    return {
        "transactions": [
            {
                "id": str(t.id),
                "transaction_type": t.transaction_type,
                "on_hand_delta": t.on_hand_delta,
                "reserved_delta": t.reserved_delta,
            }
            for t in transactions
        ]
    }


def _handle_get_vendors(db: Session, user: CurrentUser, args: dict[str, Any]) -> dict[str, Any]:
    vendors = vendor_service.list_vendors(db, organization_id=user.organization_id)
    return {
        "vendors": [
            {
                "id": str(v.id),
                "name": v.name,
                "approved": v.approved,
                "reliability_score": v.reliability_score,
            }
            for v in vendors
        ]
    }


def _handle_get_vendor_fit(db: Session, user: CurrentUser, args: dict[str, Any]) -> dict[str, Any]:
    part_id = _uuid(args["part_id"], "part_id")
    results = vendor_fit_service.score_vendor_options_for_part(
        db, organization_id=user.organization_id, part_id=part_id
    )
    return {
        "results": [
            {
                "vendor_id": str(r.vendor_id),
                "vendor_name": r.vendor_name,
                "score": r.score,
                "confidence": r.confidence,
                "factors": r.factors,
                "missing_factors": r.missing_factors,
            }
            for r in results
        ]
    }


def _handle_get_procurement_requests(
    db: Session, user: CurrentUser, args: dict[str, Any]
) -> dict[str, Any]:
    status = args.get("status")
    requests = procurement_service.list_requests(
        db, organization_id=user.organization_id, status=status
    )
    return {
        "requests": [
            {
                "id": str(r.id),
                "aircraft_id": str(r.aircraft_id),
                "part_number": r.part_number,
                "quantity": r.quantity,
                "priority": r.priority,
                "status": r.status,
            }
            for r in requests
        ]
    }


def _handle_get_purchase_orders(
    db: Session, user: CurrentUser, args: dict[str, Any]
) -> dict[str, Any]:
    status = args.get("status")
    purchase_orders = purchase_order_service.list_purchase_orders(
        db, organization_id=user.organization_id, status=status
    )
    return {
        "purchase_orders": [
            {
                "id": str(po.id),
                "po_number": po.po_number,
                "vendor_id": str(po.vendor_id),
                "status": po.status,
                "total_cents": po.total_cents,
                "lines": [
                    {
                        "id": str(line.id),
                        "procurement_request_id": (
                            str(line.procurement_request_id)
                            if line.procurement_request_id
                            else None
                        ),
                        "part_number": line.part_number,
                        "quantity": line.quantity,
                        "received_quantity": line.received_quantity,
                    }
                    for line in po.lines
                ],
            }
            for po in purchase_orders
        ]
    }


def _handle_get_aog_events(db: Session, user: CurrentUser, args: dict[str, Any]) -> dict[str, Any]:
    aircraft_id = args.get("aircraft_id")
    status = args.get("status")
    events = aog_service.list_aog_events(
        db,
        organization_id=user.organization_id,
        status=status,
        aircraft_id=_uuid(aircraft_id, "aircraft_id") if aircraft_id else None,
    )
    return {
        "events": [
            {
                "id": str(e.id),
                "aircraft_id": str(e.aircraft_id),
                "status": e.status,
                "severity": e.severity,
                "root_cause": e.root_cause,
                "blockers": [
                    {
                        "blocker_type": b.blocker_type,
                        "description": b.description,
                        "resolved": b.resolved,
                    }
                    for b in e.blockers
                ],
            }
            for e in events
        ]
    }


def _handle_get_aog_recovery_status(
    db: Session, user: CurrentUser, args: dict[str, Any]
) -> dict[str, Any]:
    status = aog_recovery_service.get_recovery_status(
        db,
        organization_id=user.organization_id,
        aircraft_id=_uuid(args["aircraft_id"], "aircraft_id"),
    )
    return {
        "aircraft_id": status.aircraft_id,
        "registration": status.registration,
        "is_aog": status.is_aog,
        "aog_event_id": status.aog_event_id,
        "aog_status": status.aog_status,
        "severity": status.severity,
        "work_order_id": status.work_order_id,
        "release_readiness_status": status.release_readiness_status,
        "tat_status": status.tat_status,
        "tat_reason": status.tat_reason,
        "blockers": [
            {
                "category": b.category,
                "description": b.description,
                "record_type": b.record_type,
                "record_id": b.record_id,
                "who_should_act": b.who_should_act,
                "dependency": b.dependency,
            }
            for b in status.blockers
        ],
        "next_best_action": (
            {
                "category": status.next_best_action.category,
                "description": status.next_best_action.description,
                "who_should_act": status.next_best_action.who_should_act,
                "dependency": status.next_best_action.dependency,
                "record_type": status.next_best_action.record_type,
                "record_id": status.next_best_action.record_id,
            }
            if status.next_best_action
            else None
        ),
        "critical_path": [
            {
                "stage": s.stage,
                "status": s.status,
                "reason": s.reason,
                "record_type": s.record_type,
                "record_id": s.record_id,
                "next_action": s.next_action,
            }
            for s in status.critical_path
        ],
        "technician_authorization": status.technician_authorization,
        "eta": status.eta,
        "compliance_status": status.compliance_status,
        "data_completeness": status.data_completeness,
    }


def _handle_check_technician_authorization(
    db: Session, user: CurrentUser, args: dict[str, Any]
) -> dict[str, Any]:
    result = technician_service.check_authorization(
        db,
        organization_id=user.organization_id,
        task_id=_uuid(args["task_id"], "task_id"),
        technician_user_id=_uuid(args["technician_user_id"], "technician_user_id"),
    )
    return {
        "status": result.status,
        "reason": result.reason,
        "task_id": str(result.task_id),
        "technician_user_id": str(result.technician_user_id),
        "aircraft_type": result.aircraft_type,
        "qualification_id": str(result.qualification_id) if result.qualification_id else None,
    }


def _handle_get_maintenance_due(
    db: Session, user: CurrentUser, args: dict[str, Any]
) -> dict[str, Any]:
    aircraft_id = _uuid(args["aircraft_id"], "aircraft_id")
    due_items = maintenance_service.get_maintenance_due_for_aircraft(
        db, organization_id=user.organization_id, aircraft_id=aircraft_id
    )
    return {
        "due_items": [
            {
                "requirement_description": item.requirement.description,
                "due_status": item.due_status,
                "due_date": item.due_date.isoformat() if item.due_date else None,
                "reason": item.reason,
            }
            for item in due_items
        ]
    }


def _handle_get_deferred_items(
    db: Session, user: CurrentUser, args: dict[str, Any]
) -> dict[str, Any]:
    aircraft_id = _uuid(args["aircraft_id"], "aircraft_id")
    open_only = bool(args.get("open_only", True))
    items = deferred_item_service.list_deferred_items_for_aircraft(
        db, organization_id=user.organization_id, aircraft_id=aircraft_id, open_only=open_only
    )
    return {
        "deferred_items": [
            {
                "id": str(i.id),
                "description": i.description,
                "category": i.category,
                "status": i.status,
                "due_at": i.due_at.isoformat() if i.due_at else None,
                "approval_status": i.approval_status,
            }
            for i in items
        ]
    }


def _handle_get_compliance_assessments(
    db: Session, user: CurrentUser, args: dict[str, Any]
) -> dict[str, Any]:
    aircraft_id = _uuid(args["aircraft_id"], "aircraft_id")
    assessments = compliance_service.list_assessments_for_aircraft(
        db, organization_id=user.organization_id, aircraft_id=aircraft_id
    )
    return {
        "assessments": [
            {
                "id": str(a.id),
                "requirement_id": str(a.requirement_id),
                "status": a.status,
                "evaluated_at": a.evaluated_at.isoformat(),
            }
            for a in assessments
        ]
    }


def _handle_get_regulatory_documents(
    db: Session, user: CurrentUser, args: dict[str, Any]
) -> dict[str, Any]:
    authority = args.get("authority")
    documents = regulatory_service.list_documents(
        db, organization_id=user.organization_id, authority=authority
    )
    return {
        "documents": [
            {
                "id": str(d.id),
                "authority": d.authority,
                "doc_number": d.doc_number,
                "title": d.title,
                "sync_status": d.sync_status,
            }
            for d in documents
        ]
    }


def _handle_get_regulatory_provider_status(
    db: Session, user: CurrentUser, args: dict[str, Any]
) -> dict[str, Any]:
    statuses = regulatory_service.get_provider_status()
    return {"providers": [s.model_dump() for s in statuses]}


def _handle_get_control_center_summary(
    db: Session, user: CurrentUser, args: dict[str, Any]
) -> dict[str, Any]:
    summary = control_center_service.get_summary(db, organization_id=user.organization_id)
    return summary.model_dump()


def _handle_get_control_center_fleet(
    db: Session, user: CurrentUser, args: dict[str, Any]
) -> dict[str, Any]:
    rows = control_center_service.get_fleet_rows(db, organization_id=user.organization_id)
    return {"fleet": [r.model_dump(mode="json") for r in rows]}


def _handle_get_proactive_alerts(
    db: Session, user: CurrentUser, args: dict[str, Any]
) -> dict[str, Any]:
    alerts = proactive_service.get_proactive_alerts(db, organization_id=user.organization_id)
    return {"alerts": [a.model_dump(mode="json") for a in alerts]}


def _handle_get_daily_brief(db: Session, user: CurrentUser, args: dict[str, Any]) -> dict[str, Any]:
    brief = proactive_service.get_daily_brief(db, organization_id=user.organization_id)
    return brief.model_dump(mode="json")


def _handle_get_proactive_intelligence_summary(
    db: Session, user: CurrentUser, args: dict[str, Any]
) -> dict[str, Any]:
    summary = proactive_intelligence_service.get_proactive_summary(
        db, organization_id=user.organization_id
    )
    return summary.model_dump(mode="json")


def _handle_get_asset_proactive_signals(
    db: Session, user: CurrentUser, args: dict[str, Any]
) -> dict[str, Any]:
    raw_id = _uuid(args["asset_id"], "asset_id")
    # Resolve to asset_id if raw_id is an Aircraft primary key
    aircraft = db.execute(
        select(Aircraft).where(
            Aircraft.organization_id == user.organization_id,
            Aircraft.id == raw_id,
        )
    ).scalar_one_or_none()
    resolved_asset_id = aircraft.asset_id if (aircraft and aircraft.asset_id) else raw_id

    signals = proactive_intelligence_service.sync_and_get_signals(
        db, organization_id=user.organization_id, asset_id=resolved_asset_id
    )
    return {"signals": [s.model_dump(mode="json") for s in signals]}


def _handle_get_asset_hums_health(
    db: Session, user: CurrentUser, args: dict[str, Any]
) -> dict[str, Any]:
    from app.services import hums_service

    asset_id = _uuid(args["asset_id"], "asset_id")
    summary = hums_service.get_asset_health(db, organization_id=user.organization_id, asset_id=asset_id)
    return summary.model_dump(mode="json")


def _handle_get_asset_hums_features(
    db: Session, user: CurrentUser, args: dict[str, Any]
) -> dict[str, Any]:
    from app.services import hums_service

    asset_id = _uuid(args["asset_id"], "asset_id")
    feature_type = args.get("feature_type")
    rows = hums_service.list_features(
        db, organization_id=user.organization_id, asset_id=asset_id, feature_type=feature_type, limit=50
    )
    return {
        "features": [
            {
                "sensor_id": str(r.sensor_id),
                "feature_type": r.feature_type,
                "value": r.value,
                "unit": r.unit,
                "quality": r.quality,
                "window_end": r.window_end.isoformat(),
                "sample_count": r.sample_count,
            }
            for r in rows
        ]
    }


def _handle_get_asset_hums_health_intelligence(
    db: Session, user: CurrentUser, args: dict[str, Any]
) -> dict[str, Any]:
    from app.services import hums_service

    asset_id = _uuid(args["asset_id"], "asset_id")
    result = hums_service.get_asset_health_intelligence(db, organization_id=user.organization_id, asset_id=asset_id)
    db.commit()
    return result.model_dump(mode="json")


def _handle_get_asset_telemetry_status(
    db: Session, user: CurrentUser, args: dict[str, Any]
) -> dict[str, Any]:
    from app.services import telemetry_service

    asset_id = _uuid(args["asset_id"], "asset_id")
    return telemetry_service.get_asset_telemetry_status(
        db, organization_id=user.organization_id, asset_id=asset_id
    )


def _handle_get_asset_hums_diagnostics(
    db: Session, user: CurrentUser, args: dict[str, Any]
) -> dict[str, Any]:
    from app.services import hums_service

    asset_id = _uuid(args["asset_id"], "asset_id")
    rows = hums_service.list_asset_diagnostics(db, organization_id=user.organization_id, asset_id=asset_id)
    return {
        "diagnostics": [
            {
                "id": str(r.id),
                "fault_code": r.fault_code,
                "fault_name": r.fault_name,
                "fault_domain": r.fault_domain,
                "status": r.status,
                "severity": r.severity,
                "confidence": r.confidence,
                "score": r.score,
                "component_id": str(r.component_id) if r.component_id else None,
                "explanation": r.explanation,
                "primary_evidence": r.primary_evidence,
                "supporting_evidence": r.supporting_evidence,
                "contradicting_evidence": r.contradicting_evidence,
                "rule_version": r.rule_version,
                "detected_at": r.detected_at.isoformat(),
            }
            for r in rows
        ]
    }


def _handle_get_asset_hums_prognostics(
    db: Session, user: CurrentUser, args: dict[str, Any]
) -> dict[str, Any]:
    from app.services import hums_service

    asset_id = _uuid(args["asset_id"], "asset_id")
    rows = hums_service.list_asset_prognostics(db, organization_id=user.organization_id, asset_id=asset_id)
    return {
        "prognostics": [
            {
                "id": str(r.id),
                "sensor_id": str(r.sensor_id),
                "component_id": str(r.component_id) if r.component_id else None,
                "feature_type": r.feature_type,
                "status": r.status,
                "current_value": r.current_value,
                "threshold_value": r.threshold_value,
                "threshold_type": r.threshold_type,
                "rul_estimate": r.rul_estimate,
                "rul_lower": r.rul_lower,
                "rul_upper": r.rul_upper,
                "rul_unit": r.rul_unit,
                "confidence": r.confidence,
                "quality": r.quality,
                "extrapolation_distance": r.extrapolation_distance,
                "related_diagnostic_candidate_id": str(r.diagnostic_candidate_id) if r.diagnostic_candidate_id else None,
                "explanation": r.explanation,
                "calculated_at": r.calculated_at.isoformat(),
                "note": "ESTIMATE — NOT A CERTIFIED LIFE LIMIT",
            }
            for r in rows
        ]
    }


def _handle_get_digital_twin(db: Session, user: CurrentUser, args: dict[str, Any]) -> dict[str, Any]:
    from app.services import digital_twin_service

    asset_id = _uuid(args["asset_id"], "asset_id")
    snapshot = digital_twin_service.get_asset_snapshot(db, organization_id=user.organization_id, asset_id=asset_id)
    return snapshot.model_dump(mode="json")


def _handle_get_component_genealogy(db: Session, user: CurrentUser, args: dict[str, Any]) -> dict[str, Any]:
    from app.services import digital_twin_service

    component_id = _uuid(args["component_id"], "component_id")
    entries = digital_twin_service.get_component_genealogy(db, organization_id=user.organization_id, component_id=component_id)
    return {"genealogy": [e.model_dump(mode="json") for e in entries]}


def _handle_get_asset_twin_timeline(db: Session, user: CurrentUser, args: dict[str, Any]) -> dict[str, Any]:
    from app.services import digital_twin_service

    asset_id = _uuid(args["asset_id"], "asset_id")
    events = digital_twin_service.get_asset_timeline(db, organization_id=user.organization_id, asset_id=asset_id)
    return {"timeline": [e.model_dump(mode="json") for e in events]}


def _handle_trace_lineage(db: Session, user: CurrentUser, args: dict[str, Any]) -> dict[str, Any]:
    from app.services import knowledge_graph

    graph = knowledge_graph.get_subgraph(
        db, organization_id=user.organization_id, node_type=str(args["node_type"]),
        node_id=_uuid(args["node_id"], "node_id"), depth=int(args.get("depth", 2)),
    )
    return knowledge_graph.to_dict(graph)


# --- H7: MRO + Compliance + Readiness Intelligence Integration -------------
# Every handler below simply wraps an existing mro_intelligence_service
# function -- none recomputes or reimplements business logic. Each returns
# facts + source refs + confidence/freshness + explicit limitations, never
# inventing missing evidence (missing data renders as UNKNOWN/DATA_UNAVAILABLE
# fields already present on the underlying schema, never silently omitted).

def _handle_get_asset_mro_intelligence(db: Session, user: CurrentUser, args: dict[str, Any]) -> dict[str, Any]:
    asset_id = _uuid(args["asset_id"], "asset_id")
    result = mro_intelligence_service.get_asset_mro_intelligence(db, organization_id=user.organization_id, asset_id=asset_id)
    db.commit()
    return result.model_dump(mode="json")


def _handle_get_asset_maintenance_candidates(db: Session, user: CurrentUser, args: dict[str, Any]) -> dict[str, Any]:
    asset_id = _uuid(args["asset_id"], "asset_id")
    mro_intelligence_service.generate_maintenance_candidates(db, organization_id=user.organization_id, asset_id=asset_id)
    candidates = mro_intelligence_service.list_asset_candidates(db, organization_id=user.organization_id, asset_id=asset_id)
    db.commit()
    from app.schemas.mro_intelligence import MaintenanceCandidateOut

    return {"candidates": [MaintenanceCandidateOut.model_validate(c).model_dump(mode="json") for c in candidates]}


def _handle_get_asset_compliance_impact(db: Session, user: CurrentUser, args: dict[str, Any]) -> dict[str, Any]:
    asset_id = _uuid(args["asset_id"], "asset_id")
    result = mro_intelligence_service.get_compliance_impact(db, organization_id=user.organization_id, asset_id=asset_id)
    return result.model_dump(mode="json")


def _handle_get_asset_readiness_impact(db: Session, user: CurrentUser, args: dict[str, Any]) -> dict[str, Any]:
    asset_id = _uuid(args["asset_id"], "asset_id")
    result = mro_intelligence_service.get_readiness_impact(db, organization_id=user.organization_id, asset_id=asset_id)
    db.commit()
    return result.model_dump(mode="json")


def _handle_get_asset_operational_impact(db: Session, user: CurrentUser, args: dict[str, Any]) -> dict[str, Any]:
    asset_id = _uuid(args["asset_id"], "asset_id")
    result = mro_intelligence_service.get_operational_impact(db, organization_id=user.organization_id, asset_id=asset_id)
    db.commit()
    return result.model_dump(mode="json")


def _handle_get_asset_integration_conflicts(db: Session, user: CurrentUser, args: dict[str, Any]) -> dict[str, Any]:
    asset_id = _uuid(args["asset_id"], "asset_id")
    conflicts = mro_intelligence_service.detect_conflicts(db, organization_id=user.organization_id, asset_id=asset_id)
    return {"conflicts": [c.model_dump(mode="json") for c in conflicts]}



_FLEET_FAMILY_FEATURE = {
    "AIRCRAFT": "aircraft_fleet_management",
    "DRONE": "drone_fleet_management",
    "HELICOPTER": "helicopter_fleet_management",
    "EVTOL": "evtol_fleet_management",
    "AAM": "evtol_fleet_management",
}


def _handle_list_fleet_assets(db: Session, user: CurrentUser, args: dict[str, Any]) -> dict[str, Any]:
    """Assets of the airframe families the organization is ENTITLED to (a drone tenant never sees helicopters
    listed through LISA, even in a multi-suite account that lacks the helicopter feature)."""
    from app.services import asset_service

    result = resolve_entitlements(db, organization_id=user.organization_id)
    entitled = {
        t for t, f in _FLEET_FAMILY_FEATURE.items()
        if result.effective_features.get(f) is True or result.effective_features.get(canonicalize_feature_key(f)) is True
    }
    wanted = str(args.get("asset_type") or "").strip().upper() or None
    if wanted and wanted not in _FLEET_FAMILY_FEATURE:
        raise AeroComplyError(f"asset_type must be one of {sorted(_FLEET_FAMILY_FEATURE)}", code="invalid_argument")
    if wanted and wanted not in entitled:
        raise ForbiddenError(f"Organization is not entitled to {wanted} assets", code="SUITE_ENTITLEMENT_REQUIRED")
    rows = asset_service.list_assets(db, organization_id=user.organization_id, asset_type=wanted)
    return {"assets": [
        {"id": str(a.id), "asset_type": a.asset_type, "registration": a.registration, "manufacturer": a.manufacturer,
         "model": a.model, "status": a.status}
        for a in rows if a.asset_type in entitled][:200]}


def _signal_record_to_dict(r: Any) -> dict[str, Any]:
    if isinstance(r, dict):
        return r
    return {
        "id": str(r.id),
        "organization_id": str(r.organization_id),
        "signal_key": r.signal_key,
        "signal_type": r.signal_type.value if hasattr(r.signal_type, "value") else str(r.signal_type),
        "severity": r.severity.value if hasattr(r.severity, "value") else str(r.severity),
        "priority": r.priority.value if hasattr(r.priority, "value") else str(r.priority),
        "status": r.status.value if hasattr(r.status, "value") else str(r.status),
        "title": r.title,
        "headline": r.headline,
        "explanation": r.explanation_json or [],
        "asset_id": str(r.asset_id) if r.asset_id else None,
        "detected_at": r.detected_at.isoformat() if r.detected_at else None,
        "evidence": r.evidence_json or [],
        "contributing_factors": r.contributing_factors_json or {},
        "recommended_actions": r.recommended_actions_json or [],
    }


def _handle_get_alert_details(db: Session, user: CurrentUser, args: dict[str, Any]) -> dict[str, Any]:
    alert_id = str(args.get("alert_id", "")).strip()
    if not alert_id:
        raise AeroComplyError("alert_id is required", code="invalid_argument")

    from app.models.proactive_signal import ProactiveSignalRecord
    from app.services import asset_service

    # Check proactive signals
    as_uuid = _try_uuid(alert_id)
    signal = None
    if as_uuid is not None:
        signal = db.execute(
            select(ProactiveSignalRecord).where(
                ProactiveSignalRecord.organization_id == user.organization_id,
                ProactiveSignalRecord.id == as_uuid,
            )
        ).scalar_one_or_none()
    if signal is None:
        signal = db.execute(
            select(ProactiveSignalRecord).where(
                ProactiveSignalRecord.organization_id == user.organization_id,
                ProactiveSignalRecord.signal_key == alert_id,
            )
        ).scalar_one_or_none()

    if signal is not None:
        return _signal_record_to_dict(signal)


    # Check proactive service alerts
    alerts = proactive_service.get_proactive_alerts(db, organization_id=user.organization_id)
    matched = next((a for a in alerts if a.id == alert_id or str(a.source_id) == alert_id), None)
    if matched is not None:
        return matched.model_dump(mode="json")

    raise NotFoundError(f"Alert with identifier '{alert_id}' not found in organization")


def _handle_get_mission_details(db: Session, user: CurrentUser, args: dict[str, Any]) -> dict[str, Any]:
    mission_id = _uuid(args["mission_id"], "mission_id")
    from app.services import mission_service, asset_service

    mission = mission_service.get_mission(db, organization_id=user.organization_id, mission_id=mission_id)
    pilot_names = mission_service.resolve_pilot_names(db, organization_id=user.organization_id, missions=[mission])
    pilot_name = pilot_names.get(mission.pilot_user_id) if mission.pilot_user_id else None

    asset_reg = None
    try:
        asset = asset_service.get_asset(db, organization_id=user.organization_id, asset_id=mission.asset_id)
        asset_reg = asset.registration or asset.serial_number or str(asset.id)
    except Exception:
        pass

    return {
        "id": str(mission.id),
        "asset_id": str(mission.asset_id),
        "asset_registration": asset_reg,
        "status": mission.status.value if hasattr(mission.status, "value") else str(mission.status),
        "purpose": mission.purpose,
        "operating_area": mission.operating_area,
        "planned_start": mission.planned_start.isoformat() if mission.planned_start else None,
        "planned_end": mission.planned_end.isoformat() if mission.planned_end else None,
        "pilot_user_id": str(mission.pilot_user_id) if mission.pilot_user_id else None,
        "pilot_name": pilot_name,
        "authorized_at": mission.authorized_at.isoformat() if mission.authorized_at else None,
        "notes": mission.notes,
        "created_at": mission.created_at.isoformat() if mission.created_at else None,
        "execution_state": "PLANNED_OR_AUTHORIZED (flight not automatically executed without verified telemetry)",
    }


def _handle_get_fleet_correlations(db: Session, user: CurrentUser, args: dict[str, Any]) -> dict[str, Any]:
    """H8.5: Retrieve H8.3 cross-asset HUMS and fleet anomaly pattern correlation results.
    Strictly read-only, tenant-isolated by user.organization_id.
    """
    days = int(args.get("days", 30))
    if days < 1 or days > 365:
        days = 30
    asset_id_raw = args.get("asset_id")
    asset_id = _try_uuid(asset_id_raw) if asset_id_raw else None
    feature_family = str(args.get("feature_family") or "").strip() or None
    pattern_type = str(args.get("pattern_type") or "").strip() or None
    confidence = str(args.get("confidence") or "").strip().upper() or None

    context = cross_asset_intelligence_service.get_fleet_correlation_context(
        db, organization_id=user.organization_id, lookback_days=days
    )
    correlations = context.anomaly_correlations
    if asset_id:
        correlations = [c for c in correlations if asset_id in c.participating_asset_ids]
    if feature_family:
        ff = feature_family.lower()
        correlations = [
            c for c in correlations
            if ff in c.feature_family.lower() or c.feature_family.lower() in ff
        ]
    if pattern_type:
        correlations = [c for c in correlations if c.pattern_type == pattern_type]
    if confidence:
        correlations = [c for c in correlations if c.confidence == confidence]

    return {
        "availability": context.availability.value if hasattr(context.availability, "value") else str(context.availability),
        "total_fleet_assets": context.total_fleet_assets,
        "affected_asset_count": context.affected_asset_count,
        "correlation_count": len(correlations),
        "correlations": [c.model_dump(mode="json") for c in correlations],
        "explanation": context.explanation,
        "lookback_days": days,
    }


def _handle_get_fleet_correlation_detail(db: Session, user: CurrentUser, args: dict[str, Any]) -> dict[str, Any]:
    """H8.5: Retrieve detailed evidence and provenance for a single cross-asset correlation record."""
    corr_id_str = str(args.get("correlation_id", "")).strip()
    corr_id = _uuid(corr_id_str, "correlation_id")
    days = int(args.get("days", 30))
    if days < 1 or days > 365:
        days = 30

    context = cross_asset_intelligence_service.get_fleet_correlation_context(
        db, organization_id=user.organization_id, lookback_days=days
    )
    for c in context.anomaly_correlations:
        if c.id == corr_id:
            return c.model_dump(mode="json")

    raise NotFoundError(f"Fleet correlation '{corr_id}' not found in organization")


def _handle_get_fleet_signals(db: Session, user: CurrentUser, args: dict[str, Any]) -> dict[str, Any]:
    """H8.5: Retrieve canonical M7 proactive signals for the organization.
    Read-only, tenant-isolated by user.organization_id.
    """
    from app.models.proactive_signal import ProactiveSignalRecord

    stmt = select(ProactiveSignalRecord).where(
        ProactiveSignalRecord.organization_id == user.organization_id
    )
    asset_id_raw = args.get("asset_id")
    if asset_id_raw:
        stmt = stmt.where(ProactiveSignalRecord.asset_id == _uuid(asset_id_raw, "asset_id"))
    category = args.get("signal_category") or args.get("signal_type")
    if category:
        stmt = stmt.where(ProactiveSignalRecord.signal_type == str(category).strip())
    severity = args.get("severity")
    if severity:
        stmt = stmt.where(ProactiveSignalRecord.severity == str(severity).strip().upper())
    status = args.get("status")
    if status:
        stmt = stmt.where(ProactiveSignalRecord.status == str(status).strip().upper())

    stmt = stmt.order_by(ProactiveSignalRecord.detected_at.desc()).limit(50)
    rows = db.execute(stmt).scalars().all()
    return {
        "signals": [
            _signal_record_to_dict(r)
            for r in rows
        ]
    }


def _handle_get_fleet_correlation_summary(db: Session, user: CurrentUser, args: dict[str, Any]) -> dict[str, Any]:
    """H8.5: Combined bounded view of cross-asset correlations, related M7 signals, and evidence."""
    from app.models.proactive_signal import ProactiveSignalRecord

    days = int(args.get("days", 30))
    if days < 1 or days > 365:
        days = 30

    context = cross_asset_intelligence_service.get_fleet_correlation_context(
        db, organization_id=user.organization_id, lookback_days=days
    )
    correlations = context.anomaly_correlations

    all_sig_ids: set[uuid.UUID] = set()
    for c in correlations:
        for sid in c.supporting_signal_ids:
            all_sig_ids.add(sid)

    related_signals: list[dict[str, Any]] = []
    if all_sig_ids:
        rows = db.execute(
            select(ProactiveSignalRecord).where(
                ProactiveSignalRecord.organization_id == user.organization_id,
                ProactiveSignalRecord.id.in_(all_sig_ids),
            )
        ).scalars().all()
        related_signals = [_signal_record_to_dict(r) for r in rows]


    return {
        "availability": context.availability.value if hasattr(context.availability, "value") else str(context.availability),
        "total_fleet_assets": context.total_fleet_assets,
        "affected_asset_count": context.affected_asset_count,
        "correlation_count": len(correlations),
        "correlations": [c.model_dump(mode="json") for c in correlations],
        "related_signals": related_signals,
        "lookback_days": days,
        "disclaimer": (
            "Statistical correlation across fleet observations does not imply shared physical origin or causality. "
            "Engineering review is required."
        ),
    }


TOOL_REGISTRY: list[ToolSpec] = [
    ToolSpec(
        name="get_aircraft",
        description="Get one aircraft by id: registration, MSN, type, status.",
        input_schema={
            "type": "object",
            "properties": {"aircraft_id": {"type": "string", "description": "Aircraft UUID"}},
            "required": ["aircraft_id"],
        },
        handler=_handle_get_aircraft,
    
    required_permission=Permission.AIRCRAFT_READ,
        required_feature="aircraft_fleet_management",
        required_suite="AIRCRAFT,HELICOPTER,EVTOL_AAM",
    ),
    ToolSpec(
        name="list_aircraft",
        description="List all aircraft in the caller's organization.",
        input_schema={"type": "object", "properties": {}},
        handler=_handle_list_aircraft,
    
    required_permission=Permission.AIRCRAFT_READ,
        required_feature="aircraft_fleet_management",
        required_suite="AIRCRAFT,HELICOPTER,EVTOL_AAM",
    ),
    ToolSpec(
        name="get_work_order",
        description="Get one work order by id: aircraft, number, status, priority.",
        input_schema={
            "type": "object",
            "properties": {"work_order_id": {"type": "string", "description": "Work order UUID"}},
            "required": ["work_order_id"],
        },
        handler=_handle_get_work_order,
    
    required_permission=Permission.AIRCRAFT_READ,
        required_feature="work_order_management",
    ),
    ToolSpec(
        name="get_work_order_tasks",
        description="List the tasks belonging to a work order.",
        input_schema={
            "type": "object",
            "properties": {"work_order_id": {"type": "string", "description": "Work order UUID"}},
            "required": ["work_order_id"],
        },
        handler=_handle_get_work_order_tasks,

    required_permission=Permission.AIRCRAFT_READ,
        required_feature="work_order_management",
    ),
    ToolSpec(
        name="get_task",
        description=(
            "Get one task by id: work order, execution_state, description, assigned technician."
        ),
        input_schema={
            "type": "object",
            "properties": {"task_id": {"type": "string", "description": "Task UUID"}},
            "required": ["task_id"],
        },
        handler=_handle_get_task,

    required_permission=Permission.AIRCRAFT_READ,
        required_feature="work_order_management",
    ),
    ToolSpec(
        name="get_evidence",
        description="Get one evidence record by id: task, status, uploader.",
        input_schema={
            "type": "object",
            "properties": {"evidence_id": {"type": "string", "description": "Evidence UUID"}},
            "required": ["evidence_id"],
        },
        handler=_handle_get_evidence,
    
    required_permission=Permission.EVIDENCE_READ,
        required_feature="work_order_management",
    ),
    ToolSpec(
        name="list_evidence_for_task",
        description="List all evidence records for a task.",
        input_schema={
            "type": "object",
            "properties": {"task_id": {"type": "string", "description": "Task UUID"}},
            "required": ["task_id"],
        },
        handler=_handle_list_evidence_for_task,
    
    required_permission=Permission.EVIDENCE_READ,
        required_feature="work_order_management",
    ),
    ToolSpec(
        name="get_inspection",
        description="Get one inspection requirement by id: task, work order, required, status.",
        input_schema={
            "type": "object",
            "properties": {
                "inspection_id": {"type": "string", "description": "Inspection requirement UUID"}
            },
            "required": ["inspection_id"],
        },
        handler=_handle_get_inspection,
    
    required_permission=Permission.INSPECTION_READ,
        required_feature="inspections_management",
    ),
    ToolSpec(
        name="list_inspections_for_work_order",
        description="List the inspection requirements (including RII) attached to a work order.",
        input_schema={
            "type": "object",
            "properties": {"work_order_id": {"type": "string", "description": "Work order UUID"}},
            "required": ["work_order_id"],
        },
        handler=_handle_list_inspections_for_work_order,
    
    required_permission=Permission.INSPECTION_READ,
        required_feature="inspections_management",
    ),
    ToolSpec(
        name="get_tat",
        description=(
            "Get TAT (turnaround time) status for one work order: ON_TRACK/AT_RISK/DELAYED/UNKNOWN "
            "with reason."
        ),
        input_schema={
            "type": "object",
            "properties": {"work_order_id": {"type": "string", "description": "Work order UUID"}},
            "required": ["work_order_id"],
        },
        handler=_handle_get_tat,
    
    required_permission=Permission.AIRCRAFT_READ,
        required_feature="work_order_management",
    ),
    ToolSpec(
        name="get_fleet_tat",
        description="Get TAT status counts across the whole fleet's work orders.",
        input_schema={"type": "object", "properties": {}},
        handler=_handle_get_fleet_tat,
    
    required_permission=Permission.AIRCRAFT_READ,
        required_feature="work_order_management",
    ),
    ToolSpec(
        name="get_release_readiness",
        description=(
            "Get the deterministic release-readiness gate result (READY/BLOCKED) for a work order, "
            "with the exact blockers found."
        ),
        input_schema={
            "type": "object",
            "properties": {"work_order_id": {"type": "string", "description": "Work order UUID"}},
            "required": ["work_order_id"],
        },
        handler=_handle_get_release_readiness,
    
    required_permission=Permission.AIRCRAFT_READ,
        required_feature="release_readiness",
    ),
    ToolSpec(
        name="get_parts",
        description="List all parts in inventory with on-hand/reserved/available quantities.",
        input_schema={"type": "object", "properties": {}},
        handler=_handle_get_parts,
    
    required_permission=Permission.PART_READ,
        required_feature="procurement_management",
    ),
    ToolSpec(
        name="get_shortages_for_work_order",
        description="List part requirements (and shortage status) for a work order.",
        input_schema={
            "type": "object",
            "properties": {"work_order_id": {"type": "string", "description": "Work order UUID"}},
            "required": ["work_order_id"],
        },
        handler=_handle_get_shortages_for_work_order,
    
    required_permission=Permission.PART_READ,
        required_feature="procurement_management",
    ),
    ToolSpec(
        name="get_inventory_transactions",
        description=(
            "List inventory movement history (receive/reserve/release/consume/adjust) for a part."
        ),
        input_schema={
            "type": "object",
            "properties": {"part_id": {"type": "string", "description": "Part UUID"}},
            "required": ["part_id"],
        },
        handler=_handle_get_inventory_transactions,
    
    required_permission=Permission.PART_READ,
        required_feature="procurement_management",
    ),
    ToolSpec(
        name="get_vendors",
        description="List all vendors with approval status and reliability score.",
        input_schema={"type": "object", "properties": {}},
        handler=_handle_get_vendors,
    
    required_permission=Permission.VENDOR_READ,
        required_feature="procurement_management",
    ),
    ToolSpec(
        name="get_vendor_fit",
        description=(
            "Get ranked, explainable vendor recommendations for a part (score, confidence, "
            "factors, missing_factors). A null score means insufficient data, never a "
            "fabricated ranking."
        ),
        input_schema={
            "type": "object",
            "properties": {"part_id": {"type": "string", "description": "Part UUID"}},
            "required": ["part_id"],
        },
        handler=_handle_get_vendor_fit,
    
    required_permission=Permission.VENDOR_READ,
        required_feature="procurement_management",
    ),
    ToolSpec(
        name="get_procurement_requests",
        description=(
            "List procurement (part) requests, optionally filtered by status "
            "(SUBMITTED/UNDER_REVIEW/APPROVED/REJECTED/CLARIFICATION_REQUIRED/ORDERED/RECEIVED/CLOSED)."
        ),
        input_schema={
            "type": "object",
            "properties": {"status": {"type": "string", "description": "Optional status filter"}},
        },
        handler=_handle_get_procurement_requests,
    
    required_permission=Permission.PROCUREMENT_READ,
        required_feature="procurement_management",
    ),
    ToolSpec(
        name="get_purchase_orders",
        description=(
            "List purchase orders, optionally filtered by status "
            "(DRAFT/PENDING_APPROVAL/APPROVED/SENT/ACKNOWLEDGED/PARTIALLY_RECEIVED/RECEIVED/CANCELLED)."
        ),
        input_schema={
            "type": "object",
            "properties": {"status": {"type": "string", "description": "Optional status filter"}},
        },
        handler=_handle_get_purchase_orders,
    
    required_permission=Permission.PROCUREMENT_READ,
        required_feature="procurement_management",
    ),
    ToolSpec(
        name="get_aog_events",
        description=(
            "List AOG (Aircraft On Ground) events, optionally filtered by aircraft_id "
            "and/or status (DECLARED/IN_RECOVERY/RECOVERED/CANCELLED), including "
            "recorded blockers."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "aircraft_id": {"type": "string", "description": "Optional aircraft UUID filter"},
                "status": {"type": "string", "description": "Optional status filter"},
            },
        },
        handler=_handle_get_aog_events,

    required_permission=Permission.AIRCRAFT_READ,
        required_feature="aircraft_fleet_management",
        required_suite="AIRCRAFT,HELICOPTER,EVTOL_AAM",
    ),
    ToolSpec(
        name="get_aog_recovery_status",
        description=(
            "Get the synthesized recovery status for one aircraft: whether it is "
            "currently AOG, the active AOG event, release readiness, TAT, a structured "
            "critical_path (PART/PROCUREMENT/PURCHASE_ORDER/RECEIVING/EXECUTION/"
            "EVIDENCE/INSPECTION_RII/TECHNICIAN/RELEASE_READINESS stages, each with a "
            "real COMPLETE/BLOCKED/WAITING/UNKNOWN status), every real blocker, and a "
            "single next-best-action. Technician authorization is real when a task has "
            "an assigned technician; ETA and compliance sync remain UNKNOWN/"
            "NOT_EVALUATED because no backend record exists for them."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "aircraft_id": {"type": "string", "description": "Aircraft UUID"},
            },
            "required": ["aircraft_id"],
        },
        handler=_handle_get_aog_recovery_status,

    required_permission=Permission.AIRCRAFT_READ,
        required_feature="aircraft_fleet_management",
        required_suite="AIRCRAFT,HELICOPTER,EVTOL_AAM",
    ),
    ToolSpec(
        name="check_technician_authorization",
        description=(
            "Check whether a specific technician is authorized to perform a specific "
            "task, based on real TechnicianQualification records matched against the "
            "task's aircraft type. Returns AUTHORIZED / NOT_AUTHORIZED / EXPIRED / "
            "MISSING / UNKNOWN with a concrete reason — never inferred from the "
            "technician's application role."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "Task UUID"},
                "technician_user_id": {"type": "string", "description": "Technician user UUID"},
            },
            "required": ["task_id", "technician_user_id"],
        },
        handler=_handle_check_technician_authorization,

    required_permission=Permission.TECHNICIAN_READ,
        required_feature="work_order_management",
    ),
    ToolSpec(
        name="get_maintenance_due",
        description=(
            "Get maintenance-due status for an aircraft's applicable requirements "
            "(OVERDUE/DUE_SOON/NOT_DUE/UNKNOWN with reason)."
        ),
        input_schema={
            "type": "object",
            "properties": {"aircraft_id": {"type": "string", "description": "Aircraft UUID"}},
            "required": ["aircraft_id"],
        },
        handler=_handle_get_maintenance_due,
    
    required_permission=Permission.AIRCRAFT_READ,
        required_feature="aircraft_fleet_management",
        required_suite="AIRCRAFT,HELICOPTER,EVTOL_AAM",
    ),
    ToolSpec(
        name="get_deferred_items",
        description="List deferred items / MEL for an aircraft (open_only defaults to true).",
        input_schema={
            "type": "object",
            "properties": {
                "aircraft_id": {"type": "string", "description": "Aircraft UUID"},
                "open_only": {"type": "boolean", "description": "Defaults to true"},
            },
            "required": ["aircraft_id"],
        },
        handler=_handle_get_deferred_items,
    
    required_permission=Permission.AIRCRAFT_READ,
        required_feature="aircraft_fleet_management",
        required_suite="AIRCRAFT,HELICOPTER,EVTOL_AAM",
    ),
    ToolSpec(
        name="get_compliance_assessments",
        description="List compliance assessments for an aircraft against regulatory requirements.",
        input_schema={
            "type": "object",
            "properties": {"aircraft_id": {"type": "string", "description": "Aircraft UUID"}},
            "required": ["aircraft_id"],
        },
        handler=_handle_get_compliance_assessments,
    
    required_permission=Permission.COMPLIANCE_ASSESS,
        required_feature="compliance_management",
    ),
    ToolSpec(
        name="get_regulatory_documents",
        description=(
            "List regulatory documents (AD/SB/regulation/etc.), optionally filtered by authority "
            "(DGCA/FAA/EASA/CASA/UK_CAA)."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "authority": {"type": "string", "description": "Optional authority filter"}
            },
        },
        handler=_handle_get_regulatory_documents,
    
    required_permission=Permission.REGULATION_READ,
        required_feature="compliance_management",
    ),
    ToolSpec(
        name="get_regulatory_provider_status",
        description=(
            "Get the live-sync configuration status for every regulatory authority. Always returns "
            "NOT_CONFIGURED today — no live feed exists — never claim synchronization beyond what "
            "this returns."
        ),
        input_schema={"type": "object", "properties": {}},
        handler=_handle_get_regulatory_provider_status,
    
    required_permission=Permission.REGULATION_READ,
        required_feature="compliance_management",
    ),
    ToolSpec(
        name="get_control_center_summary",
        description=(
            "Get fleet-wide operational summary: aircraft counts by status "
            "(OPERATIONAL/UNDER_MAINTENANCE/AOG), open work orders, open deferred items, open part "
            "shortages."
        ),
        input_schema={"type": "object", "properties": {}},
        handler=_handle_get_control_center_summary,
    
    required_permission=Permission.AIRCRAFT_READ,
        required_feature="aircraft_fleet_management",
        required_suite="AIRCRAFT,HELICOPTER,EVTOL_AAM",
    ),
    ToolSpec(
        name="get_control_center_fleet",
        description=(
            "Get the per-aircraft operational control-center row for every aircraft (status, open "
            "work orders, open deferred items, open part shortages, active AOG event id)."
        ),
        input_schema={"type": "object", "properties": {}},
        handler=_handle_get_control_center_fleet,
        required_permission=Permission.AIRCRAFT_READ,
        required_feature="aircraft_fleet_management",
        required_suite="AIRCRAFT,HELICOPTER,EVTOL_AAM",
    ),
    ToolSpec(
        name="get_proactive_alerts",
        description=(
            "Get real, backend-derived operational alerts (AOG, part shortages, release "
            "blockers, overdue/due-soon deferred items, non-compliant assessments) — every "
            "alert traces to a real record, never fabricated."
        ),
        input_schema={"type": "object", "properties": {}},
        handler=_handle_get_proactive_alerts,
        required_permission=Permission.AIRCRAFT_READ,
        required_feature="aircraft_fleet_management",
        required_suite="AIRCRAFT,HELICOPTER,EVTOL_AAM",
    ),
    ToolSpec(
        name="get_daily_brief",
        description=(
            "Get the backend-authoritative daily brief: alert counts by severity and the top "
            "5 priorities, derived the same way as get_proactive_alerts."
        ),
        input_schema={"type": "object", "properties": {}},
        handler=_handle_get_daily_brief,
        required_permission=Permission.AIRCRAFT_READ,
        required_feature="aircraft_fleet_management",
        required_suite="AIRCRAFT,HELICOPTER,EVTOL_AAM",
    ),
    ToolSpec(
        name="get_assessments",
        description=(
            "List all MRO assessments for this organization (fleet/aircraft/work-order scoped)."
        ),
        input_schema={"type": "object", "properties": {}},
        handler=_handle_get_assessments,
        required_permission=Permission.ASSESSMENT_READ,
        required_feature="advanced_compliance_intelligence",
    ),
    ToolSpec(
        name="get_assessment",
        description=(
            "Get one assessment's metadata plus its latest snapshot summary "
            "(overall score, maturity band, finding counts)."
        ),
        input_schema={
            "type": "object",
            "properties": {"assessment_id": {"type": "string", "description": "Assessment UUID"}},
            "required": ["assessment_id"],
        },
        handler=_handle_get_assessment,
        required_permission=Permission.ASSESSMENT_READ,
        required_feature="advanced_compliance_intelligence",
    ),
    ToolSpec(
        name="run_assessment",
        description=(
            "Run (or re-run) a deterministic assessment against real operational data, "
            "producing a new versioned snapshot with findings, risks, gaps, "
            "recommendations, and roadmap items."
        ),
        input_schema={
            "type": "object",
            "properties": {"assessment_id": {"type": "string", "description": "Assessment UUID"}},
            "required": ["assessment_id"],
        },
        handler=_handle_run_assessment,
        required_permission=Permission.ASSESSMENT_WRITE,
        required_feature="advanced_compliance_intelligence",
    ),
    ToolSpec(
        name="get_assessment_findings",
        description="Get the findings from an assessment's latest snapshot, ranked by priority.",
        input_schema={
            "type": "object",
            "properties": {"assessment_id": {"type": "string", "description": "Assessment UUID"}},
            "required": ["assessment_id"],
        },
        handler=_handle_get_assessment_findings,
        required_permission=Permission.ASSESSMENT_READ,
        required_feature="advanced_compliance_intelligence",
    ),
    ToolSpec(
        name="get_assessment_risks",
        description=(
            "Get the risks from an assessment's latest snapshot. Likelihood is always "
            "UNKNOWN — this backend has no historical failure-rate data, and never "
            "fabricates a probability."
        ),
        input_schema={
            "type": "object",
            "properties": {"assessment_id": {"type": "string", "description": "Assessment UUID"}},
            "required": ["assessment_id"],
        },
        handler=_handle_get_assessment_risks,
        required_permission=Permission.ASSESSMENT_READ,
        required_feature="advanced_compliance_intelligence",
    ),
    ToolSpec(
        name="get_assessment_gaps",
        description=(
            "Get the gaps (expected vs. current condition) from an assessment's latest snapshot."
        ),
        input_schema={
            "type": "object",
            "properties": {"assessment_id": {"type": "string", "description": "Assessment UUID"}},
            "required": ["assessment_id"],
        },
        handler=_handle_get_assessment_gaps,
        required_permission=Permission.ASSESSMENT_READ,
        required_feature="advanced_compliance_intelligence",
    ),
    ToolSpec(
        name="get_assessment_recommendations",
        description="Get the recommendations from an assessment's latest snapshot.",
        input_schema={
            "type": "object",
            "properties": {"assessment_id": {"type": "string", "description": "Assessment UUID"}},
            "required": ["assessment_id"],
        },
        handler=_handle_get_assessment_recommendations,
        required_permission=Permission.ASSESSMENT_READ,
        required_feature="advanced_compliance_intelligence",
    ),
    ToolSpec(
        name="get_assessment_roadmap",
        description=(
            "Get the dependency-sequenced roadmap from an assessment's latest snapshot. "
            "Effort is a qualitative band (never a fabricated hour count or date)."
        ),
        input_schema={
            "type": "object",
            "properties": {"assessment_id": {"type": "string", "description": "Assessment UUID"}},
            "required": ["assessment_id"],
        },
        handler=_handle_get_assessment_roadmap,
        required_permission=Permission.ASSESSMENT_READ,
        required_feature="advanced_compliance_intelligence",
    ),
    ToolSpec(
        name="compare_assessment_snapshots",
        description=(
            "Compare two snapshots of the same assessment: score delta, findings that "
            "newly appeared, and findings that were resolved between the two versions."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "snapshot_id_a": {"type": "string", "description": "First snapshot UUID"},
                "snapshot_id_b": {"type": "string", "description": "Second snapshot UUID"},
            },
            "required": ["snapshot_id_a", "snapshot_id_b"],
        },
        handler=_handle_compare_assessment_snapshots,
        required_permission=Permission.ASSESSMENT_READ,
        required_feature="advanced_compliance_intelligence",
    ),
    ToolSpec(
        name="get_intelligence_context",
        description=(
            "Get the deterministic D2.2 aerospace intelligence chain for one asset: "
            "aerospace intelligence state, readiness, risk, priority, decision, and "
            "recommendation, each with its blockers/warnings and source records. This is "
            "the ONLY tool that may answer a question about whether an asset is ready, "
            "how risky/high-priority it is, what decision or recommendation currently "
            "applies, or what is blocking it -- never assert or compute any of those "
            "yourself. If a field is UNKNOWN, UNKNOWN_INTEL, or INSUFFICIENT_DATA, report "
            "that explicitly; never restate it as ready, safe, low risk, or nominal."
        ),
        input_schema={
            "type": "object",
            "properties": {"asset_id": {"type": "string", "description": "Asset UUID"}},
            "required": ["asset_id"],
        },
        handler=_handle_get_intelligence_context,
        required_permission=Permission.AIRCRAFT_READ,
        required_feature="predictive_maintenance",
    ),
    ToolSpec(
        name="get_fleet_attention_summary",
        description=(
            "Get the full fleet-wide deterministic intelligence picture: every asset's "
            "operational state, aerospace intelligence status, readiness, risk, priority, "
            "decision, top recommendation, and blockers (with source/required_action/"
            "resolution_action where available), plus fleet-wide count distributions and the "
            "subset of assets currently requiring attention (CRITICAL/HIGH priority, or "
            "ACTION_REQUIRED/IMMEDIATE_ACTION_REQUIRED/MONITOR/INSUFFICIENT_DATA decision "
            "state). This is the ONE tool for any fleet-wide or multi-asset question: 'which "
            "assets need attention', 'summarize the fleet', 'which assets have the highest "
            "risk', 'which assets are not ready', 'what is blocking the fleet', 'which assets "
            "have recommendations', 'give me a fleet brief', or 'compare asset A and asset B' "
            "(find both by registration or asset_id in the returned assets list -- do not call "
            "this tool twice for a comparison). For a question about exactly ONE specific "
            "asset with no comparison involved, get_intelligence_context is more detailed and "
            "may be preferable. Never compute risk/readiness/priority/decision/recommendation "
            "yourself from this data -- report the fields exactly as returned."
        ),
        input_schema={"type": "object", "properties": {}},
        handler=_handle_get_fleet_attention_summary,
        required_permission=Permission.AIRCRAFT_READ,
        required_feature="predictive_maintenance",
    ),
    ToolSpec(
        name="get_proactive_intelligence_summary",
        description=(
            "Get the proactive aerospace intelligence and emerging risks summary for the fleet: "
            "active early-warning signals, approaching maintenance and inspection thresholds, "
            "recurring finding patterns, compliance evidence gaps, readiness degradation drivers, "
            "and fleet-level anomaly patterns. Use for questions like 'what needs attention today', "
            "'what emerging risks exist', 'which maintenance intervals are due soon', or 'what "
            "proactive alerts are active'."
        ),
        input_schema={"type": "object", "properties": {}},
        handler=_handle_get_proactive_intelligence_summary,
        required_permission=Permission.AIRCRAFT_READ,
        required_feature="predictive_maintenance",
    ),
    ToolSpec(
        name="get_asset_proactive_signals",
        description=(
            "Get deterministic proactive intelligence signals for one specific asset: "
            "approaching flight-hour/cycle thresholds, recurring finding patterns, evidence gaps, "
            "and recommended decision actions. Use when investigating why a specific aircraft or "
            "drone requires attention or has high priority."
        ),
        input_schema={
            "type": "object",
            "properties": {"asset_id": {"type": "string", "description": "Asset UUID"}},
            "required": ["asset_id"],
        },
        handler=_handle_get_asset_proactive_signals,
        required_permission=Permission.AIRCRAFT_READ,
        required_feature="predictive_maintenance",
    ),
    ToolSpec(
        name="get_asset_hums_health",
        description=(
            "Get the HUMS (Health & Usage Monitoring System) telemetry-derived health summary for "
            "one asset: per-sensor health status (HEALTHY/DEGRADED/CRITICAL/INSUFFICIENT_DATA), the "
            "latest computed vibration feature, and active threshold exceedance counts. Use for "
            "questions like 'what is the current health of aircraft X' or 'which components show "
            "abnormal vibration'. Never states a health score when data is insufficient — reports "
            "INSUFFICIENT_DATA instead of fabricating one."
        ),
        input_schema={
            "type": "object",
            "properties": {"asset_id": {"type": "string", "description": "Asset UUID"}},
            "required": ["asset_id"],
        },
        handler=_handle_get_asset_hums_health,
        required_permission=Permission.HUMS_READ,
        required_feature="hums",
    ),
    ToolSpec(
        name="get_asset_hums_features",
        description=(
            "Get recent HUMS feature-engine history for one asset: individual computed feature "
            "values (RMS, peak, crest factor, kurtosis, skewness, dominant frequency, spectral "
            "energy, temperature/pressure/RPM trend, etc.), each with its data quality and the "
            "window it was computed over. Use for questions like 'what changed over the last N "
            "readings', 'which sensors have insufficient data', 'what is the current vibration "
            "condition', or 'why did this HUMS signal trigger'. Optionally filter by feature_type "
            "(e.g. 'rms', 'kurtosis', 'dominant_frequency'). Only reports stored, computed values — "
            "never infers an engineering conclusion beyond what was actually calculated."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "asset_id": {"type": "string", "description": "Asset UUID"},
                "feature_type": {
                    "type": "string",
                    "description": "Optional: filter to one feature type, e.g. 'rms', 'crest_factor', 'kurtosis', 'dominant_frequency', 'trend'.",
                },
            },
            "required": ["asset_id"],
        },
        handler=_handle_get_asset_hums_features,
        required_permission=Permission.HUMS_READ,
        required_feature="hums",
    ),
    ToolSpec(
        name="get_asset_hums_health_intelligence",
        description=(
            "Get the explainable, baseline-driven HUMS health intelligence verdict for one asset: "
            "overall state (HEALTHY/WATCH/DEGRADED/WARNING/CRITICAL/INSUFFICIENT_DATA), confidence, "
            "per-component breakdown, and the primary contributing features with their deviation from "
            "baseline (current value, baseline mean, normal range, standardized deviation), trend "
            "direction (increasing/decreasing/stable/volatile/accelerating), and a plain-language "
            "explanation. Use for questions like 'what is the health of this aircraft', 'why is this "
            "aircraft degraded', 'which component is contributing most to the degradation', 'how far is "
            "the current RMS from baseline', or 'has this feature been getting worse'. This is NOT fault "
            "diagnosis, RUL, or a failure prediction — only reports stored, computed deviation/trend "
            "data, never a fabricated engineering conclusion."
        ),
        input_schema={
            "type": "object",
            "properties": {"asset_id": {"type": "string", "description": "Asset UUID"}},
            "required": ["asset_id"],
        },
        handler=_handle_get_asset_hums_health_intelligence,
        required_permission=Permission.HUMS_READ,
        required_feature="hums",
    ),
    ToolSpec(
        name="get_asset_telemetry_status",
        description=(
            "Get the telemetry ingestion status and recent telemetry events for one asset: "
            "source system (DJI_FLIGHTHUB, HUMS_DEVICE), external asset/device ID, telemetry "
            "state (ACTIVE/STALE/NO_TELEMETRY_RECORDED), last received timestamp, total events, "
            "and recent event audit logs. Use for questions like 'what is the latest telemetry for "
            "this asset', 'when was telemetry last received for DR-HZ01', 'is telemetry current or "
            "stale', or 'which telemetry event supports the signal'. Never assumes an asset is healthy "
            "if telemetry is absent or stale."
        ),
        input_schema={
            "type": "object",
            "properties": {"asset_id": {"type": "string", "description": "Asset UUID"}},
            "required": ["asset_id"],
        },
        handler=_handle_get_asset_telemetry_status,
        required_permission=Permission.DRONE_READ,
        required_feature="flight_telemetry",
    ),
    ToolSpec(
        name="get_asset_hums_diagnostics",
        description=(
            "Get rule-based HUMS diagnostic candidates for one asset: fault hypothesis name, status "
            "(CANDIDATE/SUPPORTED/WEAK/CONFIRMED/REJECTED), severity, confidence, numeric score, "
            "affected component, and the full explanation with supporting AND contradicting evidence. "
            "Use for questions like 'why does Kota think this component may have a problem', 'what "
            "could be causing this', 'which component is most likely affected', or 'are there "
            "alternative explanations'. ALWAYS state that a candidate is a hypothesis requiring "
            "engineering confirmation, never present it as a confirmed fault — only status=='CONFIRMED' "
            "means a human has confirmed it, and the AI must never claim or imply a candidate is "
            "confirmed, that an aircraft is unsafe, or that maintenance is required, only report what "
            "is stored."
        ),
        input_schema={
            "type": "object",
            "properties": {"asset_id": {"type": "string", "description": "Asset UUID"}},
            "required": ["asset_id"],
        },
        handler=_handle_get_asset_hums_diagnostics,
        required_permission=Permission.HUMS_READ,
        required_feature="hums",
    ),
    ToolSpec(
        name="get_asset_hums_prognostics",
        description=(
            "Get HUMS Remaining Useful Life (RUL) prognostic estimates for one asset: RUL point "
            "estimate, lower/upper range, unit (flight hours or elapsed hours), confidence, quality, "
            "current value vs. configured threshold (and the threshold's type/source), degradation "
            "trajectory state, and any related H4 diagnostic hypothesis used as context. Use for "
            "questions like 'how much life does this component have left', 'when will this reach the "
            "maintenance threshold', or 'is this degrading'. CRITICAL: every RUL value is an ESTIMATE, "
            "NOT A CERTIFIED LIFE LIMIT. Always phrase responses as 'Kota estimates...' with the range "
            "and confidence, never as a guaranteed remaining life (e.g. never say 'the component will "
            "fail in N hours' — say 'Kota estimates N1-N2 hours of remaining useful life, confidence "
            "X, based on the current degradation trajectory; this is a prognostic estimate, not a "
            "certified life limit'). Never present a status=='INSUFFICIENT_DATA' or null RUL as a "
            "number — report that there isn't enough evidence yet."
        ),
        input_schema={
            "type": "object",
            "properties": {"asset_id": {"type": "string", "description": "Asset UUID"}},
            "required": ["asset_id"],
        },
        handler=_handle_get_asset_hums_prognostics,
        required_permission=Permission.HUMS_READ,
        required_feature="predictive_maintenance",
    ),
    ToolSpec(
        name="get_digital_twin",
        description=(
            "Get the complete current digital-twin state of one asset: identity, configuration, "
            "usage (flight hours/cycles), H3 health, H4 diagnostic candidates, H5 RUL prognostics, "
            "maintenance (open work orders/findings), compliance summary, and readiness state — all "
            "in one call. Use for questions like 'give me the complete current state of aircraft "
            "KA-102' or 'what is the current health and RUL of this asset'. Every section reports its "
            "own availability; never infer a missing section's value. This is a read-only aggregation "
            "over existing authoritative records — it never computes new health/diagnosis/RUL/"
            "compliance/readiness values, only reports what those systems already concluded."
        ),
        input_schema={
            "type": "object",
            "properties": {"asset_id": {"type": "string", "description": "Asset UUID"}},
            "required": ["asset_id"],
        },
        handler=_handle_get_digital_twin,
        required_permission=Permission.DIGITAL_TWIN_READ,
        required_feature="digital_twin",
    ),
    ToolSpec(
        name="get_component_genealogy",
        description=(
            "Get a component's full installation lineage: every asset it has ever been installed on, "
            "with install/removal dates, in chronological order. Use for questions like 'where has "
            "this engine been installed' or 'what is this component's history'."
        ),
        input_schema={
            "type": "object",
            "properties": {"component_id": {"type": "string", "description": "Component UUID"}},
            "required": ["component_id"],
        },
        handler=_handle_get_component_genealogy,
        required_permission=Permission.DIGITAL_TWIN_READ,
        required_feature="digital_twin",
    ),
    ToolSpec(
        name="get_asset_twin_timeline",
        description=(
            "Get the unified chronological lifecycle timeline for an asset: component installs/"
            "removals, HUMS diagnostic candidates, RUL updates, findings, and work orders, each "
            "linked back to its source record. Use for questions like 'show me the major events "
            "affecting this aircraft' or 'why is this aircraft restricted' (trace readiness blockers "
            "back through the timeline to their originating maintenance/compliance/HUMS event)."
        ),
        input_schema={
            "type": "object",
            "properties": {"asset_id": {"type": "string", "description": "Asset UUID"}},
            "required": ["asset_id"],
        },
        handler=_handle_get_asset_twin_timeline,
        required_permission=Permission.DIGITAL_TWIN_READ,
        required_feature="digital_twin",
    ),
    ToolSpec(
        name="trace_lineage",
        description=(
            "Trace how records are connected: from an asset, component, HUMS sensor, exceedance, finding, M7 "
            "signal or work order, return the surrounding graph (sensor -> exceedance -> finding -> signal -> work "
            "order -> asset/component) up to a few hops. Use for 'what is connected to this finding', 'what raised "
            "this signal' or 'what is impacted if this component is grounded'. Returns ids and relationships only; "
            "fetch details with the other tools."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "node_type": {"type": "string",
                              "enum": ["ASSET", "COMPONENT", "SENSOR", "EXCEEDANCE", "FINDING", "SIGNAL", "WORK_ORDER"]},
                "node_id": {"type": "string", "description": "UUID of the starting record"},
                "depth": {"type": "integer", "minimum": 0, "maximum": 4, "description": "Hops to follow (default 2)"},
            },
            "required": ["node_type", "node_id"],
        },
        handler=_handle_trace_lineage,
        required_permission=Permission.DIGITAL_TWIN_READ,
        required_feature="digital_twin",
    ),
    ToolSpec(
        name="get_asset_mro_intelligence",
        description=(
            "Get the H7 correlated MRO/compliance/readiness intelligence view for an asset: HUMS "
            "health state, open diagnostic/prognostic counts, authoritative readiness state alongside "
            "H7's own readiness-impact classification, compliance impact, operational impact, open "
            "maintenance intelligence candidates, and integration conflicts. This is a CORRELATION "
            "over existing authoritative services, never a new readiness/compliance engine."
        ),
        input_schema={
            "type": "object",
            "properties": {"asset_id": {"type": "string", "description": "Asset UUID"}},
            "required": ["asset_id"],
        },
        handler=_handle_get_asset_mro_intelligence,
        required_permission=Permission.MRO_INTELLIGENCE_READ,
        required_feature="mro_intelligence",
    ),
    ToolSpec(
        name="get_asset_maintenance_candidates",
        description=(
            "List maintenance intelligence candidates for an asset -- correlated recommendations "
            "generated when HUMS health/diagnostic/prognostic signals converge with maintenance "
            "state. These are advisory review items requiring human accept/reject/defer, never "
            "confirmed faults or automatic work orders."
        ),
        input_schema={
            "type": "object",
            "properties": {"asset_id": {"type": "string", "description": "Asset UUID"}},
            "required": ["asset_id"],
        },
        handler=_handle_get_asset_maintenance_candidates,
        required_permission=Permission.MRO_INTELLIGENCE_READ,
        required_feature="mro_intelligence",
    ),
    ToolSpec(
        name="get_asset_compliance_impact",
        description=(
            "Get compliance impact for an asset, correlating existing ComplianceObligation records "
            "(authoritative status, never re-derived) with open HUMS diagnostic signals for context."
        ),
        input_schema={
            "type": "object",
            "properties": {"asset_id": {"type": "string", "description": "Asset UUID"}},
            "required": ["asset_id"],
        },
        handler=_handle_get_asset_compliance_impact,
        required_permission=Permission.MRO_INTELLIGENCE_READ,
        required_feature="mro_intelligence",
    ),
    ToolSpec(
        name="get_asset_readiness_impact",
        description=(
            "Get H7's readiness-impact classification for an asset. Always returns BOTH the "
            "authoritative readiness_state (from readiness_intelligence_service, unmodified) and "
            "H7's own readiness_impact layer -- never merges them."
        ),
        input_schema={
            "type": "object",
            "properties": {"asset_id": {"type": "string", "description": "Asset UUID"}},
            "required": ["asset_id"],
        },
        handler=_handle_get_asset_readiness_impact,
        required_permission=Permission.MRO_INTELLIGENCE_READ,
        required_feature="mro_intelligence",
    ),
    ToolSpec(
        name="get_asset_operational_impact",
        description=(
            "Get H7's operational impact level (LOW/MEDIUM/HIGH/UNKNOWN) for an asset, derived from "
            "readiness impact and RUL horizon proximity. Returns UNKNOWN explicitly when no "
            "authoritative mission-criticality data exists -- never invents it."
        ),
        input_schema={
            "type": "object",
            "properties": {"asset_id": {"type": "string", "description": "Asset UUID"}},
            "required": ["asset_id"],
        },
        handler=_handle_get_asset_operational_impact,
        required_permission=Permission.MRO_INTELLIGENCE_READ,
        required_feature="mro_intelligence",
    ),
    ToolSpec(
        name="get_asset_integration_conflicts",
        description=(
            "List H7 integration conflicts for an asset -- cross-domain inconsistencies (readiness "
            "vs compliance, maintenance vs evidence, component configuration, diagnostic vs "
            "maintenance, prognostic vs telemetry freshness, compliance vs maintenance evidence). "
            "Reported only, never auto-resolved."
        ),
        input_schema={
            "type": "object",
            "properties": {"asset_id": {"type": "string", "description": "Asset UUID"}},
            "required": ["asset_id"],
        },
        handler=_handle_get_asset_integration_conflicts,
        required_permission=Permission.MRO_INTELLIGENCE_READ,
        required_feature="mro_intelligence",
    ),
    ToolSpec(
        name="list_fleet_assets",
        description=(
            "List the organization's airframes (aircraft, drones, helicopters, eVTOL) that its subscription "
            "entitles it to, with registration, type and status. Optional asset_type filter."
        ),
        input_schema={
            "type": "object",
            "properties": {"asset_type": {"type": "string", "description": "AIRCRAFT, DRONE, HELICOPTER or EVTOL"}},
        },
        handler=_handle_list_fleet_assets,
        required_permission=Permission.AIRCRAFT_READ,
        required_feature="aircraft_fleet_management,drone_fleet_management,helicopter_fleet_management,evtol_fleet_management",
    ),
    ToolSpec(
        name="get_alert_details",
        description=(
            "Get the verified, authoritative record and evidence for an individual operational or "
            "proactive alert by alert_id or signal_key (e.g. 'aog-...', 'shortage-...', 'deferred-...', "
            "'compliance-...', or proactive signal UUID/key). Returns severity, headline, contributing "
            "factors, evidence refs, and recommended actions. Never fabricate an alert or claim resolution "
            "without verified record state."
        ),
        input_schema={
            "type": "object",
            "properties": {"alert_id": {"type": "string", "description": "Alert UUID or signal key"}},
            "required": ["alert_id"],
        },
        handler=_handle_get_alert_details,
        required_permission=Permission.AIRCRAFT_READ,
        required_feature="aircraft_fleet_management,drone_fleet_management",
    ),
    ToolSpec(
        name="get_mission_details",
        description=(
            "Get the authoritative mission details for a planned or authorized drone mission by mission UUID: "
            "purpose, operating area, status, planned start/end times, assigned pilot name, and associated asset. "
            "Clearly distinguishes planned/authorized mission context from actual flight execution — never infer "
            "flight completion without verified flight telemetry."
        ),
        input_schema={
            "type": "object",
            "properties": {"mission_id": {"type": "string", "description": "Mission UUID"}},
            "required": ["mission_id"],
        },
        handler=_handle_get_mission_details,
        required_permission=Permission.DRONE_READ,
        required_feature="drone_fleet_management",
    ),
    ToolSpec(
        name="get_fleet_correlations",
        description=(
            "Retrieve H8.3 cross-asset HUMS and fleet anomaly pattern correlation results for the "
            "authenticated organization. Returns correlated multi-asset patterns (e.g. harmonic vibration, "
            "temperature exceedance clusters), similarity scores, confidence classification, participating "
            "assets, and supporting evidence references. Filter by asset_id, feature_family (e.g. 'vibration', "
            "'temperature'), pattern_type, confidence ('HIGH', 'MEDIUM', 'LOW', 'INSUFFICIENT_EVIDENCE'), "
            "or lookback days. Read-only, tenant-isolated."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "asset_id": {"type": "string", "description": "Optional asset UUID to filter correlations involving this asset"},
                "feature_family": {"type": "string", "description": "Optional feature family (e.g. 'vibration', 'temperature')"},
                "pattern_type": {"type": "string", "description": "Optional pattern type (e.g. 'CROSS_ASSET_HARMONIC_VIBRATION')"},
                "confidence": {"type": "string", "description": "Optional confidence: HIGH, MEDIUM, LOW, INSUFFICIENT_EVIDENCE"},
                "days": {"type": "integer", "description": "Lookback window in days (default 30, range 1-365)"},
            },
        },
        handler=_handle_get_fleet_correlations,
        required_permission=Permission.AIRCRAFT_READ,
        required_feature="predictive_maintenance",
    ),
    ToolSpec(
        name="get_fleet_correlation_detail",
        description=(
            "Retrieve detailed record, participating assets, observation window, similarity metrics, "
            "confidence classification, explicit limitations, and evidence provenance for a specific cross-asset "
            "correlation result by correlation_id. Read-only, tenant-isolated."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "correlation_id": {"type": "string", "description": "Correlation UUID"},
                "days": {"type": "integer", "description": "Lookback window in days (default 30)"},
            },
            "required": ["correlation_id"],
        },
        handler=_handle_get_fleet_correlation_detail,
        required_permission=Permission.AIRCRAFT_READ,
        required_feature="predictive_maintenance",
    ),
    ToolSpec(
        name="get_fleet_signals",
        description=(
            "Retrieve canonical M7 proactive fleet signals for the authenticated organization with optional "
            "asset_id, signal_category, severity (CRITICAL, HIGH, MEDIUM, LOW), or status (OPEN, ACKNOWLEDGED, RESOLVED) "
            "filters. Read-only, tenant-isolated."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "asset_id": {"type": "string", "description": "Optional asset UUID"},
                "signal_category": {"type": "string", "description": "Optional signal category/type"},
                "severity": {"type": "string", "description": "Optional severity: CRITICAL, HIGH, MEDIUM, LOW"},
                "status": {"type": "string", "description": "Optional status: OPEN, ACKNOWLEDGED, RESOLVED"},
            },
        },
        handler=_handle_get_fleet_signals,
        required_permission=Permission.AIRCRAFT_READ,
        required_feature="predictive_maintenance",
    ),
    ToolSpec(
        name="get_fleet_correlation_summary",
        description=(
            "Get a combined bounded view of cross-asset anomaly correlations, related M7 proactive signals, "
            "and supporting evidence references across the fleet. Read-only, tenant-isolated."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "days": {"type": "integer", "description": "Lookback window in days (default 30)"},
            },
        },
        handler=_handle_get_fleet_correlation_summary,
        required_permission=Permission.AIRCRAFT_READ,
        required_feature="predictive_maintenance",
    ),
]


TOOL_REGISTRY_BY_NAME: dict[str, ToolSpec] = {t.name: t for t in TOOL_REGISTRY}


def anthropic_tool_schemas() -> list[dict[str, Any]]:
    """Tool list in the shape the Anthropic Messages API expects."""
    return [
        {"name": t.name, "description": t.description, "input_schema": t.input_schema}
        for t in TOOL_REGISTRY
    ]


def execute_tool(db: Session, user: CurrentUser, name: str, args: dict[str, Any]) -> dict[str, Any]:
    spec = TOOL_REGISTRY_BY_NAME.get(name)
    if spec is None:
        raise AeroComplyError(f"Unknown tool: {name}", code="unknown_tool")
    from app.core import metrics

    with metrics.Timer() as timer:
        try:
            _require_permission(user, spec.required_permission)
            _require_entitlement(db, user, spec)
            return spec.handler(db, user, args)
        except AeroComplyError as exc:
            metrics.LISA_TOOL_ERRORS.inc(tool=name, code=str(getattr(exc, "code", None) or "error"))
            raise
        finally:
            metrics.LISA_TOOL_LATENCY.observe(timer.seconds, tool=name)
