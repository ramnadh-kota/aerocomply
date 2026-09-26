"""M21.7: backend usage limit enforcement service.

Enforces commercial PlanLimits and TenantUsageLimit ceilings before mutating
actions (asset creation, user invitation, work order creation, etc.).

Strict separation of concerns:
- RBAC answers: "Does the user have the required system permission?"
- Entitlements answer: "Does the tenant's plan/overrides include this feature?"
- Usage Limits answer: "Has the tenant reached their commercial resource ceiling?"

Raises UsageLimitExceededError (HTTP 403 Forbidden with code="usage_limit_exceeded")
when a non-unlimited limit ceiling is met or exceeded.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import UsageLimitExceededError
from app.models.asset import Asset
from app.models.user import User
from app.models.work_order import WorkOrder
from app.services.entitlement_service import (
    EntitlementResolutionStatus,
    UsageLimitConfiguration,
    resolve_entitlements,
)


def get_effective_limit(
    db: Session,
    *,
    organization_id: uuid.UUID,
    limit_key: str,
) -> UsageLimitConfiguration | None:
    """Resolves the effective usage limit for a given limit key for this organization,
    factoring in PlanLimit defaults and TenantUsageLimit overrides."""
    resolution = resolve_entitlements(db, organization_id=organization_id)
    # Check for direct key match
    for limit in resolution.usage_limits:
        if limit.limit_key == limit_key:
            return limit
    return None


def check_asset_creation_limit(
    db: Session,
    *,
    organization_id: uuid.UUID,
) -> None:
    """Verifies that the tenant has not reached their maximum asset capacity.
    Applies to max_assets."""
    limit = get_effective_limit(db, organization_id=organization_id, limit_key="max_assets")
    if limit is None or limit.is_unlimited or limit.limit_value is None:
        return

    current_count = db.execute(
        select(func.count(Asset.id)).where(
            Asset.organization_id == organization_id,
            Asset.deleted_at.is_(None),
        )
    ).scalar_one()

    if current_count >= limit.limit_value:
        raise UsageLimitExceededError(
            f"Asset limit of {limit.limit_value} reached for this organization ({current_count} active assets). "
            "Please upgrade your commercial plan to add more assets.",
            code="usage_limit_exceeded",
        )


def check_user_creation_limit(
    db: Session,
    *,
    organization_id: uuid.UUID,
) -> None:
    """Verifies that the tenant has not reached their maximum user seat capacity.
    Applies to max_users."""
    limit = get_effective_limit(db, organization_id=organization_id, limit_key="max_users")
    if limit is None or limit.is_unlimited or limit.limit_value is None:
        return

    current_count = db.execute(
        select(func.count(User.id)).where(
            User.organization_id == organization_id,
            User.is_active == True,
        )
    ).scalar_one()

    if current_count >= limit.limit_value:
        raise UsageLimitExceededError(
            f"User seat limit of {limit.limit_value} reached for this organization ({current_count} active users). "
            "Please upgrade your commercial plan to invite more team members.",
            code="usage_limit_exceeded",
        )


def check_work_order_creation_limit(
    db: Session,
    *,
    organization_id: uuid.UUID,
) -> None:
    """Verifies that the tenant has not exceeded their monthly work order allocation.
    Applies to monthly_work_orders (counted for the current calendar month)."""
    limit = get_effective_limit(
        db, organization_id=organization_id, limit_key="monthly_work_orders"
    )
    if limit is None or limit.is_unlimited or limit.limit_value is None:
        return

    now = datetime.now(UTC)
    start_of_month = datetime(now.year, now.month, 1, tzinfo=UTC)

    current_count = db.execute(
        select(func.count(WorkOrder.id)).where(
            WorkOrder.organization_id == organization_id,
            WorkOrder.deleted_at.is_(None),
            WorkOrder.created_at >= start_of_month,
        )
    ).scalar_one()

    if current_count >= limit.limit_value:
        raise UsageLimitExceededError(
            f"Monthly work order limit of {limit.limit_value} reached for this billing period ({current_count} created). "
            "Please upgrade your commercial plan to create additional work orders.",
            code="usage_limit_exceeded",
        )


def check_storage_limit(
    db: Session,
    *,
    organization_id: uuid.UUID,
    current_storage_gb: float,
    additional_gb: float = 0.0,
) -> None:
    """Verifies that storage consumption does not exceed storage_gb."""
    limit = get_effective_limit(db, organization_id=organization_id, limit_key="storage_gb")
    if limit is None or limit.is_unlimited or limit.limit_value is None:
        return

    if current_storage_gb + additional_gb > limit.limit_value:
        raise UsageLimitExceededError(
            f"Storage limit of {limit.limit_value} GB exceeded for this organization. "
            "Please upgrade your commercial plan to store more data.",
            code="usage_limit_exceeded",
        )


def check_lisa_ai_limit(
    db: Session,
    *,
    organization_id: uuid.UUID,
    current_monthly_tokens: int,
    additional_tokens: int = 0,
) -> None:
    """Verifies that monthly LISA AI token consumption does not exceed monthly_lisa_ai_tokens."""
    limit = get_effective_limit(
        db, organization_id=organization_id, limit_key="monthly_lisa_ai_tokens"
    )
    if limit is None or limit.is_unlimited or limit.limit_value is None:
        return

    if current_monthly_tokens + additional_tokens > limit.limit_value:
        raise UsageLimitExceededError(
            f"Monthly LISA AI token limit of {limit.limit_value:,} tokens reached for this organization. "
            "Please upgrade your commercial plan for additional AI intelligence capacity.",
            code="usage_limit_exceeded",
        )


def check_api_request_limit(
    db: Session,
    *,
    organization_id: uuid.UUID,
    current_monthly_requests: int,
    additional_requests: int = 1,
) -> None:
    """Verifies that monthly API request bandwidth does not exceed monthly_api_requests."""
    limit = get_effective_limit(
        db, organization_id=organization_id, limit_key="monthly_api_requests"
    )
    if limit is None or limit.is_unlimited or limit.limit_value is None:
        return

    if current_monthly_requests + additional_requests > limit.limit_value:
        raise UsageLimitExceededError(
            f"Monthly API request limit of {limit.limit_value:,} requests reached for this organization. "
            "Please upgrade your commercial plan for higher API bandwidth.",
            code="usage_limit_exceeded",
        )
