"""Platform Control Plane M1: model-level tests for the pure database/domain
foundation (no API, no service layer beyond the models/migration).

Uses db_session directly (matches tests/integration/test_lisa_conversation_context.py's
pattern for model-only tests), not the HTTP client, since M1 deliberately
ships no API surface.

Some invariants below are documented as NOT database-enforced (see comments
on each such test) -- consistent with the tradeoffs recorded in
app/models/subscription.py and app/models/tenant_entitlement.py.
"""
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.exc import IntegrityError

from app.models.organization import Organization
from app.models.plan import Plan, PlanFeature
from app.models.subscription import Subscription, SubscriptionStatus
from app.models.tenant_entitlement import TenantFeatureOverride, TenantUsageLimit
from app.models.user import User


def _make_org(db_session, name="Test Org"):
    org = Organization(name=name)
    db_session.add(org)
    db_session.commit()
    db_session.refresh(org)
    return org


def _make_user(db_session, org_id):
    user = User(
        organization_id=org_id,
        email=f"{uuid.uuid4()}@example.com",
        hashed_password="not-a-real-hash",
        full_name="Test User",
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def _make_plan(db_session, code="PRO"):
    plan = Plan(name="Pro Plan", code=code)
    db_session.add(plan)
    db_session.commit()
    db_session.refresh(plan)
    return plan


def _now():
    return datetime.now(UTC)


def test_create_plan(db_session):
    plan = _make_plan(db_session, code="STARTER")
    assert plan.id is not None
    assert plan.is_active is True
    assert plan.created_at is not None


def test_create_plan_feature(db_session):
    plan = _make_plan(db_session, code="STARTER-2")
    feature = PlanFeature(plan_id=plan.id, feature_key="LISA", enabled=True)
    db_session.add(feature)
    db_session.commit()
    db_session.refresh(feature)
    assert feature.id is not None
    assert feature.enabled is True


def test_duplicate_plan_feature_rejected(db_session):
    """DB-enforced: uq_plan_features_plan_id_feature_key."""
    plan = _make_plan(db_session, code="DUP-FEATURE")
    db_session.add(PlanFeature(plan_id=plan.id, feature_key="LISA", enabled=True))
    db_session.commit()

    db_session.add(PlanFeature(plan_id=plan.id, feature_key="LISA", enabled=False))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_create_subscription_referencing_valid_org_and_plan(db_session):
    org = _make_org(db_session, "Sub Org")
    plan = _make_plan(db_session, code="SUB-1")
    sub = Subscription(
        organization_id=org.id,
        plan_id=plan.id,
        status=SubscriptionStatus.ACTIVE,
        starts_at=_now(),
    )
    db_session.add(sub)
    db_session.commit()
    db_session.refresh(sub)
    assert sub.id is not None
    assert sub.ends_at is None  # open-ended


def test_open_ended_subscription(db_session):
    org = _make_org(db_session, "OpenEnded Org")
    plan = _make_plan(db_session, code="OPEN-1")
    sub = Subscription(
        organization_id=org.id,
        plan_id=plan.id,
        status=SubscriptionStatus.ACTIVE,
        starts_at=_now(),
        ends_at=None,
    )
    db_session.add(sub)
    db_session.commit()
    db_session.refresh(sub)
    assert sub.ends_at is None


def test_scheduled_future_subscription(db_session):
    org = _make_org(db_session, "Future Org")
    plan = _make_plan(db_session, code="FUTURE-1")
    sub = Subscription(
        organization_id=org.id,
        plan_id=plan.id,
        status=SubscriptionStatus.SCHEDULED,
        starts_at=_now() + timedelta(days=30),
    )
    db_session.add(sub)
    db_session.commit()
    db_session.refresh(sub)
    assert sub.status == SubscriptionStatus.SCHEDULED


def test_canceled_subscription_remains_historical(db_session):
    org = _make_org(db_session, "Canceled Org")
    plan = _make_plan(db_session, code="CANCELED-1")
    sub = Subscription(
        organization_id=org.id,
        plan_id=plan.id,
        status=SubscriptionStatus.CANCELED,
        starts_at=_now() - timedelta(days=60),
        ends_at=_now() - timedelta(days=1),
    )
    db_session.add(sub)
    db_session.commit()
    db_session.refresh(sub)
    fetched = db_session.get(Subscription, sub.id)
    assert fetched is not None
    assert fetched.status == SubscriptionStatus.CANCELED


def test_multiple_subscriptions_preserve_history(db_session):
    """A plan change creates a new row rather than mutating the old one --
    the entire point of a subscriptions table instead of organizations.plan_id
    (see docs/PLATFORM_CONTROL_PLANE_ARCHITECTURE.md Section 21)."""
    org = _make_org(db_session, "History Org")
    plan_a = _make_plan(db_session, code="HIST-A")
    plan_b = _make_plan(db_session, code="HIST-B")

    old_sub = Subscription(
        organization_id=org.id,
        plan_id=plan_a.id,
        status=SubscriptionStatus.CANCELED,
        starts_at=_now() - timedelta(days=90),
        ends_at=_now() - timedelta(days=30),
    )
    new_sub = Subscription(
        organization_id=org.id,
        plan_id=plan_b.id,
        status=SubscriptionStatus.ACTIVE,
        starts_at=_now() - timedelta(days=30),
    )
    db_session.add_all([old_sub, new_sub])
    db_session.commit()

    all_subs = (
        db_session.query(Subscription)
        .filter(Subscription.organization_id == org.id)
        .order_by(Subscription.starts_at)
        .all()
    )
    assert len(all_subs) == 2
    assert all_subs[0].plan_id == plan_a.id
    assert all_subs[0].status == SubscriptionStatus.CANCELED
    assert all_subs[1].plan_id == plan_b.id
    assert all_subs[1].status == SubscriptionStatus.ACTIVE


def test_overlapping_active_subscriptions_not_db_enforced(db_session):
    """Documents a deliberate M1 gap: two concurrently-ACTIVE subscriptions
    for the same org are NOT rejected by the database (see the docstring on
    Subscription in app/models/subscription.py). A future
    entitlement-resolution service must handle/reject this ambiguity."""
    org = _make_org(db_session, "Overlap Org")
    plan = _make_plan(db_session, code="OVERLAP-1")
    db_session.add(
        Subscription(
            organization_id=org.id,
            plan_id=plan.id,
            status=SubscriptionStatus.ACTIVE,
            starts_at=_now() - timedelta(days=10),
        )
    )
    db_session.commit()

    # A second ACTIVE subscription for the same org is NOT rejected today.
    db_session.add(
        Subscription(
            organization_id=org.id,
            plan_id=plan.id,
            status=SubscriptionStatus.ACTIVE,
            starts_at=_now(),
        )
    )
    db_session.commit()  # does not raise -- documents the gap

    active_count = (
        db_session.query(Subscription)
        .filter(
            Subscription.organization_id == org.id,
            Subscription.status == SubscriptionStatus.ACTIVE,
        )
        .count()
    )
    assert active_count == 2


def test_plan_cannot_be_deleted_when_referenced_by_subscription(db_session):
    org = _make_org(db_session, "Restrict Org")
    plan = _make_plan(db_session, code="RESTRICT-1")
    sub = Subscription(
        organization_id=org.id,
        plan_id=plan.id,
        status=SubscriptionStatus.ACTIVE,
        starts_at=_now(),
    )
    db_session.add(sub)
    db_session.commit()

    db_session.delete(plan)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_tenant_feature_override_referencing_valid_org(db_session):
    org = _make_org(db_session, "Override Org")
    user = _make_user(db_session, org.id)
    override = TenantFeatureOverride(
        organization_id=org.id,
        feature_key="LISA",
        enabled=True,
        reason="Support-granted trial",
        created_by_user_id=user.id,
    )
    db_session.add(override)
    db_session.commit()
    db_session.refresh(override)
    assert override.id is not None
    assert override.expires_at is None


def test_duplicate_active_override_not_db_enforced(db_session):
    """Documents a deliberate M1 gap: two simultaneously-active overrides for
    the same (organization_id, feature_key) are NOT rejected by the database
    (see the docstring on TenantFeatureOverride). A future
    entitlement-resolution service must handle/reject this ambiguity."""
    org = _make_org(db_session, "Dup Override Org")
    db_session.add(
        TenantFeatureOverride(organization_id=org.id, feature_key="LISA", enabled=True)
    )
    db_session.commit()

    db_session.add(
        TenantFeatureOverride(organization_id=org.id, feature_key="LISA", enabled=False)
    )
    db_session.commit()  # does not raise -- documents the gap

    count = (
        db_session.query(TenantFeatureOverride)
        .filter(
            TenantFeatureOverride.organization_id == org.id,
            TenantFeatureOverride.feature_key == "LISA",
        )
        .count()
    )
    assert count == 2


def test_usage_limit_referencing_valid_org(db_session):
    org = _make_org(db_session, "Limit Org")
    limit = TenantUsageLimit(
        organization_id=org.id,
        feature_key="LISA",
        limit_key="monthly_queries",
        limit_value=1000,
        is_unlimited=False,
    )
    db_session.add(limit)
    db_session.commit()
    db_session.refresh(limit)
    assert limit.id is not None
    assert limit.limit_value == 1000


def test_usage_limit_unlimited(db_session):
    org = _make_org(db_session, "Unlimited Org")
    limit = TenantUsageLimit(
        organization_id=org.id,
        feature_key="LISA",
        limit_key="monthly_queries",
        is_unlimited=True,
        limit_value=None,
    )
    db_session.add(limit)
    db_session.commit()
    db_session.refresh(limit)
    assert limit.is_unlimited is True
    assert limit.limit_value is None


def test_duplicate_usage_limit_rejected(db_session):
    """DB-enforced: uq_tenant_usage_limits_org_feature_limit."""
    org = _make_org(db_session, "Dup Limit Org")
    db_session.add(
        TenantUsageLimit(
            organization_id=org.id,
            feature_key="LISA",
            limit_key="monthly_queries",
            limit_value=100,
        )
    )
    db_session.commit()

    db_session.add(
        TenantUsageLimit(
            organization_id=org.id,
            feature_key="LISA",
            limit_key="monthly_queries",
            limit_value=200,
        )
    )
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_cross_tenant_reference_impossible_via_distinct_organization_ids(db_session):
    """Subscriptions/overrides/limits are keyed to organization_id like every
    other TenantScopedMixin table; there is no FK from one tenant's row into
    another tenant's data, and a query scoped to org A never returns org B's
    rows -- the same mechanism proven for existing tables in
    test_tenancy_isolation.py, exercised here at the model level."""
    org_a = _make_org(db_session, "Tenant A")
    org_b = _make_org(db_session, "Tenant B")
    plan = _make_plan(db_session, code="CROSS-TENANT-1")

    db_session.add(
        Subscription(
            organization_id=org_b.id,
            plan_id=plan.id,
            status=SubscriptionStatus.ACTIVE,
            starts_at=_now(),
        )
    )
    db_session.commit()

    org_a_subs = (
        db_session.query(Subscription).filter(Subscription.organization_id == org_a.id).all()
    )
    assert org_a_subs == []
