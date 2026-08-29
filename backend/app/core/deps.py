import uuid
from collections.abc import Generator

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.errors import ForbiddenError, UnauthorizedError
from app.core.permissions import Permission, permissions_for_roles
from app.core.request_context import bind_request_identity
from app.core.security import InvalidTokenError, decode_token
from app.db.session import get_db
from app.schemas.auth import CurrentUser

bearer_scheme = HTTPBearer(auto_error=False)


def get_db_session() -> Generator[Session, None, None]:
    yield from get_db()


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> CurrentUser:
    """Decode and validate the bearer token. This is the ONLY place org_id is
    trusted from — never from a request body/query param (see FOUNDATION.md §8).
    """
    if credentials is None:
        raise UnauthorizedError("Missing bearer token")

    try:
        payload = decode_token(credentials.credentials)
    except InvalidTokenError as exc:
        raise UnauthorizedError("Invalid or expired token") from exc

    if payload.get("type") != "access":
        raise UnauthorizedError("Token is not an access token")

    bind_request_identity(
        organization_id=payload["organization_id"], user_id=payload["sub"]
    )

    return CurrentUser(
        id=uuid.UUID(payload["sub"]),
        organization_id=uuid.UUID(payload["organization_id"]),
        email=payload.get("email", ""),
        full_name=payload.get("full_name", ""),
        roles=payload.get("roles", []),
    )


def require_permission(permission: Permission):
    """Dependency factory enforcing an RBAC permission at the service boundary,
    not just hidden in the UI (FOUNDATION.md §8).
    """

    def _check(current_user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        granted = permissions_for_roles(current_user.roles)
        if permission.value not in granted:
            raise ForbiddenError(f"Missing required permission: {permission.value}")
        return current_user

    return _check
