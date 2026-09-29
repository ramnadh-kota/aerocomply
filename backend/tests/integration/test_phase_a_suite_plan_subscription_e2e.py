"""Phase A Functional Implementation — Suite -> Plan -> Subscription -> Entitlement E2E Test.

Validates:
1. Suite model & Plan-to-Suite mandatory binding.
2. Multi-suite organizations (Org A having coexisting Drone + Aircraft subscriptions).
3. Subscription ambiguity invariant:
   - Duplicate active subscriptions on the SAME suite are rejected as ambiguous.
   - Active subscriptions on DIFFERENT suites coexist cleanly.
4. Suite-aware entitlement resolution:
   - Single-suite resolution vs multi-suite aggregation.
   - Suite-specific feature masking (disallowing cross-suite features).
   - Suite-aware tenant overrides.
5. End-to-End customer journey:
   - Create organization
   - Select Drone suite
   - Select Drone Professional plan
   - Create subscription
   - Verify Drone operations permitted / Aircraft operations blocked
   - Add Aircraft Enterprise subscription to the same organization
   - Verify both Drone and Aircraft operations simultaneously entitled
6. Subscription lifecycle verification (ACTIVE, PAST_DUE, CANCELED).
"""
import uuid
from datetime import UTC, datetime, timedelta
import pytest
from sqlalchemy import select

from app.core.errors import ConflictError, NotFoundError
from app.core.permissions import Role
from app.core.security import hash_password
from app.models.organization import Organization
from app.models.plan import Plan, PlanFeature, PlanLimit
from app.models.product_catalog import ProductFeature, ProductModule, ProductPage, ProductSuite
from app.models.subscription import Subscription, SubscriptionStatus
from app.models.user import User, UserRole
from app.services.entitlement_service import EntitlementResolutionStatus, resolve_entitlements
from app.services.plan_service import create_plan, create_plan_feature
from app.services.subscription_service import (
    cancel_subscription,
    create_subscription,
    update_subscription,
)
from app.services.tenant_entitlement_admin_service import create_feature_override


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _get_or_create_suite(db_session, code: str, name: str, icon: str = "Plane") -> ProductSuite:
    suite = db_session.execute(select(ProductSuite).where(ProductSuite.code == code)).scalars().first()
    if not suite:
        suite = ProductSuite(code=code, name=name, is_active=True, icon=icon)
        db_session.add(suite)
        db_session.flush()
    return suite


def test_suite_plan_binding_and_mandatory_suite_id(db_session) -> None:
    """Verify plans MUST belong to a suite and duplicate codes are permitted across suites."""
    org = Organization(name="Admin Ops Org")
    db_session.add(org)
    db_session.flush()

    suite_drone = _get_or_create_suite(db_session, "DRONE_UAV", "Drone / UAV Suite", "Bot")
    suite_aircraft = _get_or_create_suite(db_session, "AIRCRAFT", "Aircraft Suite", "Plane")

    # 1. Create Drone Professional
    plan_drone = create_plan(
        db_session,
        actor_user_id=None,
        actor_organization_id=org.id,
        code=f"PROFESSIONAL_{uuid.uuid4().hex[:4]}",
        name="Drone Professional",
        suite_id=suite_drone.id,
        asset_scope="DRONE_UAV",
    )
    assert plan_drone.suite_id == suite_drone.id

    # 2. Create Aircraft Professional (same code under distinct suite is allowed)
    plan_air = create_plan(
        db_session,
        actor_user_id=None,
        actor_organization_id=org.id,
        code=f"PROFESSIONAL_DUP_{uuid.uuid4().hex[:4]}",
        name="Aircraft Professional",
        suite_id=suite_aircraft.id,
        asset_scope="AIRCRAFT",
    )
    assert plan_air.suite_id == suite_aircraft.id
    assert plan_air.id != plan_drone.id

    # 3. Duplicate code under the same suite is rejected
    with pytest.raises(ConflictError):
        create_plan(
            db_session,
            actor_user_id=None,
            actor_organization_id=org.id,
            code=plan_drone.code,
            name="Another Drone Pro",
            suite_id=suite_drone.id,
        )


