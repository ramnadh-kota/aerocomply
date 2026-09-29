"""Comprehensive tests for LISA tool authorization, commercial entitlements,
suite boundaries, and multi-tenant isolation (Section 10 Test Matrix).
"""

from datetime import UTC, datetime, timedelta
import uuid

import pytest

from app.core.errors import ForbiddenError, NotFoundError
from app.models.organization import Organization
from app.models.plan import Plan, PlanFeature
from app.models.product_catalog import ProductSuite
from app.models.subscription import Subscription, SubscriptionStatus
from app.models.tenant_entitlement import TenantFeatureOverride
from app.models.user import User, UserRole
from app.schemas.aircraft import AircraftCreateRequest
from app.schemas.auth import CurrentUser
from app.services import aircraft_service
from app.services.ai.tools import execute_tool, TOOL_REGISTRY


def _create_tenant(
    db_session,
    suite_code: str = "AIRCRAFT",
    features: dict[str, bool] | None = None,
    sub_status: SubscriptionStatus = SubscriptionStatus.ACTIVE,
    starts_at: datetime | None = None,
    ends_at: datetime | None = None,
) -> tuple[Organization, Plan, Subscription]:
    org = Organization(name=f"Org-{uuid.uuid4().hex[:8]}")
    db_session.add(org)
    db_session.flush()

    suite = (
        db_session.query(ProductSuite).filter(ProductSuite.code == suite_code).first()
    )
    if not suite:
        suite = ProductSuite(code=suite_code, name=f"{suite_code} Suite")
        db_session.add(suite)
        db_session.flush()

    plan = Plan(
        name=f"Plan-{uuid.uuid4().hex[:8]}",
        code=f"plan-{uuid.uuid4().hex[:12]}",
        suite_id=suite.id,
        is_active=True,
    )
    db_session.add(plan)
    db_session.flush()

    default_features = {
        "aircraft_fleet_management": True,
        "work_order_management": True,
        "inspections_management": True,
        "procurement_management": True,
        "compliance_management": True,
        "advanced_compliance_intelligence": True,
        "predictive_maintenance": True,
        "hums": True,
        "flight_telemetry": True,
        "digital_twin": True,
        "mro_intelligence": True,
        "lisa_ai_copilot": True,
        "drone_fleet_management": True if suite_code == "DRONE_UAV" else False,
    }
    if features is not None:
        default_features.update(features)

    for f_key, enabled in default_features.items():
        db_session.add(
            PlanFeature(plan_id=plan.id, feature_key=f_key, enabled=enabled)
        )

    sub = Subscription(
        organization_id=org.id,
        plan_id=plan.id,
        suite_id=suite.id,
        status=sub_status,
        starts_at=starts_at or (datetime.now(UTC) - timedelta(days=1)),
        ends_at=ends_at,
    )
    db_session.add(sub)
    db_session.commit()
    return org, plan, sub


def _create_user(
    db_session, org_id: uuid.UUID, roles: list[str] | None = None
) -> CurrentUser:
    user = User(
        organization_id=org_id,
        email=f"user-{uuid.uuid4().hex[:8]}@example.com",
        hashed_password="not-a-real-hash",
        full_name="LISA Test User",
        is_active=True,
    )
    db_session.add(user)
    db_session.flush()

    if roles:
        for r in roles:
            db_session.add(
                UserRole(user_id=user.id, role_name=r, organization_id=org_id)
            )
    db_session.commit()

    return CurrentUser(
        id=user.id,
        organization_id=org_id,
        email=user.email,
        full_name=user.full_name,
        roles=roles or [],
    )


def test_org_admin_with_valid_entitlement_allowed(db_session):
    org, plan, sub = _create_tenant(db_session, suite_code="AIRCRAFT")
    user = _create_user(db_session, org.id, ["ORG_ADMIN"])
    aircraft = aircraft_service.create_aircraft(
        db_session,
        organization_id=org.id,
        payload=AircraftCreateRequest(
            registration="N-ADM1", msn="MSN-ADM-1", aircraft_type="A320"
        ),
    )

    res = execute_tool(
        db_session, user, "get_aircraft", {"aircraft_id": str(aircraft.id)}
    )
    assert res["registration"] == "N-ADM1"


def test_org_admin_with_disabled_feature_denied(db_session):
    org, plan, sub = _create_tenant(
        db_session,
        suite_code="AIRCRAFT",
        features={"aircraft_fleet_management": False},
    )
    user = _create_user(db_session, org.id, ["ORG_ADMIN"])
    aircraft = aircraft_service.create_aircraft(
        db_session,
        organization_id=org.id,
        payload=AircraftCreateRequest(
            registration="N-ADM2", msn="MSN-ADM-2", aircraft_type="A320"
        ),
    )

    with pytest.raises(ForbiddenError) as exc:
        execute_tool(
            db_session, user, "get_aircraft", {"aircraft_id": str(aircraft.id)}
        )
    assert "not entitled to feature" in str(exc.value)


