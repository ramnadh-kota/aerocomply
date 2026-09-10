"""Synthesize a real, backend-authoritative AOG recovery status for one
aircraft, by aggregating existing domain services — never re-implementing
their logic. This module is read-only: it never mutates any record.

Reused as-is (never re-derived):
  - aog_service.list_aog_events           (the active AOG event, if any)
  - release_readiness_service              (task execution / evidence / RII)
  - tat_service                            (turnaround status, honestly UNKNOWN
                                             where the schema has no due date)
  - part_requirement_service               (which parts are SHORT for the WO)
  - procurement_service / purchase_order_service (where a shortage sits in
                                             the request -> approval -> PO ->
                                             receive chain)

What this module deliberately does NOT claim, because no backend record
exists for it yet (see release_readiness_service's own data_completeness
note): technician authorization/qualification, an ETA/lead-time for a part
in transit, and a live regulatory/compliance sync result. Those fields are
always returned as an explicit NOT_TRACKED/UNKNOWN string, never fabricated.
"""

import uuid
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.models.aog_event import AogEvent, AogEventStatus
from app.models.part_requirement import PartRequirementStatus
from app.models.procurement_request import ProcurementRequestStatus
from app.models.purchase_order import PurchaseOrderStatus
from app.services import (
    aircraft_service,
    aog_service,
    part_requirement_service,
    procurement_service,
    purchase_order_service,
    release_readiness_service,
    tat_service,
)

# Deterministic blocker priority — lower number resolves the AOG event
# sooner in the dependency chain, so it is surfaced first as the "next best
# action". Not a guess: this mirrors the actual dependency order (a part
# that hasn't even been requested blocks everything downstream of it).
_CATEGORY_PRIORITY = {
    "MATERIAL_NOT_REQUESTED": 0,
    "MATERIAL_AWAITING_APPROVAL": 1,
    "MATERIAL_PO_NOT_SENT": 2,
    "MATERIAL_AWAITING_RECEIPT": 3,
    "MATERIAL_SHORT": 4,
    "INSPECTION": 5,
    "EVIDENCE": 6,
    "TASK_EXECUTION": 7,
    "EVENT_BLOCKER": 8,
}


@dataclass
class RecoveryBlocker:
    category: str
    description: str
    record_type: str
    record_id: str | None
    who_should_act: str
    dependency: str


@dataclass
class AogRecoveryStatus:
    aircraft_id: str
    registration: str
    is_aog: bool
    aog_event_id: str | None = None
    aog_status: str | None = None
    severity: str | None = None
    work_order_id: str | None = None
    release_readiness_status: str | None = None
    tat_status: str | None = None
    tat_reason: str | None = None
    blockers: list[RecoveryBlocker] = field(default_factory=list)
    next_best_action: RecoveryBlocker | None = None
    technician_authorization: str = (
        "NOT_TRACKED — no technician authorization/qualification model exists yet"
    )
    eta: str = "UNKNOWN — no vendor lead-time or delivery-date field is tracked; never inferred"
    compliance_status: str = (
        "NOT_EVALUATED — this analysis does not query regulatory/compliance assessments"
    )
    data_completeness: str = ""


def _active_event(events: list[AogEvent]) -> AogEvent | None:
    for event in events:
        if event.status in (AogEventStatus.DECLARED, AogEventStatus.IN_RECOVERY):
            return event
    return None


