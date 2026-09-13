"""Tests for app.services.entitlement_service.resolve_entitlements.

Uses db_session directly (matches tests/integration/test_platform_control_plane.py's
conventions). Each test runs in ONE flat, non-savepointed transaction --
never call db_session.rollback() mid-test, it wipes everything committed
earlier in that same test.
"""
import inspect
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import text

from app.models.organization import Organization, OrganizationStatus
from app.models.plan import Plan, PlanFeature
from app.models.subscription import Subscription, SubscriptionStatus
from app.models.tenant_entitlement import TenantFeatureOverride, TenantUsageLimit
from app.services import entitlement_service
from app.services.entitlement_service import (
    EntitlementResolutionStatus,
    resolve_entitlements,
)


def _make_org(db_session, name="Test Org", status=OrganizationStatus.ACTIVE):
    org = Organization(name=name, status=status)
    db_session.add(org)
    db_session.commit()
    db_session.refresh(org)
    return org


def _make_plan(db_session, code="PRO", is_active=True):
    plan = Plan(name=code, code=code, is_active=is_active)
    db_session.add(plan)
    db_session.commit()
    db_session.refresh(plan)
    return plan


def _make_sub(
    db_session,
    *,
    org,
    plan,
    status=SubscriptionStatus.ACTIVE,
    starts_at=None,
    ends_at=None,
):
    sub = Subscription(
        organization_id=org.id,
        plan_id=plan.id,
        status=status,
        starts_at=starts_at or (datetime.now(UTC) - timedelta(days=1)),
        ends_at=ends_at,
    )
    db_session.add(sub)
    db_session.commit()
    db_session.refresh(sub)
    return sub


def _now():
    return datetime.now(UTC)


# 1. active org + active sub + feature enabled
def test_active_org_active_subscription_feature_enabled(db_session):
    org = _make_org(db_session, "Org1")
    plan = _make_plan(db_session, code="ORG1-PLAN")
    db_session.add(PlanFeature(plan_id=plan.id, feature_key="LISA", enabled=True))
    db_session.commit()
    _make_sub(db_session, org=org, plan=plan, status=SubscriptionStatus.ACTIVE)

    result = resolve_entitlements(db_session, organization_id=org.id)
    assert result.resolution_status == EntitlementResolutionStatus.ACTIVE
    assert result.effective_features["LISA"] is True


# 2. trialing subscription
def test_trialing_subscription_is_current(db_session):
    org = _make_org(db_session, "Org2")
    plan = _make_plan(db_session, code="ORG2-PLAN")
    _make_sub(db_session, org=org, plan=plan, status=SubscriptionStatus.TRIALING)

    result = resolve_entitlements(db_session, organization_id=org.id)
    assert result.resolution_status == EntitlementResolutionStatus.ACTIVE
    assert result.subscription_status == SubscriptionStatus.TRIALING


# 3. suspended org short-circuits
def test_suspended_org_denied_without_checking_subscription(db_session):
    org = _make_org(db_session, "Org3", status=OrganizationStatus.SUSPENDED)
    plan = _make_plan(db_session, code="ORG3-PLAN")
    _make_sub(db_session, org=org, plan=plan, status=SubscriptionStatus.ACTIVE)

    result = resolve_entitlements(db_session, organization_id=org.id)
    assert result.resolution_status == EntitlementResolutionStatus.SUSPENDED
    assert result.subscription_id is None


# 4. no subscription
def test_no_subscription(db_session):
    org = _make_org(db_session, "Org4")
    result = resolve_entitlements(db_session, organization_id=org.id)
    assert result.resolution_status == EntitlementResolutionStatus.NO_SUBSCRIPTION


# 5. expired subscription (ends_at in the past)
def test_expired_subscription(db_session):
    org = _make_org(db_session, "Org5")
    plan = _make_plan(db_session, code="ORG5-PLAN")
    _make_sub(
        db_session,
        org=org,
        plan=plan,
        status=SubscriptionStatus.ACTIVE,
        starts_at=_now() - timedelta(days=30),
        ends_at=_now() - timedelta(days=1),
    )
    result = resolve_entitlements(db_session, organization_id=org.id)
    assert result.resolution_status == EntitlementResolutionStatus.NO_SUBSCRIPTION


