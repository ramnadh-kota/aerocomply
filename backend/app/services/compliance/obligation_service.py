"""Compliance Obligation Service.

Connects regulatory requirements, applicability evaluations, required actions,
and the evidence digital thread into a deterministic, auditable compliance lifecycle.

Target Flow:
REGULATORY REQUIREMENT
    ↓
APPLICABILITY RULE
    ↓
APPLICABILITY EVALUATION
    ↓
COMPLIANCE OBLIGATION
    ↓
REQUIRED ACTION
    ↓
EVIDENCE
    ↓
VERIFICATION
    ↓
COMPLIANCE STATE
"""

import datetime
import uuid
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.errors import AeroComplyError, ConflictError, NotFoundError
from app.models.aircraft import Aircraft
from app.models.applicability import ApplicabilityEvaluation, ApplicabilityRule, EvaluationResult
from app.models.asset import Asset
from app.models.compliance import (
    ComplianceObligation,
    ComplianceState,
    RegulatoryRequirement,
)
from app.models.evidence import Evidence, EvidenceStatus
from app.schemas.compliance import (
    ComplianceObligationCreateRequest,
    ComplianceObligationUpdateRequest,
    ComplianceOverviewResponse,
    ComplianceTraceabilityResponse,
)
from app.services import aircraft_service, asset_service
from app.services.applicability import evaluation_service
from app.services.asset_resolution import resolve_asset_id
from app.services.audit_service import record_audit_event


def create_obligation(
    db: Session,
    *,
    organization_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    payload: ComplianceObligationCreateRequest,
) -> ComplianceObligation:
    """Create or idempotently find a compliance obligation."""
    # 1. Verify requirement belongs to tenant
    req = db.execute(
        select(RegulatoryRequirement).where(
            RegulatoryRequirement.id == payload.requirement_id,
            RegulatoryRequirement.organization_id == organization_id,
        )
    ).scalar_one_or_none()
    if req is None:
        raise NotFoundError("Regulatory requirement not found")

    # 2. Resolve asset/aircraft
    aircraft_id = payload.aircraft_id
    asset_id = payload.asset_id
    if aircraft_id is not None:
        aircraft = aircraft_service.get_aircraft(
            db, organization_id=organization_id, aircraft_id=aircraft_id
        )
        if asset_id is None:
            asset_id = resolve_asset_id(aircraft)
    elif asset_id is not None:
        asset_service.get_asset(db, organization_id=organization_id, asset_id=asset_id)

    # 3. Verify rule if provided
    rule_id = payload.rule_id
    if rule_id is not None:
        rule = db.execute(
            select(ApplicabilityRule).where(
                ApplicabilityRule.id == rule_id,
                ApplicabilityRule.organization_id == organization_id,
            )
        ).scalar_one_or_none()
        if rule is None:
            raise NotFoundError("Applicability rule not found")

    # 4. Check for existing obligation (idempotency check)
    existing_query = select(ComplianceObligation).where(
        ComplianceObligation.organization_id == organization_id,
        ComplianceObligation.requirement_id == payload.requirement_id,
    )
    if asset_id is not None:
        existing_query = existing_query.where(ComplianceObligation.asset_id == asset_id)
    elif aircraft_id is not None:
        existing_query = existing_query.where(ComplianceObligation.aircraft_id == aircraft_id)

    existing = db.execute(existing_query).scalar_one_or_none()
    if existing is not None:
        # Idempotently update and return existing obligation
        if payload.priority:
            existing.priority = payload.priority
        if payload.due_date is not None:
            existing.due_date = payload.due_date
        if payload.required_action is not None:
            existing.required_action = payload.required_action
        if payload.evidence_requirements is not None:
            existing.evidence_requirements = payload.evidence_requirements
        if payload.rule_id is not None:
            existing.rule_id = payload.rule_id
        db.add(existing)
        db.commit()
        db.refresh(existing)
        return existing

    # Derive initial status based on due date if provided
    initial_status = ComplianceState.NOT_EVALUATED.value
    today = datetime.date.today()
    if payload.due_date and payload.due_date < today:
        initial_status = ComplianceState.OVERDUE.value
    elif payload.due_date:
        initial_status = ComplianceState.DUE.value

    obligation = ComplianceObligation(
        organization_id=organization_id,
        requirement_id=payload.requirement_id,
        rule_id=rule_id,
        asset_id=asset_id,
        aircraft_id=aircraft_id,
        applicability_evaluation_id=payload.applicability_evaluation_id,
        status=initial_status,
        priority=payload.priority or "MEDIUM",
        due_date=payload.due_date,
        recurrence=payload.recurrence,
        responsible_role=payload.responsible_role,
        assigned_user_id=payload.assigned_user_id,
        required_action=payload.required_action or req.description,
        evidence_requirements=payload.evidence_requirements,
        notes=payload.notes,
    )
    db.add(obligation)
    db.flush()

    record_audit_event(
        db,
        organization_id=organization_id,
        user_id=actor_user_id,
        action="compliance_obligation.created",
        entity_type="ComplianceObligation",
        entity_id=obligation.id,
        metadata={
            "requirement_id": str(obligation.requirement_id),
            "asset_id": str(obligation.asset_id) if obligation.asset_id else None,
            "aircraft_id": str(obligation.aircraft_id) if obligation.aircraft_id else None,
            "status": obligation.status,
        },
    )
    db.commit()
    db.refresh(obligation)
    return obligation


