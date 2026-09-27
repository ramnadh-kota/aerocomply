import datetime
from datetime import UTC
import uuid

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError
from app.models.aircraft import Aircraft
from app.models.asset import AssetType
from app.models.inspection_requirement import InspectionRequirement
from app.models.task import Task, TaskExecutionState
from app.models.user import User
from app.models.work_order import WorkOrder, WorkOrderStatus, WorkOrderType
from app.schemas.release_readiness import ReadinessStatus
from app.schemas.task import TaskCreateRequest, TaskUpdateRequest
from app.schemas.work_order import (
    WorkOrderAssignRequest,
    WorkOrderCancelRequest,
    WorkOrderCreateRequest,
    WorkOrderTransitionRequest,
    WorkOrderUpdateRequest,
)
from app.services import aircraft_service, asset_service
from app.services.asset_resolution import resolve_asset_id
from app.services.audit_service import record_audit_event
from app.services.limit_enforcement_service import check_work_order_creation_limit

_TASK_TERMINAL_STATE = TaskExecutionState.COMPLETED
_TASK_COMPLETABLE_FROM = {TaskExecutionState.PENDING, TaskExecutionState.IN_PROGRESS}

# Explicit state transition graph
_ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    WorkOrderStatus.DRAFT: {WorkOrderStatus.OPEN, WorkOrderStatus.CANCELLED},
    WorkOrderStatus.OPEN: {WorkOrderStatus.PLANNED, WorkOrderStatus.ASSIGNED, WorkOrderStatus.CANCELLED},
    WorkOrderStatus.PLANNED: {WorkOrderStatus.ASSIGNED, WorkOrderStatus.CANCELLED},
    WorkOrderStatus.ASSIGNED: {WorkOrderStatus.IN_PROGRESS, WorkOrderStatus.PLANNED, WorkOrderStatus.CANCELLED},
    WorkOrderStatus.IN_PROGRESS: {WorkOrderStatus.ON_HOLD, WorkOrderStatus.INSPECTION, WorkOrderStatus.CANCELLED},
    WorkOrderStatus.ON_HOLD: {WorkOrderStatus.IN_PROGRESS, WorkOrderStatus.CANCELLED},
    WorkOrderStatus.INSPECTION: {WorkOrderStatus.COMPLETED, WorkOrderStatus.IN_PROGRESS, WorkOrderStatus.CANCELLED},
    WorkOrderStatus.COMPLETED: {WorkOrderStatus.CLOSED},
    WorkOrderStatus.CLOSED: set(),
    WorkOrderStatus.CANCELLED: set(),
}


def _assert_user_in_organization(
    db: Session, *, organization_id: uuid.UUID, user_id: uuid.UUID
) -> User:
    user = db.execute(
        select(User).where(User.id == user_id, User.organization_id == organization_id)
    ).scalar_one_or_none()
    if user is None:
        raise NotFoundError("User does not belong to this organization")
    return user