# 6. canceled subscription never counts, even if date range overlaps
def test_canceled_subscription_never_current(db_session):
    org = _make_org(db_session, "Org6")
    plan = _make_plan(db_session, code="ORG6-PLAN")
    _make_sub(
        db_session,
        org=org,
        plan=plan,
        status=SubscriptionStatus.CANCELED,
        starts_at=_now() - timedelta(days=10),
        ends_at=None,
    )
    result = resolve_entitlements(db_session, organization_id=org.id)
    assert result.resolution_status == EntitlementResolutionStatus.NO_SUBSCRIPTION


# 7. future scheduled subscription never counts as current
def test_scheduled_future_subscription_not_current(db_session):
    org = _make_org(db_session, "Org7")
    plan = _make_plan(db_session, code="ORG7-PLAN")
    _make_sub(
        db_session,
        org=org,
        plan=plan,
        status=SubscriptionStatus.SCHEDULED,
        starts_at=_now() + timedelta(days=10),
    )
    result = resolve_entitlements(db_session, organization_id=org.id)
    assert result.resolution_status == EntitlementResolutionStatus.NO_SUBSCRIPTION


# 8. past-due subscription still grants access (documented grace-period decision)
def test_past_due_subscription_grants_access(db_session):
    org = _make_org(db_session, "Org8")
    plan = _make_plan(db_session, code="ORG8-PLAN")
    _make_sub(db_session, org=org, plan=plan, status=SubscriptionStatus.PAST_DUE)
    result = resolve_entitlements(db_session, organization_id=org.id)
    assert result.resolution_status == EntitlementResolutionStatus.ACTIVE
    assert result.subscription_status == SubscriptionStatus.PAST_DUE


# 9. subscription referencing a missing plan (defensive path)
def test_subscription_with_missing_plan_is_invalid(db_session):
    # The RESTRICT FK makes a genuinely dangling plan_id unreachable via the
    # ORM in a real (constrained) database, so this test drives the same
    # defensive branch directly by deferring the FK check to end-of-transaction
    # via DEFERRABLE is not available here either -- instead we disable the
    # constraint trigger for this session only, insert the dangling row, then
    # re-enable it, proving resolve_entitlements handles a plan lookup miss
    # gracefully rather than crashing.
    org = _make_org(db_session, "Org9")
    plan = _make_plan(db_session, code="ORG9-PLAN")
    sub = _make_sub(db_session, org=org, plan=plan, status=SubscriptionStatus.ACTIVE)
    dangling_plan_id = uuid.uuid4()

    db_session.execute(text("ALTER TABLE subscriptions DISABLE TRIGGER ALL"))
    try:
        db_session.execute(
            text("UPDATE subscriptions SET plan_id = :plan_id WHERE id = :sub_id"),
            {"plan_id": dangling_plan_id, "sub_id": sub.id},
        )
    finally:
        db_session.execute(text("ALTER TABLE subscriptions ENABLE TRIGGER ALL"))
    db_session.flush()
    db_session.expire_all()

    result = resolve_entitlements(db_session, organization_id=org.id)
    assert result.resolution_status == EntitlementResolutionStatus.INVALID


# 10. inactive plan
def test_inactive_plan_still_resolves_with_its_features(db_session):
    org = _make_org(db_session, "Org10")
    plan = _make_plan(db_session, code="ORG10-PLAN", is_active=False)
    db_session.add(PlanFeature(plan_id=plan.id, feature_key="LISA", enabled=True))
    db_session.commit()
    _make_sub(db_session, org=org, plan=plan, status=SubscriptionStatus.ACTIVE)

    result = resolve_entitlements(db_session, organization_id=org.id)
    assert result.resolution_status == EntitlementResolutionStatus.INACTIVE_PLAN
    assert result.effective_features["LISA"] is True


# 11. plan feature enabled
def test_plan_feature_enabled(db_session):
    org = _make_org(db_session, "Org11")
    plan = _make_plan(db_session, code="ORG11-PLAN")
    db_session.add(PlanFeature(plan_id=plan.id, feature_key="FEATURE_X", enabled=True))
    db_session.commit()
    _make_sub(db_session, org=org, plan=plan)

    result = resolve_entitlements(db_session, organization_id=org.id)
    assert result.effective_features["FEATURE_X"] is True


# 12. plan feature disabled
def test_plan_feature_disabled(db_session):
    org = _make_org(db_session, "Org12")
    plan = _make_plan(db_session, code="ORG12-PLAN")
    db_session.add(PlanFeature(plan_id=plan.id, feature_key="FEATURE_Y", enabled=False))
    db_session.commit()
    _make_sub(db_session, org=org, plan=plan)

    result = resolve_entitlements(db_session, organization_id=org.id)
    assert result.effective_features["FEATURE_Y"] is False


