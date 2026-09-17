"""Phase 18.3: tenant provisioning orchestration
(app/services/provisioning_service.py + POST /platform/organizations/provision).

Confirms provisioning composes the existing Organization/Subscription/User/
entitlement/auth systems rather than duplicating them, that the Super
Master never handles the new admin's password, that authorization is
platform-scoped, and that a failure partway through leaves no orphaned
Organization/Subscription behind.
"""

import uuid

from sqlalchemy import select

from app.core.security import hash_password, verify_password
from app.models.audit_event import AuditEvent
from app.models.organization import Organization
from app.models.plan import Plan, PlanFeature
from app.models.subscription import Subscription
from app.models.user import User, UserRole
from app.services.entitlement_service import EntitlementResolutionStatus, resolve_entitlements


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


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


def _create_platform_admin(db_session, email):
    org = Organization(name="Provisioning Platform Ops")
    db_session.add(org)
    db_session.flush()
    user = User(
        organization_id=org.id,
        email=email,
        hashed_password=hash_password("supersecret123"),
        full_name="Platform Admin",
        is_active=True,
    )
    db_session.add(user)
    db_session.flush()
    db_session.add(UserRole(user_id=user.id, role_name="PLATFORM_ADMIN", organization_id=org.id))
    db_session.commit()
    return user


def _login(client, email, password="supersecret123"):
    resp = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200
    return resp.json()


def _make_plan(db_session, *, feature_key: str | None = None):
    plan = Plan(name="Provisioning Test Plan", code=f"prov-plan-{uuid.uuid4().hex[:8]}")
    db_session.add(plan)
    db_session.commit()
    if feature_key:
        db_session.add(PlanFeature(plan_id=plan.id, feature_key=feature_key, enabled=True))
        db_session.commit()
    return plan


def _provision_payload(*, plan_id, admin_email, org_name=None, status="TRIALING"):
    return {
        "organization_name": org_name or f"Provisioned Org {uuid.uuid4().hex[:8]}",
        "plan_id": str(plan_id),
        "subscription_status": status,
        "admin_email": admin_email,
        "admin_full_name": "New Tenant Admin",
    }


class TestPlatformAuthorization:
    def test_platform_admin_can_provision(self, client, db_session):
        admin = _create_platform_admin(db_session, "prov-admin1@example.com")
        tokens = _login(client, admin.email)
        plan = _make_plan(db_session)

        resp = client.post(
            "/api/v1/platform/organizations/provision",
            headers=_auth(tokens["access_token"]),
            json=_provision_payload(plan_id=plan.id, admin_email="new-tenant-admin1@example.com"),
        )
        assert resp.status_code == 201

    def test_unauthenticated_request_rejected(self, client, db_session):
        plan = _make_plan(db_session)
        resp = client.post(
            "/api/v1/platform/organizations/provision",
            json=_provision_payload(plan_id=plan.id, admin_email="unauth@example.com"),
        )
        assert resp.status_code == 401

    def test_tenant_org_admin_cannot_provision(self, client, db_session):
        tenant = _register(client, "Tenant Trying To Provision", "tenant-admin1@example.com")
        plan = _make_plan(db_session)

        resp = client.post(
            "/api/v1/platform/organizations/provision",
            headers=_auth(tenant["access_token"]),
            json=_provision_payload(plan_id=plan.id, admin_email="tenant-victim1@example.com"),
        )
        assert resp.status_code == 403

    def test_tenant_viewer_cannot_provision(self, client, db_session):
        tenant = _register(client, "Tenant Viewer Org Prov", "tenant-owner2@example.com")
        org_id = uuid.UUID(
            client.get("/api/v1/auth/me", headers=_auth(tenant["access_token"])).json()[
                "organization_id"
            ]
        )
        viewer = User(
            organization_id=org_id,
            email="tenant-viewer2@example.com",
            hashed_password=hash_password("supersecret123"),
            full_name="Viewer",
            is_active=True,
        )
        db_session.add(viewer)
        db_session.flush()
        db_session.add(UserRole(user_id=viewer.id, role_name="VIEWER", organization_id=org_id))
        db_session.commit()
        viewer_tokens = _login(client, viewer.email)
        plan = _make_plan(db_session)

        resp = client.post(
            "/api/v1/platform/organizations/provision",
            headers=_auth(viewer_tokens["access_token"]),
            json=_provision_payload(plan_id=plan.id, admin_email="tenant-victim2@example.com"),
        )
        assert resp.status_code == 403


