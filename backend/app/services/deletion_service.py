"""Platform Control Plane: tenant-facing soft-delete + Platform Admin's
privileged permanent-delete.

Asset is the pilot soft-deletable entity (see app/models/asset.py's
docstring and SoftDeleteMixin in app/db/base.py). A tenant's DELETE never
issues SQL DELETE -- it stamps deleted_at/deleted_by/deletion_reason and the
row is immediately excluded from every tenant-facing read (asset_service.
get_asset/list_assets, drone_service.get_drone/list_drones, aircraft_service.
get_aircraft/list_aircraft). Only Platform Admin's permanently_delete_asset
below issues a real DELETE, and only after restoration_service confirms the
row is currently soft-deleted.

See restoration_service.py for the other half: listing the soft-deleted
queue and restoring a row.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core import lifecycle_policy
from app.core.errors import ConflictError, NotFoundError
from app.models.aog_event import AogEvent
from app.models.asset import Asset
from app.models.deferred_item import DeferredItem
from app.models.finding import Finding
from app.models.inspection_requirement import InspectionRequirement
from app.models.maintenance_requirement import MaintenanceAccomplishment
from app.models.organization import Organization
from app.models.part_requirement import PartRequirement
from app.models.procurement_request import ProcurementRequest
from app.models.task import Task
from app.models.user import User
from app.models.work_order import WorkOrder
from app.schemas.deletion import (
    AssetDeleteRequest,
    OrganizationDeletionRequest,
    PermanentDeleteRequest,
    WorkOrderDeleteRequest,
)
from app.services.audit_service import record_audit_event


def soft_delete_asset(
    db: Session,
    *,
    organization_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    asset_id: uuid.UUID,
    payload: AssetDeleteRequest,
) -> Asset:
    """Tenant-facing DELETE /assets/{asset_id}. Idempotency is deliberately
    refused (ConflictError, not a silent no-op) -- a second DELETE on an
    already-deleted asset is almost always a stale UI state, not intent, and
    the audit trail should show "attempted to delete an already-deleted
    record" rather than nothing."""
    lifecycle_policy.assert_tenant_delete_permitted("ASSET")
    asset = db.execute(
        select(Asset).where(Asset.id == asset_id, Asset.organization_id == organization_id)
    ).scalar_one_or_none()
    if asset is None:
        raise NotFoundError("Asset not found")
    if asset.deleted_at is not None:
        raise ConflictError("Asset is already deleted", code="already_deleted")

    now = datetime.now(UTC)
    asset.deleted_at = now
    asset.deleted_by = actor_user_id
    asset.deletion_reason = payload.reason.strip() if payload.reason else None

    record_audit_event(
        db,
        organization_id=organization_id,
        user_id=actor_user_id,
        action="asset.deleted",
        entity_type="Asset",
        entity_id=asset.id,
        metadata={
            "registration": asset.registration,
            "asset_type": asset.asset_type,
            "reason": asset.deletion_reason,
        },
    )
    db.commit()
    db.refresh(asset)
    return asset


def permanently_delete_asset(
    db: Session,
    *,
    actor_user_id: uuid.UUID | None,
    asset_id: uuid.UUID,
    payload: PermanentDeleteRequest,
) -> None:
    """Platform Admin only (Permission.DATA_PERMANENT_DELETE, enforced at
    the API layer -- see app/api/v1/platform.py). Deliberately NOT
    organization-scoped the way every tenant-facing function is: Platform
    Admin's whole purpose here is cross-tenant governance of a record the
    owning tenant can no longer see or act on.

    Refuses to run on a row that isn't currently soft-deleted
    (ConflictError) -- permanent deletion is a step in the soft-delete
    lifecycle, never a bypass of it; an active asset must go through
    soft_delete_asset first.

    The audit event is recorded (with the asset's identifying details
    captured in metadata, since the row itself won't exist to look up
    afterward) BEFORE the row is deleted, in the same transaction, so a
    failure between the two can never produce a permanent deletion with no
    audit trail.

    Every dependent table (Flight, Component, Battery, WorkOrder,
    ComplianceAssessment, MaintenanceRequirement, Mission, Finding, ...) has
    its FK to assets.id declared ondelete="RESTRICT" (a pre-existing,
    deliberate constraint -- see e.g. Battery.asset_id's own comment). That
    is exactly the "do not implement unrestricted permanent deletion for
    compliance-critical records" boundary the platform spec calls for: this
    function does not re-implement that check in Python, it relies on
    Postgres to refuse the DELETE and surfaces that refusal as a clear
    ConflictError instead of a raw 500. In practice this means only a
    genuinely empty Asset (no flights, no components, no work orders, ...)
    can ever be permanently deleted; anything with real operational or
    compliance history cannot, by construction.
    """
    lifecycle_policy.assert_permanent_delete_permitted("ASSET")
    if not payload.confirm:
        raise ConflictError(
            "Permanent deletion requires explicit confirmation", code="confirmation_required"
        )

    asset = db.execute(select(Asset).where(Asset.id == asset_id)).scalar_one_or_none()
    if asset is None:
        raise NotFoundError("Asset not found")
    if asset.deleted_at is None:
        raise ConflictError(
            "Only a soft-deleted asset can be permanently deleted", code="not_soft_deleted"
        )

    record_audit_event(
        db,
        organization_id=asset.organization_id,
        user_id=actor_user_id,
        action="asset.permanently_deleted",
        entity_type="Asset",
        entity_id=asset.id,
        metadata={
            "registration": asset.registration,
            "asset_type": asset.asset_type,
            "reason": payload.reason.strip(),
            "originally_deleted_by": str(asset.deleted_by) if asset.deleted_by else None,
            "originally_deleted_at": asset.deleted_at.isoformat(),
        },
    )
    db.flush()
    try:
        db.delete(asset)
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ConflictError(
            "This asset has dependent records (flights, components, work orders, compliance "
            "history, ...) and cannot be permanently deleted while they exist.",
            code="has_dependent_records",
        ) from exc


