"""Comprehensive integration tests for Work Order Lifecycle & MRO Operations (Milestone M22).

Covers:
- CRUD and rich query filtering
- State machine transitions and transition gates
- Task gates and completion
- Release readiness integration on closure
- Mandatory cancellation validation
- Strict cross-tenant isolation
- RBAC permissions (TECHNICIAN_WRITE vs AIRCRAFT_WRITE)
- Entitlement enforcement ("work_order_management")
- TAT status endpoint
- Audit trail recording
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.core.deps import get_db_session
from app.main import app
from app.core.permissions import Role
from app.models.audit_event import AuditEvent
from app.models.plan import Plan, PlanFeature
from app.models.subscription import Subscription, SubscriptionStatus
from app.models.user import User, UserRole


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


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _get_org_id(client, token):
    return uuid.UUID(
        client.get("/api/v1/auth/me", headers=_auth(token)).json()["organization_id"]
    )


def _entitle_work_orders(db_session, org_id):
    sub = db_session.execute(
        select(Subscription).where(
            Subscription.organization_id == org_id,
            Subscription.status.in_(["ACTIVE", "TRIALING", "PAST_DUE"]),
        )
    ).scalars().first()
    if sub:
        pf = db_session.execute(
            select(PlanFeature).where(
                PlanFeature.plan_id == sub.plan_id,
                PlanFeature.feature_key == "work_order_management",
            )
        ).scalar_one_or_none()
        if pf is None:
            db_session.add(PlanFeature(plan_id=sub.plan_id, feature_key="work_order_management", enabled=True))
            db_session.commit()
        elif not pf.enabled:
            pf.enabled = True
            db_session.commit()
        return

    plan = Plan(
        name=f"WO-Plan-{org_id}",
        code=f"wo-plan-{org_id}",
        is_active=True,
    )
    db_session.add(plan)
    db_session.commit()
    db_session.refresh(plan)
    db_session.add(
        PlanFeature(plan_id=plan.id, feature_key="work_order_management", enabled=True)
    )
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


def _create_aircraft(client, headers, reg="N900WO"):
    resp = client.post(
        "/api/v1/aircraft",
        json={"registration": reg, "msn": f"MSN-{reg}", "aircraft_type": "B737"},
        headers=headers,
    )
    assert resp.status_code == 201
    return resp.json()["id"]


def test_work_order_crud_and_rich_filtering(client, db_session):
    tokens = _register(client, "Air Trans 1", "admin@airtrans1.com")
    headers = _auth(tokens["access_token"])
    org_id = _get_org_id(client, tokens["access_token"])
    _entitle_work_orders(db_session, org_id)

    aircraft_id = _create_aircraft(client, headers, "N101CRUD")

    # 1. Create with new fields
    due_at = (datetime.now(UTC) + timedelta(days=5)).isoformat()
    create_resp = client.post(
        "/api/v1/work-orders",
        json={
            "aircraft_id": aircraft_id,
            "work_order_number": "WO-CRUD-100",
            "title": "Aileron Rigging Check",
            "description": "Perform full functional rigging inspection on primary control surfaces.",
            "priority": "HIGH",
            "work_order_type": "CORRECTIVE",
            "maintenance_category": "AIRFRAME",
            "due_at": due_at,
            "estimated_hours": 6.5,
            "location": "Hangar 2, Bay 4",
        },
        headers=headers,
    )
    assert create_resp.status_code == 201, create_resp.text
    wo_data = create_resp.json()
    wo_id = wo_data["id"]
    assert wo_data["status"] == "DRAFT"
    assert wo_data["title"] == "Aileron Rigging Check"
    assert wo_data["work_order_type"] == "CORRECTIVE"
    assert wo_data["estimated_hours"] == 6.5
    assert wo_data["location"] == "Hangar 2, Bay 4"

    # 2. Get Work Order
    get_resp = client.get(f"/api/v1/work-orders/{wo_id}", headers=headers)
    assert get_resp.status_code == 200
    assert get_resp.json()["work_order_number"] == "WO-CRUD-100"

    # 3. Patch Work Order
    patch_resp = client.patch(
        f"/api/v1/work-orders/{wo_id}",
        json={
            "title": "Updated Aileron Check",
            "estimated_hours": 8.0,
            "location": "Hangar 3, Bay 1",
        },
        headers=headers,
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["title"] == "Updated Aileron Check"
    assert patch_resp.json()["estimated_hours"] == 8.0
    assert patch_resp.json()["location"] == "Hangar 3, Bay 1"

    # 4. Rich Query Filtering & Header Count
    filter_resp = client.get(
        "/api/v1/work-orders",
        params={
            "status": "DRAFT",
            "priority": "HIGH",
            "work_order_type": "CORRECTIVE",
            "search": "Updated",
        },
        headers=headers,
    )
    assert filter_resp.status_code == 200
    items = filter_resp.json()
    assert len(items) >= 1
    assert items[0]["id"] == wo_id
    assert "X-Total-Count" in filter_resp.headers


def test_work_order_lifecycle_transitions_and_gates(client, db_session):
    tokens = _register(client, "Air Trans 2", "admin@airtrans2.com")
    headers = _auth(tokens["access_token"])
    org_id = _get_org_id(client, tokens["access_token"])
    _entitle_work_orders(db_session, org_id)

    aircraft_id = _create_aircraft(client, headers, "N202GATE")

    create_resp = client.post(
        "/api/v1/work-orders",
        json={
            "aircraft_id": aircraft_id,
            "work_order_number": "WO-GATE-200",
            "title": "Engine Filter Replacement",
        },
        headers=headers,
    )
    assert create_resp.status_code == 201
    wo_id = create_resp.json()["id"]

    # Gate 1: DRAFT -> OPEN
    trans_resp = client.post(
        f"/api/v1/work-orders/{wo_id}/transition",
        json={"target_status": "OPEN"},
        headers=headers,
    )
    assert trans_resp.status_code == 200
    assert trans_resp.json()["status"] == "OPEN"

    # Gate 2: OPEN -> PLANNED
    trans_resp = client.post(
        f"/api/v1/work-orders/{wo_id}/transition",
        json={"target_status": "PLANNED"},
        headers=headers,
    )
    assert trans_resp.status_code == 200
    assert trans_resp.json()["status"] == "PLANNED"

    # Gate 3: PLANNED -> ASSIGNED requires valid assignment
    invalid_trans = client.post(
        f"/api/v1/work-orders/{wo_id}/transition",
        json={"target_status": "ASSIGNED"},
        headers=headers,
    )
    assert invalid_trans.status_code in (400, 409)
    assert "assigned technician" in invalid_trans.text.lower()

    # Assign technician to the work order
    tech_user = User(
        email=f"tech-{uuid.uuid4().hex[:6]}@airtrans2.com",
        full_name="Certified Tech",
        hashed_password="pw",
        organization_id=org_id,
        is_active=True,
    )
    db_session.add(tech_user)
    db_session.flush()
    db_session.add(
        UserRole(
            user_id=tech_user.id,
            role_name=Role.MAINTENANCE_ENGINEER.value,
            organization_id=org_id,
        )
    )
    db_session.commit()
    db_session.refresh(tech_user)

    assign_resp = client.post(
        f"/api/v1/work-orders/{wo_id}/assign",
        json={"assigned_to_user_id": str(tech_user.id)},
        headers=headers,
    )
    assert assign_resp.status_code == 200
    assert assign_resp.json()["status"] == "ASSIGNED"
    assert assign_resp.json()["assigned_to_user_id"] == str(tech_user.id)

    # Gate 4: ASSIGNED -> IN_PROGRESS sets actual_start
    start_resp = client.post(
        f"/api/v1/work-orders/{wo_id}/transition",
        json={"target_status": "IN_PROGRESS"},
        headers=headers,
    )
    assert start_resp.status_code == 200
    wo_started = start_resp.json()
    assert wo_started["status"] == "IN_PROGRESS"
    assert wo_started["actual_start"] is not None

    # Gate 5: IN_PROGRESS <-> ON_HOLD
    hold_resp = client.post(
        f"/api/v1/work-orders/{wo_id}/transition",
        json={"target_status": "ON_HOLD", "reason": "Awaiting special tool"},
        headers=headers,
    )
    assert hold_resp.status_code == 200
    assert hold_resp.json()["status"] == "ON_HOLD"

    resume_resp = client.post(
        f"/api/v1/work-orders/{wo_id}/transition",
        json={"target_status": "IN_PROGRESS"},
        headers=headers,
    )
    assert resume_resp.status_code == 200
    assert resume_resp.json()["status"] == "IN_PROGRESS"


def test_task_gate_and_work_order_completion_and_closure(client, db_session):
    tokens = _register(client, "Air Trans 3", "admin@airtrans3.com")
    headers = _auth(tokens["access_token"])
    org_id = _get_org_id(client, tokens["access_token"])
    _entitle_work_orders(db_session, org_id)

    aircraft_id = _create_aircraft(client, headers, "N303TASK")

    wo_resp = client.post(
        "/api/v1/work-orders",
        json={"aircraft_id": aircraft_id, "work_order_number": "WO-TASK-300"},
        headers=headers,
    )
    wo_id = wo_resp.json()["id"]

    # Move to IN_PROGRESS
    client.post(f"/api/v1/work-orders/{wo_id}/transition", json={"target_status": "OPEN"}, headers=headers)
    client.post(f"/api/v1/work-orders/{wo_id}/transition", json={"target_status": "PLANNED"}, headers=headers)

    tech = User(
        email=f"tech-{uuid.uuid4().hex[:6]}@airtrans3.com",
        full_name="Lead Tech",
        hashed_password="pw",
        organization_id=org_id,
        is_active=True,
    )
    db_session.add(tech)
    db_session.flush()
    db_session.add(
        UserRole(
            user_id=tech.id,
            role_name=Role.MAINTENANCE_ENGINEER.value,
            organization_id=org_id,
        )
    )
    db_session.commit()

    client.post(
        f"/api/v1/work-orders/{wo_id}/assign",
        json={"assigned_to_user_id": str(tech.id)},
        headers=headers,
    )
    client.post(f"/api/v1/work-orders/{wo_id}/transition", json={"target_status": "IN_PROGRESS"}, headers=headers)

    # Add 2 tasks
    t1_resp = client.post(
        f"/api/v1/work-orders/{wo_id}/tasks",
        json={
            "description": "Inspect hydraulic actuator",
            "task_number": "TASK-1",
            "estimated_hours": 2.0,
        },
        headers=headers,
    )
    assert t1_resp.status_code == 201
    t1_id = t1_resp.json()["id"]

    t2_resp = client.post(
        f"/api/v1/work-orders/{wo_id}/tasks",
        json={
            "description": "Purge line and verify pressure",
            "task_number": "TASK-2",
            "estimated_hours": 1.5,
        },
        headers=headers,
    )
    assert t2_resp.status_code == 201
    t2_id = t2_resp.json()["id"]

    # Gate: IN_PROGRESS -> INSPECTION blocked if tasks are incomplete
    premature_insp = client.post(
        f"/api/v1/work-orders/{wo_id}/transition",
        json={"target_status": "INSPECTION"},
        headers=headers,
    )
    assert premature_insp.status_code in (400, 409)
    assert "uncompleted" in premature_insp.text.lower()

    # Complete task 1
    c1 = client.post(f"/api/v1/work-orders/{wo_id}/tasks/{t1_id}/complete", headers=headers)
    assert c1.status_code == 200
    assert c1.json()["execution_state"] == "COMPLETED"

    # Still 1 task incomplete
    premature_insp2 = client.post(
        f"/api/v1/work-orders/{wo_id}/transition",
        json={"target_status": "INSPECTION"},
        headers=headers,
    )
    assert premature_insp2.status_code in (400, 409)

    # Complete task 2
    c2 = client.post(f"/api/v1/work-orders/{wo_id}/tasks/{t2_id}/complete", headers=headers)
    assert c2.status_code == 200
    assert c2.json()["execution_state"] == "COMPLETED"

    # Now IN_PROGRESS -> INSPECTION succeeds!
    insp_resp = client.post(
        f"/api/v1/work-orders/{wo_id}/transition",
        json={"target_status": "INSPECTION"},
        headers=headers,
    )
    assert insp_resp.status_code == 200
    assert insp_resp.json()["status"] == "INSPECTION"

    # Complete Work Order
    comp_resp = client.post(f"/api/v1/work-orders/{wo_id}/complete", headers=headers)
    assert comp_resp.status_code == 200
    assert comp_resp.json()["status"] == "COMPLETED"
    assert comp_resp.json()["completed_at"] is not None

    # Close Work Order (Release readiness gate)
    close_resp = client.post(f"/api/v1/work-orders/{wo_id}/close", headers=headers)
    assert close_resp.status_code == 200
    assert close_resp.json()["status"] == "CLOSED"
    assert close_resp.json()["closed_at"] is not None

    # Closed is terminal
    post_close = client.post(
        f"/api/v1/work-orders/{wo_id}/transition",
        json={"target_status": "IN_PROGRESS"},
        headers=headers,
    )
    assert post_close.status_code in (400, 409)


def test_work_order_cancellation_validation(client, db_session):
    tokens = _register(client, "Air Trans 4", "admin@airtrans4.com")
    headers = _auth(tokens["access_token"])
    org_id = _get_org_id(client, tokens["access_token"])
    _entitle_work_orders(db_session, org_id)

    aircraft_id = _create_aircraft(client, headers, "N404CANCEL")
    wo_resp = client.post(
        "/api/v1/work-orders",
        json={"aircraft_id": aircraft_id, "work_order_number": "WO-CANCEL-400"},
        headers=headers,
    )
    wo_id = wo_resp.json()["id"]

    # Short cancellation reason fails (< 3 chars)
    short_resp = client.post(
        f"/api/v1/work-orders/{wo_id}/cancel",
        json={"cancellation_reason": "no"},
        headers=headers,
    )
    assert short_resp.status_code in (400, 422)

    # Valid cancellation succeeds
    cancel_resp = client.post(
        f"/api/v1/work-orders/{wo_id}/cancel",
        json={"cancellation_reason": "Aircraft mission cancelled permanently"},
        headers=headers,
    )
    assert cancel_resp.status_code == 200
    cancelled = cancel_resp.json()
    assert cancelled["status"] == "CANCELLED"
    assert cancelled["cancelled_at"] is not None
    assert cancelled["cancellation_reason"] == "Aircraft mission cancelled permanently"

    # CANCELLED is terminal
    retry = client.post(
        f"/api/v1/work-orders/{wo_id}/transition",
        json={"target_status": "OPEN"},
        headers=headers,
    )
    assert retry.status_code in (400, 409)


def test_cross_tenant_isolation(client, db_session):
    tokens_a = _register(client, "Org Alpha", "admin@alpha.com")
    headers_a = _auth(tokens_a["access_token"])
    org_a_id = _get_org_id(client, tokens_a["access_token"])
    _entitle_work_orders(db_session, org_a_id)

    tokens_b = _register(client, "Org Beta", "admin@beta.com")
    headers_b = _auth(tokens_b["access_token"])
    org_b_id = _get_org_id(client, tokens_b["access_token"])
    _entitle_work_orders(db_session, org_b_id)

    # Org A creates an aircraft and work order
    aircraft_a = _create_aircraft(client, headers_a, "N-ALPHA-1")
    wo_a_resp = client.post(
        "/api/v1/work-orders",
        json={"aircraft_id": aircraft_a, "work_order_number": "WO-ALPHA-01"},
        headers=headers_a,
    )
    wo_a_id = wo_a_resp.json()["id"]

    # Org B cannot list Org A's work order
    list_b = client.get("/api/v1/work-orders", headers=headers_b)
    assert list_b.status_code == 200
    wo_ids_b = [w["id"] for w in list_b.json()]
    assert wo_a_id not in wo_ids_b

    # Org B cannot get Org A's work order (404, not leaked)
    assert client.get(f"/api/v1/work-orders/{wo_a_id}", headers=headers_b).status_code == 404

    # Org B cannot update Org A's work order
    assert (
        client.patch(
            f"/api/v1/work-orders/{wo_a_id}",
            json={"title": "Hacked Title"},
            headers=headers_b,
        ).status_code
        == 404
    )

    # Org B cannot assign Org A's work order
    assert (
        client.post(
            f"/api/v1/work-orders/{wo_a_id}/assign",
            json={"assigned_to_user_id": str(uuid.uuid4())},
            headers=headers_b,
        ).status_code
        == 404
    )

    # Org B cannot transition Org A's work order
    assert (
        client.post(
            f"/api/v1/work-orders/{wo_a_id}/transition",
            json={"target_status": "OPEN"},
            headers=headers_b,
        ).status_code
        == 404
    )

    # Org B cannot add tasks to Org A's work order
    assert (
        client.post(
            f"/api/v1/work-orders/{wo_a_id}/tasks",
            json={"description": "Unauthorized task"},
            headers=headers_b,
        ).status_code
        == 404
    )

    # Org B cannot complete, close, cancel, or delete Org A's work order
    assert client.post(f"/api/v1/work-orders/{wo_a_id}/complete", headers=headers_b).status_code == 404
    assert client.post(f"/api/v1/work-orders/{wo_a_id}/close", headers=headers_b).status_code == 404
    assert (
        client.post(
            f"/api/v1/work-orders/{wo_a_id}/cancel",
            json={"cancellation_reason": "Malicious cancellation"},
            headers=headers_b,
        ).status_code
        == 404
    )
    assert client.delete(f"/api/v1/work-orders/{wo_a_id}", headers=headers_b).status_code == 404


def test_entitlement_enforcement(client, db_session):
    from sqlalchemy import delete
    # Register an organization and remove its subscription to test unentitled behavior
    tokens_unentitled = _register(client, "Unentitled Org", "admin@unentitled.com")
    headers = _auth(tokens_unentitled["access_token"])
    org_id = _get_org_id(client, tokens_unentitled["access_token"])
    db_session.execute(delete(Subscription).where(Subscription.organization_id == org_id))
    db_session.commit()

    # Attempting to list or create work orders yields 403 Forbidden
    list_resp = client.get("/api/v1/work-orders", headers=headers)
    assert list_resp.status_code == 403

    create_resp = client.post(
        "/api/v1/work-orders",
        json={"work_order_number": "WO-UNENTITLED-1"},
        headers=headers,
    )
    assert create_resp.status_code == 403


def test_tat_status_endpoint_live(client, db_session):
    tokens = _register(client, "Air Trans TAT", "admin@airtrans-tat.com")
    headers = _auth(tokens["access_token"])
    org_id = _get_org_id(client, tokens["access_token"])
    _entitle_work_orders(db_session, org_id)

    aircraft_id = _create_aircraft(client, headers, "N-TAT-99")

    # Due in 5 days -> ON_TRACK
    due_at = (datetime.now(UTC) + timedelta(days=5)).isoformat()
    wo_resp = client.post(
        "/api/v1/work-orders",
        json={
            "aircraft_id": aircraft_id,
            "work_order_number": "WO-TAT-99",
            "due_at": due_at,
        },
        headers=headers,
    )
    wo_id = wo_resp.json()["id"]

    tat_resp = client.get(f"/api/v1/work-orders/{wo_id}/tat", headers=headers)
    assert tat_resp.status_code == 200
    tat = tat_resp.json()
    assert tat["status"] == "ON_TRACK"
    assert tat["days_remaining"] == 5

    fleet_tat_resp = client.get("/api/v1/fleet/tat", headers=headers)
    assert fleet_tat_resp.status_code == 200
    fleet = fleet_tat_resp.json()
    assert fleet["on_track_count"] >= 1


def test_audit_event_logging(client, db_session):
    tokens = _register(client, "Air Trans Audit", "admin@airtrans-audit.com")
    headers = _auth(tokens["access_token"])
    org_id = _get_org_id(client, tokens["access_token"])
    _entitle_work_orders(db_session, org_id)

    aircraft_id = _create_aircraft(client, headers, "N-AUDIT-1")
    wo_resp = client.post(
        "/api/v1/work-orders",
        json={"aircraft_id": aircraft_id, "work_order_number": "WO-AUDIT-01"},
        headers=headers,
    )
    wo_id = wo_resp.json()["id"]

    # Transition to OPEN
    client.post(
        f"/api/v1/work-orders/{wo_id}/transition",
        json={"target_status": "OPEN"},
        headers=headers,
    )

    # Verify audit event in database
    audit_events = list(
        db_session.execute(
            select(AuditEvent).where(
                AuditEvent.organization_id == org_id,
                AuditEvent.entity_id == uuid.UUID(wo_id),
            )
        )
        .scalars()
        .all()
    )
    actions = [e.action for e in audit_events]
    assert any("work_order.created" in a for a in actions)
    assert any("work_order.transition" in a for a in actions)


def test_rbac_technician_vs_admin(client, db_session):
    from app.core.security import hash_password

    # 1. Register admin organization
    tokens_admin = _register(client, "Air Trans RBAC", "admin@airtrans-rbac.com")
    headers_admin = _auth(tokens_admin["access_token"])
    org_id = _get_org_id(client, tokens_admin["access_token"])
    _entitle_work_orders(db_session, org_id)

    aircraft_id = _create_aircraft(client, headers_admin, "N-RBAC-1")

    # 2. Create technician user with MAINTENANCE_ENGINEER role (has TECHNICIAN_WRITE)
    tech_email = "tech@airtrans-rbac.com"
    tech_password = "technician123"
    tech_user = User(
        email=tech_email,
        full_name="Field Technician",
        hashed_password=hash_password(tech_password),
        organization_id=org_id,
        is_active=True,
    )
    db_session.add(tech_user)
    db_session.flush()
    db_session.add(
        UserRole(
            user_id=tech_user.id,
            role_name=Role.MAINTENANCE_ENGINEER.value,
            organization_id=org_id,
        )
    )
    db_session.commit()

    # Login as technician
    tech_login = client.post(
        "/api/v1/auth/login",
        json={"email": tech_email, "password": tech_password},
    )
    assert tech_login.status_code == 200, tech_login.text
    headers_tech = _auth(tech_login.json()["access_token"])

    # 3. Technician CANNOT create work orders (requires AIRCRAFT_WRITE)
    tech_create = client.post(
        "/api/v1/work-orders",
        json={"aircraft_id": aircraft_id, "work_order_number": "WO-ILLEGAL-1"},
        headers=headers_tech,
    )
    assert tech_create.status_code == 403

    # 4. Admin creates and sets up work order into IN_PROGRESS
    wo_resp = client.post(
        "/api/v1/work-orders",
        json={"aircraft_id": aircraft_id, "work_order_number": "WO-RBAC-OK"},
        headers=headers_admin,
    )
    wo_id = wo_resp.json()["id"]
    client.post(f"/api/v1/work-orders/{wo_id}/transition", json={"target_status": "OPEN"}, headers=headers_admin)
    client.post(f"/api/v1/work-orders/{wo_id}/transition", json={"target_status": "PLANNED"}, headers=headers_admin)
    client.post(
        f"/api/v1/work-orders/{wo_id}/assign",
        json={"assigned_to_user_id": str(tech_user.id)},
        headers=headers_admin,
    )
    client.post(f"/api/v1/work-orders/{wo_id}/transition", json={"target_status": "IN_PROGRESS"}, headers=headers_admin)

    # 5. Technician CAN execute operational transitions (e.g. IN_PROGRESS -> ON_HOLD)
    hold_resp = client.post(
        f"/api/v1/work-orders/{wo_id}/transition",
        json={"target_status": "ON_HOLD", "reason": "Technician pause"},
        headers=headers_tech,
    )
    assert hold_resp.status_code == 200
    assert hold_resp.json()["status"] == "ON_HOLD"

    # 6. Technician CANNOT add tasks (requires AIRCRAFT_WRITE)
    tech_add_task = client.post(
        f"/api/v1/work-orders/{wo_id}/tasks",
        json={"description": "Technician operational check"},
        headers=headers_tech,
    )
    assert tech_add_task.status_code == 403

    # Admin adds task
    admin_add_task = client.post(
        f"/api/v1/work-orders/{wo_id}/tasks",
        json={"description": "Administrative work order task"},
        headers=headers_admin,
    )
    assert admin_add_task.status_code == 201
    task_id = admin_add_task.json()["id"]

    # Technician CAN complete tasks (has TECHNICIAN_WRITE)
    comp_task = client.post(
        f"/api/v1/work-orders/{wo_id}/tasks/{task_id}/complete",
        headers=headers_tech,
    )
    assert comp_task.status_code == 200

    # 7. Technician CANNOT perform administrative closure, cancellation, or deletion
    assert client.post(f"/api/v1/work-orders/{wo_id}/close", headers=headers_tech).status_code == 403
    assert (
        client.post(
            f"/api/v1/work-orders/{wo_id}/cancel",
            json={"cancellation_reason": "Not allowed"},
            headers=headers_tech,
        ).status_code
        == 403
    )
    assert client.delete(f"/api/v1/work-orders/{wo_id}", headers=headers_tech).status_code == 403