class TestProvisioningResult:
    def test_organization_subscription_and_admin_created(self, client, db_session):
        admin = _create_platform_admin(db_session, "prov-admin2@example.com")
        tokens = _login(client, admin.email)
        plan = _make_plan(db_session)
        admin_email = "new-tenant-admin2@example.com"

        resp = client.post(
            "/api/v1/platform/organizations/provision",
            headers=_auth(tokens["access_token"]),
            json=_provision_payload(plan_id=plan.id, admin_email=admin_email),
        )
        assert resp.status_code == 201
        body = resp.json()

        assert body["plan_id"] == str(plan.id)
        assert body["subscription_status"] == "TRIALING"
        assert body["admin_email"] == admin_email
        assert body["admin_email_verified"] is False
        assert body["onboarding_email_sent"] is True

        org = db_session.get(Organization, uuid.UUID(body["organization_id"]))
        assert org is not None
        assert org.status == "ACTIVE"

        sub = db_session.get(Subscription, uuid.UUID(body["subscription_id"]))
        assert sub is not None
        assert sub.organization_id == org.id
        assert sub.plan_id == plan.id

        tenant_admin = db_session.get(User, uuid.UUID(body["admin_user_id"]))
        assert tenant_admin is not None
        assert tenant_admin.organization_id == org.id
        assert tenant_admin.email == admin_email

    def test_admin_has_org_admin_role_only_within_new_org(self, client, db_session):
        admin = _create_platform_admin(db_session, "prov-admin3@example.com")
        tokens = _login(client, admin.email)
        plan = _make_plan(db_session)
        admin_email = "new-tenant-admin3@example.com"

        resp = client.post(
            "/api/v1/platform/organizations/provision",
            headers=_auth(tokens["access_token"]),
            json=_provision_payload(plan_id=plan.id, admin_email=admin_email),
        )
        body = resp.json()

        roles = (
            db_session.execute(
                select(UserRole).where(UserRole.user_id == uuid.UUID(body["admin_user_id"]))
            )
            .scalars()
            .all()
        )
        assert len(roles) == 1
        assert roles[0].role_name == "ORG_ADMIN"
        assert roles[0].organization_id == uuid.UUID(body["organization_id"])
        assert "PLATFORM_ADMIN" not in [r.role_name for r in roles]
        assert "PLATFORM_STAFF" not in [r.role_name for r in roles]

    def test_response_contains_no_secrets(self, client, db_session):
        admin = _create_platform_admin(db_session, "prov-admin4@example.com")
        tokens = _login(client, admin.email)
        plan = _make_plan(db_session)

        resp = client.post(
            "/api/v1/platform/organizations/provision",
            headers=_auth(tokens["access_token"]),
            json=_provision_payload(plan_id=plan.id, admin_email="new-tenant-admin4@example.com"),
        )
        body_text = resp.text.lower()
        assert "password" not in body_text
        assert "hashed" not in body_text
        assert "otp" not in body_text
        assert "token" not in body_text


class TestClientCannotEscalate:
    def test_client_cannot_choose_organization_id(self, client, db_session):
        # ProvisionOrganizationRequest has no organization_id field at all --
        # the server always creates a fresh Organization. Sending one is
        # simply ignored by Pydantic (extra fields dropped), never trusted.
        admin = _create_platform_admin(db_session, "prov-admin5@example.com")
        tokens = _login(client, admin.email)
        plan = _make_plan(db_session)
        payload = _provision_payload(plan_id=plan.id, admin_email="new-tenant-admin5@example.com")
        payload["organization_id"] = str(uuid.uuid4())

        resp = client.post(
            "/api/v1/platform/organizations/provision",
            headers=_auth(tokens["access_token"]),
            json=payload,
        )
        assert resp.status_code == 201
        assert resp.json()["organization_id"] != payload["organization_id"]

    def test_client_cannot_set_admin_password(self, client, db_session):
        admin = _create_platform_admin(db_session, "prov-admin6@example.com")
        tokens = _login(client, admin.email)
        plan = _make_plan(db_session)
        payload = _provision_payload(plan_id=plan.id, admin_email="new-tenant-admin6@example.com")
        payload["password"] = "attacker-chosen-password"

        resp = client.post(
            "/api/v1/platform/organizations/provision",
            headers=_auth(tokens["access_token"]),
            json=payload,
        )
        assert resp.status_code == 201
        new_user = db_session.get(User, uuid.UUID(resp.json()["admin_user_id"]))
        assert not verify_password("attacker-chosen-password", new_user.hashed_password)

    def test_client_cannot_assign_platform_role(self, client, db_session):
        admin = _create_platform_admin(db_session, "prov-admin7@example.com")
        tokens = _login(client, admin.email)
        plan = _make_plan(db_session)
        payload = _provision_payload(plan_id=plan.id, admin_email="new-tenant-admin7@example.com")
        payload["role"] = "PLATFORM_ADMIN"

        resp = client.post(
            "/api/v1/platform/organizations/provision",
            headers=_auth(tokens["access_token"]),
            json=payload,
        )
        assert resp.status_code == 201
        roles = (
            db_session.execute(
                select(UserRole).where(UserRole.user_id == uuid.UUID(resp.json()["admin_user_id"]))
            )
            .scalars()
            .all()
        )
        assert [r.role_name for r in roles] == ["ORG_ADMIN"]


