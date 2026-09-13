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
    exclude_subscription_id: uuid.UUID | None = None,
) -> None:
    """Reject a create/update that would produce two simultaneously-current
    (per M2's own candidacy rule) subscriptions for the same organization."""
    if status not in _CURRENT_GRANTING_STATUSES:
        return
    stmt = select(Subscription).where(
        Subscription.organization_id == organization_id,
        Subscription.status.in_(tuple(_CURRENT_GRANTING_STATUSES)),
    )
    if exclude_subscription_id is not None:
        stmt = stmt.where(Subscription.id != exclude_subscription_id)
    others = list(db.execute(stmt).scalars().all())
    for other in others:
        if _ranges_overlap(starts_at, ends_at, other.starts_at, other.ends_at):
            raise ConflictError(
                "Creating/updating this subscription would produce two "
                f"simultaneously-current subscriptions for organization {organization_id} "
                f"(conflicts with subscription {other.id}).",
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
) -> Subscription:
    if db.get(Organization, organization_id) is None:
        raise NotFoundError("Organization not found")
    if db.get(Plan, plan_id) is None:
        raise NotFoundError("Plan not found")
    _validate_status(status)
    _assert_no_ambiguity(
        db, organization_id=organization_id, status=status, starts_at=starts_at, ends_at=ends_at
    )

    sub = Subscription(
        organization_id=organization_id,
        plan_id=plan_id,
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
        metadata={"plan_id": str(plan_id), "status": status},
    )
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

    if plan_id is not None and db.get(Plan, plan_id) is None:
        raise NotFoundError("Plan not found")

    new_starts_at = starts_at if starts_at is not None else sub.starts_at
    new_ends_at = ends_at if ends_at is not None else sub.ends_at

    _assert_no_ambiguity(
        db,
        organization_id=sub.organization_id,
        status=new_status,
        starts_at=new_starts_at,
        ends_at=new_ends_at,
        exclude_subscription_id=sub.id,
    )

    updates: dict = {}
    if status is not None and new_status != sub.status:
        sub.status = new_status
        updates["status"] = new_status
    if plan_id is not None and plan_id != sub.plan_id:
        sub.plan_id = plan_id
        updates["plan_id"] = str(plan_id)
    if starts_at is not None and starts_at != sub.starts_at:
        sub.starts_at = starts_at
        updates["starts_at"] = starts_at.isoformat()
    if ends_at is not None and ends_at != sub.ends_at:
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
    db.commit()
    db.refresh(sub)
    return sub


def cancel_subscription(
    db: Session, *, actor_user_id: uuid.UUID | None, subscription_id: uuid.UUID
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
    db.commit()
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
    if db.get(Plan, plan_id) is None:
        raise NotFoundError("Plan not found")

    sub = Subscription(
        organization_id=organization_id,
        plan_id=plan_id,
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
        metadata={"plan_id": str(plan_id)},
    )
    db.commit()
    db.refresh(sub)
    return sub
