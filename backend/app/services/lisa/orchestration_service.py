"""Deterministic operational investigation planner/orchestrator.

Reuses execute_tool (app/services/ai/tools.py) exclusively for all
data access — this module contains ZERO duplicated domain-service logic.
Every fact in a synthesized answer traces directly to a real tool result.

Flow: classify_intent -> dispatch to an intent-specific investigation
function -> that function calls a small, bounded sequence of tools (never
more than MAX_TOOL_CALLS, never the same tool+args twice) -> builds a
compact ResultGraph of real identifiers -> returns an InvestigationResult
that agent_service can either use directly (deterministic answer, no LLM
needed) or fall back to the existing LLM tool-loop for (UNKNOWN intent).

This module never expresses chain-of-thought — InvestigationResult.
tools_invoked is a flat audit list of tool names actually called (for
auditability), not reasoning.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from app.core.errors import AeroComplyError, ForbiddenError, NotFoundError
from app.models.lisa_conversation_context import LisaConversationContext
from app.schemas.auth import CurrentUser
from app.services.ai.tools import execute_tool
from app.services.lisa.intent_service import Intent, classify_intent
from app.services.lisa.message_resolution_service import MessageResolution

MAX_TOOL_CALLS = 6


@dataclass
class RelatedRecord:
    label: str
    id: str


@dataclass
class InvestigationResult:
    intent: str
    status: str  # ANSWERED | NEEDS_ENTITY | NOT_FOUND | PERMISSION_DENIED | BACKEND_UNAVAILABLE
    headline: str
    tools_invoked: list[str] = field(default_factory=list)
    result_graph: dict[str, str] = field(default_factory=dict)
    what_i_found: list[str] = field(default_factory=list)
    why_it_matters: str | None = None
    next_step: str | None = None
    who_should_act: str | None = None
    related_records: list[RelatedRecord] = field(default_factory=list)


class _CallBudget:
    """Bounded, duplicate-call-safe tool executor shared by every
    investigation function below — the single place call-limit and
    duplicate-prevention logic lives.
    """

    def __init__(self, db: Session, user: CurrentUser) -> None:
        self.db = db
        self.user = user
        self.tools_invoked: list[str] = []
        self._seen: set[tuple[str, str]] = set()

    def call(self, tool_name: str, args: dict[str, Any]) -> dict[str, Any] | None:
        """Returns the tool result, or None if the call budget is
        exhausted or this exact (tool, args) pair was already called this
        turn (duplicate-call prevention) — callers must treat None as
        "stop, do not fabricate further investigation".
        """
        key = (tool_name, repr(sorted(args.items())))
        if key in self._seen:
            return None
        if len(self.tools_invoked) >= MAX_TOOL_CALLS:
            return None
        self._seen.add(key)
        result = execute_tool(self.db, self.user, tool_name, args)
        self.tools_invoked.append(tool_name)
        return result


def _needs_entity(intent: Intent, entity_label: str) -> InvestigationResult:
    article = "an" if entity_label[0] in "aeiou" else "a"
    return InvestigationResult(
        intent=intent.value,
        status="NEEDS_ENTITY",
        headline=f"I need {article} {entity_label} to investigate this — which one do you mean?",
    )


def _error_result(intent: Intent, exc: Exception, tools_invoked: list[str]) -> InvestigationResult:
    if isinstance(exc, ForbiddenError):
        return InvestigationResult(
            intent=intent.value,
            status="PERMISSION_DENIED",
            headline="You don't have permission to view this record.",
            tools_invoked=tools_invoked,
        )
    if isinstance(exc, NotFoundError):
        return InvestigationResult(
            intent=intent.value,
            status="NOT_FOUND",
            headline="I couldn't find that record.",
            tools_invoked=tools_invoked,
        )
    return InvestigationResult(
        intent=intent.value,
        status="BACKEND_UNAVAILABLE",
        headline="I couldn't retrieve that information right now.",
        tools_invoked=tools_invoked,
    )


def _investigate_aog(
    db: Session, user: CurrentUser, resolution: MessageResolution
) -> InvestigationResult:
    context = resolution.context
    if context.current_aircraft_id is None:
        return _needs_entity(Intent.AOG, "aircraft")

    budget = _CallBudget(db, user)
    try:
        result = budget.call(
            "get_aog_recovery_status", {"aircraft_id": str(context.current_aircraft_id)}
        )
    except AeroComplyError as exc:
        return _error_result(Intent.AOG, exc, budget.tools_invoked)
    if result is None:
        return InvestigationResult(
            intent=Intent.AOG.value,
            status="BACKEND_UNAVAILABLE",
            headline="I couldn't complete the AOG investigation within the tool-call budget.",
            tools_invoked=budget.tools_invoked,
        )

    graph: dict[str, str] = {
        "aircraft_id": result["aircraft_id"],
        "registration": result["registration"],
    }

    if not result["is_aog"]:
        return InvestigationResult(
            intent=Intent.AOG.value,
            status="ANSWERED",
            headline=f"{result['registration']} is not currently AOG.",
            tools_invoked=budget.tools_invoked,
            result_graph=graph,
            what_i_found=[
                f"{result['registration']} has no active DECLARED/IN_RECOVERY AOG event."
            ],
        )

    graph["aog_event_id"] = result["aog_event_id"]
    if result.get("work_order_id"):
        graph["work_order_id"] = result["work_order_id"]

    blockers = result.get("blockers", [])
    what_i_found = [b["description"] for b in blockers] or [
        "No specific blocker is recorded for this AOG event."
    ]

    nba = result.get("next_best_action")
    why_it_matters = None
    next_step = None
    who_should_act = None
    related: list[RelatedRecord] = []
    if nba:
        why_it_matters = (
            f"This is the highest-priority blocker on the real dependency chain to recovery "
            f"({nba['category'].replace('_', ' ').title()})."
        )
        next_step = nba["dependency"]
        who_should_act = nba["who_should_act"]
        if nba.get("record_id"):
            related.append(
                RelatedRecord(label=nba.get("record_type") or nba["category"], id=nba["record_id"])
            )
            if nba.get("record_type") == "PurchaseOrder":
                graph["purchase_order_id"] = nba["record_id"]
            elif nba.get("record_type") == "ProcurementRequest":
                graph["procurement_request_id"] = nba["record_id"]
            elif nba.get("record_type") == "PartRequirement":
                graph["part_requirement_id"] = nba["record_id"]
            elif nba.get("record_type") == "TASK_EXECUTION":
                # aog_recovery_service uses the blocker category as
                # record_type for task/evidence/inspection blockers — the
                # record_id is a real Task id in this case.
                graph["task_id"] = nba["record_id"]

    headline = (
        f"{result['registration']} remains AOG"
        + (f" — {nba['description']}" if nba else " with no recorded blocker.")
    )

    return InvestigationResult(
        intent=Intent.AOG.value,
        status="ANSWERED",
        headline=headline,
        tools_invoked=budget.tools_invoked,
        result_graph=graph,
        what_i_found=what_i_found,
        why_it_matters=why_it_matters,
        next_step=next_step,
        who_should_act=who_should_act,
        related_records=related,
    )


def _investigate_release_readiness(
    db: Session, user: CurrentUser, resolution: MessageResolution
) -> InvestigationResult:
    context = resolution.context
    if context.current_work_order_id is None:
        return _needs_entity(Intent.RELEASE_READINESS, "work order")

    budget = _CallBudget(db, user)
    try:
        result = budget.call(
            "get_release_readiness", {"work_order_id": str(context.current_work_order_id)}
        )
    except AeroComplyError as exc:
        return _error_result(Intent.RELEASE_READINESS, exc, budget.tools_invoked)
    if result is None:
        return InvestigationResult(
            intent=Intent.RELEASE_READINESS.value,
            status="BACKEND_UNAVAILABLE",
            headline="I couldn't complete the release-readiness investigation.",
            tools_invoked=budget.tools_invoked,
        )

    graph = {"work_order_id": str(context.current_work_order_id)}
    blockers = result.get("blockers", [])

    if result.get("status") == "READY":
        return InvestigationResult(
            intent=Intent.RELEASE_READINESS.value,
            status="ANSWERED",
            headline="This work order is release-ready.",
            tools_invoked=budget.tools_invoked,
            result_graph=graph,
            what_i_found=["Release readiness is READY — no open task/evidence/inspection blocker."],
        )

    what_i_found = [b["description"] for b in blockers] or [
        "Release readiness is BLOCKED but no specific blocker was returned."
    ]
    related = [
        RelatedRecord(label=b["category"], id=str(b["related_record_id"]))
        for b in blockers
        if b.get("related_record_id")
    ]
    # A blocking TASK_EXECUTION record_id IS a task id — carry it forward so
    # a follow-up ("who is assigned?") can resolve the technician without
    # re-asking the user which task they mean.
    task_blocker = next((b for b in blockers if b["category"] == "TASK_EXECUTION"), None)
    if task_blocker and task_blocker.get("related_record_id"):
        graph["task_id"] = str(task_blocker["related_record_id"])

    return InvestigationResult(
        intent=Intent.RELEASE_READINESS.value,
        status="ANSWERED",
        headline=f"This work order is BLOCKED from release by {len(blockers)} blocker(s).",
        tools_invoked=budget.tools_invoked,
        result_graph=graph,
        what_i_found=what_i_found,
        why_it_matters="Every blocker below must clear before release readiness can be READY.",
        next_step="Resolve the listed blockers (task execution / evidence / inspection).",
        who_should_act="Assigned technician / independent inspector as applicable.",
        related_records=related,
    )


def _investigate_technician_authorization(
    db: Session, user: CurrentUser, resolution: MessageResolution
) -> InvestigationResult:
    context = resolution.context
    if context.current_task_id is None:
        return _needs_entity(Intent.TECHNICIAN_AUTHORIZATION, "task")

    budget = _CallBudget(db, user)
    try:
        task = budget.call("get_task", {"task_id": str(context.current_task_id)})
    except AeroComplyError as exc:
        return _error_result(Intent.TECHNICIAN_AUTHORIZATION, exc, budget.tools_invoked)
    if task is None:
        return InvestigationResult(
            intent=Intent.TECHNICIAN_AUTHORIZATION.value,
            status="BACKEND_UNAVAILABLE",
            headline="I couldn't retrieve that task right now.",
            tools_invoked=budget.tools_invoked,
        )

    graph = {"task_id": task["id"]}
    technician_id = context.current_technician_user_id and str(context.current_technician_user_id)
    technician_id = technician_id or task.get("assigned_technician_user_id")

    if not technician_id:
        return InvestigationResult(
            intent=Intent.TECHNICIAN_AUTHORIZATION.value,
            status="ANSWERED",
            headline="No technician is currently assigned to this task.",
            tools_invoked=budget.tools_invoked,
            result_graph=graph,
            what_i_found=["Task has no assigned_technician_user_id."],
            next_step="Assign a technician to this task.",
            who_should_act="Maintenance Planner.",
        )

    graph["technician_user_id"] = technician_id
    try:
        auth = budget.call(
            "check_technician_authorization",
            {"task_id": task["id"], "technician_user_id": technician_id},
        )
    except AeroComplyError as exc:
        return _error_result(Intent.TECHNICIAN_AUTHORIZATION, exc, budget.tools_invoked)
    if auth is None:
        return InvestigationResult(
            intent=Intent.TECHNICIAN_AUTHORIZATION.value,
            status="BACKEND_UNAVAILABLE",
            headline="I couldn't complete the authorization check.",
            tools_invoked=budget.tools_invoked,
            result_graph=graph,
        )

    return InvestigationResult(
        intent=Intent.TECHNICIAN_AUTHORIZATION.value,
        status="ANSWERED",
        headline=f"Technician authorization: {auth['status']}.",
        tools_invoked=budget.tools_invoked,
        result_graph=graph,
        what_i_found=[auth["reason"]],
        next_step=None if auth["status"] == "AUTHORIZED" else "Assign an authorized technician.",
        who_should_act=None if auth["status"] == "AUTHORIZED" else "Maintenance Planner.",
    )


def _investigate_procurement_chain(
    db: Session, user: CurrentUser, resolution: MessageResolution
) -> InvestigationResult:
    context = resolution.context
    budget = _CallBudget(db, user)
    graph: dict[str, str] = {}

    po_id = str(context.current_purchase_order_id) if context.current_purchase_order_id else None
    pr_id = (
        str(context.current_procurement_request_id)
        if context.current_procurement_request_id
        else None
    )

    if po_id:
        try:
            result = budget.call("get_purchase_orders", {})
        except AeroComplyError as exc:
            return _error_result(Intent.PROCUREMENT_CHAIN, exc, budget.tools_invoked)
        if result is None:
            return InvestigationResult(
                intent=Intent.PROCUREMENT_CHAIN.value,
                status="BACKEND_UNAVAILABLE",
                headline="I couldn't retrieve purchase order data right now.",
                tools_invoked=budget.tools_invoked,
            )
        po = next((p for p in result["purchase_orders"] if p["id"] == po_id), None)
        if po is None:
            return InvestigationResult(
                intent=Intent.PROCUREMENT_CHAIN.value,
                status="NOT_FOUND",
                headline="I couldn't find that purchase order.",
                tools_invoked=budget.tools_invoked,
            )
        graph["purchase_order_id"] = po_id
        return _synthesize_po_answer(po, budget.tools_invoked, graph)

    if pr_id:
        try:
            result = budget.call("get_procurement_requests", {})
        except AeroComplyError as exc:
            return _error_result(Intent.PROCUREMENT_CHAIN, exc, budget.tools_invoked)
        if result is None:
            return InvestigationResult(
                intent=Intent.PROCUREMENT_CHAIN.value,
                status="BACKEND_UNAVAILABLE",
                headline="I couldn't retrieve procurement request data right now.",
                tools_invoked=budget.tools_invoked,
            )
        pr = next((r for r in result["requests"] if r["id"] == pr_id), None)
        if pr is None:
            return InvestigationResult(
                intent=Intent.PROCUREMENT_CHAIN.value,
                status="NOT_FOUND",
                headline="I couldn't find that procurement request.",
                tools_invoked=budget.tools_invoked,
            )
        graph["procurement_request_id"] = pr_id
        awaiting_approval = pr["status"] in ("SUBMITTED", "UNDER_REVIEW")
        return InvestigationResult(
            intent=Intent.PROCUREMENT_CHAIN.value,
            status="ANSWERED",
            headline=f"Procurement request for {pr['part_number']} is {pr['status']}.",
            tools_invoked=budget.tools_invoked,
            result_graph=graph,
            what_i_found=[
                f"Procurement request {pr['id']} ({pr['part_number']}) is {pr['status']}."
            ],
            next_step="Approve the request." if awaiting_approval else None,
            who_should_act="Procurement approver" if awaiting_approval else None,
        )

    # No PO or procurement request in context — try to fall back through an
    # aircraft's AOG material blocker if one is in context, since that's the
    # most common way a user reaches "what's delaying the PO" conversationally.
    if context.current_aircraft_id:
        aog_result = _investigate_aog(db, user, resolution)
        graph_keys = aog_result.result_graph
        if "purchase_order_id" in graph_keys or "procurement_request_id" in graph_keys:
            return aog_result

    return _needs_entity(Intent.PROCUREMENT_CHAIN, "purchase order or procurement request")


def _synthesize_po_answer(
    po: dict[str, Any], tools_invoked: list[str], graph: dict[str, str]
) -> InvestigationResult:
    status = po["status"]
    lines = po.get("lines", [])
    outstanding = [
        (line["part_number"], line["quantity"] - line["received_quantity"])
        for line in lines
        if line["quantity"] > line["received_quantity"]
    ]

    if status == "RECEIVED":
        what_i_found = [
            f"Purchase order {po['po_number']} is fully RECEIVED — no outstanding quantity."
        ]
        next_step = None
        who = None
    elif status in ("SENT", "ACKNOWLEDGED", "PARTIALLY_RECEIVED"):
        outstanding_desc = (
            "; ".join(f"{qty} x {part}" for part, qty in outstanding) or "an unspecified quantity"
        )
        what_i_found = [
            f"Purchase order {po['po_number']} is {status} — outstanding: {outstanding_desc}."
        ]
        next_step = "Record receipt of the outstanding quantity."
        who = "Receiving"
    elif status in ("DRAFT", "PENDING_APPROVAL", "APPROVED"):
        what_i_found = [
            f"Purchase order {po['po_number']} is {status} — not yet sent to the vendor."
        ]
        next_step = "Advance the purchase order to SENT."
        who = "Procurement approver"
    else:  # CANCELLED or any other terminal/unknown status
        what_i_found = [f"Purchase order {po['po_number']} is {status}."]
        next_step = None
        who = None

    return InvestigationResult(
        intent=Intent.PROCUREMENT_CHAIN.value,
        status="ANSWERED",
        headline=f"Purchase order {po['po_number']} is {status}.",
        tools_invoked=tools_invoked,
        result_graph=graph,
        what_i_found=what_i_found,
        next_step=next_step,
        who_should_act=who,
        related_records=[RelatedRecord(label="PurchaseOrder", id=po["id"])],
    )


def _investigate_compliance(
    db: Session, user: CurrentUser, resolution: MessageResolution
) -> InvestigationResult:
    context = resolution.context
    if context.current_aircraft_id is None:
        return _needs_entity(Intent.COMPLIANCE, "aircraft")

    budget = _CallBudget(db, user)
    try:
        result = budget.call(
            "get_compliance_assessments", {"aircraft_id": str(context.current_aircraft_id)}
        )
    except AeroComplyError as exc:
        return _error_result(Intent.COMPLIANCE, exc, budget.tools_invoked)
    if result is None:
        return InvestigationResult(
            intent=Intent.COMPLIANCE.value,
            status="BACKEND_UNAVAILABLE",
            headline="I couldn't retrieve compliance assessments right now.",
            tools_invoked=budget.tools_invoked,
        )

    assessments = result.get("assessments", [])
    graph = {"aircraft_id": str(context.current_aircraft_id)}
    if not assessments:
        return InvestigationResult(
            intent=Intent.COMPLIANCE.value,
            status="ANSWERED",
            headline="No compliance assessments are recorded for this aircraft.",
            tools_invoked=budget.tools_invoked,
            result_graph=graph,
            what_i_found=[
                "NOT_TRACKED — no compliance assessment records exist for this aircraft."
            ],
        )

    non_compliant = [a for a in assessments if a.get("status") == "NON_COMPLIANT"]
    headline = (
        f"{len(non_compliant)} of {len(assessments)} assessment(s) are NON_COMPLIANT."
        if non_compliant
        else "All recorded assessments are compliant."
    )
    return InvestigationResult(
        intent=Intent.COMPLIANCE.value,
        status="ANSWERED",
        headline=headline,
        tools_invoked=budget.tools_invoked,
        result_graph=graph,
        what_i_found=[f"{a['requirement_id']}: {a['status']}" for a in assessments[:10]],
    )


_INVESTIGATORS = {
    Intent.AOG: _investigate_aog,
    Intent.RELEASE_READINESS: _investigate_release_readiness,
    Intent.TECHNICIAN_AUTHORIZATION: _investigate_technician_authorization,
    Intent.PROCUREMENT_CHAIN: _investigate_procurement_chain,
    Intent.COMPLIANCE: _investigate_compliance,
}

# Which entity_type(s) each intent's investigator actually reads from
# context. Used only to decide whether an explicit-but-unresolvable
# reference in THIS message should block investigation (see investigate())
# — deliberately not a general "required entities" schema beyond that.
_INTENT_ENTITY_TYPES: dict[Intent, tuple[str, ...]] = {
    Intent.AOG: ("aircraft",),
    Intent.RELEASE_READINESS: ("work_order",),
    Intent.TECHNICIAN_AUTHORIZATION: ("task", "technician"),
    Intent.PROCUREMENT_CHAIN: ("purchase_order", "procurement_request"),
    Intent.COMPLIANCE: ("aircraft",),
}


def investigate(
    db: Session, user: CurrentUser, *, question: str, resolution: MessageResolution
) -> InvestigationResult | None:
    """Returns None when the question doesn't match a known deterministic
    intent — the caller (agent_service) should fall through to the
    existing LLM tool-loop in that case, unchanged.
    """
    resolved_intent: Intent | None = classify_intent(question)
    if resolved_intent == Intent.UNKNOWN:
        resolved_intent = _infer_continuation_intent(resolution.context)
    if resolved_intent is None:
        return None

    # If THIS message contained an explicit reference that failed to
    # resolve (e.g. a registration/number that looks real but matches no
    # record), never silently fall back to whatever entity was in context
    # from an earlier turn — that would answer about the wrong record. Only
    # the entity type(s) the chosen intent actually needs are checked, so
    # an unrelated not-found elsewhere in the message doesn't block it.
    needed_types = _INTENT_ENTITY_TYPES.get(resolved_intent, ())
    for not_found in resolution.not_found:
        if not_found.entity_type in needed_types:
            label = not_found.entity_type.replace("_", " ")
            article = "an" if label[0] in "aeiou" else "a"
            return InvestigationResult(
                intent=resolved_intent.value,
                status="NOT_FOUND",
                headline=f"I couldn't find {article} {label} matching {not_found.identifier!r}.",
            )

    investigator = _INVESTIGATORS.get(resolved_intent)
    if investigator is None:
        return None
    return investigator(db, user, resolution)


def _infer_continuation_intent(context: LisaConversationContext) -> Intent | None:
    """A bare follow-up ("what is blocking it?", "why?") carries no
    keyword of its own — infer which investigation it continues from
    which context field is populated, most-specific first. Never guesses
    an entity, only which REAL investigation to re-run against the
    identifiers already in context.
    """
    if context.current_purchase_order_id or context.current_procurement_request_id:
        return Intent.PROCUREMENT_CHAIN
    if context.current_task_id and context.current_technician_user_id:
        return Intent.TECHNICIAN_AUTHORIZATION
    if context.current_aog_event_id:
        return Intent.AOG
    if context.current_work_order_id:
        return Intent.RELEASE_READINESS
    return None
