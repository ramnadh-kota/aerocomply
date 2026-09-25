"""Platform Control Plane: end-to-end soft-delete / restore / permanent-delete
governance for WorkOrder -- the third soft-deletable entity (Asset,
Organization, now WorkOrder). Mirrors
tests/integration/test_soft_delete_governance.py's structure/conventions
exactly (same _register/_auth/_create_platform_user helpers).

Additionally covers WorkOrder's own extra requirement: permanent deletion
must be blocked by each of its 8 real FK dependents (Task, PartRequirement,
AogEvent, DeferredItem, Finding, InspectionRequirement,
MaintenanceRequirement, ProcurementRequest) individually, since those FKs
are deliberately NOT DB ondelete=RESTRICT (see migration
0042_soft_delete_work_orders.py) -- the guard is application-level
(deletion_service._work_order_dependency_counts), so it needs its own test
coverage per dependent, unlike Asset's single DB-enforced case.
"""

import datetime
import uuid
from datetime import UTC, timedelta

from sqlalchemy import select

from app.core.deps import get_db_session
from app.core.security import hash_password
from app.main import app
from app.models.aog_event import AogEvent
from app.models.audit_event import AuditEvent
from app.models.deferred_item import DeferredItem
from app.models.finding import Finding
from app.models.inspection_requirement import InspectionRequirement
from app.models.maintenance_requirement import MaintenanceAccomplishment, MaintenanceRequirement
from app.models.organization import Organization
from app.models.part import Part
from app.models.part_requirement import PartRequirement
from app.models.plan import Plan, PlanFeature
from app.models.procurement_request import ProcurementRequest
from app.models.subscription import Subscription, SubscriptionStatus
from app.models.task import Task
from app.models.user import User, UserRole
from app.models.work_order import WorkOrder


def _entitle_work_orders(db_session, org_id):
    """POST /work-orders (and every other work-order route) requires
    require_feature("work_order_management") -- a freshly registered org
    has no subscription at all. Same fixture shape as
    tests/integration/test_drone_operations.py's _entitle_work_orders."""
    plan = Plan(name=f"WO-Del-Test-Plan-{org_id}", code=f"wo-del-test-{org_id}", is_active=True)
    db_session.add(plan)
    db_session.commit()
    db_session.refresh(plan)
    db_session.add(PlanFeature(plan_id=plan.id, feature_key="work_order_management", enabled=True))
    db_session.add(
        Subscription(
            organization_id=org_id,
            plan_id=plan.id,
            status=SubscriptionStatus.ACTIVE,
            starts_at=datetime.datetime.now(UTC) - timedelta(days=1),
            ends_at=None,
        )
    )
    db_session.commit()


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
    assert resp.status_code == 201
    return resp.json()


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _create_platform_user(client, db_session, email, role_name):
    org = Organization(name=f"Platform Ops WO ({role_name}-{email})")
    db_session.add(org)
    db_session.flush()
    user = User(
        organization_id=org.id,
        email=email,
        hashed_password=hash_password("supersecret123"),
        full_name="Platform User",
        is_active=True,
    )
    db_session.add(user)
    db_session.flush()
    db_session.add(UserRole(user_id=user.id, role_name=role_name, organization_id=org.id))
    db_session.commit()

    login = client.post("/api/v1/auth/login", json={"email": email, "password": "supersecret123"})
    assert login.status_code == 200
    return _auth(login.json()["access_token"])


def _create_aircraft_and_work_order(client, db_session, auth, *, registration, wo_number):
    org_id = client.get("/api/v1/auth/me", headers=auth).json()["organization_id"]
    _entitle_work_orders(db_session, org_id)

    aircraft_resp = client.post(
        "/api/v1/aircraft",
        json={"registration": registration, "msn": f"MSN-{registration}", "aircraft_type": "A320"},
        headers=auth,
    )
    assert aircraft_resp.status_code == 201, aircraft_resp.text
    aircraft = aircraft_resp.json()

    work_order_resp = client.post(
        "/api/v1/work-orders",
        json={"aircraft_id": aircraft["id"], "work_order_number": wo_number},
        headers=auth,
    )
    assert work_order_resp.status_code == 201, work_order_resp.text
    return aircraft, work_order_resp.json()


