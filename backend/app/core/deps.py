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
from app.models.organization import Organization, OrganizationStatus
from app.schemas.auth import CurrentUser
from app.services.entitlement_service import EntitlementResolutionStatus, resolve_entitlements

bearer_scheme = HTTPBearer(auto_error=False)


def get_db_session() -> Generator[Session, None, None]:
    yield from get_db()


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db_session),
) -> CurrentUser:
    """Decode and validate the bearer token. This is the ONLY place org_id is
    trusted from — never from a request body/query param (see FOUNDATION.md §8).

    Also re-checks the caller's organization status on every request (a
    single indexed lookup) rather than trusting the JWT's roles/org_id for
    the lifetime of the token — otherwise an access token issued before an
    organization was suspended would keep working, at full privilege, for
    the rest of its TTL. Login/refresh already refuse a suspended org
    (app/services/auth_service.py); this closes the same gap for tokens
    already in a client's hands.
    """
    if credentials is None:
        raise UnauthorizedError("Missing bearer token")

    try:
        payload = decode_token(credentials.credentials)
    except InvalidTokenError as exc:
        raise UnauthorizedError("Invalid or expired token") from exc

    if payload.get("type") != "access":
        raise UnauthorizedError("Token is not an access token")

    organization_id = uuid.UUID(payload["organization_id"])

    org = db.get(Organization, organization_id)
    if org is not None and org.status == OrganizationStatus.SUSPENDED:
        raise UnauthorizedError("This organization has been suspended")

    bind_request_identity(organization_id=payload["organization_id"], user_id=payload["sub"])

    return CurrentUser(
        id=uuid.UUID(payload["sub"]),
        organization_id=organization_id,
        email=payload.get("email", ""),
        full_name=payload.get("full_name", ""),
        roles=payload.get("roles", []),
        email_verified=payload.get("email_verified", False),
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


# M17.3: the commercial-entitlement counterpart to require_permission above.
#
# RBAC (require_permission) answers "is this USER allowed to perform this
# action" -- a property of the user's role, independent of billing/plan.
# require_feature answers a completely different question: "has this
# ORGANIZATION'S subscription/plan enabled this capability at all" -- a
# property of the tenant's commercial state, independent of who the user is.
# Both are enforced server-side; neither substitutes for the other. A route
# that needs both composes two separate dependencies (matching how every
# other multi-condition FastAPI route in this codebase already stacks
# Depends(...) rather than inventing a combined abstraction):
#
#     @router.post("/flights")
#     def create_flight(
#         current_user: CurrentUser = Depends(require_permission(Permission.FLIGHT_CREATE)),
#         _entitled: CurrentUser = Depends(require_feature("drone_operations")),
#     ) -> ...
#
# feature_key is a plain string, not a Permission enum member -- entitlement
# features are plan-catalog data (Plan/PlanFeature rows, see
# app/models/plan.py), not a fixed enum the codebase controls, exactly like
# entitlement_service.resolve_entitlements's own feature_key parameters.
def require_feature(feature_key: str):
    """Dependency factory enforcing that the caller's organization currently
    has `feature_key` enabled, per entitlement_service.resolve_entitlements.

    Deliberately reuses the SAME resolution path GET /entitlements and the
    platform-admin entitlement endpoints already use (app/api/v1/
    entitlements.py, app/api/v1/platform.py) -- no second entitlement
    evaluation exists anywhere in this codebase.

    An organization only passes when resolution_status is ACTIVE or
    INACTIVE_PLAN (both cases where resolve_entitlements returns the
    subscription's real, current feature map -- see that module's design
    decision (2)) AND effective_features[feature_key] is True. SUSPENDED,
    NO_SUBSCRIPTION, AMBIGUOUS, and INVALID are always denied, since none of
    them has a trustworthy feature map to consult.
    """

    _GRANTING_STATUSES = frozenset(
        {EntitlementResolutionStatus.ACTIVE, EntitlementResolutionStatus.INACTIVE_PLAN}
    )

    def _check(
        current_user: CurrentUser = Depends(get_current_user),
        db: Session = Depends(get_db_session),
    ) -> CurrentUser:
        # organization_id comes only from the already-authenticated
        # CurrentUser (itself derived only from the validated JWT in
        # get_current_user above) -- never from any request body/query
        # param, exactly like require_permission's own contract.
        result = resolve_entitlements(db, organization_id=current_user.organization_id)
        if result.resolution_status not in _GRANTING_STATUSES or not result.effective_features.get(
            feature_key, False
        ):
            raise ForbiddenError(f"Organization is not entitled to feature: {feature_key}")
        return current_user

    return _check
