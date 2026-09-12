import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.models.task import Task
from app.models.work_order import WorkOrder
from app.schemas.task import TaskCreateRequest
from app.schemas.work_order import WorkOrderCreateRequest
from app.services import aircraft_service


def create_work_order(
    db: Session,
    *,
    organization_id: uuid.UUID,
    created_by_user_id: uuid.UUID | None,
    payload: WorkOrderCreateRequest,
) -> WorkOrder:
    # aircraft_id is client-supplied; verify it belongs to this organization
    # before attaching a work order to it (cross-tenant IDOR otherwise).
    aircraft_service.get_aircraft(
        db, organization_id=organization_id, aircraft_id=payload.aircraft_id
    )

    work_order = WorkOrder(
        organization_id=organization_id,
        aircraft_id=payload.aircraft_id,
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


def list_work_orders(db: Session, *, organization_id: uuid.UUID) -> list[WorkOrder]:
    return list(
        db.execute(
            select(WorkOrder).where(WorkOrder.organization_id == organization_id)
        ).scalars().all()
    )


def create_task(
    db: Session, *, organization_id: uuid.UUID, payload: TaskCreateRequest
) -> Task:
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


def list_tasks_for_work_order(
    db: Session, *, organization_id: uuid.UUID, work_order_id: uuid.UUID
) -> list[Task]:
    return list(
        db.execute(
            select(Task).where(
                Task.organization_id == organization_id, Task.work_order_id == work_order_id
            )
        ).scalars().all()
    )