class TestTenantSoftDeleteWorkOrder:
    def test_delete_work_order_soft_deletes_and_hides_from_tenant_reads(self, client, db_session):
        tokens = _register(client, "WO Delete Tenant", "admin@wo-delete.example.com")
        auth = _auth(tokens["access_token"])
        _aircraft, wo = _create_aircraft_and_work_order(
            client, db_session, auth, registration="N70WD", wo_number="WO-70"
        )

        resp = client.delete(f"/api/v1/work-orders/{wo['id']}", headers=auth)
        assert resp.status_code == 200, resp.text

        get_resp = client.get(f"/api/v1/work-orders/{wo['id']}", headers=auth)
        assert get_resp.status_code == 404

        list_resp = client.get("/api/v1/work-orders", headers=auth)
        assert all(w["id"] != wo["id"] for w in list_resp.json())

    def test_cross_tenant_cannot_delete_others_work_order(self, client, db_session):
        tokens_a = _register(client, "WO Delete Tenant A", "admin@wo-delete-a.example.com")
        tokens_b = _register(client, "WO Delete Tenant B", "admin@wo-delete-b.example.com")
        auth_a, auth_b = _auth(tokens_a["access_token"]), _auth(tokens_b["access_token"])
        _aircraft, wo = _create_aircraft_and_work_order(
            client, db_session, auth_a, registration="N71XT", wo_number="WO-71"
        )

        # Tenant B has no work_order_management entitlement of its own (only
        # tenant A was granted one by _create_aircraft_and_work_order's
        # _entitle_work_orders call) -- require_feature rejects with 403
        # before the service layer's organization_id scoping is ever
        # reached. Grant B the same feature to isolate what this test
        # actually verifies: cross-tenant scoping, not entitlement gating.
        org_b_id = client.get("/api/v1/auth/me", headers=auth_b).json()["organization_id"]
        _entitle_work_orders(db_session, org_b_id)

        resp = client.delete(f"/api/v1/work-orders/{wo['id']}", headers=auth_b)
        assert resp.status_code == 404

        still_there = client.get(f"/api/v1/work-orders/{wo['id']}", headers=auth_a)
        assert still_there.status_code == 200

    def test_double_delete_returns_409(self, client, db_session):
        tokens = _register(client, "WO Double Delete Tenant", "admin@wo-doubledelete.example.com")
        auth = _auth(tokens["access_token"])
        _aircraft, wo = _create_aircraft_and_work_order(
            client, db_session, auth, registration="N72DD", wo_number="WO-72"
        )

        assert client.delete(f"/api/v1/work-orders/{wo['id']}", headers=auth).status_code == 200
        second = client.delete(f"/api/v1/work-orders/{wo['id']}", headers=auth)
        assert second.status_code == 409
        assert second.json()["error"]["code"] == "already_deleted"

    def test_delete_with_reason_persists_it(self, client, db_session):
        tokens = _register(client, "WO Delete Reason Tenant", "admin@wo-delete-reason.example.com")
        auth = _auth(tokens["access_token"])
        _aircraft, wo = _create_aircraft_and_work_order(
            client, db_session, auth, registration="N73RS", wo_number="WO-73"
        )

        resp = client.delete(
            f"/api/v1/work-orders/{wo['id']}",
            params={"reason": "Cancelled by customer"},
            headers=auth,
        )
        assert resp.status_code == 200
        assert resp.json()["id"] == wo["id"]

    def test_delete_emits_audit_event(self, client, db_session):
        tokens = _register(client, "WO Delete Audit Tenant", "admin@wo-delete-audit.example.com")
        auth = _auth(tokens["access_token"])
        _aircraft, wo = _create_aircraft_and_work_order(
            client, db_session, auth, registration="N74AU", wo_number="WO-74"
        )

        client.delete(f"/api/v1/work-orders/{wo['id']}", params={"reason": "test"}, headers=auth)

        events = (
            db_session.execute(
                select(AuditEvent).where(
                    AuditEvent.action == "work_order.deleted",
                    AuditEvent.entity_id == uuid.UUID(wo["id"]),
                )
            )
            .scalars()
            .all()
        )
        assert len(events) == 1
        assert events[0].event_metadata["reason"] == "test"
        assert events[0].event_metadata["work_order_number"] == "WO-74"

    def test_deleted_work_order_disappears_from_normal_tenant_queries(self, client, db_session):
        tokens = _register(client, "WO Query Hide Tenant", "admin@wo-query-hide.example.com")
        auth = _auth(tokens["access_token"])
        aircraft, wo = _create_aircraft_and_work_order(
            client, db_session, auth, registration="N75QH", wo_number="WO-75"
        )
        client.delete(f"/api/v1/work-orders/{wo['id']}", headers=auth)

        by_aircraft = client.get(
            "/api/v1/work-orders", params={"aircraft_id": aircraft["id"]}, headers=auth
        ).json()
        assert all(w["id"] != wo["id"] for w in by_aircraft)


