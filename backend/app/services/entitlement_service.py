"""M2: read-side effective entitlement resolution for an organization.

This module answers exactly one question -- "given everything currently
stored about organization X's tenant status, subscription, plan, and
tenant-level adjustments, what is X entitled to right now?" -- and nothing
else. It is a pure read/derive service: it never writes, never bills, never
meters usage, and never authorizes a *user*.

Explicit non-goals (see docs/PLATFORM_CONTROL_PLANE_ARCHITECTURE.md, M1
Implementation and Section 21 addendum for the schema decisions this builds
on):
  - No RBAC / user permissions. This service's only input identity is
    ``organization_id``. It never imports ``app.models.user.User``,
    ``app.core.permissions.Permission``, or ``app.core.permissions.Role``,
    and never will -- RBAC answers "can this user act", this service answers
    "what can this tenant use", and those two questions are kept completely
    independent (the same separation ``technician_service.check_authorization``
    already draws between system role and aircraft-type qualification).
  - No usage metering/enforcement. ``TenantUsageLimit`` rows are surfaced as
    *configuration* only (see ``UsageLimitConfiguration`` below) -- no
    consumption counter exists anywhere in this codebase yet, so this service
    cannot and does not claim to enforce anything.
  - No authorization of who may write a ``TenantFeatureOverride`` row. This
    milestone is read-only; override rows are read and applied exactly as
    stored, whatever wrote them.

Tenant isolation contract: exactly like every other service in this codebase
(e.g. ``work_order_service.get_work_order(db, organization_id=..., ...)``),
``resolve_entitlements`` trusts its caller to have already derived
``organization_id`` correctly (typically from ``CurrentUser`` in a normal
tenant route, or from an explicit platform-admin flow gated by
``Permission.PLATFORM_MANAGE``). This function performs no additional
authorization of its own and never infers ``organization_id`` from any
ambient/global state.

Design decisions worth calling out explicitly (also repeated inline below):

1. PAST_DUE grants access. A lapsed payment is a billing-collection problem,
   not an instant-lockout problem, in every SaaS grace-period convention this
   codebase's docs reference -- an org should not lose its tools mid-audit
   because an invoice bounced. TRIALING, ACTIVE, and PAST_DUE all count as
   "current" statuses for step 2 below; CANCELED and SCHEDULED never do,
   regardless of date-range overlap (SCHEDULED rows are treated as "not yet
   in force" even if someone mistakenly back-dated ``starts_at``, and
   CANCELED rows are historical fact and never re-activate).
2. An inactive Plan does not silently equal "no plan". M1's own docs
   describe "inactive plans remain historically referenceable" -- marking a
   Plan inactive stops new subscriptions from being written against it, it
   does not retroactively evict existing subscribers. So an existing
   subscription pointing at an inactive Plan resolves to status
   INACTIVE_PLAN (distinct from ACTIVE) but still returns the plan's real
   feature map, not an empty one.
3. Overlapping concurrently-current subscriptions are AMBIGUOUS, never
   guessed. M1 deliberately left this DB-unenforced (see
   ``app/models/subscription.py``'s module docstring) and named the future
   entitlement service as the place that must handle it. Silently picking
   "the newest" or "the most privileged" would hide a data integrity problem
   behind a plausible-looking answer, so this service refuses to guess.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.feature_keys import (
    canonicalize_feature_key,
    get_feature_lookup_aliases,
    is_known_feature_key,
)
from app.models.organization import Organization, OrganizationStatus
from app.models.plan import Plan, PlanFeature, PlanLimit
from app.models.subscription import Subscription, SubscriptionStatus
from app.models.tenant_entitlement import TenantFeatureOverride, TenantUsageLimit

# Subscription statuses that grant access when their [starts_at, ends_at)
# window covers `as_of`. See design decision (1) in the module docstring for
# why PAST_DUE is included.
_CURRENT_GRANTING_STATUSES = frozenset(
    {
        SubscriptionStatus.TRIALING,
        SubscriptionStatus.ACTIVE,
        SubscriptionStatus.PAST_DUE,
    }
)


class EntitlementResolutionStatus(StrEnum):
    """Mirrors the AUTHORIZED/NOT_AUTHORIZED/EXPIRED/MISSING/UNKNOWN style
    already used by ``technician_service.check_authorization`` /
    ``TechnicianAuthorizationResponse``, adapted to the tenant-entitlement
    domain."""

    ACTIVE = "ACTIVE"
    INACTIVE_PLAN = "INACTIVE_PLAN"
    SUSPENDED = "SUSPENDED"
    NO_SUBSCRIPTION = "NO_SUBSCRIPTION"
    AMBIGUOUS = "AMBIGUOUS"
    INVALID = "INVALID"


@dataclass(frozen=True)
class UsageLimitConfiguration:
    """A *configured* ceiling only -- no consumption/usage counter exists in
    this codebase, so this is never "remaining" or "enforced" usage, only
    what has been set."""

    feature_key: str
    limit_key: str
    limit_value: int | None
    is_unlimited: bool


from app.models.product_catalog import ProductModule, ProductPage, ProductSuite


_SUITE_DISALLOWED_FEATURES: dict[str, set[str]] = {
    "DRONE_UAV": {
        "aircraft_fleet_management",
        "aircraft_operations",
        "aircraft_mro",
        "helicopter_fleet_management",
        "helicopter_operations",
        "evtol_fleet_management",
        "evtol_operations",
    },
    "AIRCRAFT": {
        "drone_fleet_management",
        "drone_missions",
        "battery_analytics",
        "helicopter_fleet_management",
        "helicopter_operations",
        "evtol_fleet_management",
        "evtol_operations",
    },
    "HELICOPTER": {
        "drone_fleet_management",
        "drone_missions",
        "battery_analytics",
        "aircraft_fleet_management",
        "aircraft_operations",
        "evtol_fleet_management",
        "evtol_operations",
    },
    "EVTOL_AAM": {
        "aircraft_fleet_management",
        "aircraft_operations",
        "helicopter_fleet_management",
        "helicopter_operations",
    },
}


def is_feature_allowed_for_suite(suite_code: str | None, feature_key: str) -> bool:
    """Return True if feature_key is permitted inside the given suite boundary."""
    if not suite_code:
        return True
    code = suite_code.strip().upper()
    disallowed = _SUITE_DISALLOWED_FEATURES.get(code, set())
    canonical = canonicalize_feature_key(feature_key)
    if feature_key in disallowed or canonical in disallowed:
        return False
    
    # Prefix-based domain boundary checks
    if code == "DRONE_UAV":
        if canonical.startswith("aircraft_") or canonical.startswith("helicopter_") or canonical.startswith("evtol_"):
            return False
    elif code == "AIRCRAFT":
        if canonical.startswith("drone_") or canonical.startswith("helicopter_") or canonical.startswith("evtol_"):
            return False
    elif code == "HELICOPTER":
        if canonical.startswith("aircraft_") or canonical.startswith("drone_") or canonical.startswith("evtol_"):
            return False
    elif code == "EVTOL_AAM":
        if canonical.startswith("aircraft_") or canonical.startswith("helicopter_"):
            return False

    return True


@dataclass(frozen=True)
class EntitlementResolution:
    organization_id: uuid.UUID
    resolution_status: EntitlementResolutionStatus
    organization_status: str
    subscription_id: uuid.UUID | None
    subscription_status: str | None
    suite_id: uuid.UUID | None = None
    suite_code: str | None = None
    suite_name: str | None = None
    plan_id: uuid.UUID | None = None
    plan_code: str | None = None
    plan_name: str | None = None
    modules: list[str] = field(default_factory=list)
    pages: list[str] = field(default_factory=list)
    effective_features: dict[str, bool] = field(default_factory=dict)
    usage_limits: list[UsageLimitConfiguration] = field(default_factory=list)
    active_suites: list[dict] = field(default_factory=list)
    reason: str = ""


def _apply_feature(effective: dict[str, bool], feature_key: str, enabled: bool) -> None:
    """Write `enabled` under the raw key and, for registered feature keys only,
    under its canonical key and aliases. Unregistered (ad hoc) keys are stored
    exactly as given so the map never gains keys nobody configured."""
    effective[feature_key] = enabled
    if not is_known_feature_key(feature_key):
        return
    canonical = canonicalize_feature_key(feature_key)
    effective[canonical] = enabled
    for alias in get_feature_lookup_aliases(canonical):
        effective[alias] = enabled


def _is_current(sub: Subscription, as_of: datetime) -> bool:
    if sub.status not in _CURRENT_GRANTING_STATUSES:
        return False
    if sub.starts_at > as_of:
        return False
    if sub.ends_at is not None and sub.ends_at <= as_of:
        return False
    return True


def resolve_entitlements(
    db: Session,
    *,
    organization_id: uuid.UUID,
    suite_id: uuid.UUID | None = None,
    suite_code: str | None = None,
    as_of: datetime | None = None,
) -> EntitlementResolution:
    """Resolve organization_id's effective entitlements as of `as_of`
    (default: now, UTC).

    If `suite_id` or `suite_code` is provided, resolution is scoped to that
    specific product suite. If omitted, all active suites for the organization
    are resolved. Multiple active subscriptions across distinct suites are
    co-existent and merged.
    """
    resolved_as_of = as_of if as_of is not None else datetime.now(UTC)

    organization = db.execute(
        select(Organization).where(Organization.id == organization_id)
    ).scalar_one_or_none()
    if organization is None:
        return EntitlementResolution(
            organization_id=organization_id,
            resolution_status=EntitlementResolutionStatus.INVALID,
            organization_status="UNKNOWN",
            subscription_id=None,
            subscription_status=None,
            plan_id=None,
            plan_code=None,
            reason="Organization not found.",
        )

    # Step 1: tenant status short-circuit. A suspended or soft-deleted org is
    # denied before even looking at subscriptions.
    if organization.status == OrganizationStatus.SUSPENDED:
        return EntitlementResolution(
            organization_id=organization_id,
            resolution_status=EntitlementResolutionStatus.SUSPENDED,
            organization_status=organization.status,
            subscription_id=None,
            subscription_status=None,
            plan_id=None,
            plan_code=None,
            reason=(
                "Organization is SUSPENDED; entitlements are denied without "
                "inspecting subscriptions."
            ),
        )

    if organization.deleted_at is not None:
        return EntitlementResolution(
            organization_id=organization_id,
            resolution_status=EntitlementResolutionStatus.SUSPENDED,
            organization_status="DELETED",
            subscription_id=None,
            subscription_status=None,
            plan_id=None,
            plan_code=None,
            reason=(
                "Organization is deletion-requested/soft-deleted; entitlements are denied without "
                "inspecting subscriptions."
            ),
        )

    # Step 2: Resolve target suite if requested
    target_suite_id = suite_id
    if target_suite_id is None and suite_code is not None:
        code_norm = suite_code.strip().upper()
        if code_norm == "DRONE":
            code_norm = "DRONE_UAV"
        elif code_norm == "EVTOL":
            code_norm = "EVTOL_AAM"
        matched_suite = db.execute(
            select(ProductSuite).where(ProductSuite.code == code_norm)
        ).scalar_one_or_none()
        if matched_suite:
            target_suite_id = matched_suite.id

    # Step 3: Candidate subscriptions query
    candidates_stmt = select(Subscription).where(
        Subscription.organization_id == organization_id,
        Subscription.status.in_(tuple(_CURRENT_GRANTING_STATUSES)),
        Subscription.starts_at <= resolved_as_of,
    )
    if target_suite_id is not None:
        candidates_stmt = candidates_stmt.where(Subscription.suite_id == target_suite_id)

    all_status_matching = list(db.execute(candidates_stmt).scalars().all())
    candidates = [s for s in all_status_matching if _is_current(s, resolved_as_of)]

    if not candidates:
        return EntitlementResolution(
            organization_id=organization_id,
            resolution_status=EntitlementResolutionStatus.NO_SUBSCRIPTION,
            organization_status=organization.status,
            subscription_id=None,
            subscription_status=None,
            plan_id=None,
            plan_code=None,
            reason="No current (TRIALING/ACTIVE/PAST_DUE, in-window) subscription found.",
        )

    # Check for duplicate active subscriptions on the SAME suite
    candidates_by_suite: dict[uuid.UUID | None, list[Subscription]] = {}
    for c in candidates:
        effective_suite_id = c.suite_id
        if c.plan_id:
            c_plan = db.execute(select(Plan).where(Plan.id == c.plan_id)).scalar_one_or_none()
            if c_plan is not None:
                effective_suite_id = c_plan.suite_id
        candidates_by_suite.setdefault(effective_suite_id, []).append(c)

    for s_id, suite_subs in candidates_by_suite.items():
        if len(suite_subs) > 1:
            ids = ", ".join(sorted(str(c.id) for c in suite_subs))
            return EntitlementResolution(
                organization_id=organization_id,
                resolution_status=EntitlementResolutionStatus.AMBIGUOUS,
                organization_status=organization.status,
                subscription_id=None,
                subscription_status=None,
                plan_id=None,
                plan_code=None,
                reason=(
                    f"Multiple simultaneously-current subscriptions found for suite {s_id} "
                    f"({len(suite_subs)}): {ids}. This is a data integrity issue "
                    "the resolver refuses to silently resolve by picking one."
                ),
            )

    # Case A: Exactly one active suite candidate
    if len(candidates) == 1:
        subscription = candidates[0]
        plan = db.execute(select(Plan).where(Plan.id == subscription.plan_id)).scalar_one_or_none()
        if plan is None:
            return EntitlementResolution(
                organization_id=organization_id,
                resolution_status=EntitlementResolutionStatus.INVALID,
                organization_status=organization.status,
                subscription_id=subscription.id,
                subscription_status=subscription.status,
                plan_id=subscription.plan_id,
                plan_code=None,
                reason=f"Subscription {subscription.id} references a plan that could not be found.",
            )

        suite = db.execute(select(ProductSuite).where(ProductSuite.id == plan.suite_id)).scalar_one_or_none()
        s_id = suite.id if suite else None
        s_code = suite.code if suite else None
        s_name = suite.name if suite else None

        modules: list[str] = []
        pages: list[str] = []
        if suite is not None:
            module_rows = list(
                db.execute(
                    select(ProductModule)
                    .where(ProductModule.suite_id == suite.id, ProductModule.is_active == True)
                    .order_by(ProductModule.display_order)
                ).scalars().all()
            )
            for mod in module_rows:
                modules.append(mod.code)
                page_rows = list(
                    db.execute(
                        select(ProductPage)
                        .where(ProductPage.module_id == mod.id, ProductPage.is_active == True)
                        .order_by(ProductPage.display_order)
                    ).scalars().all()
                )
                for page in page_rows:
                    if page.route:
                        pages.append(page.route)
                    pages.append(page.code)

        plan_features = list(
            db.execute(select(PlanFeature).where(PlanFeature.plan_id == plan.id)).scalars().all()
        )
        effective_features: dict[str, bool] = {}
        for pf in plan_features:
            _apply_feature(effective_features, pf.feature_key, pf.enabled)

        overrides = list(
            db.execute(
                select(TenantFeatureOverride).where(
                    TenantFeatureOverride.organization_id == organization_id,
                )
            ).scalars().all()
        )
        active_overrides = [
            o for o in overrides
            if (o.expires_at is None or o.expires_at > resolved_as_of)
            and is_feature_allowed_for_suite(s_code, o.feature_key)
        ]
        for override in active_overrides:
            _apply_feature(effective_features, override.feature_key, override.enabled)

        plan_limit_rows = list(
            db.execute(select(PlanLimit).where(PlanLimit.plan_id == plan.id)).scalars().all()
        )
        usage_limit_rows = list(
            db.execute(
                select(TenantUsageLimit).where(TenantUsageLimit.organization_id == organization_id)
            ).scalars().all()
        )
        tenant_override_map = {row.limit_key: row for row in usage_limit_rows}

        effective_limits_map: dict[str, UsageLimitConfiguration] = {}
        for pl in plan_limit_rows:
            if pl.limit_key in tenant_override_map:
                tl = tenant_override_map[pl.limit_key]
                effective_limits_map[pl.limit_key] = UsageLimitConfiguration(
                    feature_key=tl.feature_key,
                    limit_key=pl.limit_key,
                    limit_value=tl.limit_value,
                    is_unlimited=tl.is_unlimited,
                )
            else:
                effective_limits_map[pl.limit_key] = UsageLimitConfiguration(
                    feature_key=pl.limit_key,
                    limit_key=pl.limit_key,
                    limit_value=pl.limit_value,
                    is_unlimited=pl.is_unlimited,
                )

        for tl in usage_limit_rows:
            if tl.limit_key not in effective_limits_map:
                effective_limits_map[tl.limit_key] = UsageLimitConfiguration(
                    feature_key=tl.feature_key,
                    limit_key=tl.limit_key,
                    limit_value=tl.limit_value,
                    is_unlimited=tl.is_unlimited,
                )

        usage_limits = sorted(
            effective_limits_map.values(), key=lambda r: (r.feature_key, r.limit_key)
        )

        active_suites = [
            {
                "suite_id": str(s_id) if s_id else None,
                "suite_code": s_code,
                "suite_name": s_name,
                "plan_id": str(plan.id),
                "plan_code": plan.code,
                "plan_name": plan.name,
                "subscription_id": str(subscription.id),
                "subscription_status": subscription.status,
            }
        ]

        if not plan.is_active:
            return EntitlementResolution(
                organization_id=organization_id,
                resolution_status=EntitlementResolutionStatus.INACTIVE_PLAN,
                organization_status=organization.status,
                subscription_id=subscription.id,
                subscription_status=subscription.status,
                suite_id=s_id,
                suite_code=s_code,
                suite_name=s_name,
                plan_id=plan.id,
                plan_code=plan.code,
                plan_name=plan.name,
                modules=modules,
                pages=pages,
                effective_features=effective_features,
                usage_limits=usage_limits,
                active_suites=active_suites,
                reason=(
                    f"Plan {plan.code!r} is marked inactive (no new subscriptions may reference "
                    "it), but this existing subscription's features remain in effect."
                ),
            )

        return EntitlementResolution(
            organization_id=organization_id,
            resolution_status=EntitlementResolutionStatus.ACTIVE,
            organization_status=organization.status,
            subscription_id=subscription.id,
            subscription_status=subscription.status,
            suite_id=s_id,
            suite_code=s_code,
            suite_name=s_name,
            plan_id=plan.id,
            plan_code=plan.code,
            plan_name=plan.name,
            modules=modules,
            pages=pages,
            effective_features=effective_features,
            usage_limits=usage_limits,
            active_suites=active_suites,
            reason=f"Subscription {subscription.id} on plan {plan.code!r} is current.",
        )

    # Case B: Multi-suite organization (multiple distinct active suites)
    modules_set: set[str] = set()
    pages_set: set[str] = set()
    effective_features: dict[str, bool] = {}
    active_suites = []
    plan_limit_rows = []

    for sub in candidates:
        plan = db.execute(select(Plan).where(Plan.id == sub.plan_id)).scalar_one_or_none()
        if plan is None:
            continue
        suite = db.execute(select(ProductSuite).where(ProductSuite.id == plan.suite_id)).scalar_one_or_none()
        s_id = suite.id if suite else None
        s_code = suite.code if suite else None
        s_name = suite.name if suite else None

        active_suites.append(
            {
                "suite_id": str(s_id) if s_id else None,
                "suite_code": s_code,
                "suite_name": s_name,
                "plan_id": str(plan.id),
                "plan_code": plan.code,
                "plan_name": plan.name,
                "subscription_id": str(sub.id),
                "subscription_status": sub.status,
            }
        )

        if suite is not None:
            mod_rows = list(
                db.execute(
                    select(ProductModule)
                    .where(ProductModule.suite_id == suite.id, ProductModule.is_active == True)
                    .order_by(ProductModule.display_order)
                ).scalars().all()
            )
            for mod in mod_rows:
                modules_set.add(mod.code)
                p_rows = list(
                    db.execute(
                        select(ProductPage)
                        .where(ProductPage.module_id == mod.id, ProductPage.is_active == True)
                        .order_by(ProductPage.display_order)
                    ).scalars().all()
                )
                for page in p_rows:
                    if page.route:
                        pages_set.add(page.route)
                    pages_set.add(page.code)

        p_feats = list(
            db.execute(select(PlanFeature).where(PlanFeature.plan_id == plan.id)).scalars().all()
        )
        for pf in p_feats:
            if is_feature_allowed_for_suite(s_code, pf.feature_key):
                _apply_feature(effective_features, pf.feature_key, pf.enabled)

        p_limits = list(
            db.execute(select(PlanLimit).where(PlanLimit.plan_id == plan.id)).scalars().all()
        )
        plan_limit_rows.extend(p_limits)

    # Apply overrides allowed by any active suite
    active_suite_codes = {s["suite_code"] for s in active_suites if s.get("suite_code")}
    overrides = list(
        db.execute(
            select(TenantFeatureOverride).where(
                TenantFeatureOverride.organization_id == organization_id,
            )
        ).scalars().all()
    )
    for override in overrides:
        if override.expires_at is None or override.expires_at > resolved_as_of:
            if any(is_feature_allowed_for_suite(code, override.feature_key) for code in active_suite_codes):
                _apply_feature(effective_features, override.feature_key, override.enabled)

    usage_limit_rows = list(
        db.execute(
            select(TenantUsageLimit).where(TenantUsageLimit.organization_id == organization_id)
        ).scalars().all()
    )
    tenant_override_map = {row.limit_key: row for row in usage_limit_rows}

    effective_limits_map = {}
    for pl in plan_limit_rows:
        if pl.limit_key in tenant_override_map:
            tl = tenant_override_map[pl.limit_key]
            effective_limits_map[pl.limit_key] = UsageLimitConfiguration(
                feature_key=tl.feature_key,
                limit_key=pl.limit_key,
                limit_value=tl.limit_value,
                is_unlimited=tl.is_unlimited,
            )
        else:
            effective_limits_map[pl.limit_key] = UsageLimitConfiguration(
                feature_key=pl.limit_key,
                limit_key=pl.limit_key,
                limit_value=pl.limit_value,
                is_unlimited=pl.is_unlimited,
            )

    for tl in usage_limit_rows:
        if tl.limit_key not in effective_limits_map:
            effective_limits_map[tl.limit_key] = UsageLimitConfiguration(
                feature_key=tl.feature_key,
                limit_key=tl.limit_key,
                limit_value=tl.limit_value,
                is_unlimited=tl.is_unlimited,
            )

    usage_limits = sorted(
        effective_limits_map.values(), key=lambda r: (r.feature_key, r.limit_key)
    )

    primary_sub = candidates[0]
    return EntitlementResolution(
        organization_id=organization_id,
        resolution_status=EntitlementResolutionStatus.ACTIVE,
        organization_status=organization.status,
        subscription_id=primary_sub.id,
        subscription_status=primary_sub.status,
        suite_id=None,
        suite_code="MULTI_SUITE",
        suite_name="Multi-Suite Aerospace Platform",
        plan_id=None,
        plan_code="MULTI_PLAN",
        plan_name="Multi-Suite Commercial Agreements",
        modules=sorted(modules_set),
        pages=sorted(pages_set),
        effective_features=effective_features,
        usage_limits=usage_limits,
        active_suites=active_suites,
        reason=f"Organization has {len(candidates)} active multi-suite subscriptions.",
    )
