"""Phase 3 of the WorkOrder lifecycle feature: DELETE /work-orders/{id} and
POST /work-orders/{id}/restore.

Lifecycle state is deleted_at IS NULL (ACTIVE) vs. deleted_at IS NOT NULL
(DELETED) only -- no second status value, no is_deleted/is_active column
(see app/db/base.py's LifecycleMixin and the approved architecture decision
report). WorkOrder.status must never change across delete/restore.

Fixture conventions match the existing suite: register/entitle pattern from
test_task_completion_api.py and test_work_order_api_authorization.py, and
the User+UserRole role-injection pattern from test_assessments_api.py for
non-ORG_ADMIN roles.
"""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.core.security import hash_password
from app.models.audit_event import AuditEvent
from app.models.plan import Plan, PlanFeature
from app.models.subscription import Subscription, SubscriptionStatus
from app.models.user import User, UserRole
from app.models.work_order import WorkOrder


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


def _entitle_work_orders(db_session, org_id):
    plan = Plan(name=f"WO-LC-Plan-{org_id}", code=f"wo-lc-{org_id}", is_active=True)
    db_session.add(plan)
    db_session.commit()
    db_session.refresh(plan)
    db_session.add(PlanFeature(plan_id=plan.id, feature_key="work_order_management", enabled=True))
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