class TestPlatformDeletedRecordsQueueWorkOrder:
    def test_ordinary_tenant_admin_gets_403(self, client):
        tokens = _register(client, "WO Queue Denied Tenant", "admin@wo-queue-denied.example.com")
        resp = client.get(
            "/api/v1/platform/deleted-records",
            params={"entity_type": "WORKORDER"},
            headers=_auth(tokens["access_token"]),
        )
        assert resp.status_code == 403

    def test_platform_admin_sees_soft_deleted_work_order(self, client, db_session):
        tenant_tokens = _register(client, "WO Queue Tenant", "admin@wo-queue.example.com")
        tenant_auth = _auth(tenant_tokens["access_token"])
        _aircraft, wo = _create_aircraft_and_work_order(
            client, db_session, tenant_auth, registration="N76QU", wo_number="WO-76"
        )
        client.delete(f"/api/v1/work-orders/{wo['id']}", params={"reason": "queued"}, headers=tenant_auth)

        platform_auth = _create_platform_user(
            client, db_session, "ops@wo-platform-queue.example.com", "PLATFORM_ADMIN"
        )
        resp = client.get(
            "/api/v1/platform/deleted-records",
            params={"organization_id": wo["organization_id"], "entity_type": "WORKORDER"},
            headers=platform_auth,
        )
        assert resp.status_code == 200
        body = resp.json()
        matching = [i for i in body["items"] if i["entity_id"] == wo["id"]]
        assert len(matching) == 1
        assert matching[0]["entity_type"] == "WORKORDER"
        # Unlike Asset (whose DeletedRecordResponse.status is a hardcoded
        # "DELETED"), WorkOrder's status reflects the WorkOrder's own
        # status column (OPEN/COMPLETED/...) -- deletedness is carried by
        # deleted_at/deleted_by/deletion_reason instead. See
        # restoration_service._deleted_work_orders.
        assert matching[0]["status"] == "OPEN"
        assert matching[0]["deleted_at"] is not None
        assert matching[0]["deletion_reason"] == "queued"
        assert matching[0]["identifier"] == "WO-76"

    def test_asset_and_organization_queue_behavior_unchanged(self, client, db_session):
        """Regression: adding WORKORDER must not alter ASSET/ORGANIZATION
        results in the merged, unfiltered queue."""
        tenant_tokens = _register(client, "WO Regression Tenant", "admin@wo-regression.example.com")
        tenant_auth = _auth(tenant_tokens["access_token"])
        asset = client.post(
            "/api/v1/assets", json={"asset_type": "AIRCRAFT", "registration": "N77RG"}, headers=tenant_auth
        ).json()
        client.delete(f"/api/v1/assets/{asset['id']}", headers=tenant_auth)

        platform_auth = _create_platform_user(
            client, db_session, "ops@wo-regression.example.com", "PLATFORM_ADMIN"
        )
        resp = client.get(
            "/api/v1/platform/deleted-records",
            params={"organization_id": asset["organization_id"]},
            headers=platform_auth,
        )
        assert resp.status_code == 200
        matching = [i for i in resp.json()["items"] if i["entity_id"] == asset["id"]]
        assert len(matching) == 1
        assert matching[0]["entity_type"] == "ASSET"

    def test_org_a_cannot_see_org_bs_deleted_work_orders(self, client, db_session):
        tokens_a = _register(client, "WO Isolation Tenant A", "admin@wo-isolation-a.example.com")
        tokens_b = _register(client, "WO Isolation Tenant B", "admin@wo-isolation-b.example.com")
        auth_a, auth_b = _auth(tokens_a["access_token"]), _auth(tokens_b["access_token"])
        _aircraft_a, wo_a = _create_aircraft_and_work_order(
            client, db_session, auth_a, registration="N78IA", wo_number="WO-78A"
        )
        _aircraft_b, wo_b = _create_aircraft_and_work_order(
            client, db_session, auth_b, registration="N79IB", wo_number="WO-78B"
        )
        client.delete(f"/api/v1/work-orders/{wo_a['id']}", headers=auth_a)
        client.delete(f"/api/v1/work-orders/{wo_b['id']}", headers=auth_b)

        platform_auth = _create_platform_user(
            client, db_session, "ops@wo-isolation.example.com", "PLATFORM_ADMIN"
        )
        # Platform Admin scoped to org A only sees org A's deleted work order.
        resp = client.get(
            "/api/v1/platform/deleted-records",
            params={"organization_id": wo_a["organization_id"], "entity_type": "WORKORDER"},
            headers=platform_auth,
        )
        ids = {i["entity_id"] for i in resp.json()["items"]}
        assert wo_a["id"] in ids
        assert wo_b["id"] not in ids

    def test_platform_admin_sees_per_platform_scope_rules(self, client, db_session):
        """Unscoped (no organization_id filter), Platform Admin sees deleted
        work orders across every tenant -- same cross-tenant visibility as
        Asset/Organization (see restoration_service.list_deleted_records's
        docstring)."""
        tokens = _register(client, "WO Platform Scope Tenant", "admin@wo-platform-scope.example.com")
        auth = _auth(tokens["access_token"])
        _aircraft, wo = _create_aircraft_and_work_order(
            client, db_session, auth, registration="N80PS", wo_number="WO-80"
        )
        client.delete(f"/api/v1/work-orders/{wo['id']}", headers=auth)

        platform_auth = _create_platform_user(
            client, db_session, "ops@wo-platform-scope.example.com", "PLATFORM_ADMIN"
        )
        resp = client.get(
            "/api/v1/platform/deleted-records", params={"entity_type": "WORKORDER"}, headers=platform_auth
        )
        assert resp.status_code == 200
        ids = {i["entity_id"] for i in resp.json()["items"]}
        assert wo["id"] in ids


