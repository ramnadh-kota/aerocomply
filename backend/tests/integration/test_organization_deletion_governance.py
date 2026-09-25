"""Platform Control Plane: organization-level deletion-request workflow --
the second entity on the same soft-delete/restore/permanent-delete lifecycle
as Asset (see tests/integration/test_soft_delete_governance.py).

Covers:
    Tenant Admin requests deletion -> org soft-deleted
        -> every user in the org is refused at login AND on any existing
           token's next request
        -> visible in Platform Admin's deleted-records queue
           (entity_type=ORGANIZATION)
        -> Platform Admin RESTORE -> org's users can authenticate again
        -> Platform Admin PERMANENT DELETE only when the org has zero
           Users and zero Assets left (no FK to lean on for Organization,
           unlike Asset -- see deletion_service.permanently_delete_
           organization's docstring)
"""

import uuid

import pytest
from sqlalchemy import select

from app.core.deps import get_db_session
from app.core.security import hash_password
from app.main import app
from app.models.audit_event import AuditEvent
from app.models.organization import Organization
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


class TestTenantDeletionRequest:
    def test_request_deletion_soft_deletes_organization(self, client):
        tokens = _register(client, "Deletion Request Tenant", "admin@deletion-req.example.com")
        auth = _auth(tokens["access_token"])

        resp = client.post("/api/v1/tenant/deletion-request", json={"reason": "closing shop"}, headers=auth)
        assert resp.status_code == 200, resp.text

    def test_existing_token_is_refused_on_next_request_after_deletion_request(self, client):
        """app/core/deps.py's get_current_user re-checks org.deleted_at on
        EVERY request -- the very next call with the same still-unexpired
        access token must be refused, not just a future login."""
        tokens = _register(client, "Token Cutoff Tenant", "admin@token-cutoff.example.com")
        auth = _auth(tokens["access_token"])

        client.post("/api/v1/tenant/deletion-request", json={}, headers=auth)

        resp = client.get("/api/v1/tenant/profile", headers=auth)
        assert resp.status_code == 401

    def test_login_is_refused_after_deletion_request(self, client):
        tokens = _register(client, "Login Refused Tenant", "admin@login-refused.example.com")
        auth = _auth(tokens["access_token"])
        client.post("/api/v1/tenant/deletion-request", json={}, headers=auth)

        login = client.post(
            "/api/v1/auth/login",
            json={"email": "admin@login-refused.example.com", "password": "supersecret123"},
        )
        assert login.status_code == 401

    def test_double_deletion_request_returns_409(self, client, db_session):
        """A second HTTP request would 401 (the first request's token is
        already refused by app/core/deps.py) rather than reach the
        idempotency guard at all -- so this exercises
        deletion_service.request_organization_deletion directly, the same
        function the endpoint calls, against an org already deletion-
        requested via the real API."""
        tokens = _register(client, "Double Deletion Tenant", "admin@double-deletion.example.com")
        auth = _auth(tokens["access_token"])
        org_id = client.get("/api/v1/auth/me", headers=auth).json()["organization_id"]
        client.post("/api/v1/tenant/deletion-request", json={}, headers=auth)

        from app.core.errors import ConflictError
        from app.schemas.deletion import OrganizationDeletionRequest
        from app.services import deletion_service

        with pytest.raises(ConflictError) as exc:
            deletion_service.request_organization_deletion(
                db_session,
                organization_id=uuid.UUID(org_id),
                actor_user_id=uuid.uuid4(),
                payload=OrganizationDeletionRequest(),
            )
        assert exc.value.code == "already_deleted"

    def test_deletion_request_emits_audit_event(self, client, db_session):
        tokens = _register(client, "Deletion Audit Tenant", "admin@deletion-audit.example.com")
        auth = _auth(tokens["access_token"])
        org_id = client.get("/api/v1/auth/me", headers=auth).json()["organization_id"]

        client.post("/api/v1/tenant/deletion-request", json={"reason": "test reason"}, headers=auth)

        events = (
            db_session.execute(
                select(AuditEvent).where(
                    AuditEvent.action == "organization.deletion_requested",
                    AuditEvent.entity_id == uuid.UUID(org_id),
                )
            )
            .scalars()
            .all()
        )
        assert len(events) == 1
        assert events[0].event_metadata["reason"] == "test reason"

    def test_ordinary_member_without_org_manage_cannot_request_deletion(self, client, db_session):
        """Permission.ORG_MANAGE gates this -- a VIEWER-role user must not
        be able to delete the whole organization."""
        tokens = _register(client, "Viewer Deletion Tenant", "admin@viewer-deletion.example.com")
        org_id = client.get(
            "/api/v1/auth/me", headers=_auth(tokens["access_token"])
        ).json()["organization_id"]

        viewer = User(
            organization_id=uuid.UUID(org_id),
            email="viewer@viewer-deletion.example.com",
            hashed_password=hash_password("supersecret123"),
            full_name="Viewer",
            is_active=True,
        )
        db_session.add(viewer)
        db_session.flush()
        db_session.add(UserRole(user_id=viewer.id, role_name="VIEWER", organization_id=uuid.UUID(org_id)))
        db_session.commit()

        login = client.post(
            "/api/v1/auth/login",
            json={"email": "viewer@viewer-deletion.example.com", "password": "supersecret123"},
        )
        viewer_auth = _auth(login.json()["access_token"])

        resp = client.post("/api/v1/tenant/deletion-request", json={}, headers=viewer_auth)
        assert resp.status_code == 403