# ---------------------------------------------------------------------------
# Organization deletion-request workflow -- the second entity on this
# lifecycle (see Organization's own docstring in app/models/organization.py
# for why it needs its own dependent-record check instead of Asset's
# ondelete=RESTRICT approach).
# ---------------------------------------------------------------------------


def request_organization_deletion(
    db: Session,
    *,
    organization_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    payload: OrganizationDeletionRequest,
) -> Organization:
    """Tenant Admin's POST /tenant/deletion-request (Permission.ORG_MANAGE).
    Same idempotency refusal as soft_delete_asset -- a second request against
    an already-deletion-requested org is treated as a mistake, not a no-op.

    Once deleted_at is set, every authenticated request from this
    organization's users is refused (app/core/deps.py's get_current_user,
    plus login/refresh in app/services/auth_service.py all check
    org.deleted_at the same way they already check OrganizationStatus.
    SUSPENDED) -- this is what "Tenant UI excludes it" means for an org
    deleting itself: there is no separate tenant-facing surface to hide,
    access is cut off outright, including for the admin who just requested
    it. Only Platform Admin can undo this (restore_organization) or approve
    permanent deletion -- the tenant has no self-service undo, by design.
    """
    lifecycle_policy.assert_tenant_delete_permitted("ORGANIZATION")
    org = db.get(Organization, organization_id)
    if org is None:
        raise NotFoundError("Organization not found")
    if org.deleted_at is not None:
        raise ConflictError("Organization deletion has already been requested", code="already_deleted")

    now = datetime.now(UTC)
    org.deleted_at = now
    org.deleted_by = actor_user_id
    org.deletion_reason = payload.reason.strip() if payload.reason else None

    record_audit_event(
        db,
        organization_id=organization_id,
        user_id=actor_user_id,
        action="organization.deletion_requested",
        entity_type="Organization",
        entity_id=org.id,
        metadata={"name": org.name, "reason": org.deletion_reason},
    )
    db.commit()
    db.refresh(org)
    return org


