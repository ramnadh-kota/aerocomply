"""API-layer tests for BL-16: server-authoritative task completion.

Mirrors the register/auth pattern in test_assessments_api.py. Confirms:
- valid completion (PENDING -> COMPLETED)
- invalid transition (already-COMPLETED cannot complete again)
- cross-tenant task is rejected (404, not leaked)
- audit event recorded
- release readiness TASK_EXECUTION blocker reacts to completion
"""

from app.models.audit_event import AuditEvent


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


def _make_work_order_with_task(client, headers):
    aircraft_resp = client.post(
        "/api/v1/aircraft",
        json={"registration": "N100TC", "msn": "MSN-TC-1", "aircraft_type": "B737"},
        headers=headers,
    )
    assert aircraft_resp.status_code == 201
    aircraft_id = aircraft_resp.json()["id"]

    wo_resp = client.post(
        "/api/v1/work-orders",
        json={"aircraft_id": aircraft_id, "work_order_number": "WO-TASK-1"},
        headers=headers,
    )
    assert wo_resp.status_code == 201
    work_order_id = wo_resp.json()["id"]

    task_resp = client.post(
        f"/api/v1/work-orders/{work_order_id}/tasks",
        json={"work_order_id": work_order_id, "description": "Torque the bolt"},
        headers=headers,
    )
    assert task_resp.status_code == 201
    return work_order_id, task_resp.json()["id"]


def test_valid_task_completion(client):
    tokens = _register(client, "Airline Task1", "admin@airline-task1.com")
    headers = _auth(tokens["access_token"])
    work_order_id, task_id = _make_work_order_with_task(client, headers)

    resp = client.post(
        f"/api/v1/work-orders/{work_order_id}/tasks/{task_id}/complete", headers=headers
    )
    assert resp.status_code == 200
    assert resp.json()["execution_state"] == "COMPLETED"


def test_duplicate_completion_rejected(client):
    tokens = _register(client, "Airline Task2", "admin@airline-task2.com")
    headers = _auth(tokens["access_token"])
    work_order_id, task_id = _make_work_order_with_task(client, headers)

    first = client.post(
        f"/api/v1/work-orders/{work_order_id}/tasks/{task_id}/complete", headers=headers
    )
    assert first.status_code == 200

    second = client.post(
        f"/api/v1/work-orders/{work_order_id}/tasks/{task_id}/complete", headers=headers
    )
    assert second.status_code == 409


def test_cross_tenant_task_completion_rejected(client):
    tokens_a = _register(client, "Airline Task3A", "admin@airline-task3a.com")
    tokens_b = _register(client, "Airline Task3B", "admin@airline-task3b.com")
    headers_a = _auth(tokens_a["access_token"])
    headers_b = _auth(tokens_b["access_token"])

    work_order_id, task_id = _make_work_order_with_task(client, headers_a)

    resp = client.post(
        f"/api/v1/work-orders/{work_order_id}/tasks/{task_id}/complete", headers=headers_b
    )
    assert resp.status_code == 404


def test_task_completion_records_audit_event(client, db_session):
    tokens = _register(client, "Airline Task4", "admin@airline-task4.com")
    headers = _auth(tokens["access_token"])
    work_order_id, task_id = _make_work_order_with_task(client, headers)

    resp = client.post(
        f"/api/v1/work-orders/{work_order_id}/tasks/{task_id}/complete", headers=headers
    )
    assert resp.status_code == 200

    events = (
        db_session.query(AuditEvent)
        .filter(AuditEvent.entity_type == "Task", AuditEvent.action == "task.completed")
        .all()
    )
    assert len(events) == 1
    assert str(events[0].entity_id) == task_id


def test_task_completion_clears_release_readiness_blocker(client):
    tokens = _register(client, "Airline Task5", "admin@airline-task5.com")
    headers = _auth(tokens["access_token"])
    work_order_id, task_id = _make_work_order_with_task(client, headers)

    before = client.get(f"/api/v1/work-orders/{work_order_id}/release-readiness", headers=headers)
    assert before.status_code == 200
    before_body = before.json()
    assert before_body["status"] == "BLOCKED"
    assert any(b["category"] == "TASK_EXECUTION" for b in before_body["blockers"])

    complete_resp = client.post(
        f"/api/v1/work-orders/{work_order_id}/tasks/{task_id}/complete", headers=headers
    )
    assert complete_resp.status_code == 200

    after = client.get(f"/api/v1/work-orders/{work_order_id}/release-readiness", headers=headers)
    assert after.status_code == 200
    after_body = after.json()
    assert not any(b["category"] == "TASK_EXECUTION" for b in after_body["blockers"])
    assert after_body["status"] == "READY"