class TestPlatformOrganizationDeletionQueue:
    def test_platform_admin_sees_deletion_requested_organization(self, client, db_session):
        tenant_tokens = _register(client, "Org Queue Tenant", "admin@org-queue.example.com")
        tenant_auth = _auth(tenant_tokens["access_token"])
        org_id = client.get("/api/v1/auth/me", headers=tenant_auth).json()["organization_id"]
        client.post("/api/v1/tenant/deletion-request", json={"reason": "queued for review"}, headers=tenant_auth)

        platform_auth = _create_platform_user(
            client, db_session, "ops@org-queue-platform.example.com", "PLATFORM_ADMIN"
        )
        resp = client.get(
            "/api/v1/platform/deleted-records",
            params={"entity_type": "ORGANIZATION", "organization_id": org_id},
            headers=platform_auth,
        )
        assert resp.status_code == 200
        items = resp.json()["items"]
        assert len(items) == 1
        assert items[0]["entity_type"] == "ORGANIZATION"
        assert items[0]["deletion_reason"] == "queued for review"

    def test_entity_type_filter_excludes_assets(self, client, db_session):
        tenant_tokens = _register(client, "Filter Tenant", "admin@filter-tenant.example.com")
        tenant_auth = _auth(tenant_tokens["access_token"])
        asset = client.post(
            "/api/v1/assets", json={"asset_type": "AIRCRAFT", "registration": "N70FL"}, headers=tenant_auth
        ).json()
        client.delete(f"/api/v1/assets/{asset['id']}", headers=tenant_auth)

        platform_auth = _create_platform_user(
            client, db_session, "ops@filter-platform.example.com", "PLATFORM_ADMIN"
        )
        resp = client.get(
            "/api/v1/platform/deleted-records",
            params={"entity_type": "ORGANIZATION", "organization_id": asset["organization_id"]},
            headers=platform_auth,
        )
        assert resp.status_code == 200
        assert resp.json()["items"] == []


class TestPlatformOrganizationRestore:
    def test_platform_admin_restores_organization_and_login_works_again(self, client, db_session):
        tenant_tokens = _register(client, "Org Restore Tenant", "admin@org-restore.example.com")
        tenant_auth = _auth(tenant_tokens["access_token"])
        org_id = client.get("/api/v1/auth/me", headers=tenant_auth).json()["organization_id"]
        client.post("/api/v1/tenant/deletion-request", json={}, headers=tenant_auth)

        platform_auth = _create_platform_user(
            client, db_session, "ops@org-restore-platform.example.com", "PLATFORM_ADMIN"
        )
        restore_resp = client.post(
            f"/api/v1/platform/deleted-records/organizations/{org_id}/restore", headers=platform_auth
        )
        assert restore_resp.status_code == 200, restore_resp.text

        login = client.post(
            "/api/v1/auth/login",
            json={"email": "admin@org-restore.example.com", "password": "supersecret123"},
        )
        assert login.status_code == 200

    def test_platform_staff_can_restore_organization(self, client, db_session):
        tenant_tokens = _register(client, "Org Staff Restore Tenant", "admin@org-staff-restore.example.com")
        tenant_auth = _auth(tenant_tokens["access_token"])
        org_id = client.get("/api/v1/auth/me", headers=tenant_auth).json()["organization_id"]
        client.post("/api/v1/tenant/deletion-request", json={}, headers=tenant_auth)

        staff_auth = _create_platform_user(
            client, db_session, "staff@org-staff-restore.example.com", "PLATFORM_STAFF"
        )
        resp = client.post(
            f"/api/v1/platform/deleted-records/organizations/{org_id}/restore", headers=staff_auth
        )
        assert resp.status_code == 200, resp.text

    def test_restoring_a_never_deleted_organization_returns_409(self, client, db_session):
        tenant_tokens = _register(client, "Org Not Deleted Tenant", "admin@org-not-deleted.example.com")
        org_id = client.get(
            "/api/v1/auth/me", headers=_auth(tenant_tokens["access_token"])
        ).json()["organization_id"]

        platform_auth = _create_platform_user(
            client, db_session, "ops@org-notdeleted-platform.example.com", "PLATFORM_ADMIN"
        )
        resp = client.post(
            f"/api/v1/platform/deleted-records/organizations/{org_id}/restore", headers=platform_auth
        )
        assert resp.status_code == 409
        assert resp.json()["error"]["code"] == "not_deleted"


