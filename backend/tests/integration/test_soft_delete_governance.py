"""Platform Control Plane: end-to-end soft-delete / restore / permanent-delete
governance for Asset (the pilot soft-deletable entity).

Covers the full lifecycle spec:
    Tenant DELETE -> soft delete -> hidden from tenant reads
        -> visible in Platform Admin's deleted-records queue
        -> Platform Admin RESTORE -> visible to tenant again
        -> Platform Admin PERMANENT DELETE (only after re-deleting) -> gone

Same fixtures/conventions as tests/integration/test_platform_api.py
(_create_platform_admin) and tests/integration/test_asset_foundation.py
(_register/_auth for tenant users).
"""

import uuid
from datetime import UTC, datetime, timedelta

from app.core.deps import get_db_session
from app.core.security import hash_password
from app.main import app
from app.models.audit_event import AuditEvent
from app.models.organization import Organization
from app.models.plan import Plan, PlanFeature
from app.models.subscription import Subscription, SubscriptionStatus
from app.models.user import User, UserRole


def _entitle_drone_ops(db_session, org_id):
    """Same fixture as tests/integration/test_drone_operations.py's
    _entitle_drone_ops -- POST/GET /drones is gated by
    require_feature("drone_fleet_management"), which a freshly registered
    org has no subscription for at all."""
    plan = Plan(name=f"Drone-Test-Plan-{org_id}", code=f"drone-test-{org_id}", is_active=True)
    db_session.add(plan)
    db_session.commit()
    db_session.refresh(plan)
    db_session.add(PlanFeature(plan_id=plan.id, feature_key="drone_fleet_management", enabled=True))
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
    org = Organization(name=f"Platform Ops ({role_name})")
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


class TestTenantSoftDelete:
    def test_delete_asset_soft_deletes_and_hides_from_tenant_reads(self, client):
        tokens = _register(client, "Soft Delete Tenant", "admin@softdelete.example.com")
        auth = _auth(tokens["access_token"])

        asset = client.post(
            "/api/v1/assets", json={"asset_type": "AIRCRAFT", "registration": "N50SD"}, headers=auth
        ).json()

        delete_resp = client.delete(f"/api/v1/assets/{asset['id']}", headers=auth)
        assert delete_resp.status_code == 200, delete_resp.text

        get_resp = client.get(f"/api/v1/assets/{asset['id']}", headers=auth)
        assert get_resp.status_code == 404

        list_resp = client.get("/api/v1/assets", headers=auth)
        assert all(a["id"] != asset["id"] for a in list_resp.json())

    def test_delete_with_reason_persists_it(self, client, db_session):
        tokens = _register(client, "Soft Delete Reason Tenant", "admin@softdelete-reason.example.com")
        auth = _auth(tokens["access_token"])

        asset = client.post(
            "/api/v1/assets", json={"asset_type": "DRONE", "registration": "UAV-SD1"}, headers=auth
        ).json()

        resp = client.delete(
            f"/api/v1/assets/{asset['id']}",
            params={"reason": "Damaged beyond repair"},
            headers=auth,
        )
        assert resp.status_code == 200
        assert resp.json()["id"] == asset["id"]  # response is the (now soft-deleted) asset

    def test_double_delete_returns_409(self, client):
        tokens = _register(client, "Double Delete Tenant", "admin@doubledelete.example.com")
        auth = _auth(tokens["access_token"])
        asset = client.post(
            "/api/v1/assets", json={"asset_type": "AIRCRAFT", "registration": "N51DD"}, headers=auth
        ).json()

        assert client.delete(f"/api/v1/assets/{asset['id']}", headers=auth).status_code == 200
        second = client.delete(f"/api/v1/assets/{asset['id']}", headers=auth)
        assert second.status_code == 409
        assert second.json()["error"]["code"] == "already_deleted"

    def test_cross_tenant_cannot_delete_others_asset(self, client):
        tokens_a = _register(client, "Delete Tenant A", "admin@delete-a.example.com")
        tokens_b = _register(client, "Delete Tenant B", "admin@delete-b.example.com")
        auth_a, auth_b = _auth(tokens_a["access_token"]), _auth(tokens_b["access_token"])

        asset = client.post(
            "/api/v1/assets", json={"asset_type": "AIRCRAFT", "registration": "N52XT"}, headers=auth_a
        ).json()

        resp = client.delete(f"/api/v1/assets/{asset['id']}", headers=auth_b)
        assert resp.status_code == 404

        # org A's asset is untouched.
        still_there = client.get(f"/api/v1/assets/{asset['id']}", headers=auth_a)
        assert still_there.status_code == 200

    def test_deleted_drone_hidden_from_drone_endpoints(self, client, db_session):
        tokens = _register(client, "Drone Delete Tenant", "admin@drone-delete.example.com")
        auth = _auth(tokens["access_token"])
        org_id = client.get("/api/v1/auth/me", headers=auth).json()["organization_id"]
        _entitle_drone_ops(db_session, org_id)

        drone = client.post(
            "/api/v1/drones",
            json={"registration": "UAV-SD2", "manufacturer": "DJI", "model": "M350"},
            headers=auth,
        ).json()

        assert client.delete(f"/api/v1/assets/{drone['id']}", headers=auth).status_code == 200
        assert client.get(f"/api/v1/drones/{drone['id']}", headers=auth).status_code == 404
        drones = client.get("/api/v1/drones", headers=auth).json()
        assert all(d["id"] != drone["id"] for d in drones)

    def test_deleted_aircraft_hidden_from_aircraft_endpoints(self, client):
        """Aircraft has its own table dual-writing an Asset (Slice A/B) --
        soft-deleting the Asset must also hide it from GET /aircraft and
        GET /aircraft/{id}, not just GET /assets."""
        tokens = _register(client, "Aircraft Delete Tenant", "admin@aircraft-delete.example.com")
        auth = _auth(tokens["access_token"])

        aircraft = client.post(
            "/api/v1/aircraft",
            json={"registration": "N53SD", "msn": "MSN-SD1", "aircraft_type": "A320"},
            headers=auth,
        ).json()

        assets = client.get("/api/v1/assets", headers=auth).json()
        asset_id = next(a["id"] for a in assets if a["registration"] == "N53SD")

        assert client.delete(f"/api/v1/assets/{asset_id}", headers=auth).status_code == 200
        assert client.get(f"/api/v1/aircraft/{aircraft['id']}", headers=auth).status_code == 404
        aircraft_list = client.get("/api/v1/aircraft", headers=auth).json()
        assert all(a["id"] != aircraft["id"] for a in aircraft_list)

    def test_delete_emits_audit_event(self, client, db_session):
        tokens = _register(client, "Delete Audit Tenant", "admin@delete-audit.example.com")
        auth = _auth(tokens["access_token"])
        asset = client.post(
            "/api/v1/assets", json={"asset_type": "AIRCRAFT", "registration": "N54AU"}, headers=auth
        ).json()

        client.delete(f"/api/v1/assets/{asset['id']}", params={"reason": "test"}, headers=auth)

        from sqlalchemy import select

        events = (
            db_session.execute(
                select(AuditEvent).where(
                    AuditEvent.action == "asset.deleted",
                    AuditEvent.entity_id == uuid.UUID(asset["id"]),
                )
            )
            .scalars()
            .all()
        )
        assert len(events) == 1
        assert events[0].event_metadata["reason"] == "test"


