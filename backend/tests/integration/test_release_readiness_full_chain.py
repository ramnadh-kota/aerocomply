"""End-to-end integration test tracing the full BL-16/BL-17 chain:

org -> aircraft -> work order -> task -> readiness shows TASK_EXECUTION
blocker -> complete task -> blocker clears -> submit+accept evidence ->
EVIDENCE blocker clears -> complete inspection (as me) -> INSPECTION
blocker clears -> final readiness is READY, reflecting only the three
categories release_readiness_service actually implements today.
"""


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


def test_full_readiness_chain(client):
    tokens = _register(client, "Airline Chain", "admin@airline-chain.com")
    headers = _auth(tokens["access_token"])

    aircraft_resp = client.post(
        "/api/v1/aircraft",
        json={"registration": "N300CH", "msn": "MSN-CHAIN-1", "aircraft_type": "A320"},
        headers=headers,
    )
    assert aircraft_resp.status_code == 201
    aircraft_id = aircraft_resp.json()["id"]

    wo_resp = client.post(
        "/api/v1/work-orders",
        json={"aircraft_id": aircraft_id, "work_order_number": "WO-CHAIN-1"},
        headers=headers,
    )
    assert wo_resp.status_code == 201
    work_order_id = wo_resp.json()["id"]

    task_resp = client.post(
        f"/api/v1/work-orders/{work_order_id}/tasks",
        json={"work_order_id": work_order_id, "description": "Replace the widget"},
        headers=headers,
    )
    assert task_resp.status_code == 201
    task_id = task_resp.json()["id"]

    # 1. Freshly created task -> TASK_EXECUTION blocker.
    r1 = client.get(f"/api/v1/work-orders/{work_order_id}/release-readiness", headers=headers)
    assert r1.status_code == 200
    assert r1.json()["status"] == "BLOCKED"
    categories_1 = {b["category"] for b in r1.json()["blockers"]}
    assert categories_1 == {"TASK_EXECUTION"}

    # 2. Complete the task -> TASK_EXECUTION blocker clears.
    complete_resp = client.post(
        f"/api/v1/work-orders/{work_order_id}/tasks/{task_id}/complete", headers=headers
    )
    assert complete_resp.status_code == 200

    r2 = client.get(f"/api/v1/work-orders/{work_order_id}/release-readiness", headers=headers)
    assert r2.status_code == 200
    assert r2.json()["status"] == "READY"
    assert r2.json()["blockers"] == []

    # 3. Add an evidence requirement -> EVIDENCE blocker (UPLOADED, not ACCEPTED).
    evidence_resp = client.post("/api/v1/evidence", json={"task_id": task_id}, headers=headers)
    assert evidence_resp.status_code == 201
    evidence_id = evidence_resp.json()["id"]

    r3 = client.get(f"/api/v1/work-orders/{work_order_id}/release-readiness", headers=headers)
    assert r3.status_code == 200
    assert r3.json()["status"] == "BLOCKED"
    assert {b["category"] for b in r3.json()["blockers"]} == {"EVIDENCE"}

    # 4. Walk evidence to ACCEPTED -> EVIDENCE blocker clears.
    for target in ("SUBMITTED", "AWAITING_REVIEW", "ACCEPTED"):
        step = client.post(
            f"/api/v1/evidence/{evidence_id}/transition",
            json={"target_status": target},
            headers=headers,
        )
        assert step.status_code == 200, step.json()

    r4 = client.get(f"/api/v1/work-orders/{work_order_id}/release-readiness", headers=headers)
    assert r4.status_code == 200
    assert r4.json()["status"] == "READY"
    assert r4.json()["blockers"] == []

    # 5. Add a non-RII (required=False) inspection requirement -> INSPECTION blocker.
    #    (Using a checklist review rather than RII avoids needing a second,
    #    independent user just to prove the readiness wiring; the RII
    #    independence path itself is covered by
    #    test_inspection_completion_identity_api.py.)
    inspection_resp = client.post(
        "/api/v1/inspections",
        json={"task_id": task_id, "required": False},
        headers=headers,
    )
    assert inspection_resp.status_code == 201
    requirement_id = inspection_resp.json()["id"]

    r5 = client.get(f"/api/v1/work-orders/{work_order_id}/release-readiness", headers=headers)
    assert r5.status_code == 200
    assert r5.json()["status"] == "BLOCKED"
    assert {b["category"] for b in r5.json()["blockers"]} == {"INSPECTION"}

    # 6. Complete the inspection "as me" (BL-17 fix path — no inspector_user_id
    #    supplied) -> INSPECTION blocker clears -> overall READY.
    transition_resp = client.post(
        f"/api/v1/inspections/{requirement_id}/transition",
        json={"target_status": "COMPLETED"},
        headers=headers,
    )
    assert transition_resp.status_code == 200

    r6 = client.get(f"/api/v1/work-orders/{work_order_id}/release-readiness", headers=headers)
    assert r6.status_code == 200
    assert r6.json()["blockers"] == []
    assert r6.json()["status"] == "READY"