class TestPlatformOrganizationPermanentDelete:
    def test_platform_staff_cannot_permanently_delete_organization(self, client, db_session):
        tenant_tokens = _register(client, "Org Staff Perm Tenant", "admin@org-staff-perm.example.com")
        tenant_auth = _auth(tenant_tokens["access_token"])
        org_id = client.get("/api/v1/auth/me", headers=tenant_auth).json()["organization_id"]
        client.post("/api/v1/tenant/deletion-request", json={}, headers=tenant_auth)

        staff_auth = _create_platform_user(
            client, db_session, "staff@org-perm.example.com", "PLATFORM_STAFF"
        )
        resp = client.post(
            f"/api/v1/platform/deleted-records/organizations/{org_id}/permanent-delete",
            json={"reason": "cleanup", "confirm": True},
            headers=staff_auth,
        )
        assert resp.status_code == 403

    def test_tenant_cannot_call_platform_permanent_delete_endpoint(self, client):
        tokens = _register(client, "Org Tenant Perm Attempt", "admin@org-tenant-perm.example.com")
        auth = _auth(tokens["access_token"])
        org_id = client.get("/api/v1/auth/me", headers=auth).json()["organization_id"]
        client.post("/api/v1/tenant/deletion-request", json={}, headers=auth)

        # The org's own token is already refused post-deletion-request
        # (see TestTenantDeletionRequest), so this also proves the tenant
        # cannot reach the platform endpoint even with its own valid-looking
        # token from before the request.
        resp = client.post(
            f"/api/v1/platform/deleted-records/organizations/{org_id}/permanent-delete",
            json={"reason": "attempt", "confirm": True},
            headers=auth,
        )
        assert resp.status_code in (401, 403)

    def test_permanent_delete_blocked_while_users_exist(self, client, db_session):
        tenant_tokens = _register(client, "Org Users Block Tenant", "admin@org-users-block.example.com")
        tenant_auth = _auth(tenant_tokens["access_token"])
        org_id = client.get("/api/v1/auth/me", headers=tenant_auth).json()["organization_id"]
        client.post("/api/v1/tenant/deletion-request", json={}, headers=tenant_auth)

        admin_auth = _create_platform_user(
            client, db_session, "ops@org-usersblock-platform.example.com", "PLATFORM_ADMIN"
        )
        resp = client.post(
            f"/api/v1/platform/deleted-records/organizations/{org_id}/permanent-delete",
            json={"reason": "attempt purge", "confirm": True},
            headers=admin_auth,
        )
        assert resp.status_code == 409
        assert resp.json()["error"]["code"] == "has_dependent_records"

    def test_permanent_delete_requires_confirm_true(self, client, db_session):
        tenant_tokens = _register(client, "Org Confirm Tenant", "admin@org-confirm.example.com")
        tenant_auth = _auth(tenant_tokens["access_token"])
        org_id = client.get("/api/v1/auth/me", headers=tenant_auth).json()["organization_id"]
        client.post("/api/v1/tenant/deletion-request", json={}, headers=tenant_auth)

        admin_auth = _create_platform_user(
            client, db_session, "ops@org-confirm-platform.example.com", "PLATFORM_ADMIN"
        )
        resp = client.post(
            f"/api/v1/platform/deleted-records/organizations/{org_id}/permanent-delete",
            json={"reason": "cleanup", "confirm": False},
            headers=admin_auth,
        )
        assert resp.status_code == 409
        assert resp.json()["error"]["code"] == "confirmation_required"

    def test_permanent_delete_refuses_a_still_active_organization(self, client, db_session):
        tenant_tokens = _register(client, "Org Active Perm Tenant", "admin@org-active-perm.example.com")
        org_id = client.get(
            "/api/v1/auth/me", headers=_auth(tenant_tokens["access_token"])
        ).json()["organization_id"]

        admin_auth = _create_platform_user(
            client, db_session, "ops@org-activeperm-platform.example.com", "PLATFORM_ADMIN"
        )
        resp = client.post(
            f"/api/v1/platform/deleted-records/organizations/{org_id}/permanent-delete",
            json={"reason": "cleanup", "confirm": True},
            headers=admin_auth,
        )
        assert resp.status_code == 409
        assert resp.json()["error"]["code"] == "not_soft_deleted"

    def test_permanent_delete_succeeds_for_a_genuinely_empty_organization(self, client, db_session):
        """Directly exercises the service, not the API: creating an org via
        the public API always creates its first admin User, so there is no
        HTTP-reachable way to end up with a deletion-requested org with zero
        Users left through ordinary usage. This proves the governance path
        works once that condition is met (e.g. after every user was
        separately offboarded) without relying on a hypothetical UI flow
        that doesn't exist yet."""
        from app.schemas.deletion import PermanentDeleteRequest
        from app.services import deletion_service, restoration_service

        org = Organization(name="Genuinely Empty Org")
        db_session.add(org)
        db_session.commit()
        db_session.refresh(org)

        restoration_service_actor = uuid.uuid4()
        from app.schemas.deletion import OrganizationDeletionRequest

        deletion_service.request_organization_deletion(
            db_session,
            organization_id=org.id,
            actor_user_id=restoration_service_actor,
            payload=OrganizationDeletionRequest(reason="never used"),
        )

        deletion_service.permanently_delete_organization(
            db_session,
            actor_user_id=restoration_service_actor,
            organization_id=org.id,
            payload=PermanentDeleteRequest(reason="confirmed empty", confirm=True),
        )

        assert db_session.get(Organization, org.id) is None

    def test_permanent_delete_emits_audit_event(self, client, db_session):
        from app.schemas.deletion import OrganizationDeletionRequest, PermanentDeleteRequest
        from app.services import deletion_service

        org = Organization(name="Audited Empty Org")
        db_session.add(org)
        db_session.commit()
        db_session.refresh(org)
        actor_id = uuid.uuid4()

        deletion_service.request_organization_deletion(
            db_session,
            organization_id=org.id,
            actor_user_id=actor_id,
            payload=OrganizationDeletionRequest(),
        )
        deletion_service.permanently_delete_organization(
            db_session,
            actor_user_id=actor_id,
            organization_id=org.id,
            payload=PermanentDeleteRequest(reason="final purge", confirm=True),
        )

        events = (
            db_session.execute(
                select(AuditEvent).where(
                    AuditEvent.action == "organization.permanently_deleted",
                    AuditEvent.entity_id == org.id,
                )
            )
            .scalars()
            .all()
        )
        assert len(events) == 1
        assert events[0].event_metadata["reason"] == "final purge"


