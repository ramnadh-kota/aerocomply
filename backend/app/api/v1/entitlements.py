"""M3: thin API exposure of M2's read-only entitlement resolution.

This module contains no entitlement logic of its own -- every route below
does nothing but derive `organization_id` from the trusted source for its
authorization tier, call `entitlement_service.resolve_entitlements`, and
serialize the result. See app/services/entitlement_service.py for the actual
resolution rules and app/api/v1/platform.py for the platform-admin
authorization pattern this mirrors.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, get_db_session
from app.models.plan import Plan
from app.schemas.auth import CurrentUser
from app.schemas.entitlement import EntitlementResolutionResponse
from app.services.entitlement_service import resolve_entitlements

router = APIRouter(prefix="/entitlements", tags=["entitlements"])


def _to_response(db: Session, result) -> EntitlementResolutionResponse:
    """Enrichment only (a secondary lookup of the already-resolved plan's
    name) -- not entitlement logic. `plan_name` is not part of M2's
    EntitlementResolution dataclase, so it is fetched here for API
    convenience.
    """
    plan_name: str | None = None
    if result.plan_id is not None:
        plan = db.get(Plan, result.plan_id)
        plan_name = plan.name if plan is not None else None
    return EntitlementResolutionResponse.from_resolution(result, plan_name=plan_name)


@router.get("", response_model=EntitlementResolutionResponse)
def get_my_entitlements(
    db: Session = Depends(get_db_session),
    # No entitlement-specific permission gate: this is read-only
    # self-information about the caller's own tenant, not a privileged
    # operation, so any authenticated user of the organization may see it
    # (matches the RBAC/entitlement separation documented in
    # entitlement_service's module docstring).
    current_user: CurrentUser = Depends(get_current_user),
) -> EntitlementResolutionResponse:
    result = resolve_entitlements(db, organization_id=current_user.organization_id)
    return _to_response(db, result)
