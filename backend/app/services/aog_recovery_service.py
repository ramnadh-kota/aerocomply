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

Technician authorization is now real (app/services/technician_service.py):
when a task on the AOG work order has an assigned technician, this module
calls check_authorization and reports the real AUTHORIZED/NOT_AUTHORIZED/
EXPIRED/MISSING/UNKNOWN result. When no task has an assignment yet, that
fact itself is reported plainly — never a fabricated authorization.

What this module still does NOT claim, because no backend record exists for
it (see release_readiness_service's own data_completeness note): an ETA/
lead-time for a part in transit, and a live regulatory/compliance sync
result. Those fields are always returned as an explicit UNKNOWN/NOT_EVALUATED
string, never fabricated.
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
    technician_service,
    work_order_service,
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
    "TECHNICIAN": 8,
    "EVENT_BLOCKER": 9,
}


@dataclass
class RecoveryBlocker:
    category: str
    description: str
    record_type: str
    record_id: str | None
    who_should_act: str
    dependency: str


# COMPLETE / ACTIVE / BLOCKED / WAITING / UNKNOWN — a stage is only ever
# included in critical_path when this module actually evaluated real data
# for it; there is no "always show all 15 stages" template.
@dataclass
class CriticalPathStage:
    stage: str
    status: str
    reason: str
    record_type: str | None = None
    record_id: str | None = None
    next_action: str | None = None


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
    critical_path: list[CriticalPathStage] = field(default_factory=list)
    technician_authorization: str = (
        "UNKNOWN — no task on this work order has an assigned technician yet"
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

    material_blockers: list[RecoveryBlocker] = []
    if shortages:
        all_requests = procurement_service.list_requests(db, organization_id=organization_id)
        all_pos = purchase_order_service.list_purchase_orders(db, organization_id=organization_id)
        for requirement in shortages:
            material_blocker = _material_blocker(requirement, work_order_id, all_requests, all_pos)
            material_blockers.append(material_blocker)
            status.blockers.append(material_blocker)

    tasks = work_order_service.list_tasks_for_work_order(
        db, organization_id=organization_id, work_order_id=work_order_id
    )
    technician_stage = _technician_stage(db, organization_id, tasks)
    if technician_stage is not None:
        status.technician_authorization = technician_stage.reason
        if technician_stage.status == "BLOCKED":
            status.blockers.append(
                RecoveryBlocker(
                    category="TECHNICIAN",
                    description=technician_stage.reason,
                    record_type="Task",
                    record_id=technician_stage.record_id,
                    who_should_act="Maintenance Manager",
                    dependency="Assign an authorized technician or resolve the qualification gap.",
                )
            )

    status.critical_path = _build_critical_path(
        readiness=readiness,
        requirements=requirements,
        shortages=shortages,
        material_blockers=material_blockers,
        technician_stage=technician_stage,
    )

    status.data_completeness = (
        "Covers AOG event blockers, release readiness (task execution / evidence / "
        "inspection), TAT, material shortages with their procurement/PO/receiving "
        "state, and technician authorization for any assigned task. Part lead-time/ETA "
        "and compliance sync are not backend-tracked and are reported as such rather "
        "than fabricated."
    )

    _set_next_best_action(status)
    return status


def _technician_stage(
    db: Session, organization_id: uuid.UUID, tasks: list
) -> CriticalPathStage | None:
    """Real technician-authorization stage for the AOG work order's tasks.

    Applicable only when at least one task actually has an assigned
    technician — otherwise there is nothing real to report beyond "no
    assignment exists yet", which is itself returned as an UNKNOWN stage
    rather than omitted, since it is a genuine (if incomplete) fact.
    """
    assigned = [t for t in tasks if t.assigned_technician_user_id is not None]
    if not assigned:
        if not tasks:
            return None
        return CriticalPathStage(
            stage="TECHNICIAN",
            status="UNKNOWN",
            reason="No task on this work order has an assigned technician yet.",
        )

    task = assigned[0]
    result = technician_service.check_authorization(
        db,
        organization_id=organization_id,
        task_id=task.id,
        technician_user_id=task.assigned_technician_user_id,
    )
    stage_status = "COMPLETE" if result.status == "AUTHORIZED" else "BLOCKED"
    return CriticalPathStage(
        stage="TECHNICIAN",
        status=stage_status,
        reason=f"{result.status}: {result.reason}",
        record_type="Task",
        record_id=str(task.id),
        next_action=None if stage_status == "COMPLETE" else "Assign an authorized technician.",
    )


_MATERIAL_STAGE_ORDER = ["PART", "PROCUREMENT", "PURCHASE_ORDER", "RECEIVING"]
_MATERIAL_CATEGORY_TO_BLOCKED_STAGE = {
    "MATERIAL_NOT_REQUESTED": "PART",
    "MATERIAL_AWAITING_APPROVAL": "PROCUREMENT",
    "MATERIAL_PO_NOT_SENT": "PURCHASE_ORDER",
    "MATERIAL_AWAITING_RECEIPT": "RECEIVING",
    "MATERIAL_SHORT": "PART",
}


def _build_critical_path(
    *,
    readiness,
    requirements: list,
    shortages: list,
    material_blockers: list[RecoveryBlocker],
    technician_stage: CriticalPathStage | None,
) -> list[CriticalPathStage]:
    path: list[CriticalPathStage] = []

    # Material chain — only applicable when this work order has part
    # requirements at all. Exactly one blocked stage per shortage's real
    # position in the chain; upstream stages are COMPLETE, downstream
    # stages are WAITING (never independently BLOCKED while an upstream
    # blocker is the real cause), matching the actual dependency order.
    if requirements:
        if not shortages:
            for stage_name in _MATERIAL_STAGE_ORDER:
                path.append(
                    CriticalPathStage(
                        stage=stage_name,
                        status="COMPLETE",
                        reason="No part shortage is blocking this work order.",
                    )
                )
        else:
            blocked_stage_names = {
                _MATERIAL_CATEGORY_TO_BLOCKED_STAGE.get(b.category) for b in material_blockers
            }
            first_blocked_index = min(
                (
                    _MATERIAL_STAGE_ORDER.index(name)
                    for name in blocked_stage_names
                    if name in _MATERIAL_STAGE_ORDER
                ),
                default=0,
            )
            representative = next(
                (
                    b
                    for b in material_blockers
                    if _MATERIAL_CATEGORY_TO_BLOCKED_STAGE.get(b.category)
                    == _MATERIAL_STAGE_ORDER[first_blocked_index]
                ),
                material_blockers[0],
            )
            for i, stage_name in enumerate(_MATERIAL_STAGE_ORDER):
                if i < first_blocked_index:
                    path.append(
                        CriticalPathStage(stage=stage_name, status="COMPLETE", reason="Resolved.")
                    )
                elif i == first_blocked_index:
                    path.append(
                        CriticalPathStage(
                            stage=stage_name,
                            status="BLOCKED",
                            reason=representative.description,
                            record_type=representative.record_type,
                            record_id=representative.record_id,
                            next_action=representative.dependency,
                        )
                    )
                else:
                    waiting_reason = (
                        f"Waiting on the {_MATERIAL_STAGE_ORDER[first_blocked_index]} stage above."
                    )
                    path.append(
                        CriticalPathStage(stage=stage_name, status="WAITING", reason=waiting_reason)
                    )

    # Task/evidence/inspection — reuse release_readiness_service's own
    # blocker categories directly; never re-derive completion logic.
    readiness_categories = {b.category for b in readiness.blockers}
    for stage_name, category in (
        ("EXECUTION", "TASK_EXECUTION"),
        ("EVIDENCE", "EVIDENCE"),
        ("INSPECTION_RII", "INSPECTION"),
    ):
        if category in readiness_categories:
            b = next(x for x in readiness.blockers if x.category == category)
            path.append(
                CriticalPathStage(
                    stage=stage_name,
                    status="BLOCKED",
                    reason=b.description,
                    record_type=category,
                    record_id=str(b.related_record_id) if b.related_record_id else None,
                    next_action=_dependency_for_category(category),
                )
            )
        else:
            path.append(
                CriticalPathStage(
                    stage=stage_name, status="COMPLETE", reason="No blocker recorded."
                )
            )

    if technician_stage is not None:
        path.append(technician_stage)

    path.append(
        CriticalPathStage(
            stage="RELEASE_READINESS",
            status="COMPLETE" if readiness.status == "READY" else "BLOCKED",
            reason=(
                "Release readiness is READY."
                if readiness.status == "READY"
                else f"Release readiness is BLOCKED by {len(readiness.blockers)} blocker(s)."
            ),
        )
    )

    return path


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
