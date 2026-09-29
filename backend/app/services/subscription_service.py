"""M6: mutation layer for tenant Subscription rows.

Follows the exact create/flush/audit/commit transaction pattern established
by app/services/plan_service.py (M5): mutate, flush inside a try/except that
translates a unique/integrity conflict into ``ConflictError``, record the
audit event (still uncommitted), then commit. A flush failure raises before
the audit event is ever added, so a rejected mutation can never leave a
partial row or an orphaned audit event.

Unlike Plan/PlanFeature (global catalog data with no natural tenant
subject), a Subscription row already carries a real ``organization_id`` (via
TenantScopedMixin) -- every audit event here is attributed to *that*
organization, not the acting platform admin's own, since the mutation
clearly targets it.

This module makes zero changes to app/services/entitlement_service.py.

Subscription ambiguity (M6-G): M2 deliberately refuses to guess between
multiple simultaneously-current subscriptions for the same organization
(TRIALING/ACTIVE/PAST_DUE, overlapping date ranges) -- see
app/models/subscription.py's module docstring and M2's own reasoning. M1 did
not enforce this at the DB level, so this service validates it explicitly
before insert/update: creating or updating a subscription into a state that
would produce two simultaneously-"current" candidates for the same org is
rejected with ConflictError, never silently allowed and never auto-repaired
by deactivating the other row.
"""

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError
from app.models.organization import Organization
from app.models.plan import Plan
from app.models.subscription import Subscription, SubscriptionStatus
from app.services.audit_service import record_audit_event

# Mirrors entitlement_service._CURRENT_GRANTING_STATUSES exactly (candidacy
# rule owned by M2) -- duplicated as a small frozenset rather than imported,
# because importing a private (underscore-prefixed) name from
# entitlement_service would couple M6 to M2 internals; this is a one-line
# constant, not algorithm duplication.
_CURRENT_GRANTING_STATUSES = frozenset(
    {SubscriptionStatus.TRIALING, SubscriptionStatus.ACTIVE, SubscriptionStatus.PAST_DUE}
)

_ALL_STATUSES = frozenset(
    {
        SubscriptionStatus.TRIALING,
        SubscriptionStatus.ACTIVE,
        SubscriptionStatus.PAST_DUE,
        SubscriptionStatus.CANCELED,
        SubscriptionStatus.SCHEDULED,
    }
)

# Lifecycle transition table: no jumping CANCELED -> ACTIVE, etc. SCHEDULED
# may move forward into any "in force" status or be canceled before it ever
# starts; CANCELED is always terminal.
_ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    SubscriptionStatus.TRIALING: {
        SubscriptionStatus.ACTIVE,
        SubscriptionStatus.PAST_DUE,
        SubscriptionStatus.CANCELED,
    },
    SubscriptionStatus.ACTIVE: {
        SubscriptionStatus.PAST_DUE,
        SubscriptionStatus.CANCELED,
    },
    SubscriptionStatus.PAST_DUE: {
        SubscriptionStatus.ACTIVE,
        SubscriptionStatus.CANCELED,
    },
    SubscriptionStatus.SCHEDULED: {
        SubscriptionStatus.TRIALING,
        SubscriptionStatus.ACTIVE,
        SubscriptionStatus.CANCELED,
    },
    SubscriptionStatus.CANCELED: set(),  # terminal
}


def _validate_status(status: str) -> None:
    if status not in _ALL_STATUSES:
        raise ConflictError(f"Invalid subscription status {status!r}", code="invalid_status")


def _ranges_overlap(
    a_start: datetime, a_end: datetime | None, b_start: datetime, b_end: datetime | None
) -> bool:
    if a_end is not None and b_start >= a_end:
        return False
    if b_end is not None and a_start >= b_end:
        return False
    return True


def _assert_no_ambiguity(
    db: Session,
    *,
    organization_id: uuid.UUID,
    status: str,
    starts_at: datetime,
    ends_at: datetime | None,
    suite_id: uuid.UUID | None = None,
    exclude_subscription_id: uuid.UUID | None = None,
) -> None:
    """Reject a create/update that would produce two simultaneously-current
    (per M2's own candidacy rule) subscriptions for the same organization and suite.

    This is a read-then-write check, so two concurrent requests could both pass it. The
    organization row is locked (SELECT ... FOR UPDATE) first: subscription mutations for one
    organization are serialised until the transaction ends, and the loser then sees the winner's
    row and is rejected. (A range-exclusion constraint would need the btree_gist extension and a
    clean production dataset; the row lock needs neither.)"""
    if status not in _CURRENT_GRANTING_STATUSES:
        return
    db.execute(select(Organization.id).where(Organization.id == organization_id).with_for_update()).first()
    stmt = select(Subscription).where(
        Subscription.organization_id == organization_id,
        Subscription.status.in_(tuple(_CURRENT_GRANTING_STATUSES)),
    )
    if exclude_subscription_id is not None:
        stmt = stmt.where(Subscription.id != exclude_subscription_id)
    others = list(db.execute(stmt).scalars().all())
    for other in others:
        other_suite_id = other.suite_id
        if other.plan_id:
            other_plan = db.get(Plan, other.plan_id)
            if other_plan is not None:
                other_suite_id = other_plan.suite_id

        # If both are distinct non-None suites, they can coexist
        if suite_id is not None and other_suite_id is not None and suite_id != other_suite_id:
            continue

        if _ranges_overlap(starts_at, ends_at, other.starts_at, other.ends_at):
            raise ConflictError(
                "Creating/updating this subscription would produce two "
                f"simultaneously-current subscriptions for organization {organization_id} "
                f"in suite {suite_id or 'global'} (conflicts with subscription {other.id}).",
                code="ambiguous_subscription_state",
            )


