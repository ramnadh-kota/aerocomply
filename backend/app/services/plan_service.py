"""M5: mutation layer for the M1 plan catalog (Plan / PlanFeature).

Plans and plan-features are global platform-catalog data (see
app/models/plan.py's module docstring) -- they carry no organization_id of
their own, so cross-org manipulation is structurally impossible here. Every
mutation in this module is called only from routes gated by
``Permission.PLATFORM_MANAGE`` (see app/api/v1/platform.py) and follows the
exact create/flush/audit/commit transaction pattern established by
app/services/platform_service.py and app/services/aircraft_service.py:

  1. mutate the ORM object and ``db.flush()`` inside a try/except that
     translates a unique-constraint ``IntegrityError`` into a clean
     ``ConflictError`` (never lets a raw DB exception leak to the API layer).
  2. record the audit event (still uncommitted).
  3. ``db.commit()``.

Because a flush failure raises before the audit event is ever added, and
the whole thing rolls back together on that failure, a duplicate-code (or
duplicate plan-feature) conflict can never leave a partial plan row or an
orphaned audit event behind (see docs addendum, "M5" section, for the
transaction-safety argument in full).

Audit attribution: plans/plan-features have no natural tenant subject, so
(per M4's review and the verified absence of any concrete "Platform
Operations org" lookup mechanism in this codebase -- see docs addendum) each
mutation is attributed to the *acting platform admin's own*
``organization_id`` (already available, already NOT NULL, and exactly the
value every other platform_service.py mutation already trusts from
``CurrentUser``). This requires no new lookup-by-name convention and keeps
``AuditEvent.organization_id`` NOT NULL exactly as it already is.

This module makes zero changes to app/services/entitlement_service.py --
it produces rows that M2 already correctly reads (Plan.is_active,
PlanFeature.plan_id/feature_key/enabled), nothing more.
"""

import uuid

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError
from app.models.audit_event import AuditEvent
from app.models.organization import Organization
from app.models.plan import Plan, PlanFeature, PlanLimit
from app.models.product_catalog import ProductSuite
from app.models.subscription import Subscription
from app.services.audit_service import record_audit_event


def _validate_suite_id(db: Session, *, suite_id: uuid.UUID | None) -> None:
    if suite_id is None:
        return
    if db.get(ProductSuite, suite_id) is None:
        raise NotFoundError("Product suite not found")


def _attach_counts(db: Session, plans: list[Plan]) -> None:
    if not plans:
        return
    plan_ids = [p.id for p in plans]
    feature_counts: dict[uuid.UUID, int] = dict(
        db.execute(
            select(PlanFeature.plan_id, func.count(PlanFeature.id))
            .where(PlanFeature.plan_id.in_(plan_ids), PlanFeature.enabled == True)
            .group_by(PlanFeature.plan_id)
        ).all()  # type: ignore[arg-type]
    )
    tenant_counts: dict[uuid.UUID, int] = dict(
        db.execute(
            select(Subscription.plan_id, func.count(func.distinct(Subscription.organization_id)))
            .where(
                Subscription.plan_id.in_(plan_ids),
                Subscription.status.in_(["ACTIVE", "TRIALING", "PAST_DUE"]),
            )
            .group_by(Subscription.plan_id)
        ).all()  # type: ignore[arg-type]
    )
    for p in plans:
        p.included_features_count = feature_counts.get(p.id, 0)
        p.tenant_count = tenant_counts.get(p.id, 0)


def create_plan(
    db: Session,
    *,
    actor_user_id: uuid.UUID | None,
    actor_organization_id: uuid.UUID,
    name: str,
    code: str,
    description: str | None = None,
    is_active: bool = True,
    suite_id: uuid.UUID | None = None,
    asset_scope: str | None = None,
) -> Plan:
    _validate_suite_id(db, suite_id=suite_id)
    plan = Plan(
        name=name,
        code=code,
        description=description,
        is_active=is_active,
        suite_id=suite_id,
        asset_scope=asset_scope,
    )
    db.add(plan)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise ConflictError(
            f"Plan code {code!r} already exists", code="duplicate_plan_code"
        ) from exc
    record_audit_event(
        db,
        organization_id=actor_organization_id,
        user_id=actor_user_id,
        action="platform.plan.created",
        entity_type="Plan",
        entity_id=plan.id,
        metadata={
            "code": code,
            "name": name,
            "suite_id": str(suite_id) if suite_id else None,
            "asset_scope": asset_scope,
        },
    )
    db.commit()
    db.refresh(plan)
    _attach_counts(db, [plan])
    return plan


