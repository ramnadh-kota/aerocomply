import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ConflictError
from app.models.inventory_transaction import InventoryTransaction, InventoryTransactionType
from app.models.part import Part, PartServiceabilityStatus
from app.schemas.inventory_transaction import (
    InventoryAdjustRequest,
    InventoryConsumeRequest,
    InventoryQuarantineRequest,
    InventoryReceiveRequest,
    InventoryReleaseQuarantineRequest,
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
    quarantined_delta: int = 0,
    reference_type: str | None,
    reference_id: uuid.UUID | None,
    notes: str | None,
) -> InventoryTransaction:
    new_on_hand = part.quantity_on_hand + on_hand_delta
    new_reserved = part.quantity_reserved + reserved_delta
    new_quarantined = part.quantity_quarantined + quarantined_delta

    if new_on_hand < 0:
        raise ConflictError(
            "Transaction would drive on-hand quantity negative", code="negative_on_hand"
        )
    if new_reserved < 0:
        raise ConflictError(
            "Transaction would drive reserved quantity negative", code="negative_reserved"
        )
    if new_quarantined < 0:
        raise ConflictError(
            "Transaction would drive quarantined quantity negative", code="negative_quarantined"
        )
    if new_reserved + new_quarantined > new_on_hand:
        raise ConflictError(
            "Reserved plus quarantined quantity cannot exceed on-hand quantity",
            code="reserved_exceeds_on_hand",
        )

    part.quantity_on_hand = new_on_hand
    part.quantity_reserved = new_reserved
    part.quantity_quarantined = new_quarantined
    db.add(part)

    transaction = InventoryTransaction(
        organization_id=organization_id,
        part_id=part.id,
        transaction_type=transaction_type,
        on_hand_delta=on_hand_delta,
        reserved_delta=reserved_delta,
        quarantined_delta=quarantined_delta,
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
            "quarantined_delta": quarantined_delta,
            "resulting_on_hand": new_on_hand,
            "resulting_reserved": new_reserved,
            "resulting_quarantined": new_quarantined,
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


def quarantine_part(
    db: Session,
    *,
    organization_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    part_id: uuid.UUID,
    payload: InventoryQuarantineRequest,
) -> InventoryTransaction:
    """Moves stock out of available inventory (excluded from
    available_quantity) pending inspection/disposition — does NOT reduce
    on_hand, since the part is still physically on hand, just not issuable.
    """
    part = part_service.get_part(db, organization_id=organization_id, part_id=part_id)
    transaction = _apply_transaction(
        db,
        organization_id=organization_id,
        actor_user_id=actor_user_id,
        part=part,
        transaction_type=InventoryTransactionType.QUARANTINE,
        on_hand_delta=0,
        reserved_delta=0,
        quarantined_delta=payload.quantity,
        reference_type=payload.reference_type,
        reference_id=payload.reference_id,
        notes=payload.reason,
    )
    part.serviceability_status = PartServiceabilityStatus.QUARANTINED
    part.quarantine_reason = payload.reason
    db.add(part)
    db.commit()
    db.refresh(part)
    return transaction


def release_quarantine(
    db: Session,
    *,
    organization_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    part_id: uuid.UUID,
    payload: InventoryReleaseQuarantineRequest,
) -> InventoryTransaction:
    """Releases quarantined stock back to the disposition an inspection
    actually determined — SERVICEABLE (passed) or SCRAPPED (failed, written
    off from on_hand too). new_status is required, never defaulted, so a
    caller can't silently mark quarantined stock serviceable.
    """
    part = part_service.get_part(db, organization_id=organization_id, part_id=part_id)
    if payload.new_status not in (
        PartServiceabilityStatus.SERVICEABLE,
        PartServiceabilityStatus.UNSERVICEABLE,
        PartServiceabilityStatus.SCRAPPED,
    ):
        raise ConflictError(
            "new_status must be SERVICEABLE, UNSERVICEABLE, or SCRAPPED",
            code="invalid_release_status",
        )
    # SCRAPPED also removes the stock from on_hand — it's leaving inventory
    # entirely, not just clearing the quarantine hold.
    on_hand_delta = (
        -payload.quantity if payload.new_status == PartServiceabilityStatus.SCRAPPED else 0
    )
    transaction = _apply_transaction(
        db,
        organization_id=organization_id,
        actor_user_id=actor_user_id,
        part=part,
        transaction_type=InventoryTransactionType.RELEASE_QUARANTINE,
        on_hand_delta=on_hand_delta,
        reserved_delta=0,
        quarantined_delta=-payload.quantity,
        reference_type=None,
        reference_id=None,
        notes=payload.notes,
    )
    part.serviceability_status = payload.new_status
    if payload.new_status != PartServiceabilityStatus.SCRAPPED:
        part.quarantine_reason = None
    db.add(part)
    db.commit()
    db.refresh(part)
    return transaction


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
