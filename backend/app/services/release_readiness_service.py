"""Aggregate release-readiness for a work order.

Pure aggregation layer: this module never re-implements the evidence gate
(app/services/evidence_service.py::satisfies_completion_gate) or the RII
independence / inspection-completion rule
(app/services/inspection_service.py::satisfies_completion_gate). It only
reads Task/Evidence/InspectionRequirement rows for a work order and asks the
existing service functions whether each one clears its own gate.

Blocker categories implemented, each grounded in a real, queryable model
field:
  - EVIDENCE: an Evidence row exists for a task on this work order but does
    not satisfy the completion gate, OR a task has Task.evidence_required=True
    (M17.6A, app/models/task.py) and has zero Evidence rows at all yet. A
    task with evidence_required=False and zero Evidence rows is not, by
    itself, an evidence blocker, since there is nothing recorded to judge and
    nothing declaring it mandatory.
  - INSPECTION: an InspectionRequirement linked to this work order (directly
    via work_order_id, or via one of its tasks' task_id) does not satisfy the
    completion gate.
  - TASK_EXECUTION: a Task on this work order is not in the terminal
    "COMPLETED" execution_state. Task.execution_state is a free-form string
    column with no enum in this schema (see app/models/task.py); COMPLETED is
    treated as the sole terminal/done value, consistent with the COMPLETED
    naming used by InspectionRequirementStatus and EvidenceStatus elsewhere
    in this codebase.
  - MATERIAL (M17.6A): a PartRequirement linked to this work order has
    fulfilled_quantity < required_quantity and its status is not FULFILLED or
    CANCELLED (app/models/part_requirement.py). Quantity semantics are read
    directly from those two columns -- no new semantics invented.
  - COMPLIANCE (M17.6A): the work order's asset (WorkOrder.asset_id) has a
    ComplianceAssessment whose *most recent* (by evaluated_at, ties broken by
    created_at) assessment per RegulatoryRequirement is NON_COMPLIANT. An
    older NON_COMPLIANT row superseded by a newer COMPLIANT/PENDING one never
    blocks -- only the latest determination per requirement is evaluated,
    which also means REVIEW_REQUIRED/UNKNOWN (pending-style) latest
    assessments do NOT block, matching this codebase's existing convention
    of not treating "unknown" as either compliant or non-compliant on its
    own. Work orders with no asset_id (e.g. drone-only work orders with
    neither aircraft_id nor asset_id set) simply have no COMPLIANCE
    blockers, since there is no asset to evaluate.
  - FINDING (M21.1): a Finding (app/models/finding.py) whose status is not
    CLOSED (i.e. OPEN or IN_PROGRESS) and that is linked to this work order
    -- directly via Finding.work_order_id, or transitively via the same
    asset the work order resolves to (Finding.asset_id == WorkOrder.asset_id
    or Finding.aircraft_id == WorkOrder.aircraft_id). Severity is never used
    to decide whether a Finding blocks (no existing precedent in this
    codebase for a severity-based split); severity is only surfaced in the
    blocker description for explainability. A CLOSED finding never blocks.
    One blocker per unresolved Finding (never collapsed), fetched in a
    single query -- no query-per-asset/per-task loop.

Authorization sign-off is the one category the frontend mock
(frontend/lib/mock/ai/analytics.ts) shows that this backend still does not
track in any model; see `data_completeness` on the returned ReleaseReadiness.
"""
import uuid

from sqlalchemy import ColumnElement, or_, select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.models.compliance import ComplianceAssessment, ComplianceAssessmentStatus
from app.models.evidence import Evidence, EvidenceStatus
from app.models.finding import Finding, FindingStatus
from app.models.inspection_requirement import InspectionRequirement, InspectionRequirementStatus
from app.models.part_requirement import PartRequirement, PartRequirementStatus
from app.models.task import Task
from app.models.work_order import WorkOrder
from app.schemas.release_readiness import Blocker, ReadinessStatus, ReleaseReadiness
from app.services.evidence_service import satisfies_completion_gate as evidence_satisfies_gate
from app.services.inspection_service import (
    satisfies_completion_gate as inspection_satisfies_gate,
)

_TASK_TERMINAL_STATE = "COMPLETED"

# PartRequirement statuses that mean the requirement is fully settled and
# should never block release, regardless of quantity bookkeeping.
_PART_REQUIREMENT_SETTLED_STATUSES = {
    PartRequirementStatus.FULFILLED,
    PartRequirementStatus.CANCELLED,
}

_DATA_COMPLETENESS = (
    "Authorization sign-off is not yet backend-tracked; this evaluation "
    "covers evidence, inspection, task execution, material, and compliance "
    "status."
)


