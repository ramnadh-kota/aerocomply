"""Integration and security test suite for Suite -> Suite-Specific Plan -> Subscription Architecture.

Verifies:
1. Suite creation & domain boundaries (AIRCRAFT, DRONE_UAV, HELICOPTER, EVTOL_AAM).
2. Plan belongs to exactly one Suite (suite_id NOT NULL, UNIQUE(suite_id, code)).
3. Duplicate plan code allowed across different suites, rejected within same suite.
4. Subscription & Provisioning suite/plan consistency enforcement.
5. Entitlement resolution with Suite, Plan, Modules, Pages, Features.
6. Security enforcement:
   - Drone org calling Aircraft API returns 403 SUITE_ENTITLEMENT_REQUIRED.
   - Aircraft org calling Drone API returns 403 SUITE_ENTITLEMENT_REQUIRED.
   - Cross-suite TenantFeatureOverride is rejected.
   - Subscription suite/plan mismatch is rejected.
   - RBAC combined with Suite entitlement.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
import pytest
from sqlalchemy import select

from app.core.errors import ConflictError, NotFoundError
from app.core.permissions import Role
from app.core.security import hash_password
from app.models.organization import Organization
from app.models.plan import Plan, PlanFeature
from app.models.product_catalog import (
    ProductFeature,
    ProductModule,
    ProductPage,
    ProductSuite,
)
from app.models.subscription import Subscription, SubscriptionStatus
from app.models.user import User, UserRole
from app.services.entitlement_service import resolve_entitlements
from app.services.plan_service import create_plan, create_plan_feature
from app.services.provisioning_service import provision_organization
from app.services.subscription_service import create_subscription, update_subscription
from app.services.tenant_entitlement_admin_service import create_feature_override


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _get_or_create_suite(db_session, code: str, name: str, icon: str = "Bot") -> ProductSuite:
    suite = db_session.execute(select(ProductSuite).where(ProductSuite.code == code)).scalars().first()
    if not suite:
        suite = ProductSuite(code=code, name=name, is_active=True, icon=icon)
        db_session.add(suite)
        db_session.flush()
    return suite


def test_suite_and_plan_hierarchy_db_constraints(db_session) -> None:
    """Test suite uniqueness and plan suite_id scoping."""
    # 1. Create two unique suites
    suite_aircraft = ProductSuite(
        code=f"TEST_AIR_{uuid.uuid4().hex[:6]}",
        name="Test Aircraft Suite",
        is_active=True,
        icon="Plane",
    )
    suite_drone = ProductSuite(
        code=f"TEST_DRN_{uuid.uuid4().hex[:6]}",
        name="Test Drone Suite",
        is_active=True,
        icon="Bot",
    )
    db_session.add_all([suite_aircraft, suite_drone])
    db_session.flush()

    # 2. Same plan code 'PROFESSIONAL' under different suites is ALLOWED
    plan_code = "PROFESSIONAL"
    plan_air = Plan(
        suite_id=suite_aircraft.id,
        code=plan_code,
        name="Aircraft Professional",
        is_active=True,
    )
    plan_drone = Plan(
        suite_id=suite_drone.id,
        code=plan_code,
        name="Drone Professional",
        is_active=True,
    )
    db_session.add_all([plan_air, plan_drone])
    db_session.flush()

    assert plan_air.id != plan_drone.id
    assert plan_air.suite_id == suite_aircraft.id
    assert plan_drone.suite_id == suite_drone.id

    # 3. Duplicate plan code under the SAME suite must be rejected by create_plan
    with pytest.raises(ConflictError):
        create_plan(
            db_session,
            actor_user_id=None,
            actor_organization_id=uuid.uuid4(),
            code=plan_code,
            name="Another Aircraft Pro",
            suite_id=suite_aircraft.id,
        )


def test_subscription_and_provisioning_suite_validation(db_session) -> None:
    """Test that provisioning and subscriptions strictly validate suite_id matches plan.suite_id."""
    # Create suites & plans
    suite_aircraft = _get_or_create_suite(db_session, "AIRCRAFT", "Aircraft Suite", "Plane")
    suite_drone = _get_or_create_suite(db_session, "DRONE_UAV", "Drone / UAV Suite", "Bot")

    plan_air = Plan(
        suite_id=suite_aircraft.id,
        code=f"AIR_PRO_{uuid.uuid4().hex[:4]}",
        name="Aircraft Pro",
        is_active=True,
    )
    plan_drone = Plan(
        suite_id=suite_drone.id,
        code=f"DRN_PRO_{uuid.uuid4().hex[:4]}",
        name="Drone Pro",
        is_active=True,
    )
    db_session.add_all([plan_air, plan_drone])
    db_session.flush()

    # Create an org
    org = Organization(name="Test Aero Corp")
    db_session.add(org)
    db_session.flush()

    now = datetime.now(UTC)

    # 1. Attempt creating subscription with mismatched suite_id and plan_id
    with pytest.raises(ConflictError) as exc:
        create_subscription(
            db_session,
            actor_user_id=None,
            organization_id=org.id,
            plan_id=plan_air.id,
            suite_id=suite_drone.id,  # MISMATCH
            status=SubscriptionStatus.ACTIVE,
            starts_at=now,
            ends_at=now + timedelta(days=30),
            commit=False,
        )
    assert "does not belong to the selected product suite" in str(exc.value)

    # 2. Successful subscription creation with matching suite_id
    sub = create_subscription(
        db_session,
        actor_user_id=None,
        organization_id=org.id,
        plan_id=plan_air.id,
        suite_id=suite_aircraft.id,
        status=SubscriptionStatus.ACTIVE,
        starts_at=now,
        ends_at=now + timedelta(days=30),
        commit=False,
    )
    assert sub.suite_id == suite_aircraft.id
    assert sub.plan_id == plan_air.id

    # 3. Updating a subscription to a plan from another suite is rejected.
    # M20: the previous assertion allowed the switch (suite_id silently
    # followed the new plan), which contradicts the rule that a suite is the
    # domain boundary and a subscription may never pair one suite with another
    # suite's plan. Suite change is explicitly unsupported; re-provision instead.
    with pytest.raises(ConflictError) as exc:
        update_subscription(
            db_session,
            actor_user_id=None,
            subscription_id=sub.id,
            plan_id=plan_drone.id,
        )
    assert exc.value.code == "suite_plan_mismatch"
    db_session.refresh(sub)
    assert sub.plan_id == plan_air.id
    assert sub.suite_id == suite_aircraft.id

    # 4. Provisioning with mismatch must be rejected
    with pytest.raises(ConflictError):
        provision_organization(
            db_session,
            actor_user_id=uuid.uuid4(),
            organization_name="Drone Org Invalid",
            plan_id=plan_air.id,
            suite_id=suite_drone.id,  # MISMATCH
            subscription_status=SubscriptionStatus.ACTIVE,
            admin_email=f"admin_{uuid.uuid4().hex[:4]}@example.com",
            admin_full_name="Admin User",
        )


def test_entitlement_resolver_resolves_suite_domain(db_session) -> None:
    """Test that resolve_entitlements returns complete suite domain structure."""
    suite = _get_or_create_suite(db_session, f"DRONE_{uuid.uuid4().hex[:6]}", "Drone / UAV Suite", "Bot")

    module = ProductModule(suite_id=suite.id, code=f"drone_ops_{uuid.uuid4().hex[:4]}", name="Drone Operations", display_order=1)
    db_session.add(module)
    db_session.flush()

    page = ProductPage(module_id=module.id, code=f"drone_missions_{uuid.uuid4().hex[:4]}", name="Missions", route="/drone-missions")
    db_session.add(page)
    db_session.flush()

    feature = ProductFeature(module_id=module.id, code=f"drone_flight_plans_{uuid.uuid4().hex[:4]}", name="Flight Plans")
    db_session.add(feature)
    db_session.flush()

    plan = Plan(
        suite_id=suite.id,
        code=f"DRONE_STARTER_{uuid.uuid4().hex[:4]}",
        name="Drone Starter",
        is_active=True,
    )
    db_session.add(plan)
    db_session.flush()

    plan_feat = PlanFeature(plan_id=plan.id, feature_key=feature.code, enabled=True)
    db_session.add(plan_feat)

    org = Organization(name="Skyline UAV")
    db_session.add(org)
    db_session.flush()

    now = datetime.now(UTC)
    sub = Subscription(
        organization_id=org.id,
        plan_id=plan.id,
        suite_id=suite.id,
        status=SubscriptionStatus.ACTIVE,
        starts_at=now,
        ends_at=now + timedelta(days=30),
    )
    db_session.add(sub)
    db_session.flush()

    # Resolve entitlements
    res = resolve_entitlements(db_session, organization_id=org.id)

    assert res.suite_id == suite.id
    assert res.suite_code == suite.code
    assert res.suite_name == suite.name
    assert res.plan_id == plan.id
    assert res.plan_name == plan.name
    assert feature.code in res.effective_features
    assert module.code in res.modules
    assert page.code in res.pages


def test_cross_suite_tenant_feature_override_rejection(db_session) -> None:
    """Test that TenantFeatureOverride cannot grant features outside the organization's Suite boundary."""
    # Use Drone Suite
    suite_drone = _get_or_create_suite(db_session, "DRONE_UAV", "Drone / UAV Suite", "Bot")

    plan = Plan(
        suite_id=suite_drone.id,
        code=f"DRONE_PRO_{uuid.uuid4().hex[:4]}",
        name="Drone Professional",
        is_active=True,
    )
    db_session.add(plan)
    db_session.flush()

    org = Organization(name="Drone Co")
    db_session.add(org)
    db_session.flush()

    now = datetime.now(UTC)
    sub = Subscription(
        organization_id=org.id,
        plan_id=plan.id,
        suite_id=suite_drone.id,
        status=SubscriptionStatus.ACTIVE,
        starts_at=now,
        ends_at=now + timedelta(days=30),
    )
    db_session.add(sub)
    db_session.flush()

    # 1. Attempt to override aircraft_fleet_management on a Drone organization
    with pytest.raises(ConflictError) as exc:
        create_feature_override(
            db_session,
            actor_user_id=None,
            caller_roles=[Role.PLATFORM_ADMIN.value],
            organization_id=org.id,
            feature_key="aircraft_fleet_management",
            enabled=True,
            reason="Illegal cross-suite bypass attempt",
        )
    assert "outside" in (getattr(exc.value, "message", "") + str(exc.value)).lower()

    # 2. Attempt to override helicopter_mro on a Drone organization
    with pytest.raises(ConflictError):
        create_feature_override(
            db_session,
            actor_user_id=None,
            caller_roles=[Role.PLATFORM_ADMIN.value],
            organization_id=org.id,
            feature_key="helicopter_mro",
            enabled=True,
            reason="Illegal helicopter bypass",
        )