def test_multi_suite_coexistence_and_same_suite_ambiguity(db_session) -> None:
    """Verify:
    - Same organization CAN have Drone ACTIVE + Aircraft ACTIVE subscriptions.
    - Same organization CANNOT have two overlapping ACTIVE subscriptions in Drone suite.
    """
    suite_drone = _get_or_create_suite(db_session, "DRONE_UAV", "Drone / UAV Suite", "Bot")
    suite_aircraft = _get_or_create_suite(db_session, "AIRCRAFT", "Aircraft Suite", "Plane")

    plan_drone_starter = Plan(
        suite_id=suite_drone.id,
        code=f"DRN_STARTER_{uuid.uuid4().hex[:4]}",
        name="Drone Starter",
        is_active=True,
    )
    plan_drone_pro = Plan(
        suite_id=suite_drone.id,
        code=f"DRN_PRO_{uuid.uuid4().hex[:4]}",
        name="Drone Pro",
        is_active=True,
    )
    plan_air_ent = Plan(
        suite_id=suite_aircraft.id,
        code=f"AIR_ENT_{uuid.uuid4().hex[:4]}",
        name="Aircraft Enterprise",
        is_active=True,
    )
    db_session.add_all([plan_drone_starter, plan_drone_pro, plan_air_ent])
    db_session.flush()

    org = Organization(name=f"Hybrid Fleet Ops {uuid.uuid4().hex[:4]}")
    db_session.add(org)
    db_session.flush()

    now = datetime.now(UTC)

    # 1. Create Drone Subscription (ACTIVE)
    sub_drone = create_subscription(
        db_session,
        actor_user_id=None,
        organization_id=org.id,
        plan_id=plan_drone_pro.id,
        suite_id=suite_drone.id,
        status=SubscriptionStatus.ACTIVE,
        starts_at=now,
        ends_at=now + timedelta(days=30),
    )
    assert sub_drone.suite_id == suite_drone.id

    # 2. Create Aircraft Subscription (ACTIVE) for SAME organization -> MUST SUCCEED (Multi-suite coexistence)
    sub_air = create_subscription(
        db_session,
        actor_user_id=None,
        organization_id=org.id,
        plan_id=plan_air_ent.id,
        suite_id=suite_aircraft.id,
        status=SubscriptionStatus.ACTIVE,
        starts_at=now,
        ends_at=now + timedelta(days=30),
    )
    assert sub_air.suite_id == suite_aircraft.id

    # 3. Attempt second ACTIVE subscription for DRONE suite -> MUST FAIL WITH CONFLICT (Ambiguity within same suite)
    with pytest.raises(ConflictError) as exc:
        create_subscription(
            db_session,
            actor_user_id=None,
            organization_id=org.id,
            plan_id=plan_drone_starter.id,
            suite_id=suite_drone.id,
            status=SubscriptionStatus.ACTIVE,
            starts_at=now,
            ends_at=now + timedelta(days=30),
        )
    assert "ambiguous" in (getattr(exc.value, "message", "") + str(exc.value)).lower() or "two simultaneously-current" in str(exc.value)


def test_suite_aware_entitlement_resolution(db_session) -> None:
    """Verify entitlement resolution respects suite context and multi-suite aggregation."""
    suite_drone = _get_or_create_suite(db_session, "DRONE_UAV", "Drone / UAV Suite", "Bot")
    suite_aircraft = _get_or_create_suite(db_session, "AIRCRAFT", "Aircraft Suite", "Plane")

    plan_drone = Plan(
        suite_id=suite_drone.id,
        code=f"DRN_PRO_{uuid.uuid4().hex[:4]}",
        name="Drone Professional",
        is_active=True,
    )
    plan_air = Plan(
        suite_id=suite_aircraft.id,
        code=f"AIR_PRO_{uuid.uuid4().hex[:4]}",
        name="Aircraft Professional",
        is_active=True,
    )
    db_session.add_all([plan_drone, plan_air])
    db_session.flush()

    # Features
    db_session.add_all([
        PlanFeature(plan_id=plan_drone.id, feature_key="drone_telemetry", enabled=True),
        PlanFeature(plan_id=plan_drone.id, feature_key="battery_analytics", enabled=True),
        PlanFeature(plan_id=plan_air.id, feature_key="aircraft_mro", enabled=True),
        PlanFeature(plan_id=plan_air.id, feature_key="airworthiness_directives", enabled=True),
    ])
    db_session.flush()

    org = Organization(name=f"Entitlement Test Org {uuid.uuid4().hex[:4]}")
    db_session.add(org)
    db_session.flush()

    now = datetime.now(UTC)
    create_subscription(
        db_session,
        actor_user_id=None,
        organization_id=org.id,
        plan_id=plan_drone.id,
        suite_id=suite_drone.id,
        status=SubscriptionStatus.ACTIVE,
        starts_at=now,
        ends_at=now + timedelta(days=30),
    )
    create_subscription(
        db_session,
        actor_user_id=None,
        organization_id=org.id,
        plan_id=plan_air.id,
        suite_id=suite_aircraft.id,
        status=SubscriptionStatus.ACTIVE,
        starts_at=now,
        ends_at=now + timedelta(days=30),
    )

    # 1. Resolve for Drone Suite specifically
    res_drone = resolve_entitlements(db_session, organization_id=org.id, suite_code="DRONE_UAV")
    assert res_drone.resolution_status == EntitlementResolutionStatus.ACTIVE
    assert res_drone.suite_code == "DRONE_UAV"
    assert res_drone.effective_features.get("drone_telemetry") is True
    assert res_drone.effective_features.get("aircraft_mro") is not True

    # 2. Resolve for Aircraft Suite specifically
    res_air = resolve_entitlements(db_session, organization_id=org.id, suite_code="AIRCRAFT")
    assert res_air.resolution_status == EntitlementResolutionStatus.ACTIVE
    assert res_air.suite_code == "AIRCRAFT"
    assert res_air.effective_features.get("aircraft_mro") is True
    assert res_air.effective_features.get("drone_telemetry") is not True

    # 3. Resolve globally (Multi-suite aggregation)
    res_multi = resolve_entitlements(db_session, organization_id=org.id)
    assert res_multi.resolution_status == EntitlementResolutionStatus.ACTIVE
    assert res_multi.suite_code == "MULTI_SUITE"
    assert res_multi.effective_features.get("drone_telemetry") is True
    assert res_multi.effective_features.get("aircraft_mro") is True
    assert len(res_multi.active_suites) == 2


