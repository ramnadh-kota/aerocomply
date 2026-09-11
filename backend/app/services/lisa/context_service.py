"""Persistent Lisa conversation-context service: one active row per
(organization, user). Pure state management — no entity resolution logic
lives here (see entity_resolution_service.py / reference_resolution_service.py).
"""

import json
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.lisa_conversation_context import LisaConversationContext

_MAX_RECENT_QUESTIONS = 5
_MAX_RECENT_ENTITIES = 10

# Every field name here must match a real column on LisaConversationContext
# — this is the whitelist of what update_context is allowed to touch.
_ENTITY_FIELDS = (
    "current_aircraft_id",
    "current_work_order_id",
    "current_task_id",
    "current_part_id",
    "current_part_requirement_id",
    "current_procurement_request_id",
    "current_vendor_id",
    "current_purchase_order_id",
    "current_technician_user_id",
    "current_aog_event_id",
)


def get_or_create_context(
    db: Session, *, organization_id: uuid.UUID, user_id: uuid.UUID
) -> LisaConversationContext:
    context = db.execute(
        select(LisaConversationContext).where(
            LisaConversationContext.organization_id == organization_id,
            LisaConversationContext.user_id == user_id,
        )
    ).scalar_one_or_none()
    if context is not None:
        return context

    context = LisaConversationContext(
        organization_id=organization_id,
        user_id=user_id,
        recent_entities="[]",
        recent_questions="[]",
        context_version=1,
        last_activity_at=datetime.now(UTC),
    )
    db.add(context)
    db.commit()
    db.refresh(context)
    return context


def update_context(
    db: Session, context: LisaConversationContext, *, updates: dict[str, str | None]
) -> LisaConversationContext:
    changed = False
    for field, value in updates.items():
        if field not in _ENTITY_FIELDS:
            raise ValueError(f"Not a resolvable context field: {field}")
        new_value = uuid.UUID(value) if value is not None else None
        if getattr(context, field) != new_value:
            setattr(context, field, new_value)
            changed = True

    if changed:
        context.context_version += 1
    context.last_activity_at = datetime.now(UTC)
    db.add(context)
    db.commit()
    db.refresh(context)
    return context


def record_resolved_entity(
    db: Session, context: LisaConversationContext, *, entity_type: str, entity_id: str, display: str
) -> LisaConversationContext:
    entities: list[dict] = json.loads(context.recent_entities or "[]")
    entities.append(
        {
            "entity_type": entity_type,
            "entity_id": entity_id,
            "display": display,
            "resolved_at": datetime.now(UTC).isoformat(),
        }
    )
    context.recent_entities = json.dumps(entities[-_MAX_RECENT_ENTITIES:])
    db.add(context)
    db.commit()
    db.refresh(context)
    return context


def most_recent_entity_of_type(
    context: LisaConversationContext, *, entity_type: str
) -> dict | None:
    entities: list[dict] = json.loads(context.recent_entities or "[]")
    for entity in reversed(entities):
        if entity.get("entity_type") == entity_type:
            return entity
    return None


def record_question(
    db: Session, context: LisaConversationContext, *, question: str
) -> LisaConversationContext:
    recent: list[str] = json.loads(context.recent_questions or "[]")
    recent.append(question)
    context.recent_questions = json.dumps(recent[-_MAX_RECENT_QUESTIONS:])
    context.previous_question = question
    context.last_activity_at = datetime.now(UTC)
    db.add(context)
    db.commit()
    db.refresh(context)
    return context


def reset_context(db: Session, context: LisaConversationContext) -> LisaConversationContext:
    """Resets active operational context only — never touches AuditEvent or
    any other historical record. A fresh conversation starts clean, but
    nothing about what actually happened in the system is deleted.
    """
    for field in _ENTITY_FIELDS:
        setattr(context, field, None)
    context.recent_entities = "[]"
    context.recent_questions = "[]"
    context.previous_question = None
    context.context_version += 1
    context.last_activity_at = datetime.now(UTC)
    db.add(context)
    db.commit()
    db.refresh(context)
    return context