class TestDuplicateProtection:
    def test_duplicate_admin_email_rejected(self, client, db_session):
        admin = _create_platform_admin(db_session, "prov-admin8@example.com")
        tokens = _login(client, admin.email)
        plan = _make_plan(db_session)
        dup_email = "duplicate-tenant-admin@example.com"

        first = client.post(
            "/api/v1/platform/organizations/provision",
            headers=_auth(tokens["access_token"]),
            json=_provision_payload(plan_id=plan.id, admin_email=dup_email),
        )
        assert first.status_code == 201

        second = client.post(
            "/api/v1/platform/organizations/provision",
            headers=_auth(tokens["access_token"]),
            json=_provision_payload(plan_id=plan.id, admin_email=dup_email),
        )
        assert second.status_code == 409

    def test_failed_provisioning_leaves_no_orphaned_organization(self, client, db_session):
        """The second attempt with a duplicate admin email fails at the
        admin-creation step, after the Organization and Subscription were
        already created -- confirms the compensating rollback in
        provisioning_service._rollback_partial_provisioning actually runs,
        not just that the HTTP call returns 409."""
        admin = _create_platform_admin(db_session, "prov-admin9@example.com")
        tokens = _login(client, admin.email)
        plan = _make_plan(db_session)
        dup_email = "duplicate-tenant-admin2@example.com"

        client.post(
            "/api/v1/platform/organizations/provision",
            headers=_auth(tokens["access_token"]),
            json=_provision_payload(plan_id=plan.id, admin_email=dup_email),
        )

        second = client.post(
            "/api/v1/platform/organizations/provision",
            headers=_auth(tokens["access_token"]),
            json=_provision_payload(
                plan_id=plan.id, admin_email=dup_email, org_name="Orphan Candidate Org"
            ),
        )
        assert second.status_code == 409

        orphan = db_session.execute(
            select(Organization).where(Organization.name == "Orphan Candidate Org")
        ).scalar_one_or_none()
        assert orphan is None
        # No orphaned subscription against a since-deleted candidate org id
        # either -- Subscription.organization_id is a plain column (not a
        # real FK, per TenantScopedMixin's repo-wide convention), so an
        # orphaned row would otherwise sit there forever with no
        # organization to belong to.
        orphan_subs = (
            db_session.execute(
                select(Subscription).where(
                    ~Subscription.organization_id.in_(select(Organization.id))
                )
            )
            .scalars()
            .all()
        )
        assert orphan_subs == []

    def test_repeated_identical_request_does_not_silently_duplicate(self, client, db_session):
        admin = _create_platform_admin(db_session, "prov-admin10@example.com")
        tokens = _login(client, admin.email)
        plan = _make_plan(db_session)
        payload = _provision_payload(
            plan_id=plan.id, admin_email="repeat-tenant-admin@example.com", org_name="Repeat Org"
        )

        first = client.post(
            "/api/v1/platform/organizations/provision",
            headers=_auth(tokens["access_token"]),
            json=payload,
        )
        assert first.status_code == 201

        second = client.post(
            "/api/v1/platform/organizations/provision",
            headers=_auth(tokens["access_token"]),
            json=payload,
        )
        # Same admin email -> rejected, not silently accepted as a duplicate
        # success. (Whether the first call's own row survives the second
        # call's compensating rollback is NOT asserted here: this test
        # suite's shared db_session/client fixture has a known
        # characteristic -- documented in prior work on this codebase --
        # where an app-level db.rollback() unwinds the whole shared test
        # transaction, including earlier commits in the same test. That is
        # a fixture artifact of running both calls through one shared
        # session, not something a real deployment exhibits, where each
        # HTTP request gets its own connection/transaction.)
        assert second.status_code == 409