def create_work_order(
    db: Session,
    *,
    organization_id: uuid.UUID,
    created_by_user_id: uuid.UUID | None,
    payload: WorkOrderCreateRequest,
) -> WorkOrder:
    check_work_order_creation_limit(db, organization_id=organization_id)

    aircraft_id = payload.aircraft_id
    asset_id = payload.asset_id
    if aircraft_id is not None:
        # aircraft_id is client-supplied; verify it belongs to this
        # organization before attaching a work order to it.
        aircraft = aircraft_service.get_aircraft(
            db, organization_id=organization_id, aircraft_id=aircraft_id
        )
        asset_id = resolve_asset_id(aircraft)
    else:
        asset = asset_service.get_asset(
            db, organization_id=organization_id, asset_id=asset_id
        )
        if asset.asset_type == AssetType.AIRCRAFT:
            aircraft = db.execute(
                select(Aircraft).where(
                    Aircraft.organization_id == organization_id,
                    Aircraft.asset_id == asset.id,
                )
            ).scalar_one_or_none()
            if aircraft is None:
                raise NotFoundError("Aircraft not found for asset")
            aircraft_id = aircraft.id

    if payload.assigned_to_user_id is not None:
        _assert_user_in_organization(
            db, organization_id=organization_id, user_id=payload.assigned_to_user_id
        )

    initial_status = payload.status
    if initial_status == WorkOrderStatus.ASSIGNED and payload.assigned_to_user_id is None:
        raise ConflictError("Work order in ASSIGNED status requires an assigned technician.")

    work_order = WorkOrder(
        organization_id=organization_id,
        aircraft_id=aircraft_id,
        asset_id=asset_id,
        work_order_number=payload.work_order_number,
        title=payload.title,
        description=payload.description,
        work_order_type=payload.work_order_type,
        maintenance_category=payload.maintenance_category,
        status=initial_status,
        priority=payload.priority,
        scheduled_start=payload.scheduled_start,
        scheduled_end=payload.scheduled_end,
        due_at=payload.due_at,
        estimated_hours=payload.estimated_hours,
        estimated_cost=payload.estimated_cost,
        assigned_to_user_id=payload.assigned_to_user_id,
        location=payload.location,
        source_type=payload.source_type,
        source_reference=payload.source_reference,
        compliance_required=payload.compliance_required,
        compliance_reference=payload.compliance_reference,
        created_by_user_id=created_by_user_id,
    )
    db.add(work_order)
    db.flush()

    record_audit_event(
        db,
        organization_id=organization_id,
        user_id=created_by_user_id,
        action="work_order.created",
        entity_type="WorkOrder",
        entity_id=work_order.id,
        metadata={
            "work_order_number": work_order.work_order_number,
            "status": work_order.status,
            "priority": work_order.priority,
            "work_order_type": work_order.work_order_type,
        },
    )

    db.commit()
    db.refresh(work_order)
    return work_order


def get_work_order(
    db: Session, *, organization_id: uuid.UUID, work_order_id: uuid.UUID
) -> WorkOrder:
    work_order = db.execute(
        select(WorkOrder).where(
            WorkOrder.id == work_order_id,
            WorkOrder.organization_id == organization_id,
            WorkOrder.deleted_at.is_(None),
        )
    ).scalar_one_or_none()
    if work_order is None:
        raise NotFoundError("Work order not found")
    return work_order


def list_work_orders(
    db: Session,
    *,
    organization_id: uuid.UUID,
    asset_id: uuid.UUID | None = None,
    aircraft_id: uuid.UUID | None = None,
    status: str | None = None,
    priority: str | None = None,
    work_order_type: str | None = None,
    assigned_to_user_id: uuid.UUID | None = None,
    search: str | None = None,
    overdue_only: bool = False,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[WorkOrder], int]:
    limit = max(1, min(limit, 100))
    offset = max(0, offset)

    base_query = select(WorkOrder).where(
        WorkOrder.organization_id == organization_id,
        WorkOrder.deleted_at.is_(None),
    )

    if asset_id is not None:
        base_query = base_query.where(WorkOrder.asset_id == asset_id)
    if aircraft_id is not None:
        base_query = base_query.where(WorkOrder.aircraft_id == aircraft_id)
    if status is not None and status != "ALL":
        base_query = base_query.where(WorkOrder.status == status)
    if priority is not None and priority != "ALL":
        base_query = base_query.where(WorkOrder.priority == priority)
    if work_order_type is not None and work_order_type != "ALL":
        base_query = base_query.where(WorkOrder.work_order_type == work_order_type)
    if assigned_to_user_id is not None:
        base_query = base_query.where(WorkOrder.assigned_to_user_id == assigned_to_user_id)
    if overdue_only:
        now = datetime.datetime.now(UTC)
        base_query = base_query.where(
            WorkOrder.due_at.is_not(None),
            WorkOrder.due_at < now,
            WorkOrder.status.not_in([WorkOrderStatus.COMPLETED, WorkOrderStatus.CLOSED, WorkOrderStatus.CANCELLED]),
        )
    if search and search.strip():
        term = f"%{search.strip().lower()}%"
        base_query = base_query.where(
            or_(
                func.lower(WorkOrder.work_order_number).like(term),
                func.lower(WorkOrder.title).like(term),
                func.lower(WorkOrder.description).like(term),
            )
        )

    count_stmt = select(func.count()).select_from(base_query.subquery())
    total = db.execute(count_stmt).scalar_one()

    stmt = (
        base_query.order_by(WorkOrder.created_at.desc(), WorkOrder.id.desc())
        .limit(limit)
        .offset(offset)
    )
    items = list(db.execute(stmt).scalars().all())
    return items, total


