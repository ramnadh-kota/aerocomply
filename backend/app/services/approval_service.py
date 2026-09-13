"""M14: governance approval requests for expansive tenant entitlement
mutations.

CRITICAL PRINCIPLE this module follows: it is NOT a generic workflow
engine. It only wraps the two mutation kinds M6 already classifies as
EXPANSIVE (app/services/tenant_entitlement_admin_service.classify_feature_override
/ classify_usage_limit) -- restrictive/neutral changes never pass through
here, and this module never reimplements the actual entitlement mutation:
approval execution calls straight into
app.services.tenant_entitlement_admin_service's existing create/update
functions.

TRANSACTION SAFETY (read this before changing approve_approval_request):
tenant_entitlement_admin_service's mutation functions each commit their own
transaction (matching M5/M6's established create/flush/audit/commit
pattern). To avoid ever marking a request APPROVED while the underlying
mutation silently failed, approval execution:

  1. Atomically claims the row with a single UPDATE ... WHERE status =
     'PENDING' statement (never a read-then-write race), flushed but NOT
     committed yet.
  2. Records the governance "approved" audit event, also flushed but not
     committed.
  3. Calls the real M6 mutation function in the SAME session. That
     function's own db.commit() is what actually durably commits BOTH the
     approval's new status and the entitlement mutation together, since
     they are the same database transaction. Two real, distinct
     AuditEvent rows result (governance + entitlement mutation), which is
     correct: they represent two distinct mutations, not a duplicate.
  4. If the mutation function raises before it commits (e.g. ConflictError
     from a duplicate override, or IntegrityError translated inside M6's
     own service, which itself calls db.rollback()), nothing durable
     happens: either M6's own rollback reverts our uncommitted claim too,
     or (for errors that never call rollback explicitly) the FastAPI
     request-scoped session is closed in get_db_session's `finally` block,
     and SQLAlchemy's Session.close() rolls back any open transaction.
     Either path leaves the approval row exactly as it was before this
     call (still PENDING) -- it can never end up claiming APPROVED while
     the tenant's entitlements are unchanged.

REPLAY / CONCURRENT-APPROVAL SAFETY: the same atomic UPDATE ... WHERE
status = 'PENDING' guards every state transition (approve/reject/cancel).
A second concurrent call for the same request_id either blocks briefly on
the row's transaction lock and then affects zero rows (because the first
call's UPDATE already changed status away from PENDING), or -- if it
arrives after the first call committed -- sees zero rows updated
immediately. Either way, a second attempt raises ConflictError and the
underlying mutation is never executed twice.

SELF-APPROVAL (read before assuming this enforces "four-eyes" review):
PLATFORM_ADMIN is currently the only platform role, and it holds both
PLATFORM_MANAGE and PLATFORM_ENTITLEMENT_OVERRIDE (see
app/core/permissions.py). There is therefore no way, today, to require a
reviewer distinct from the requester without inventing a fake role split
that the rest of the platform RBAC does not support -- and this milestone
deliberately does NOT redesign platform RBAC to manufacture one. This
module does NOT block a user from approving their own request. It records
requested_by_user_id and reviewed_by_user_id as independent columns (see
app/models/approval_request.py) and the approval response/audit event
carry both, so a self-approval is always visible and honestly attributed
-- never hidden, never labeled as independently reviewed. M14 is a
governance foundation (deliberate two-step request/approve action, full
audit trail, snapshot-based deterministic review) rather than a full
four-eyes control. Do not add UI or API copy that claims otherwise.
"""

import uuid
from datetime import UTC, datetime
from typing import Any, cast

from sqlalchemy import select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError
from app.models.approval_request import (
    ALL_APPROVAL_REQUEST_TYPES,
    ApprovalRequest,
    ApprovalRequestStatus,
    ApprovalRequestType,
)
from app.models.organization import Organization
from app.services import tenant_entitlement_admin_service as tea_service
from app.services.audit_service import record_audit_event

APPROVAL_LIST_DEFAULT_LIMIT = 50
APPROVAL_LIST_MAX_LIMIT = 100


# ---------------------------------------------------------------------------
# Read
# ---------------------------------------------------------------------------


def get_approval_request(db: Session, *, approval_id: uuid.UUID) -> ApprovalRequest:
    approval = db.get(ApprovalRequest, approval_id)
    if approval is None:
        raise NotFoundError("Approval request not found")
    return approval


def list_approval_requests(
    db: Session,
    *,
    status: str | None = None,
    organization_id: uuid.UUID | None = None,
    limit: int = APPROVAL_LIST_DEFAULT_LIMIT,
    offset: int = 0,
) -> tuple[list[ApprovalRequest], int]:
    limit = max(1, min(limit, APPROVAL_LIST_MAX_LIMIT))
    offset = max(0, offset)

    filters = []
    if status is not None:
        filters.append(ApprovalRequest.status == status)
    if organization_id is not None:
        filters.append(ApprovalRequest.organization_id == organization_id)

    from sqlalchemy import func as sa_func

    count_stmt = select(sa_func.count()).select_from(ApprovalRequest)
    base_stmt = select(ApprovalRequest)
    for f in filters:
        count_stmt = count_stmt.where(f)
        base_stmt = base_stmt.where(f)

    total = db.execute(count_stmt).scalar_one()
    stmt = (
        base_stmt.order_by(ApprovalRequest.created_at.desc(), ApprovalRequest.id.desc())
        .limit(limit)
        .offset(offset)
    )
    items = list(db.execute(stmt).scalars().all())
    return items, total


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------


