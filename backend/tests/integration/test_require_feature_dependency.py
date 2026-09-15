"""M17.3: tests for app.core.deps.require_feature and its combination with
require_permission -- proving RBAC and entitlement are independent gates
that must BOTH pass, exactly as described in entitlement_service's own
module docstring and demonstrated end-to-end here (Phase 18's logical
trace: permission x entitlement x tenant isolation).

These call the dependency factories' inner check functions directly rather
than mounting a throwaway HTTP route -- require_permission/require_feature
are plain callables once produced by their factories (FastAPI's Depends()
wrapping is what makes them dependency-injectable in a real router; calling
them directly here exercises the exact same code path without mutating the
real app's router table for a test-only endpoint).
"""

from datetime import UTC, datetime, timedelta

import pytest

from app.core.deps import require_feature, require_permission
from app.core.errors import ForbiddenError
from app.core.permissions import Permission
from app.models.organization import Organization, OrganizationStatus
from app.models.plan import Plan, PlanFeature
from app.models.subscription import Subscription, SubscriptionStatus
from app.schemas.auth import CurrentUser


def _make_org(db_session, name="RF Org", status=OrganizationStatus.ACTIVE):
    org = Organization(name=name, status=status)
    db_session.add(org)
    db_session.commit()
    db_session.refresh(org)
    return org


def _make_plan_with_feature(db_session, *, code, feature_key, enabled):
    plan = Plan(name=code, code=code, is_active=True)
    db_session.add(plan)
    db_session.commit()
    db_session.refresh(plan)
    db_session.add(PlanFeature(plan_id=plan.id, feature_key=feature_key, enabled=enabled))
    db_session.commit()
    return plan


def _make_active_subscription(db_session, *, org, plan):
    sub = Subscription(
        organization_id=org.id,
        plan_id=plan.id,
        status=SubscriptionStatus.ACTIVE,
        starts_at=datetime.now(UTC) - timedelta(days=1),
        ends_at=None,
    )
    db_session.add(sub)
    db_session.commit()
    return sub


def _current_user(org_id, roles):
    import uuid

    return CurrentUser(
        id=uuid.uuid4(),
        organization_id=org_id,
        email="user@example.com",
        full_name="Test User",
        roles=roles,
    )


class TestRequireFeature:
    def test_grants_when_active_subscription_has_feature_enabled(self, db_session):
        org = _make_org(db_session, "RF Org 1")
        plan = _make_plan_with_feature(
            db_session, code="RF-PLAN-1", feature_key="drone_operations", enabled=True
        )
        _make_active_subscription(db_session, org=org, plan=plan)
        user = _current_user(org.id, roles=["ORG_ADMIN"])

        check = require_feature("drone_operations")
        result = check(current_user=user, db=db_session)
        assert result is user

    def test_denies_when_feature_disabled_on_plan(self, db_session):
        org = _make_org(db_session, "RF Org 2")
        plan = _make_plan_with_feature(
            db_session, code="RF-PLAN-2", feature_key="drone_operations", enabled=False
        )
        _make_active_subscription(db_session, org=org, plan=plan)
        user = _current_user(org.id, roles=["ORG_ADMIN"])

        check = require_feature("drone_operations")
        with pytest.raises(ForbiddenError):
            check(current_user=user, db=db_session)

    def test_denies_when_no_subscription_exists(self, db_session):
        org = _make_org(db_session, "RF Org 3")
        user = _current_user(org.id, roles=["ORG_ADMIN"])

        check = require_feature("drone_operations")
        with pytest.raises(ForbiddenError):
            check(current_user=user, db=db_session)

    def test_denies_when_organization_suspended_even_if_plan_has_feature(self, db_session):
        org = _make_org(db_session, "RF Org 4", status=OrganizationStatus.SUSPENDED)
        plan = _make_plan_with_feature(
            db_session, code="RF-PLAN-4", feature_key="drone_operations", enabled=True
        )
        _make_active_subscription(db_session, org=org, plan=plan)
        user = _current_user(org.id, roles=["ORG_ADMIN"])

        check = require_feature("drone_operations")
        with pytest.raises(ForbiddenError):
            check(current_user=user, db=db_session)

    def test_unknown_feature_key_is_denied_not_a_server_error(self, db_session):
        org = _make_org(db_session, "RF Org 5")
        plan = _make_plan_with_feature(
            db_session, code="RF-PLAN-5", feature_key="drone_operations", enabled=True
        )
        _make_active_subscription(db_session, org=org, plan=plan)
        user = _current_user(org.id, roles=["ORG_ADMIN"])

        check = require_feature("some_feature_that_was_never_configured")
        with pytest.raises(ForbiddenError):
            check(current_user=user, db=db_session)


