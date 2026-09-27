"""One true end-to-end operational golden-path test (Developer 1 Lifecycle
sprint, Phase 3): proves the full chain

    Asset -> Configuration/Component -> Mission -> Flight -> Utilization
    -> Inspection -> Finding -> Work Order -> Maintenance -> Follow-up
    Inspection -> Release -> Lifecycle History -> Operational State

is actually connected end to end through real production API/service paths
-- not that each module works in isolation. Every step uses the real HTTP
API (via `client`), the same paths a real user/frontend would call.
"""

import uuid
from datetime import UTC, datetime, timedelta

from app.core.deps import get_db_session
from app.main import app
from app.models.audit_event import AuditEvent
from app.models.plan import Plan, PlanFeature
from app.models.subscription import Subscription, SubscriptionStatus


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _register(client, org_name, email):
    from tests.integration.conftest import make_platform_admin_headers

    db_session = next(app.dependency_overrides[get_db_session]())
    headers = make_platform_admin_headers(client, db_session)
    resp = client.post(
        "/api/v1/auth/register-organization",
        json={
            "organization_name": org_name,
            "admin_email": email,
            "admin_full_name": "Admin",
            "admin_password": "supersecret123",
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _get_org_id(client, token):
    return uuid.UUID(
        client.get("/api/v1/auth/me", headers=_auth(token)).json()["organization_id"]
    )


def _entitle(db_session, org_id, *feature_keys):
    """Ensure org_id has the named features enabled on an active subscription."""
    from sqlalchemy import select

    sub = db_session.execute(
        select(Subscription).where(
            Subscription.organization_id == org_id,
            Subscription.status.in_(["ACTIVE", "TRIALING", "PAST_DUE"]),
        )
    ).scalars().first()
    if sub:
        for key in feature_keys:
            pf = db_session.execute(
                select(PlanFeature).where(
                    PlanFeature.plan_id == sub.plan_id,
                    PlanFeature.feature_key == key,
                )
            ).scalar_one_or_none()
            if pf is None:
                db_session.add(PlanFeature(plan_id=sub.plan_id, feature_key=key, enabled=True))
            elif not pf.enabled:
                pf.enabled = True
        db_session.commit()
        return

    plan = Plan(name=f"GP-Plan-{uuid.uuid4().hex[:8]}", code=f"gp-plan-{uuid.uuid4().hex[:12]}", is_active=True)
    db_session.add(plan)
    db_session.commit()
    db_session.refresh(plan)
    for key in feature_keys:
        db_session.add(PlanFeature(plan_id=plan.id, feature_key=key, enabled=True))
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


def test_full_operational_lifecycle_golden_path(client, db_session):
    # 1-3. Create organization/tenant, authorized user, entitle required features.
    tokens = _register(client, "Golden Path Airlines", "admin@goldenpath.com")
    headers = _auth(tokens["access_token"])
    org_id = _get_org_id(client, tokens["access_token"])
    _entitle(db_session, org_id, "drone_fleet_management", "work_order_management")

    # 4. Create asset.
    asset_resp = client.post(
        "/api/v1/drones",
        headers=headers,
        json={"registration": "DRN-GP-1", "manufacturer": "DJI", "model": "M300"},
    )
    assert asset_resp.status_code == 201, asset_resp.text
    asset_id = asset_resp.json()["id"]

    ctx = client.get(f"/api/v1/assets/{asset_id}/context", headers=headers)
    assert ctx.status_code == 200
    assert ctx.json()["operational_status"] == "AVAILABLE"

    # 5-7. Configure asset / add + install component.
    component_resp = client.post(
        f"/api/v1/assets/{asset_id}/components",
        headers=headers,
        json={"component_type": "GPS", "name": "Primary GPS", "serial_number": "GPS-GP-1"},
    )
    assert component_resp.status_code == 201, component_resp.text
    component_id = component_resp.json()["id"]

    components = client.get(f"/api/v1/assets/{asset_id}/components", headers=headers)
    assert components.status_code == 200
    assert any(c["id"] == component_id for c in components.json())

    # 8. Create mission.
    mission_resp = client.post(
        "/api/v1/missions",
        headers=headers,
        json={"asset_id": asset_id, "purpose": "Golden Path Survey"},
    )
    assert mission_resp.status_code == 201, mission_resp.text
    mission_id = mission_resp.json()["id"]

    auth_resp = client.post(f"/api/v1/missions/{mission_id}/authorize", headers=headers)
    assert auth_resp.status_code == 200

    ctx = client.get(f"/api/v1/assets/{asset_id}/context", headers=headers)
    assert ctx.json()["operational_status"] == "IN_MISSION"

    # 9. Complete/record flight. (Drone assets must use the drone-specific
    # flight endpoint, not the generic /assets one -- it also maintains
    # attached battery cycle counts; confirmed by the API's own 400 rejection.)
    flight_resp = client.post(
        f"/api/v1/drones/{asset_id}/flights",
        headers=headers,
        json={
            "flown_at": datetime.now(UTC).isoformat(),
            "duration_minutes": 45,
            "cycles": 1,
            "mission_id": mission_id,
        },
    )
    assert flight_resp.status_code == 201, flight_resp.text

    complete_mission_resp = client.patch(
        f"/api/v1/missions/{mission_id}", headers=headers, json={"status": "COMPLETED"}
    )
    assert complete_mission_resp.status_code == 200

    # 10. Record/verify utilization.
    utilization_resp = client.get(f"/api/v1/assets/{asset_id}/utilization", headers=headers)
    assert utilization_resp.status_code == 200
    util_body = utilization_resp.json()
    assert util_body["total_flight_hours"] > 0 or util_body.get("total_cycles", 0) > 0

    # Work order created early so it can host the inspection requirement,
    # finding linkage, and task-execution gate.
    wo_resp = client.post(
        "/api/v1/work-orders",
        headers=headers,
        json={
            "asset_id": asset_id,
            "work_order_number": "WO-GP-1",
            "title": "Post-flight GPS inspection & corrective action",
        },
    )
    assert wo_resp.status_code == 201, wo_resp.text
    wo_id = wo_resp.json()["id"]

    # 11. Create inspection (checklist-style, not RII, to keep the golden
    # path's identity requirements minimal -- RII independence is already
    # covered by test_inspection_completion_identity_api.py).
    inspection_resp = client.post(
        "/api/v1/inspections",
        headers=headers,
        json={"work_order_id": wo_id, "required": False},
    )
    assert inspection_resp.status_code == 201, inspection_resp.text
    inspection_id = inspection_resp.json()["id"]

    # 12. Create finding, linked to both the asset and the work order.
    finding_resp = client.post(
        "/api/v1/findings",
        headers=headers,
        json={
            "title": "GPS drift detected",
            "description": "Post-flight review shows GPS drift exceeding tolerance.",
            "severity": "MAJOR",
            "asset_id": asset_id,
            "component_id": component_id,
            "work_order_id": wo_id,
        },
    )
    assert finding_resp.status_code == 201, finding_resp.text
    finding_id = finding_resp.json()["id"]

    ctx = client.get(f"/api/v1/assets/{asset_id}/context", headers=headers)
    assert ctx.json()["operational_status"] == "MAINTENANCE"

    # 13. Assign technician (work order level -- ASSIGNED requires this).
    me_resp = client.get("/api/v1/auth/me", headers=headers)
    admin_user_id = me_resp.json()["id"]

    # Task created and completed before the IN_PROGRESS -> INSPECTION gate.
    task_resp = client.post(
        f"/api/v1/work-orders/{wo_id}/tasks",
        headers=headers,
        json={"description": "Reseat and recalibrate GPS module"},
    )
    assert task_resp.status_code == 201, task_resp.text
    task_id = task_resp.json()["id"]

    for target_status in ("OPEN", "PLANNED"):
        t = client.post(
            f"/api/v1/work-orders/{wo_id}/transition",
            headers=headers,
            json={"target_status": target_status},
        )
        assert t.status_code == 200, t.text

    assign_resp = client.post(
        f"/api/v1/work-orders/{wo_id}/assign",
        headers=headers,
        json={"assigned_to_user_id": admin_user_id},
    )
    assert assign_resp.status_code == 200, assign_resp.text

    in_progress_resp = client.post(
        f"/api/v1/work-orders/{wo_id}/transition",
        headers=headers,
        json={"target_status": "IN_PROGRESS"},
    )
    assert in_progress_resp.status_code == 200, in_progress_resp.text

    # 15. Complete maintenance (task execution).
    complete_task_resp = client.post(
        f"/api/v1/work-orders/{wo_id}/tasks/{task_id}/complete", headers=headers
    )
    assert complete_task_resp.status_code == 200, complete_task_resp.text

    to_inspection_resp = client.post(
        f"/api/v1/work-orders/{wo_id}/transition",
        headers=headers,
        json={"target_status": "INSPECTION"},
    )
    assert to_inspection_resp.status_code == 200, to_inspection_resp.text

    # 16. Perform (follow-up) inspection: complete the requirement created
    # earlier -- this IS the follow-up inspection the roadmap's step 16
    # names, performed after maintenance execution, gating INSPECTION->COMPLETED.
    complete_inspection_resp = client.post(
        f"/api/v1/inspections/{inspection_id}/transition",
        headers=headers,
        json={"target_status": "COMPLETED", "inspector_user_id": admin_user_id},
    )
    assert complete_inspection_resp.status_code == 200, complete_inspection_resp.text

    to_completed_resp = client.post(
        f"/api/v1/work-orders/{wo_id}/transition",
        headers=headers,
        json={"target_status": "COMPLETED"},
    )
    assert to_completed_resp.status_code == 200, to_completed_resp.text

    # Close the finding before closure -- an open Finding linked to this
    # work order/asset is a release-readiness blocker. A disposition is
    # required before a finding can be closed.
    disposition_resp = client.post(
        f"/api/v1/findings/{finding_id}/dispositions",
        headers=headers,
        json={"disposition_type": "CORRECTIVE_ACTION", "corrective_action": "Recalibrated GPS module"},
    )
    assert disposition_resp.status_code == 200, disposition_resp.text

    close_finding_resp = client.post(f"/api/v1/findings/{finding_id}/close", headers=headers)
    assert close_finding_resp.status_code == 200, close_finding_resp.text

    readiness_resp = client.get(f"/api/v1/work-orders/{wo_id}/release-readiness", headers=headers)
    assert readiness_resp.status_code == 200
    assert readiness_resp.json()["status"] == "READY", readiness_resp.text

    # 17. Release asset -- COMPLETED -> CLOSED, gated on release readiness.
    close_resp = client.post(
        f"/api/v1/work-orders/{wo_id}/transition",
        headers=headers,
        json={"target_status": "CLOSED"},
    )
    assert close_resp.status_code == 200, close_resp.text

    # 18. Query lifecycle history -- every major milestone must appear.
    history_resp = client.get(f"/api/v1/assets/{asset_id}/history", headers=headers)
    assert history_resp.status_code == 200
    event_types = {e["event_type"] for e in history_resp.json()["events"]}
    assert {
        "MISSION_CREATED",
        "MISSION_COMPLETED",
        "FLIGHT_SORTIE",
        "COMPONENT_INSTALLATION",
        "WORK_ORDER_CREATED",
        "WORK_ORDER_COMPLETED",
        "WORK_ORDER_CLOSED",
        "FINDING_CREATED",
        "FINDING_CLOSED",
        "INSPECTION_COMPLETED",
    }.issubset(event_types)

    # 19-20. Query and verify operational state -- back to AVAILABLE now
    # that the work order is closed and the finding is closed.
    final_ctx = client.get(f"/api/v1/assets/{asset_id}/context", headers=headers)
    assert final_ctx.status_code == 200
    assert final_ctx.json()["operational_status"] == "AVAILABLE"

    # 21. Verify domain/audit events were actually persisted (not just
    # reflected back through the timeline projection).
    audit_actions = {
        row.action
        for row in db_session.query(AuditEvent)
        .filter(AuditEvent.organization_id == org_id)
        .all()
    }
    assert {
        "mission.created",
        "mission.authorized",
        "work_order.created",
        "work_order.assigned",
        "work_order.transitioned",
        "finding.created",
        "finding.closed",
        "inspection.completed",
    }.issubset(audit_actions)

    # 22. Verify tenant isolation: a second organization cannot see any of
    # this organization's operational data.
    tokens_b = _register(client, "Golden Path Rival Airlines", "admin@goldenpathrival.com")
    headers_b = _auth(tokens_b["access_token"])
    # Entitle org B the same way -- otherwise every feature-gated route 403s
    # on the entitlement check before ever reaching the tenant-isolation
    # check this section exists to prove (a 403-for-no-feature and a
    # 404-for-wrong-tenant are both "denied", but they are different checks;
    # entitling org B isolates the one this test is actually verifying).
    _entitle(db_session, _get_org_id(client, tokens_b["access_token"]), "drone_fleet_management", "work_order_management")

    assert client.get(f"/api/v1/assets/{asset_id}/context", headers=headers_b).status_code == 404
    assert client.get(f"/api/v1/assets/{asset_id}/history", headers=headers_b).status_code == 404
    assert client.get(f"/api/v1/missions/{mission_id}", headers=headers_b).status_code == 404
    assert client.get(f"/api/v1/work-orders/{wo_id}", headers=headers_b).status_code == 404
    assert client.get(f"/api/v1/findings/{finding_id}", headers=headers_b).status_code == 404
