import uuid
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.audit_event import AuditEvent

# M12.0: read-side pagination bounds. No existing platform list endpoint
# paginates (they return full lists), so these are new, deliberately
# conservative defaults/maximum to avoid ever loading unbounded audit
# history in one response.
AUDIT_LIST_DEFAULT_LIMIT = 50
AUDIT_LIST_MAX_LIMIT = 100


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


def list_audit_events(
    db: Session,
    *,
    organization_id: uuid.UUID | None = None,
    action: str | None = None,
    entity_type: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    limit: int = AUDIT_LIST_DEFAULT_LIMIT,
    offset: int = 0,
) -> tuple[list[AuditEvent], int]:
    """Platform-level read of audit_events (see app/api/v1/platform.py's
    GET /platform/audit -- gated by Permission.PLATFORM_MANAGE, which by
    design grants cross-tenant read access, same precedent as
    GET /platform/organizations/{organization_id}/entitlements).

    Read-only: never mutates, never records an audit event of its own.
    Filtering/ordering/pagination all happen in the database -- no
    in-Python filtering of a fully-loaded result set.

    date_from is inclusive, date_to is exclusive (matches created_at as a
    half-open [from, to) range).

    Returns (events, total_matching_count) -- total is over the filtered
    set before limit/offset are applied, for pagination metadata.
    """
    limit = max(1, min(limit, AUDIT_LIST_MAX_LIMIT))
    offset = max(0, offset)

    filters = []
    if organization_id is not None:
        filters.append(AuditEvent.organization_id == organization_id)
    if action is not None:
        filters.append(AuditEvent.action == action)
    if entity_type is not None:
        filters.append(AuditEvent.entity_type == entity_type)
    if date_from is not None:
        filters.append(AuditEvent.created_at >= date_from)
    if date_to is not None:
        filters.append(AuditEvent.created_at < date_to)

    base_stmt = select(AuditEvent)
    count_stmt = select(func.count()).select_from(AuditEvent)
    for f in filters:
        base_stmt = base_stmt.where(f)
        count_stmt = count_stmt.where(f)

    total = db.execute(count_stmt).scalar_one()

    stmt = (
        base_stmt.order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc())
        .limit(limit)
        .offset(offset)
    )
    events = list(db.execute(stmt).scalars().all())
    return events, total
