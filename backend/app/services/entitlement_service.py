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


@dataclass(frozen=True)
class EntitlementResolution:
    organization_id: uuid.UUID
    resolution_status: EntitlementResolutionStatus
    organization_status: str
    subscription_id: uuid.UUID | None
    subscription_status: str | None
    plan_id: uuid.UUID | None
    plan_code: str | None
    effective_features: dict[str, bool] = field(default_factory=dict)
    usage_limits: list[UsageLimitConfiguration] = field(default_factory=list)
    reason: str = ""


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
    as_of: datetime | None = None,
) -> EntitlementResolution:
    """Resolve organization_id's effective entitlements as of `as_of`
    (default: now, UTC).

    `organization_id` is trusted as caller-supplied and server-controlled --
    this function does not re-derive or authorize it. See module docstring
    for the full tenant-isolation and RBAC-separation contract.
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

    # Step 2: subscription resolution.
    candidates_stmt = select(Subscription).where(
        Subscription.organization_id == organization_id,
        Subscription.status.in_(tuple(_CURRENT_GRANTING_STATUSES)),
        Subscription.starts_at <= resolved_as_of,
    )
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

    if len(candidates) > 1:
        # Deterministic, tested, and explicit: never guess which one "wins".
        ids = ", ".join(sorted(str(c.id) for c in candidates))
        return EntitlementResolution(
            organization_id=organization_id,
            resolution_status=EntitlementResolutionStatus.AMBIGUOUS,
            organization_status=organization.status,
            subscription_id=None,
            subscription_status=None,
            plan_id=None,
            plan_code=None,
            reason=(
                "Multiple simultaneously-current subscriptions found "
                f"({len(candidates)}): {ids}. This is a data integrity issue "
                "the resolver refuses to silently resolve by picking one."
            ),
        )

    subscription = candidates[0]

    # Step 3: plan resolution.
    plan = db.execute(select(Plan).where(Plan.id == subscription.plan_id)).scalar_one_or_none()
    if plan is None:
        # Defensive only: the RESTRICT FK should make this unreachable.
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

    # Step 4: plan feature lookup.
    plan_features = list(
        db.execute(select(PlanFeature).where(PlanFeature.plan_id == plan.id)).scalars().all()
    )
    effective_features: dict[str, bool] = {pf.feature_key: pf.enabled for pf in plan_features}

    # Step 5: tenant override application (override wins; expired ignored).
    overrides = list(
        db.execute(
            select(TenantFeatureOverride).where(
                TenantFeatureOverride.organization_id == organization_id,
            )
        )
        .scalars()
        .all()
    )
    active_overrides = [
        o for o in overrides if o.expires_at is None or o.expires_at > resolved_as_of
    ]
    for override in active_overrides:
        effective_features[override.feature_key] = override.enabled

    # Step 7: usage limits (PlanLimit baseline + TenantUsageLimit overrides).
    plan_limit_rows = list(
        db.execute(select(PlanLimit).where(PlanLimit.plan_id == plan.id)).scalars().all()
    )
    usage_limit_rows = list(
        db.execute(
            select(TenantUsageLimit).where(TenantUsageLimit.organization_id == organization_id)
        )
        .scalars()
        .all()
    )
    tenant_override_map = {row.limit_key: row for row in usage_limit_rows}

    effective_limits_map: dict[str, UsageLimitConfiguration] = {}

    # Plan baseline limits
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

    # Standalone tenant usage limits not in plan baseline
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

    if not plan.is_active:
        return EntitlementResolution(
            organization_id=organization_id,
            resolution_status=EntitlementResolutionStatus.INACTIVE_PLAN,
            organization_status=organization.status,
            subscription_id=subscription.id,
            subscription_status=subscription.status,
            plan_id=plan.id,
            plan_code=plan.code,
            effective_features=effective_features,
            usage_limits=usage_limits,
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
        plan_id=plan.id,
        plan_code=plan.code,
        effective_features=effective_features,
        usage_limits=usage_limits,
        reason=f"Subscription {subscription.id} on plan {plan.code!r} is current.",
    )
