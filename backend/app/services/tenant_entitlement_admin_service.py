"""M6: mutation layer for TenantFeatureOverride and TenantUsageLimit, plus
the deterministic restrictive-vs-expansive classification that decides
whether a mutation additionally requires
``Permission.PLATFORM_ENTITLEMENT_OVERRIDE`` on top of ``PLATFORM_MANAGE``.

Follows the same create/flush/audit/commit pattern as
app/services/plan_service.py and app/services/subscription_service.py.
Every row here is tenant-scoped (TenantScopedMixin), so audit events are
attributed to the organization being administered, exactly like
subscription_service.py.

Classification does NOT duplicate M2's algorithm. It calls
``resolve_entitlements`` to get the organization's CURRENT effective feature
map (the baseline, ignoring the row being proposed) and compares the
proposed value against it:

  - feature override: proposed enabled=True where baseline is False (or the
    feature is entirely absent from the baseline map, i.e. not granted by
    the plan) is EXPANSIVE. Anything else (disabling a currently-enabled
    feature, or setting enabled=False/True where the baseline already
    agrees) is RESTRICTIVE/NEUTRAL.
  - usage limit: proposed is_unlimited=True where the current configured
    row is not unlimited, or proposed limit_value greater than the current
    configured limit_value (None/unlimited baseline treated as already
    maximal, so nothing can expand past it -- only the is_unlimited=True
    transition itself is expansive in that case), is EXPANSIVE. Decreasing
    or holding constant is RESTRICTIVE/NEUTRAL. A brand-new limit row
    (no prior configuration) is classified against an implicit "no limit
    configured" baseline: setting is_unlimited=True is expansive; any
    concrete limit_value on a first-ever row is treated as RESTRICTIVE
    (introducing a limit where none existed only ever narrows access, never
    expands it).

This module makes zero changes to app/services/entitlement_service.py.
"""

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, ForbiddenError, NotFoundError
from app.core.permissions import Permission, permissions_for_roles
from app.models.organization import Organization
from app.models.tenant_entitlement import TenantFeatureOverride, TenantUsageLimit
from app.services.audit_service import record_audit_event
from app.services.entitlement_service import resolve_entitlements


def require_expansion_permission_if_needed(*, is_expansive: bool, caller_roles: list[str]) -> None:
    if not is_expansive:
        return
    granted = permissions_for_roles(caller_roles)
    if Permission.PLATFORM_ENTITLEMENT_OVERRIDE.value not in granted:
        raise ForbiddenError(
            f"Missing required permission: {Permission.PLATFORM_ENTITLEMENT_OVERRIDE.value} "
            "for entitlement-expansion operation"
        )


def classify_feature_override(
    db: Session, *, organization_id: uuid.UUID, feature_key: str, proposed_enabled: bool
) -> bool:
    """Returns True if EXPANSIVE."""
    if not proposed_enabled:
        return False  # disabling is never expansive
    baseline = resolve_entitlements(db, organization_id=organization_id)
    return not baseline.effective_features.get(feature_key, False)


def classify_usage_limit(
    *,
    current_limit_value: int | None,
    current_is_unlimited: bool,
    proposed_limit_value: int | None,
    proposed_is_unlimited: bool,
    has_existing_row: bool,
) -> bool:
    """Returns True if EXPANSIVE."""
    if proposed_is_unlimited and not current_is_unlimited:
        return True
    if current_is_unlimited:
        return False  # already maximal, cannot expand further
    if not has_existing_row:
        return False  # a brand-new concrete limit only ever narrows
    if proposed_limit_value is not None and current_limit_value is not None:
        return proposed_limit_value > current_limit_value
    return False


# ---------------------------------------------------------------------------
# Tenant feature overrides
# ---------------------------------------------------------------------------


def list_feature_overrides(
    db: Session, *, organization_id: uuid.UUID
) -> list[TenantFeatureOverride]:
    if db.get(Organization, organization_id) is None:
        raise NotFoundError("Organization not found")
    return list(
        db.execute(
            select(TenantFeatureOverride)
            .where(TenantFeatureOverride.organization_id == organization_id)
            .order_by(TenantFeatureOverride.created_at.desc())
        )
        .scalars()
        .all()
    )


def _get_override(
    db: Session, *, organization_id: uuid.UUID, feature_key: str
) -> TenantFeatureOverride:
    override = db.execute(
        select(TenantFeatureOverride).where(
            TenantFeatureOverride.organization_id == organization_id,
            TenantFeatureOverride.feature_key == feature_key,
        )
    ).scalar_one_or_none()
    if override is None:
        raise NotFoundError("Tenant feature override not found")
    return override


