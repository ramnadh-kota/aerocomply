"""API-layer tests for BL-17: RII completion inspector identity handling.

Confirms:
- "Complete (as me)" (no inspector_user_id in the request) now succeeds and
  records the authenticated actor as inspector, instead of failing backend
  validation as it did before the fix.
- An explicit inspector_user_id from another organization is rejected
  (cross-tenant IDOR).
- The RII independence rule (_assert_independent_inspector) is unchanged:
  an inspector who uploaded evidence for the same task is still rejected.
- Audit event recorded on completion.
- Release readiness INSPECTION blocker clears on completion.
"""

from app.core.security import hash_password
from app.models.audit_event import AuditEvent
from app.models.user import User, UserRole


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


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _make_work_order_with_task(client, headers, wo_number="WO-INSP-1"):
    aircraft_resp = client.post(
        "/api/v1/aircraft",
        json={"registration": "N200IC", "msn": f"MSN-{wo_number}", "aircraft_type": "B737"},
        headers=headers,
    )
    assert aircraft_resp.status_code == 201
    aircraft_id = aircraft_resp.json()["id"]

    wo_resp = client.post(
        "/api/v1/work-orders",
        json={"aircraft_id": aircraft_id, "work_order_number": wo_number},
        headers=headers,
    )
    assert wo_resp.status_code == 201
    work_order_id = wo_resp.json()["id"]

    task_resp = client.post(
        f"/api/v1/work-orders/{work_order_id}/tasks",
        json={"work_order_id": work_order_id, "description": "Inspect the panel"},
        headers=headers,
    )
    assert task_resp.status_code == 201
    return work_order_id, task_resp.json()["id"]


def test_complete_as_me_derives_inspector_from_session(client):
    """BL-17: omitting inspector_user_id (the frontend's "Complete (as me)"
    button) must succeed and attribute the completion to the actor, not fail
    with "An inspector_user_id is required"."""
    tokens = _register(client, "Airline Insp1", "admin@airline-insp1.com")
    headers = _auth(tokens["access_token"])
    me = client.get("/api/v1/auth/me", headers=headers).json()

    work_order_id, task_id = _make_work_order_with_task(client, headers)
    req_resp = client.post(
        "/api/v1/inspections", json={"task_id": task_id, "required": True}, headers=headers
    )
    assert req_resp.status_code == 201
    requirement_id = req_resp.json()["id"]

    # No evidence uploaded for this task yet, so the independence check has
    # nothing to compare against (see inspection_service._executing_technician_ids)
    # and the actor may complete it as themselves.
    resp = client.post(
        f"/api/v1/inspections/{requirement_id}/transition",
        json={"target_status": "COMPLETED"},
        headers=headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "COMPLETED"
    assert body["inspector_user_id"] == me["id"]


def test_explicit_inspector_from_other_org_rejected(client):
    tokens_a = _register(client, "Airline Insp2A", "admin@airline-insp2a.com")
    tokens_b = _register(client, "Airline Insp2B", "admin@airline-insp2b.com")
    headers_a = _auth(tokens_a["access_token"])
    me_b = client.get("/api/v1/auth/me", headers=_auth(tokens_b["access_token"])).json()

    work_order_id, task_id = _make_work_order_with_task(client, headers_a, "WO-INSP-2")
    req_resp = client.post(
        "/api/v1/inspections", json={"task_id": task_id, "required": True}, headers=headers_a
    )
    requirement_id = req_resp.json()["id"]

    resp = client.post(
        f"/api/v1/inspections/{requirement_id}/transition",
        json={"target_status": "COMPLETED", "inspector_user_id": me_b["id"]},
        headers=headers_a,
    )
    assert resp.status_code == 409


def test_independence_violation_still_rejected(client, db_session):
    """A named inspector who uploaded evidence for the same task must still
    be rejected — the independence rule itself is unchanged by BL-17."""
    tokens = _register(client, "Airline Insp3", "admin@airline-insp3.com")
    headers = _auth(tokens["access_token"])
    me = client.get("/api/v1/auth/me", headers=headers).json()

    work_order_id, task_id = _make_work_order_with_task(client, headers, "WO-INSP-3")

    evidence_resp = client.post(
        "/api/v1/evidence", json={"task_id": task_id}, headers=headers
    )
    assert evidence_resp.status_code == 201
    assert evidence_resp.json()["uploaded_by_user_id"] == me["id"]

    req_resp = client.post(
        "/api/v1/inspections", json={"task_id": task_id, "required": True}, headers=headers
    )
    requirement_id = req_resp.json()["id"]

    # Explicit self-as-inspector, but this same user uploaded the evidence —
    # RII independence rule must reject it.
    resp = client.post(
        f"/api/v1/inspections/{requirement_id}/transition",
        json={"target_status": "COMPLETED", "inspector_user_id": me["id"]},
        headers=headers,
    )
    assert resp.status_code == 409

    # "Complete (as me)" (no explicit inspector_user_id) resolves to the same
    # actor and must be rejected for the same reason.
    resp2 = client.post(
        f"/api/v1/inspections/{requirement_id}/transition",
        json={"target_status": "COMPLETED"},
        headers=headers,
    )
    assert resp2.status_code == 409


def test_independent_inspector_completion_succeeds(client, db_session):
    tokens = _register(client, "Airline Insp4", "admin@airline-insp4.com")
    headers = _auth(tokens["access_token"])
    me = client.get("/api/v1/auth/me", headers=headers).json()
    org_id = me["organization_id"]

    work_order_id, task_id = _make_work_order_with_task(client, headers, "WO-INSP-4")

    evidence_resp = client.post(
        "/api/v1/evidence", json={"task_id": task_id}, headers=headers
    )
    assert evidence_resp.status_code == 201

    inspector = User(
        organization_id=org_id,
        email="inspector@airline-insp4.com",
        hashed_password=hash_password("supersecret123"),
        full_name="Independent Inspector",
    )
    db_session.add(inspector)
    db_session.commit()
    db_session.refresh(inspector)
    db_session.add(UserRole(user_id=inspector.id, role_name="ORG_ADMIN", organization_id=org_id))
    db_session.commit()

    req_resp = client.post(
        "/api/v1/inspections", json={"task_id": task_id, "required": True}, headers=headers
    )
    requirement_id = req_resp.json()["id"]

    resp = client.post(
        f"/api/v1/inspections/{requirement_id}/transition",
        json={"target_status": "COMPLETED", "inspector_user_id": str(inspector.id)},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["inspector_user_id"] == str(inspector.id)

    events = (
        db_session.query(AuditEvent)
        .filter(
            AuditEvent.entity_type == "InspectionRequirement",
            AuditEvent.action == "inspection.completed",
        )
        .all()
    )
    assert len(events) == 1

    readiness = client.get(
        f"/api/v1/work-orders/{work_order_id}/release-readiness", headers=headers
    )
    assert readiness.status_code == 200
    assert not any(b["category"] == "INSPECTION" for b in readiness.json()["blockers"])
