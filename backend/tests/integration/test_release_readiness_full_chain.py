"""End-to-end integration test tracing the full BL-16/BL-17 chain:

org -> aircraft -> work order -> task -> readiness shows TASK_EXECUTION
blocker -> complete task -> blocker clears -> submit+accept evidence ->
EVIDENCE blocker clears -> complete inspection (as me) -> INSPECTION
blocker clears -> final readiness is READY, reflecting only the three
categories release_readiness_service actually implements today.
"""

import uuid

from app.models.plan import Plan, PlanFeature
from app.models.subscription import Subscription, SubscriptionStatus
from app.models.user import User
from app.schemas.procurement_request import ProcurementRequestApproveRequest
from app.services import procurement_service
from datetime import UTC, datetime, timedelta


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


def _entitle(db_session, org_id, feature_key):
    """M21.5 fixture maintenance: grant org_id the named feature on an
    active plan subscription so entitlement-gated routes are reachable."""
    plan = Plan(
        name=f"RR-Plan-{feature_key}-{org_id}",
        code=f"rr-{feature_key}-{org_id}",
        is_active=True,
    )
    db_session.add(plan)
    db_session.commit()
    db_session.refresh(plan)
    db_session.add(PlanFeature(plan_id=plan.id, feature_key=feature_key, enabled=True))
    db_session.add(
        Subscription(
            organization_id=org_id,
            plan_id=plan.id,
            status=SubscriptionStatus.ACTIVE,
            starts_at=datetime.now(UTC) - timedelta(days=1),
            ends_at=None,
        )
    )
    db_session.commit()


def test_full_readiness_chain(client, db_session):
    tokens = _register(client, "Airline Chain", "admin@airline-chain.com")
    headers = _auth(tokens["access_token"])

    # M21.5 fixture maintenance: work-order and procurement routes now
    # require their respective feature entitlements.
    org_id_str = client.get("/api/v1/auth/me", headers=headers).json()["organization_id"]
    chain_org_id = uuid.UUID(org_id_str)
    _entitle(db_session, chain_org_id, "work_order_management")
    _entitle(db_session, chain_org_id, "procurement_management")

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

    # 7. MATERIAL blocker end-to-end through the real HTTP API (not just the
    #    service layer): create a part with zero stock, attach a
    #    PartRequirement to this work order -> MATERIAL blocker appears ->
    #    walk a purchase order through submit/approve/send/receive via the
    #    API -> the receipt fulfills the requirement and the MATERIAL
    #    blocker clears through the same /release-readiness endpoint used
    #    above. This closes the gap the Part 1 fix (fulfilled_quantity on
    #    receipt) only had service-level coverage for.
    part_resp = client.post(
        "/api/v1/parts",
        json={
            "part_number": "PN-CHAIN-1",
            "description": "Fuel pump",
            "quantity_on_hand": 0,
        },
        headers=headers,
    )
    assert part_resp.status_code == 201
    part_id = part_resp.json()["id"]

    requirement_resp = client.post(
        "/api/v1/part-requirements",
        json={
            "work_order_id": work_order_id,
            "task_id": task_id,
            "part_id": part_id,
            "required_quantity": 2,
        },
        headers=headers,
    )
    assert requirement_resp.status_code == 201

    r7 = client.get(f"/api/v1/work-orders/{work_order_id}/release-readiness", headers=headers)
    assert r7.status_code == 200
    assert r7.json()["status"] == "BLOCKED"
    assert {b["category"] for b in r7.json()["blockers"]} == {"MATERIAL"}

    vendor_resp = client.post(
        "/api/v1/vendors", json={"name": "Chain Vendor"}, headers=headers
    )
    assert vendor_resp.status_code == 201
    vendor_id = vendor_resp.json()["id"]

    procurement_resp = client.post(
        "/api/v1/procurement-requests",
        json={
            "aircraft_id": aircraft_id,
            "work_order_id": work_order_id,
            "task_id": task_id,
            "part_id": part_id,
            "part_number": "PN-CHAIN-1",
            "description": "Fuel pump",
            "quantity": 2,
            "reason": "Release readiness chain test",
        },
        headers=headers,
    )
    assert procurement_resp.status_code == 201
    procurement_request_id = procurement_resp.json()["id"]

    # procurement_service.approve_request forbids self-approval (the
    # requester and approver must differ) and this test only has a single
    # registered admin user/token available through the HTTP API. The
    # approve step itself is exercised independently by
    # test_approval_governance.py and test_aog_recovery_service.py's own
    # coverage of procurement_service.approve_request; here it is invoked
    # directly against the same db_session the `client` fixture uses (so it
    # commits into the same transaction the API calls see) with a distinct
    # synthetic approver id, purely to unblock the receiving chain under
    # test. Every other step remains a real HTTP round trip.
    org_id = uuid.UUID(procurement_resp.json()["organization_id"])
    second_approver = User(
        organization_id=org_id,
        email="second-approver@airline-chain.com",
        hashed_password="not-used-for-login",
        full_name="Second Approver",
    )
    db_session.add(second_approver)
    db_session.flush()

    approved = procurement_service.approve_request(
        db_session,
        organization_id=org_id,
        actor_user_id=second_approver.id,
        request_id=uuid.UUID(procurement_request_id),
        payload=ProcurementRequestApproveRequest(selected_vendor_id=uuid.UUID(vendor_id)),
    )
    assert approved.status == "APPROVED"

    po_resp = client.post(
        "/api/v1/purchase-orders",
        json={
            "po_number": "PO-CHAIN-1",
            "vendor_id": vendor_id,
            "lines": [
                {
                    "procurement_request_id": procurement_request_id,
                    "part_number": "PN-CHAIN-1",
                    "description": "Fuel pump",
                    "quantity": 2,
                }
            ],
        },
        headers=headers,
    )
    assert po_resp.status_code == 201, po_resp.json()
    po_id = po_resp.json()["id"]
    line_id = po_resp.json()["lines"][0]["id"]

    for step in ("submit-for-approval", "approve", "send"):
        step_resp = client.post(f"/api/v1/purchase-orders/{po_id}/{step}", headers=headers)
        assert step_resp.status_code == 200, step_resp.json()

    r8 = client.get(f"/api/v1/work-orders/{work_order_id}/release-readiness", headers=headers)
    assert r8.status_code == 200
    assert r8.json()["status"] == "BLOCKED"
    assert {b["category"] for b in r8.json()["blockers"]} == {"MATERIAL"}

    receive_resp = client.post(
        f"/api/v1/purchase-orders/{po_id}/receive",
        json={"lines": [{"line_id": line_id, "quantity": 2}]},
        headers=headers,
    )
    assert receive_resp.status_code == 200, receive_resp.json()

    r9 = client.get(f"/api/v1/work-orders/{work_order_id}/release-readiness", headers=headers)
    assert r9.status_code == 200
    assert r9.json()["blockers"] == []
    assert r9.json()["status"] == "READY"