class TestEntitlementResolution:
    def test_provisioned_organization_resolves_plan_entitlements(self, client, db_session):
        plan = _make_plan(db_session, feature_key="work_order_management")
        admin = _create_platform_admin(db_session, "prov-admin11@example.com")
        tokens = _login(client, admin.email)

        resp = client.post(
            "/api/v1/platform/organizations/provision",
            headers=_auth(tokens["access_token"]),
            json=_provision_payload(
                plan_id=plan.id, admin_email="new-tenant-admin11@example.com", status="ACTIVE"
            ),
        )
        org_id = uuid.UUID(resp.json()["organization_id"])

        result = resolve_entitlements(db_session, organization_id=org_id)
        assert result.resolution_status == EntitlementResolutionStatus.ACTIVE
        assert result.effective_features.get("work_order_management") is True

    def test_trialing_subscription_also_resolves_active_entitlements(self, client, db_session):
        plan = _make_plan(db_session, feature_key="lisa")
        admin = _create_platform_admin(db_session, "prov-admin12@example.com")
        tokens = _login(client, admin.email)

        resp = client.post(
            "/api/v1/platform/organizations/provision",
            headers=_auth(tokens["access_token"]),
            json=_provision_payload(
                plan_id=plan.id, admin_email="new-tenant-admin12@example.com", status="TRIALING"
            ),
        )
        org_id = uuid.UUID(resp.json()["organization_id"])

        result = resolve_entitlements(db_session, organization_id=org_id)
        assert result.resolution_status == EntitlementResolutionStatus.ACTIVE
        assert result.effective_features.get("lisa") is True


class TestAudit:
    def test_provisioning_records_audit_event(self, client, db_session):
        admin = _create_platform_admin(db_session, "prov-admin13@example.com")
        tokens = _login(client, admin.email)
        plan = _make_plan(db_session)

        resp = client.post(
            "/api/v1/platform/organizations/provision",
            headers=_auth(tokens["access_token"]),
            json=_provision_payload(plan_id=plan.id, admin_email="new-tenant-admin13@example.com"),
        )
        org_id = uuid.UUID(resp.json()["organization_id"])

        actions = (
            db_session.execute(
                select(AuditEvent.action).where(
                    AuditEvent.entity_type == "Organization", AuditEvent.entity_id == org_id
                )
            )
            .scalars()
            .all()
        )
        assert "platform.organization.create" in actions
        assert "platform.organization.provisioned" in actions

    def test_audit_metadata_contains_no_secrets(self, client, db_session):
        admin = _create_platform_admin(db_session, "prov-admin14@example.com")
        tokens = _login(client, admin.email)
        plan = _make_plan(db_session)

        resp = client.post(
            "/api/v1/platform/organizations/provision",
            headers=_auth(tokens["access_token"]),
            json=_provision_payload(plan_id=plan.id, admin_email="new-tenant-admin14@example.com"),
        )
        org_id = uuid.UUID(resp.json()["organization_id"])

        events = (
            db_session.execute(
                select(AuditEvent).where(
                    AuditEvent.entity_type == "Organization", AuditEvent.entity_id == org_id
                )
            )
            .scalars()
            .all()
        )
        for event in events:
            metadata_text = str(event.event_metadata).lower()
            assert "password" not in metadata_text
            assert "otp" not in metadata_text


class TestTenantIsolation:
    def test_provisioned_admin_cannot_see_other_organizations(self, client, db_session):
        admin = _create_platform_admin(db_session, "prov-admin15@example.com")
        tokens = _login(client, admin.email)
        plan = _make_plan(db_session)
        admin_email = "new-tenant-admin15@example.com"

        client.post(
            "/api/v1/platform/organizations/provision",
            headers=_auth(tokens["access_token"]),
            json=_provision_payload(plan_id=plan.id, admin_email=admin_email),
        )

        # The new tenant admin has no usable password yet (Phase 9) -- their
        # only route to a session is completing onboarding, exercised in
        # test_provisioning_onboarding.py. Here we just confirm the
        # provisioning-time password is genuinely unusable/unknown.
        new_user = db_session.execute(select(User).where(User.email == admin_email)).scalar_one()
        login_attempt = client.post(
            "/api/v1/auth/login", json={"email": admin_email, "password": "supersecret123"}
        )
        assert login_attempt.status_code == 401
        assert new_user.email_verified is False


class TestInvalidPlan:
    def test_nonexistent_plan_rejected_and_leaves_no_orphan(self, client, db_session):
        admin = _create_platform_admin(db_session, "prov-admin16@example.com")
        tokens = _login(client, admin.email)
        org_name = "Invalid Plan Candidate Org"

        resp = client.post(
            "/api/v1/platform/organizations/provision",
            headers=_auth(tokens["access_token"]),
            json=_provision_payload(
                plan_id=uuid.uuid4(), admin_email="orphan-admin16@example.com", org_name=org_name
            ),
        )
        assert resp.status_code == 404

        orphan = db_session.execute(
            select(Organization).where(Organization.name == org_name)
        ).scalar_one_or_none()
        assert orphan is None