def get_obligation(
    db: Session, *, organization_id: uuid.UUID, obligation_id: uuid.UUID
) -> ComplianceObligation:
    """Retrieve an obligation with tenant isolation."""
    obligation = db.execute(
        select(ComplianceObligation).where(
            ComplianceObligation.id == obligation_id,
            ComplianceObligation.organization_id == organization_id,
        )
    ).scalar_one_or_none()
    if obligation is None:
        raise NotFoundError("Compliance obligation not found")
    return obligation


def list_obligations(
    db: Session,
    *,
    organization_id: uuid.UUID,
    asset_id: uuid.UUID | None = None,
    aircraft_id: uuid.UUID | None = None,
    requirement_id: uuid.UUID | None = None,
    status: str | None = None,
) -> list[ComplianceObligation]:
    """List obligations for an organization with optional filters."""
    query = select(ComplianceObligation).where(
        ComplianceObligation.organization_id == organization_id
    )
    if asset_id is not None:
        query = query.where(ComplianceObligation.asset_id == asset_id)
    if aircraft_id is not None:
        query = query.where(ComplianceObligation.aircraft_id == aircraft_id)
    if requirement_id is not None:
        query = query.where(ComplianceObligation.requirement_id == requirement_id)
    if status is not None:
        query = query.where(ComplianceObligation.status == status)

    query = query.order_by(ComplianceObligation.created_at.desc())
    return list(db.execute(query).scalars().all())


def update_obligation(
    db: Session,
    *,
    organization_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    obligation_id: uuid.UUID,
    payload: ComplianceObligationUpdateRequest,
) -> ComplianceObligation:
    """Update compliance obligation fields."""
    obligation = get_obligation(db, organization_id=organization_id, obligation_id=obligation_id)
    previous_status = obligation.status

    if payload.priority is not None:
        obligation.priority = payload.priority
    if payload.due_date is not None:
        obligation.due_date = payload.due_date
    if payload.recurrence is not None:
        obligation.recurrence = payload.recurrence
    if payload.responsible_role is not None:
        obligation.responsible_role = payload.responsible_role
    if payload.assigned_user_id is not None:
        obligation.assigned_user_id = payload.assigned_user_id
    if payload.required_action is not None:
        obligation.required_action = payload.required_action
    if payload.evidence_requirements is not None:
        obligation.evidence_requirements = payload.evidence_requirements
    if payload.notes is not None:
        obligation.notes = payload.notes
    if payload.status is not None:
        obligation.status = payload.status

    if previous_status != obligation.status:
        record_audit_event(
            db,
            organization_id=organization_id,
            user_id=actor_user_id,
            action="compliance_obligation.status_changed",
            entity_type="ComplianceObligation",
            entity_id=obligation.id,
            metadata={
                "previous_status": previous_status,
                "new_status": obligation.status,
            },
        )

    db.add(obligation)
    db.commit()
    db.refresh(obligation)
    return obligation


