import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError
from app.models.aircraft import Aircraft
from app.models.asset import AssetType
from app.models.task import Task
from app.models.work_order import WorkOrder
from app.schemas.task import TaskCreateRequest
from app.schemas.work_order import (
    WorkOrderCreateRequest,
    WorkOrderDeleteReasonCode,
    WorkOrderRestoreReasonCode,
)
from app.services import aircraft_service, asset_service
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
    db: Session,
    *,
    organization_id: uuid.UUID,
    work_order_id: uuid.UUID,
    include_deleted: bool = True,
) -> WorkOrder:
    """include_deleted defaults to True so every existing caller (task/part
    requirement/inspection/procurement/deferred-item creation, assessment
    engine, AI tools, Lisa entity resolution, dashboards) keeps its current
    behavior unchanged -- child-mutation guards against a deleted WorkOrder
    are a deliberately separate, later slice (see the WorkOrder lifecycle
    architecture decision report), not an incidental side effect of this
    parameter. Only the tenant-facing GET route and the delete/restore
    lifecycle actions below pass include_deleted explicitly.
    """
    query = select(WorkOrder).where(
        WorkOrder.id == work_order_id, WorkOrder.organization_id == organization_id
    )
    if not include_deleted:
        query = query.where(WorkOrder.deleted_at.is_(None))
    work_order = db.execute(query).scalar_one_or_none()
    if work_order is None:
        raise NotFoundError("Work order not found")
    return work_order


def list_work_orders(
    db: Session,
    *,
    organization_id: uuid.UUID,
    asset_id: uuid.UUID | None = None,
    aircraft_id: uuid.UUID | None = None,
    include_deleted: bool = True,
) -> list[WorkOrder]:
    """include_deleted defaults to True for the same reason as
    get_work_order above -- existing callers (assessment engine, Lisa,
    proactive/control-center dashboards) are unaffected by this slice.
    Only the tenant-facing GET route passes include_deleted=False."""
    query = select(WorkOrder).where(WorkOrder.organization_id == organization_id)
    if asset_id is not None:
        query = query.where(WorkOrder.asset_id == asset_id)
    if aircraft_id is not None:
        query = query.where(WorkOrder.aircraft_id == aircraft_id)
    if not include_deleted:
        query = query.where(WorkOrder.deleted_at.is_(None))
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


def soft_delete_work_order(
    db: Session,
    *,
    organization_id: uuid.UUID,
    work_order_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    reason_code: WorkOrderDeleteReasonCode,
    note: str | None = None,
) -> WorkOrder:
    """ACTIVE -> DELETED. deleted_at IS NULL is the only lifecycle-state
    signal (see LifecycleMixin, app/db/base.py) -- WorkOrder.status is never
    touched here. Tenant scoping uses include_deleted=True so a
    cross-tenant work_order_id and an already-deleted one both reach this
    function identically to a nonexistent one from another org's
    perspective; the two cases are then told apart only by whether the row
    was found at all (NotFoundError, mapped to 404) vs. found but already
    deleted (ConflictError, mapped to 409) -- never a distinguishable error
    for tenant ownership.
    """
    work_order = get_work_order(
        db, organization_id=organization_id, work_order_id=work_order_id, include_deleted=True
    )
    if work_order.deleted_at is not None:
        raise ConflictError("Work order is already deleted")

    work_order.deleted_at = datetime.now(UTC)
    work_order.deleted_by = actor_user_id

    record_audit_event(
        db,
        organization_id=organization_id,
        user_id=actor_user_id,
        action="work_order.deleted",
        entity_type="WorkOrder",
        entity_id=work_order.id,
        metadata={
            "lifecycle_transition": "ACTIVE->DELETED",
            "reason_code": reason_code,
            "note": note,
            "status_snapshot": work_order.status,
        },
    )

    db.add(work_order)
    db.commit()
    db.refresh(work_order)
    return work_order


def restore_work_order(
    db: Session,
    *,
    organization_id: uuid.UUID,
    work_order_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    reason_code: WorkOrderRestoreReasonCode,
    note: str | None = None,
) -> WorkOrder:
    """DELETED -> ACTIVE. WorkOrder.status is left exactly as it was at
    delete time -- restore never re-derives or resets it. deleted_by is
    cleared alongside deleted_at (the most recent transition's actor moves
    to restored_by); the full delete/restore history lives in the audit
    trail (work_order.deleted/work_order.restored events), not in these
    columns, matching the approved lifecycle contract.
    """
    work_order = get_work_order(
        db, organization_id=organization_id, work_order_id=work_order_id, include_deleted=True
    )
    if work_order.deleted_at is None:
        raise ConflictError("Work order is not deleted")

    work_order.deleted_at = None
    work_order.deleted_by = None
    work_order.restored_at = datetime.now(UTC)
    work_order.restored_by = actor_user_id

    record_audit_event(
        db,
        organization_id=organization_id,
        user_id=actor_user_id,
        action="work_order.restored",
        entity_type="WorkOrder",
        entity_id=work_order.id,
        metadata={
            "lifecycle_transition": "DELETED->ACTIVE",
            "reason_code": reason_code,
            "note": note,
            "status_snapshot": work_order.status,
        },
    )

    db.add(work_order)
    db.commit()
    db.refresh(work_order)
    return work_order
