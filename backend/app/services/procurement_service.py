import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, ForbiddenError, NotFoundError
from app.models.procurement_request import ProcurementRequest, ProcurementRequestStatus
from app.schemas.procurement_request import (
    ProcurementRequestApproveRequest,
    ProcurementRequestClarifyRequest,
    ProcurementRequestCreateRequest,
    ProcurementRequestRejectRequest,
)
from app.services import aircraft_service, part_service, vendor_service, work_order_service
from app.services.audit_service import record_audit_event

# Explicit transition table — a status change not listed here is rejected
# rather than silently allowed. UNDER_REVIEW is reachable but not required:
# a SUBMITTED request may be approved/rejected directly, matching how small
# MRO procurement teams actually operate (not every request gets a separate
# review step).
_ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    ProcurementRequestStatus.SUBMITTED: {
        ProcurementRequestStatus.UNDER_REVIEW,
        ProcurementRequestStatus.APPROVED,
        ProcurementRequestStatus.REJECTED,
        ProcurementRequestStatus.CLARIFICATION_REQUIRED,
    },
    ProcurementRequestStatus.UNDER_REVIEW: {
        ProcurementRequestStatus.APPROVED,
        ProcurementRequestStatus.REJECTED,
        ProcurementRequestStatus.CLARIFICATION_REQUIRED,
    },
    ProcurementRequestStatus.CLARIFICATION_REQUIRED: {
        ProcurementRequestStatus.SUBMITTED,
    },
    ProcurementRequestStatus.APPROVED: {
        ProcurementRequestStatus.ORDERED,
    },
    ProcurementRequestStatus.ORDERED: {
        ProcurementRequestStatus.RECEIVED,
    },
    ProcurementRequestStatus.RECEIVED: {
        ProcurementRequestStatus.CLOSED,
    },
}


def _require_transition(current: str, target: str) -> None:
    allowed = _ALLOWED_TRANSITIONS.get(current, set())
    if target not in allowed:
        raise ConflictError(
            f"Cannot transition procurement request from {current} to {target}",
            code="invalid_transition",
        )


def create_request(
    db: Session,
    *,
    organization_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    payload: ProcurementRequestCreateRequest,
) -> ProcurementRequest:
    # Confirm tenant-owned relationships before creating the request.
    aircraft_service.get_aircraft(
        db, organization_id=organization_id, aircraft_id=payload.aircraft_id
    )
    if payload.preferred_vendor_id is not None:
        vendor_service.get_vendor(
            db, organization_id=organization_id, vendor_id=payload.preferred_vendor_id
        )
    # work_order_id / task_id / part_id are optional, client-supplied
    # references -- verify each belongs to this organization before linking
    # it to the request (cross-tenant IDOR otherwise).
    if payload.work_order_id is not None:
        work_order_service.get_work_order(
            db, organization_id=organization_id, work_order_id=payload.work_order_id
        )
    if payload.task_id is not None:
        work_order_service.get_task(db, organization_id=organization_id, task_id=payload.task_id)
    if payload.part_id is not None:
        part_service.get_part(db, organization_id=organization_id, part_id=payload.part_id)

    request = ProcurementRequest(
        organization_id=organization_id,
        aircraft_id=payload.aircraft_id,
        work_order_id=payload.work_order_id,
        task_id=payload.task_id,
        part_id=payload.part_id,
        part_number=payload.part_number,
        description=payload.description,
        quantity=payload.quantity,
        priority=payload.priority,
        reason=payload.reason,
        requested_by_user_id=actor_user_id,
        preferred_vendor_id=payload.preferred_vendor_id,
        estimated_cost_cents=payload.estimated_cost_cents,
        status=ProcurementRequestStatus.SUBMITTED,
    )
    db.add(request)
    db.flush()
    record_audit_event(
        db,
        organization_id=organization_id,
        user_id=actor_user_id,
        action="procurement_request.created",
        entity_type="ProcurementRequest",
        entity_id=request.id,
        metadata={"status": request.status},
    )
    db.commit()
    db.refresh(request)
    return request


def get_request(
    db: Session, *, organization_id: uuid.UUID, request_id: uuid.UUID
) -> ProcurementRequest:
    request = db.execute(
        select(ProcurementRequest).where(
            ProcurementRequest.id == request_id,
            ProcurementRequest.organization_id == organization_id,
        )
    ).scalar_one_or_none()
    if request is None:
        raise NotFoundError("Procurement request not found")
    return request


def list_requests(
    db: Session, *, organization_id: uuid.UUID, status: str | None = None
) -> list[ProcurementRequest]:
    stmt = select(ProcurementRequest).where(ProcurementRequest.organization_id == organization_id)
    if status is not None:
        stmt = stmt.where(ProcurementRequest.status == status)
    return list(db.execute(stmt).scalars().all())


