"""Confirms the DB-level trigger (migration 0002) rejects UPDATE/DELETE on
audit_events, not just that the app happens not to issue them.
"""
import uuid

import pytest
from sqlalchemy.exc import DBAPIError

from app.models.audit_event import AuditEvent


def test_audit_event_update_is_rejected_by_db(db_session):
    event = AuditEvent(
        organization_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        action="test.action",
        entity_type="Test",
        event_metadata={},
    )
    db_session.add(event)
    db_session.flush()

    event.action = "tampered"
    with pytest.raises(DBAPIError, match="append-only"):
        db_session.flush()


def test_audit_event_delete_is_rejected_by_db(db_session):
    event = AuditEvent(
        organization_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        action="test.action",
        entity_type="Test",
        event_metadata={},
    )
    db_session.add(event)
    db_session.flush()

    db_session.delete(event)
    with pytest.raises(DBAPIError, match="append-only"):
        db_session.flush()
