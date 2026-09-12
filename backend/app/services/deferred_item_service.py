import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError
from app.models.deferred_item import (
    DeferredItem,
    DeferredItemApprovalStatus,
    DeferredItemStatus,
)
from app.schemas.deferred_item import (
    DeferredItemCloseRequest,
    DeferredItemCreateRequest,
    DeferredItemUpdateRequest,
)
from app.services import aircraft_service, work_order_service
from app.services.audit_service import record_audit_event


def create_deferred_item(
    db: Session,
    *,
    organization_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    payload: DeferredItemCreateRequest,
) -> DeferredItem:
    aircraft_service.get_aircraft(
        db, organization_id=organization_id, aircraft_id=payload.aircraft_id
    )
    # work_order_id is optional, client-supplied data -- verify it belongs to
    # this organization too, or a caller could link a deferred item to a
    # different tenant's work order (cross-tenant IDOR).
    if payload.work_order_id is not None:
        work_order_service.get_work_order(
            db, organization_id=organization_id, work_order_id=payload.work_order_id
        )
    approval_status = (
        DeferredItemApprovalStatus.PENDING
        if payload.approval_required
        else DeferredItemApprovalStatus.NOT_REQUIRED
    )
    item = DeferredItem(
        organization_id=organization_id,
        aircraft_id=payload.aircraft_id,
        work_order_id=payload.work_order_id,
        mel_reference=payload.mel_reference,
        category=payload.category,
        description=payload.description,
        opened_at=payload.opened_at,
        due_at=payload.due_at,
        status=DeferredItemStatus.OPEN,
        deferral_basis=payload.deferral_basis,
        operational_limitations=payload.operational_limitations,
        required_actions=payload.required_actions,
        approval_required=payload.approval_required,
        approval_status=approval_status,
    )
    db.add(item)
    db.flush()
    record_audit_event(
        db,
        organization_id=organization_id,
        user_id=actor_user_id,
        action="deferred_item.created",
        entity_type="DeferredItem",
        entity_id=item.id,
        metadata={"aircraft_id": str(payload.aircraft_id)},
    )
    db.commit()
    db.refresh(item)
    return item


def get_deferred_item(
    db: Session, *, organization_id: uuid.UUID, item_id: uuid.UUID
) -> DeferredItem:
    item = db.execute(
        select(DeferredItem).where(
            DeferredItem.id == item_id, DeferredItem.organization_id == organization_id
        )
    ).scalar_one_or_none()
    if item is None:
        raise NotFoundError("Deferred item not found")
    return item


def list_deferred_items_for_aircraft(
    db: Session, *, organization_id: uuid.UUID, aircraft_id: uuid.UUID, open_only: bool = False
) -> list[DeferredItem]:
    stmt = select(DeferredItem).where(
        DeferredItem.organization_id == organization_id, DeferredItem.aircraft_id == aircraft_id
    )
    if open_only:
        stmt = stmt.where(DeferredItem.status == DeferredItemStatus.OPEN)
    return list(db.execute(stmt).scalars().all())


def list_fleet_deferred_items(
    db: Session, *, organization_id: uuid.UUID, open_only: bool = False
) -> list[DeferredItem]:
    stmt = select(DeferredItem).where(DeferredItem.organization_id == organization_id)
    if open_only:
        stmt = stmt.where(DeferredItem.status == DeferredItemStatus.OPEN)
    return list(db.execute(stmt).scalars().all())


def update_deferred_item(
    db: Session,
    *,
    organization_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    item_id: uuid.UUID,
    payload: DeferredItemUpdateRequest,
) -> DeferredItem:
    item = get_deferred_item(db, organization_id=organization_id, item_id=item_id)
    updates = payload.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(item, field, value)
    db.add(item)
    if updates:
        record_audit_event(
            db,
            organization_id=organization_id,
            user_id=actor_user_id,
            action="deferred_item.updated",
            entity_type="DeferredItem",
            entity_id=item.id,
            metadata=updates,
        )
    db.commit()
    db.refresh(item)
    return item


def close_deferred_item(
    db: Session,
    *,
    organization_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    item_id: uuid.UUID,
    payload: DeferredItemCloseRequest,
) -> DeferredItem:
    item = get_deferred_item(db, organization_id=organization_id, item_id=item_id)
    if item.status == DeferredItemStatus.CLOSED:
        raise ConflictError("Deferred item is already closed", code="already_closed")
    if (
        item.approval_required
        and item.approval_status != DeferredItemApprovalStatus.APPROVED
    ):
        raise ConflictError(
            "Cannot close a deferred item that requires approval until it is approved",
            code="approval_required",
        )
    item.status = DeferredItemStatus.CLOSED
    item.closed_at = payload.closed_at
    item.closure_notes = payload.closure_notes
    db.add(item)
    record_audit_event(
        db,
        organization_id=organization_id,
        user_id=actor_user_id,
        action="deferred_item.closed",
        entity_type="DeferredItem",
        entity_id=item.id,
        metadata={"closed_at": payload.closed_at.isoformat()},
    )
    db.commit()
    db.refresh(item)
    return item