def evaluate_and_sync_obligation(
    db: Session,
    *,
    organization_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    obligation_id: uuid.UUID,
) -> ComplianceObligation:
    """Evaluate applicability for an existing obligation and update its status.
    
    Domain Invariant #23:
    UNKNOWN must never be treated as FALSE.
    Missing configuration information produces INSUFFICIENT_DATA / BLOCKED,
    never silently declaring a requirement NOT_APPLICABLE.
    """
    obligation = get_obligation(db, organization_id=organization_id, obligation_id=obligation_id)

    # 1. Resolve rule to evaluate
    rule: ApplicabilityRule | None = None
    if obligation.rule_id is not None:
        rule = db.execute(
            select(ApplicabilityRule).where(
                ApplicabilityRule.id == obligation.rule_id,
                ApplicabilityRule.organization_id == organization_id,
            )
        ).scalar_one_or_none()

    if rule is None:
        # Search for active rule linked to requirement
        rule = db.execute(
            select(ApplicabilityRule).where(
                ApplicabilityRule.regulatory_requirement_id == obligation.requirement_id,
                ApplicabilityRule.organization_id == organization_id,
                ApplicabilityRule.is_active == True,  # noqa: E712
            )
        ).scalar_one_or_none()

    if rule is None:
        # No rule configured: requires human review
        obligation.status = ComplianceState.REVIEW_REQUIRED.value
        obligation.notes = (obligation.notes or "") + "\nNo applicability rule configured for requirement."
        db.add(obligation)
        db.commit()
        db.refresh(obligation)
        return obligation

    obligation.rule_id = rule.id

    # 2. Execute applicability evaluation using D2-1 evaluation engine
    from app.schemas.applicability import ApplicabilityEvaluationRequest

    eval_payload = ApplicabilityEvaluationRequest(
        rule_id=rule.id,
        aircraft_id=obligation.aircraft_id,
        asset_id=obligation.asset_id,
    )
    evaluation = evaluation_service.evaluate_applicability(
        db,
        organization_id=organization_id,
        actor_user_id=actor_user_id,
        payload=eval_payload,
    )
    obligation.applicability_evaluation_id = evaluation.id

    # 3. Map applicability evaluation to obligation compliance state
    today = datetime.date.today()
    if evaluation.system_result == EvaluationResult.APPLICABLE.value:
        if obligation.status in {
            ComplianceState.NOT_EVALUATED.value,
            ComplianceState.NOT_APPLICABLE.value,
            ComplianceState.BLOCKED.value,
        }:
            if obligation.due_date and obligation.due_date < today:
                obligation.status = ComplianceState.OVERDUE.value
            else:
                obligation.status = ComplianceState.DUE.value
    elif evaluation.system_result == EvaluationResult.NOT_APPLICABLE.value:
        obligation.status = ComplianceState.NOT_APPLICABLE.value
    elif evaluation.system_result == EvaluationResult.INSUFFICIENT_DATA.value:
        # UNKNOWN != FALSE: missing data produces BLOCKED, not NOT_APPLICABLE
        obligation.status = ComplianceState.BLOCKED.value
        missing_reasons = evaluation.reasoning_trace.get("missing_data", [])
        if missing_reasons:
            obligation.notes = f"Blocked by missing configuration data: {', '.join(missing_reasons)}"
    elif evaluation.system_result == EvaluationResult.REVIEW_REQUIRED.value:
        obligation.status = ComplianceState.REVIEW_REQUIRED.value

    # 4. Resolve compliance based on evidence if APPLICABLE
    resolve_obligation_compliance(db, obligation, actor_user_id=actor_user_id)

    record_audit_event(
        db,
        organization_id=organization_id,
        user_id=actor_user_id,
        action="compliance_obligation.evaluated",
        entity_type="ComplianceObligation",
        entity_id=obligation.id,
        metadata={
            "applicability_result": evaluation.system_result,
            "obligation_status": obligation.status,
            "evaluation_id": str(evaluation.id),
        },
    )

    db.add(obligation)
    db.commit()
    db.refresh(obligation)
    return obligation


