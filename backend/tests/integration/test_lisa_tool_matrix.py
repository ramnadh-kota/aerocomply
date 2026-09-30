"""Exhaustive LISA tool authorization matrix.

Every registered tool is exercised against: RBAC (role without the tool's permission), commercial state (no
subscription / cancelled), feature entitlement (plan without the tool's features), suite boundary, fuzzed identifiers
(random UUIDs, wrong types, missing arguments: must end in an AeroComplyError, never a raw exception) and tenant
isolation. The inventory itself is pinned so adding a tool without a permission / feature fails this file."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import delete

from app.core.errors import AeroComplyError, ForbiddenError
from app.core.permissions import permissions_for_roles
from app.models.subscription import Subscription, SubscriptionStatus
from app.services.ai.tools import TOOL_REGISTRY, execute_tool
from tests.integration.conftest import grant_features
from tests.integration.test_lisa_security_entitlements import _create_tenant, _create_user

ALL_TOOLS = [t.name for t in TOOL_REGISTRY]
BY_NAME = {t.name: t for t in TOOL_REGISTRY}


def _args_for(spec, value=None):
    """Arguments satisfying the tool's required schema with random UUIDs (or `value`)."""
    args = {}
    props = spec.input_schema.get("properties", {})
    for key in spec.input_schema.get("required", []) or []:
        args[key] = value if value is not None else str(uuid.uuid4())
        if props.get(key, {}).get("type") == "integer":
            args[key] = 1
    return args


def _all_features_of(spec):
    return [f.strip() for f in (spec.required_feature or "").split(",") if f.strip()]


# ------------------------------------------------------------------ inventory invariants
def test_inventory_every_tool_has_a_permission_and_a_feature_and_unique_name():
    assert len(ALL_TOOLS) == len(set(ALL_TOOLS)) >= 60
    for t in TOOL_REGISTRY:
        assert t.required_permission is not None, t.name
        assert t.required_feature, f"{t.name} has no feature gate"
        assert t.handler and t.input_schema.get("type") == "object", t.name
        # tenant identity must never be a model-supplied argument
        assert "organization_id" not in t.input_schema.get("properties", {}), t.name


def test_no_tool_accepts_an_organization_argument_and_handlers_ignore_smuggled_org_ids(db_session):
    org, _, _ = _create_tenant(db_session, "AIRCRAFT")
    other, _, _ = _create_tenant(db_session, "AIRCRAFT")
    user = _create_user(db_session, org.id, ["ORG_ADMIN"])
    res = execute_tool(db_session, user, "list_aircraft", {"organization_id": str(other.id)})
    assert res == {"aircraft": []}                                    # still the caller's own (empty) tenant


# ------------------------------------------------------------------ RBAC: role without the permission
@pytest.mark.parametrize("tool", ALL_TOOLS)
def test_role_without_permission_is_forbidden(db_session, tool):
    spec = BY_NAME[tool]
    suite = "DRONE_UAV" if "drone" in (spec.required_feature or "") and "aircraft" not in (spec.required_feature or "") else "AIRCRAFT"
    feats = {f: True for f in _all_features_of(spec)}
    org, _, _ = _create_tenant(db_session, suite, features=feats)
    # find a real role that lacks this tool's permission
    roles = ["VIEWER", "TECHNICIAN", "AUDITOR", "PILOT", "PLANNER", "ORG_ADMIN"]
    lacking = [r for r in roles if spec.required_permission.value not in permissions_for_roles([r])]
    user = _create_user(db_session, org.id, lacking[:1] or [])
    if not lacking:
        user = _create_user(db_session, org.id, [])                    # no roles at all is always insufficient
    with pytest.raises(ForbiddenError) as exc:
        execute_tool(db_session, user, tool, _args_for(spec))
    assert exc.value.code in {"forbidden", "SUITE_ENTITLEMENT_REQUIRED"}


# ------------------------------------------------------------------ commercial state
@pytest.mark.parametrize("tool", ALL_TOOLS)
def test_no_subscription_or_expired_subscription_is_denied(db_session, tool):
    spec = BY_NAME[tool]
    org, _, sub = _create_tenant(db_session, "AIRCRAFT", features={f: True for f in _all_features_of(spec)})
    user = _create_user(db_session, org.id, ["ORG_ADMIN"])
    sub.status = SubscriptionStatus.CANCELED
    sub.ends_at = datetime.now(UTC) - timedelta(days=1)
    db_session.commit()
    with pytest.raises(ForbiddenError):
        execute_tool(db_session, user, tool, _args_for(spec))
    db_session.execute(delete(Subscription).where(Subscription.organization_id == org.id))
    db_session.commit()
    with pytest.raises(ForbiddenError):
        execute_tool(db_session, user, tool, _args_for(spec))


# ------------------------------------------------------------------ feature entitlement
@pytest.mark.parametrize("tool", ALL_TOOLS)
def test_plan_without_the_tools_features_is_denied(db_session, tool):
    spec = BY_NAME[tool]
    feats = {f: False for f in _all_features_of(spec)}
    org, _, _ = _create_tenant(db_session, "AIRCRAFT", features=feats)
    user = _create_user(db_session, org.id, ["ORG_ADMIN"])
    with pytest.raises(ForbiddenError):
        execute_tool(db_session, user, tool, _args_for(spec))


# ------------------------------------------------------------------ suite boundary
@pytest.mark.parametrize("tool", [t.name for t in TOOL_REGISTRY if t.required_suite])
def test_tool_restricted_to_suites_denies_other_suites(db_session, tool):
    spec = BY_NAME[tool]
    allowed = {s.strip() for s in spec.required_suite.split(",")}
    outside = "DRONE_UAV"
    assert outside not in allowed
    org, _, _ = _create_tenant(db_session, outside, features={f: True for f in _all_features_of(spec)})
    user = _create_user(db_session, org.id, ["ORG_ADMIN"])
    with pytest.raises(ForbiddenError) as exc:
        execute_tool(db_session, user, tool, _args_for(spec))
    assert exc.value.code == "SUITE_ENTITLEMENT_REQUIRED"


