"""Tool registry for the Lisa agent.

Every tool wraps an EXISTING backend service — nothing here recomputes or
reimplements business logic. Every handler takes organization_id from the
authenticated caller ONLY (never from model/tool input), exactly like every
existing v1 endpoint.

Domain boundary (read before adding a tool): as of M3.1-M3.14, this backend
has real, database-backed Aircraft / WorkOrder / Task / Evidence /
InspectionRequirement / TAT / ReleaseReadiness / Part / PartRequirement /
InventoryTransaction / Vendor / VendorPartAvailability (vendor fit) /
ProcurementRequest / PurchaseOrder / AogEvent / MaintenanceRequirement /
DeferredItem / ComplianceAssessment / RegulatoryDocument / MRO Control
Center domains — tools below cover all of them. Regulatory *applicability
rules* (condition-tree evaluation) and aircraft flight-hour/cycle
utilization remain NOT backend-resident (see compliance.py/
maintenance_service.py docstrings) — do not add tools that would let the
model answer as if those existed.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.core.errors import AeroComplyError, ForbiddenError
from app.core.permissions import Permission, permissions_for_roles
from app.schemas.auth import CurrentUser
from app.services import (
    aircraft_service,
    aog_recovery_service,
    aog_service,
    compliance_service,
    control_center_service,
    deferred_item_service,
    evidence_service,
    inspection_service,
    inventory_transaction_service,
    maintenance_service,
    part_requirement_service,
    part_service,
    proactive_service,
    procurement_service,
    purchase_order_service,
    regulatory_service,
    release_readiness_service,
    tat_service,
    vendor_fit_service,
    vendor_service,
    work_order_service,
)

ToolHandler = Callable[[Session, CurrentUser, dict[str, Any]], dict[str, Any]]


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    input_schema: dict[str, Any]
    handler: ToolHandler
    # Every tool maps to the SAME permission its equivalent REST endpoint
    # requires (see the matching app/api/v1/*.py router) — Lisa never grants
    # a caller access to data their role couldn't already read directly.
    required_permission: Permission


def _require_permission(user: CurrentUser, permission: Permission) -> None:
    if permission.value not in permissions_for_roles(user.roles):
        raise ForbiddenError(
            f"Role does not have permission {permission.value}", code="forbidden"
        )


def _uuid(raw: Any, field: str) -> uuid.UUID:
    try:
        return uuid.UUID(str(raw))
    except (ValueError, TypeError) as exc:
        raise AeroComplyError(
            f"Invalid UUID for {field}: {raw!r}", code="invalid_tool_input"
        ) from exc


def _aircraft_to_dict(a: Any) -> dict[str, Any]:
    return {
        "id": str(a.id),
        "registration": a.registration,
        "msn": a.msn,
        "aircraft_type": a.aircraft_type,
        "status": a.status,
    }


def _work_order_to_dict(w: Any) -> dict[str, Any]:
    return {
        "id": str(w.id),
        "aircraft_id": str(w.aircraft_id),
        "work_order_number": w.work_order_number,
        "status": w.status,
        "priority": w.priority,
    }


def _task_to_dict(t: Any) -> dict[str, Any]:
    return {
        "id": str(t.id),
        "work_order_id": str(t.work_order_id),
        "status": getattr(t, "status", None),
        "description": getattr(t, "description", None),
    }


def _evidence_to_dict(e: Any) -> dict[str, Any]:
    return {
        "id": str(e.id),
        "task_id": str(e.task_id),
        "status": e.status,
        "uploaded_by_user_id": str(e.uploaded_by_user_id) if e.uploaded_by_user_id else None,
    }


def _inspection_to_dict(i: Any) -> dict[str, Any]:
    return {
        "id": str(i.id),
        "task_id": str(i.task_id),
        "work_order_id": str(i.work_order_id),
        "required": i.required,
        "status": i.status,
    }


def _handle_get_aircraft(db: Session, user: CurrentUser, args: dict[str, Any]) -> dict[str, Any]:
    aircraft_id = _uuid(args["aircraft_id"], "aircraft_id")
    aircraft = aircraft_service.get_aircraft(
        db, organization_id=user.organization_id, aircraft_id=aircraft_id
    )
    return _aircraft_to_dict(aircraft)


def _handle_list_aircraft(db: Session, user: CurrentUser, args: dict[str, Any]) -> dict[str, Any]:
    items = aircraft_service.list_aircraft(db, organization_id=user.organization_id)
    return {"aircraft": [_aircraft_to_dict(a) for a in items]}


def _handle_get_work_order(db: Session, user: CurrentUser, args: dict[str, Any]) -> dict[str, Any]:
    work_order_id = _uuid(args["work_order_id"], "work_order_id")
    wo = work_order_service.get_work_order(
        db, organization_id=user.organization_id, work_order_id=work_order_id
    )
    return _work_order_to_dict(wo)


def _handle_get_work_order_tasks(
    db: Session, user: CurrentUser, args: dict[str, Any]
) -> dict[str, Any]:
    work_order_id = _uuid(args["work_order_id"], "work_order_id")
    tasks = work_order_service.list_tasks_for_work_order(
        db, organization_id=user.organization_id, work_order_id=work_order_id
    )
    return {"tasks": [_task_to_dict(t) for t in tasks]}


def _handle_get_evidence(db: Session, user: CurrentUser, args: dict[str, Any]) -> dict[str, Any]:
    evidence_id = _uuid(args["evidence_id"], "evidence_id")
    evidence = evidence_service.get_evidence(
        db, organization_id=user.organization_id, evidence_id=evidence_id
    )
    return _evidence_to_dict(evidence)


def _handle_list_evidence_for_task(
    db: Session, user: CurrentUser, args: dict[str, Any]
) -> dict[str, Any]:
    task_id = _uuid(args["task_id"], "task_id")
    items = evidence_service.list_evidence_for_task(
        db, organization_id=user.organization_id, task_id=task_id
    )
    return {"evidence": [_evidence_to_dict(e) for e in items]}


def _handle_get_inspection(db: Session, user: CurrentUser, args: dict[str, Any]) -> dict[str, Any]:
    inspection_id = _uuid(args["inspection_id"], "inspection_id")
    requirement = inspection_service.get_inspection_requirement(
        db, organization_id=user.organization_id, requirement_id=inspection_id
    )
    return _inspection_to_dict(requirement)


def _handle_list_inspections_for_work_order(
    db: Session, user: CurrentUser, args: dict[str, Any]
) -> dict[str, Any]:
    work_order_id = _uuid(args["work_order_id"], "work_order_id")
    items = inspection_service.list_inspection_requirements_for_work_order(
        db, organization_id=user.organization_id, work_order_id=work_order_id
    )
    return {"inspections": [_inspection_to_dict(i) for i in items]}


def _handle_get_tat(db: Session, user: CurrentUser, args: dict[str, Any]) -> dict[str, Any]:
    work_order_id = _uuid(args["work_order_id"], "work_order_id")
    status = tat_service.get_work_order_tat_status(
        db, organization_id=user.organization_id, work_order_id=work_order_id
    )
    return {
        "work_order_id": str(work_order_id),
        "status": status.status,
        "due_date": status.due_date.isoformat() if status.due_date else None,
        "reason": status.reason,
    }


def _handle_get_fleet_tat(db: Session, user: CurrentUser, args: dict[str, Any]) -> dict[str, Any]:
    summary = tat_service.get_fleet_tat_status(db, organization_id=user.organization_id)
    return {
        "on_track_count": summary.on_track_count,
        "at_risk_count": summary.at_risk_count,
        "delayed_count": summary.delayed_count,
        "unknown_count": summary.unknown_count,
        "total_work_orders": summary.total_work_orders,
        "reason": summary.reason,
    }


def _handle_get_release_readiness(
    db: Session, user: CurrentUser, args: dict[str, Any]
) -> dict[str, Any]:
    work_order_id = _uuid(args["work_order_id"], "work_order_id")
    readiness = release_readiness_service.get_release_readiness_for_work_order(
        db, organization_id=user.organization_id, work_order_id=work_order_id
    )
    return {
        "work_order_id": str(work_order_id),
        "status": readiness.status,
        "blockers": [
            {"category": b.category, "description": b.description} for b in readiness.blockers
        ],
        "data_completeness": readiness.data_completeness,
    }


def _handle_get_parts(db: Session, user: CurrentUser, args: dict[str, Any]) -> dict[str, Any]:
    parts = part_service.list_parts(db, organization_id=user.organization_id)
    return {
        "parts": [
            {
                "id": str(p.id),
                "part_number": p.part_number,
                "description": p.description,
                "serviceability_status": p.serviceability_status,
                "quantity_on_hand": p.quantity_on_hand,
                "quantity_reserved": p.quantity_reserved,
                "quantity_quarantined": p.quantity_quarantined,
                "available_quantity": p.available_quantity,
            }
            for p in parts
        ]
    }


def _handle_get_shortages_for_work_order(
    db: Session, user: CurrentUser, args: dict[str, Any]
) -> dict[str, Any]:
    work_order_id = _uuid(args["work_order_id"], "work_order_id")
    requirements = part_requirement_service.list_part_requirements_for_work_order(
        db, organization_id=user.organization_id, work_order_id=work_order_id
    )
    return {
        "requirements": [
            {
                "id": str(r.id),
                "part_id": str(r.part_id),
                "required_quantity": r.required_quantity,
                "fulfilled_quantity": r.fulfilled_quantity,
                "status": r.status,
            }
            for r in requirements
        ]
    }


def _handle_get_inventory_transactions(
    db: Session, user: CurrentUser, args: dict[str, Any]
) -> dict[str, Any]:
    part_id = _uuid(args["part_id"], "part_id")
    transactions = inventory_transaction_service.list_transactions_for_part(
        db, organization_id=user.organization_id, part_id=part_id
    )
    return {
        "transactions": [
            {
                "id": str(t.id),
                "transaction_type": t.transaction_type,
                "on_hand_delta": t.on_hand_delta,
                "reserved_delta": t.reserved_delta,
            }
            for t in transactions
        ]
    }


def _handle_get_vendors(db: Session, user: CurrentUser, args: dict[str, Any]) -> dict[str, Any]:
    vendors = vendor_service.list_vendors(db, organization_id=user.organization_id)
    return {
        "vendors": [
            {
                "id": str(v.id),
                "name": v.name,
                "approved": v.approved,
                "reliability_score": v.reliability_score,
            }
            for v in vendors
        ]
    }


def _handle_get_vendor_fit(db: Session, user: CurrentUser, args: dict[str, Any]) -> dict[str, Any]:
    part_id = _uuid(args["part_id"], "part_id")
    results = vendor_fit_service.score_vendor_options_for_part(
        db, organization_id=user.organization_id, part_id=part_id
    )
    return {
        "results": [
            {
                "vendor_id": str(r.vendor_id),
                "vendor_name": r.vendor_name,
                "score": r.score,
                "confidence": r.confidence,
                "factors": r.factors,
                "missing_factors": r.missing_factors,
            }
            for r in results
        ]
    }


def _handle_get_procurement_requests(
    db: Session, user: CurrentUser, args: dict[str, Any]
) -> dict[str, Any]:
    status = args.get("status")
    requests = procurement_service.list_requests(
        db, organization_id=user.organization_id, status=status
    )
    return {
        "requests": [
            {
                "id": str(r.id),
                "aircraft_id": str(r.aircraft_id),
                "part_number": r.part_number,
                "quantity": r.quantity,
                "priority": r.priority,
                "status": r.status,
            }
            for r in requests
        ]
    }


def _handle_get_purchase_orders(
    db: Session, user: CurrentUser, args: dict[str, Any]
) -> dict[str, Any]:
    status = args.get("status")
    purchase_orders = purchase_order_service.list_purchase_orders(
        db, organization_id=user.organization_id, status=status
    )
    return {
        "purchase_orders": [
            {
                "id": str(po.id),
                "po_number": po.po_number,
                "vendor_id": str(po.vendor_id),
                "status": po.status,
                "total_cents": po.total_cents,
            }
            for po in purchase_orders
        ]
    }


def _handle_get_aog_events(db: Session, user: CurrentUser, args: dict[str, Any]) -> dict[str, Any]:
    aircraft_id = args.get("aircraft_id")
    status = args.get("status")
    events = aog_service.list_aog_events(
        db,
        organization_id=user.organization_id,
        status=status,
        aircraft_id=_uuid(aircraft_id, "aircraft_id") if aircraft_id else None,
    )
    return {
        "events": [
            {
                "id": str(e.id),
                "aircraft_id": str(e.aircraft_id),
                "status": e.status,
                "severity": e.severity,
                "root_cause": e.root_cause,
                "blockers": [
                    {
                        "blocker_type": b.blocker_type,
                        "description": b.description,
                        "resolved": b.resolved,
                    }
                    for b in e.blockers
                ],
            }
            for e in events
        ]
    }


def _handle_get_aog_recovery_status(
    db: Session, user: CurrentUser, args: dict[str, Any]
) -> dict[str, Any]:
    status = aog_recovery_service.get_recovery_status(
        db,
        organization_id=user.organization_id,
        aircraft_id=_uuid(args["aircraft_id"], "aircraft_id"),
    )
    return {
        "aircraft_id": status.aircraft_id,
        "registration": status.registration,
        "is_aog": status.is_aog,
        "aog_event_id": status.aog_event_id,
        "aog_status": status.aog_status,
        "severity": status.severity,
        "work_order_id": status.work_order_id,
        "release_readiness_status": status.release_readiness_status,
        "tat_status": status.tat_status,
        "tat_reason": status.tat_reason,
        "blockers": [
            {
                "category": b.category,
                "description": b.description,
                "record_type": b.record_type,
                "record_id": b.record_id,
                "who_should_act": b.who_should_act,
                "dependency": b.dependency,
            }
            for b in status.blockers
        ],
        "next_best_action": (
            {
                "category": status.next_best_action.category,
                "description": status.next_best_action.description,
                "who_should_act": status.next_best_action.who_should_act,
                "dependency": status.next_best_action.dependency,
            }
            if status.next_best_action
            else None
        ),
        "technician_authorization": status.technician_authorization,
        "eta": status.eta,
        "compliance_status": status.compliance_status,
        "data_completeness": status.data_completeness,
    }


def _handle_get_maintenance_due(
    db: Session, user: CurrentUser, args: dict[str, Any]
) -> dict[str, Any]:
    aircraft_id = _uuid(args["aircraft_id"], "aircraft_id")
    due_items = maintenance_service.get_maintenance_due_for_aircraft(
        db, organization_id=user.organization_id, aircraft_id=aircraft_id
    )
    return {
        "due_items": [
            {
                "requirement_description": item.requirement.description,
                "due_status": item.due_status,
                "due_date": item.due_date.isoformat() if item.due_date else None,
                "reason": item.reason,
            }
            for item in due_items
        ]
    }


def _handle_get_deferred_items(
    db: Session, user: CurrentUser, args: dict[str, Any]
) -> dict[str, Any]:
    aircraft_id = _uuid(args["aircraft_id"], "aircraft_id")
    open_only = bool(args.get("open_only", True))
    items = deferred_item_service.list_deferred_items_for_aircraft(
        db, organization_id=user.organization_id, aircraft_id=aircraft_id, open_only=open_only
    )
    return {
        "deferred_items": [
            {
                "id": str(i.id),
                "description": i.description,
                "category": i.category,
                "status": i.status,
                "due_at": i.due_at.isoformat() if i.due_at else None,
                "approval_status": i.approval_status,
            }
            for i in items
        ]
    }


def _handle_get_compliance_assessments(
    db: Session, user: CurrentUser, args: dict[str, Any]
) -> dict[str, Any]:
    aircraft_id = _uuid(args["aircraft_id"], "aircraft_id")
    assessments = compliance_service.list_assessments_for_aircraft(
        db, organization_id=user.organization_id, aircraft_id=aircraft_id
    )
    return {
        "assessments": [
            {
                "id": str(a.id),
                "requirement_id": str(a.requirement_id),
                "status": a.status,
                "evaluated_at": a.evaluated_at.isoformat(),
            }
            for a in assessments
        ]
    }


def _handle_get_regulatory_documents(
    db: Session, user: CurrentUser, args: dict[str, Any]
) -> dict[str, Any]:
    authority = args.get("authority")
    documents = regulatory_service.list_documents(
        db, organization_id=user.organization_id, authority=authority
    )
    return {
        "documents": [
            {
                "id": str(d.id),
                "authority": d.authority,
                "doc_number": d.doc_number,
                "title": d.title,
                "sync_status": d.sync_status,
            }
            for d in documents
        ]
    }


def _handle_get_regulatory_provider_status(
    db: Session, user: CurrentUser, args: dict[str, Any]
) -> dict[str, Any]:
    statuses = regulatory_service.get_provider_status()
    return {"providers": [s.model_dump() for s in statuses]}


def _handle_get_control_center_summary(
    db: Session, user: CurrentUser, args: dict[str, Any]
) -> dict[str, Any]:
    summary = control_center_service.get_summary(db, organization_id=user.organization_id)
    return summary.model_dump()


def _handle_get_control_center_fleet(
    db: Session, user: CurrentUser, args: dict[str, Any]
) -> dict[str, Any]:
    rows = control_center_service.get_fleet_rows(db, organization_id=user.organization_id)
    return {"fleet": [r.model_dump(mode="json") for r in rows]}


def _handle_get_proactive_alerts(
    db: Session, user: CurrentUser, args: dict[str, Any]
) -> dict[str, Any]:
    alerts = proactive_service.get_proactive_alerts(db, organization_id=user.organization_id)
    return {"alerts": [a.model_dump(mode="json") for a in alerts]}


def _handle_get_daily_brief(db: Session, user: CurrentUser, args: dict[str, Any]) -> dict[str, Any]:
    brief = proactive_service.get_daily_brief(db, organization_id=user.organization_id)
    return brief.model_dump(mode="json")


TOOL_REGISTRY: list[ToolSpec] = [
    ToolSpec(
        name="get_aircraft",
        description="Get one aircraft by id: registration, MSN, type, status.",
        input_schema={
            "type": "object",
            "properties": {"aircraft_id": {"type": "string", "description": "Aircraft UUID"}},
            "required": ["aircraft_id"],
        },
        handler=_handle_get_aircraft,
    
    required_permission=Permission.AIRCRAFT_READ,
    ),
    ToolSpec(
        name="list_aircraft",
        description="List all aircraft in the caller's organization.",
        input_schema={"type": "object", "properties": {}},
        handler=_handle_list_aircraft,
    
    required_permission=Permission.AIRCRAFT_READ,
    ),
    ToolSpec(
        name="get_work_order",
        description="Get one work order by id: aircraft, number, status, priority.",
        input_schema={
            "type": "object",
            "properties": {"work_order_id": {"type": "string", "description": "Work order UUID"}},
            "required": ["work_order_id"],
        },
        handler=_handle_get_work_order,
    
    required_permission=Permission.AIRCRAFT_READ,
    ),
    ToolSpec(
        name="get_work_order_tasks",
        description="List the tasks belonging to a work order.",
        input_schema={
            "type": "object",
            "properties": {"work_order_id": {"type": "string", "description": "Work order UUID"}},
            "required": ["work_order_id"],
        },
        handler=_handle_get_work_order_tasks,
    
    required_permission=Permission.AIRCRAFT_READ,
    ),
    ToolSpec(
        name="get_evidence",
        description="Get one evidence record by id: task, status, uploader.",
        input_schema={
            "type": "object",
            "properties": {"evidence_id": {"type": "string", "description": "Evidence UUID"}},
            "required": ["evidence_id"],
        },
        handler=_handle_get_evidence,
    
    required_permission=Permission.EVIDENCE_READ,
    ),
    ToolSpec(
        name="list_evidence_for_task",
        description="List all evidence records for a task.",
        input_schema={
            "type": "object",
            "properties": {"task_id": {"type": "string", "description": "Task UUID"}},
            "required": ["task_id"],
        },
        handler=_handle_list_evidence_for_task,
    
    required_permission=Permission.EVIDENCE_READ,
    ),
    ToolSpec(
        name="get_inspection",
        description="Get one inspection requirement by id: task, work order, required, status.",
        input_schema={
            "type": "object",
            "properties": {
                "inspection_id": {"type": "string", "description": "Inspection requirement UUID"}
            },
            "required": ["inspection_id"],
        },
        handler=_handle_get_inspection,
    
    required_permission=Permission.INSPECTION_READ,
    ),
    ToolSpec(
        name="list_inspections_for_work_order",
        description="List the inspection requirements (including RII) attached to a work order.",
        input_schema={
            "type": "object",
            "properties": {"work_order_id": {"type": "string", "description": "Work order UUID"}},
            "required": ["work_order_id"],
        },
        handler=_handle_list_inspections_for_work_order,
    
    required_permission=Permission.INSPECTION_READ,
    ),
    ToolSpec(
        name="get_tat",
        description=(
            "Get TAT (turnaround time) status for one work order: ON_TRACK/AT_RISK/DELAYED/UNKNOWN "
            "with reason."
        ),
        input_schema={
            "type": "object",
            "properties": {"work_order_id": {"type": "string", "description": "Work order UUID"}},
            "required": ["work_order_id"],
        },
        handler=_handle_get_tat,
    
    required_permission=Permission.AIRCRAFT_READ,
    ),
    ToolSpec(
        name="get_fleet_tat",
        description="Get TAT status counts across the whole fleet's work orders.",
        input_schema={"type": "object", "properties": {}},
        handler=_handle_get_fleet_tat,
    
    required_permission=Permission.AIRCRAFT_READ,
    ),
    ToolSpec(
        name="get_release_readiness",
        description=(
            "Get the deterministic release-readiness gate result (READY/BLOCKED) for a work order, "
            "with the exact blockers found."
        ),
        input_schema={
            "type": "object",
            "properties": {"work_order_id": {"type": "string", "description": "Work order UUID"}},
            "required": ["work_order_id"],
        },
        handler=_handle_get_release_readiness,
    
    required_permission=Permission.AIRCRAFT_READ,
    ),
    ToolSpec(
        name="get_parts",
        description="List all parts in inventory with on-hand/reserved/available quantities.",
        input_schema={"type": "object", "properties": {}},
        handler=_handle_get_parts,
    
    required_permission=Permission.PART_READ,
    ),
    ToolSpec(
        name="get_shortages_for_work_order",
        description="List part requirements (and shortage status) for a work order.",
        input_schema={
            "type": "object",
            "properties": {"work_order_id": {"type": "string", "description": "Work order UUID"}},
            "required": ["work_order_id"],
        },
        handler=_handle_get_shortages_for_work_order,
    
    required_permission=Permission.PART_READ,
    ),
    ToolSpec(
        name="get_inventory_transactions",
        description=(
            "List inventory movement history (receive/reserve/release/consume/adjust) for a part."
        ),
        input_schema={
            "type": "object",
            "properties": {"part_id": {"type": "string", "description": "Part UUID"}},
            "required": ["part_id"],
        },
        handler=_handle_get_inventory_transactions,
    
    required_permission=Permission.PART_READ,
    ),
    ToolSpec(
        name="get_vendors",
        description="List all vendors with approval status and reliability score.",
        input_schema={"type": "object", "properties": {}},
        handler=_handle_get_vendors,
    
    required_permission=Permission.VENDOR_READ,
    ),
    ToolSpec(
        name="get_vendor_fit",
        description=(
            "Get ranked, explainable vendor recommendations for a part (score, confidence, "
            "factors, missing_factors). A null score means insufficient data, never a "
            "fabricated ranking."
        ),
        input_schema={
            "type": "object",
            "properties": {"part_id": {"type": "string", "description": "Part UUID"}},
            "required": ["part_id"],
        },
        handler=_handle_get_vendor_fit,
    
    required_permission=Permission.VENDOR_READ,
    ),
    ToolSpec(
        name="get_procurement_requests",
        description=(
            "List procurement (part) requests, optionally filtered by status "
            "(SUBMITTED/UNDER_REVIEW/APPROVED/REJECTED/CLARIFICATION_REQUIRED/ORDERED/RECEIVED/CLOSED)."
        ),
        input_schema={
            "type": "object",
            "properties": {"status": {"type": "string", "description": "Optional status filter"}},
        },
        handler=_handle_get_procurement_requests,
    
    required_permission=Permission.PROCUREMENT_READ,
    ),
    ToolSpec(
        name="get_purchase_orders",
        description=(
            "List purchase orders, optionally filtered by status "
            "(DRAFT/PENDING_APPROVAL/APPROVED/SENT/ACKNOWLEDGED/PARTIALLY_RECEIVED/RECEIVED/CANCELLED)."
        ),
        input_schema={
            "type": "object",
            "properties": {"status": {"type": "string", "description": "Optional status filter"}},
        },
        handler=_handle_get_purchase_orders,
    
    required_permission=Permission.PROCUREMENT_READ,
    ),
    ToolSpec(
        name="get_aog_events",
        description=(
            "List AOG (Aircraft On Ground) events, optionally filtered by aircraft_id "
            "and/or status (DECLARED/IN_RECOVERY/RECOVERED/CANCELLED), including "
            "recorded blockers."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "aircraft_id": {"type": "string", "description": "Optional aircraft UUID filter"},
                "status": {"type": "string", "description": "Optional status filter"},
            },
        },
        handler=_handle_get_aog_events,

    required_permission=Permission.AIRCRAFT_READ,
    ),
    ToolSpec(
        name="get_aog_recovery_status",
        description=(
            "Get the synthesized recovery status for one aircraft: whether it is "
            "currently AOG, the active AOG event, release readiness, TAT, and every "
            "real blocker (task execution, evidence, inspection/RII, and material "
            "shortages with their exact procurement/PO/receiving state), ranked into "
            "a single next-best-action. Never fabricates technician authorization, "
            "ETA, or compliance sync — those are reported as NOT_TRACKED/UNKNOWN when "
            "no backend record exists."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "aircraft_id": {"type": "string", "description": "Aircraft UUID"},
            },
            "required": ["aircraft_id"],
        },
        handler=_handle_get_aog_recovery_status,

    required_permission=Permission.AIRCRAFT_READ,
    ),
    ToolSpec(
        name="get_maintenance_due",
        description=(
            "Get maintenance-due status for an aircraft's applicable requirements "
            "(OVERDUE/DUE_SOON/NOT_DUE/UNKNOWN with reason)."
        ),
        input_schema={
            "type": "object",
            "properties": {"aircraft_id": {"type": "string", "description": "Aircraft UUID"}},
            "required": ["aircraft_id"],
        },
        handler=_handle_get_maintenance_due,
    
    required_permission=Permission.AIRCRAFT_READ,
    ),
    ToolSpec(
        name="get_deferred_items",
        description="List deferred items / MEL for an aircraft (open_only defaults to true).",
        input_schema={
            "type": "object",
            "properties": {
                "aircraft_id": {"type": "string", "description": "Aircraft UUID"},
                "open_only": {"type": "boolean", "description": "Defaults to true"},
            },
            "required": ["aircraft_id"],
        },
        handler=_handle_get_deferred_items,
    
    required_permission=Permission.AIRCRAFT_READ,
    ),
    ToolSpec(
        name="get_compliance_assessments",
        description="List compliance assessments for an aircraft against regulatory requirements.",
        input_schema={
            "type": "object",
            "properties": {"aircraft_id": {"type": "string", "description": "Aircraft UUID"}},
            "required": ["aircraft_id"],
        },
        handler=_handle_get_compliance_assessments,
    
    required_permission=Permission.COMPLIANCE_ASSESS,
    ),
    ToolSpec(
        name="get_regulatory_documents",
        description=(
            "List regulatory documents (AD/SB/regulation/etc.), optionally filtered by authority "
            "(DGCA/FAA/EASA/CASA/UK_CAA)."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "authority": {"type": "string", "description": "Optional authority filter"}
            },
        },
        handler=_handle_get_regulatory_documents,
    
    required_permission=Permission.REGULATION_READ,
    ),
    ToolSpec(
        name="get_regulatory_provider_status",
        description=(
            "Get the live-sync configuration status for every regulatory authority. Always returns "
            "NOT_CONFIGURED today — no live feed exists — never claim synchronization beyond what "
            "this returns."
        ),
        input_schema={"type": "object", "properties": {}},
        handler=_handle_get_regulatory_provider_status,
    
    required_permission=Permission.REGULATION_READ,
    ),
    ToolSpec(
        name="get_control_center_summary",
        description=(
            "Get fleet-wide operational summary: aircraft counts by status "
            "(OPERATIONAL/UNDER_MAINTENANCE/AOG), open work orders, open deferred items, open part "
            "shortages."
        ),
        input_schema={"type": "object", "properties": {}},
        handler=_handle_get_control_center_summary,
    
    required_permission=Permission.AIRCRAFT_READ,
    ),
    ToolSpec(
        name="get_control_center_fleet",
        description=(
            "Get the per-aircraft operational control-center row for every aircraft (status, open "
            "work orders, open deferred items, open part shortages, active AOG event id)."
        ),
        input_schema={"type": "object", "properties": {}},
        handler=_handle_get_control_center_fleet,
        required_permission=Permission.AIRCRAFT_READ,
    ),
    ToolSpec(
        name="get_proactive_alerts",
        description=(
            "Get real, backend-derived operational alerts (AOG, part shortages, release "
            "blockers, overdue/due-soon deferred items, non-compliant assessments) — every "
            "alert traces to a real record, never fabricated."
        ),
        input_schema={"type": "object", "properties": {}},
        handler=_handle_get_proactive_alerts,
        required_permission=Permission.AIRCRAFT_READ,
    ),
    ToolSpec(
        name="get_daily_brief",
        description=(
            "Get the backend-authoritative daily brief: alert counts by severity and the top "
            "5 priorities, derived the same way as get_proactive_alerts."
        ),
        input_schema={"type": "object", "properties": {}},
        handler=_handle_get_daily_brief,
        required_permission=Permission.AIRCRAFT_READ,
    ),
]

TOOL_REGISTRY_BY_NAME: dict[str, ToolSpec] = {t.name: t for t in TOOL_REGISTRY}


def anthropic_tool_schemas() -> list[dict[str, Any]]:
    """Tool list in the shape the Anthropic Messages API expects."""
    return [
        {"name": t.name, "description": t.description, "input_schema": t.input_schema}
        for t in TOOL_REGISTRY
    ]


def execute_tool(db: Session, user: CurrentUser, name: str, args: dict[str, Any]) -> dict[str, Any]:
    spec = TOOL_REGISTRY_BY_NAME.get(name)
    if spec is None:
        raise AeroComplyError(f"Unknown tool: {name}", code="unknown_tool")
    _require_permission(user, spec.required_permission)
    return spec.handler(db, user, args)