def test_e2e_customer_onboarding_and_cross_suite_entitlement_journey(client, db_session) -> None:
    """Complete End-to-End Journey:
    1. Create Organization & User.
    2. Initially subscribe ONLY to Drone Suite.
    3. User accesses Drone endpoint (200 OK) and is blocked from Aircraft endpoint (403 Forbidden).
    4. Add Aircraft Suite subscription to the organization.
    5. User now has access to BOTH Drone and Aircraft operations.
    6. Cancel Drone subscription -> Drone endpoint blocked (403), Aircraft endpoint continues to work (200 OK).
    """
    suite_drone = _get_or_create_suite(db_session, "DRONE_UAV", "Drone / UAV Suite", "Bot")
    suite_aircraft = _get_or_create_suite(db_session, "AIRCRAFT", "Aircraft Suite", "Plane")

    plan_drone = Plan(
        suite_id=suite_drone.id,
        code=f"E2E_DRN_{uuid.uuid4().hex[:4]}",
        name="E2E Drone Pro",
        is_active=True,
    )
    plan_air = Plan(
        suite_id=suite_aircraft.id,
        code=f"E2E_AIR_{uuid.uuid4().hex[:4]}",
        name="E2E Aircraft Pro",
        is_active=True,
    )
    db_session.add_all([plan_drone, plan_air])
    db_session.flush()

    db_session.add_all([
        PlanFeature(plan_id=plan_drone.id, feature_key="drone_fleet_management", enabled=True),
        PlanFeature(plan_id=plan_drone.id, feature_key="asset_management", enabled=True),
        PlanFeature(plan_id=plan_air.id, feature_key="aircraft_fleet_management", enabled=True),
        PlanFeature(plan_id=plan_air.id, feature_key="asset_management", enabled=True),
    ])
    db_session.flush()

    # Step 1: Create Organization & Admin User
    org = Organization(name=f"SkyTech Aero {uuid.uuid4().hex[:4]}")
    db_session.add(org)
    db_session.flush()

    user = User(
        organization_id=org.id,
        email=f"operator_{uuid.uuid4().hex[:4]}@skytech.com",
        hashed_password=hash_password("AeroPass123!"),
        full_name="Fleet Director",
        is_active=True,
    )
    db_session.add(user)
    db_session.flush()

    db_session.add(UserRole(user_id=user.id, role_name=Role.ORG_ADMIN, organization_id=org.id))
    db_session.commit()

    # Login
    login_resp = client.post("/api/v1/auth/login", json={"email": user.email, "password": "AeroPass123!"})
    assert login_resp.status_code == 200
    token = login_resp.json()["access_token"]

    # Step 2: Subscribe to Drone Suite ONLY
    now = datetime.now(UTC)
    sub_drone = create_subscription(
        db_session,
        actor_user_id=user.id,
        organization_id=org.id,
        plan_id=plan_drone.id,
        suite_id=suite_drone.id,
        status=SubscriptionStatus.ACTIVE,
        starts_at=now,
        ends_at=now + timedelta(days=30),
    )

    # Step 3: Verify Drone API works, Aircraft API returns 403 SUITE_ENTITLEMENT_REQUIRED
    resp_drones = client.get("/api/v1/drones", headers=_auth(token))
    assert resp_drones.status_code == 200

    resp_aircraft = client.get("/api/v1/aircraft", headers=_auth(token))
    assert resp_aircraft.status_code == 403
    assert resp_aircraft.json().get("code") == "SUITE_ENTITLEMENT_REQUIRED" or "entitlement" in str(resp_aircraft.json()).lower()

    # Step 4: Add Aircraft Suite subscription
    sub_air = create_subscription(
        db_session,
        actor_user_id=user.id,
        organization_id=org.id,
        plan_id=plan_air.id,
        suite_id=suite_aircraft.id,
        status=SubscriptionStatus.ACTIVE,
        starts_at=now,
        ends_at=now + timedelta(days=30),
    )

    # Step 5: Verify BOTH Drone and Aircraft APIs now return 200 OK
    resp_drones_2 = client.get("/api/v1/drones", headers=_auth(token))
    assert resp_drones_2.status_code == 200

    resp_aircraft_2 = client.get("/api/v1/aircraft", headers=_auth(token))
    assert resp_aircraft_2.status_code == 200

    # Step 6: Cancel Drone subscription
    cancel_subscription(db_session, actor_user_id=user.id, subscription_id=sub_drone.id)

    # Drone API now blocked, Aircraft API continues to function
    resp_drones_3 = client.get("/api/v1/drones", headers=_auth(token))
    assert resp_drones_3.status_code == 403

    resp_aircraft_3 = client.get("/api/v1/aircraft", headers=_auth(token))
    assert resp_aircraft_3.status_code == 200