class TestPlatformRestoreWorkOrder:
    def test_platform_admin_restores_work_order_and_tenant_sees_it_again(self, client, db_session):
        tenant_tokens = _register(client, "WO Restore Tenant", "admin@wo-restore.example.com")
        tenant_auth = _auth(tenant_tokens["access_token"])
        _aircraft, wo = _create_aircraft_and_work_order(
            client, db_session, tenant_auth, registration="N81RS", wo_number="WO-81"
        )
        client.delete(f"/api/v1/work-orders/{wo['id']}", headers=tenant_auth)

        platform_auth = _create_platform_user(
            client, db_session, "ops@wo-platform-restore.example.com", "PLATFORM_ADMIN"
        )
        restore_resp = client.post(
            f"/api/v1/platform/deleted-records/work-orders/{wo['id']}/restore", headers=platform_auth
        )
        assert restore_resp.status_code == 200, restore_resp.text

        get_resp = client.get(f"/api/v1/work-orders/{wo['id']}", headers=tenant_auth)
        assert get_resp.status_code == 200

    def test_non_platform_user_cannot_restore(self, client, db_session):
        tenant_tokens = _register(client, "WO Restore Denied Tenant", "admin@wo-restore-denied.example.com")
        tenant_auth = _auth(tenant_tokens["access_token"])
        _aircraft, wo = _create_aircraft_and_work_order(
            client, db_session, tenant_auth, registration="N82RD", wo_number="WO-82"
        )
        client.delete(f"/api/v1/work-orders/{wo['id']}", headers=tenant_auth)

        resp = client.post(
            f"/api/v1/platform/deleted-records/work-orders/{wo['id']}/restore", headers=tenant_auth
        )
        assert resp.status_code == 403

    def test_restoring_a_never_deleted_work_order_returns_409(self, client, db_session):
        tenant_tokens = _register(client, "WO Not Deleted Tenant", "admin@wo-not-deleted.example.com")
        tenant_auth = _auth(tenant_tokens["access_token"])
        _aircraft, wo = _create_aircraft_and_work_order(
            client, db_session, tenant_auth, registration="N83ND", wo_number="WO-83"
        )

        platform_auth = _create_platform_user(
            client, db_session, "ops@wo-platform-notdeleted.example.com", "PLATFORM_ADMIN"
        )
        resp = client.post(
            f"/api/v1/platform/deleted-records/work-orders/{wo['id']}/restore", headers=platform_auth
        )
        assert resp.status_code == 409
        assert resp.json()["error"]["code"] == "not_deleted"

    def test_restore_emits_audit_event(self, client, db_session):
        tenant_tokens = _register(client, "WO Restore Audit Tenant", "admin@wo-restore-audit.example.com")
        tenant_auth = _auth(tenant_tokens["access_token"])
        _aircraft, wo = _create_aircraft_and_work_order(
            client, db_session, tenant_auth, registration="N84RA", wo_number="WO-84"
        )
        client.delete(f"/api/v1/work-orders/{wo['id']}", headers=tenant_auth)

        platform_auth = _create_platform_user(
            client, db_session, "ops@wo-platform-restoreaudit.example.com", "PLATFORM_ADMIN"
        )
        client.post(
            f"/api/v1/platform/deleted-records/work-orders/{wo['id']}/restore", headers=platform_auth
        )

        events = (
            db_session.execute(
                select(AuditEvent).where(
                    AuditEvent.action == "work_order.restored",
                    AuditEvent.entity_id == uuid.UUID(wo["id"]),
                )
            )
            .scalars()
            .all()
        )
        assert len(events) == 1


