"""Read-only organization personnel directory. Deliberately minimal — a
single list function, not a user-management engine (creation/role
changes/deactivation already exist through registration and the platform
admin bootstrap flow; adding a full CRUD surface here would duplicate
those without a concrete requirement driving it yet).

This exists specifically to give the frontend a way to enumerate an
organization's users so the Technician roster (and, later, any other
personnel-picker UI) has real people to show instead of only being able
to look up a qualification by a user_id it must already know.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.user import User, UserRole


def list_organization_users(db: Session, *, organization_id: uuid.UUID) -> list[dict]:
    users = list(
        db.execute(select(User).where(User.organization_id == organization_id))
        .scalars()
        .all()
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
            "email": user.email,
            "full_name": user.full_name,
            "is_active": user.is_active,
            "roles": roles_by_user.get(user.id, []),
            "created_at": user.created_at,
        }
        for user in users
    ]
