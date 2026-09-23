import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError
from app.models.aircraft import Aircraft
from app.models.asset import AssetType
from app.models.task import Task
from app.models.work_order import WorkOrder
from app.schemas.task import TaskCreateRequest
from app.schemas.work_order import WorkOrderCreateRequest
from app.services import aircraft_service
from app.services import asset_service
from app.services.asset_resolution import resolve_asset_id
from app.services.audit_service import record_audit_event

_TASK_TERMINAL_STATE = "COMPLETED"

# States a task may legally complete from. A task with no recorded execution
# yet (PENDING) or one actively being worked (IN_PROGRESS) may be marked
# complete; COMPLETED itself is terminal (no duplicate completion), and there
# is no other execution_state value in use today (see app/models/task.py —
# execution_state is a free-form string with "PENDING" as the only default).
_TASK_COMPLETABLE_FROM = {"PENDING", "IN_PROGRESS"}


def create_work_order(
    db: Session,
    *,
    organization_id: uuid.UUID,
    created_by_user_id: uuid.UUID | None,
    payload: WorkOrderCreateRequest,
) -> WorkOrder:
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

    work_order = WorkOrder(
        organization_id=organization_id,
        aircraft_id=aircraft_id,
        asset_id=asset_id,
        work_order_number=payload.work_order_number,
        status=payload.status,
        priority=payload.priority,
        created_by_user_id=created_by_user_id,
    )
    db.add(work_order)
    db.commit()
    db.refresh(work_order)
    return work_order


def get_work_order(
    db: Session, *, organization_id: uuid.UUID, work_order_id: uuid.UUID
) -> WorkOrder:
    work_order = db.execute(
        select(WorkOrder).where(
            WorkOrder.id == work_order_id, WorkOrder.organization_id == organization_id
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
) -> list[WorkOrder]:
    query = select(WorkOrder).where(WorkOrder.organization_id == organization_id)
    if asset_id is not None:
        query = query.where(WorkOrder.asset_id == asset_id)
    if aircraft_id is not None:
        query = query.where(WorkOrder.aircraft_id == aircraft_id)
    return list(db.execute(query).scalars().all())


def create_task(db: Session, *, organization_id: uuid.UUID, payload: TaskCreateRequest) -> Task:
    # Confirm the parent work order belongs to this tenant before creating the task.
    get_work_order(db, organization_id=organization_id, work_order_id=payload.work_order_id)

    task = Task(
        organization_id=organization_id,
        work_order_id=payload.work_order_id,
        description=payload.description,
        execution_state=payload.execution_state,
    )
    db.add(task)
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


def complete_task(db: Session, task: Task, *, actor_user_id: uuid.UUID | None) -> Task:
    """Mark a task's execution_state COMPLETED.

    This is deliberately narrow: it only records that the work itself was
    executed. It never re-implements or short-circuits the separate
    Evidence/Inspection gates that release_readiness_service checks — a
    completed task does not by itself mean the aircraft is
    airworthy/released, only that this one execution step is done.
    """
    if task.execution_state == _TASK_TERMINAL_STATE:
        raise ConflictError("Task is already completed")
    if task.execution_state not in _TASK_COMPLETABLE_FROM:
        raise ConflictError(f"Cannot complete task from execution_state={task.execution_state!r}")

    task.execution_state = _TASK_TERMINAL_STATE
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
            select(Task).where(
                Task.organization_id == organization_id, Task.work_order_id == work_order_id
            )
        )
        .scalars()
        .all()
    )
