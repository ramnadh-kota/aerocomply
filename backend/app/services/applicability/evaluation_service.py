"""Applicability Evaluation Engine Service.

Evaluates an aircraft/asset against hierarchical applicability rules using
deterministic 3-valued (Kleene) logic. Produces immutable evaluation results
capturing the exact configuration snapshot and reasoning trace.
"""

import re
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError
from app.models.aircraft import Aircraft
from app.models.applicability import (
    ApplicabilityCondition,
    ApplicabilityEvaluation,
    ApplicabilityRule,
    ConditionType,
    EvaluationResult,
)
from app.models.asset import Asset
from app.models.component import Component, ComponentStatus
from app.schemas.applicability import (
    ApplicabilityConditionCreateRequest,
    ApplicabilityEvaluationRequest,
    ApplicabilityRuleCreateRequest,
)
from app.services.applicability.kleene import (
    KleeneValue,
    kleene_and_all,
    kleene_not,
    kleene_or_all,
)
from app.services.audit_service import record_audit_event


def create_rule(
    db: Session,
    *,
    organization_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    payload: ApplicabilityRuleCreateRequest,
) -> ApplicabilityRule:
    """Create a new applicability rule with an optional hierarchical condition tree."""
    # Check uniqueness of rule_code within tenant
    existing = db.execute(
        select(ApplicabilityRule).where(
            ApplicabilityRule.organization_id == organization_id,
            ApplicabilityRule.rule_code == payload.rule_code,
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise ConflictError(f"Applicability rule with code '{payload.rule_code}' already exists.")

    rule = ApplicabilityRule(
        organization_id=organization_id,
        rule_code=payload.rule_code,
        title=payload.title,
        description=payload.description,
        regulatory_requirement_id=payload.regulatory_requirement_id,
        is_active=payload.is_active,
    )
    db.add(rule)
    db.flush()

    if payload.root_condition is not None:
        root_cond = _create_condition_node(
            db,
            organization_id=organization_id,
            rule_id=rule.id,
            parent_id=None,
            req=payload.root_condition,
        )
        rule.root_condition_id = root_cond.id
        db.flush()

    record_audit_event(
        db,
        organization_id=organization_id,
        user_id=actor_user_id,
        action="applicability_rule.created",
        entity_type="ApplicabilityRule",
        entity_id=rule.id,
        metadata={"rule_code": rule.rule_code, "title": rule.title},
    )

    db.commit()
    db.refresh(rule)
    return rule


def _create_condition_node(
    db: Session,
    *,
    organization_id: uuid.UUID,
    rule_id: uuid.UUID,
    parent_id: uuid.UUID | None,
    req: ApplicabilityConditionCreateRequest,
) -> ApplicabilityCondition:
    """Recursively persist condition nodes in the hierarchical condition tree."""
    cond = ApplicabilityCondition(
        organization_id=organization_id,
        rule_id=rule_id,
        parent_condition_id=parent_id,
        condition_type=req.condition_type,
        label=req.label,
        parameters=req.parameters,
        sequence=req.sequence,
    )
    db.add(cond)
    db.flush()

    for child_req in req.children:
        _create_condition_node(
            db,
            organization_id=organization_id,
            rule_id=rule_id,
            parent_id=cond.id,
            req=child_req,
        )

    return cond


def get_rule(
    db: Session,
    *,
    organization_id: uuid.UUID,
    rule_id: uuid.UUID,
) -> ApplicabilityRule:
    rule = db.execute(
        select(ApplicabilityRule).where(
            ApplicabilityRule.id == rule_id,
            ApplicabilityRule.organization_id == organization_id,
        )
    ).scalar_one_or_none()
    if rule is None:
        raise NotFoundError(f"Applicability rule {rule_id} not found.")
    return rule


def list_rules(
    db: Session,
    *,
    organization_id: uuid.UUID,
) -> list[ApplicabilityRule]:
    return list(
        db.execute(
            select(ApplicabilityRule)
            .where(ApplicabilityRule.organization_id == organization_id)
            .order_by(ApplicabilityRule.rule_code.asc())
        )
        .scalars()
        .all()
    )


def _resolve_subject(
    db: Session,
    *,
    organization_id: uuid.UUID,
    aircraft_id: uuid.UUID | None,
    asset_id: uuid.UUID | None,
) -> tuple[Aircraft | None, Asset | None]:
    """Resolve target aircraft and asset while strictly enforcing tenant isolation and soft-delete."""
    resolved_aircraft: Aircraft | None = None
    resolved_asset: Asset | None = None

    if aircraft_id is not None:
        resolved_aircraft = db.execute(
            select(Aircraft).where(
                Aircraft.id == aircraft_id,
                Aircraft.organization_id == organization_id,
            )
        ).scalar_one_or_none()
        if resolved_aircraft is None:
            raise NotFoundError(f"Aircraft {aircraft_id} not found.")

        if resolved_aircraft.asset_id is not None:
            resolved_asset = db.execute(
                select(Asset).where(
                    Asset.id == resolved_aircraft.asset_id,
                    Asset.organization_id == organization_id,
                    Asset.deleted_at.is_(None),
                )
            ).scalar_one_or_none()
            if resolved_asset is None:
                # Soft-deleted or unresolvable asset
                raise NotFoundError(f"Asset linked to aircraft {aircraft_id} is deleted or inaccessible.")

    elif asset_id is not None:
        resolved_asset = db.execute(
            select(Asset).where(
                Asset.id == asset_id,
                Asset.organization_id == organization_id,
                Asset.deleted_at.is_(None),
            )
        ).scalar_one_or_none()
        if resolved_asset is None:
            raise NotFoundError(f"Asset {asset_id} not found.")

        resolved_aircraft = db.execute(
            select(Aircraft).where(
                Aircraft.asset_id == asset_id,
                Aircraft.organization_id == organization_id,
            )
        ).scalar_one_or_none()

    return resolved_aircraft, resolved_asset


def _capture_configuration_snapshot(
    db: Session,
    *,
    organization_id: uuid.UUID,
    aircraft: Aircraft | None,
    asset: Asset | None,
) -> dict[str, Any]:
    """Build an immutable snapshot of the aircraft and component configuration at evaluation time."""
    asset_id = (asset.id if asset else None) or (aircraft.asset_id if aircraft else None)

    # Fetch currently installed engines on this asset
    installed_engines: list[dict[str, Any]] = []
    if asset_id is not None:
        engines = db.execute(
            select(Component).where(
                Component.asset_id == asset_id,
                Component.organization_id == organization_id,
                Component.component_type == "ENGINE",
                Component.status == ComponentStatus.INSTALLED,
            )
        ).scalars().all()

        for eng in engines:
            installed_engines.append(
                {
                    "component_id": str(eng.id),
                    "name": eng.name,
                    "model": eng.model,
                    "manufacturer": eng.manufacturer,
                    "serial_number": eng.serial_number,
                }
            )

    return {
        "aircraft_id": str(aircraft.id) if aircraft else None,
        "asset_id": str(asset_id) if asset_id else None,
        "registration": aircraft.registration if aircraft else (asset.registration if asset else None),
        "msn": aircraft.msn if aircraft else None,
        "aircraft_type": aircraft.aircraft_type if aircraft else None,
        "status": aircraft.status if aircraft else (asset.status if asset else None),
        "installed_engines": installed_engines,
        "snapshot_timestamp": datetime.now(UTC).isoformat(),
    }


def _evaluate_node(
    node: ApplicabilityCondition,
    snapshot: dict[str, Any],
) -> tuple[KleeneValue, dict[str, Any]]:
    """Recursively evaluate a condition tree node against a configuration snapshot.

    Returns (KleeneValue, reasoning_trace_node).
    """
    cond_type = node.condition_type.upper()
    params = node.parameters or {}

    if cond_type == ConditionType.AND.value:
        child_results = [_evaluate_node(child, snapshot) for child in node.children]
        val = kleene_and_all([c[0] for c in child_results])
        trace = {
            "condition_id": str(node.id),
            "condition_type": cond_type,
            "label": node.label,
            "result": str(val),
            "reason": f"Kleene AND across {len(child_results)} condition(s) evaluated to {val}",
            "children": [c[1] for c in child_results],
        }
        return val, trace

    elif cond_type == ConditionType.OR.value:
        child_results = [_evaluate_node(child, snapshot) for child in node.children]
        val = kleene_or_all([c[0] for c in child_results])
        trace = {
            "condition_id": str(node.id),
            "condition_type": cond_type,
            "label": node.label,
            "result": str(val),
            "reason": f"Kleene OR across {len(child_results)} condition(s) evaluated to {val}",
            "children": [c[1] for c in child_results],
        }
        return val, trace

    elif cond_type == ConditionType.NOT.value:
        if not node.children:
            val = KleeneValue.UNKNOWN
            reason = "NOT combinator has no child condition"
            trace_children = []
        else:
            child_val, child_trace = _evaluate_node(node.children[0], snapshot)
            val = kleene_not(child_val)
            reason = f"Kleene NOT over child result {child_val} yielded {val}"
            trace_children = [child_trace]
        trace = {
            "condition_id": str(node.id),
            "condition_type": cond_type,
            "label": node.label,
            "result": str(val),
            "reason": reason,
            "children": trace_children,
        }
        return val, trace

    elif cond_type == ConditionType.AIRCRAFT_VARIANT.value:
        target_variant = params.get("variant") or params.get("variants") or params.get("model")
        actual_type = snapshot.get("aircraft_type")

        if not target_variant or not actual_type:
            val = KleeneValue.UNKNOWN
            reason = "Missing aircraft type in configuration record" if not actual_type else "Missing variant in rule specification"
            expected = target_variant
            actual = actual_type
        else:
            targets = [t.strip().upper() for t in target_variant] if isinstance(target_variant, list) else [target_variant.strip().upper()]
            actual_norm = actual_type.strip().upper()

            # Check exact match or prefix/family match (e.g. A320 matches A320-200)
            matches = any(
                actual_norm == t or actual_norm.startswith(f"{t}-") or actual_norm.startswith(f"{t} ") or t in actual_norm.split("-")
                for t in targets
            )
            val = KleeneValue.TRUE if matches else KleeneValue.FALSE
            reason = f"Aircraft variant '{actual_type}' matches target '{target_variant}'" if matches else f"Aircraft variant '{actual_type}' does not match target '{target_variant}'"
            expected = target_variant
            actual = actual_type

        return val, {
            "condition_id": str(node.id),
            "condition_type": cond_type,
            "label": node.label,
            "expected": expected,
            "actual": actual,
            "result": str(val),
            "reason": reason,
        }

    elif cond_type == ConditionType.MSN_RANGE.value:
        min_msn = params.get("min_msn") if params.get("min_msn") is not None else params.get("min")
        max_msn = params.get("max_msn") if params.get("max_msn") is not None else params.get("max")
        actual_msn = snapshot.get("msn")

        if actual_msn is None or (min_msn is None and max_msn is None):
            val = KleeneValue.UNKNOWN
            reason = "MSN missing in configuration record" if actual_msn is None else "MSN range unspecified in rule"
            expected = f"[{min_msn}, {max_msn}]"
            actual = actual_msn
        else:
            # Extract digits from MSN
            digits = re.findall(r"\d+", str(actual_msn))
            if not digits:
                val = KleeneValue.UNKNOWN
                reason = f"MSN '{actual_msn}' cannot be parsed as numeric"
                expected = f"[{min_msn}, {max_msn}]"
                actual = actual_msn
            else:
                msn_num = int(digits[-1])  # Take primary numeric identifier
                is_below = min_msn is not None and msn_num < min_msn
                is_above = max_msn is not None and msn_num > max_msn

                if is_below or is_above:
                    val = KleeneValue.FALSE
                    reason = f"MSN {msn_num} is outside range [{min_msn}, {max_msn}]"
                else:
                    val = KleeneValue.TRUE
                    reason = f"MSN {msn_num} is within range [{min_msn}, {max_msn}]"
                expected = f"[{min_msn}, {max_msn}]"
                actual = msn_num

        return val, {
            "condition_id": str(node.id),
            "condition_type": cond_type,
            "label": node.label,
            "expected": expected,
            "actual": actual,
            "result": str(val),
            "reason": reason,
        }

    elif cond_type == ConditionType.ENGINE_TYPE.value:
        target_engine = params.get("engine_type") or params.get("model") or params.get("engine_types")
        installed_engines = snapshot.get("installed_engines", [])

        if not target_engine:
            val = KleeneValue.UNKNOWN
            reason = "Engine specification missing in rule parameters"
            expected = target_engine
            actual = None
        elif not installed_engines:
            # Missing configuration information -> UNKNOWN (NEVER FALSE)
            val = KleeneValue.UNKNOWN
            reason = "No installed engine configuration records on file for this aircraft"
            expected = target_engine
            actual = "NO_RECORDS"
        else:
            targets = [t.strip().upper() for t in target_engine] if isinstance(target_engine, list) else [target_engine.strip().upper()]

            matched = False
            has_unknown_model = False
            engine_models: list[str | None] = []

            for eng in installed_engines:
                m = eng.get("model")
                engine_models.append(m)
                if not m:
                    has_unknown_model = True
                    continue
                m_norm = m.strip().upper()
                if any(t in m_norm or m_norm in t for t in targets):
                    matched = True
                    break

            if matched:
                val = KleeneValue.TRUE
                reason = f"Installed engine matches target '{target_engine}'"
            elif has_unknown_model:
                val = KleeneValue.UNKNOWN
                reason = "One or more installed engines have incomplete model records"
            else:
                val = KleeneValue.FALSE
                reason = f"Installed engine models {engine_models} do not match target '{target_engine}'"

            expected = target_engine
            actual = engine_models

        return val, {
            "condition_id": str(node.id),
            "condition_type": cond_type,
            "label": node.label,
            "expected": expected,
            "actual": actual,
            "result": str(val),
            "reason": reason,
        }

    else:
        # Fallback for unrecognized condition type
        val = KleeneValue.UNKNOWN
        return val, {
            "condition_id": str(node.id),
            "condition_type": cond_type,
            "label": node.label,
            "result": str(val),
            "reason": f"Unsupported condition type '{cond_type}' evaluated to UNKNOWN",
        }


def evaluate_applicability(
    db: Session,
    *,
    organization_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    payload: ApplicabilityEvaluationRequest,
) -> ApplicabilityEvaluation:
    """Evaluate an applicability rule against an asset/aircraft and persist an immutable evaluation record."""
    rule = get_rule(db, organization_id=organization_id, rule_id=payload.rule_id)
    if not rule.is_active:
        raise ConflictError(f"Applicability rule '{rule.rule_code}' is inactive.")

    aircraft, asset = _resolve_subject(
        db,
        organization_id=organization_id,
        aircraft_id=payload.aircraft_id,
        asset_id=payload.asset_id,
    )

    # 1. Capture immutable configuration snapshot
    config_snapshot = _capture_configuration_snapshot(
        db,
        organization_id=organization_id,
        aircraft=aircraft,
        asset=asset,
    )

    # 2. Evaluate condition tree
    if rule.root_condition_id is not None:
        root_condition = db.execute(
            select(ApplicabilityCondition).where(
                ApplicabilityCondition.id == rule.root_condition_id,
                ApplicabilityCondition.organization_id == organization_id,
            )
        ).scalar_one_or_none()
    else:
        root_condition = None

    if root_condition is None:
        overall_kleene = KleeneValue.UNKNOWN
        reasoning_trace = {
            "rule_id": str(rule.id),
            "rule_code": rule.rule_code,
            "result": str(overall_kleene),
            "reason": "Rule has no root condition configured",
            "root_node": None,
        }
    else:
        overall_kleene, root_trace = _evaluate_node(root_condition, config_snapshot)
        reasoning_trace = {
            "rule_id": str(rule.id),
            "rule_code": rule.rule_code,
            "result": str(overall_kleene),
            "root_node": root_trace,
        }

    # 3. Determine system result without collapsing states
    if payload.force_review:
        system_result = EvaluationResult.REVIEW_REQUIRED.value
    elif overall_kleene is KleeneValue.TRUE:
        system_result = EvaluationResult.APPLICABLE.value
    elif overall_kleene is KleeneValue.FALSE:
        system_result = EvaluationResult.NOT_APPLICABLE.value
    else:
        # UNKNOWN MUST NEVER BE TREATED AS FALSE or NOT_APPLICABLE
        system_result = EvaluationResult.INSUFFICIENT_DATA.value

    evaluation = ApplicabilityEvaluation(
        organization_id=organization_id,
        rule_id=rule.id,
        aircraft_id=aircraft.id if aircraft else None,
        asset_id=asset.id if asset else None,
        evaluated_by_user_id=actor_user_id,
        system_result=system_result,
        configuration_snapshot=config_snapshot,
        reasoning_trace=reasoning_trace,
        notes=payload.notes,
    )
    db.add(evaluation)
    db.flush()

    record_audit_event(
        db,
        organization_id=organization_id,
        user_id=actor_user_id,
        action="applicability.evaluated",
        entity_type="ApplicabilityEvaluation",
        entity_id=evaluation.id,
        metadata={
            "rule_id": str(rule.id),
            "rule_code": rule.rule_code,
            "aircraft_id": str(aircraft.id) if aircraft else None,
            "asset_id": str(asset.id) if asset else None,
            "system_result": system_result,
        },
    )

    db.commit()
    db.refresh(evaluation)
    return evaluation