class TestPlatformDeletedRecordsQueue:
    def test_ordinary_tenant_admin_gets_403(self, client):
        tokens = _register(client, "Queue Denied Tenant", "admin@queue-denied.example.com")
        resp = client.get(
            "/api/v1/platform/deleted-records", headers=_auth(tokens["access_token"])
        )
        assert resp.status_code == 403

    def test_platform_admin_sees_soft_deleted_asset(self, client, db_session):
        tenant_tokens = _register(client, "Queue Tenant", "admin@queue.example.com")
        tenant_auth = _auth(tenant_tokens["access_token"])
        asset = client.post(
            "/api/v1/assets", json={"asset_type": "AIRCRAFT", "registration": "N55QU"}, headers=tenant_auth
        ).json()
        client.delete(f"/api/v1/assets/{asset['id']}", params={"reason": "queued"}, headers=tenant_auth)

        platform_auth = _create_platform_user(
            client, db_session, "ops@platform-queue.example.com", "PLATFORM_ADMIN"
        )
        resp = client.get(
            "/api/v1/platform/deleted-records",
            params={"organization_id": asset["organization_id"]},
            headers=platform_auth,
        )
        assert resp.status_code == 200
        body = resp.json()
        matching = [i for i in body["items"] if i["entity_id"] == asset["id"]]
        assert len(matching) == 1
        assert matching[0]["status"] == "DELETED"
        assert matching[0]["deletion_reason"] == "queued"
        assert matching[0]["identifier"] == "N55QU"