def _transition(
    db: Session,
    *,
    organization_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    request: ProcurementRequest,
    target_status: str,
    action: str,
    extra_fields: dict | None = None,
) -> ProcurementRequest:
    _require_transition(request.status, target_status)
    previous_status = request.status
    request.status = target_status
    for field, value in (extra_fields or {}).items():
        setattr(request, field, value)

    db.add(request)
    record_audit_event(
        db,
        organization_id=organization_id,
        user_id=actor_user_id,
        action=action,
        entity_type="ProcurementRequest",
        entity_id=request.id,
        metadata={"from_status": previous_status, "to_status": target_status},
    )
    db.commit()
    db.refresh(request)
    return request


def submit_for_review(
    db: Session,
    *,
    organization_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    request_id: uuid.UUID,
) -> ProcurementRequest:
    request = get_request(db, organization_id=organization_id, request_id=request_id)
    return _transition(
        db,
        organization_id=organization_id,
        actor_user_id=actor_user_id,
        request=request,
        target_status=ProcurementRequestStatus.UNDER_REVIEW,
        action="procurement_request.under_review",
    )


def approve_request(
    db: Session,
    *,
    organization_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    request_id: uuid.UUID,
    payload: ProcurementRequestApproveRequest,
) -> ProcurementRequest:
    request = get_request(db, organization_id=organization_id, request_id=request_id)
    if (
        actor_user_id is not None
        and request.requested_by_user_id is not None
        and actor_user_id == request.requested_by_user_id
    ):
        raise ForbiddenError(
            "A procurement request cannot be approved by its own requester",
            code="self_approval_forbidden",
        )
    selected_vendor_id = payload.selected_vendor_id or request.preferred_vendor_id
    if selected_vendor_id is not None:
        vendor_service.get_vendor(
            db, organization_id=organization_id, vendor_id=selected_vendor_id
        )
    return _transition(
        db,
        organization_id=organization_id,
        actor_user_id=actor_user_id,
        request=request,
        target_status=ProcurementRequestStatus.APPROVED,
        action="procurement_request.approved",
        extra_fields={
            "approved_by_user_id": actor_user_id,
            "selected_vendor_id": selected_vendor_id,
        },
    )


def reject_request(
    db: Session,
    *,
    organization_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    request_id: uuid.UUID,
    payload: ProcurementRequestRejectRequest,
) -> ProcurementRequest:
    request = get_request(db, organization_id=organization_id, request_id=request_id)
    return _transition(
        db,
        organization_id=organization_id,
        actor_user_id=actor_user_id,
        request=request,
        target_status=ProcurementRequestStatus.REJECTED,
        action="procurement_request.rejected",
        extra_fields={"rejection_reason": payload.rejection_reason},
    )


def request_clarification(
    db: Session,
    *,
    organization_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    request_id: uuid.UUID,
    payload: ProcurementRequestClarifyRequest,
) -> ProcurementRequest:
    request = get_request(db, organization_id=organization_id, request_id=request_id)
    return _transition(
        db,
        organization_id=organization_id,
        actor_user_id=actor_user_id,
        request=request,
        target_status=ProcurementRequestStatus.CLARIFICATION_REQUIRED,
        action="procurement_request.clarification_requested",
        extra_fields={"clarification_note": payload.clarification_note},
    )


def resubmit_request(
    db: Session,
    *,
    organization_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    request_id: uuid.UUID,
) -> ProcurementRequest:
    request = get_request(db, organization_id=organization_id, request_id=request_id)
    return _transition(
        db,
        organization_id=organization_id,
        actor_user_id=actor_user_id,
        request=request,
        target_status=ProcurementRequestStatus.SUBMITTED,
        action="procurement_request.resubmitted",
        extra_fields={"clarification_note": None},
    )


def mark_ordered(
    db: Session,
    *,
    organization_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    request_id: uuid.UUID,
) -> ProcurementRequest:
    request = get_request(db, organization_id=organization_id, request_id=request_id)
    return _transition(
        db,
        organization_id=organization_id,
        actor_user_id=actor_user_id,
        request=request,
        target_status=ProcurementRequestStatus.ORDERED,
        action="procurement_request.ordered",
    )


def mark_received(
    db: Session,
    *,
    organization_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    request_id: uuid.UUID,
) -> ProcurementRequest:
    request = get_request(db, organization_id=organization_id, request_id=request_id)
    return _transition(
        db,
        organization_id=organization_id,
        actor_user_id=actor_user_id,
        request=request,
        target_status=ProcurementRequestStatus.RECEIVED,
        action="procurement_request.received",
    )


def close_request(
    db: Session,
    *,
    organization_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    request_id: uuid.UUID,
) -> ProcurementRequest:
    request = get_request(db, organization_id=organization_id, request_id=request_id)
    return _transition(
        db,
        organization_id=organization_id,
        actor_user_id=actor_user_id,
        request=request,
        target_status=ProcurementRequestStatus.CLOSED,
        action="procurement_request.closed",
    )