def get_recovery_status(
    db: Session, *, organization_id: uuid.UUID, aircraft_id: uuid.UUID
) -> AogRecoveryStatus:
    aircraft = aircraft_service.get_aircraft(
        db, organization_id=organization_id, aircraft_id=aircraft_id
    )
    events = aog_service.list_aog_events(
        db, organization_id=organization_id, aircraft_id=aircraft_id
    )
    active_event = _active_event(events)

    if active_event is None:
        return AogRecoveryStatus(
            aircraft_id=str(aircraft.id),
            registration=aircraft.registration,
            is_aog=False,
            data_completeness="No DECLARED or IN_RECOVERY AogEvent exists for this aircraft.",
        )

    status = AogRecoveryStatus(
        aircraft_id=str(aircraft.id),
        registration=aircraft.registration,
        is_aog=True,
        aog_event_id=str(active_event.id),
        aog_status=active_event.status,
        severity=active_event.severity,
        work_order_id=str(active_event.work_order_id) if active_event.work_order_id else None,
    )

    for blocker in active_event.blockers:
        if blocker.resolved:
            continue
        status.blockers.append(
            RecoveryBlocker(
                category="EVENT_BLOCKER",
                description=blocker.description,
                record_type=blocker.blocker_type,
                record_id=blocker.source_reference,
                who_should_act="AOG recovery owner",
                dependency="Recorded directly against the AOG event.",
            )
        )

    if active_event.work_order_id is None:
        status.data_completeness = (
            "AOG event has no linked work order — release readiness, TAT, and "
            "part-shortage analysis require one and cannot be evaluated."
        )
        _set_next_best_action(status)
        return status

    work_order_id = active_event.work_order_id

    readiness = release_readiness_service.get_release_readiness_for_work_order(
        db, organization_id=organization_id, work_order_id=work_order_id
    )
    status.release_readiness_status = readiness.status
    for b in readiness.blockers:
        status.blockers.append(
            RecoveryBlocker(
                category=b.category,
                description=b.description,
                record_type=b.category,
                record_id=str(b.related_record_id) if b.related_record_id else None,
                who_should_act=_actor_for_category(b.category),
                dependency=_dependency_for_category(b.category),
            )
        )

    tat = tat_service.get_work_order_tat_status(
        db, organization_id=organization_id, work_order_id=work_order_id
    )
    status.tat_status = tat.status
    status.tat_reason = tat.reason

    requirements = part_requirement_service.list_part_requirements_for_work_order(
        db, organization_id=organization_id, work_order_id=work_order_id
    )
    shortages = [r for r in requirements if r.status == PartRequirementStatus.SHORT]

    if shortages:
        all_requests = procurement_service.list_requests(db, organization_id=organization_id)
        all_pos = purchase_order_service.list_purchase_orders(db, organization_id=organization_id)
        for requirement in shortages:
            status.blockers.append(
                _material_blocker(requirement, work_order_id, all_requests, all_pos)
            )

    status.data_completeness = (
        "Covers AOG event blockers, release readiness (task execution / evidence / "
        "inspection), TAT, and material shortages with their procurement/PO/receiving "
        "state. Technician authorization, part lead-time/ETA, and compliance sync are "
        "not backend-tracked and are reported as such rather than fabricated."
    )

    _set_next_best_action(status)
    return status


