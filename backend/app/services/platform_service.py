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
from app.models.organization import Organization, OrganizationStatus
from app.models.user import User, UserRole
from app.services.audit_service import record_audit_event


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
    return [
        {
            "organization": org,
            "user_count": user_counts.get(org.id, 0),
            "aircraft_count": aircraft_counts.get(org.id, 0),
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
    return {"organization": org, "user_count": user_count, "aircraft_count": aircraft_count}


def create_organization(
    db: Session, *, actor_user_id: uuid.UUID | None, name: str
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


def create_organization_admin(
    db: Session,
    *,
    actor_user_id: uuid.UUID | None,
    organization_id: uuid.UUID,
    email: str,
    full_name: str,
    password: str,
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
    db.commit()
    db.refresh(user)
    return user