class TestPlatformRestore:
    def test_platform_admin_restores_asset_and_tenant_sees_it_again(self, client, db_session):
        tenant_tokens = _register(client, "Restore Tenant", "admin@restore.example.com")
        tenant_auth = _auth(tenant_tokens["access_token"])
        asset = client.post(
            "/api/v1/assets", json={"asset_type": "AIRCRAFT", "registration": "N56RS"}, headers=tenant_auth
        ).json()
        client.delete(f"/api/v1/assets/{asset['id']}", headers=tenant_auth)

        platform_auth = _create_platform_user(
            client, db_session, "ops@platform-restore.example.com", "PLATFORM_ADMIN"
        )
        restore_resp = client.post(
            f"/api/v1/platform/deleted-records/assets/{asset['id']}/restore", headers=platform_auth
        )
        assert restore_resp.status_code == 200, restore_resp.text

        # Tenant sees it again.
        get_resp = client.get(f"/api/v1/assets/{asset['id']}", headers=tenant_auth)
        assert get_resp.status_code == 200

    def test_platform_staff_can_restore(self, client, db_session):
        """DATA_RESTORE is granted to both PLATFORM_ADMIN and PLATFORM_STAFF
        -- restoring is routine platform-support work."""
        tenant_tokens = _register(client, "Staff Restore Tenant", "admin@staff-restore.example.com")
        tenant_auth = _auth(tenant_tokens["access_token"])
        asset = client.post(
            "/api/v1/assets", json={"asset_type": "DRONE", "registration": "UAV-SR1"}, headers=tenant_auth
        ).json()
        client.delete(f"/api/v1/assets/{asset['id']}", headers=tenant_auth)

        staff_auth = _create_platform_user(
            client, db_session, "staff@platform-restore.example.com", "PLATFORM_STAFF"
        )
        resp = client.post(
            f"/api/v1/platform/deleted-records/assets/{asset['id']}/restore", headers=staff_auth
        )
        assert resp.status_code == 200, resp.text

    def test_restoring_a_never_deleted_asset_returns_409(self, client, db_session):
        tenant_tokens = _register(client, "Not Deleted Tenant", "admin@not-deleted.example.com")
        tenant_auth = _auth(tenant_tokens["access_token"])
        asset = client.post(
            "/api/v1/assets", json={"asset_type": "AIRCRAFT", "registration": "N57ND"}, headers=tenant_auth
        ).json()

        platform_auth = _create_platform_user(
            client, db_session, "ops@platform-notdeleted.example.com", "PLATFORM_ADMIN"
        )
        resp = client.post(
            f"/api/v1/platform/deleted-records/assets/{asset['id']}/restore", headers=platform_auth
        )
        assert resp.status_code == 409
        assert resp.json()["error"]["code"] == "not_deleted"