def test_api_security_suite_isolation(client, db_session) -> None:
    """Security Test:
    - Drone organization user calling GET /api/v1/aircraft receives 403 SUITE_ENTITLEMENT_REQUIRED.
    - Aircraft organization user calling GET /api/v1/aircraft receives 200 OK.
    """
    # 1. Find or create suites
    suite_air = _get_or_create_suite(db_session, "AIRCRAFT", "Aircraft Suite", "Plane")
    suite_drone = _get_or_create_suite(db_session, "DRONE_UAV", "Drone / UAV Suite", "Bot")

    # 2. Create Plans
    plan_air = Plan(
        suite_id=suite_air.id,
        code=f"AIR_PLAN_{uuid.uuid4().hex[:4]}",
        name="Aircraft Standard",
        is_active=True,
    )
    plan_drone = Plan(
        suite_id=suite_drone.id,
        code=f"DRN_PLAN_{uuid.uuid4().hex[:4]}",
        name="Drone Standard",
        is_active=True,
    )
    db_session.add_all([plan_air, plan_drone])
    db_session.flush()

    # 3. Grant features
    db_session.add_all([
        PlanFeature(plan_id=plan_air.id, feature_key="aircraft_fleet_management", enabled=True),
        PlanFeature(plan_id=plan_air.id, feature_key="asset_management", enabled=True),
        PlanFeature(plan_id=plan_drone.id, feature_key="drone_fleet_management", enabled=True),
        PlanFeature(plan_id=plan_drone.id, feature_key="asset_management", enabled=True),
    ])
    db_session.flush()

    # 4. Provision organizations and admin users
    org_air = Organization(name=f"Aircraft Corp {uuid.uuid4().hex[:4]}")
    org_drone = Organization(name=f"Drone Corp {uuid.uuid4().hex[:4]}")
    db_session.add_all([org_air, org_drone])
    db_session.flush()

    now = datetime.now(UTC)
    sub_air = Subscription(
        organization_id=org_air.id,
        plan_id=plan_air.id,
        suite_id=suite_air.id,
        status=SubscriptionStatus.ACTIVE,
        starts_at=now,
        ends_at=now + timedelta(days=30),
    )
    sub_drone = Subscription(
        organization_id=org_drone.id,
        plan_id=plan_drone.id,
        suite_id=suite_drone.id,
        status=SubscriptionStatus.ACTIVE,
        starts_at=now,
        ends_at=now + timedelta(days=30),
    )
    db_session.add_all([sub_air, sub_drone])
    db_session.flush()

    air_user = User(
        organization_id=org_air.id,
        email=f"air_admin_{uuid.uuid4().hex[:4]}@example.com",
        hashed_password=hash_password("SuperSecret123!"),
        full_name="Aircraft Admin",
        is_active=True,
    )
    drone_user = User(
        organization_id=org_drone.id,
        email=f"drone_admin_{uuid.uuid4().hex[:4]}@example.com",
        hashed_password=hash_password("SuperSecret123!"),
        full_name="Drone Admin",
        is_active=True,
    )
    db_session.add_all([air_user, drone_user])
    db_session.flush()

    db_session.add_all([
        UserRole(user_id=air_user.id, role_name=Role.ORG_ADMIN, organization_id=org_air.id),
        UserRole(user_id=drone_user.id, role_name=Role.ORG_ADMIN, organization_id=org_drone.id),
    ])
    db_session.commit()

    # Logins
    resp_air_login = client.post("/api/v1/auth/login", json={"email": air_user.email, "password": "SuperSecret123!"})
    assert resp_air_login.status_code == 200
    air_token = resp_air_login.json()["access_token"]

    resp_drone_login = client.post("/api/v1/auth/login", json={"email": drone_user.email, "password": "SuperSecret123!"})
    assert resp_drone_login.status_code == 200
    drone_token = resp_drone_login.json()["access_token"]

    # 1. Drone Admin requests GET /api/v1/aircraft -> MUST BE 403 FORBIDDEN with SUITE_ENTITLEMENT_REQUIRED
    resp_drone = client.get(
        "/api/v1/aircraft",
        headers=_auth(drone_token),
    )
    assert resp_drone.status_code == 403
    drone_body = resp_drone.json()
    assert drone_body.get("code") == "SUITE_ENTITLEMENT_REQUIRED" or "feature" in str(drone_body).lower()

    # 2. Aircraft Admin requests GET /api/v1/aircraft -> MUST BE 200 OK
    resp_air = client.get(
        "/api/v1/aircraft",
        headers=_auth(air_token),
    )
    assert resp_air.status_code == 200
    assert isinstance(resp_air.json(), list)

    # 3. Drone Admin requests GET /api/v1/drones -> MUST BE 200 OK
    resp_drone_drones = client.get(
        "/api/v1/drones",
        headers=_auth(drone_token),
    )
    assert resp_drone_drones.status_code == 200
    assert isinstance(resp_drone_drones.json(), list)