class TestOrganizationDeletionTenantIsolation:
    def test_tenant_a_deletion_request_never_affects_tenant_b(self, client):
        tokens_a = _register(client, "Isolation Tenant A", "admin@isolation-a.example.com")
        tokens_b = _register(client, "Isolation Tenant B", "admin@isolation-b.example.com")
        auth_a, auth_b = _auth(tokens_a["access_token"]), _auth(tokens_b["access_token"])

        client.post("/api/v1/tenant/deletion-request", json={}, headers=auth_a)

        # Org A's token is now refused...
        assert client.get("/api/v1/tenant/profile", headers=auth_a).status_code == 401
        # ...but Org B is completely unaffected.
        assert client.get("/api/v1/tenant/profile", headers=auth_b).status_code == 200

    def test_platform_admin_cannot_see_tenant_bs_deleted_org_under_tenant_as_filter(self, client, db_session):
        tokens_a = _register(client, "Isolation Filter A", "admin@isolation-filter-a.example.com")
        tokens_b = _register(client, "Isolation Filter B", "admin@isolation-filter-b.example.com")
        auth_a = _auth(tokens_a["access_token"])
        auth_b = _auth(tokens_b["access_token"])
        org_a_id = client.get("/api/v1/auth/me", headers=auth_a).json()["organization_id"]
        org_b_id = client.get("/api/v1/auth/me", headers=auth_b).json()["organization_id"]

        client.post("/api/v1/tenant/deletion-request", json={}, headers=auth_a)
        client.post("/api/v1/tenant/deletion-request", json={}, headers=auth_b)

        platform_auth = _create_platform_user(
            client, db_session, "ops@isolation-filter-platform.example.com", "PLATFORM_ADMIN"
        )
        resp = client.get(
            "/api/v1/platform/deleted-records",
            params={"entity_type": "ORGANIZATION", "organization_id": org_a_id},
            headers=platform_auth,
        )
        items = resp.json()["items"]
        assert all(i["entity_id"] == org_a_id for i in items)
        assert not any(i["entity_id"] == org_b_id for i in items)