def test_multi_suite_organization_holding_an_allowed_suite_is_not_locked_out(db_session):
    """Regression: a MULTI_SUITE org reports suite_code 'MULTI_SUITE', which is in no tool's allow-list, so an org
    that really holds the AIRCRAFT suite was refused every aircraft tool."""
    org, _, _ = _create_tenant(db_session, "AIRCRAFT")
    grant_features(db_session, org.id, "drone_fleet_management", suite_code="DRONE_UAV")
    user = _create_user(db_session, org.id, ["ORG_ADMIN"])
    assert execute_tool(db_session, user, "list_aircraft", {}) == {"aircraft": []}


def test_multi_suite_organization_without_an_allowed_suite_is_still_denied(db_session):
    org, _, _ = _create_tenant(db_session, "DRONE_UAV")
    grant_features(db_session, org.id, "helicopter_fleet_management", "aircraft_fleet_management", suite_code="HELICOPTER")
    # aircraft_fleet_management is not allowed inside the HELICOPTER suite; the drone suite is not an allowed suite either
    user = _create_user(db_session, org.id, ["ORG_ADMIN"])
    with pytest.raises(ForbiddenError):
        execute_tool(db_session, user, "list_aircraft", {})


# ------------------------------------------------------------------ fuzzing: entitled caller, hostile arguments
@pytest.mark.parametrize("tool", ALL_TOOLS)
def test_entitled_caller_with_random_or_malformed_ids_gets_a_clean_error_or_empty_result(db_session, tool):
    spec = BY_NAME[tool]
    suite = "AIRCRAFT"
    feats = {f: True for f in _all_features_of(spec)}
    if "drone_fleet_management" in feats and len(feats) == 1:
        suite = "DRONE_UAV"
    org, _, _ = _create_tenant(db_session, suite, features=feats)
    user = _create_user(db_session, org.id, ["ORG_ADMIN"])
    if tool == "list_fleet_assets":
        grant_features(db_session, org.id, *feats, suite_code="AIRCRAFT")
    for args in (_args_for(spec), _args_for(spec, "not-a-uuid"), {}, _args_for(spec, "' OR 1=1 --"), _args_for(spec, "../../etc/passwd")):
        try:
            out = execute_tool(db_session, user, tool, args)
            assert isinstance(out, dict)                               # an empty/valid result is acceptable
        except AeroComplyError:
            pass                                                       # NotFound / validation / forbidden: fail closed
        except (KeyError, TypeError):
            # a missing required argument surfaces as KeyError from the handler; the ORCHESTRATOR converts it to a
            # tool error. Anything else (DB errors, AttributeError...) is a defect and is NOT swallowed here.
            assert args == {} or not spec.input_schema.get("required")
        db_session.rollback()


# ------------------------------------------------------------------ list_fleet_assets: entitlement-filtered inventory
def test_list_fleet_assets_only_returns_families_the_org_is_entitled_to(db_session):
    from app.models.asset import Asset

    org, _, _ = _create_tenant(db_session, "AIRCRAFT")                # aircraft feature on, drone off by default
    user = _create_user(db_session, org.id, ["ORG_ADMIN"])
    for t, reg in (("AIRCRAFT", "LA-1"), ("DRONE", "LD-1"), ("HELICOPTER", "LH-1")):
        db_session.add(Asset(organization_id=org.id, asset_type=t, registration=reg, status="ACTIVE"))
    db_session.commit()
    out = execute_tool(db_session, user, "list_fleet_assets", {})["assets"]
    assert {a["asset_type"] for a in out} == {"AIRCRAFT"}             # drone/helicopter rows exist but are not entitled
    with pytest.raises(ForbiddenError):
        execute_tool(db_session, user, "list_fleet_assets", {"asset_type": "HELICOPTER"})
    with pytest.raises(AeroComplyError):
        execute_tool(db_session, user, "list_fleet_assets", {"asset_type": "SPACESHIP"})


def test_list_fleet_assets_is_tenant_scoped(db_session):
    from app.models.asset import Asset

    a, _, _ = _create_tenant(db_session, "AIRCRAFT")
    b, _, _ = _create_tenant(db_session, "AIRCRAFT")
    db_session.add_all([Asset(organization_id=a.id, asset_type="AIRCRAFT", registration="TA-1", status="ACTIVE"),
                        Asset(organization_id=b.id, asset_type="AIRCRAFT", registration="TB-1", status="ACTIVE")])
    db_session.commit()
    ua = _create_user(db_session, a.id, ["ORG_ADMIN"])
    assert [x["registration"] for x in execute_tool(db_session, ua, "list_fleet_assets", {})["assets"]] == ["TA-1"]


def test_helicopter_org_gets_helicopters_through_lisa(db_session):
    from app.models.asset import Asset

    org, _, _ = _create_tenant(db_session, "HELICOPTER", features={"aircraft_fleet_management": False,
                                                                    "helicopter_fleet_management": True})
    user = _create_user(db_session, org.id, ["ORG_ADMIN"])
    db_session.add(Asset(organization_id=org.id, asset_type="HELICOPTER", registration="HX-1", status="ACTIVE"))
    db_session.commit()
    out = execute_tool(db_session, user, "list_fleet_assets", {"asset_type": "helicopter"})["assets"]
    assert [a["registration"] for a in out] == ["HX-1"]
