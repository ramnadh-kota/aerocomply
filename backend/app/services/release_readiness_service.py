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
    not satisfy the completion gate (Evidence has no separate `required`
    boolean column today — see app/models/evidence.py — so every existing
    Evidence row is treated as required; a task with zero Evidence rows is
    not, by itself, an evidence blocker, since there is nothing recorded to
    judge).
  - INSPECTION: an InspectionRequirement linked to this work order (directly
    via work_order_id, or via one of its tasks' task_id) does not satisfy the
    completion gate.
  - TASK_EXECUTION: a Task on this work order is not in the terminal
    "COMPLETED" execution_state. Task.execution_state is a free-form string
    column with no enum in this schema (see app/models/task.py); COMPLETED is
    treated as the sole terminal/done value, consistent with the COMPLETED
    naming used by InspectionRequirementStatus and EvidenceStatus elsewhere
    in this codebase.

Categories the frontend mock (frontend/lib/mock/ai/analytics.ts) shows but
this backend does not yet track in any model — authorization sign-off and
material/parts availability — are deliberately NOT implemented here; see
`data_completeness` on the returned ReleaseReadiness.
"""
import uuid

from sqlalchemy import ColumnElement, or_, select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.models.evidence import Evidence, EvidenceStatus
from app.models.inspection_requirement import InspectionRequirement, InspectionRequirementStatus
from app.models.task import Task
from app.models.work_order import WorkOrder
from app.schemas.release_readiness import Blocker, ReadinessStatus, ReleaseReadiness
from app.services.evidence_service import satisfies_completion_gate as evidence_satisfies_gate
from app.services.inspection_service import (
    satisfies_completion_gate as inspection_satisfies_gate,
)

_TASK_TERMINAL_STATE = "COMPLETED"

_DATA_COMPLETENESS = (
    "Authorization, material, and regulatory blocker categories are not yet "
    "backend-tracked; this evaluation covers evidence, inspection, and task "
    "execution status only."
)


def get_release_readiness_for_work_order(
    db: Session, *, organization_id: uuid.UUID, work_order_id: uuid.UUID
) -> ReleaseReadiness:
    work_order = db.execute(
        select(WorkOrder).where(
            WorkOrder.id == work_order_id, WorkOrder.organization_id == organization_id
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

    status: ReadinessStatus = "BLOCKED" if blockers else "READY"

    return ReleaseReadiness(
        work_order_id=work_order.id,
        status=status,
        blockers=blockers,
        data_completeness=_DATA_COMPLETENESS,
    )