def create_approval_request(
    db: Session,
    *,
    actor_user_id: uuid.UUID | None,
    organization_id: uuid.UUID,
    request_type: str,
    feature_key: str,
    reason: str | None = None,
    requested_enabled: bool | None = None,
    limit_key: str | None = None,
    requested_limit_value: int | None = None,
    requested_is_unlimited: bool | None = None,
) -> ApprovalRequest:
    if db.get(Organization, organization_id) is None:
        raise NotFoundError("Organization not found")
    if request_type not in ALL_APPROVAL_REQUEST_TYPES:
        raise ConflictError(f"Invalid request_type {request_type!r}", code="invalid_request_type")

    # Reuse M6's own classification -- never re-derive expansiveness here.
    # A request that is not actually expansive has no reason to go through
    # governance at all; the caller should use the direct M6 endpoint.
    if request_type == ApprovalRequestType.FEATURE_OVERRIDE_EXPANSION:
        is_expansive = tea_service.classify_feature_override(
            db,
            organization_id=organization_id,
            feature_key=feature_key,
            proposed_enabled=bool(requested_enabled),
        )
    else:
        existing_limit = db.execute(
            select(tea_service.TenantUsageLimit).where(
                tea_service.TenantUsageLimit.organization_id == organization_id,
                tea_service.TenantUsageLimit.feature_key == feature_key,
                tea_service.TenantUsageLimit.limit_key == limit_key,
            )
        ).scalar_one_or_none()
        is_expansive = tea_service.classify_usage_limit(
            current_limit_value=existing_limit.limit_value if existing_limit else None,
            current_is_unlimited=existing_limit.is_unlimited if existing_limit else False,
            proposed_limit_value=requested_limit_value,
            proposed_is_unlimited=bool(requested_is_unlimited),
            has_existing_row=existing_limit is not None,
        )

    if not is_expansive:
        raise ConflictError(
            "The requested change is not expansive per existing entitlement "
            "classification -- it does not require approval. Use the direct "
            "administration endpoint instead.",
            code="not_expansive",
        )

    approval = ApprovalRequest(
        organization_id=organization_id,
        request_type=request_type,
        status=ApprovalRequestStatus.PENDING,
        feature_key=feature_key,
        requested_enabled=requested_enabled,
        limit_key=limit_key,
        requested_limit_value=requested_limit_value,
        requested_is_unlimited=requested_is_unlimited,
        reason=reason,
        requested_by_user_id=actor_user_id,
    )
    db.add(approval)
    db.flush()

    record_audit_event(
        db,
        organization_id=organization_id,
        user_id=actor_user_id,
        action="platform.approval_request.created",
        entity_type="ApprovalRequest",
        entity_id=approval.id,
        metadata={"request_type": request_type, "feature_key": feature_key},
    )
    db.commit()
    db.refresh(approval)
    return approval


# ---------------------------------------------------------------------------
# State transitions
# ---------------------------------------------------------------------------


def _claim_pending(db: Session, *, approval_id: uuid.UUID, new_status: str, **extra) -> None:
    """Atomically transition PENDING -> new_status. Raises NotFoundError if
    the row doesn't exist, ConflictError if it exists but is not currently
    PENDING (already decided, or a concurrent decision won the race). Never
    reads-then-writes -- this single UPDATE...WHERE is what makes replay and
    concurrent-approval safety hold (see module docstring)."""
    stmt = (
        update(ApprovalRequest)
        .where(
            ApprovalRequest.id == approval_id,
            ApprovalRequest.status == ApprovalRequestStatus.PENDING,
        )
        .values(status=new_status, **extra)
    )
    result = cast(CursorResult[Any], db.execute(stmt))
    if result.rowcount == 0:
        existing = db.get(ApprovalRequest, approval_id)
        if existing is None:
            raise NotFoundError("Approval request not found")
        raise ConflictError(
            f"Approval request {approval_id} is not PENDING (current status: {existing.status})",
            code="invalid_transition",
        )
    db.flush()