def update_work_order(
    db: Session,
    *,
    organization_id: uuid.UUID,
    work_order_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    payload: WorkOrderUpdateRequest,
) -> WorkOrder:
    work_order = get_work_order(db, organization_id=organization_id, work_order_id=work_order_id)

    if work_order.status in (WorkOrderStatus.CLOSED, WorkOrderStatus.CANCELLED):
        raise ConflictError(f"Cannot update a {work_order.status} work order.")

    update_data = payload.model_dump(exclude_unset=True)
    for field, val in update_data.items():
        setattr(work_order, field, val)

    record_audit_event(
        db,
        organization_id=organization_id,
        user_id=actor_user_id,
        action="work_order.updated",
        entity_type="WorkOrder",
        entity_id=work_order.id,
        metadata={"updated_fields": list(update_data.keys())},
    )

    db.add(work_order)
    db.commit()
    db.refresh(work_order)
    return work_order


def assign_work_order(
    db: Session,
    *,
    organization_id: uuid.UUID,
    work_order_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    payload: WorkOrderAssignRequest,
) -> WorkOrder:
    work_order = get_work_order(db, organization_id=organization_id, work_order_id=work_order_id)

    if work_order.status in (WorkOrderStatus.CLOSED, WorkOrderStatus.CANCELLED):
        raise ConflictError(f"Cannot assign a {work_order.status} work order.")

    technician = _assert_user_in_organization(
        db, organization_id=organization_id, user_id=payload.assigned_to_user_id
    )

    prev_assignee = work_order.assigned_to_user_id
    work_order.assigned_to_user_id = technician.id

    prev_status = work_order.status
    if work_order.status in (WorkOrderStatus.OPEN, WorkOrderStatus.PLANNED):
        work_order.status = WorkOrderStatus.ASSIGNED

    record_audit_event(
        db,
        organization_id=organization_id,
        user_id=actor_user_id,
        action="work_order.assigned",
        entity_type="WorkOrder",
        entity_id=work_order.id,
        metadata={
            "previous_assigned_to": str(prev_assignee) if prev_assignee else None,
            "assigned_to_user_id": str(technician.id),
            "previous_status": prev_status,
            "new_status": work_order.status,
        },
    )

    db.add(work_order)
    db.commit()
    db.refresh(work_order)
    return work_order


