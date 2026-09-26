"""Platform-level (cross-tenant) administration. Every function here is
deliberately NOT organization-scoped by the caller's own organization_id —
that is the entire point of a platform-admin capability — but every
endpoint that calls into this module is gated by Permission.PLATFORM_MANAGE
(see app/api/v1/platform.py), never by a frontend route check alone.

This module never exposes customer *operational* data (aircraft, work
orders, etc.) — only tenant metadata and counts needed for administration.
"""

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError
from app.core.permissions import Role
from app.core.security import hash_password
from app.models.aircraft import Aircraft
from app.models.asset import Asset, AssetType
from app.models.audit_event import AuditEvent
from app.models.organization import Organization, OrganizationStatus
from app.models.plan import Plan
from app.models.subscription import Subscription, SubscriptionStatus
from app.models.user import User, UserRole
from app.services.audit_service import record_audit_event


def get_platform_dashboard_stats(db: Session) -> dict:
    total_orgs = db.execute(select(func.count(Organization.id))).scalar_one()
    active_orgs = db.execute(
        select(func.count(Organization.id)).where(Organization.status == OrganizationStatus.ACTIVE)
    ).scalar_one()
    suspended_orgs = db.execute(
        select(func.count(Organization.id)).where(Organization.status == OrganizationStatus.SUSPENDED)
    ).scalar_one()

    active_subs = db.execute(
        select(func.count(Subscription.id)).where(Subscription.status == SubscriptionStatus.ACTIVE)
    ).scalar_one()
    trial_subs = db.execute(
        select(func.count(Subscription.id)).where(Subscription.status == SubscriptionStatus.TRIALING)
    ).scalar_one()

    total_users = db.execute(select(func.count(User.id))).scalar_one()
    total_aircraft = db.execute(select(func.count(Aircraft.id))).scalar_one()
    total_drones = db.execute(
        select(func.count(Asset.id)).where(Asset.asset_type == AssetType.DRONE.value)
    ).scalar_one()

    plan_rows = db.execute(
        select(Plan.code, Plan.name, func.count(Subscription.id))
        .join(Subscription, Plan.id == Subscription.plan_id)
        .where(Subscription.status.in_([SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIALING]))
        .group_by(Plan.code, Plan.name)
        .order_by(func.count(Subscription.id).desc())
    ).all()
    orgs_by_plan = [
        {"plan_code": code, "plan_name": name, "count": count}
        for code, name, count in plan_rows
    ]

    recent_events = list(
        db.execute(
            select(AuditEvent).order_by(AuditEvent.created_at.desc()).limit(10)
        ).scalars().all()
    )

    return {
        "total_organizations": total_orgs,
        "active_organizations": active_orgs,
        "suspended_organizations": suspended_orgs,
        "pending_provisioning": 0,
        "active_subscriptions": active_subs,
        "trial_subscriptions": trial_subs,
        "total_users": total_users,
        "total_aircraft": total_aircraft,
        "total_drones": total_drones,
        "organizations_by_plan": orgs_by_plan,
        "recent_activity": recent_events,
    }


def list_organizations(db: Session) -> list[dict]:
    orgs = list(
        db.execute(select(Organization).order_by(Organization.created_at.desc())).scalars().all()
    )
    user_counts: dict[uuid.UUID, int] = dict(
        db.execute(
            select(User.organization_id, func.count(User.id)).group_by(User.organization_id)
        ).all()  # type: ignore[arg-type]
    )
    aircraft_counts: dict[uuid.UUID, int] = dict(
        db.execute(
            select(Aircraft.organization_id, func.count(Aircraft.id)).group_by(
                Aircraft.organization_id
            )
        ).all()  # type: ignore[arg-type]
    )
    drone_counts: dict[uuid.UUID, int] = dict(
        db.execute(
            select(Asset.organization_id, func.count(Asset.id))
            .where(Asset.asset_type == AssetType.DRONE.value)
            .group_by(Asset.organization_id)
        ).all()  # type: ignore[arg-type]
    )
    return [
        {
            "organization": org,
            "user_count": user_counts.get(org.id, 0),
            "aircraft_count": aircraft_counts.get(org.id, 0),
            "drone_count": drone_counts.get(org.id, 0),
        }
        for org in orgs
    ]


def get_organization(db: Session, *, organization_id: uuid.UUID) -> Organization:
    org = db.get(Organization, organization_id)
    if org is None:
        raise NotFoundError("Organization not found")
    return org


def get_organization_with_counts(db: Session, *, organization_id: uuid.UUID) -> dict:
    org = get_organization(db, organization_id=organization_id)
    user_count = db.execute(
        select(func.count(User.id)).where(User.organization_id == org.id)
    ).scalar_one()
    aircraft_count = db.execute(
        select(func.count(Aircraft.id)).where(Aircraft.organization_id == org.id)
    ).scalar_one()
    drone_count = db.execute(
        select(func.count(Asset.id)).where(
            Asset.organization_id == org.id,
            Asset.asset_type == AssetType.DRONE.value,
        )
    ).scalar_one()
    return {
        "organization": org,
        "user_count": user_count,
        "aircraft_count": aircraft_count,
        "drone_count": drone_count,
    }


