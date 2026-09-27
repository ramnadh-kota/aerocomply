import uuid

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.core.deps import get_db_session, require_any_permission, require_feature, require_permission
from app.core.errors import NotFoundError
from app.core.permissions import Permission
from app.schemas.auth import CurrentUser
from app.schemas.deletion import WorkOrderDeleteRequest
from app.schemas.task import TaskCreateRequest, TaskResponse, TaskUpdateRequest
from app.schemas.work_order import (
    WorkOrderAssignRequest,
    WorkOrderCancelRequest,
    WorkOrderCreateRequest,
    WorkOrderResponse,
    WorkOrderTransitionRequest,
    WorkOrderUpdateRequest,
)
from app.services import deletion_service, work_order_service

router = APIRouter(prefix="/work-orders", tags=["work-orders"])


@router.post("", response_model=WorkOrderResponse, status_code=201)
def create_work_order(
    payload: WorkOrderCreateRequest,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.AIRCRAFT_WRITE)),
    _entitled: CurrentUser = Depends(require_feature("work_order_management")),
) -> WorkOrderResponse:
    work_order = work_order_service.create_work_order(
        db,
        organization_id=current_user.organization_id,
        created_by_user_id=current_user.id,
        payload=payload,
    )
    return WorkOrderResponse.model_validate(work_order)


@router.get("", response_model=list[WorkOrderResponse])
def list_work_orders(
    response: Response,
    asset_id: uuid.UUID | None = None,
    aircraft_id: uuid.UUID | None = None,
    status: str | None = None,
    priority: str | None = None,
    work_order_type: str | None = None,
    assigned_to_user_id: uuid.UUID | None = None,
    search: str | None = None,
    overdue_only: bool = False,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.AIRCRAFT_READ)),
    _entitled: CurrentUser = Depends(require_feature("work_order_management")),
) -> list[WorkOrderResponse]:
    items, total = work_order_service.list_work_orders(
        db,
        organization_id=current_user.organization_id,
        asset_id=asset_id,
        aircraft_id=aircraft_id,
        status=status,
        priority=priority,
        work_order_type=work_order_type,
        assigned_to_user_id=assigned_to_user_id,
        search=search,
        overdue_only=overdue_only,
        limit=limit,
        offset=offset,
    )
    response.headers["X-Total-Count"] = str(total)
    return [WorkOrderResponse.model_validate(w) for w in items]


@router.get("/{work_order_id}", response_model=WorkOrderResponse)
def get_work_order(
    work_order_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.AIRCRAFT_READ)),
    _entitled: CurrentUser = Depends(require_feature("work_order_management")),
) -> WorkOrderResponse:
    work_order = work_order_service.get_work_order(
        db, organization_id=current_user.organization_id, work_order_id=work_order_id
    )
    return WorkOrderResponse.model_validate(work_order)


@router.patch("/{work_order_id}", response_model=WorkOrderResponse)
def update_work_order(
    work_order_id: uuid.UUID,
    payload: WorkOrderUpdateRequest,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.AIRCRAFT_WRITE)),
    _entitled: CurrentUser = Depends(require_feature("work_order_management")),
) -> WorkOrderResponse:
    work_order = work_order_service.update_work_order(
        db,
        organization_id=current_user.organization_id,
        work_order_id=work_order_id,
        actor_user_id=current_user.id,
        payload=payload,
    )
    return WorkOrderResponse.model_validate(work_order)


@router.post("/{work_order_id}/assign", response_model=WorkOrderResponse)
def assign_work_order(
    work_order_id: uuid.UUID,
    payload: WorkOrderAssignRequest,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.AIRCRAFT_WRITE)),
    _entitled: CurrentUser = Depends(require_feature("work_order_management")),
) -> WorkOrderResponse:
    work_order = work_order_service.assign_work_order(
        db,
        organization_id=current_user.organization_id,
        work_order_id=work_order_id,
        actor_user_id=current_user.id,
        payload=payload,
    )
    return WorkOrderResponse.model_validate(work_order)


@router.post("/{work_order_id}/transition", response_model=WorkOrderResponse)
def transition_work_order(
    work_order_id: uuid.UUID,
    payload: WorkOrderTransitionRequest,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(
        require_any_permission(Permission.AIRCRAFT_WRITE, Permission.TECHNICIAN_WRITE)
    ),
    _entitled: CurrentUser = Depends(require_feature("work_order_management")),
) -> WorkOrderResponse:
    work_order = work_order_service.transition_work_order(
        db,
        organization_id=current_user.organization_id,
        work_order_id=work_order_id,
        actor_user_id=current_user.id,
        target_status=payload.target_status,
        notes=payload.notes,
        reason=payload.reason,
    )
    return WorkOrderResponse.model_validate(work_order)


