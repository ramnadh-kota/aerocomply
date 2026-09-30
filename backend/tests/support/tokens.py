"""Test token minting that matches how production authenticates.

get_current_user now treats the DATABASE as the authority on a user's existence, activity and roles (the token's role
claim is ignored). Many fixtures build users by hand and mint a token; `mint_token` keeps them honest by making sure the
user's UserRole rows exist before signing the token, exactly as a real login would have found them."""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import create_access_token
from app.models.user import User, UserRole

_SESSION: Session | None = None


def set_session(db: Session | None) -> None:
    global _SESSION
    _SESSION = db


def mint_token(user_id: uuid.UUID, organization_id: uuid.UUID, roles: list[str], *args, **kwargs) -> str:
    db = _SESSION
    if db is not None and roles:
        user = db.get(User, user_id)
        if user is not None:
            have = set(db.execute(select(UserRole.role_name).where(UserRole.user_id == user_id)).scalars())
            for role in roles:
                name = getattr(role, "value", role)
                if name not in have:
                    db.add(UserRole(user_id=user_id, role_name=str(name), organization_id=user.organization_id))
                    have.add(str(name))
            db.flush()
    return create_access_token(user_id, organization_id, roles, *args, **kwargs)