def get_subscription(db: Session, *, subscription_id: uuid.UUID) -> Subscription:
    sub = db.get(Subscription, subscription_id)
    if sub is None:
        raise NotFoundError("Subscription not found")
    return sub


def list_subscriptions_for_org(db: Session, *, organization_id: uuid.UUID) -> list[Subscription]:
    if db.get(Organization, organization_id) is None:
        raise NotFoundError("Organization not found")
    return list(
        db.execute(
            select(Subscription)
            .where(Subscription.organization_id == organization_id)
            .order_by(Subscription.created_at.desc())
        )
        .scalars()
        .all()
    )


def create_subscription(
    db: Session,
    *,
    actor_user_id: uuid.UUID | None,
    organization_id: uuid.UUID,
    plan_id: uuid.UUID,
    status: str,
    starts_at: datetime,
    ends_at: datetime | None = None,
    suite_id: uuid.UUID | None = None,
    commit: bool = True,
) -> Subscription:
    if db.get(Organization, organization_id) is None:
        raise NotFoundError("Organization not found")
    plan = db.get(Plan, plan_id)
    if plan is None:
        raise NotFoundError("Plan not found")
    if suite_id is not None and plan.suite_id != suite_id:
        raise ConflictError(
            f"Plan '{plan.name}' ({plan.code}) does not belong to the selected product suite ({suite_id})",
            code="suite_plan_mismatch",
        )
    _validate_status(status)
    _assert_no_ambiguity(
        db,
        organization_id=organization_id,
        status=status,
        starts_at=starts_at,
        ends_at=ends_at,
        suite_id=plan.suite_id,
    )

    sub = Subscription(
        organization_id=organization_id,
        plan_id=plan_id,
        suite_id=plan.suite_id,
        status=status,
        starts_at=starts_at,
        ends_at=ends_at,
    )
    db.add(sub)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise ConflictError("Could not create subscription", code="subscription_conflict") from exc

    record_audit_event(
        db,
        organization_id=organization_id,
        user_id=actor_user_id,
        action="platform.subscription.created",
        entity_type="Subscription",
        entity_id=sub.id,
        metadata={"plan_id": str(plan_id), "suite_id": str(plan.suite_id), "status": status},
    )
    if commit:
        db.commit()
        db.refresh(sub)
    return sub


