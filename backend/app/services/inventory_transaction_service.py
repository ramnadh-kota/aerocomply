import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ConflictError
from app.models.inventory_transaction import InventoryTransaction, InventoryTransactionType
from app.models.part import Part
from app.schemas.inventory_transaction import (
    InventoryAdjustRequest,
    InventoryConsumeRequest,
    InventoryReceiveRequest,
    InventoryReleaseRequest,
    InventoryReserveRequest,
)
from app.services import part_requirement_service, part_service
from app.services.audit_service import record_audit_event


def _apply_transaction(
    db: Session,
    *,
    organization_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    part: Part,
    transaction_type: str,
    on_hand_delta: int,
    reserved_delta: int,
    reference_type: str | None,
    reference_id: uuid.UUID | None,
    notes: str | None,
) -> InventoryTransaction:
    new_on_hand = part.quantity_on_hand + on_hand_delta
    new_reserved = part.quantity_reserved + reserved_delta

    if new_on_hand < 0:
        raise ConflictError(
            "Transaction would drive on-hand quantity negative", code="negative_on_hand"
        )
    if new_reserved < 0:
        raise ConflictError(
            "Transaction would drive reserved quantity negative", code="negative_reserved"
        )
    if new_reserved > new_on_hand:
        raise ConflictError(
            "Reserved quantity cannot exceed on-hand quantity", code="reserved_exceeds_on_hand"
        )

    part.quantity_on_hand = new_on_hand
    part.quantity_reserved = new_reserved
    db.add(part)

    transaction = InventoryTransaction(
        organization_id=organization_id,
        part_id=part.id,
        transaction_type=transaction_type,
        on_hand_delta=on_hand_delta,
        reserved_delta=reserved_delta,
        reference_type=reference_type,
        reference_id=reference_id,
        notes=notes,
        actor_user_id=actor_user_id,
    )
    db.add(transaction)
    db.flush()

    record_audit_event(
        db,
        organization_id=organization_id,
        user_id=actor_user_id,
        action=f"inventory.{transaction_type.lower()}",
        entity_type="Part",
        entity_id=part.id,
        metadata={
            "transaction_id": str(transaction.id),
            "on_hand_delta": on_hand_delta,
            "reserved_delta": reserved_delta,
            "resulting_on_hand": new_on_hand,
            "resulting_reserved": new_reserved,
        },
    )

    db.commit()
    db.refresh(transaction)
    db.refresh(part)

    # Any part-quantity change can flip an open requirement's SHORT/AVAILABLE
    # status — re-derive it immediately rather than leaving it stale.
    part_requirement_service.recompute_status_for_part(
        db, organization_id=organization_id, part_id=part.id
    )
    return transaction


def receive_part(
    db: Session,
    *,
    organization_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    part_id: uuid.UUID,
    payload: InventoryReceiveRequest,
) -> InventoryTransaction:
    part = part_service.get_part(db, organization_id=organization_id, part_id=part_id)
    return _apply_transaction(
        db,
        organization_id=organization_id,
        actor_user_id=actor_user_id,
        part=part,
        transaction_type=InventoryTransactionType.RECEIVE,
        on_hand_delta=payload.quantity,
        reserved_delta=0,
        reference_type=payload.reference_type,
        reference_id=payload.reference_id,
        notes=payload.notes,
    )


def reserve_part(
    db: Session,
    *,
    organization_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    part_id: uuid.UUID,
    payload: InventoryReserveRequest,
) -> InventoryTransaction:
    part = part_service.get_part(db, organization_id=organization_id, part_id=part_id)
    return _apply_transaction(
        db,
        organization_id=organization_id,
        actor_user_id=actor_user_id,
        part=part,
        transaction_type=InventoryTransactionType.RESERVE,
        on_hand_delta=0,
        reserved_delta=payload.quantity,
        reference_type=payload.reference_type,
        reference_id=payload.reference_id,
        notes=payload.notes,
    )


def release_reservation(
    db: Session,
    *,
    organization_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    part_id: uuid.UUID,
    payload: InventoryReleaseRequest,
) -> InventoryTransaction:
    part = part_service.get_part(db, organization_id=organization_id, part_id=part_id)
    return _apply_transaction(
        db,
        organization_id=organization_id,
        actor_user_id=actor_user_id,
        part=part,
        transaction_type=InventoryTransactionType.RELEASE,
        on_hand_delta=0,
        reserved_delta=-payload.quantity,
        reference_type=payload.reference_type,
        reference_id=payload.reference_id,
        notes=payload.notes,
    )


def consume_part(
    db: Session,
    *,
    organization_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    part_id: uuid.UUID,
    payload: InventoryConsumeRequest,
) -> InventoryTransaction:
    part = part_service.get_part(db, organization_id=organization_id, part_id=part_id)
    return _apply_transaction(
        db,
        organization_id=organization_id,
        actor_user_id=actor_user_id,
        part=part,
        transaction_type=InventoryTransactionType.CONSUME,
        on_hand_delta=-payload.quantity,
        reserved_delta=-payload.quantity,
        reference_type=payload.reference_type,
        reference_id=payload.reference_id,
        notes=payload.notes,
    )


def adjust_part(
    db: Session,
    *,
    organization_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    part_id: uuid.UUID,
    payload: InventoryAdjustRequest,
) -> InventoryTransaction:
    part = part_service.get_part(db, organization_id=organization_id, part_id=part_id)
    return _apply_transaction(
        db,
        organization_id=organization_id,
        actor_user_id=actor_user_id,
        part=part,
        transaction_type=InventoryTransactionType.ADJUST,
        on_hand_delta=payload.on_hand_delta,
        reserved_delta=0,
        reference_type=None,
        reference_id=None,
        notes=payload.notes,
    )


def list_transactions_for_part(
    db: Session, *, organization_id: uuid.UUID, part_id: uuid.UUID
) -> list[InventoryTransaction]:
    return list(
        db.execute(
            select(InventoryTransaction)
            .where(
                InventoryTransaction.organization_id == organization_id,
                InventoryTransaction.part_id == part_id,
            )
            .order_by(InventoryTransaction.created_at)
        )
        .scalars()
        .all()
    )
