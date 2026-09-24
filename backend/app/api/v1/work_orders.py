import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.deps import get_db_session, require_feature, require_permission
from app.core.errors import NotFoundError
from app.core.permissions import Permission
from app.schemas.auth import CurrentUser
from app.schemas.task import TaskCreateRequest, TaskResponse
from app.schemas.work_order import WorkOrderCreateRequest, WorkOrderResponse
from app.services import work_order_service

router = APIRouter(prefix="/work-orders", tags=["work-orders"])


@router.post("", response_model=WorkOrderResponse, status_code=201)
def create_work_order(
    payload: WorkOrderCreateRequest,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.WORK_ORDER_CREATE)),
    _entitled: CurrentUser = Depends(require_feature("work_order_management")),
) -> WorkOrderResponse:
    # organization_id always comes from the authenticated user, never the request body.
    work_order = work_order_service.create_work_order(
        db,
        organization_id=current_user.organization_id,
        created_by_user_id=current_user.id,
        payload=payload,
    )
    return WorkOrderResponse.model_validate(work_order)


@router.get("", response_model=list[WorkOrderResponse])
def list_work_orders(
    asset_id: uuid.UUID | None = None,
    aircraft_id: uuid.UUID | None = None,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.WORK_ORDER_READ)),
    _entitled: CurrentUser = Depends(require_feature("work_order_management")),
) -> list[WorkOrderResponse]:
    work_orders = work_order_service.list_work_orders(
        db,
        organization_id=current_user.organization_id,
        asset_id=asset_id,
        aircraft_id=aircraft_id,
    )
    return [WorkOrderResponse.model_validate(w) for w in work_orders]


@router.get("/{work_order_id}", response_model=WorkOrderResponse)
def get_work_order(
    work_order_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.WORK_ORDER_READ)),
    _entitled: CurrentUser = Depends(require_feature("work_order_management")),
) -> WorkOrderResponse:
    work_order = work_order_service.get_work_order(
        db, organization_id=current_user.organization_id, work_order_id=work_order_id
    )
    return WorkOrderResponse.model_validate(work_order)


@router.post("/{work_order_id}/tasks", response_model=TaskResponse, status_code=201)
def create_task(
    work_order_id: uuid.UUID,
    payload: TaskCreateRequest,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.WORK_ORDER_UPDATE)),
    _entitled: CurrentUser = Depends(require_feature("work_order_management")),
) -> TaskResponse:
    payload = payload.model_copy(update={"work_order_id": work_order_id})
    task = work_order_service.create_task(
        db, organization_id=current_user.organization_id, payload=payload
    )
    return TaskResponse.model_validate(task)


@router.post("/{work_order_id}/tasks/{task_id}/complete", response_model=TaskResponse)
def complete_task(
    work_order_id: uuid.UUID,
    task_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    # No distinct TASK_WRITE permission exists in the catalog (see
    # app/core/permissions.py); WORK_ORDER_UPDATE already gates task creation
    # above, so it gates task completion too for the same reason.
    current_user: CurrentUser = Depends(require_permission(Permission.WORK_ORDER_UPDATE)),
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
    current_user: CurrentUser = Depends(require_permission(Permission.WORK_ORDER_READ)),
    _entitled: CurrentUser = Depends(require_feature("work_order_management")),
) -> list[TaskResponse]:
    tasks = work_order_service.list_tasks_for_work_order(
        db, organization_id=current_user.organization_id, work_order_id=work_order_id
    )
    return [TaskResponse.model_validate(t) for t in tasks]
