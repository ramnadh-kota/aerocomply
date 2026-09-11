"""Deterministic pronoun/reference resolution for Lisa. Purely rule-based —
no LLM call, no guessing across entity types. Resolves phrases like "it",
"that aircraft", "the PO", "the previous one" against the caller's
persisted LisaConversationContext (current_*_id fields + recent_entities).

If nothing in the message and nothing in context can answer a reference,
the caller must treat it as unresolved and ask the user to clarify — this
module never invents a fallback entity.
"""

import json
import re

from app.models.lisa_conversation_context import LisaConversationContext

RESET_PHRASES = (
    "start over",
    "forget this context",
    "forget the context",
    "new aircraft",
    "switch aircraft",
    "clear the current context",
    "clear context",
    "clear the context",
    "another work order",
    "different aircraft",
    "reset context",
    "reset the context",
)

# Ordered so a more specific phrase ("that work order") is checked before a
# bare pronoun ("that") would otherwise swallow it.
_TYPED_REFERENCE_PHRASES: tuple[tuple[str, str], ...] = (
    ("this aircraft", "aircraft"),
    ("that aircraft", "aircraft"),
    ("same aircraft", "aircraft"),
    ("the aircraft", "aircraft"),
    ("this work order", "work_order"),
    ("that work order", "work_order"),
    ("same work order", "work_order"),
    ("the work order", "work_order"),
    ("this task", "task"),
    ("that task", "task"),
    ("the task", "task"),
    ("the part", "part"),
    ("that part", "part"),
    ("the vendor", "vendor"),
    ("that vendor", "vendor"),
    ("this po", "purchase_order"),
    ("that po", "purchase_order"),
    ("the po", "purchase_order"),
    ("the purchase order", "purchase_order"),
    ("that purchase order", "purchase_order"),
    ("the technician", "technician"),
    ("that technician", "technician"),
    ("this aog", "aog_event"),
    ("that aog", "aog_event"),
    ("the aog", "aog_event"),
)

_BARE_PRONOUNS = ("it", "this", "that", "this one", "that one")
_PREVIOUS_PHRASES = ("the previous one", "the other one", "previous one")
_NEXT_PHRASES = ("next one", "the next one")

_CONTEXT_FIELD_BY_TYPE = {
    "aircraft": "current_aircraft_id",
    "work_order": "current_work_order_id",
    "task": "current_task_id",
    "part": "current_part_id",
    "vendor": "current_vendor_id",
    "purchase_order": "current_purchase_order_id",
    "technician": "current_technician_user_id",
    "aog_event": "current_aog_event_id",
}

# WO-/PO- numbers deliberately excluded from the generic registration regex
# below so "WO-1042" is never misread as an aircraft registration.
_WORK_ORDER_PATTERN = re.compile(r"\bWO-[A-Za-z0-9-]+\b", re.IGNORECASE)
_PURCHASE_ORDER_PATTERN = re.compile(r"\bPO-[A-Za-z0-9-]+\b", re.IGNORECASE)
_AIRCRAFT_REGISTRATION_PATTERN = re.compile(
    r"\b(?:[A-Z]{1,2}-[A-Z0-9]{2,6}|N[0-9]{1,5}[A-Z]{0,3})\b"
)


def is_reset_request(question: str) -> bool:
    lowered = question.lower()
    return any(phrase in lowered for phrase in RESET_PHRASES)


def extract_explicit_identifiers(question: str) -> dict[str, str]:
    """Regex-extracted explicit identifiers only — WO-/PO- numbers and
    aircraft-registration-shaped tokens. Does not resolve them against the
    database (that's entity_resolution_service's job); this only decides
    WHAT to try to resolve and as what entity type.
    """
    found: dict[str, str] = {}

    wo_match = _WORK_ORDER_PATTERN.search(question)
    if wo_match:
        found["work_order"] = wo_match.group(0).upper()

    po_match = _PURCHASE_ORDER_PATTERN.search(question)
    if po_match:
        found["purchase_order"] = po_match.group(0).upper()

    remainder = question
    if wo_match:
        remainder = remainder.replace(wo_match.group(0), " ")
    if po_match:
        remainder = remainder.replace(po_match.group(0), " ")

    ac_match = _AIRCRAFT_REGISTRATION_PATTERN.search(remainder)
    if ac_match:
        found["aircraft"] = ac_match.group(0).upper()

    return found


def resolve_reference(
    question: str, context: LisaConversationContext
) -> tuple[str, str] | None:
    """Returns (entity_type, entity_id) if a pronoun/reference phrase in
    `question` can be deterministically resolved against `context`, else
    None (caller must ask for clarification rather than guess).
    """
    lowered = question.lower()

    for phrase, entity_type in _TYPED_REFERENCE_PHRASES:
        if phrase in lowered:
            field = _CONTEXT_FIELD_BY_TYPE[entity_type]
            value = getattr(context, field)
            if value is not None:
                return entity_type, str(value)
            return None

    if any(phrase in lowered for phrase in _PREVIOUS_PHRASES):
        entities = json.loads(context.recent_entities or "[]")
        if len(entities) >= 2:
            prev = entities[-2]
            return prev["entity_type"], prev["entity_id"]
        return None

    if any(phrase in lowered for phrase in _NEXT_PHRASES):
        # "Next" has no deterministic backend meaning without an ordered
        # list already presented to the user — never guess an entity here.
        return None

    tokens = set(re.findall(r"[a-z']+", lowered))
    if tokens & set(_BARE_PRONOUNS):
        entities = json.loads(context.recent_entities or "[]")
        if entities:
            last = entities[-1]
            return last["entity_type"], last["entity_id"]
        return None

    return None