# 13. tenant override disables a feature that the plan enables
def test_tenant_override_disables_plan_feature(db_session):
    org = _make_org(db_session, "Org13")
    plan = _make_plan(db_session, code="ORG13-PLAN")
    db_session.add(PlanFeature(plan_id=plan.id, feature_key="FEATURE_Z", enabled=True))
    db_session.commit()
    _make_sub(db_session, org=org, plan=plan)
    db_session.add(
        TenantFeatureOverride(
            organization_id=org.id, feature_key="FEATURE_Z", enabled=False
        )
    )
    db_session.commit()

    result = resolve_entitlements(db_session, organization_id=org.id)
    assert result.effective_features["FEATURE_Z"] is False


# 14. expired override ignored
def test_expired_override_is_ignored(db_session):
    org = _make_org(db_session, "Org14")
    plan = _make_plan(db_session, code="ORG14-PLAN")
    db_session.add(PlanFeature(plan_id=plan.id, feature_key="FEATURE_W", enabled=True))
    db_session.commit()
    _make_sub(db_session, org=org, plan=plan)
    db_session.add(
        TenantFeatureOverride(
            organization_id=org.id,
            feature_key="FEATURE_W",
            enabled=False,
            expires_at=_now() - timedelta(days=1),
        )
    )
    db_session.commit()

    result = resolve_entitlements(db_session, organization_id=org.id)
    assert result.effective_features["FEATURE_W"] is True


# 15. multiple simultaneous current subscriptions -> AMBIGUOUS
def test_multiple_current_subscriptions_are_ambiguous(db_session):
    org = _make_org(db_session, "Org15")
    plan = _make_plan(db_session, code="ORG15-PLAN")
    _make_sub(db_session, org=org, plan=plan, status=SubscriptionStatus.ACTIVE)
    _make_sub(db_session, org=org, plan=plan, status=SubscriptionStatus.TRIALING)

    result = resolve_entitlements(db_session, organization_id=org.id)
    assert result.resolution_status == EntitlementResolutionStatus.AMBIGUOUS
    assert result.subscription_id is None
    assert result.effective_features == {}


# 16. usage limit configured
def test_usage_limit_configured(db_session):
    org = _make_org(db_session, "Org16")
    plan = _make_plan(db_session, code="ORG16-PLAN")
    _make_sub(db_session, org=org, plan=plan)
    db_session.add(
        TenantUsageLimit(
            organization_id=org.id,
            feature_key="LISA",
            limit_key="monthly_queries",
            limit_value=1000,
            is_unlimited=False,
        )
    )
    db_session.commit()

    result = resolve_entitlements(db_session, organization_id=org.id)
    assert len(result.usage_limits) == 1
    limit = result.usage_limits[0]
    assert limit.feature_key == "LISA"
    assert limit.limit_key == "monthly_queries"
    assert limit.limit_value == 1000
    assert limit.is_unlimited is False


# 17. unlimited usage
def test_usage_limit_unlimited(db_session):
    org = _make_org(db_session, "Org17")
    plan = _make_plan(db_session, code="ORG17-PLAN")
    _make_sub(db_session, org=org, plan=plan)
    db_session.add(
        TenantUsageLimit(
            organization_id=org.id,
            feature_key="LISA",
            limit_key="monthly_queries",
            limit_value=None,
            is_unlimited=True,
        )
    )
    db_session.commit()

    result = resolve_entitlements(db_session, organization_id=org.id)
    assert result.usage_limits[0].is_unlimited is True
    assert result.usage_limits[0].limit_value is None


# 18. multiple feature keys
def test_multiple_feature_keys(db_session):
    org = _make_org(db_session, "Org18")
    plan = _make_plan(db_session, code="ORG18-PLAN")
    db_session.add_all(
        [
            PlanFeature(plan_id=plan.id, feature_key="A", enabled=True),
            PlanFeature(plan_id=plan.id, feature_key="B", enabled=False),
            PlanFeature(plan_id=plan.id, feature_key="C", enabled=True),
        ]
    )
    db_session.commit()
    _make_sub(db_session, org=org, plan=plan)

    result = resolve_entitlements(db_session, organization_id=org.id)
    assert result.effective_features == {"A": True, "B": False, "C": True}