def get_plan(db: Session, *, plan_id: uuid.UUID) -> Plan:
    plan = db.get(Plan, plan_id)
    if plan is None:
        raise NotFoundError("Plan not found")
    _attach_counts(db, [plan])
    return plan


def list_plans(db: Session) -> list[Plan]:
    plans = list(db.execute(select(Plan).order_by(Plan.created_at.desc())).scalars().all())
    _attach_counts(db, plans)
    return plans


def update_plan(
    db: Session,
    *,
    actor_user_id: uuid.UUID | None,
    actor_organization_id: uuid.UUID,
    plan_id: uuid.UUID,
    name: str | None = None,
    code: str | None = None,
    description: str | None = None,
    suite_id: uuid.UUID | None = None,
    asset_scope: str | None = None,
) -> Plan:
    plan = get_plan(db, plan_id=plan_id)

    updates: dict = {}
    if name is not None:
        plan.name = name
        updates["name"] = name
    if code is not None:
        plan.code = code
        updates["code"] = code
    if description is not None:
        plan.description = description
        updates["description"] = description
    if suite_id is not None and suite_id != plan.suite_id:
        _validate_suite_id(db, suite_id=suite_id)
        plan.suite_id = suite_id
        updates["suite_id"] = str(suite_id)
    if asset_scope is not None:
        plan.asset_scope = asset_scope
        updates["asset_scope"] = asset_scope

    db.add(plan)
    if updates:
        try:
            db.flush()
        except IntegrityError as exc:
            db.rollback()
            raise ConflictError(
                f"Plan code {code!r} already exists", code="duplicate_plan_code"
            ) from exc
        record_audit_event(
            db,
            organization_id=actor_organization_id,
            user_id=actor_user_id,
            action="platform.plan.updated",
            entity_type="Plan",
            entity_id=plan.id,
            metadata=updates,
        )
    db.commit()
    db.refresh(plan)
    _attach_counts(db, [plan])
    return plan


def set_plan_active(
    db: Session,
    *,
    actor_user_id: uuid.UUID | None,
    actor_organization_id: uuid.UUID,
    plan_id: uuid.UUID,
    is_active: bool,
) -> Plan:
    plan = get_plan(db, plan_id=plan_id)
    plan.is_active = is_active
    db.add(plan)
    record_audit_event(
        db,
        organization_id=actor_organization_id,
        user_id=actor_user_id,
        action="platform.plan.activated" if is_active else "platform.plan.deactivated",
        entity_type="Plan",
        entity_id=plan.id,
    )
    db.commit()
    db.refresh(plan)
    _attach_counts(db, [plan])
    return plan


def list_plan_features(db: Session, *, plan_id: uuid.UUID) -> list[PlanFeature]:
    get_plan(db, plan_id=plan_id)  # 404 if the plan itself doesn't exist
    return list(
        db.execute(select(PlanFeature).where(PlanFeature.plan_id == plan_id).order_by(PlanFeature.feature_key)).scalars().all()
    )


def create_plan_feature(
    db: Session,
    *,
    actor_user_id: uuid.UUID | None,
    actor_organization_id: uuid.UUID,
    plan_id: uuid.UUID,
    feature_key: str,
    enabled: bool = True,
) -> PlanFeature:
    get_plan(db, plan_id=plan_id)  # 404 if the plan itself doesn't exist
    feature = PlanFeature(plan_id=plan_id, feature_key=feature_key, enabled=enabled)
    db.add(feature)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise ConflictError(
            f"Feature {feature_key!r} already exists on this plan",
            code="duplicate_plan_feature",
        ) from exc
    record_audit_event(
        db,
        organization_id=actor_organization_id,
        user_id=actor_user_id,
        action="platform.plan_feature.created",
        entity_type="PlanFeature",
        entity_id=feature.id,
        metadata={"plan_id": str(plan_id), "feature_key": feature_key, "enabled": enabled},
    )
    db.commit()
    db.refresh(feature)
    return feature


