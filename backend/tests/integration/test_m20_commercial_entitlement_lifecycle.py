"""M20: commercial entitlement lifecycle -- gaps found by
M20_COMMERCIAL_ENTITLEMENT_GAP_ANALYSIS.md, exercised end to end.

Covers: cross-suite plan change rejection, scheduled-subscription suite
integrity, plan change refresh, override enable/disable/removal, limit
override, canonical error codes, stale-token enforcement, audit previous
values, provisioning atomicity.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.core.errors import ConflictError, UsageLimitExceededError
from app.core.security import hash_password
from app.models.audit_event import AuditEvent
from app.models.organization import Organization
from app.models.plan import Plan, PlanFeature, PlanLimit
from app.models.product_catalog import ProductSuite
from app.models.subscription import Subscription, SubscriptionStatus
from app.models.user import User, UserRole
from app.services.entitlement_service import resolve_entitlements
from app.services.limit_enforcement_service import check_asset_creation_limit
from app.models.asset import Asset
from app.services.provisioning_service import provision_organization
from app.services.subscription_service import (
    cancel_subscription,
    create_subscription,
    schedule_subscription,
    update_subscription,
)
from app.services.tenant_entitlement_admin_service import (
    create_feature_override,
    create_usage_limit,
    remove_feature_override,
    update_feature_override,
    update_usage_limit,
)

PASSWORD = "supersecret123"


def _suite(db, code: str) -> ProductSuite:
    s = db.execute(select(ProductSuite).where(ProductSuite.code == code)).scalar_one()
    return s


def _plan(db, suite_code: str, features: dict[str, bool], limits: dict[str, int] | None = None) -> Plan:
    suite = _suite(db, suite_code)
    plan = Plan(
        suite_id=suite.id,
        code=f"M20-{uuid.uuid4().hex[:8]}",
        name=f"M20 {suite_code}",
        is_active=True,
    )
    db.add(plan)
    db.flush()
    for k, v in features.items():
        db.add(PlanFeature(plan_id=plan.id, feature_key=k, enabled=v))
    for k, v in (limits or {}).items():
        db.add(PlanLimit(plan_id=plan.id, limit_key=k, limit_value=v, is_unlimited=False))
    db.flush()
    return plan


def _org_with_sub(db, plan: Plan, status: str = SubscriptionStatus.ACTIVE) -> Organization:
    org = Organization(name=f"M20 Org {uuid.uuid4().hex[:8]}")
    db.add(org)
    db.flush()
    create_subscription(
        db,
        actor_user_id=None,
        organization_id=org.id,
        plan_id=plan.id,
        status=status,
        starts_at=datetime.now(UTC) - timedelta(days=1),
    )
    return org


def _audit(db, org_id, action: str) -> list[AuditEvent]:
    return list(
        db.execute(
            select(AuditEvent).where(
                AuditEvent.organization_id == org_id, AuditEvent.action == action
            )
        ).scalars()
    )


def _login_user(client, db, org: Organization, role: str = "ORG_ADMIN") -> dict[str, str]:
    user = User(
        organization_id=org.id,
        email=f"m20-{uuid.uuid4().hex[:10]}@example.com",
        hashed_password=hash_password(PASSWORD),
        full_name="M20 User",
        is_active=True,
    )
    db.add(user)
    db.flush()
    db.add(UserRole(user_id=user.id, role_name=role, organization_id=org.id))
    db.commit()
    resp = client.post("/api/v1/auth/login", json={"email": user.email, "password": PASSWORD})
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


# ---- suite / plan / subscription integrity ------------------------------


def test_plan_change_across_suites_is_rejected(db_session):
    drone = _plan(db_session, "DRONE_UAV", {"drone_fleet_management": True})
    aircraft = _plan(db_session, "AIRCRAFT", {"aircraft_fleet_management": True})
    org = _org_with_sub(db_session, drone)
    sub = db_session.execute(select(Subscription).where(Subscription.organization_id == org.id)).scalar_one()

    with pytest.raises(ConflictError) as exc:
        update_subscription(db_session, actor_user_id=None, subscription_id=sub.id, plan_id=aircraft.id)
    assert exc.value.code == "suite_plan_mismatch"

    db_session.refresh(sub)
    assert sub.plan_id == drone.id
    assert resolve_entitlements(db_session, organization_id=org.id).suite_code == "DRONE_UAV"


def test_plan_change_within_suite_refreshes_features_and_limits(db_session):
    starter = _plan(db_session, "DRONE_UAV", {"drone_fleet_management": True, "battery_analytics": False}, {"max_assets": 5})
    pro = _plan(db_session, "DRONE_UAV", {"drone_fleet_management": True, "battery_analytics": True}, {"max_assets": 25})
    org = _org_with_sub(db_session, starter)
    sub = db_session.execute(select(Subscription).where(Subscription.organization_id == org.id)).scalar_one()

    before = resolve_entitlements(db_session, organization_id=org.id)
    assert before.effective_features["battery_analytics"] is False

    update_subscription(db_session, actor_user_id=None, subscription_id=sub.id, plan_id=pro.id)
    after = resolve_entitlements(db_session, organization_id=org.id)
    assert after.plan_id == pro.id
    assert after.effective_features["battery_analytics"] is True
    assert {l.limit_key: l.limit_value for l in after.usage_limits}["max_assets"] == 25

    ev = _audit(db_session, org.id, "platform.subscription.updated")
    assert ev and ev[-1].event_metadata["previous_plan_id"] == str(starter.id)


def test_plan_change_to_inactive_plan_rejected(db_session):
    a = _plan(db_session, "DRONE_UAV", {})
    b = _plan(db_session, "DRONE_UAV", {})
    b.is_active = False
    db_session.flush()
    org = _org_with_sub(db_session, a)
    sub = db_session.execute(select(Subscription).where(Subscription.organization_id == org.id)).scalar_one()
    with pytest.raises(ConflictError) as exc:
        update_subscription(db_session, actor_user_id=None, subscription_id=sub.id, plan_id=b.id)
    assert exc.value.code == "inactive_plan"


def test_scheduled_subscription_carries_plan_suite(db_session):
    plan = _plan(db_session, "AIRCRAFT", {})
    org = Organization(name=f"M20 Sched {uuid.uuid4().hex[:6]}")
    db_session.add(org)
    db_session.flush()
    sub = schedule_subscription(
        db_session,
        actor_user_id=None,
        organization_id=org.id,
        plan_id=plan.id,
        starts_at=datetime.now(UTC) + timedelta(days=7),
    )
    assert sub.suite_id == plan.suite_id


# ---- lifecycle -------------------------------------------------------------


def test_lifecycle_states_grant_and_deny(db_session):
    plan = _plan(db_session, "DRONE_UAV", {"drone_fleet_management": True})
    org = _org_with_sub(db_session, plan, SubscriptionStatus.TRIALING)
    assert resolve_entitlements(db_session, organization_id=org.id).resolution_status == "ACTIVE"

    sub = db_session.execute(select(Subscription).where(Subscription.organization_id == org.id)).scalar_one()
    update_subscription(db_session, actor_user_id=None, subscription_id=sub.id, status=SubscriptionStatus.PAST_DUE)
    assert resolve_entitlements(db_session, organization_id=org.id).resolution_status == "ACTIVE"

    cancel_subscription(db_session, actor_user_id=None, subscription_id=sub.id)
    res = resolve_entitlements(db_session, organization_id=org.id)
    assert res.resolution_status == "NO_SUBSCRIPTION"
    assert res.effective_features == {}


def test_expired_subscription_denies(db_session):
    plan = _plan(db_session, "DRONE_UAV", {"drone_fleet_management": True})
    org = _org_with_sub(db_session, plan)
    sub = db_session.execute(select(Subscription).where(Subscription.organization_id == org.id)).scalar_one()
    sub.ends_at = datetime.now(UTC) - timedelta(minutes=1)
    db_session.flush()
    assert resolve_entitlements(db_session, organization_id=org.id).resolution_status == "NO_SUBSCRIPTION"


# ---- overrides & limits -----------------------------------------------------


def test_override_disable_enable_remove_and_audit(db_session):
    plan = _plan(db_session, "DRONE_UAV", {"battery_analytics": True})
    org = _org_with_sub(db_session, plan)
    roles = ["PLATFORM_ADMIN"]

    create_feature_override(
        db_session, actor_user_id=None, caller_roles=roles,
        organization_id=org.id, feature_key="battery_analytics", enabled=False, reason="test",
    )
    assert resolve_entitlements(db_session, organization_id=org.id).effective_features["battery_analytics"] is False

    update_feature_override(
        db_session, actor_user_id=None, caller_roles=roles,
        organization_id=org.id, feature_key="battery_analytics", enabled=True,
    )
    assert resolve_entitlements(db_session, organization_id=org.id).effective_features["battery_analytics"] is True
    upd = _audit(db_session, org.id, "platform.tenant_feature_override.updated")
    assert upd[-1].event_metadata["previous_enabled"] is False and upd[-1].event_metadata["enabled"] is True

    remove_feature_override(
        db_session, actor_user_id=None, organization_id=org.id, feature_key="battery_analytics",
    )
    assert resolve_entitlements(db_session, organization_id=org.id).effective_features["battery_analytics"] is True
    assert _audit(db_session, org.id, "platform.tenant_feature_override.removed")


def test_limit_override_up_and_down_is_enforced(db_session):
    plan = _plan(db_session, "DRONE_UAV", {}, {"max_assets": 25})
    org = _org_with_sub(db_session, plan)
    roles = ["PLATFORM_ADMIN"]

    def limit() -> int:
        return {l.limit_key: l.limit_value for l in resolve_entitlements(db_session, organization_id=org.id).usage_limits}["max_assets"]

    assert limit() == 25
    create_usage_limit(
        db_session, actor_user_id=None, caller_roles=roles, organization_id=org.id,
        feature_key="max_assets", limit_key="max_assets", limit_value=50, is_unlimited=False,
    )
    assert limit() == 50
    update_usage_limit(
        db_session, actor_user_id=None, caller_roles=roles, organization_id=org.id,
        feature_key="max_assets", limit_key="max_assets", limit_value=1,
    )
    assert limit() == 1
    ev = _audit(db_session, org.id, "platform.tenant_usage_limit.updated")
    assert ev[-1].event_metadata["previous_limit_value"] == 50

    # server-side enforcement at the effective (overridden) limit
    db_session.add(Asset(organization_id=org.id, asset_type="DRONE", registration="M20-1"))
    db_session.flush()
    with pytest.raises(UsageLimitExceededError):
        check_asset_creation_limit(db_session, organization_id=org.id)


# ---- provisioning atomicity -------------------------------------------------


def test_provisioning_suite_mismatch_leaves_nothing(db_session):
    drone = _plan(db_session, "DRONE_UAV", {})
    aircraft_suite = _suite(db_session, "AIRCRAFT")
    admin = Organization(name="M20 Ops")
    db_session.add(admin)
    db_session.flush()
    name = f"M20 Prov {uuid.uuid4().hex[:6]}"
    with pytest.raises(ConflictError) as exc:
        provision_organization(
            db_session, actor_user_id=uuid.uuid4(), organization_name=name, plan_id=drone.id,
            subscription_status=SubscriptionStatus.ACTIVE, admin_email=f"{uuid.uuid4().hex[:8]}@example.com",
            admin_full_name="X", suite_id=aircraft_suite.id,
        )
    assert exc.value.code == "suite_plan_mismatch"
    assert db_session.execute(select(Organization).where(Organization.name == name)).first() is None


# ---- API: canonical errors, stale token, cross-suite -------------------------


def test_drone_org_denied_aircraft_api_with_canonical_code(client, db_session):
    plan = _plan(db_session, "DRONE_UAV", {"drone_fleet_management": True})
    org = _org_with_sub(db_session, plan)
    headers = _login_user(client, db_session, org)

    assert client.get("/api/v1/drones", headers=headers).status_code == 200
    resp = client.get("/api/v1/aircraft", headers=headers)
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "SUITE_ENTITLEMENT_REQUIRED"


def test_aircraft_org_denied_drone_api(client, db_session):
    plan = _plan(db_session, "AIRCRAFT", {"aircraft_fleet_management": True})
    org = _org_with_sub(db_session, plan)
    headers = _login_user(client, db_session, org)
    resp = client.get("/api/v1/drones", headers=headers)
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "SUITE_ENTITLEMENT_REQUIRED"


def test_plan_disabled_feature_uses_forbidden_not_suite_code(client, db_session):
    plan = _plan(db_session, "DRONE_UAV", {"drone_fleet_management": False})
    org = _org_with_sub(db_session, plan)
    headers = _login_user(client, db_session, org)
    resp = client.get("/api/v1/drones", headers=headers)
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "forbidden"


def test_stale_token_loses_access_when_feature_disabled_and_org_state_refreshes(client, db_session):
    plan = _plan(db_session, "DRONE_UAV", {"drone_fleet_management": True})
    org = _org_with_sub(db_session, plan)
    headers = _login_user(client, db_session, org)  # token issued while entitled

    assert client.get("/api/v1/drones", headers=headers).status_code == 200
    assert client.get("/api/v1/entitlements", headers=headers).json()["effective_features"]["drone_fleet_management"] is True

    create_feature_override(
        db_session, actor_user_id=None, caller_roles=["PLATFORM_ADMIN"],
        organization_id=org.id, feature_key="drone_fleet_management", enabled=False, reason="revoke",
    )

    # same token, no re-login
    assert client.get("/api/v1/drones", headers=headers).status_code == 403
    assert client.get("/api/v1/entitlements", headers=headers).json()["effective_features"]["drone_fleet_management"] is False


def test_cancelled_subscription_blocks_existing_token(client, db_session):
    plan = _plan(db_session, "DRONE_UAV", {"drone_fleet_management": True})
    org = _org_with_sub(db_session, plan)
    headers = _login_user(client, db_session, org)
    assert client.get("/api/v1/drones", headers=headers).status_code == 200
    sub = db_session.execute(select(Subscription).where(Subscription.organization_id == org.id)).scalar_one()
    cancel_subscription(db_session, actor_user_id=None, subscription_id=sub.id)
    assert client.get("/api/v1/drones", headers=headers).status_code == 403


def test_org_suspension_blocks_existing_token(client, db_session):
    plan = _plan(db_session, "DRONE_UAV", {"drone_fleet_management": True})
    org = _org_with_sub(db_session, plan)
    headers = _login_user(client, db_session, org)
    org_row = db_session.get(Organization, org.id)
    org_row.status = "SUSPENDED"
    db_session.commit()
    assert client.get("/api/v1/drones", headers=headers).status_code == 401


# ---- forensic-pass regressions -------------------------------------------------


def test_update_plan_suite_move_guards(db_session):
    """update_plan(suite_id=...) previously raised NameError (undefined
    _validate_suite_id). A plan may only change suite while it has no
    subscribers and no features outside the target suite."""
    from app.services.plan_service import update_plan

    org = Organization(name=f"M20 PlanMove {uuid.uuid4().hex[:6]}")
    db_session.add(org)
    db_session.flush()
    aircraft = _suite(db_session, "AIRCRAFT")

    subscribed = _plan(db_session, "DRONE_UAV", {})
    _org_with_sub(db_session, subscribed)
    with pytest.raises(ConflictError) as exc:
        update_plan(db_session, actor_user_id=None, actor_organization_id=org.id,
                    plan_id=subscribed.id, suite_id=aircraft.id)
    assert exc.value.code == "plan_has_subscribers"

    drone_only = _plan(db_session, "DRONE_UAV", {"drone_fleet_management": True})
    with pytest.raises(ConflictError) as exc:
        update_plan(db_session, actor_user_id=None, actor_organization_id=org.id,
                    plan_id=drone_only.id, suite_id=aircraft.id)
    assert exc.value.code == "feature_outside_suite_boundary"

    clean = _plan(db_session, "DRONE_UAV", {"work_order_management": True})
    moved = update_plan(db_session, actor_user_id=None, actor_organization_id=org.id,
                        plan_id=clean.id, suite_id=aircraft.id)
    assert moved.suite_id == aircraft.id


def test_revoked_edge_device_conflicts_instead_of_nameerror():
    """edge_hardware_service raised an undefined ValidationError for revoked devices."""
    import app.services.edge_hardware_service as svc

    assert not hasattr(svc, "ValidationError")
    assert svc.ConflictError is ConflictError


def test_onboarding_stage_patch_rbac_validation_and_persistence(client, db_session):
    """PATCH /onboarding-stage always 500'd (non-existent Permission /
    CurrentUser method) and never committed."""
    plan = _plan(db_session, "DRONE_UAV", {})
    org = _org_with_sub(db_session, plan)
    admin = _login_user(client, db_session, org, "ORG_ADMIN")
    viewer = _login_user(client, db_session, org, "VIEWER")

    ok = client.patch("/api/v1/commercial/onboarding-stage", json={"stage": "UAT"}, headers=admin)
    assert ok.status_code == 200, ok.text
    db_session.expire_all()
    assert db_session.get(Organization, org.id).onboarding_stage == "UAT"

    bad = client.patch("/api/v1/commercial/onboarding-stage", json={"stage": "NOPE"}, headers=admin)
    assert bad.status_code == 409

    denied = client.patch("/api/v1/commercial/onboarding-stage", json={"stage": "GO_LIVE"}, headers=viewer)
    assert denied.status_code == 403


def test_commercial_router_endpoints_no_longer_500(client, db_session):
    """All /commercial endpoints raised AttributeError (500) before the fix."""
    plan = _plan(db_session, "DRONE_UAV", {})
    org = _org_with_sub(db_session, plan)
    admin = _login_user(client, db_session, org, "ORG_ADMIN")
    viewer = _login_user(client, db_session, org, "VIEWER")

    assert client.get("/api/v1/commercial/onboarding-stage", headers=viewer).status_code == 200
    assert client.get("/api/v1/commercial/cross-asset-intelligence", headers=admin).status_code == 200
    assert client.post("/api/v1/commercial/export", headers=admin).status_code == 200
    # export is a tenant-data operation: a viewer must not get it
    assert client.post("/api/v1/commercial/export", headers=viewer).status_code == 403
    assert client.get("/api/v1/commercial/cross-asset-intelligence").status_code == 401


def test_edge_router_rbac_instead_of_500(client, db_session):
    """/edge/* handlers used a non-existent CurrentUser.require_permission and
    non-existent Permission.FLEET_* members (HTTP 500 on every call)."""
    plan = _plan(db_session, "DRONE_UAV", {})
    org = _org_with_sub(db_session, plan)
    admin = _login_user(client, db_session, org, "ORG_ADMIN")
    viewer = _login_user(client, db_session, org, "VIEWER")

    assert client.get("/api/v1/edge/devices", headers=admin).status_code == 200
    assert client.get("/api/v1/edge/devices", headers=viewer).status_code == 200
    assert client.get("/api/v1/edge/devices").status_code == 401

    missing = f"/api/v1/edge/devices/does-not-exist-{uuid.uuid4().hex[:6]}/revoke"
    assert client.post(missing, json={}, headers=viewer).status_code == 403
    r = client.post(missing, json={"reason": "m20"}, headers=admin)
    assert r.status_code in (404, 422), r.text  # reaches the service; never 500


def test_m7_evidence_gap_query_no_longer_raises_for_completed_work_order(db_session):
    """_evaluate_compliance_evidence_gaps filtered on the non-existent
    EvidenceFile.work_order_id, raising AttributeError for any asset that had a
    COMPLETED work order."""
    from app.models.asset import Asset
    from app.models.work_order import WorkOrder
    from app.services.intelligence.proactive_intelligence_service import (
        _evaluate_compliance_evidence_gaps,
    )

    plan = _plan(db_session, "AIRCRAFT", {})
    org = _org_with_sub(db_session, plan)
    asset = Asset(organization_id=org.id, asset_type="AIRCRAFT", registration="M20-EG-1")
    db_session.add(asset)
    db_session.flush()
    db_session.add(
        WorkOrder(
            organization_id=org.id, asset_id=asset.id, work_order_number="WO-M20-EG",
            title="Completed without evidence", status="COMPLETED", priority="MEDIUM",
        )
    )
    db_session.flush()

    signals = _evaluate_compliance_evidence_gaps(db_session, org.id, asset, "FAA")
    assert any(s["signal_type"] == "EVIDENCE_GAP" and "WO-M20-EG" in s["title"] for s in signals)