# 19. cross-tenant isolation
def test_cross_tenant_isolation(db_session):
    org_a = _make_org(db_session, "OrgA19")
    org_b = _make_org(db_session, "OrgB19")
    plan_a = _make_plan(db_session, code="ORG19-A-PLAN")
    plan_b = _make_plan(db_session, code="ORG19-B-PLAN")
    db_session.add(PlanFeature(plan_id=plan_a.id, feature_key="A_ONLY", enabled=True))
    db_session.add(PlanFeature(plan_id=plan_b.id, feature_key="B_ONLY", enabled=True))
    db_session.commit()
    _make_sub(db_session, org=org_a, plan=plan_a)
    _make_sub(db_session, org=org_b, plan=plan_b)

    result_a = resolve_entitlements(db_session, organization_id=org_a.id)
    result_b = resolve_entitlements(db_session, organization_id=org_b.id)

    assert "A_ONLY" in result_a.effective_features
    assert "B_ONLY" not in result_a.effective_features
    assert "B_ONLY" in result_b.effective_features
    assert "A_ONLY" not in result_b.effective_features
    assert result_a.plan_id != result_b.plan_id


# 20. deterministic result ordering: identical DB state -> identical results
def test_deterministic_repeated_resolution(db_session):
    org = _make_org(db_session, "Org20")
    plan = _make_plan(db_session, code="ORG20-PLAN")
    db_session.add_all(
        [
            PlanFeature(plan_id=plan.id, feature_key="A", enabled=True),
            PlanFeature(plan_id=plan.id, feature_key="B", enabled=False),
        ]
    )
    db_session.commit()
    _make_sub(db_session, org=org, plan=plan)
    db_session.add(
        TenantUsageLimit(
            organization_id=org.id,
            feature_key="A",
            limit_key="k1",
            limit_value=5,
            is_unlimited=False,
        )
    )
    db_session.add(
        TenantUsageLimit(
            organization_id=org.id,
            feature_key="B",
            limit_key="k2",
            limit_value=None,
            is_unlimited=True,
        )
    )
    db_session.commit()

    as_of = _now()
    r1 = resolve_entitlements(db_session, organization_id=org.id, as_of=as_of)
    r2 = resolve_entitlements(db_session, organization_id=org.id, as_of=as_of)

    assert r1.effective_features == r2.effective_features
    assert r1.usage_limits == r2.usage_limits
    assert r1.resolution_status == r2.resolution_status


# 21. missing/invalid references handled gracefully (no crash) -- unknown org
def test_unknown_organization_id_handled_gracefully(db_session):
    result = resolve_entitlements(db_session, organization_id=uuid.uuid4())
    assert result.resolution_status == EntitlementResolutionStatus.INVALID


# 22. LISA is an ordinary feature_key, no special-cased behavior
def test_lisa_feature_key_has_no_special_casing(db_session):
    org_a = _make_org(db_session, "OrgLisaA")
    org_b = _make_org(db_session, "OrgLisaB")
    plan_a = _make_plan(db_session, code="LISA-PLAN-A")
    plan_b = _make_plan(db_session, code="LISA-PLAN-B")
    db_session.add(PlanFeature(plan_id=plan_a.id, feature_key="LISA", enabled=True))
    db_session.add(PlanFeature(plan_id=plan_b.id, feature_key="ORDINARY_FEATURE", enabled=True))
    db_session.commit()
    _make_sub(db_session, org=org_a, plan=plan_a)
    _make_sub(db_session, org=org_b, plan=plan_b)

    result_a = resolve_entitlements(db_session, organization_id=org_a.id)
    result_b = resolve_entitlements(db_session, organization_id=org_b.id)

    # Same resolution status/shape regardless of whether the feature_key
    # happens to be "LISA" or something else -- no special code path exists.
    assert result_a.resolution_status == result_b.resolution_status
    assert result_a.effective_features == {"LISA": True}
    assert result_b.effective_features == {"ORDINARY_FEATURE": True}


def test_service_module_never_imports_rbac_or_user():
    """Structural proof of the RBAC separation described in the module
    docstring: entitlement_service must never import User/Permission/Role.
    Checks the module's actual import statements (not prose in comments or
    docstrings, which legitimately reference these names when explaining the
    boundary)."""
    source = inspect.getsource(entitlement_service)
    import_lines = [
        line.strip()
        for line in source.splitlines()
        if line.strip().startswith("import ") or line.strip().startswith("from ")
    ]
    joined_imports = "\n".join(import_lines)
    assert "app.models.user" not in joined_imports
    assert "app.core.permissions" not in joined_imports
    assert "User" not in joined_imports
    assert "Permission" not in joined_imports
    assert "Role" not in joined_imports
