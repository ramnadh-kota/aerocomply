"""Ties together context_service + entity_resolution_service +
reference_resolution_service into the single deterministic step
agent_service runs before calling the LLM: SAFETY -> CONTEXT LOAD ->
ENTITY RESOLUTION -> REFERENCE RESOLUTION -> (context update). This module
performs no LLM calls and no tool execution — it only resolves identifiers
against real backend records and updates the persisted context.
"""

import uuid
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.models.lisa_conversation_context import LisaConversationContext
from app.services.lisa import (
    context_service,
    entity_resolution_service,
    reference_resolution_service,
)
from app.services.lisa.entity_resolution_service import (
    AmbiguousMatch,
    NotFound,
    ResolvedEntity,
)

_RESOLVER_BY_TYPE = {
    "aircraft": entity_resolution_service.resolve_aircraft,
    "work_order": entity_resolution_service.resolve_work_order,
    "part": entity_resolution_service.resolve_part,
    "vendor": entity_resolution_service.resolve_vendor,
    "purchase_order": entity_resolution_service.resolve_purchase_order,
    "technician": entity_resolution_service.resolve_technician,
}

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


@dataclass
class MessageResolution:
    context: LisaConversationContext
    context_reset: bool = False
    resolved: list[ResolvedEntity] = field(default_factory=list)
    ambiguous: AmbiguousMatch | None = None
    not_found: list[NotFound] = field(default_factory=list)

    @property
    def needs_clarification(self) -> bool:
        return self.ambiguous is not None

    def entity_summary_line(self) -> str | None:
        """A short, structured line for the LLM prompt — real resolved
        identifiers only, never free-text reasoning about how they were
        resolved.
        """
        parts = [f"{e.entity_type}={e.entity_id} ({e.display})" for e in self.resolved]
        if not parts:
            return None
        return "Resolved entities this turn: " + "; ".join(parts)


def resolve_message(
    db: Session, *, organization_id: uuid.UUID, user_id: uuid.UUID, question: str
) -> MessageResolution:
    context = context_service.get_or_create_context(
        db, organization_id=organization_id, user_id=user_id
    )

    if reference_resolution_service.is_reset_request(question):
        context = context_service.reset_context(db, context)
        return MessageResolution(context=context, context_reset=True)

    result = MessageResolution(context=context)

    # 1. Explicit identifiers found directly in the message text.
    explicit = reference_resolution_service.extract_explicit_identifiers(question)
    context_updates: dict[str, str | None] = {}
    for entity_type, identifier in explicit.items():
        resolver = _RESOLVER_BY_TYPE[entity_type]
        resolution = resolver(db, organization_id=organization_id, identifier=identifier)
        if isinstance(resolution, AmbiguousMatch):
            result.ambiguous = resolution
            return result
        if isinstance(resolution, NotFound):
            result.not_found.append(resolution)
            continue
        result.resolved.append(resolution)
        context_updates[_CONTEXT_FIELD_BY_TYPE[resolution.entity_type]] = resolution.entity_id

    # 1b. A bare UUID (e.g. the user replying with the exact id Lisa just
    # surfaced while asking them to disambiguate) — try each known entity
    # type's resolver in a fixed priority order until one actually finds a
    # record. Only attempted when nothing already resolved above, so a
    # typed identifier (a WO-/PO-/registration match) always wins.
    if not result.resolved:
        bare_uuid = reference_resolution_service.extract_bare_uuid(question)
        if bare_uuid is not None:
            for resolver in _RESOLVER_BY_TYPE.values():
                resolution = resolver(db, organization_id=organization_id, identifier=bare_uuid)
                if isinstance(resolution, ResolvedEntity):
                    result.resolved.append(resolution)
                    context_updates[_CONTEXT_FIELD_BY_TYPE[resolution.entity_type]] = (
                        resolution.entity_id
                    )
                    break
                # A syntactically valid UUID that doesn't match this type is
                # simply NotFound for that type — try the next one. It can
                # never be AmbiguousMatch (a UUID is unique by definition).

    # 2. Pronoun/reference resolution against context — only attempted for
    # entity types the message didn't already resolve explicitly.
    if not explicit and not result.resolved:
        reference = reference_resolution_service.resolve_reference(question, context)
        if reference is not None:
            entity_type, entity_id = reference
            result.resolved.append(
                ResolvedEntity(entity_type, entity_id, entity_id)
            )

    if context_updates:
        context = context_service.update_context(db, context, updates=context_updates)
        result.context = context

    for resolved in result.resolved:
        context = context_service.record_resolved_entity(
            db,
            context,
            entity_type=resolved.entity_type,
            entity_id=resolved.entity_id,
            display=resolved.display,
        )
    result.context = context

    return result
