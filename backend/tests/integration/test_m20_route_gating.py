"""M20 phase 2: backend commercial gating of previously ungated surfaces.

Feature -> route mapping (documented product decisions):
  flight_telemetry       -> /telemetry/* (JWT routes) and the DJI webhook's target tenant
  battery_analytics      -> /batteries/*, /drones/{id}/batteries, battery maintenance requirements
  predictive_maintenance -> /hums/{assets,components}/*/prognostics (prognostics / RUL)
  audit_logging          -> /tenant/audit          (baseline: on unless explicitly disabled)
  release_readiness      -> /work-orders/{id}/release-readiness (baseline: on unless disabled)

Every case is over real HTTP with a real JWT. 403 = commercial denial; 401/404/422 for
an entitled caller means the request passed the gate (the resource just doesn't exist).
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.core.errors import ConflictError
from app.core.security import hash_password
from app.models.organization import Organization
from app.models.plan import Plan, PlanFeature
from app.models.product_catalog import ProductSuite
from app.models.subscription import Subscription, SubscriptionStatus
from app.models.user import User, UserRole
from app.services.plan_service import create_plan_feature
from app.services.tenant_entitlement_admin_service import create_feature_override

PW = "supersecret123"
RID = str(uuid.uuid4())

# (name, method, path, extra features the route's router already requires, feature under test, baseline?)
ROUTES = [
    ("telemetry", "GET", "/api/v1/telemetry/events", [], "flight_telemetry", False),
    ("battery", "GET", f"/api/v1/batteries/{RID}", ["drone_fleet_management"], "battery_analytics", False),
    ("drone-batteries", "GET", f"/api/v1/drones/{RID}/batteries", ["drone_fleet_management"], "battery_analytics", False),
    ("prognostics", "GET", f"/api/v1/hums/assets/{RID}/prognostics", ["hums"], "predictive_maintenance", False),
    ("audit", "GET", "/api/v1/tenant/audit", [], "audit_logging", True),
    ("release-readiness", "GET", f"/api/v1/work-orders/{RID}/release-readiness", ["work_order_management"], "release_readiness", True),
]
IDS = [r[0] for r in ROUTES]


def _org(db, suite_code, features: dict[str, bool], *, sub=True, ends_at=None):
    suite = db.execute(select(ProductSuite).where(ProductSuite.code == suite_code)).scalar_one()
    plan = Plan(suite_id=suite.id, code=f"G-{uuid.uuid4().hex[:8]}", name="Gate", is_active=True)
    db.add(plan)
    db.flush()
    for k, v in features.items():
        db.add(PlanFeature(plan_id=plan.id, feature_key=k, enabled=v))
    org = Organization(name=f"Gate Org {uuid.uuid4().hex[:6]}")
    db.add(org)
    db.flush()
    if sub:
        db.add(Subscription(
            organization_id=org.id, plan_id=plan.id, suite_id=suite.id,
            status=SubscriptionStatus.ACTIVE, starts_at=datetime.now(UTC) - timedelta(days=2),
            ends_at=ends_at,
        ))
    return org


def _login(client, db, org, role="ORG_ADMIN"):
    u = User(organization_id=org.id, email=f"g-{uuid.uuid4().hex[:8]}@example.com",
             hashed_password=hash_password(PW), full_name="G", is_active=True, email_verified=True)
    db.add(u)
    db.flush()
    db.add(UserRole(user_id=u.id, role_name=role, organization_id=org.id))
    db.commit()
    r = client.post("/api/v1/auth/login", json={"email": u.email, "password": PW})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _call(client, headers, method, path):
    return client.request(method, path, headers=headers)


@pytest.mark.parametrize("name,method,path,extra,feature,baseline", ROUTES, ids=IDS)
def test_enabled_passes_gate(client, db_session, name, method, path, extra, feature, baseline):
    org = _org(db_session, "DRONE_UAV", {**{k: True for k in extra}, feature: True})
    r = _call(client, _login(client, db_session, org), method, path)
    assert r.status_code not in (401, 403), (name, r.status_code, r.text)


@pytest.mark.parametrize("name,method,path,extra,feature,baseline", ROUTES, ids=IDS)
def test_explicitly_disabled_is_403(client, db_session, name, method, path, extra, feature, baseline):
    org = _org(db_session, "DRONE_UAV", {**{k: True for k in extra}, feature: False})
    r = _call(client, _login(client, db_session, org), method, path)
    assert r.status_code == 403, (name, r.status_code, r.text)


@pytest.mark.parametrize("name,method,path,extra,feature,baseline", ROUTES, ids=IDS)
def test_absent_from_plan(client, db_session, name, method, path, extra, feature, baseline):
    """Not configured on the plan: denied, except baseline capabilities which every
    tenant has always had (audit trail, release readiness) and stay on until disabled."""
    org = _org(db_session, "DRONE_UAV", {k: True for k in extra})
    r = _call(client, _login(client, db_session, org), method, path)
    if baseline:
        assert r.status_code not in (401, 403), (name, r.status_code, r.text)
    else:
        assert r.status_code == 403, (name, r.status_code, r.text)


@pytest.mark.parametrize("name,method,path,extra,feature,baseline", ROUTES, ids=IDS)
def test_override_disable_and_enable(client, db_session, name, method, path, extra, feature, baseline):
    base = {k: True for k in extra}
    # plan enables, override disables -> denied
    org = _org(db_session, "DRONE_UAV", {**base, feature: True})
    h = _login(client, db_session, org)
    assert _call(client, h, method, path).status_code != 403
    create_feature_override(db_session, actor_user_id=None, caller_roles=["PLATFORM_ADMIN"],
                            organization_id=org.id, feature_key=feature, enabled=False, reason="t")
    assert _call(client, h, method, path).status_code == 403
    # plan disables, override enables -> allowed
    org2 = _org(db_session, "DRONE_UAV", {**base, feature: False})
    h2 = _login(client, db_session, org2)
    assert _call(client, h2, method, path).status_code == 403
    create_feature_override(db_session, actor_user_id=None, caller_roles=["PLATFORM_ADMIN"],
                            organization_id=org2.id, feature_key=feature, enabled=True, reason="t")
    assert _call(client, h2, method, path).status_code != 403


@pytest.mark.parametrize("name,method,path,extra,feature,baseline", ROUTES, ids=IDS)
def test_no_subscription_and_expired_are_403(client, db_session, name, method, path, extra, feature, baseline):
    feats = {**{k: True for k in extra}, feature: True}
    none = _org(db_session, "DRONE_UAV", feats, sub=False)
    assert _call(client, _login(client, db_session, none), method, path).status_code == 403
    expired = _org(db_session, "DRONE_UAV", feats, ends_at=datetime.now(UTC) - timedelta(minutes=5))
    assert _call(client, _login(client, db_session, expired), method, path).status_code == 403


@pytest.mark.parametrize("name,method,path,extra,feature,baseline", ROUTES, ids=IDS)
def test_platform_admin_has_no_tenant_bypass(client, db_session, name, method, path, extra, feature, baseline):
    """Platform admins administer tenants through /platform/*; the tenant routes are
    governed by the caller's OWN organization's entitlement (no server-side bypass;
    the frontend FeatureGuard bypass for platform users is display-only)."""
    org = _org(db_session, "DRONE_UAV", {}, sub=False)
    r = _call(client, _login(client, db_session, org, "PLATFORM_ADMIN"), method, path)
    assert r.status_code == 403, (name, r.status_code)


@pytest.mark.parametrize("feature", ["battery_analytics", "flight_telemetry", "drone_missions"])
def test_wrong_suite_feature_cannot_be_added_to_aircraft_plan(db_session, feature):
    """Drone-domain features cannot be written into an AIRCRAFT plan (write-time
    suite boundary); the same applies to overrides (existing rule)."""
    plan = _org(db_session, "AIRCRAFT", {}, sub=False)  # creates an AIRCRAFT plan as side effect
    aircraft_plan = db_session.execute(
        select(Plan).join(ProductSuite, ProductSuite.id == Plan.suite_id)
        .where(ProductSuite.code == "AIRCRAFT").order_by(Plan.created_at.desc())
    ).scalars().first()
    if feature == "flight_telemetry":
        # not suite-restricted: allowed everywhere
        create_plan_feature(db_session, actor_user_id=None, actor_organization_id=plan.id,
                            plan_id=aircraft_plan.id, feature_key=feature)
        return
    with pytest.raises(ConflictError) as exc:
        create_plan_feature(db_session, actor_user_id=None, actor_organization_id=plan.id,
                            plan_id=aircraft_plan.id, feature_key=feature)
    assert exc.value.code == "feature_outside_suite_boundary"


def test_aircraft_suite_org_denied_drone_battery_route(client, db_session):
    org = _org(db_session, "AIRCRAFT", {"aircraft_fleet_management": True, "work_order_management": True})
    h = _login(client, db_session, org)
    r = client.get(f"/api/v1/batteries/{RID}", headers=h)
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "SUITE_ENTITLEMENT_REQUIRED"


def test_dji_webhook_requires_tenant_entitlement(client, db_session, monkeypatch):
    import hashlib
    import hmac
    import json
    from types import SimpleNamespace

    from app.api.v1 import telemetry as telemetry_api

    secret = "gate-secret"
    monkeypatch.setattr(telemetry_api, "get_settings", lambda: SimpleNamespace(dji_webhook_secret=secret))
    body = json.dumps({"bid": "b1", "event": "flight_record.created",
                       "timestamp": int(datetime.now(UTC).timestamp() * 1000),
                       "data": {"device_sn": "X"}}).encode()
    sig = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()

    def post(org):
        return client.post("/api/v1/telemetry/dji/webhook", content=body,
                           headers={"Content-Type": "application/json", "X-Organization-ID": str(org.id),
                                    "X-DJI-Signature": sig})

    denied = _org(db_session, "DRONE_UAV", {"flight_telemetry": False})
    assert post(denied).status_code == 403
    nosub = _org(db_session, "DRONE_UAV", {"flight_telemetry": True}, sub=False)
    assert post(nosub).status_code == 403
    allowed = _org(db_session, "DRONE_UAV", {"flight_telemetry": True})
    assert post(allowed).status_code not in (401, 403)
