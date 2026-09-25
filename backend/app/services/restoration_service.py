"""Platform Control Plane: the read (governance queue) and restore half of
soft-delete. See deletion_service.py for the delete/permanent-delete half.

Deliberately its own module (not folded into deletion_service.py) --
matches the platform spec's DeletionService/RestorationService boundary and
keeps "make something disappear" and "bring something back / list what's
disappeared" as separately reviewable concerns.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import lifecycle_policy
from app.core.errors import ConflictError, NotFoundError
from app.models.asset import Asset
from app.models.organization import Organization
from app.models.work_order import WorkOrder
from app.schemas.deletion import DeletedRecordResponse
from app.services.audit_service import record_audit_event

DELETED_RECORDS_DEFAULT_LIMIT = 50
DELETED_RECORDS_MAX_LIMIT = 100

# Defensive per-type bound on the raw rows fetched before the Python-side
# merge/sort below (see list_deleted_records) -- the soft-delete queue is a
# small, actively-managed governance worklist (not an unbounded history
# table: a restored or permanently-deleted row leaves it immediately), so
# this is a safety ceiling, not an expected volume.
_MERGE_FETCH_CAP = 500


def _deleted_assets(db: Session, *, organization_id: uuid.UUID | None) -> list[DeletedRecordResponse]:
    filters = [Asset.deleted_at.is_not(None)]
    if organization_id is not None:
        filters.append(Asset.organization_id == organization_id)
    rows = list(
        db.execute(
            select(Asset).where(*filters).order_by(Asset.deleted_at.desc()).limit(_MERGE_FETCH_CAP)
        )
        .scalars()
        .all()
    )
    return [
        DeletedRecordResponse(
            entity_type="ASSET",
            entity_id=a.id,
            organization_id=a.organization_id,
            identifier=a.registration,
            asset_type=a.asset_type,
            status="DELETED",
            deleted_at=a.deleted_at,
            deleted_by=a.deleted_by,
            deletion_reason=a.deletion_reason,
            restored_at=a.restored_at,
            restored_by=a.restored_by,
        )
        for a in rows
    ]


def _deleted_organizations(
    db: Session, *, organization_id: uuid.UUID | None
) -> list[DeletedRecordResponse]:
    filters = [Organization.deleted_at.is_not(None)]
    if organization_id is not None:
        filters.append(Organization.id == organization_id)
    rows = list(
        db.execute(
            select(Organization)
            .where(*filters)
            .order_by(Organization.deleted_at.desc())
            .limit(_MERGE_FETCH_CAP)
        )
        .scalars()
        .all()
    )
    return [
        DeletedRecordResponse(
            entity_type="ORGANIZATION",
            entity_id=o.id,
            organization_id=o.id,
            identifier=o.name,
            asset_type=None,
            status="DELETED",
            deleted_at=o.deleted_at,
            deleted_by=o.deleted_by,
            deletion_reason=o.deletion_reason,
            restored_at=o.restored_at,
            restored_by=o.restored_by,
        )
        for o in rows
    ]


def _deleted_work_orders(
    db: Session, *, organization_id: uuid.UUID | None
) -> list[DeletedRecordResponse]:
    filters = [WorkOrder.deleted_at.is_not(None)]
    if organization_id is not None:
        filters.append(WorkOrder.organization_id == organization_id)
    rows = list(
        db.execute(
            select(WorkOrder)
            .where(*filters)
            .order_by(WorkOrder.deleted_at.desc())
            .limit(_MERGE_FETCH_CAP)
        )
        .scalars()
        .all()
    )
    return [
        DeletedRecordResponse(
            entity_type="WORKORDER",
            entity_id=w.id,
            organization_id=w.organization_id,
            identifier=w.work_order_number,
            asset_type=None,
            status=w.status,
            deleted_at=w.deleted_at,
            deleted_by=w.deleted_by,
            deletion_reason=w.deletion_reason,
            restored_at=w.restored_at,
            restored_by=w.restored_by,
        )
        for w in rows
    ]


def list_deleted_records(
    db: Session,
    *,
    entity_type: str | None = None,
    organization_id: uuid.UUID | None = None,
    limit: int = DELETED_RECORDS_DEFAULT_LIMIT,
    offset: int = 0,
) -> tuple[list[DeletedRecordResponse], int]:
    """Platform Admin's unified soft-delete governance queue across every
    soft-deletable entity type (currently Asset and Organization -- see
    _deleted_assets/_deleted_organizations above), across all organizations
    unless organization_id narrows it. Cross-tenant by design -- see
    deletion_service.permanently_delete_asset's docstring for why this
    whole module is deliberately not organization-scoped the way tenant
    services are.

    entity_type filters to one type ("ASSET" or "ORGANIZATION"); omitted,
    both are merged and re-sorted by deleted_at descending. Each type is
    queried (and DB-side ordered/capped) separately, then merged and paged
    in Python -- there are only two types today, so a real SQL UNION isn't
    worth the added complexity; revisit if a third type makes this
    meaningfully slower.

    Only the ACTIVE soft-delete queue -- a record already restored or
    permanently deleted drops out of it immediately. Both are still visible
    historically through the existing platform audit log (GET
    /platform/audit, action=asset.restored / organization.restored / etc.)
    rather than duplicated here.

    entity_type is validated against the lifecycle policy registry (see
    app/core/lifecycle_policy.py) when given: a retention-protected
    (category C) entity type -- e.g. FINDING -- is refused outright rather
    than silently returning an empty page, since it must never be visible
    here even in principle, not merely "no rows right now." Any other
    registered-but-not-yet-implemented entity type (WorkOrder, Vendor, ...)
    is allowed through and simply contributes zero rows, since no data
    source exists for it yet -- that is a "not built" state, not a
    "forbidden" one.
    """
    limit = max(1, min(limit, DELETED_RECORDS_MAX_LIMIT))
    offset = max(0, offset)

    if entity_type is not None:
        lifecycle_policy.assert_visible_in_deletion_queue(entity_type)

    combined: list[DeletedRecordResponse] = []
    if entity_type is None or entity_type.upper() == "ASSET":
        combined.extend(_deleted_assets(db, organization_id=organization_id))
    if entity_type is None or entity_type.upper() == "ORGANIZATION":
        combined.extend(_deleted_organizations(db, organization_id=organization_id))
    if entity_type is None or entity_type.upper() == "WORKORDER":
        combined.extend(_deleted_work_orders(db, organization_id=organization_id))

    combined.sort(key=lambda r: r.deleted_at, reverse=True)
    total = len(combined)
    return combined[offset : offset + limit], total


def restore_asset(
    db: Session,
    *,
    actor_user_id: uuid.UUID | None,
    asset_id: uuid.UUID,
) -> Asset:
    """Platform Admin only (Permission.DATA_RESTORE). Not organization-scoped
    -- same reasoning as permanently_delete_asset. Clears deleted_at/
    deleted_by/deletion_reason (the asset immediately becomes visible again
    through every ordinary tenant-facing read) and stamps restored_at/
    restored_by as a permanent record of the most recent restore -- those
    two are never cleared, so "this was deleted and restored before" stays
    visible even long after.

    Asset has no dependent records that themselves need restoring (a
    Component/Flight/WorkOrder was never soft-deleted just because its
    parent Asset was -- see deletion_service.soft_delete_asset, which only
    touches the Asset row), so there is no cascading-restore relationship to
    implement for this pilot entity.
    """
    lifecycle_policy.assert_restore_permitted("ASSET")
    asset = db.execute(select(Asset).where(Asset.id == asset_id)).scalar_one_or_none()
    if asset is None:
        raise NotFoundError("Asset not found")
    if asset.deleted_at is None:
        raise ConflictError("Asset is not currently deleted", code="not_deleted")

    now = datetime.now(UTC)
    asset.deleted_at = None
    asset.deleted_by = None
    asset.deletion_reason = None
    asset.restored_at = now
    asset.restored_by = actor_user_id

    record_audit_event(
        db,
        organization_id=asset.organization_id,
        user_id=actor_user_id,
        action="asset.restored",
        entity_type="Asset",
        entity_id=asset.id,
        metadata={"registration": asset.registration, "asset_type": asset.asset_type},
    )
    db.commit()
    db.refresh(asset)
    return asset


def restore_organization(
    db: Session,
    *,
    actor_user_id: uuid.UUID | None,
    organization_id: uuid.UUID,
) -> Organization:
    """Platform Admin only (Permission.DATA_RESTORE). Clears deleted_at/
    deleted_by/deletion_reason -- every user in this organization can
    authenticate again immediately (app/core/deps.py's get_current_user and
    both login/refresh checks in app/services/auth_service.py all key off
    deleted_at being null), no separate "reactivate users" step needed since
    User.is_active was never touched by request_organization_deletion in
    the first place."""
    lifecycle_policy.assert_restore_permitted("ORGANIZATION")
    org = db.get(Organization, organization_id)
    if org is None:
        raise NotFoundError("Organization not found")
    if org.deleted_at is None:
        raise ConflictError("Organization is not currently deleted", code="not_deleted")

    now = datetime.now(UTC)
    org.deleted_at = None
    org.deleted_by = None
    org.deletion_reason = None
    org.restored_at = now
    org.restored_by = actor_user_id

    record_audit_event(
        db,
        organization_id=org.id,
        user_id=actor_user_id,
        action="organization.restored",
        entity_type="Organization",
        entity_id=org.id,
        metadata={"name": org.name},
    )
    db.commit()
    db.refresh(org)
    return org


def restore_work_order(
    db: Session,
    *,
    actor_user_id: uuid.UUID | None,
    work_order_id: uuid.UUID,
) -> WorkOrder:
    """Platform Admin only (Permission.DATA_RESTORE). Tenant Admin has no
    path to this -- there is no tenant-facing restore endpoint for
    WorkOrder, only the platform one wired in app/api/v1/platform.py.

    Same shape as restore_asset: clears deleted_at/deleted_by/
    deletion_reason (the work order immediately becomes visible again
    through every ordinary tenant-facing read -- work_order_service.
    get_work_order/list_work_orders) and stamps restored_at/restored_by.
    Task/PartRequirement/... rows that reference this work order were never
    touched by soft_delete_work_order, so there is nothing to cascade-
    restore here either."""
    lifecycle_policy.assert_restore_permitted("WORKORDER")
    work_order = db.execute(
        select(WorkOrder).where(WorkOrder.id == work_order_id)
    ).scalar_one_or_none()
    if work_order is None:
        raise NotFoundError("Work order not found")
    if work_order.deleted_at is None:
        raise ConflictError("Work order is not currently deleted", code="not_deleted")

    now = datetime.now(UTC)
    work_order.deleted_at = None
    work_order.deleted_by = None
    work_order.deletion_reason = None
    work_order.restored_at = now
    work_order.restored_by = actor_user_id

    record_audit_event(
        db,
        organization_id=work_order.organization_id,
        user_id=actor_user_id,
        action="work_order.restored",
        entity_type="WorkOrder",
        entity_id=work_order.id,
        metadata={"work_order_number": work_order.work_order_number, "status": work_order.status},
    )
    db.commit()
    db.refresh(work_order)
    return work_order