def list_organization_users(db: Session, *, organization_id: uuid.UUID) -> list[dict]:
    get_organization(db, organization_id=organization_id)
    users = list(
        db.execute(
            select(User)
            .where(User.organization_id == organization_id)
            .order_by(User.created_at.asc())
        ).scalars().all()
    )
    roles_by_user: dict[uuid.UUID, list[str]] = {}
    for user_id, role_name in db.execute(
        select(UserRole.user_id, UserRole.role_name).where(
            UserRole.organization_id == organization_id
        )
    ).all():
        roles_by_user.setdefault(user_id, []).append(role_name)

    return [
        {
            "id": user.id,
            "organization_id": user.organization_id,
            "email": user.email,
            "full_name": user.full_name,
            "is_active": user.is_active,
            "roles": roles_by_user.get(user.id, []),
            "created_at": user.created_at,
        }
        for user in users
    ]


def list_platform_users(
    db: Session,
    *,
    organization_id: uuid.UUID | None = None,
    role: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[dict]:
    stmt = (
        select(User, Organization.name.label("org_name"))
        .join(Organization, User.organization_id == Organization.id)
        .order_by(User.created_at.desc())
    )
    if organization_id is not None:
        stmt = stmt.where(User.organization_id == organization_id)
    if role is not None:
        stmt = stmt.join(UserRole, User.id == UserRole.user_id).where(UserRole.role_name == role)

    stmt = stmt.limit(limit).offset(offset)
    rows = db.execute(stmt).all()
    user_ids = [r[0].id for r in rows]

    roles_by_user: dict[uuid.UUID, list[str]] = {}
    if user_ids:
        for uid, role_name in db.execute(
            select(UserRole.user_id, UserRole.role_name).where(UserRole.user_id.in_(user_ids))
        ).all():
            roles_by_user.setdefault(uid, []).append(role_name)

    return [
        {
            "id": user.id,
            "organization_id": user.organization_id,
            "organization_name": org_name,
            "email": user.email,
            "full_name": user.full_name,
            "is_active": user.is_active,
            "roles": roles_by_user.get(user.id, []),
            "created_at": user.created_at,
        }
        for user, org_name in rows
    ]


def create_organization(
    db: Session, *, actor_user_id: uuid.UUID | None, name: str, commit: bool = True
) -> Organization:
    org = Organization(name=name, status=OrganizationStatus.ACTIVE)
    db.add(org)
    db.flush()
    record_audit_event(
        db,
        organization_id=org.id,
        user_id=actor_user_id,
        action="platform.organization.create",
        entity_type="Organization",
        entity_id=org.id,
        metadata={"name": name},
    )
    if commit:
        db.commit()
        db.refresh(org)
    return org


def set_organization_status(
    db: Session, *, actor_user_id: uuid.UUID | None, organization_id: uuid.UUID, status: str
) -> Organization:
    org = get_organization(db, organization_id=organization_id)
    org.status = status
    db.add(org)
    record_audit_event(
        db,
        organization_id=org.id,
        user_id=actor_user_id,
        action=f"platform.organization.{status.lower()}",
        entity_type="Organization",
        entity_id=org.id,
    )
    db.commit()
    db.refresh(org)
    return org


def set_organization_industry(
    db: Session, *, actor_user_id: uuid.UUID | None, organization_id: uuid.UUID, industry: str | None
) -> Organization:
    """M21.4: set (or clear, with industry=None) an organization's
    OrganizationIndustry classification. Purely a metadata tag -- never
    consulted by entitlement_service.resolve_entitlements or by any
    permission check; setting it neither grants nor revokes anything."""
    org = get_organization(db, organization_id=organization_id)
    org.industry = industry
    db.add(org)
    record_audit_event(
        db,
        organization_id=org.id,
        user_id=actor_user_id,
        action="platform.organization.industry_set",
        entity_type="Organization",
        entity_id=org.id,
        metadata={"industry": industry},
    )
    db.commit()
    db.refresh(org)
    return org


def create_organization_admin(
    db: Session,
    *,
    actor_user_id: uuid.UUID | None,
    organization_id: uuid.UUID,
    email: str,
    full_name: str,
    password: str,
    commit: bool = True,
) -> User:
    get_organization(db, organization_id=organization_id)  # raises NotFoundError if missing

    existing = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if existing is not None:
        raise ConflictError("A user with this email already exists")

    user = User(
        organization_id=organization_id,
        email=email,
        hashed_password=hash_password(password),
        full_name=full_name,
        is_active=True,
    )
    db.add(user)
    db.flush()
    db.add(
        UserRole(user_id=user.id, role_name=Role.ORG_ADMIN.value, organization_id=organization_id)
    )
    record_audit_event(
        db,
        organization_id=organization_id,
        user_id=actor_user_id,
        action="platform.organization.admin_created",
        entity_type="User",
        entity_id=user.id,
        metadata={"email": email},
    )
    if commit:
        db.commit()
        db.refresh(user)
    return user