def transition_work_order(
    db: Session,
    *,
    organization_id: uuid.UUID,
    work_order_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    target_status: str,
    notes: str | None = None,
    reason: str | None = None,
) -> WorkOrder:
    work_order = get_work_order(db, organization_id=organization_id, work_order_id=work_order_id)
    current_status = work_order.status

    if current_status == target_status:
        return work_order

    allowed_targets = _ALLOWED_TRANSITIONS.get(current_status, set())
    if target_status not in allowed_targets:
        raise ConflictError(
            f"Invalid state transition from {current_status} to {target_status}. "
            f"Allowed transitions from {current_status}: {sorted(allowed_targets) or 'None (terminal)'}."
        )

    now = datetime.datetime.now(UTC)

    # Transition-specific gate validations
    if target_status == WorkOrderStatus.ASSIGNED:
        if work_order.assigned_to_user_id is None:
            raise ConflictError(
                "Cannot transition to ASSIGNED: Work order must have an assigned technician."
            )

    elif target_status == WorkOrderStatus.IN_PROGRESS:
        if work_order.assigned_to_user_id is None:
            raise ConflictError(
                "Cannot start work (IN_PROGRESS): Work order must have an assigned technician."
            )
        if work_order.actual_start is None:
            work_order.actual_start = now

    elif target_status == WorkOrderStatus.INSPECTION:
        # Precondition: all tasks on work order must be COMPLETED
        incomplete_tasks = list(
            db.execute(
                select(Task).where(
                    Task.organization_id == organization_id,
                    Task.work_order_id == work_order.id,
                    Task.execution_state != TaskExecutionState.COMPLETED,
                )
            )
            .scalars()
            .all()
        )
        if incomplete_tasks:
            raise ConflictError(
                f"Cannot transition to INSPECTION: {len(incomplete_tasks)} task(s) remain uncompleted."
            )

    elif target_status == WorkOrderStatus.COMPLETED:
        # Precondition: all inspection requirements must be satisfied
        inspections = list(
            db.execute(
                select(InspectionRequirement).where(
                    InspectionRequirement.organization_id == organization_id,
                    or_(
                        InspectionRequirement.work_order_id == work_order.id,
                        InspectionRequirement.task_id.in_(
                            select(Task.id).where(
                                Task.organization_id == organization_id,
                                Task.work_order_id == work_order.id,
                            )
                        ),
                    ),
                )
            )
            .scalars()
            .all()
        )
        from app.services.inspection_service import satisfies_completion_gate

        unsatisfied_inspections = [i for i in inspections if not satisfies_completion_gate(i.status)]
        if unsatisfied_inspections:
            raise ConflictError(
                f"Cannot complete work order: {len(unsatisfied_inspections)} inspection requirement(s) are unsatisfied."
            )
        work_order.completed_at = now
        if work_order.actual_end is None:
            work_order.actual_end = now

    elif target_status == WorkOrderStatus.CLOSED:
        # Precondition: Must be COMPLETED before CLOSED
        if current_status != WorkOrderStatus.COMPLETED:
            raise ConflictError("Work order must be COMPLETED before it can be CLOSED.")

        from app.services import release_readiness_service

        readiness = release_readiness_service.get_release_readiness_for_work_order(
            db, organization_id=organization_id, work_order_id=work_order.id
        )
        if readiness.status == "BLOCKED":
            reasons = "; ".join(b.description for b in readiness.blockers)
            raise ConflictError(
                f"Cannot close work order: Release readiness is BLOCKED ({reasons})."
            )
        work_order.closed_at = now

    elif target_status == WorkOrderStatus.CANCELLED:
        if not reason or len(reason.strip()) < 3:
            raise ConflictError(
                "A cancellation reason (at least 3 characters) is required to cancel a work order."
            )
        work_order.cancelled_at = now
        work_order.cancellation_reason = reason.strip()

    prev_status = work_order.status
    work_order.status = target_status

    record_audit_event(
        db,
        organization_id=organization_id,
        user_id=actor_user_id,
        action="work_order.transitioned",
        entity_type="WorkOrder",
        entity_id=work_order.id,
        metadata={
            "previous_status": prev_status,
            "new_status": target_status,
            "notes": notes,
            "reason": reason,
        },
    )

    db.add(work_order)
    db.commit()
    db.refresh(work_order)
    return work_order


def cancel_work_order(
    db: Session,
    *,
    organization_id: uuid.UUID,
    work_order_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    payload: WorkOrderCancelRequest,
) -> WorkOrder:
    return transition_work_order(
        db,
        organization_id=organization_id,
        work_order_id=work_order_id,
        actor_user_id=actor_user_id,
        target_status=WorkOrderStatus.CANCELLED,
        reason=payload.reason,
    )


def close_work_order(
    db: Session,
    *,
    organization_id: uuid.UUID,
    work_order_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
) -> WorkOrder:
    return transition_work_order(
        db,
        organization_id=organization_id,
        work_order_id=work_order_id,
        actor_user_id=actor_user_id,
        target_status=WorkOrderStatus.CLOSED,
    )


def complete_work_order(
    db: Session,
    *,
    organization_id: uuid.UUID,
    work_order_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
) -> WorkOrder:
    return transition_work_order(
        db,
        organization_id=organization_id,
        work_order_id=work_order_id,
        actor_user_id=actor_user_id,
        target_status=WorkOrderStatus.COMPLETED,
    )