def create_or_sync_from_evaluation(
    db: Session,
    *,
    organization_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    evaluation: ApplicabilityEvaluation,
) -> ComplianceObligation | None:
    """Create or update a compliance obligation from an applicability evaluation."""
    rule = evaluation.rule
    if rule is None:
        rule = db.execute(
            select(ApplicabilityRule).where(
                ApplicabilityRule.id == evaluation.rule_id,
                ApplicabilityRule.organization_id == organization_id,
            )
        ).scalar_one_or_none()

    if rule is None or rule.regulatory_requirement_id is None:
        # Standalone rule not tied to a regulatory requirement: no obligation created
        return None

    req_id = rule.regulatory_requirement_id

    # Check for existing obligation
    query = select(ComplianceObligation).where(
        ComplianceObligation.organization_id == organization_id,
        ComplianceObligation.requirement_id == req_id,
    )
    if evaluation.asset_id is not None:
        query = query.where(ComplianceObligation.asset_id == evaluation.asset_id)
    elif evaluation.aircraft_id is not None:
        query = query.where(ComplianceObligation.aircraft_id == evaluation.aircraft_id)

    obligation = db.execute(query).scalar_one_or_none()
    today = datetime.date.today()

    if obligation is None:
        # Determine status based on evaluation
        if evaluation.system_result == EvaluationResult.APPLICABLE.value:
            status = ComplianceState.DUE.value
        elif evaluation.system_result == EvaluationResult.NOT_APPLICABLE.value:
            status = ComplianceState.NOT_APPLICABLE.value
        elif evaluation.system_result == EvaluationResult.INSUFFICIENT_DATA.value:
            status = ComplianceState.BLOCKED.value
        else:
            status = ComplianceState.REVIEW_REQUIRED.value

        req = db.execute(
            select(RegulatoryRequirement).where(RegulatoryRequirement.id == req_id)
        ).scalar_one_or_none()

        obligation = ComplianceObligation(
            organization_id=organization_id,
            requirement_id=req_id,
            rule_id=rule.id,
            asset_id=evaluation.asset_id,
            aircraft_id=evaluation.aircraft_id,
            applicability_evaluation_id=evaluation.id,
            status=status,
            priority="HIGH" if evaluation.system_result == EvaluationResult.APPLICABLE.value else "MEDIUM",
            required_action=req.description if req else "Comply with regulatory requirement",
        )
        db.add(obligation)
        db.flush()
        record_audit_event(
            db, organization_id=organization_id, user_id=actor_user_id,
            action="compliance_obligation.created_from_evaluation", entity_type="ComplianceObligation",
            entity_id=obligation.id,
            metadata={"requirement_id": str(req_id), "rule_id": str(rule.id), "status": status,
                      "evaluation_result": evaluation.system_result},
        )
    else:
        previous_status = obligation.status
        obligation.applicability_evaluation_id = evaluation.id
        obligation.rule_id = rule.id
        if evaluation.system_result == EvaluationResult.APPLICABLE.value:
            if obligation.status in {
                ComplianceState.NOT_EVALUATED.value,
                ComplianceState.NOT_APPLICABLE.value,
                ComplianceState.BLOCKED.value,
            }:
                obligation.status = (
                    ComplianceState.OVERDUE.value
                    if (obligation.due_date and obligation.due_date < today)
                    else ComplianceState.DUE.value
                )
        elif evaluation.system_result == EvaluationResult.NOT_APPLICABLE.value:
            obligation.status = ComplianceState.NOT_APPLICABLE.value
        elif evaluation.system_result == EvaluationResult.INSUFFICIENT_DATA.value:
            obligation.status = ComplianceState.BLOCKED.value
        elif evaluation.system_result == EvaluationResult.REVIEW_REQUIRED.value:
            obligation.status = ComplianceState.REVIEW_REQUIRED.value

        resolve_obligation_compliance(db, obligation, actor_user_id=actor_user_id)
        db.add(obligation)
        if obligation.status != previous_status:
            record_audit_event(
                db, organization_id=organization_id, user_id=actor_user_id,
                action="compliance_obligation.status_changed", entity_type="ComplianceObligation",
                entity_id=obligation.id,
                metadata={"from_status": previous_status, "to_status": obligation.status,
                          "evaluation_result": evaluation.system_result, "source": "applicability_evaluation"},
            )

    db.commit()
    db.refresh(obligation)
    return obligation