def _get_plan_feature(db: Session, *, plan_id: uuid.UUID, feature_key: str) -> PlanFeature:
    feature = db.execute(
        select(PlanFeature).where(
            PlanFeature.plan_id == plan_id, PlanFeature.feature_key == feature_key
        )
    ).scalar_one_or_none()
    if feature is None:
        raise NotFoundError("Plan feature not found")
    return feature


def set_plan_feature_enabled(
    db: Session,
    *,
    actor_user_id: uuid.UUID | None,
    actor_organization_id: uuid.UUID,
    plan_id: uuid.UUID,
    feature_key: str,
    enabled: bool,
) -> PlanFeature:
    # If the feature doesn't exist yet on the plan, create it
    feature = db.execute(
        select(PlanFeature).where(
            PlanFeature.plan_id == plan_id, PlanFeature.feature_key == feature_key
        )
    ).scalar_one_or_none()
    if feature is None:
        return create_plan_feature(
            db,
            actor_user_id=actor_user_id,
            actor_organization_id=actor_organization_id,
            plan_id=plan_id,
            feature_key=feature_key,
            enabled=enabled,
        )
    feature.enabled = enabled
    db.add(feature)
    record_audit_event(
        db,
        organization_id=actor_organization_id,
        user_id=actor_user_id,
        action="platform.plan_feature.enabled" if enabled else "platform.plan_feature.disabled",
        entity_type="PlanFeature",
        entity_id=feature.id,
        metadata={"plan_id": str(plan_id), "feature_key": feature_key, "enabled": enabled},
    )
    db.commit()
    db.refresh(feature)
    return feature


def bulk_set_plan_features(
    db: Session,
    *,
    actor_user_id: uuid.UUID | None,
    actor_organization_id: uuid.UUID,
    plan_id: uuid.UUID,
    features: list[dict],
) -> list[PlanFeature]:
    plan = get_plan(db, plan_id=plan_id)
    existing_features = {
        pf.feature_key: pf
        for pf in db.execute(
            select(PlanFeature).where(PlanFeature.plan_id == plan.id)
        ).scalars().all()
    }

    modified_keys = []
    created_keys = []

    for item in features:
        key = item["feature_key"]
        enabled = bool(item.get("enabled", True))
        if key in existing_features:
            pf = existing_features[key]
            if pf.enabled != enabled:
                pf.enabled = enabled
                db.add(pf)
                modified_keys.append(f"{key}={enabled}")
        else:
            new_pf = PlanFeature(plan_id=plan.id, feature_key=key, enabled=enabled)
            db.add(new_pf)
            created_keys.append(f"{key}={enabled}")

    if modified_keys or created_keys:
        record_audit_event(
            db,
            organization_id=actor_organization_id,
            user_id=actor_user_id,
            action="platform.plan.features_updated",
            entity_type="Plan",
            entity_id=plan.id,
            metadata={
                "created": created_keys,
                "modified": modified_keys,
                "total_configured": len(features),
            },
        )
    db.commit()
    return list_plan_features(db, plan_id=plan.id)


def list_plan_limits(db: Session, *, plan_id: uuid.UUID) -> list[PlanLimit]:
    get_plan(db, plan_id=plan_id)  # 404 check
    return list(
        db.execute(
            select(PlanLimit)
            .where(PlanLimit.plan_id == plan_id)
            .order_by(PlanLimit.created_at.asc())
        )
        .scalars()
        .all()
    )