def _material_blocker(
    requirement, work_order_id: uuid.UUID, all_requests, all_pos
) -> RecoveryBlocker:
    matching_requests = [
        r
        for r in all_requests
        if r.part_id == requirement.part_id and r.work_order_id == work_order_id
    ]
    matching_requests.sort(key=lambda r: r.created_at, reverse=True)
    latest_request = matching_requests[0] if matching_requests else None

    if latest_request is None:
        return RecoveryBlocker(
            category="MATERIAL_NOT_REQUESTED",
            description=(
                f"Part requirement {requirement.id} is SHORT (required "
                f"{requirement.required_quantity}, fulfilled {requirement.fulfilled_quantity}) "
                "and no procurement request has been created for it yet."
            ),
            record_type="PartRequirement",
            record_id=str(requirement.id),
            who_should_act="Procurement",
            dependency="Create a procurement request for this shortage.",
        )

    request_status = latest_request.status

    if request_status in (
        ProcurementRequestStatus.SUBMITTED,
        ProcurementRequestStatus.UNDER_REVIEW,
        ProcurementRequestStatus.CLARIFICATION_REQUIRED,
    ):
        return RecoveryBlocker(
            category="MATERIAL_AWAITING_APPROVAL",
            description=(
                f"Procurement request {latest_request.id} is {request_status}, "
                "awaiting approval."
            ),
            record_type="ProcurementRequest",
            record_id=str(latest_request.id),
            who_should_act="Procurement approver",
            dependency="Approve (or clarify/resolve) the procurement request.",
        )

    if request_status == ProcurementRequestStatus.REJECTED:
        reason = latest_request.rejection_reason or "no reason recorded"
        return RecoveryBlocker(
            category="MATERIAL_AWAITING_APPROVAL",
            description=f"Procurement request {latest_request.id} was REJECTED: {reason}.",
            record_type="ProcurementRequest",
            record_id=str(latest_request.id),
            who_should_act="Procurement",
            dependency="Submit a new procurement request for this shortage.",
        )

    if request_status == ProcurementRequestStatus.APPROVED:
        return RecoveryBlocker(
            category="MATERIAL_PO_NOT_SENT",
            description=(
                f"Procurement request {latest_request.id} is APPROVED but no purchase "
                "order has been created for it yet."
            ),
            record_type="ProcurementRequest",
            record_id=str(latest_request.id),
            who_should_act="Procurement",
            dependency="Create a purchase order from this approved request.",
        )

    # ORDERED or RECEIVED — a PO should exist referencing this request via a line.
    matching_pos = [
        po
        for po in all_pos
        if any(line.procurement_request_id == latest_request.id for line in po.lines)
    ]
    matching_pos.sort(key=lambda po: po.created_at, reverse=True)
    po = matching_pos[0] if matching_pos else None

    if po is None:
        return RecoveryBlocker(
            category="MATERIAL_PO_NOT_SENT",
            description=(
                f"Procurement request {latest_request.id} is {request_status} but "
                "its purchase order could not be found."
            ),
            record_type="ProcurementRequest",
            record_id=str(latest_request.id),
            who_should_act="Procurement",
            dependency="Verify the purchase order linked to this request.",
        )

    not_yet_sent = (
        PurchaseOrderStatus.DRAFT,
        PurchaseOrderStatus.PENDING_APPROVAL,
        PurchaseOrderStatus.APPROVED,
    )
    if po.status in not_yet_sent:
        return RecoveryBlocker(
            category="MATERIAL_PO_NOT_SENT",
            description=(
                f"Purchase order {po.po_number} is {po.status}, not yet sent to the vendor."
            ),
            record_type="PurchaseOrder",
            record_id=str(po.id),
            who_should_act="Procurement approver",
            dependency="Advance the purchase order to SENT.",
        )

    sent_not_fully_received = (
        PurchaseOrderStatus.SENT,
        PurchaseOrderStatus.ACKNOWLEDGED,
        "PARTIALLY_RECEIVED",
    )
    if po.status in sent_not_fully_received:
        return RecoveryBlocker(
            category="MATERIAL_AWAITING_RECEIPT",
            description=(
                f"Purchase order {po.po_number} is {po.status} — part has not been "
                "fully received."
            ),
            record_type="PurchaseOrder",
            record_id=str(po.id),
            who_should_act="Receiving",
            dependency="Record receipt of the outstanding quantity.",
        )

    # PO fully RECEIVED but the requirement still computed SHORT (e.g. stock
    # consumed elsewhere in the meantime) — report the fact plainly rather
    # than guessing why.
    return RecoveryBlocker(
        category="MATERIAL_SHORT",
        description=(
            f"Part requirement {requirement.id} is still SHORT even though purchase "
            f"order {po.po_number} shows RECEIVED — inventory may have been consumed "
            "or reserved elsewhere."
        ),
        record_type="PartRequirement",
        record_id=str(requirement.id),
        who_should_act="Inventory / Procurement",
        dependency="Investigate current available_quantity against this requirement.",
    )


def _actor_for_category(category: str) -> str:
    return {
        "TASK_EXECUTION": "Assigned technician",
        "EVIDENCE": "Assigned technician",
        "INSPECTION": "Authorized inspector (independent of the executing technician)",
    }.get(category, "Maintenance")


def _dependency_for_category(category: str) -> str:
    return {
        "TASK_EXECUTION": "Complete task execution.",
        "EVIDENCE": "Submit and have evidence accepted.",
        "INSPECTION": "Complete the required inspection (RII requires an independent inspector).",
    }.get(category, "Resolve the underlying record.")


def _set_next_best_action(status: AogRecoveryStatus) -> None:
    if not status.blockers:
        status.next_best_action = None
        return
    ranked = sorted(
        status.blockers, key=lambda b: _CATEGORY_PRIORITY.get(b.category, 99)
    )
    status.next_best_action = ranked[0]