def resolve_obligation_compliance(
    db: Session,
    obligation: ComplianceObligation,
    *,
    actor_user_id: uuid.UUID | None = None,
) -> ComplianceObligation:
    """Evaluate attached evidence and resolve the deterministic compliance state.
    
    Critical Safety Rules:
    - Evidence in REJECTED state prevents COMPLIANT status (produces NON_COMPLIANT or BLOCKED).
    - An obligation only becomes COMPLIANT when all required evidence is VERIFIED and accepted.
    - If evidence is absent or unverified, remains DUE / OVERDUE / IN_PROGRESS.
    """
    # If not applicable or blocked at applicability level, do not resolve to compliant
    if obligation.status in {
        ComplianceState.NOT_APPLICABLE.value,
        ComplianceState.BLOCKED.value,
        ComplianceState.REVIEW_REQUIRED.value,
    }:
        return obligation

    # Fetch all linked evidence items
    evidence_items = list(
        db.execute(
            select(Evidence).where(
                Evidence.compliance_obligation_id == obligation.id,
                Evidence.organization_id == obligation.organization_id,
            )
        )
        .scalars()
        .all()
    )

    today = datetime.date.today()
    any_rejected = any(
        e.verification_status == "REJECTED" or e.status == EvidenceStatus.REJECTED.value
        for e in evidence_items
    )
    verified_items = [
        e
        for e in evidence_items
        if e.verification_status == "VERIFIED" and e.status in {EvidenceStatus.ACCEPTED.value, "VERIFIED"}
    ]

    previous_status = obligation.status

    if any_rejected:
        # Explicit rejected evidence produces NON_COMPLIANT
        obligation.status = ComplianceState.NON_COMPLIANT.value
    elif verified_items:
        # Has verified evidence
        obligation.status = ComplianceState.COMPLIANT.value
        obligation.verified_at = datetime.datetime.now(datetime.timezone.utc)
        if obligation.completed_at is None:
            obligation.completed_at = datetime.datetime.now(datetime.timezone.utc)
    elif evidence_items:
        # Evidence has been uploaded but not yet verified
        obligation.status = ComplianceState.IN_PROGRESS.value
    else:
        # No evidence yet attached
        if obligation.due_date and obligation.due_date < today:
            obligation.status = ComplianceState.OVERDUE.value
        else:
            obligation.status = ComplianceState.DUE.value

    if previous_status != obligation.status and obligation.status == ComplianceState.COMPLIANT.value:
        record_audit_event(
            db,
            organization_id=obligation.organization_id,
            user_id=actor_user_id,
            action="compliance_obligation.resolved_compliant",
            entity_type="ComplianceObligation",
            entity_id=obligation.id,
            metadata={"verified_evidence_count": len(verified_items)},
        )

    db.add(obligation)
    return obligation


