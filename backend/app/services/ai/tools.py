"""Tool registry for the Lisa agent.

Every tool wraps an EXISTING backend service (aircraft_service,
work_order_service, evidence_service, inspection_service) — nothing here
recomputes or reimplements business logic. Every handler takes
organization_id from the authenticated caller ONLY (never from model/tool
input), exactly like every existing v1 endpoint.

Domain boundary (read before adding a tool): this backend today only has
real, database-backed Aircraft / WorkOrder / Task / Evidence /
InspectionRequirement domains. TAT, vendor/procurement, regulatory
requirements, and operational-priority ranking are NOT backend-resident —
they exist only in the frontend mock engine
(frontend/lib/mock/ai/{engine,analytics,proactive}.ts). Do not add tools
for those areas; doing so would let the model "answer" with numbers that
don't exist in the real database. When a question needs one of those, the
agent's synthesis step must say so plainly rather than inventing a tool.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.core.errors import AeroComplyError
from app.schemas.auth import CurrentUser
from app.services import (
    aircraft_service,
    evidence_service,
    inspection_service,
    work_order_service,
)

ToolHandler = Callable[[Session, CurrentUser, dict[str, Any]], dict[str, Any]]


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    input_schema: dict[str, Any]
    handler: ToolHandler


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
    ),
    ToolSpec(
        name="list_aircraft",
        description="List all aircraft in the caller's organization.",
        input_schema={"type": "object", "properties": {}},
        handler=_handle_list_aircraft,
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
    return spec.handler(db, user, args)