def update_subscription(
    db: Session,
    *,
    actor_user_id: uuid.UUID | None,
    subscription_id: uuid.UUID,
    status: str | None = None,
    plan_id: uuid.UUID | None = None,
    starts_at: datetime | None = None,
    ends_at: datetime | None = None,
    commit: bool = True,
) -> Subscription:
    sub = get_subscription(db, subscription_id=subscription_id)

    new_status = sub.status
    if status is not None and status != sub.status:
        _validate_status(status)
        allowed = _ALLOWED_TRANSITIONS.get(sub.status, set())
        if status not in allowed:
            raise ConflictError(
                f"Invalid subscription lifecycle transition {sub.status!r} -> {status!r}",
                code="invalid_transition",
            )
        new_status = status

    target_suite_id = sub.suite_id
    if plan_id is not None and plan_id != sub.plan_id:
        target_plan = db.get(Plan, plan_id)
        if target_plan is None:
            raise NotFoundError("Plan not found")
        if not target_plan.is_active:
            raise ConflictError(
                f"Plan '{target_plan.name}' ({target_plan.code}) is inactive and cannot be assigned",
                code="inactive_plan",
            )
        # Suite changes are deliberately unsupported: a suite is the domain
        # boundary, and moving suites would strand suite-scoped overrides and
        # limits. Re-provision under the new suite instead.
        current_suite_id = sub.suite_id
        if current_suite_id is None:
            current_plan = db.get(Plan, sub.plan_id)
            current_suite_id = current_plan.suite_id if current_plan else None
        if current_suite_id is not None and target_plan.suite_id != current_suite_id:
            raise ConflictError(
                f"Plan '{target_plan.name}' ({target_plan.code}) belongs to a different "
                "product suite than this subscription; changing suite is not supported",
                code="suite_plan_mismatch",
            )
        target_suite_id = target_plan.suite_id

    new_starts_at = starts_at if starts_at is not None else sub.starts_at
    new_ends_at = ends_at if ends_at is not None else sub.ends_at

    _assert_no_ambiguity(
        db,
        organization_id=sub.organization_id,
        status=new_status,
        starts_at=new_starts_at,
        ends_at=new_ends_at,
        suite_id=target_suite_id,
        exclude_subscription_id=sub.id,
    )

    updates: dict = {}
    if status is not None and new_status != sub.status:
        updates["previous_status"] = sub.status
        sub.status = new_status
        updates["status"] = new_status
    if plan_id is not None and plan_id != sub.plan_id:
        new_plan = db.get(Plan, plan_id)
        if new_plan is None:
            raise NotFoundError("Plan not found")
        updates["previous_plan_id"] = str(sub.plan_id)
        updates["suite_id"] = str(new_plan.suite_id)
        sub.plan_id = plan_id
        sub.suite_id = new_plan.suite_id
        updates["plan_id"] = str(plan_id)
    if starts_at is not None and starts_at != sub.starts_at:
        updates["previous_starts_at"] = sub.starts_at.isoformat()
        sub.starts_at = starts_at
        updates["starts_at"] = starts_at.isoformat()
    if ends_at is not None and ends_at != sub.ends_at:
        updates["previous_ends_at"] = sub.ends_at.isoformat() if sub.ends_at else None
        sub.ends_at = ends_at
        updates["ends_at"] = ends_at.isoformat()

    db.add(sub)
    if updates:
        try:
            db.flush()
        except IntegrityError as exc:
            db.rollback()
            raise ConflictError(
                "Could not update subscription", code="subscription_conflict"
            ) from exc
        record_audit_event(
            db,
            organization_id=sub.organization_id,
            user_id=actor_user_id,
            action="platform.subscription.updated",
            entity_type="Subscription",
            entity_id=sub.id,
            metadata=updates,
        )
    if commit:
        db.commit()
    else:
        db.flush()
    db.refresh(sub)
    return sub


def cancel_subscription(
    db: Session, *, actor_user_id: uuid.UUID | None, subscription_id: uuid.UUID, commit: bool = True
) -> Subscription:
    sub = get_subscription(db, subscription_id=subscription_id)
    allowed = _ALLOWED_TRANSITIONS.get(sub.status, set())
    if SubscriptionStatus.CANCELED not in allowed and sub.status != SubscriptionStatus.CANCELED:
        raise ConflictError(
            f"Cannot cancel a subscription in status {sub.status!r}",
            code="invalid_transition",
        )
    if sub.status == SubscriptionStatus.CANCELED:
        return sub  # idempotent no-op, no duplicate audit event
    sub.status = SubscriptionStatus.CANCELED
    db.add(sub)
    record_audit_event(
        db,
        organization_id=sub.organization_id,
        user_id=actor_user_id,
        action="platform.subscription.canceled",
        entity_type="Subscription",
        entity_id=sub.id,
    )
    if commit:
        db.commit()
    else:
        db.flush()
    db.refresh(sub)
    return sub


def schedule_subscription(
    db: Session,
    *,
    actor_user_id: uuid.UUID | None,
    organization_id: uuid.UUID,
    plan_id: uuid.UUID,
    starts_at: datetime,
    ends_at: datetime | None = None,
) -> Subscription:
    """Create a SCHEDULED subscription -- a future-dated row that is not yet
    "current" per M2's candidacy rule (SCHEDULED never grants access
    regardless of date overlap), so no ambiguity check against
    TRIALING/ACTIVE/PAST_DUE rows is needed here."""
    if db.get(Organization, organization_id) is None:
        raise NotFoundError("Organization not found")
    plan = db.get(Plan, plan_id)
    if plan is None:
        raise NotFoundError("Plan not found")

    sub = Subscription(
        organization_id=organization_id,
        plan_id=plan_id,
        suite_id=plan.suite_id,
        status=SubscriptionStatus.SCHEDULED,
        starts_at=starts_at,
        ends_at=ends_at,
    )
    db.add(sub)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise ConflictError(
            "Could not schedule subscription", code="subscription_conflict"
        ) from exc

    record_audit_event(
        db,
        organization_id=organization_id,
        user_id=actor_user_id,
        action="platform.subscription.scheduled",
        entity_type="Subscription",
        entity_id=sub.id,
        metadata={"plan_id": str(plan_id), "suite_id": str(plan.suite_id)},
    )
    db.commit()
    db.refresh(sub)
    return sub
