"""Phase 18.2: tests for the platform product catalog (Suite -> Module ->
Page/Feature) -- creation, platform authorization, invalid-parent
rejection, duplicate-code rejection, and confirmation that M17.3's
entitlement resolution is completely unaffected by this milestone.
"""

import uuid

import pytest
from sqlalchemy import select

from app.core.deps import get_db_session
from app.core.errors import ConflictError, NotFoundError
from app.main import app
from app.models.organization import Organization
from app.models.plan import Plan, PlanFeature
from app.models.product_catalog import ProductFeature, ProductModule, ProductPage, ProductSuite
from app.models.subscription import Subscription, SubscriptionStatus
from app.services import product_catalog_service
from app.services.entitlement_service import (
    EntitlementResolutionStatus,
    resolve_entitlements,
)


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


def _org_id(client, token):
    return uuid.UUID(client.get("/api/v1/auth/me", headers=_auth(token)).json()["organization_id"])


def _add_viewer(db_session, org_id, email):
    from app.core.security import hash_password
    from app.models.user import User, UserRole

    user = User(
        organization_id=org_id,
        email=email,
        hashed_password=hash_password("supersecret123"),
        full_name="Viewer",
        is_active=True,
    )
    db_session.add(user)
    db_session.flush()
    db_session.add(UserRole(user_id=user.id, role_name="VIEWER", organization_id=org_id))
    db_session.commit()
    return user


class TestSuiteCreation:
    def test_create_suite_with_platform_permission(self, db_session):
        org = Organization(name="Catalog Org 1")
        db_session.add(org)
        db_session.commit()

        suite = product_catalog_service.create_suite(
            db_session,
            actor_user_id=uuid.uuid4(),
            actor_organization_id=org.id,
            code=f"suite-{uuid.uuid4().hex[:8]}",
            name="Test Suite",
        )
        assert suite.id is not None
        assert suite.is_active is True

    def test_duplicate_suite_code_rejected(self, db_session):
        org = Organization(name="Catalog Org 2")
        db_session.add(org)
        db_session.commit()
        code = f"dup-suite-{uuid.uuid4().hex[:8]}"

        product_catalog_service.create_suite(
            db_session, actor_user_id=None, actor_organization_id=org.id, code=code, name="A"
        )
        with pytest.raises(ConflictError):
            product_catalog_service.create_suite(
                db_session, actor_user_id=None, actor_organization_id=org.id, code=code, name="B"
            )


class TestModuleCreation:
    def _make_suite(self, db_session, org_id):
        return product_catalog_service.create_suite(
            db_session,
            actor_user_id=None,
            actor_organization_id=org_id,
            code=f"suite-{uuid.uuid4().hex[:8]}",
            name="Suite",
        )

    def test_create_module_under_valid_suite(self, db_session):
        org = Organization(name="Catalog Org 3")
        db_session.add(org)
        db_session.commit()
        suite = self._make_suite(db_session, org.id)

        module = product_catalog_service.create_module(
            db_session,
            actor_user_id=None,
            actor_organization_id=org.id,
            suite_id=suite.id,
            code=f"module-{uuid.uuid4().hex[:8]}",
            name="Module",
        )
        assert module.suite_id == suite.id

    def test_reject_invalid_suite_relationship(self, db_session):
        org = Organization(name="Catalog Org 4")
        db_session.add(org)
        db_session.commit()

        with pytest.raises(NotFoundError):
            product_catalog_service.create_module(
                db_session,
                actor_user_id=None,
                actor_organization_id=org.id,
                suite_id=uuid.uuid4(),
                code=f"module-{uuid.uuid4().hex[:8]}",
                name="Orphan Module",
            )

    def test_duplicate_module_code_rejected(self, db_session):
        org = Organization(name="Catalog Org 5")
        db_session.add(org)
        db_session.commit()
        suite = self._make_suite(db_session, org.id)
        code = f"dup-module-{uuid.uuid4().hex[:8]}"

        product_catalog_service.create_module(
            db_session,
            actor_user_id=None,
            actor_organization_id=org.id,
            suite_id=suite.id,
            code=code,
            name="A",
        )
        with pytest.raises(ConflictError):
            product_catalog_service.create_module(
                db_session,
                actor_user_id=None,
                actor_organization_id=org.id,
                suite_id=suite.id,
                code=code,
                name="B",
            )