def _login_as_role(client, db_session, org_id, role_name, email):
    user = User(
        organization_id=org_id,
        email=email,
        hashed_password=hash_password("supersecret123"),
        full_name=f"{role_name} User",
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    db_session.add(UserRole(user_id=user.id, role_name=role_name, organization_id=org_id))
    db_session.commit()

    login_resp = client.post(
        "/api/v1/auth/login", json={"email": email, "password": "supersecret123"}
    )
    assert login_resp.status_code == 200
    return _auth(login_resp.json()["access_token"])


def _setup_org_with_work_order(client, db_session, tag, status="OPEN"):
    tokens = _register(client, f"WO Lifecycle {tag}", f"admin@wo-lc-{tag}.example.com")
    admin_auth = _auth(tokens["access_token"])
    org_id = uuid.UUID(
        client.get("/api/v1/auth/me", headers=admin_auth).json()["organization_id"]
    )
    _entitle_work_orders(db_session, org_id)

    aircraft_resp = client.post(
        "/api/v1/aircraft",
        json={"registration": f"N{tag}", "msn": f"MSN-{tag}", "aircraft_type": "B737"},
        headers=admin_auth,
    )
    assert aircraft_resp.status_code == 201
    aircraft_id = aircraft_resp.json()["id"]

    wo_resp = client.post(
        "/api/v1/work-orders",
        json={
            "aircraft_id": aircraft_id,
            "work_order_number": f"WO-{tag}-1",
            "status": status,
        },
        headers=admin_auth,
    )
    assert wo_resp.status_code == 201
    work_order_id = wo_resp.json()["id"]

    return org_id, admin_auth, aircraft_id, work_order_id


def _delete(client, auth, work_order_id, reason_code="ADMINISTRATIVE_CORRECTION", note=None):
    return client.request(
        "DELETE",
        f"/api/v1/work-orders/{work_order_id}",
        json={"reason_code": reason_code, "note": note},
        headers=auth,
    )


def _restore(client, auth, work_order_id, reason_code="ADMINISTRATIVE_CORRECTION", note=None):
    return client.post(
        f"/api/v1/work-orders/{work_order_id}/restore",
        json={"reason_code": reason_code, "note": note},
        headers=auth,
    )


def _audit_events(db_session, work_order_id, action):
    return list(
        db_session.execute(
            select(AuditEvent).where(
                AuditEvent.entity_id == work_order_id, AuditEvent.action == action
            )
        )
        .scalars()
        .all()
    )


class TestSoftDelete:
    def test_authorized_tenant_can_soft_delete_active_work_order(self, client, db_session):
        _, auth, _, wo_id = _setup_org_with_work_order(client, db_session, "del-1")
        resp = _delete(client, auth, wo_id, reason_code="CREATED_IN_ERROR")
        assert resp.status_code == 204, resp.text

    def test_delete_sets_deleted_at(self, client, db_session):
        _, auth, _, wo_id = _setup_org_with_work_order(client, db_session, "del-2")
        _delete(client, auth, wo_id)
        db_session.expire_all()
        row = db_session.get(WorkOrder, uuid.UUID(wo_id))
        assert row.deleted_at is not None

    def test_delete_sets_deleted_by(self, client, db_session):
        org_id, auth, _, wo_id = _setup_org_with_work_order(client, db_session, "del-3")
        me = client.get("/api/v1/auth/me", headers=auth).json()
        _delete(client, auth, wo_id)
        db_session.expire_all()
        row = db_session.get(WorkOrder, uuid.UUID(wo_id))
        assert str(row.deleted_by) == me["id"]

    def test_delete_does_not_modify_business_status(self, client, db_session):
        _, auth, _, wo_id = _setup_org_with_work_order(client, db_session, "del-4", status="CLOSED")
        _delete(client, auth, wo_id)
        db_session.expire_all()
        row = db_session.get(WorkOrder, uuid.UUID(wo_id))
        assert row.status == "CLOSED"

    def test_delete_creates_exactly_one_audit_event(self, client, db_session):
        _, auth, _, wo_id = _setup_org_with_work_order(client, db_session, "del-5")
        _delete(client, auth, wo_id)
        events = _audit_events(db_session, uuid.UUID(wo_id), "work_order.deleted")
        assert len(events) == 1

    def test_deleted_work_order_excluded_from_normal_list(self, client, db_session):
        _, auth, _, wo_id = _setup_org_with_work_order(client, db_session, "del-6")
        _delete(client, auth, wo_id)
        list_resp = client.get("/api/v1/work-orders", headers=auth)
        assert list_resp.status_code == 200
        assert wo_id not in [w["id"] for w in list_resp.json()]

    def test_deleted_work_order_not_retrievable_through_normal_get(self, client, db_session):
        _, auth, _, wo_id = _setup_org_with_work_order(client, db_session, "del-7")
        _delete(client, auth, wo_id)
        get_resp = client.get(f"/api/v1/work-orders/{wo_id}", headers=auth)
        assert get_resp.status_code == 404

    def test_double_delete_returns_409(self, client, db_session):
        _, auth, _, wo_id = _setup_org_with_work_order(client, db_session, "del-8")
        first = _delete(client, auth, wo_id)
        assert first.status_code == 204
        second = _delete(client, auth, wo_id)
        assert second.status_code == 409

    def test_cross_tenant_delete_returns_404(self, client, db_session):
        _, _auth_a, _, wo_id = _setup_org_with_work_order(client, db_session, "del-9a")
        tokens_b = _register(client, "WO Lifecycle del-9b", "admin@wo-lc-del-9b.example.com")
        auth_b = _auth(tokens_b["access_token"])
        me_b = client.get("/api/v1/auth/me", headers=auth_b).json()
        org_b_id = uuid.UUID(me_b["organization_id"])
        _entitle_work_orders(db_session, org_b_id)

        resp = _delete(client, auth_b, wo_id)
        assert resp.status_code == 404

    def test_user_without_delete_permission_gets_403(self, client, db_session):
        org_id, _admin_auth, _, wo_id = _setup_org_with_work_order(client, db_session, "del-10")
        viewer_auth = _login_as_role(
            client, db_session, org_id, "VIEWER", "viewer@wo-lc-del-10.example.com"
        )
        resp = _delete(client, viewer_auth, wo_id)
        assert resp.status_code == 403

    def test_delete_reason_code_validation_rejects_unknown_code(self, client, db_session):
        _, auth, _, wo_id = _setup_org_with_work_order(client, db_session, "del-11")
        resp = _delete(client, auth, wo_id, reason_code="NOT_A_REAL_REASON")
        assert resp.status_code == 422

    def test_delete_note_is_persisted_in_audit_metadata(self, client, db_session):
        _, auth, _, wo_id = _setup_org_with_work_order(client, db_session, "del-12")
        _delete(client, auth, wo_id, reason_code="DUPLICATE_WORK_ORDER", note="dup of WO-1")
        events = _audit_events(db_session, uuid.UUID(wo_id), "work_order.deleted")
        assert len(events) == 1
        assert events[0].event_metadata["note"] == "dup of WO-1"
        assert events[0].event_metadata["reason_code"] == "DUPLICATE_WORK_ORDER"
        assert events[0].event_metadata["lifecycle_transition"] == "ACTIVE->DELETED"


class TestRestore:
    def test_authorized_tenant_can_restore_deleted_work_order(self, client, db_session):
        _, auth, _, wo_id = _setup_org_with_work_order(client, db_session, "res-1")
        _delete(client, auth, wo_id)
        resp = _restore(client, auth, wo_id, reason_code="DELETED_IN_ERROR")
        assert resp.status_code == 200, resp.text

    def test_restore_clears_deleted_at_and_deleted_by(self, client, db_session):
        _, auth, _, wo_id = _setup_org_with_work_order(client, db_session, "res-2")
        _delete(client, auth, wo_id)
        _restore(client, auth, wo_id)
        db_session.expire_all()
        row = db_session.get(WorkOrder, uuid.UUID(wo_id))
        assert row.deleted_at is None
        assert row.deleted_by is None

    def test_restore_sets_restored_at_and_restored_by(self, client, db_session):
        org_id, auth, _, wo_id = _setup_org_with_work_order(client, db_session, "res-3")
        me = client.get("/api/v1/auth/me", headers=auth).json()
        _delete(client, auth, wo_id)
        _restore(client, auth, wo_id)
        db_session.expire_all()
        row = db_session.get(WorkOrder, uuid.UUID(wo_id))
        assert row.restored_at is not None
        assert str(row.restored_by) == me["id"]

    def test_restore_does_not_modify_business_status(self, client, db_session):
        _, auth, _, wo_id = _setup_org_with_work_order(client, db_session, "res-4", status="CLOSED")
        _delete(client, auth, wo_id)
        _restore(client, auth, wo_id)
        db_session.expire_all()
        row = db_session.get(WorkOrder, uuid.UUID(wo_id))
        assert row.status == "CLOSED"

    def test_restore_creates_exactly_one_audit_event(self, client, db_session):
        _, auth, _, wo_id = _setup_org_with_work_order(client, db_session, "res-5")
        _delete(client, auth, wo_id)
        _restore(client, auth, wo_id)
        events = _audit_events(db_session, uuid.UUID(wo_id), "work_order.restored")
        assert len(events) == 1

    def test_double_restore_returns_409(self, client, db_session):
        _, auth, _, wo_id = _setup_org_with_work_order(client, db_session, "res-6")
        _delete(client, auth, wo_id)
        first = _restore(client, auth, wo_id)
        assert first.status_code == 200
        second = _restore(client, auth, wo_id)
        assert second.status_code == 409

    def test_restore_on_never_deleted_work_order_returns_409(self, client, db_session):
        _, auth, _, wo_id = _setup_org_with_work_order(client, db_session, "res-7")
        resp = _restore(client, auth, wo_id)
        assert resp.status_code == 409

    def test_cross_tenant_restore_returns_404(self, client, db_session):
        _, auth_a, _, wo_id = _setup_org_with_work_order(client, db_session, "res-8a")
        _delete(client, auth_a, wo_id)

        tokens_b = _register(client, "WO Lifecycle res-8b", "admin@wo-lc-res-8b.example.com")
        auth_b = _auth(tokens_b["access_token"])
        me_b = client.get("/api/v1/auth/me", headers=auth_b).json()
        org_b_id = uuid.UUID(me_b["organization_id"])
        _entitle_work_orders(db_session, org_b_id)

        resp = _restore(client, auth_b, wo_id)
        assert resp.status_code == 404

    def test_user_without_restore_permission_gets_403(self, client, db_session):
        org_id, admin_auth, _, wo_id = _setup_org_with_work_order(client, db_session, "res-9")
        _delete(client, admin_auth, wo_id)
        viewer_auth = _login_as_role(
            client, db_session, org_id, "VIEWER", "viewer@wo-lc-res-9.example.com"
        )
        resp = _restore(client, viewer_auth, wo_id)
        assert resp.status_code == 403

    def test_restore_reason_code_validation_rejects_unknown_code(self, client, db_session):
        _, auth, _, wo_id = _setup_org_with_work_order(client, db_session, "res-10")
        _delete(client, auth, wo_id)
        resp = _restore(client, auth, wo_id, reason_code="NOT_A_REAL_REASON")
        assert resp.status_code == 422

    def test_restore_note_is_persisted_in_audit_metadata(self, client, db_session):
        _, auth, _, wo_id = _setup_org_with_work_order(client, db_session, "res-11")
        _delete(client, auth, wo_id)
        _restore(client, auth, wo_id, reason_code="OPERATIONAL_REQUIREMENT", note="needed back")
        events = _audit_events(db_session, uuid.UUID(wo_id), "work_order.restored")
        assert len(events) == 1
        assert events[0].event_metadata["note"] == "needed back"
        assert events[0].event_metadata["reason_code"] == "OPERATIONAL_REQUIREMENT"
        assert events[0].event_metadata["lifecycle_transition"] == "DELETED->ACTIVE"


class TestLifecycleCycles:
    def test_delete_then_restore_preserves_original_status(self, client, db_session):
        _, auth, _, wo_id = _setup_org_with_work_order(client, db_session, "cyc-1", status="OPEN")
        _delete(client, auth, wo_id)
        restore_resp = _restore(client, auth, wo_id)
        assert restore_resp.json()["status"] == "OPEN"

        get_resp = client.get(f"/api/v1/work-orders/{wo_id}", headers=auth)
        assert get_resp.status_code == 200
        assert get_resp.json()["status"] == "OPEN"

    def test_second_delete_restore_cycle_updates_actor_and_timestamps(self, client, db_session):
        _, auth, _, wo_id = _setup_org_with_work_order(client, db_session, "cyc-2")

        _delete(client, auth, wo_id, reason_code="CREATED_IN_ERROR")
        _restore(client, auth, wo_id, reason_code="DELETED_IN_ERROR")
        db_session.expire_all()
        first_restored_at = db_session.get(WorkOrder, uuid.UUID(wo_id)).restored_at

        second_delete = _delete(client, auth, wo_id, reason_code="ADMINISTRATIVE_CORRECTION")
        assert second_delete.status_code == 204
        db_session.expire_all()
        row = db_session.get(WorkOrder, uuid.UUID(wo_id))
        assert row.deleted_at is not None
        assert row.deleted_by is not None
        # Second cycle's delete does not retroactively touch the first
        # cycle's restored_at -- only a subsequent restore would.
        assert row.restored_at == first_restored_at

        delete_events = _audit_events(db_session, uuid.UUID(wo_id), "work_order.deleted")
        restore_events = _audit_events(db_session, uuid.UUID(wo_id), "work_order.restored")
        assert len(delete_events) == 2
        assert len(restore_events) == 1