def test_tenant_feature_override_disable_denies_tool(db_session):
    org, plan, sub = _create_tenant(
        db_session,
        suite_code="AIRCRAFT",
        features={"hums": True},
    )
    user = _create_user(db_session, org.id, ["ORG_ADMIN"])
    aircraft = aircraft_service.create_aircraft(
        db_session,
        organization_id=org.id,
        payload=AircraftCreateRequest(
            registration="N-OVR1", msn="MSN-OVR-1", aircraft_type="A320"
        ),
    )

    # Disable HUMS via TenantFeatureOverride
    db_session.add(
        TenantFeatureOverride(
            organization_id=org.id,
            feature_key="hums",
            enabled=False,
            reason="Auditing compliance block",
        )
    )
    db_session.commit()

    with pytest.raises(ForbiddenError) as exc:
        execute_tool(
            db_session,
            user,
            "get_asset_hums_health",
            {"asset_id": str(aircraft.id)},
        )
    assert "not entitled to feature" in str(exc.value)


def test_user_with_no_role_denied_fail_closed(db_session):
    org, plan, sub = _create_tenant(db_session, suite_code="AIRCRAFT")
    # User with empty roles list
    user = _create_user(db_session, org.id, [])

    with pytest.raises(ForbiddenError) as exc:
        execute_tool(db_session, user, "list_aircraft", {})
    assert "Role does not have permission" in str(exc.value)


def test_cross_tenant_asset_access_denied_or_not_found(db_session):
    org_a, _, _ = _create_tenant(db_session, suite_code="AIRCRAFT")
    org_b, _, _ = _create_tenant(db_session, suite_code="AIRCRAFT")

    user_b = _create_user(db_session, org_b.id, ["ORG_ADMIN"])
    aircraft_a = aircraft_service.create_aircraft(
        db_session,
        organization_id=org_a.id,
        payload=AircraftCreateRequest(
            registration="N-TENA", msn="MSN-TENA-1", aircraft_type="A320"
        ),
    )

    with pytest.raises(NotFoundError):
        execute_tool(
            db_session,
            user_b,
            "get_aircraft",
            {"aircraft_id": str(aircraft_a.id)},
        )


def test_no_subscription_denied(db_session):
    org = Organization(name="No-Sub-Org")
    db_session.add(org)
    db_session.commit()
    user = _create_user(db_session, org.id, ["ORG_ADMIN"])

    with pytest.raises(ForbiddenError) as exc:
        execute_tool(db_session, user, "list_aircraft", {})
    assert "subscription is not active" in str(exc.value)


def test_expired_subscription_denied(db_session):
    org, plan, sub = _create_tenant(
        db_session,
        suite_code="AIRCRAFT",
        starts_at=datetime.now(UTC) - timedelta(days=30),
        ends_at=datetime.now(UTC) - timedelta(days=1),
    )
    user = _create_user(db_session, org.id, ["ORG_ADMIN"])

    with pytest.raises(ForbiddenError) as exc:
        execute_tool(db_session, user, "list_aircraft", {})
    assert "subscription is not active" in str(exc.value)


def test_suite_boundary_mismatch_denied(db_session):
    # Drone suite subscriber trying to access aircraft tool requiring AIRCRAFT/HELICOPTER suite
    org, plan, sub = _create_tenant(db_session, suite_code="DRONE_UAV")
    user = _create_user(db_session, org.id, ["ORG_ADMIN"])

    with pytest.raises(ForbiddenError) as exc:
        execute_tool(db_session, user, "list_aircraft", {})
    assert (
        "is not entitled" in str(exc.value)
        or "SUITE_ENTITLEMENT_REQUIRED" in str(exc.value)
    )


def test_platform_admin_without_tenant_role_denied(db_session):
    org, plan, sub = _create_tenant(db_session, suite_code="AIRCRAFT")
    user = _create_user(db_session, org.id, ["PLATFORM_ADMIN"])

    with pytest.raises(ForbiddenError) as exc:
        execute_tool(db_session, user, "list_aircraft", {})
    assert "Role does not have permission" in str(exc.value)


def test_missing_asset_safe_error(db_session):
    org, plan, sub = _create_tenant(db_session, suite_code="AIRCRAFT")
    user = _create_user(db_session, org.id, ["ORG_ADMIN"])
    non_existent = uuid.uuid4()

    with pytest.raises(NotFoundError):
        execute_tool(
            db_session, user, "get_aircraft", {"aircraft_id": str(non_existent)}
        )


def test_all_59_tools_registered_with_permissions_and_features():
    assert len(TOOL_REGISTRY) == 59
    for tool in TOOL_REGISTRY:
        assert tool.name
        assert tool.description
        assert tool.input_schema is not None
        assert tool.handler is not None
        assert tool.required_permission is not None
        assert (
            tool.required_feature is not None
        ), f"Tool {tool.name} is missing required_feature"