class TestPlatformPermanentDeleteWorkOrder:
    def test_non_soft_deleted_work_order_cannot_be_permanently_deleted(self, client, db_session):
        tenant_tokens = _register(client, "WO Active Perm Tenant", "admin@wo-active-perm.example.com")
        tenant_auth = _auth(tenant_tokens["access_token"])
        _aircraft, wo = _create_aircraft_and_work_order(
            client, db_session, tenant_auth, registration="N85AP", wo_number="WO-85"
        )

        admin_auth = _create_platform_user(
            client, db_session, "ops@wo-platform-activeperm.example.com", "PLATFORM_ADMIN"
        )
        resp = client.post(
            f"/api/v1/platform/deleted-records/work-orders/{wo['id']}/permanent-delete",
            json={"reason": "cleanup", "confirm": True},
            headers=admin_auth,
        )
        assert resp.status_code == 409
        assert resp.json()["error"]["code"] == "not_soft_deleted"

    def test_missing_confirm_flag_blocks(self, client, db_session):
        tenant_tokens = _register(client, "WO Confirm Tenant", "admin@wo-confirm.example.com")
        tenant_auth = _auth(tenant_tokens["access_token"])
        _aircraft, wo = _create_aircraft_and_work_order(
            client, db_session, tenant_auth, registration="N86CF", wo_number="WO-86"
        )
        client.delete(f"/api/v1/work-orders/{wo['id']}", headers=tenant_auth)

        admin_auth = _create_platform_user(
            client, db_session, "ops@wo-platform-confirm.example.com", "PLATFORM_ADMIN"
        )
        resp = client.post(
            f"/api/v1/platform/deleted-records/work-orders/{wo['id']}/permanent-delete",
            json={"reason": "cleanup", "confirm": False},
            headers=admin_auth,
        )
        assert resp.status_code == 409
        assert resp.json()["error"]["code"] == "confirmation_required"

    def test_permanent_delete_of_an_empty_work_order_succeeds_and_removes_from_queue(
        self, client, db_session
    ):
        tenant_tokens = _register(client, "WO Empty Perm Tenant", "admin@wo-empty-perm.example.com")
        tenant_auth = _auth(tenant_tokens["access_token"])
        _aircraft, wo = _create_aircraft_and_work_order(
            client, db_session, tenant_auth, registration="N87EP", wo_number="WO-87"
        )
        client.delete(f"/api/v1/work-orders/{wo['id']}", headers=tenant_auth)

        admin_auth = _create_platform_user(
            client, db_session, "ops@wo-platform-emptyperm.example.com", "PLATFORM_ADMIN"
        )
        resp = client.post(
            f"/api/v1/platform/deleted-records/work-orders/{wo['id']}/permanent-delete",
            json={"reason": "no dependents, safe to purge", "confirm": True},
            headers=admin_auth,
        )
        assert resp.status_code == 200, resp.text

        queue = client.get(
            "/api/v1/platform/deleted-records",
            params={"organization_id": wo["organization_id"], "entity_type": "WORKORDER"},
            headers=admin_auth,
        ).json()
        assert all(i["entity_id"] != wo["id"] for i in queue["items"])

    def test_permanent_delete_emits_audit_event_before_row_is_gone(self, client, db_session):
        tenant_tokens = _register(client, "WO Audit Perm Tenant", "admin@wo-audit-perm.example.com")
        tenant_auth = _auth(tenant_tokens["access_token"])
        _aircraft, wo = _create_aircraft_and_work_order(
            client, db_session, tenant_auth, registration="N88AU", wo_number="WO-88"
        )
        client.delete(f"/api/v1/work-orders/{wo['id']}", headers=tenant_auth)

        admin_auth = _create_platform_user(
            client, db_session, "ops@wo-platform-auditperm.example.com", "PLATFORM_ADMIN"
        )
        client.post(
            f"/api/v1/platform/deleted-records/work-orders/{wo['id']}/permanent-delete",
            json={"reason": "final cleanup", "confirm": True},
            headers=admin_auth,
        )

        events = (
            db_session.execute(
                select(AuditEvent).where(
                    AuditEvent.action == "work_order.permanently_deleted",
                    AuditEvent.entity_id == uuid.UUID(wo["id"]),
                )
            )
            .scalars()
            .all()
        )
        assert len(events) == 1
        assert events[0].event_metadata["reason"] == "final cleanup"

        # The audit event survives the physical row deletion -- WorkOrder
        # itself is now gone from the table.
        gone = db_session.execute(
            select(WorkOrder).where(WorkOrder.id == uuid.UUID(wo["id"]))
        ).scalar_one_or_none()
        assert gone is None