def get_release_readiness_for_work_order(
    db: Session, *, organization_id: uuid.UUID, work_order_id: uuid.UUID
) -> ReleaseReadiness:
    work_order = db.execute(
        select(WorkOrder).where(
            WorkOrder.id == work_order_id,
            WorkOrder.organization_id == organization_id,
            WorkOrder.deleted_at.is_(None),
        )
    ).scalar_one_or_none()
    if work_order is None:
        raise NotFoundError("Work order not found")

    tasks = list(
        db.execute(
            select(Task).where(
                Task.organization_id == organization_id, Task.work_order_id == work_order_id
            )
        ).scalars().all()
    )
    task_ids = [t.id for t in tasks]

    blockers: list[Blocker] = []

    # TASK_EXECUTION blockers.
    for task in tasks:
        if task.execution_state != _TASK_TERMINAL_STATE:
            blockers.append(
                Blocker(
                    category="TASK_EXECUTION",
                    description=(
                        f"Task is in execution_state={task.execution_state!r}, "
                        f"not {_TASK_TERMINAL_STATE!r}"
                    ),
                    related_record_id=task.id,
                )
            )

    # EVIDENCE blockers: every Evidence row for a task on this work order that
    # does not satisfy the completion gate.
    if task_ids:
        evidence_rows = list(
            db.execute(
                select(Evidence).where(
                    Evidence.organization_id == organization_id,
                    Evidence.task_id.in_(task_ids),
                )
            ).scalars().all()
        )
    else:
        evidence_rows = []
    for evidence in evidence_rows:
        if not evidence_satisfies_gate(EvidenceStatus(evidence.status)):
            blockers.append(
                Blocker(
                    category="EVIDENCE",
                    description=f"Evidence is in status={evidence.status!r}, not ACCEPTED",
                    related_record_id=evidence.id,
                )
            )

    # EVIDENCE blockers (M17.6A): tasks that declare evidence_required=True
    # but have zero Evidence rows at all yet -- otherwise invisible to the
    # check above, since there is nothing to inspect the status of.
    tasks_with_evidence = {evidence.task_id for evidence in evidence_rows}
    for task in tasks:
        if task.evidence_required and task.id not in tasks_with_evidence:
            blockers.append(
                Blocker(
                    category="EVIDENCE",
                    description="Task requires evidence but none has been submitted yet",
                    related_record_id=task.id,
                )
            )

    # INSPECTION blockers: requirements linked to this work order directly or
    # via one of its tasks.
    conditions: list[ColumnElement[bool]] = [InspectionRequirement.work_order_id == work_order_id]
    if task_ids:
        conditions.append(InspectionRequirement.task_id.in_(task_ids))
    requirement_rows = list(
        db.execute(
            select(InspectionRequirement).where(
                InspectionRequirement.organization_id == organization_id,
                or_(*conditions),
            )
        ).scalars().all()
    )
    for requirement in requirement_rows:
        if not inspection_satisfies_gate(InspectionRequirementStatus(requirement.status)):
            blockers.append(
                Blocker(
                    category="INSPECTION",
                    description=(
                        f"Inspection requirement is in status={requirement.status!r}, "
                        "not COMPLETED/NOT_REQUIRED"
                    ),
                    related_record_id=requirement.id,
                )
            )

    # MATERIAL blockers (M17.6A): outstanding PartRequirement rows for this
    # work order.
    part_requirements = list(
        db.execute(
            select(PartRequirement).where(
                PartRequirement.organization_id == organization_id,
                PartRequirement.work_order_id == work_order_id,
            )
        ).scalars().all()
    )
    for part_requirement in part_requirements:
        if part_requirement.status in _PART_REQUIREMENT_SETTLED_STATUSES:
            continue
        if part_requirement.fulfilled_quantity < part_requirement.required_quantity:
            blockers.append(
                Blocker(
                    category="MATERIAL",
                    description=(
                        f"Part requirement is short: fulfilled_quantity="
                        f"{part_requirement.fulfilled_quantity} of required_quantity="
                        f"{part_requirement.required_quantity} "
                        f"(status={part_requirement.status!r})"
                    ),
                    related_record_id=part_requirement.id,
                )
            )

    # COMPLIANCE blockers (M17.6A): the work order's asset has a NON_COMPLIANT
    # *latest* assessment for some regulatory requirement. Only evaluated
    # when the work order actually resolves to an asset.
    if work_order.asset_id is not None:
        assessments = list(
            db.execute(
                select(ComplianceAssessment).where(
                    ComplianceAssessment.organization_id == organization_id,
                    ComplianceAssessment.asset_id == work_order.asset_id,
                )
            ).scalars().all()
        )
        latest_by_requirement: dict[uuid.UUID, ComplianceAssessment] = {}
        for assessment in assessments:
            current = latest_by_requirement.get(assessment.requirement_id)
            if current is None:
                latest_by_requirement[assessment.requirement_id] = assessment
                continue
            current_key = (current.evaluated_at, current.created_at)
            candidate_key = (assessment.evaluated_at, assessment.created_at)
            if candidate_key > current_key:
                latest_by_requirement[assessment.requirement_id] = assessment
        for assessment in latest_by_requirement.values():
            if assessment.status == ComplianceAssessmentStatus.NON_COMPLIANT:
                blockers.append(
                    Blocker(
                        category="COMPLIANCE",
                        description=(
                            "Latest compliance assessment for this asset is "
                            f"NON_COMPLIANT (requirement_id={assessment.requirement_id})"
                        ),
                        related_record_id=assessment.id,
                    )
                )

    # FINDING blockers (M21.1): unresolved Findings linked to this work order
    # directly, or via the same asset/aircraft the work order resolves to.
    # Single query, no per-asset loop.
    finding_conditions: list[ColumnElement[bool]] = [Finding.work_order_id == work_order_id]
    if work_order.asset_id is not None:
        finding_conditions.append(Finding.asset_id == work_order.asset_id)
    if work_order.aircraft_id is not None:
        finding_conditions.append(Finding.aircraft_id == work_order.aircraft_id)
    findings = list(
        db.execute(
            select(Finding).where(
                Finding.organization_id == organization_id,
                Finding.status != FindingStatus.CLOSED,
                or_(*finding_conditions),
            )
        ).scalars().all()
    )
    for finding in findings:
        blockers.append(
            Blocker(
                category="FINDING",
                description=(
                    f"Unresolved finding ({finding.severity}): {finding.title!r} "
                    f"(status={finding.status!r})"
                ),
                related_record_id=finding.id,
            )
        )

    status: ReadinessStatus = "BLOCKED" if blockers else "READY"

    return ReleaseReadiness(
        work_order_id=work_order.id,
        status=status,
        blockers=blockers,
        data_completeness=_DATA_COMPLETENESS,
    )
