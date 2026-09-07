import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.deps import get_db_session, require_permission
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
    current_user: CurrentUser = Depends(require_permission(Permission.AIRCRAFT_WRITE)),
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
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.AIRCRAFT_READ)),
) -> list[WorkOrderResponse]:
    work_orders = work_order_service.list_work_orders(
        db, organization_id=current_user.organization_id
    )
    return [WorkOrderResponse.model_validate(w) for w in work_orders]


@router.get("/{work_order_id}", response_model=WorkOrderResponse)
def get_work_order(
    work_order_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.AIRCRAFT_READ)),
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
    current_user: CurrentUser = Depends(require_permission(Permission.AIRCRAFT_WRITE)),
) -> TaskResponse:
    payload = payload.model_copy(update={"work_order_id": work_order_id})
    task = work_order_service.create_task(
        db, organization_id=current_user.organization_id, payload=payload
    )
    return TaskResponse.model_validate(task)


@router.get("/{work_order_id}/tasks", response_model=list[TaskResponse])
def list_tasks(
    work_order_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.AIRCRAFT_READ)),
) -> list[TaskResponse]:
    tasks = work_order_service.list_tasks_for_work_order(
        db, organization_id=current_user.organization_id, work_order_id=work_order_id
    )
    return [TaskResponse.model_validate(t) for t in tasks]