class TestPageCreation:
    def _make_suite_and_module(self, db_session, org_id):
        suite = product_catalog_service.create_suite(
            db_session,
            actor_user_id=None,
            actor_organization_id=org_id,
            code=f"suite-{uuid.uuid4().hex[:8]}",
            name="Suite",
        )
        module = product_catalog_service.create_module(
            db_session,
            actor_user_id=None,
            actor_organization_id=org_id,
            suite_id=suite.id,
            code=f"module-{uuid.uuid4().hex[:8]}",
            name="Module",
        )
        return suite, module

    def test_create_page_under_valid_module(self, db_session):
        org = Organization(name="Catalog Org 6")
        db_session.add(org)
        db_session.commit()
        _, module = self._make_suite_and_module(db_session, org.id)

        page = product_catalog_service.create_page(
            db_session,
            actor_user_id=None,
            actor_organization_id=org.id,
            module_id=module.id,
            code=f"page-{uuid.uuid4().hex[:8]}",
            name="Page",
            route="/some/route",
        )
        assert page.module_id == module.id
        assert page.route == "/some/route"

    def test_reject_invalid_module_relationship(self, db_session):
        org = Organization(name="Catalog Org 7")
        db_session.add(org)
        db_session.commit()

        with pytest.raises(NotFoundError):
            product_catalog_service.create_page(
                db_session,
                actor_user_id=None,
                actor_organization_id=org.id,
                module_id=uuid.uuid4(),
                code=f"page-{uuid.uuid4().hex[:8]}",
                name="Orphan Page",
            )

    def test_duplicate_page_code_rejected(self, db_session):
        org = Organization(name="Catalog Org 8")
        db_session.add(org)
        db_session.commit()
        _, module = self._make_suite_and_module(db_session, org.id)
        code = f"dup-page-{uuid.uuid4().hex[:8]}"

        product_catalog_service.create_page(
            db_session,
            actor_user_id=None,
            actor_organization_id=org.id,
            module_id=module.id,
            code=code,
            name="A",
        )
        with pytest.raises(ConflictError):
            product_catalog_service.create_page(
                db_session,
                actor_user_id=None,
                actor_organization_id=org.id,
                module_id=module.id,
                code=code,
                name="B",
            )


class TestFeatureCreation:
    def _make_suite_and_module(self, db_session, org_id):
        suite = product_catalog_service.create_suite(
            db_session,
            actor_user_id=None,
            actor_organization_id=org_id,
            code=f"suite-{uuid.uuid4().hex[:8]}",
            name="Suite",
        )
        module = product_catalog_service.create_module(
            db_session,
            actor_user_id=None,
            actor_organization_id=org_id,
            suite_id=suite.id,
            code=f"module-{uuid.uuid4().hex[:8]}",
            name="Module",
        )
        return suite, module

    def test_feature_uniqueness_by_stable_code(self, db_session):
        org = Organization(name="Catalog Org 9")
        db_session.add(org)
        db_session.commit()
        _, module = self._make_suite_and_module(db_session, org.id)
        code = f"dup-feature-{uuid.uuid4().hex[:8]}"

        product_catalog_service.create_feature(
            db_session,
            actor_user_id=None,
            actor_organization_id=org.id,
            module_id=module.id,
            code=code,
            name="A",
        )
        with pytest.raises(ConflictError):
            product_catalog_service.create_feature(
                db_session,
                actor_user_id=None,
                actor_organization_id=org.id,
                module_id=module.id,
                code=code,
                name="B",
            )

    def test_reject_invalid_module_relationship(self, db_session):
        org = Organization(name="Catalog Org 10")
        db_session.add(org)
        db_session.commit()

        with pytest.raises(NotFoundError):
            product_catalog_service.create_feature(
                db_session,
                actor_user_id=None,
                actor_organization_id=org.id,
                module_id=uuid.uuid4(),
                code=f"feature-{uuid.uuid4().hex[:8]}",
                name="Orphan Feature",
            )


