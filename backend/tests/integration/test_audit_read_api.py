"""Tests for M12.0: the platform-level audit read API (GET /platform/audit).

Covers the read service (app/services/audit_service.list_audit_events) and
the HTTP route (app/api/v1/platform.py), plus a re-confirmation that the
existing audit write path and append-only DB trigger are untouched.
"""
import uuid
from datetime import UTC, datetime, timedelta

from app.core.security import hash_password
from app.models.audit_event import AuditEvent
from app.models.organization import Organization
from app.models.user import User, UserRole
from app.services.audit_service import (
    AUDIT_LIST_MAX_LIMIT,
    list_audit_events,
    record_audit_event,
)


def _make_event(
    db,
    *,
    organization_id=None,
    user_id=None,
    action="test.action",
    entity_type="Test",
    entity_id=None,
    metadata=None,
    created_at=None,
):
    kwargs = {}
    if created_at is not None:
        # audit_events is append-only (DB trigger rejects UPDATE/DELETE --
        # see test_audit_immutability.py), so a distinct created_at must be
        # set at INSERT time, never patched in afterward.
        kwargs["created_at"] = created_at
    event = AuditEvent(
        organization_id=organization_id or uuid.uuid4(),
        user_id=user_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        event_metadata=metadata or {},
        **kwargs,
    )
    db.add(event)
    db.flush()
    return event


# ---------------------------------------------------------------------------
# Service-level tests
# ---------------------------------------------------------------------------


def test_list_audit_events_default_pagination(db_session):
    org_id = uuid.uuid4()
    for i in range(5):
        _make_event(db_session, organization_id=org_id, action=f"a.{i}")

    events, total = list_audit_events(db_session, organization_id=org_id)
    assert total == 5
    assert len(events) == 5


def test_list_audit_events_maximum_pagination_enforced(db_session):
    org_id = uuid.uuid4()
    for i in range(AUDIT_LIST_MAX_LIMIT + 20):
        _make_event(db_session, organization_id=org_id, action=f"a.{i}")

    events, total = list_audit_events(db_session, organization_id=org_id, limit=10_000)
    assert total == AUDIT_LIST_MAX_LIMIT + 20
    assert len(events) == AUDIT_LIST_MAX_LIMIT


def test_list_audit_events_deterministic_ordering(db_session):
    org_id = uuid.uuid4()
    same_ts = datetime.now(UTC)
    e1 = _make_event(db_session, organization_id=org_id, action="a.1", created_at=same_ts)
    e2 = _make_event(db_session, organization_id=org_id, action="a.2", created_at=same_ts)

    events, _ = list_audit_events(db_session, organization_id=org_id)
    ids_desc = sorted([e1.id, e2.id], reverse=True)
    assert [e.id for e in events] == ids_desc


def test_list_audit_events_organization_id_filter(db_session):
    org_a = uuid.uuid4()
    org_b = uuid.uuid4()
    _make_event(db_session, organization_id=org_a, action="a.only")
    _make_event(db_session, organization_id=org_b, action="b.only")

    events, total = list_audit_events(db_session, organization_id=org_a)
    assert total == 1
    assert events[0].organization_id == org_a


def test_list_audit_events_action_filter(db_session):
    org_id = uuid.uuid4()
    _make_event(db_session, organization_id=org_id, action="match.me")
    _make_event(db_session, organization_id=org_id, action="other")

    events, total = list_audit_events(db_session, organization_id=org_id, action="match.me")
    assert total == 1
    assert events[0].action == "match.me"


def test_list_audit_events_entity_type_filter(db_session):
    org_id = uuid.uuid4()
    _make_event(db_session, organization_id=org_id, entity_type="Aircraft")
    _make_event(db_session, organization_id=org_id, entity_type="Plan")

    events, total = list_audit_events(db_session, organization_id=org_id, entity_type="Plan")
    assert total == 1
    assert events[0].entity_type == "Plan"


def test_list_audit_events_date_from_filter(db_session):
    org_id = uuid.uuid4()
    now = datetime.now(UTC)
    old = _make_event(db_session, organization_id=org_id, created_at=now - timedelta(days=10))
    recent = _make_event(db_session, organization_id=org_id, created_at=now)

    events, total = list_audit_events(
        db_session, organization_id=org_id, date_from=now - timedelta(days=1)
    )
    assert total == 1
    assert events[0].id == recent.id
    assert old.id != recent.id


def test_list_audit_events_date_to_filter_is_exclusive(db_session):
    org_id = uuid.uuid4()
    boundary = datetime.now(UTC)
    at_boundary = _make_event(db_session, organization_id=org_id, created_at=boundary)
    before = _make_event(
        db_session, organization_id=org_id, created_at=boundary - timedelta(seconds=5)
    )

    events, total = list_audit_events(db_session, organization_id=org_id, date_to=boundary)
    ids = {e.id for e in events}
    assert at_boundary.id not in ids
    assert before.id in ids
    assert total == 1


def test_list_audit_events_combined_filters(db_session):
    org_id = uuid.uuid4()
    now = datetime.now(UTC)
    target = _make_event(
        db_session,
        organization_id=org_id,
        action="combo.match",
        entity_type="Combo",
        created_at=now,
    )
    _make_event(db_session, organization_id=org_id, action="combo.match", entity_type="Other")
    _make_event(db_session, organization_id=org_id, action="different", entity_type="Combo")

    events, total = list_audit_events(
        db_session,
        organization_id=org_id,
        action="combo.match",
        entity_type="Combo",
        date_from=now - timedelta(minutes=1),
    )
    assert total == 1
    assert events[0].id == target.id


def test_list_audit_events_empty_result(db_session):
    events, total = list_audit_events(db_session, organization_id=uuid.uuid4())
    assert events == []
    assert total == 0