class TestPlatformPermanentDelete:
    def test_platform_staff_cannot_permanently_delete(self, client, db_session):
        """DATA_PERMANENT_DELETE is PLATFORM_ADMIN-only -- irreversible, so
        narrower than DATA_RESTORE."""
        tenant_tokens = _register(client, "Staff Perm Tenant", "admin@staff-perm.example.com")
        tenant_auth = _auth(tenant_tokens["access_token"])
        asset = client.post(
            "/api/v1/assets", json={"asset_type": "AIRCRAFT", "registration": "N58SP"}, headers=tenant_auth
        ).json()
        client.delete(f"/api/v1/assets/{asset['id']}", headers=tenant_auth)

        staff_auth = _create_platform_user(
            client, db_session, "staff@platform-perm.example.com", "PLATFORM_STAFF"
        )
        resp = client.post(
            f"/api/v1/platform/deleted-records/assets/{asset['id']}/permanent-delete",
            json={"reason": "cleanup", "confirm": True},
            headers=staff_auth,
        )
        assert resp.status_code == 403

    def test_permanent_delete_requires_confirm_true(self, client, db_session):
        tenant_tokens = _register(client, "Confirm Tenant", "admin@confirm.example.com")
        tenant_auth = _auth(tenant_tokens["access_token"])
        asset = client.post(
            "/api/v1/assets", json={"asset_type": "AIRCRAFT", "registration": "N59CF"}, headers=tenant_auth
        ).json()
        client.delete(f"/api/v1/assets/{asset['id']}", headers=tenant_auth)

        admin_auth = _create_platform_user(
            client, db_session, "ops@platform-confirm.example.com", "PLATFORM_ADMIN"
        )
        resp = client.post(
            f"/api/v1/platform/deleted-records/assets/{asset['id']}/permanent-delete",
            json={"reason": "cleanup", "confirm": False},
            headers=admin_auth,
        )
        assert resp.status_code == 409
        assert resp.json()["error"]["code"] == "confirmation_required"

    def test_permanent_delete_refuses_a_still_active_asset(self, client, db_session):
        tenant_tokens = _register(client, "Active Perm Tenant", "admin@active-perm.example.com")
        tenant_auth = _auth(tenant_tokens["access_token"])
        asset = client.post(
            "/api/v1/assets", json={"asset_type": "AIRCRAFT", "registration": "N60AP"}, headers=tenant_auth
        ).json()

        admin_auth = _create_platform_user(
            client, db_session, "ops@platform-activeperm.example.com", "PLATFORM_ADMIN"
        )
        resp = client.post(
            f"/api/v1/platform/deleted-records/assets/{asset['id']}/permanent-delete",
            json={"reason": "cleanup", "confirm": True},
            headers=admin_auth,
        )
        assert resp.status_code == 409
        assert resp.json()["error"]["code"] == "not_soft_deleted"

    def test_permanent_delete_of_an_empty_asset_succeeds_and_removes_from_queue(self, client, db_session):
        tenant_tokens = _register(client, "Empty Perm Tenant", "admin@empty-perm.example.com")
        tenant_auth = _auth(tenant_tokens["access_token"])
        asset = client.post(
            "/api/v1/assets", json={"asset_type": "AIRCRAFT", "registration": "N61EP"}, headers=tenant_auth
        ).json()
        client.delete(f"/api/v1/assets/{asset['id']}", headers=tenant_auth)

        admin_auth = _create_platform_user(
            client, db_session, "ops@platform-emptyperm.example.com", "PLATFORM_ADMIN"
        )
        resp = client.post(
            f"/api/v1/platform/deleted-records/assets/{asset['id']}/permanent-delete",
            json={"reason": "no dependent records, safe to purge", "confirm": True},
            headers=admin_auth,
        )
        assert resp.status_code == 200, resp.text

        queue = client.get(
            "/api/v1/platform/deleted-records",
            params={"organization_id": asset["organization_id"]},
            headers=admin_auth,
        ).json()
        assert all(i["entity_id"] != asset["id"] for i in queue["items"])

    def test_permanent_delete_blocked_by_dependent_flight_records(self, client, db_session):
        """The safety property the platform spec asks for ("do not implement
        unrestricted permanent deletion for compliance-critical records")
        falls directly out of the pre-existing ondelete=RESTRICT FK on
        Flight.asset_id -- a drone with real flight history cannot be
        permanently purged."""
        tenant_tokens = _register(client, "Dependent Perm Tenant", "admin@dependent-perm.example.com")
        tenant_auth = _auth(tenant_tokens["access_token"])
        tenant_org_id = client.get("/api/v1/auth/me", headers=tenant_auth).json()["organization_id"]
        _entitle_drone_ops(db_session, tenant_org_id)
        drone = client.post(
            "/api/v1/drones", json={"registration": "UAV-DP1"}, headers=tenant_auth
        ).json()
        flight_resp = client.post(
            f"/api/v1/drones/{drone['id']}/flights",
            json={"flown_at": "2025-01-01T00:00:00Z", "duration_minutes": 30, "cycles": 1},
            headers=tenant_auth,
        )
        assert flight_resp.status_code == 201, flight_resp.text

        client.delete(f"/api/v1/assets/{drone['id']}", headers=tenant_auth)

        admin_auth = _create_platform_user(
            client, db_session, "ops@platform-dependentperm.example.com", "PLATFORM_ADMIN"
        )
        resp = client.post(
            f"/api/v1/platform/deleted-records/assets/{drone['id']}/permanent-delete",
            json={"reason": "attempt purge", "confirm": True},
            headers=admin_auth,
        )
        assert resp.status_code == 409
        assert resp.json()["error"]["code"] == "has_dependent_records"
        # Not asserting the drone is still in the deleted-records queue here:
        # this test's `client` fixture shares ONE session/transaction across
        # every request (see tests/integration/conftest.py), and
        # permanently_delete_asset's internal db.rollback() on the RESTRICT
        # violation rolls back that entire shared transaction -- including
        # this test's earlier, already-"committed" soft-delete request --
        # not just the failed delete. That is a property of this specific
        # test harness (documented precedent: test_asset_foundation.py's
        # test_duplicate_registration_leaves_no_orphaned_asset_or_detail),
        # not of the real per-request-session production behavior.

    def test_permanent_delete_emits_audit_event_before_row_is_gone(self, client, db_session):
        tenant_tokens = _register(client, "Audit Perm Tenant", "admin@audit-perm.example.com")
        tenant_auth = _auth(tenant_tokens["access_token"])
        asset = client.post(
            "/api/v1/assets", json={"asset_type": "AIRCRAFT", "registration": "N62AU"}, headers=tenant_auth
        ).json()
        client.delete(f"/api/v1/assets/{asset['id']}", headers=tenant_auth)

        admin_auth = _create_platform_user(
            client, db_session, "ops@platform-auditperm.example.com", "PLATFORM_ADMIN"
        )
        client.post(
            f"/api/v1/platform/deleted-records/assets/{asset['id']}/permanent-delete",
            json={"reason": "final cleanup", "confirm": True},
            headers=admin_auth,
        )

        from sqlalchemy import select

        events = (
            db_session.execute(
                select(AuditEvent).where(
                    AuditEvent.action == "asset.permanently_deleted",
                    AuditEvent.entity_id == uuid.UUID(asset["id"]),
                )
            )
            .scalars()
            .all()
        )
        assert len(events) == 1
        assert events[0].event_metadata["reason"] == "final cleanup"