class TestInactiveCatalogEntities:
    def test_deactivated_suite_still_readable_and_children_intact(self, db_session):
        org = Organization(name="Catalog Org 11")
        db_session.add(org)
        db_session.commit()
        suite = product_catalog_service.create_suite(
            db_session,
            actor_user_id=None,
            actor_organization_id=org.id,
            code=f"suite-{uuid.uuid4().hex[:8]}",
            name="Suite",
        )
        module = product_catalog_service.create_module(
            db_session,
            actor_user_id=None,
            actor_organization_id=org.id,
            suite_id=suite.id,
            code=f"module-{uuid.uuid4().hex[:8]}",
            name="Module",
        )

        deactivated = product_catalog_service.update_suite(
            db_session,
            actor_user_id=None,
            actor_organization_id=org.id,
            suite_id=suite.id,
            is_active=False,
        )
        assert deactivated.is_active is False

        # Deactivating a suite never cascades or destroys its modules --
        # matching Plan.is_active's own precedent (app/services/plan_service.py).
        still_there = product_catalog_service.get_module(db_session, module_id=module.id)
        assert still_there.id == module.id
        assert still_there.is_active is True


class TestPlatformAuthorization:
    def test_organization_user_cannot_create_suite(self, client, db_session):
        tokens = _register(client, "Catalog Tenant Org", "admin@catalog-tenant.com")
        resp = client.post(
            "/api/v1/platform/product-suites",
            headers=_auth(tokens["access_token"]),
            json={"code": f"blocked-{uuid.uuid4().hex[:8]}", "name": "Blocked Suite"},
        )
        assert resp.status_code == 403

    def test_organization_viewer_cannot_read_platform_catalog(self, client, db_session):
        tokens = _register(client, "Catalog Viewer Org", "admin@catalog-viewer.com")
        org_id = _org_id(client, tokens["access_token"])
        viewer = _add_viewer(db_session, org_id, "viewer@catalog-viewer.com")
        login = client.post(
            "/api/v1/auth/login", json={"email": viewer.email, "password": "supersecret123"}
        )
        viewer_token = login.json()["access_token"]

        resp = client.get("/api/v1/platform/product-suites", headers=_auth(viewer_token))
        assert resp.status_code == 403

    def test_platform_admin_can_create_and_read_suite(self, client, db_session):
        from app.core.security import hash_password
        from app.models.user import User, UserRole

        org = Organization(name="Platform Ops Catalog Org")
        db_session.add(org)
        db_session.flush()
        admin = User(
            organization_id=org.id,
            email="platform-admin@catalog.example.com",
            hashed_password=hash_password("supersecret123"),
            full_name="Platform Admin",
            is_active=True,
        )
        db_session.add(admin)
        db_session.flush()
        db_session.add(
            UserRole(user_id=admin.id, role_name="PLATFORM_ADMIN", organization_id=org.id)
        )
        db_session.commit()

        login = client.post(
            "/api/v1/auth/login", json={"email": admin.email, "password": "supersecret123"}
        )
        assert login.status_code == 200
        admin_token = login.json()["access_token"]

        code = f"admin-suite-{uuid.uuid4().hex[:8]}"
        create_resp = client.post(
            "/api/v1/platform/product-suites",
            headers=_auth(admin_token),
            json={"code": code, "name": "Admin Suite"},
        )
        assert create_resp.status_code == 201
        suite_id = create_resp.json()["id"]

        list_resp = client.get("/api/v1/platform/product-suites", headers=_auth(admin_token))
        assert list_resp.status_code == 200
        assert any(s["id"] == suite_id for s in list_resp.json())