def get_obligation_traceability(
    db: Session, *, organization_id: uuid.UUID, obligation_id: uuid.UUID
) -> ComplianceTraceabilityResponse:
    """Answer all 7 core explainability questions:
    
    1. WHY does this requirement apply?
    2. WHAT action is required?
    3. WHAT evidence is required?
    4. WHAT evidence has been provided?
    5. HAS it been verified?
    6. WHY is the current compliance state what it is?
    7. WHAT is blocking compliance?
    """
    obligation = get_obligation(db, organization_id=organization_id, obligation_id=obligation_id)
    req = obligation.requirement

    # Asset summary
    asset_dict: dict[str, Any] = {
        "asset_id": str(obligation.asset_id) if obligation.asset_id else None,
        "aircraft_id": str(obligation.aircraft_id) if obligation.aircraft_id else None,
        "identifier": "UNKNOWN",
        "variant": "UNKNOWN",
    }
    if obligation.aircraft_id is not None:
        ac = db.execute(
            select(Aircraft).where(Aircraft.id == obligation.aircraft_id)
        ).scalar_one_or_none()
        if ac:
            asset_dict["identifier"] = getattr(ac, "registration", getattr(ac, "registration_number", "UNKNOWN"))
            asset_dict["msn"] = getattr(ac, "msn", getattr(ac, "serial_number", "UNKNOWN"))
            asset_dict["variant"] = getattr(ac, "aircraft_type", getattr(ac, "model", "UNKNOWN"))
    elif obligation.asset_id is not None:
        ast = db.execute(
            select(Asset).where(Asset.id == obligation.asset_id)
        ).scalar_one_or_none()
        if ast:
            asset_dict["identifier"] = ast.registration or str(ast.id)
            asset_dict["variant"] = ast.model or ast.asset_type

    # Why applies (Applicability Evaluation)
    why_applies: dict[str, Any] = {
        "evaluation_id": None,
        "evaluated_at": None,
        "system_result": "NOT_EVALUATED",
        "rule_code": None,
        "rule_title": None,
        "reasoning_summary": "Applicability has not yet been formally evaluated.",
        "configuration_snapshot": {},
    }
    if obligation.applicability_evaluation_id is not None:
        eval_record = db.execute(
            select(ApplicabilityEvaluation).where(
                ApplicabilityEvaluation.id == obligation.applicability_evaluation_id
            )
        ).scalar_one_or_none()
        if eval_record:
            why_applies["evaluation_id"] = str(eval_record.id)
            why_applies["evaluated_at"] = eval_record.evaluated_at.isoformat()
            why_applies["system_result"] = eval_record.system_result
            why_applies["configuration_snapshot"] = eval_record.configuration_snapshot
            rule = eval_record.rule
            if rule:
                why_applies["rule_code"] = rule.rule_code
                why_applies["rule_title"] = rule.title
            why_applies["reasoning_summary"] = (
                f"Evaluated with result '{eval_record.system_result}' based on asset configuration snapshot."
            )

    # Required action
    today = datetime.date.today()
    is_overdue = bool(obligation.due_date and obligation.due_date < today)
    required_action_dict: dict[str, Any] = {
        "description": obligation.required_action,
        "due_date": obligation.due_date.isoformat() if obligation.due_date else None,
        "is_overdue": is_overdue,
        "recurrence": obligation.recurrence,
        "responsible_role": obligation.responsible_role,
        "is_completed": obligation.completed_at is not None,
    }

    # Required evidence specs
    req_evidence = []
    if isinstance(obligation.evidence_requirements, list):
        req_evidence = obligation.evidence_requirements
    elif isinstance(obligation.evidence_requirements, dict):
        req_evidence = [obligation.evidence_requirements]

    # Provided evidence items
    evidence_items = list(
        db.execute(
            select(Evidence).where(
                Evidence.compliance_obligation_id == obligation.id,
                Evidence.organization_id == organization_id,
            )
        )
        .scalars()
        .all()
    )

    provided_evidence_list = []
    is_all_verified = True if evidence_items else False
    blockers: list[str] = []

    for item in evidence_items:
        file_count = len(item.files) if item.files else 0
        provided_evidence_list.append(
            {
                "id": str(item.id),
                "title": item.title,
                "evidence_type": item.evidence_type,
                "source": item.source,
                "status": item.status,
                "verification_status": item.verification_status,
                "verified_at": item.verified_at.isoformat() if item.verified_at else None,
                "verifier_user_id": str(item.verifier_user_id) if item.verifier_user_id else None,
                "rejection_reason": item.rejection_reason,
                "file_count": file_count,
            }
        )
        if item.verification_status == "REJECTED":
            blockers.append(
                f"Evidence '{item.title or item.id}' was REJECTED: {item.rejection_reason or 'No reason provided'}."
            )
            is_all_verified = False
        elif item.verification_status != "VERIFIED":
            is_all_verified = False

    # Identify domain blockers
    if obligation.status == ComplianceState.NOT_EVALUATED.value:
        blockers.append("Applicability evaluation has not been performed.")
    elif obligation.status == ComplianceState.BLOCKED.value:
        blockers.append(
            "Evaluation returned INSUFFICIENT_DATA (missing aircraft/component configuration records)."
        )
    elif obligation.status == ComplianceState.REVIEW_REQUIRED.value:
        blockers.append("Applicability determination flagged for authorized human review.")
    elif obligation.status == ComplianceState.NOT_APPLICABLE.value:
        blockers.append("Requirement is NOT APPLICABLE to this asset configuration.")
    elif obligation.status in {
        ComplianceState.DUE.value,
        ComplianceState.OVERDUE.value,
        ComplianceState.IN_PROGRESS.value,
    }:
        if not evidence_items:
            blockers.append("No verification evidence has been submitted yet.")
        elif not is_all_verified:
            blockers.append("Attached evidence is awaiting independent verification.")
        if is_overdue:
            blockers.append(f"Obligation is OVERDUE (past deadline {obligation.due_date}).")

    return ComplianceTraceabilityResponse(
        obligation_id=obligation.id,
        compliance_state=obligation.status,
        is_compliant=obligation.status == ComplianceState.COMPLIANT.value,
        requirement={
            "id": str(req.id),
            "requirement_number": req.requirement_number,
            "title": req.title,
            "authority": req.authority,
            "compliance_time": req.compliance_time,
        },
        asset=asset_dict,
        why_applies=why_applies,
        required_action=required_action_dict,
        required_evidence=req_evidence,
        provided_evidence=provided_evidence_list,
        is_verified=is_all_verified and obligation.status == ComplianceState.COMPLIANT.value,
        blockers=blockers,
    )