class TestRbacAndEntitlementLogicalMatrix:
    """Phase 18's exact trace: permission x entitlement, both independent
    server-side gates. A route requiring both passes only when BOTH checks
    (called in sequence, as a real router would via two Depends()) succeed.
    """

    def _both_checks_pass(self, *, user, db, permission, feature_key):
        try:
            require_permission(permission)(current_user=user)
            require_feature(feature_key)(current_user=user, db=db)
            return True
        except ForbiddenError:
            return False

    def test_permission_and_entitlement_both_present_allows(self, db_session):
        org = _make_org(db_session, "Matrix Org 1")
        plan = _make_plan_with_feature(
            db_session, code="MATRIX-1", feature_key="drone_operations", enabled=True
        )
        _make_active_subscription(db_session, org=org, plan=plan)
        # MAINTENANCE_ENGINEER holds EVIDENCE_WRITE per app/core/permissions.py's
        # ROLE_PERMISSIONS -- reused here only as a real, already-defined
        # permission grant, not as a claim about drone-specific permissions
        # (none exist yet, per this milestone's explicit non-goals).
        user = _current_user(org.id, roles=["MAINTENANCE_ENGINEER"])

        assert self._both_checks_pass(
            user=user,
            db=db_session,
            permission=Permission.EVIDENCE_WRITE,
            feature_key="drone_operations",
        )

    def test_permission_present_entitlement_missing_denies(self, db_session):
        org = _make_org(db_session, "Matrix Org 2")
        plan = _make_plan_with_feature(
            db_session, code="MATRIX-2", feature_key="drone_operations", enabled=False
        )
        _make_active_subscription(db_session, org=org, plan=plan)
        user = _current_user(org.id, roles=["MAINTENANCE_ENGINEER"])

        assert not self._both_checks_pass(
            user=user,
            db=db_session,
            permission=Permission.EVIDENCE_WRITE,
            feature_key="drone_operations",
        )

    def test_permission_missing_entitlement_present_denies(self, db_session):
        org = _make_org(db_session, "Matrix Org 3")
        plan = _make_plan_with_feature(
            db_session, code="MATRIX-3", feature_key="drone_operations", enabled=True
        )
        _make_active_subscription(db_session, org=org, plan=plan)
        # VIEWER does not hold EVIDENCE_WRITE.
        user = _current_user(org.id, roles=["VIEWER"])

        assert not self._both_checks_pass(
            user=user,
            db=db_session,
            permission=Permission.EVIDENCE_WRITE,
            feature_key="drone_operations",
        )

    def test_permission_missing_entitlement_missing_denies(self, db_session):
        org = _make_org(db_session, "Matrix Org 4")
        plan = _make_plan_with_feature(
            db_session, code="MATRIX-4", feature_key="drone_operations", enabled=False
        )
        _make_active_subscription(db_session, org=org, plan=plan)
        user = _current_user(org.id, roles=["VIEWER"])

        assert not self._both_checks_pass(
            user=user,
            db=db_session,
            permission=Permission.EVIDENCE_WRITE,
            feature_key="drone_operations",
        )

    def test_tenant_isolation_org_b_entitlement_does_not_leak_to_org_a_user(self, db_session):
        org_a = _make_org(db_session, "Matrix Org A")
        org_b = _make_org(db_session, "Matrix Org B")
        # Org B has the feature; Org A has no subscription at all.
        plan_b = _make_plan_with_feature(
            db_session, code="MATRIX-B", feature_key="drone_operations", enabled=True
        )
        _make_active_subscription(db_session, org=org_b, plan=plan_b)

        user_in_org_a = _current_user(org_a.id, roles=["MAINTENANCE_ENGINEER"])

        # This user's own organization_id (org_a) is all require_feature ever
        # consults -- org B's entitlement can never leak across the tenant
        # boundary, regardless of role/permission.
        assert not self._both_checks_pass(
            user=user_in_org_a,
            db=db_session,
            permission=Permission.EVIDENCE_WRITE,
            feature_key="drone_operations",
        )
