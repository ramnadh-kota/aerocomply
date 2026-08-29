import uuid

from sqlalchemy.orm import Session

from app.models.audit_event import AuditEvent


def record_audit_event(
    db: Session,
    *,
    organization_id: uuid.UUID,
    user_id: uuid.UUID | None,
    action: str,
    entity_type: str,
    entity_id: uuid.UUID | None = None,
    metadata: dict | None = None,
) -> AuditEvent:
    event = AuditEvent(
        organization_id=organization_id,
        user_id=user_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        event_metadata=metadata or {},
    )
    db.add(event)
    return event