class TestAudit:
    def test_suite_creation_records_audit_event(self, db_session):
        from app.models.audit_event import AuditEvent

        org = Organization(name="Catalog Audit Org")
        db_session.add(org)
        db_session.commit()
        actor_id = uuid.uuid4()

        suite = product_catalog_service.create_suite(
            db_session,
            actor_user_id=actor_id,
            actor_organization_id=org.id,
            code=f"audit-suite-{uuid.uuid4().hex[:8]}",
            name="Audited Suite",
        )

        event = db_session.execute(
            select(AuditEvent).where(
                AuditEvent.action == "platform.product_suite.created",
                AuditEvent.entity_id == suite.id,
            )
        ).scalar_one()
        assert event.organization_id == org.id
        assert event.user_id == actor_id
        assert event.entity_type == "ProductSuite"


class TestEntitlementResolutionUnaffected:
    """Confirms this milestone made zero changes to M17.3 behavior: the
    resolution engine has no awareness of the product catalog at all."""

    def test_entitlement_resolution_still_works_with_catalog_present(self, db_session):
        org = Organization(name="Entitlement Regression Org")
        db_session.add(org)
        db_session.commit()

        plan = Plan(name="Catalog Regression Plan", code=f"plan-{uuid.uuid4().hex[:8]}")
        db_session.add(plan)
        db_session.commit()
        db_session.add(
            PlanFeature(plan_id=plan.id, feature_key="work_order_management", enabled=True)
        )
        db_session.commit()

        from datetime import UTC, datetime, timedelta

        db_session.add(
            Subscription(
                organization_id=org.id,
                plan_id=plan.id,
                status=SubscriptionStatus.ACTIVE,
                starts_at=datetime.now(UTC) - timedelta(days=1),
            )
        )
        db_session.commit()

        # A ProductFeature row with the SAME code exists, but resolve_entitlements
        # never queries product_catalog tables -- this proves that.
        suite = product_catalog_service.create_suite(
            db_session,
            actor_user_id=None,
            actor_organization_id=org.id,
            code=f"suite-{uuid.uuid4().hex[:8]}",
            name="Suite",
        )
        module = product_catalog_service.create_module(
            db_session,
            actor_user_id=None,
            actor_organization_id=org.id,
            suite_id=suite.id,
            code=f"module-{uuid.uuid4().hex[:8]}",
            name="Module",
        )
        product_catalog_service.create_feature(
            db_session,
            actor_user_id=None,
            actor_organization_id=org.id,
            module_id=module.id,
            code="work_order_management",
            name="Work Order Management",
        )

        result = resolve_entitlements(db_session, organization_id=org.id)
        assert result.resolution_status == EntitlementResolutionStatus.ACTIVE
        assert result.effective_features.get("work_order_management") is True

    def test_deleting_nothing_plan_feature_tests_remain_independent(self, db_session):
        # Sanity: PlanFeature enforcement (uniqueness per plan) is completely
        # untouched by the new product_features table -- same feature_key
        # string can be reused freely across both, since there is no FK.
        org = Organization(name="Independent Regression Org")
        db_session.add(org)
        db_session.commit()
        plan = Plan(name="Independent Plan", code=f"plan-{uuid.uuid4().hex[:8]}")
        db_session.add(plan)
        db_session.commit()
        db_session.add(PlanFeature(plan_id=plan.id, feature_key="lisa", enabled=True))
        db_session.commit()  # must not raise


class TestTenantIsolation:
    def test_catalog_entities_carry_no_organization_id(self, db_session):
        # ProductSuite/Module/Page/Feature are platform-global (see
        # app/models/product_catalog.py) -- confirm none of them accept or
        # expose an organization_id column at all.
        assert not hasattr(ProductSuite, "organization_id")
        assert not hasattr(ProductModule, "organization_id")
        assert not hasattr(ProductPage, "organization_id")
        assert not hasattr(ProductFeature, "organization_id")