# Task Management
def create_task(
    db: Session,
    *,
    organization_id: uuid.UUID,
    payload: TaskCreateRequest,
    actor_user_id: uuid.UUID | None = None,
) -> Task:
    if payload.work_order_id is None:
        raise ConflictError("work_order_id is required to create a task")

    work_order = get_work_order(db, organization_id=organization_id, work_order_id=payload.work_order_id)
    if work_order.status in (WorkOrderStatus.CLOSED, WorkOrderStatus.CANCELLED):
        raise ConflictError(f"Cannot add tasks to a {work_order.status} work order.")

    if payload.assigned_technician_user_id is not None:
        _assert_user_in_organization(
            db, organization_id=organization_id, user_id=payload.assigned_technician_user_id
        )

    task = Task(
        organization_id=organization_id,
        work_order_id=payload.work_order_id,
        task_number=payload.task_number,
        title=payload.title,
        description=payload.description,
        execution_state=payload.execution_state,
        assigned_technician_user_id=payload.assigned_technician_user_id,
        sequence=payload.sequence,
        estimated_hours=payload.estimated_hours,
        evidence_required=payload.evidence_required,
        notes=payload.notes,
    )
    db.add(task)
    db.flush()

    record_audit_event(
        db,
        organization_id=organization_id,
        user_id=actor_user_id,
        action="task.created",
        entity_type="Task",
        entity_id=task.id,
        metadata={"work_order_id": str(payload.work_order_id), "description": task.description},
    )

    db.commit()
    db.refresh(task)
    return task


def get_task(db: Session, *, organization_id: uuid.UUID, task_id: uuid.UUID) -> Task:
    task = db.execute(
        select(Task).where(Task.id == task_id, Task.organization_id == organization_id)
    ).scalar_one_or_none()
    if task is None:
        raise NotFoundError("Task not found")
    return task


def update_task(
    db: Session,
    *,
    organization_id: uuid.UUID,
    task_id: uuid.UUID,
    payload: TaskUpdateRequest,
    actor_user_id: uuid.UUID | None = None,
) -> Task:
    task = get_task(db, organization_id=organization_id, task_id=task_id)

    work_order = get_work_order(db, organization_id=organization_id, work_order_id=task.work_order_id)
    if work_order.status in (WorkOrderStatus.CLOSED, WorkOrderStatus.CANCELLED):
        raise ConflictError(f"Cannot update tasks on a {work_order.status} work order.")

    if payload.assigned_technician_user_id is not None:
        _assert_user_in_organization(
            db, organization_id=organization_id, user_id=payload.assigned_technician_user_id
        )

    update_data = payload.model_dump(exclude_unset=True)
    for field, val in update_data.items():
        setattr(task, field, val)

    record_audit_event(
        db,
        organization_id=organization_id,
        user_id=actor_user_id,
        action="task.updated",
        entity_type="Task",
        entity_id=task.id,
        metadata={"updated_fields": list(update_data.keys())},
    )

    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def complete_task(db: Session, task: Task, *, actor_user_id: uuid.UUID | None) -> Task:
    """Mark a task's execution_state COMPLETED."""
    if task.execution_state == _TASK_TERMINAL_STATE:
        raise ConflictError("Task is already completed")
    if task.execution_state not in _TASK_COMPLETABLE_FROM:
        raise ConflictError(f"Cannot complete task from execution_state={task.execution_state!r}")

    now = datetime.datetime.now(UTC)
    task.execution_state = _TASK_TERMINAL_STATE
    task.completed_at = now

    record_audit_event(
        db,
        organization_id=task.organization_id,
        user_id=actor_user_id,
        action="task.completed",
        entity_type="Task",
        entity_id=task.id,
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def list_tasks_for_work_order(
    db: Session, *, organization_id: uuid.UUID, work_order_id: uuid.UUID
) -> list[Task]:
    return list(
        db.execute(
            select(Task)
            .join(WorkOrder, WorkOrder.id == Task.work_order_id)
            .where(
                Task.organization_id == organization_id,
                Task.work_order_id == work_order_id,
                WorkOrder.deleted_at.is_(None),
            )
            .order_by(Task.sequence.asc(), Task.created_at.asc())
        )
        .scalars()
        .all()
    )