def permanently_delete_organization(
    db: Session,
    *,
    actor_user_id: uuid.UUID | None,
    organization_id: uuid.UUID,
    payload: PermanentDeleteRequest,
) -> None:
    """Platform Admin only (Permission.DATA_PERMANENT_DELETE). Same shape as
    permanently_delete_asset (confirm required, must already be soft-deleted)
    but the dependent-record check is explicit application-level COUNT
    queries rather than a DB-level ondelete=RESTRICT: organization_id
    columns elsewhere (TenantScopedMixin) are plain UUID columns, never a
    real foreign key to organizations.id, so there is no constraint for
    Postgres to enforce here the way there is for Asset.

    Checking User and Asset counts is enough to make this safe: User is
    every tenant's only path to authenticate/act at all, and Asset is the
    root of virtually every other tenant table's own organization_id-scoped
    data (flights, work orders, compliance assessments, ...) per the M4
    Common Domain Foundation -- an organization with zero Users and zero
    Assets has no operational history left to protect. This deliberately
    does NOT attempt a cascading delete of a non-empty organization's data;
    that is out of scope for this slice (see this function's calling
    docstring in app/api/v1/platform.py) and is exactly the "do not
    introduce cascading physical deletion" boundary the platform spec calls
    for.
    """
    lifecycle_policy.assert_permanent_delete_permitted("ORGANIZATION")
    if not payload.confirm:
        raise ConflictError(
            "Permanent deletion requires explicit confirmation", code="confirmation_required"
        )

    org = db.get(Organization, organization_id)
    if org is None:
        raise NotFoundError("Organization not found")
    if org.deleted_at is None:
        raise ConflictError(
            "Only a deletion-requested organization can be permanently deleted",
            code="not_soft_deleted",
        )

    user_count = db.execute(
        select(func.count(User.id)).where(User.organization_id == organization_id)
    ).scalar_one()
    asset_count = db.execute(
        select(func.count(Asset.id)).where(Asset.organization_id == organization_id)
    ).scalar_one()
    if user_count > 0 or asset_count > 0:
        raise ConflictError(
            "This organization has dependent records (users, assets, ...) and cannot be "
            "permanently deleted while they exist.",
            code="has_dependent_records",
        )

    record_audit_event(
        db,
        organization_id=organization_id,
        user_id=actor_user_id,
        action="organization.permanently_deleted",
        entity_type="Organization",
        entity_id=org.id,
        metadata={
            "name": org.name,
            "reason": payload.reason.strip(),
            "originally_deleted_by": str(org.deleted_by) if org.deleted_by else None,
            "originally_deleted_at": org.deleted_at.isoformat(),
        },
    )
    db.delete(org)
    db.commit()


# ---------------------------------------------------------------------------
# WorkOrder deletion -- the third entity on this lifecycle (see
# app/models/work_order.py, lifecycle_policy.py's WORKORDER entry). Same
# tenant-scoped soft-delete shape as soft_delete_asset. Permanent deletion
# uses an explicit application-level dependency check (like Organization's
# User/Asset count check) rather than DB ondelete=RESTRICT, since the 8
# dependent tables' work_order_id FKs are deliberately left at their
# existing (unspecified/NO ACTION) ondelete value -- see this migration's
# own docstring (0042_soft_delete_work_orders.py) and the HARD CONSTRAINTS
# in this slice's task spec: never weaken/alter those FK definitions.
# ---------------------------------------------------------------------------

# (model class, human-readable singular label, human-readable plural label)
# used by _work_order_dependency_counts below. Order matches the task spec's
# enumeration of the 8 real FK dependents.
_WORK_ORDER_DEPENDENT_TABLES: list[tuple[type, str, str]] = [
    (Task, "Task", "Tasks"),
    (PartRequirement, "PartRequirement", "PartRequirements"),
    (AogEvent, "AogEvent", "AogEvents"),
    (DeferredItem, "DeferredItem", "DeferredItems"),
    (Finding, "Finding", "Findings"),
    (InspectionRequirement, "InspectionRequirement", "InspectionRequirements"),
    # NOTE: the task spec names this dependent "MaintenanceRequirement", but
    # app/models/maintenance_requirement.py's MaintenanceRequirement class
    # itself has NO work_order_id column -- the real FK to work_orders.id
    # lives on MaintenanceAccomplishment (same module, line ~116: "Proof a
    # requirement was actually performed"). This uses the model that
    # actually carries the FK rather than one that doesn't exist, since a
    # dependency check against a nonexistent column would fail at import
    # time, not silently pass.
    (MaintenanceAccomplishment, "MaintenanceAccomplishment", "MaintenanceAccomplishments"),
    (ProcurementRequest, "ProcurementRequest", "ProcurementRequests"),
]


def _work_order_dependency_counts(db: Session, *, work_order_id: uuid.UUID) -> list[tuple[str, str, int]]:
    """Returns (singular_label, plural_label, count) for every dependent
    table that still has at least one row referencing this work order.
    Application-level pre-flight check, run BEFORE attempting the physical
    DELETE -- this is what turns "an IntegrityError from Postgres" into a
    clear, entity-named ConflictError as the normal user-facing failure
    mode. The DB FK remains the final safety net only (see the IntegrityError
    catch below)."""
    results: list[tuple[str, str, int]] = []
    for model, singular, plural in _WORK_ORDER_DEPENDENT_TABLES:
        count = db.execute(
            select(func.count()).select_from(model).where(model.work_order_id == work_order_id)
        ).scalar_one()
        if count > 0:
            results.append((singular, plural, count))
    return results