def approve_approval_request(
    db: Session,
    *,
    actor_user_id: uuid.UUID | None,
    caller_roles: list[str],
    approval_id: uuid.UUID,
    decision_reason: str | None = None,
) -> ApprovalRequest:
    approval = get_approval_request(db, approval_id=approval_id)
    if approval.status != ApprovalRequestStatus.PENDING:
        raise ConflictError(
            f"Approval request {approval_id} is not PENDING (current status: {approval.status})",
            code="invalid_transition",
        )

    now = datetime.now(UTC)
    _claim_pending(
        db,
        approval_id=approval_id,
        new_status=ApprovalRequestStatus.APPROVED,
        reviewed_by_user_id=actor_user_id,
        reviewed_at=now,
        decision_reason=decision_reason,
    )

    self_reviewed = (
        approval.requested_by_user_id is not None and approval.requested_by_user_id == actor_user_id
    )
    record_audit_event(
        db,
        organization_id=approval.organization_id,
        user_id=actor_user_id,
        action="platform.approval_request.approved",
        entity_type="ApprovalRequest",
        entity_id=approval.id,
        metadata={
            "request_type": approval.request_type,
            "feature_key": approval.feature_key,
            # Honest, unmasked record of whether requester == reviewer -- see
            # module docstring's SELF-APPROVAL section. Never omitted.
            "self_reviewed": self_reviewed,
        },
    )

    # Execute the real, canonical M6 mutation in this same session/
    # transaction. Its own db.commit() durably commits both this approval's
    # new status and the entitlement mutation together.
    if approval.request_type == ApprovalRequestType.FEATURE_OVERRIDE_EXPANSION:
        existing = db.execute(
            select(tea_service.TenantFeatureOverride).where(
                tea_service.TenantFeatureOverride.organization_id == approval.organization_id,
                tea_service.TenantFeatureOverride.feature_key == approval.feature_key,
            )
        ).scalar_one_or_none()
        if existing is not None:
            tea_service.update_feature_override(
                db,
                actor_user_id=actor_user_id,
                caller_roles=caller_roles,
                organization_id=approval.organization_id,
                feature_key=approval.feature_key,
                enabled=True,
                reason=approval.reason,
            )
        else:
            tea_service.create_feature_override(
                db,
                actor_user_id=actor_user_id,
                caller_roles=caller_roles,
                organization_id=approval.organization_id,
                feature_key=approval.feature_key,
                enabled=True,
                reason=approval.reason,
            )
    else:
        existing_limit = db.execute(
            select(tea_service.TenantUsageLimit).where(
                tea_service.TenantUsageLimit.organization_id == approval.organization_id,
                tea_service.TenantUsageLimit.feature_key == approval.feature_key,
                tea_service.TenantUsageLimit.limit_key == approval.limit_key,
            )
        ).scalar_one_or_none()
        assert approval.limit_key is not None  # enforced by schema validation at creation
        if existing_limit is not None:
            tea_service.update_usage_limit(
                db,
                actor_user_id=actor_user_id,
                caller_roles=caller_roles,
                organization_id=approval.organization_id,
                feature_key=approval.feature_key,
                limit_key=approval.limit_key,
                limit_value=approval.requested_limit_value,
                is_unlimited=approval.requested_is_unlimited,
            )
        else:
            tea_service.create_usage_limit(
                db,
                actor_user_id=actor_user_id,
                caller_roles=caller_roles,
                organization_id=approval.organization_id,
                feature_key=approval.feature_key,
                limit_key=approval.limit_key,
                limit_value=approval.requested_limit_value,
                is_unlimited=bool(approval.requested_is_unlimited),
            )

    db.refresh(approval)
    return approval


def reject_approval_request(
    db: Session,
    *,
    actor_user_id: uuid.UUID | None,
    approval_id: uuid.UUID,
    decision_reason: str | None = None,
) -> ApprovalRequest:
    approval = get_approval_request(db, approval_id=approval_id)
    now = datetime.now(UTC)
    _claim_pending(
        db,
        approval_id=approval_id,
        new_status=ApprovalRequestStatus.REJECTED,
        reviewed_by_user_id=actor_user_id,
        reviewed_at=now,
        decision_reason=decision_reason,
    )
    record_audit_event(
        db,
        organization_id=approval.organization_id,
        user_id=actor_user_id,
        action="platform.approval_request.rejected",
        entity_type="ApprovalRequest",
        entity_id=approval.id,
        metadata={"request_type": approval.request_type, "feature_key": approval.feature_key},
    )
    db.commit()
    db.refresh(approval)
    return approval


def cancel_approval_request(
    db: Session, *, actor_user_id: uuid.UUID | None, approval_id: uuid.UUID
) -> ApprovalRequest:
    approval = get_approval_request(db, approval_id=approval_id)
    now = datetime.now(UTC)
    _claim_pending(
        db,
        approval_id=approval_id,
        new_status=ApprovalRequestStatus.CANCELED,
        reviewed_by_user_id=actor_user_id,
        reviewed_at=now,
    )
    record_audit_event(
        db,
        organization_id=approval.organization_id,
        user_id=actor_user_id,
        action="platform.approval_request.canceled",
        entity_type="ApprovalRequest",
        entity_id=approval.id,
        metadata={"request_type": approval.request_type, "feature_key": approval.feature_key},
    )
    db.commit()
    db.refresh(approval)
    return approval