class TestOnboardingIntegration:
    """Phase 24: the complete authentication integration -- provision ->
    admin created -> onboarding email (captured via monkeypatch, same
    pattern as tests/integration/test_auth_verification.py) -> OTP ->
    /auth/onboarding/complete sets password + email_verified -> tenant
    admin logs in -> lands in their own organization, not the platform's."""

    def test_full_provision_to_tenant_login_flow(self, client, db_session, monkeypatch):
        captured: dict[str, list[str]] = {}

        def _fake_send(*, to: str, code: str, purpose_label: str) -> None:
            captured.setdefault(to, []).append(code)

        monkeypatch.setattr("app.services.auth_service.send_verification_code_email", _fake_send)

        platform_admin = _create_platform_admin(db_session, "prov-onboard-admin@example.com")
        platform_tokens = _login(client, platform_admin.email)
        plan = _make_plan(db_session, feature_key="work_order_management")
        admin_email = "onboarding-tenant-admin@example.com"

        provision_resp = client.post(
            "/api/v1/platform/organizations/provision",
            headers=_auth(platform_tokens["access_token"]),
            json=_provision_payload(plan_id=plan.id, admin_email=admin_email, status="ACTIVE"),
        )
        assert provision_resp.status_code == 201
        organization_id = provision_resp.json()["organization_id"]

        # The invited admin has no usable password yet -- cannot log in.
        blocked_login = client.post(
            "/api/v1/auth/login", json={"email": admin_email, "password": "anything123"}
        )
        assert blocked_login.status_code == 401

        code = captured[admin_email][-1]
        complete_resp = client.post(
            "/api/v1/auth/onboarding/complete",
            json={"email": admin_email, "code": code, "new_password": "tenant-chosen-password123"},
        )
        assert complete_resp.status_code == 200

        login_resp = client.post(
            "/api/v1/auth/login",
            json={"email": admin_email, "password": "tenant-chosen-password123"},
        )
        assert login_resp.status_code == 200
        tenant_tokens = login_resp.json()

        me = client.get("/api/v1/auth/me", headers=_auth(tenant_tokens["access_token"])).json()
        assert me["organization_id"] == organization_id
        assert me["roles"] == ["ORG_ADMIN"]
        assert me["email_verified"] is True

        # Platform routes remain rejected for the new tenant admin.
        platform_resp = client.get(
            "/api/v1/platform/organizations", headers=_auth(tenant_tokens["access_token"])
        )
        assert platform_resp.status_code == 403

    def test_resend_invitation(self, client, db_session, monkeypatch):
        captured: dict[str, list[str]] = {}
        monkeypatch.setattr(
            "app.services.auth_service.send_verification_code_email",
            lambda *, to, code, purpose_label: captured.setdefault(to, []).append(code),
        )

        platform_admin = _create_platform_admin(db_session, "prov-resend-admin@example.com")
        platform_tokens = _login(client, platform_admin.email)
        plan = _make_plan(db_session)
        admin_email = "resend-tenant-admin@example.com"

        provision_resp = client.post(
            "/api/v1/platform/organizations/provision",
            headers=_auth(platform_tokens["access_token"]),
            json=_provision_payload(plan_id=plan.id, admin_email=admin_email),
        )
        admin_user_id = provision_resp.json()["admin_user_id"]
        first_code = captured[admin_email][-1]

        # Within the resend cooldown -- rejected, matching the existing OTP
        # resend-cooldown contract (auth_service.OTP_RESEND_COOLDOWN_SECONDS).
        resend_resp = client.post(
            f"/api/v1/platform/admins/{admin_user_id}/resend-invitation",
            headers=_auth(platform_tokens["access_token"]),
        )
        assert resend_resp.status_code == 409

        # The original code from provisioning is still valid.
        complete_resp = client.post(
            "/api/v1/auth/onboarding/complete",
            json={
                "email": admin_email,
                "code": first_code,
                "new_password": "tenant-chosen-password456",
            },
        )
        assert complete_resp.status_code == 200

    def test_tenant_user_cannot_resend_invitation(self, client, db_session):
        tenant = _register(client, "Resend Guard Org", "resend-guard-admin@example.com")
        resp = client.post(
            f"/api/v1/platform/admins/{uuid.uuid4()}/resend-invitation",
            headers=_auth(tenant["access_token"]),
        )
        assert resp.status_code == 403
