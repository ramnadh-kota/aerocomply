import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, UnauthorizedError
from app.core.permissions import Role
from app.core.security import (
    InvalidTokenError,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.models.organization import Organization
from app.models.user import User, UserRole
from app.schemas.auth import RegisterOrganizationRequest, TokenResponse
from app.services.audit_service import record_audit_event


def _roles_for_user(db: Session, user_id: uuid.UUID) -> list[str]:
    rows = db.execute(select(UserRole.role_name).where(UserRole.user_id == user_id)).scalars().all()
    return list(rows)


def _issue_tokens(user: User, roles: list[str]) -> TokenResponse:
    return TokenResponse(
        access_token=create_access_token(
            user.id, user.organization_id, roles, email=user.email, full_name=user.full_name
        ),
        refresh_token=create_refresh_token(user.id, user.organization_id),
    )


def register_organization(db: Session, payload: RegisterOrganizationRequest) -> TokenResponse:
    """Bootstrap a new tenant: creates the Organization and its first ORG_ADMIN user."""
    existing = db.execute(select(User).where(User.email == payload.admin_email)).scalar_one_or_none()
    if existing is not None:
        raise ConflictError("A user with this email already exists")

    org = Organization(name=payload.organization_name)
    db.add(org)
    db.flush()  # populate org.id

    user = User(
        organization_id=org.id,
        email=payload.admin_email,
        hashed_password=hash_password(payload.admin_password),
        full_name=payload.admin_full_name,
        is_active=True,
    )
    db.add(user)
    db.flush()

    db.add(UserRole(user_id=user.id, role_name=Role.ORG_ADMIN.value, organization_id=org.id))

    record_audit_event(
        db,
        organization_id=org.id,
        user_id=user.id,
        action="organization.register",
        entity_type="Organization",
        entity_id=org.id,
    )

    db.commit()
    return _issue_tokens(user, [Role.ORG_ADMIN.value])


def authenticate(db: Session, email: str, password: str) -> TokenResponse:
    user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if user is None or not user.is_active or not verify_password(password, user.hashed_password):
        raise UnauthorizedError("Invalid email or password")

    roles = _roles_for_user(db, user.id)

    record_audit_event(
        db,
        organization_id=user.organization_id,
        user_id=user.id,
        action="auth.login",
        entity_type="User",
        entity_id=user.id,
    )
    db.commit()

    return _issue_tokens(user, roles)


def refresh_access_token(db: Session, refresh_token: str) -> TokenResponse:
    try:
        payload = decode_token(refresh_token)
    except InvalidTokenError as exc:
        raise UnauthorizedError("Invalid or expired refresh token") from exc

    if payload.get("type") != "refresh":
        raise UnauthorizedError("Token is not a refresh token")

    user_id = uuid.UUID(payload["sub"])
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise UnauthorizedError("User no longer active")

    roles = _roles_for_user(db, user.id)
    return _issue_tokens(user, roles)
