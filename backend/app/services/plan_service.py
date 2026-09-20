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

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError
from app.models.plan import Plan, PlanFeature
from app.models.product_catalog import ProductSuite
from app.services.audit_service import record_audit_event


def _validate_suite_id(db: Session, *, suite_id: uuid.UUID | None) -> None:
    """M21.4: a caller-supplied suite_id must reference a real ProductSuite
    row, checked explicitly here (rather than only relying on the DB-level
    RESTRICT FK) so a bad id 404s cleanly instead of surfacing as a raw
    IntegrityError -- same "validate before flush" spirit as the rest of
    this module's IntegrityError-to-ConflictError translation, just for a
    missing-reference case instead of a duplicate one."""
    if suite_id is None:
        return
    if db.get(ProductSuite, suite_id) is None:
        raise NotFoundError("Product suite not found")


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
) -> Plan:
    _validate_suite_id(db, suite_id=suite_id)
    plan = Plan(
        name=name, code=code, description=description, is_active=is_active, suite_id=suite_id
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
        metadata={"code": code, "name": name, "suite_id": str(suite_id) if suite_id else None},
    )
    db.commit()
    db.refresh(plan)
    return plan


def get_plan(db: Session, *, plan_id: uuid.UUID) -> Plan:
    plan = db.get(Plan, plan_id)
    if plan is None:
        raise NotFoundError("Plan not found")
    return plan


def list_plans(db: Session) -> list[Plan]:
    return list(db.execute(select(Plan).order_by(Plan.created_at.desc())).scalars().all())


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
    return plan


def set_plan_active(
    db: Session,
    *,
    actor_user_id: uuid.UUID | None,
    actor_organization_id: uuid.UUID,
    plan_id: uuid.UUID,
    is_active: bool,
) -> Plan:
    """Flip Plan.is_active only -- never deletes the row, never cascades to
    PlanFeature rows or Subscription rows (the RESTRICT FK already guarantees
    this at the DB level; this function simply never attempts a delete)."""
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
    return plan


def list_plan_features(db: Session, *, plan_id: uuid.UUID) -> list[PlanFeature]:
    get_plan(db, plan_id=plan_id)  # 404 if the plan itself doesn't exist
    return list(
        db.execute(select(PlanFeature).where(PlanFeature.plan_id == plan_id)).scalars().all()
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
    feature = _get_plan_feature(db, plan_id=plan_id, feature_key=feature_key)
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