def test_list_audit_events_metadata_and_nullable_fields(db_session):
    org_id = uuid.uuid4()
    event = _make_event(
        db_session,
        organization_id=org_id,
        user_id=None,
        entity_id=None,
        metadata={"key": "value", "nested": {"a": 1}},
    )

    events, _ = list_audit_events(db_session, organization_id=org_id)
    found = next(e for e in events if e.id == event.id)
    assert found.user_id is None
    assert found.entity_id is None
    assert found.event_metadata == {"key": "value", "nested": {"a": 1}}


def test_list_audit_events_is_read_only_and_writes_no_new_events(db_session):
    org_id = uuid.uuid4()
    _make_event(db_session, organization_id=org_id)

    before_total = db_session.query(AuditEvent).count()
    list_audit_events(db_session, organization_id=org_id)
    after_total = db_session.query(AuditEvent).count()
    assert before_total == after_total


# ---------------------------------------------------------------------------
# HTTP route tests
# ---------------------------------------------------------------------------


def _create_platform_admin(db_session, email):
    org = Organization(name="Audit Read Platform Ops")
    db_session.add(org)
    db_session.flush()
    user = User(
        organization_id=org.id,
        email=email,
        hashed_password=hash_password("supersecret123"),
        full_name="Platform Admin",
        is_active=True,
    )
    db_session.add(user)
    db_session.flush()
    db_session.add(UserRole(user_id=user.id, role_name="PLATFORM_ADMIN", organization_id=org.id))
    db_session.commit()
    return user


def _login(client, email):
    resp = client.post(
        "/api/v1/auth/login", json={"email": email, "password": "supersecret123"}
    )
    assert resp.status_code == 200
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


def _register(client, org_name, email):
    resp = client.post(
        "/api/v1/auth/register-organization",
        json={
            "organization_name": org_name,
            "admin_email": email,
            "admin_full_name": "Admin",
            "admin_password": "supersecret123",
        },
    )
    assert resp.status_code == 201
    return resp.json()


def test_platform_admin_can_list_audit_events_via_api(client, db_session):
    _create_platform_admin(db_session, "audit-ops@kotas-aerospace-internal.com")
    org_id = uuid.uuid4()
    record_audit_event(
        db_session,
        organization_id=org_id,
        user_id=None,
        action="api.test",
        entity_type="Test",
    )
    db_session.commit()

    headers = _login(client, "audit-ops@kotas-aerospace-internal.com")
    resp = client.get("/api/v1/platform/audit", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert "items" in body and "total" in body and "limit" in body and "offset" in body
    assert any(item["action"] == "api.test" for item in body["items"])


def test_non_platform_admin_gets_403_from_audit_endpoint(client):
    tokens = _register(client, "Audit Read Customer", "admin@audit-read-customer.com")
    resp = client.get(
        "/api/v1/platform/audit", headers={"Authorization": f"Bearer {tokens['access_token']}"}
    )
    assert resp.status_code == 403


def test_audit_endpoint_rejects_negative_limit(client, db_session):
    _create_platform_admin(db_session, "audit-neg-limit@kotas-aerospace-internal.com")
    headers = _login(client, "audit-neg-limit@kotas-aerospace-internal.com")
    resp = client.get("/api/v1/platform/audit?limit=-1", headers=headers)
    assert resp.status_code == 422


def test_audit_endpoint_rejects_negative_offset(client, db_session):
    _create_platform_admin(db_session, "audit-neg-offset@kotas-aerospace-internal.com")
    headers = _login(client, "audit-neg-offset@kotas-aerospace-internal.com")
    resp = client.get("/api/v1/platform/audit?offset=-1", headers=headers)
    assert resp.status_code == 422


def test_audit_endpoint_clamps_oversized_limit(client, db_session):
    _create_platform_admin(db_session, "audit-clamp@kotas-aerospace-internal.com")
    headers = _login(client, "audit-clamp@kotas-aerospace-internal.com")
    resp = client.get("/api/v1/platform/audit?limit=99999", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["limit"] == AUDIT_LIST_MAX_LIMIT


def test_audit_endpoint_organization_filter_via_api(client, db_session):
    _create_platform_admin(db_session, "audit-org-filter@kotas-aerospace-internal.com")
    org_a = uuid.uuid4()
    org_b = uuid.uuid4()
    record_audit_event(
        db_session, organization_id=org_a, user_id=None, action="org-a.event", entity_type="Test"
    )
    record_audit_event(
        db_session, organization_id=org_b, user_id=None, action="org-b.event", entity_type="Test"
    )
    db_session.commit()

    headers = _login(client, "audit-org-filter@kotas-aerospace-internal.com")
    resp = client.get(f"/api/v1/platform/audit?organization_id={org_a}", headers=headers)
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert all(item["organization_id"] == str(org_a) for item in items)
    assert any(item["action"] == "org-a.event" for item in items)


def test_get_audit_does_not_create_new_audit_event(client, db_session):
    _create_platform_admin(db_session, "audit-readonly@kotas-aerospace-internal.com")
    headers = _login(client, "audit-readonly@kotas-aerospace-internal.com")

    resp = client.get("/api/v1/platform/audit", headers=headers)
    assert resp.status_code == 200
    after = db_session.query(AuditEvent).count()
    # The GET itself must add nothing -- verified by comparing two
    # consecutive reads rather than a pre/post snapshot around unrelated
    # setup (admin creation/login) that may itself record audit events.
    resp2 = client.get("/api/v1/platform/audit", headers=headers)
    assert resp2.status_code == 200
    after2 = db_session.query(AuditEvent).count()
    assert after == after2