def get_compliance_overview(
    db: Session, *, organization_id: uuid.UUID
) -> ComplianceOverviewResponse:
    """Aggregate statistics across all compliance obligations for an organization."""
    obligations = list(
        db.execute(
            select(ComplianceObligation).where(
                ComplianceObligation.organization_id == organization_id
            )
        )
        .scalars()
        .all()
    )

    total = len(obligations)
    compliant = sum(1 for o in obligations if o.status == ComplianceState.COMPLIANT.value)
    due = sum(1 for o in obligations if o.status == ComplianceState.DUE.value)
    overdue = sum(1 for o in obligations if o.status == ComplianceState.OVERDUE.value)
    in_progress = sum(1 for o in obligations if o.status == ComplianceState.IN_PROGRESS.value)
    non_compliant = sum(1 for o in obligations if o.status == ComplianceState.NON_COMPLIANT.value)
    blocked = sum(1 for o in obligations if o.status == ComplianceState.BLOCKED.value)
    review_required = sum(1 for o in obligations if o.status == ComplianceState.REVIEW_REQUIRED.value)
    not_applicable = sum(1 for o in obligations if o.status == ComplianceState.NOT_APPLICABLE.value)

    applicable_count = total - not_applicable
    compliance_rate = (
        round((compliant / applicable_count) * 100.0, 1) if applicable_count > 0 else 100.0
    )

    return ComplianceOverviewResponse(
        total_obligations=total,
        applicable_count=applicable_count,
        compliant_count=compliant,
        due_count=due,
        overdue_count=overdue,
        in_progress_count=in_progress,
        non_compliant_count=non_compliant,
        blocked_count=blocked,
        review_required_count=review_required,
        not_applicable_count=not_applicable,
        compliance_rate_percent=compliance_rate,
    )