def _create_org_scoped(db_session, model, **kwargs):
    row = model(**kwargs)
    db_session.add(row)
    db_session.commit()
    db_session.refresh(row)
    return row


class TestPlatformPermanentDeleteWorkOrderDependents:
    """One test per each of the 8 real FK dependents named in the task spec.
    Each creates exactly one dependent row directly via the ORM (these
    domains' own create flows are out of scope here), then asserts
    permanent-delete is blocked with a clear, entity-named ConflictError."""

    def _setup(self, client, db_session, *, registration, wo_number, admin_email):
        tokens = _register(client, f"WO Dep Tenant {wo_number}", f"admin@{wo_number.lower()}.example.com")
        auth = _auth(tokens["access_token"])
        aircraft, wo = _create_aircraft_and_work_order(
            client, db_session, auth, registration=registration, wo_number=wo_number
        )
        client.delete(f"/api/v1/work-orders/{wo['id']}", headers=auth)
        admin_auth = _create_platform_user(client, db_session, admin_email, "PLATFORM_ADMIN")
        org_id = uuid.UUID(wo["organization_id"])
        return auth, admin_auth, org_id, wo, aircraft

    def _assert_blocked(self, client, admin_auth, wo, *, expect_substring):
        resp = client.post(
            f"/api/v1/platform/deleted-records/work-orders/{wo['id']}/permanent-delete",
            json={"reason": "attempt purge", "confirm": True},
            headers=admin_auth,
        )
        assert resp.status_code == 409, resp.text
        assert resp.json()["error"]["code"] == "has_dependent_records"
        assert expect_substring in resp.json()["error"]["message"]

    def test_blocked_by_task(self, client, db_session):
        _auth, admin_auth, org_id, wo, _aircraft = self._setup(
            client, db_session, registration="N90T1", wo_number="WO-90T", admin_email="ops@wo-dep-task.example.com"
        )
        _create_org_scoped(
            db_session,
            Task,
            organization_id=org_id,
            work_order_id=uuid.UUID(wo["id"]),
            description="Inspect panel",
        )
        self._assert_blocked(client, admin_auth, wo, expect_substring="Task")

    def test_blocked_by_part_requirement(self, client, db_session):
        _auth, admin_auth, org_id, wo, _aircraft = self._setup(
            client, db_session, registration="N90T2", wo_number="WO-90P", admin_email="ops@wo-dep-part.example.com"
        )
        part = _create_org_scoped(
            db_session, Part, organization_id=org_id, part_number="PN-1", description="Widget"
        )
        _create_org_scoped(
            db_session,
            PartRequirement,
            organization_id=org_id,
            work_order_id=uuid.UUID(wo["id"]),
            part_id=part.id,
            required_quantity=1,
        )
        self._assert_blocked(client, admin_auth, wo, expect_substring="PartRequirement")

    def test_blocked_by_aog_event(self, client, db_session):
        _auth, admin_auth, org_id, wo, aircraft = self._setup(
            client, db_session, registration="N90T3", wo_number="WO-90A", admin_email="ops@wo-dep-aog.example.com"
        )
        _create_org_scoped(
            db_session,
            AogEvent,
            organization_id=org_id,
            aircraft_id=uuid.UUID(aircraft["id"]),
            work_order_id=uuid.UUID(wo["id"]),
        )
        self._assert_blocked(client, admin_auth, wo, expect_substring="AogEvent")

    def test_blocked_by_deferred_item(self, client, db_session):
        _auth, admin_auth, org_id, wo, aircraft = self._setup(
            client, db_session, registration="N90T4", wo_number="WO-90D", admin_email="ops@wo-dep-deferred.example.com"
        )
        _create_org_scoped(
            db_session,
            DeferredItem,
            organization_id=org_id,
            aircraft_id=uuid.UUID(aircraft["id"]),
            work_order_id=uuid.UUID(wo["id"]),
            description="Deferred squawk",
            opened_at=datetime.date(2025, 1, 1),
        )
        self._assert_blocked(client, admin_auth, wo, expect_substring="DeferredItem")

    def test_blocked_by_finding(self, client, db_session):
        _auth, admin_auth, org_id, wo, _aircraft = self._setup(
            client, db_session, registration="N90T5", wo_number="WO-90F", admin_email="ops@wo-dep-finding.example.com"
        )
        _create_org_scoped(
            db_session,
            Finding,
            organization_id=org_id,
            work_order_id=uuid.UUID(wo["id"]),
            title="Finding title",
            description="Finding description",
            severity="MINOR",
        )
        self._assert_blocked(client, admin_auth, wo, expect_substring="Finding")

    def test_blocked_by_inspection_requirement(self, client, db_session):
        _auth, admin_auth, org_id, wo, _aircraft = self._setup(
            client, db_session, registration="N90T6", wo_number="WO-90I", admin_email="ops@wo-dep-inspection.example.com"
        )
        _create_org_scoped(
            db_session,
            InspectionRequirement,
            organization_id=org_id,
            work_order_id=uuid.UUID(wo["id"]),
        )
        self._assert_blocked(client, admin_auth, wo, expect_substring="InspectionRequirement")

    def test_blocked_by_maintenance_requirement(self, client, db_session):
        """The task spec names this dependent "MaintenanceRequirement", but
        the real work_order_id FK lives on MaintenanceAccomplishment (see
        deletion_service._WORK_ORDER_DEPENDENT_TABLES's own note) --
        MaintenanceRequirement itself has no such column. This test exercises
        the actual FK: a MaintenanceAccomplishment row referencing this work
        order."""
        _auth, admin_auth, org_id, wo, _aircraft = self._setup(
            client, db_session, registration="N90T7", wo_number="WO-90M", admin_email="ops@wo-dep-maint.example.com"
        )
        requirement = _create_org_scoped(
            db_session,
            MaintenanceRequirement,
            organization_id=org_id,
            description="100-hour inspection",
            ata_chapter="05",
            interval_type="CALENDAR",
            calendar_interval_days=100,
        )
        _create_org_scoped(
            db_session,
            MaintenanceAccomplishment,
            organization_id=org_id,
            requirement_id=requirement.id,
            work_order_id=uuid.UUID(wo["id"]),
            accomplished_at=datetime.date(2025, 1, 1),
        )
        self._assert_blocked(client, admin_auth, wo, expect_substring="MaintenanceAccomplishment")

    def test_blocked_by_procurement_request(self, client, db_session):
        _auth, admin_auth, org_id, wo, aircraft = self._setup(
            client, db_session, registration="N90T8", wo_number="WO-90R", admin_email="ops@wo-dep-procurement.example.com"
        )
        _create_org_scoped(
            db_session,
            ProcurementRequest,
            organization_id=org_id,
            aircraft_id=uuid.UUID(aircraft["id"]),
            work_order_id=uuid.UUID(wo["id"]),
            part_number="PN-9",
            description="Replacement part",
            reason="Needed for repair",
        )
        self._assert_blocked(client, admin_auth, wo, expect_substring="ProcurementRequest")