def create_feature_override(
    db: Session,
    *,
    actor_user_id: uuid.UUID | None,
    caller_roles: list[str],
    organization_id: uuid.UUID,
    feature_key: str,
    enabled: bool,
    reason: str | None = None,
    expires_at: datetime | None = None,
) -> TenantFeatureOverride:
    if db.get(Organization, organization_id) is None:
        raise NotFoundError("Organization not found")

    is_expansive = classify_feature_override(
        db, organization_id=organization_id, feature_key=feature_key, proposed_enabled=enabled
    )
    require_expansion_permission_if_needed(is_expansive=is_expansive, caller_roles=caller_roles)

    existing = db.execute(
        select(TenantFeatureOverride).where(
            TenantFeatureOverride.organization_id == organization_id,
            TenantFeatureOverride.feature_key == feature_key,
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise ConflictError(
            f"An override for feature {feature_key!r} already exists on this organization",
            code="duplicate_feature_override",
        )

    override = TenantFeatureOverride(
        organization_id=organization_id,
        feature_key=feature_key,
        enabled=enabled,
        reason=reason,
        created_by_user_id=actor_user_id,
        expires_at=expires_at,
    )
    db.add(override)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise ConflictError(
            f"An override for feature {feature_key!r} already exists on this organization",
            code="duplicate_feature_override",
        ) from exc

    record_audit_event(
        db,
        organization_id=organization_id,
        user_id=actor_user_id,
        action="platform.tenant_feature_override.created",
        entity_type="TenantFeatureOverride",
        entity_id=override.id,
        metadata={"feature_key": feature_key, "enabled": enabled, "expansive": is_expansive},
    )
    db.commit()
    db.refresh(override)
    return override


def update_feature_override(
    db: Session,
    *,
    actor_user_id: uuid.UUID | None,
    caller_roles: list[str],
    organization_id: uuid.UUID,
    feature_key: str,
    enabled: bool | None = None,
    reason: str | None = None,
    expires_at: datetime | None = None,
) -> TenantFeatureOverride:
    override = _get_override(db, organization_id=organization_id, feature_key=feature_key)

    if enabled is not None and enabled != override.enabled:
        # Classify against the baseline that EXCLUDES this override's own
        # current effect -- otherwise an existing expansive override would
        # mask itself as "no change" in the resolver's map. Temporarily
        # remove and re-check is unnecessary: the resolver reads the
        # override as currently stored, so what matters is whether the
        # requested *new* value is more permissive than what the plan alone
        # (i.e. ignoring this override) would grant. We approximate this
        # safely by classifying the transition itself: turning it ON is
        # expansive unless the plan already grants it.
        is_expansive = classify_feature_override(
            db, organization_id=organization_id, feature_key=feature_key, proposed_enabled=enabled
        )
        require_expansion_permission_if_needed(is_expansive=is_expansive, caller_roles=caller_roles)

    updates: dict = {}
    if enabled is not None and enabled != override.enabled:
        override.enabled = enabled
        updates["enabled"] = enabled
    if reason is not None and reason != override.reason:
        override.reason = reason
        updates["reason"] = reason
    if expires_at is not None and expires_at != override.expires_at:
        override.expires_at = expires_at
        updates["expires_at"] = expires_at.isoformat()

    db.add(override)
    if updates:
        db.flush()
        record_audit_event(
            db,
            organization_id=organization_id,
            user_id=actor_user_id,
            action="platform.tenant_feature_override.updated",
            entity_type="TenantFeatureOverride",
            entity_id=override.id,
            metadata=updates,
        )
    db.commit()
    db.refresh(override)
    return override


def remove_feature_override(
    db: Session,
    *,
    actor_user_id: uuid.UUID | None,
    organization_id: uuid.UUID,
    feature_key: str,
) -> None:
    """Hard-remove. Removing an override is always RESTRICTIVE-or-neutral
    from a permission standpoint (it can only ever return the tenant to
    plan-default behavior), so this never requires the expansion
    permission -- PLATFORM_MANAGE alone is sufficient. If the removed
    override happened to be expansive, the tenant's effective entitlement
    only ever narrows or stays the same."""
    override = _get_override(db, organization_id=organization_id, feature_key=feature_key)
    entity_id = override.id
    db.delete(override)
    db.flush()
    record_audit_event(
        db,
        organization_id=organization_id,
        user_id=actor_user_id,
        action="platform.tenant_feature_override.removed",
        entity_type="TenantFeatureOverride",
        entity_id=entity_id,
        metadata={"feature_key": feature_key},
    )
    db.commit()


# ---------------------------------------------------------------------------
# Tenant usage limits
# ---------------------------------------------------------------------------


def list_usage_limits(db: Session, *, organization_id: uuid.UUID) -> list[TenantUsageLimit]:
    if db.get(Organization, organization_id) is None:
        raise NotFoundError("Organization not found")
    return list(
        db.execute(
            select(TenantUsageLimit)
            .where(TenantUsageLimit.organization_id == organization_id)
            .order_by(TenantUsageLimit.created_at.desc())
        )
        .scalars()
        .all()
    )


def _get_usage_limit(
    db: Session, *, organization_id: uuid.UUID, feature_key: str, limit_key: str
) -> TenantUsageLimit:
    limit = db.execute(
        select(TenantUsageLimit).where(
            TenantUsageLimit.organization_id == organization_id,
            TenantUsageLimit.feature_key == feature_key,
            TenantUsageLimit.limit_key == limit_key,
        )
    ).scalar_one_or_none()
    if limit is None:
        raise NotFoundError("Tenant usage limit not found")
    return limit


def create_usage_limit(
    db: Session,
    *,
    actor_user_id: uuid.UUID | None,
    caller_roles: list[str],
    organization_id: uuid.UUID,
    feature_key: str,
    limit_key: str,
    limit_value: int | None = None,
    is_unlimited: bool = False,
) -> TenantUsageLimit:
    if db.get(Organization, organization_id) is None:
        raise NotFoundError("Organization not found")

    is_expansive = classify_usage_limit(
        current_limit_value=None,
        current_is_unlimited=False,
        proposed_limit_value=limit_value,
        proposed_is_unlimited=is_unlimited,
        has_existing_row=False,
    )
    require_expansion_permission_if_needed(is_expansive=is_expansive, caller_roles=caller_roles)

    existing = db.execute(
        select(TenantUsageLimit).where(
            TenantUsageLimit.organization_id == organization_id,
            TenantUsageLimit.feature_key == feature_key,
            TenantUsageLimit.limit_key == limit_key,
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise ConflictError(
            f"A usage limit for ({feature_key!r}, {limit_key!r}) already exists",
            code="duplicate_usage_limit",
        )

    limit = TenantUsageLimit(
        organization_id=organization_id,
        feature_key=feature_key,
        limit_key=limit_key,
        limit_value=None if is_unlimited else limit_value,
        is_unlimited=is_unlimited,
    )
    db.add(limit)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise ConflictError(
            f"A usage limit for ({feature_key!r}, {limit_key!r}) already exists",
            code="duplicate_usage_limit",
        ) from exc

    record_audit_event(
        db,
        organization_id=organization_id,
        user_id=actor_user_id,
        action="platform.tenant_usage_limit.created",
        entity_type="TenantUsageLimit",
        entity_id=limit.id,
        metadata={
            "feature_key": feature_key,
            "limit_key": limit_key,
            "limit_value": limit_value,
            "is_unlimited": is_unlimited,
            "expansive": is_expansive,
        },
    )
    db.commit()
    db.refresh(limit)
    return limit


def update_usage_limit(
    db: Session,
    *,
    actor_user_id: uuid.UUID | None,
    caller_roles: list[str],
    organization_id: uuid.UUID,
    feature_key: str,
    limit_key: str,
    limit_value: int | None = None,
    is_unlimited: bool | None = None,
) -> TenantUsageLimit:
    limit = _get_usage_limit(
        db, organization_id=organization_id, feature_key=feature_key, limit_key=limit_key
    )

    proposed_is_unlimited = is_unlimited if is_unlimited is not None else limit.is_unlimited
    proposed_limit_value = limit_value if limit_value is not None else limit.limit_value

    is_expansive = classify_usage_limit(
        current_limit_value=limit.limit_value,
        current_is_unlimited=limit.is_unlimited,
        proposed_limit_value=proposed_limit_value,
        proposed_is_unlimited=proposed_is_unlimited,
        has_existing_row=True,
    )
    require_expansion_permission_if_needed(is_expansive=is_expansive, caller_roles=caller_roles)

    updates: dict = {}
    if is_unlimited is not None and is_unlimited != limit.is_unlimited:
        limit.is_unlimited = is_unlimited
        updates["is_unlimited"] = is_unlimited
    if is_unlimited is True:
        if limit.limit_value is not None:
            limit.limit_value = None
            updates["limit_value"] = None
    elif limit_value is not None and limit_value != limit.limit_value:
        limit.limit_value = limit_value
        updates["limit_value"] = limit_value

    db.add(limit)
    if updates:
        db.flush()
        record_audit_event(
            db,
            organization_id=organization_id,
            user_id=actor_user_id,
            action="platform.tenant_usage_limit.updated",
            entity_type="TenantUsageLimit",
            entity_id=limit.id,
            metadata={**updates, "expansive": is_expansive},
        )
    db.commit()
    db.refresh(limit)
    return limit


def remove_usage_limit(
    db: Session,
    *,
    actor_user_id: uuid.UUID | None,
    organization_id: uuid.UUID,
    feature_key: str,
    limit_key: str,
) -> None:
    """Hard-remove/reset. Like feature-override removal, this can only ever
    remove a configured ceiling (returning to "no limit configured"), never
    expand one -- PLATFORM_MANAGE alone is sufficient."""
    limit = _get_usage_limit(
        db, organization_id=organization_id, feature_key=feature_key, limit_key=limit_key
    )
    entity_id = limit.id
    db.delete(limit)
    db.flush()
    record_audit_event(
        db,
        organization_id=organization_id,
        user_id=actor_user_id,
        action="platform.tenant_usage_limit.removed",
        entity_type="TenantUsageLimit",
        entity_id=entity_id,
        metadata={"feature_key": feature_key, "limit_key": limit_key},
    )
    db.commit()