@router.post("/{work_order_id}/complete", response_model=WorkOrderResponse)
def complete_work_order(
    work_order_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(
        require_any_permission(Permission.AIRCRAFT_WRITE, Permission.TECHNICIAN_WRITE)
    ),
    _entitled: CurrentUser = Depends(require_feature("work_order_management")),
) -> WorkOrderResponse:
    work_order = work_order_service.complete_work_order(
        db,
        organization_id=current_user.organization_id,
        work_order_id=work_order_id,
        actor_user_id=current_user.id,
    )
    return WorkOrderResponse.model_validate(work_order)


@router.post("/{work_order_id}/close", response_model=WorkOrderResponse)
def close_work_order(
    work_order_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.AIRCRAFT_WRITE)),
    _entitled: CurrentUser = Depends(require_feature("work_order_management")),
) -> WorkOrderResponse:
    work_order = work_order_service.close_work_order(
        db,
        organization_id=current_user.organization_id,
        work_order_id=work_order_id,
        actor_user_id=current_user.id,
    )
    return WorkOrderResponse.model_validate(work_order)


@router.post("/{work_order_id}/cancel", response_model=WorkOrderResponse)
def cancel_work_order(
    work_order_id: uuid.UUID,
    payload: WorkOrderCancelRequest,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.AIRCRAFT_WRITE)),
    _entitled: CurrentUser = Depends(require_feature("work_order_management")),
) -> WorkOrderResponse:
    work_order = work_order_service.cancel_work_order(
        db,
        organization_id=current_user.organization_id,
        work_order_id=work_order_id,
        actor_user_id=current_user.id,
        payload=payload,
    )
    return WorkOrderResponse.model_validate(work_order)


@router.delete("/{work_order_id}", response_model=WorkOrderResponse)
def delete_work_order(
    work_order_id: uuid.UUID,
    reason: str | None = Query(default=None, max_length=500),
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.AIRCRAFT_WRITE)),
    _entitled: CurrentUser = Depends(require_feature("work_order_management")),
) -> WorkOrderResponse:
    work_order = deletion_service.soft_delete_work_order(
        db,
        organization_id=current_user.organization_id,
        actor_user_id=current_user.id,
        work_order_id=work_order_id,
        payload=WorkOrderDeleteRequest(reason=reason),
    )
    return WorkOrderResponse.model_validate(work_order)


# Task routes
@router.post("/{work_order_id}/tasks", response_model=TaskResponse, status_code=201)
def create_task(
    work_order_id: uuid.UUID,
    payload: TaskCreateRequest,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.AIRCRAFT_WRITE)),
    _entitled: CurrentUser = Depends(require_feature("work_order_management")),
) -> TaskResponse:
    payload = payload.model_copy(update={"work_order_id": work_order_id})
    task = work_order_service.create_task(
        db,
        organization_id=current_user.organization_id,
        actor_user_id=current_user.id,
        payload=payload,
    )
    return TaskResponse.model_validate(task)


@router.patch("/{work_order_id}/tasks/{task_id}", response_model=TaskResponse)
def update_task(
    work_order_id: uuid.UUID,
    task_id: uuid.UUID,
    payload: TaskUpdateRequest,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(
        require_any_permission(Permission.AIRCRAFT_WRITE, Permission.TECHNICIAN_WRITE)
    ),
    _entitled: CurrentUser = Depends(require_feature("work_order_management")),
) -> TaskResponse:
    task = work_order_service.get_task(
        db, organization_id=current_user.organization_id, task_id=task_id
    )
    if task.work_order_id != work_order_id:
        raise NotFoundError("Task not found on this work order")
    updated_task = work_order_service.update_task(
        db,
        organization_id=current_user.organization_id,
        task_id=task_id,
        actor_user_id=current_user.id,
        payload=payload,
    )
    return TaskResponse.model_validate(updated_task)


@router.post("/{work_order_id}/tasks/{task_id}/complete", response_model=TaskResponse)
def complete_task(
    work_order_id: uuid.UUID,
    task_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(
        require_any_permission(Permission.AIRCRAFT_WRITE, Permission.TECHNICIAN_WRITE)
    ),
    _entitled: CurrentUser = Depends(require_feature("work_order_management")),
) -> TaskResponse:
    task = work_order_service.get_task(
        db, organization_id=current_user.organization_id, task_id=task_id
    )
    if task.work_order_id != work_order_id:
        raise NotFoundError("Task not found on this work order")
    task = work_order_service.complete_task(db, task, actor_user_id=current_user.id)
    return TaskResponse.model_validate(task)


@router.get("/{work_order_id}/tasks", response_model=list[TaskResponse])
def list_tasks(
    work_order_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.AIRCRAFT_READ)),
    _entitled: CurrentUser = Depends(require_feature("work_order_management")),
) -> list[TaskResponse]:
    tasks = work_order_service.list_tasks_for_work_order(
        db, organization_id=current_user.organization_id, work_order_id=work_order_id
    )
    return [TaskResponse.model_validate(t) for t in tasks]