def bulk_set_plan_limits(
    db: Session,
    *,
    actor_user_id: uuid.UUID | None,
    actor_organization_id: uuid.UUID,
    plan_id: uuid.UUID,
    limits: list[dict],
) -> list[PlanLimit]:
    plan = get_plan(db, plan_id=plan_id)

    seen_keys: set[str] = set()
    for item in limits:
        key = item.get("limit_key", "").strip()
        if not key:
            raise ConflictError("limit_key cannot be empty", code="invalid_limit_key")
        if key in seen_keys:
            raise ConflictError(
                f"Duplicate limit key {key!r} in request", code="duplicate_limit_key"
            )
        seen_keys.add(key)

    existing_limits = {
        pl.limit_key: pl
        for pl in db.execute(
            select(PlanLimit).where(PlanLimit.plan_id == plan.id)
        ).scalars().all()
    }

    # Upsert provided limits
    for item in limits:
        key = item["limit_key"].strip()
        unlimited = bool(item.get("is_unlimited", False))
        val = None if unlimited else item.get("limit_value")

        if key in existing_limits:
            pl = existing_limits[key]
            if pl.limit_value != val or pl.is_unlimited != unlimited:
                prev_val = pl.limit_value
                prev_unl = pl.is_unlimited
                pl.limit_value = val
                pl.is_unlimited = unlimited
                db.add(pl)
                record_audit_event(
                    db,
                    organization_id=actor_organization_id,
                    user_id=actor_user_id,
                    action="platform.plan_limit.updated",
                    entity_type="PlanLimit",
                    entity_id=pl.id,
                    metadata={
                        "plan_id": str(plan.id),
                        "limit_key": key,
                        "previous_value": prev_val,
                        "previous_unlimited": prev_unl,
                        "new_value": val,
                        "new_unlimited": unlimited,
                    },
                )
        else:
            new_pl = PlanLimit(
                plan_id=plan.id,
                limit_key=key,
                limit_value=val,
                is_unlimited=unlimited,
            )
            db.add(new_pl)
            db.flush()
            record_audit_event(
                db,
                organization_id=actor_organization_id,
                user_id=actor_user_id,
                action="platform.plan_limit.created",
                entity_type="PlanLimit",
                entity_id=new_pl.id,
                metadata={
                    "plan_id": str(plan.id),
                    "limit_key": key,
                    "limit_value": val,
                    "is_unlimited": unlimited,
                },
            )

    # Delete intentionally excluded limits
    for key, pl in existing_limits.items():
        if key not in seen_keys:
            entity_id = pl.id
            db.delete(pl)
            record_audit_event(
                db,
                organization_id=actor_organization_id,
                user_id=actor_user_id,
                action="platform.plan_limit.removed",
                entity_type="PlanLimit",
                entity_id=entity_id,
                metadata={
                    "plan_id": str(plan.id),
                    "limit_key": key,
                    "previous_value": pl.limit_value,
                    "previous_unlimited": pl.is_unlimited,
                },
            )

    db.commit()
    return list_plan_limits(db, plan_id=plan.id)


def list_plan_subscribers(db: Session, *, plan_id: uuid.UUID) -> list[dict]:
    get_plan(db, plan_id=plan_id)  # 404 check
    stmt = (
        select(Organization, Subscription)
        .join(Subscription, Subscription.organization_id == Organization.id)
        .where(
            Subscription.plan_id == plan_id,
        )
        .order_by(Subscription.starts_at.desc())
    )
    rows = db.execute(stmt).all()
    return [
        {
            "organization_id": org.id,
            "organization_name": org.name,
            "organization_status": org.status,
            "subscription_id": sub.id,
            "subscription_status": sub.status,
            "starts_at": sub.starts_at,
            "ends_at": sub.ends_at,
        }
        for org, sub in rows
    ]


def list_plan_audit_events(
    db: Session, *, plan_id: uuid.UUID, limit: int = 50
) -> list[AuditEvent]:
    get_plan(db, plan_id=plan_id)  # 404 check
    stmt = (
        select(AuditEvent)
        .where(
            (AuditEvent.entity_type == "Plan") & (AuditEvent.entity_id == plan_id)
            | (AuditEvent.entity_type.in_(["PlanFeature", "PlanLimit"]))
        )
        .order_by(AuditEvent.created_at.desc())
        .limit(limit * 3)
    )
    all_events = list(db.execute(stmt).scalars().all())
    matching = [
        e
        for e in all_events
        if (e.entity_type == "Plan" and e.entity_id == plan_id)
        or (
            e.entity_type in ("PlanFeature", "PlanLimit")
            and (e.event_metadata or {}).get("plan_id") == str(plan_id)
        )
    ]
    return matching[:limit]