def soft_delete_work_order(
    db: Session,
    *,
    organization_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    work_order_id: uuid.UUID,
    payload: WorkOrderDeleteRequest,
) -> WorkOrder:
    """Tenant-facing DELETE /work-orders/{work_order_id}. Same idempotency
    refusal as soft_delete_asset -- a second DELETE on an already-deleted
    work order is a ConflictError, not a silent no-op.

    Only the WorkOrder row itself is stamped. Task/PartRequirement/
    AogEvent/DeferredItem/Finding/InspectionRequirement/
    MaintenanceRequirement/ProcurementRequest rows that reference it are
    never mutated -- historical traceability outranks UI hiding for those
    (see this slice's task spec, invariant #8)."""
    lifecycle_policy.assert_tenant_delete_permitted("WORKORDER")
    work_order = db.execute(
        select(WorkOrder).where(
            WorkOrder.id == work_order_id, WorkOrder.organization_id == organization_id
        )
    ).scalar_one_or_none()
    if work_order is None:
        raise NotFoundError("Work order not found")
    if work_order.deleted_at is not None:
        raise ConflictError("Work order is already deleted", code="already_deleted")

    now = datetime.now(UTC)
    work_order.deleted_at = now
    work_order.deleted_by = actor_user_id
    work_order.deletion_reason = payload.reason.strip() if payload.reason else None

    record_audit_event(
        db,
        organization_id=organization_id,
        user_id=actor_user_id,
        action="work_order.deleted",
        entity_type="WorkOrder",
        entity_id=work_order.id,
        metadata={
            "work_order_number": work_order.work_order_number,
            "status": work_order.status,
            "asset_id": str(work_order.asset_id) if work_order.asset_id else None,
            "aircraft_id": str(work_order.aircraft_id) if work_order.aircraft_id else None,
            "reason": work_order.deletion_reason,
        },
    )
    db.commit()
    db.refresh(work_order)
    return work_order


def permanently_delete_work_order(
    db: Session,
    *,
    actor_user_id: uuid.UUID | None,
    work_order_id: uuid.UUID,
    payload: PermanentDeleteRequest,
) -> None:
    """Platform Admin only (Permission.DATA_PERMANENT_DELETE). Same shape as
    permanently_delete_asset/permanently_delete_organization (confirm
    required, must already be soft-deleted), but the dependency check is an
    explicit application-level COUNT across all 8 dependent tables (see
    _work_order_dependency_counts) rather than relying on DB ondelete=
    RESTRICT, since those FKs are deliberately left unmodified at their
    existing ondelete value. A raw IntegrityError is still caught as a
    last-resort safety net, never the expected user-facing path.

    The permanently_deleted audit event is written BEFORE the row is
    deleted, in the same transaction, so it survives the physical row
    deletion and a failure between the two can never produce a permanent
    deletion with no audit trail."""
    lifecycle_policy.assert_permanent_delete_permitted("WORKORDER")
    if not payload.confirm:
        raise ConflictError(
            "Permanent deletion requires explicit confirmation", code="confirmation_required"
        )

    work_order = db.execute(
        select(WorkOrder).where(WorkOrder.id == work_order_id)
    ).scalar_one_or_none()
    if work_order is None:
        raise NotFoundError("Work order not found")
    if work_order.deleted_at is None:
        raise ConflictError(
            "Only a soft-deleted work order can be permanently deleted", code="not_soft_deleted"
        )

    dependents = _work_order_dependency_counts(db, work_order_id=work_order_id)
    if dependents:
        parts = [
            f"{count} {singular if count == 1 else plural}" for singular, plural, count in dependents
        ]
        joined = " and ".join(parts) if len(parts) <= 2 else ", ".join(parts[:-1]) + f", and {parts[-1]}"
        raise ConflictError(
            f"WorkOrder cannot be permanently deleted because {joined} still reference it.",
            code="has_dependent_records",
        )

    record_audit_event(
        db,
        organization_id=work_order.organization_id,
        user_id=actor_user_id,
        action="work_order.permanently_deleted",
        entity_type="WorkOrder",
        entity_id=work_order.id,
        metadata={
            "work_order_number": work_order.work_order_number,
            "status": work_order.status,
            "asset_id": str(work_order.asset_id) if work_order.asset_id else None,
            "aircraft_id": str(work_order.aircraft_id) if work_order.aircraft_id else None,
            "reason": payload.reason.strip(),
            "originally_deleted_by": str(work_order.deleted_by) if work_order.deleted_by else None,
            "originally_deleted_at": work_order.deleted_at.isoformat(),
        },
    )
    db.flush()
    try:
        db.delete(work_order)
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ConflictError(
            "This work order has dependent records and cannot be permanently deleted while "
            "they exist.",
            code="has_dependent_records",
        ) from exc
