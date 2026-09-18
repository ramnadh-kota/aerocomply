"""M17.2A: install/remove lifecycle for serialized Battery and Component,
preserving full installation history. Battery.asset_id / Component.asset_id
remain the single source of truth for current placement (see those models'
docstrings) -- this service keeps that column and the corresponding
*_installations history row consistent within one transaction, never one
without the other.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError
from app.models.battery import Battery
from app.models.component import Component
from app.models.installation_history import BatteryInstallation, ComponentInstallation
from app.services import drone_service
from app.services.audit_service import record_audit_event

# M17.2B: read-side pagination bounds for lifecycle history, same
# conservative-default-plus-hard-max precedent as
# app/services/audit_service.py's AUDIT_LIST_DEFAULT_LIMIT/MAX_LIMIT --
# lifecycle history must never become an unbounded response.
LIFECYCLE_HISTORY_DEFAULT_LIMIT = 50
LIFECYCLE_HISTORY_MAX_LIMIT = 100


class LifecycleEventType:
    """M17.2B: the smallest typed API-level representation needed for the
    asset-scoped lifecycle timeline. Not a persisted event/audit table --
    each event is derived on read from a BatteryInstallation/
    ComponentInstallation row (one row yields an INSTALLATION event, plus a
    REMOVAL event if removed_at is set). AuditEvent already exists as the
    project's general-purpose audit trail (battery.installed/removed etc.)
    and is not reused here because it is organization-wide and free-text
    (`action: str`), not asset-scoped and strongly typed the way a lifecycle
    timeline UI needs."""

    BATTERY_INSTALLATION = "BATTERY_INSTALLATION"
    BATTERY_REMOVAL = "BATTERY_REMOVAL"
    COMPONENT_INSTALLATION = "COMPONENT_INSTALLATION"
    COMPONENT_REMOVAL = "COMPONENT_REMOVAL"


@dataclass(frozen=True)
class AssetLifecycleEvent:
    event_type: str
    occurred_at: datetime
    asset_id: uuid.UUID
    installation_id: uuid.UUID
    battery_id: uuid.UUID | None
    component_id: uuid.UUID | None
    actor_user_id: uuid.UUID | None


def install_battery(
    db: Session,
    *,
    organization_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    battery_id: uuid.UUID,
    asset_id: uuid.UUID,
) -> Battery:
    # Confirms the target asset belongs to this tenant before installing
    # onto it (cross-tenant IDOR otherwise).
    drone_service.get_drone(db, organization_id=organization_id, asset_id=asset_id)

    battery = db.execute(
        select(Battery).where(
            Battery.id == battery_id, Battery.organization_id == organization_id
        )
    ).scalar_one_or_none()
    if battery is None:
        raise NotFoundError("Battery not found")

    open_installation = db.execute(
        select(BatteryInstallation).where(
            BatteryInstallation.battery_id == battery_id,
            BatteryInstallation.organization_id == organization_id,
            BatteryInstallation.removed_at.is_(None),
        )
    ).scalar_one_or_none()
    if open_installation is not None:
        raise ConflictError(
            "Battery is already actively installed", code="battery_already_installed"
        )

    now = datetime.now(UTC)
    battery.asset_id = asset_id
    battery.installed_at = now
    db.add(battery)

    installation = BatteryInstallation(
        organization_id=organization_id,
        battery_id=battery_id,
        asset_id=asset_id,
        installed_at=now,
        installed_by=actor_user_id,
    )
    db.add(installation)
    db.flush()
    record_audit_event(
        db,
        organization_id=organization_id,
        user_id=actor_user_id,
        action="battery.installed",
        entity_type="Battery",
        entity_id=battery.id,
        metadata={"asset_id": str(asset_id), "installation_id": str(installation.id)},
    )
    db.commit()
    db.refresh(battery)
    return battery


def remove_battery(
    db: Session,
    *,
    organization_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    battery_id: uuid.UUID,
    asset_id: uuid.UUID,
) -> Battery:
    battery = db.execute(
        select(Battery).where(
            Battery.id == battery_id, Battery.organization_id == organization_id
        )
    ).scalar_one_or_none()
    if battery is None:
        raise NotFoundError("Battery not found")

    installation = db.execute(
        select(BatteryInstallation).where(
            BatteryInstallation.battery_id == battery_id,
            BatteryInstallation.asset_id == asset_id,
            BatteryInstallation.organization_id == organization_id,
            BatteryInstallation.removed_at.is_(None),
        )
    ).scalar_one_or_none()
    if installation is None or battery.asset_id != asset_id:
        raise ConflictError(
            "Battery is not actively installed on this asset", code="battery_not_installed"
        )

    now = datetime.now(UTC)
    installation.removed_at = now
    installation.removed_by = actor_user_id
    db.add(installation)

    battery.asset_id = None
    battery.installed_at = None
    db.add(battery)
    db.flush()
    record_audit_event(
        db,
        organization_id=organization_id,
        user_id=actor_user_id,
        action="battery.removed",
        entity_type="Battery",
        entity_id=battery.id,
        metadata={"asset_id": str(asset_id), "installation_id": str(installation.id)},
    )
    db.commit()
    db.refresh(battery)
    return battery


def install_component(
    db: Session,
    *,
    organization_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    component_id: uuid.UUID,
    asset_id: uuid.UUID,
) -> Component:
    drone_service.get_drone(db, organization_id=organization_id, asset_id=asset_id)

    component = db.execute(
        select(Component).where(
            Component.id == component_id, Component.organization_id == organization_id
        )
    ).scalar_one_or_none()
    if component is None:
        raise NotFoundError("Component not found")

    open_installation = db.execute(
        select(ComponentInstallation).where(
            ComponentInstallation.component_id == component_id,
            ComponentInstallation.organization_id == organization_id,
            ComponentInstallation.removed_at.is_(None),
        )
    ).scalar_one_or_none()
    if open_installation is not None:
        raise ConflictError(
            "Component is already actively installed", code="component_already_installed"
        )

    now = datetime.now(UTC)
    component.asset_id = asset_id
    component.status = "INSTALLED"
    db.add(component)

    installation = ComponentInstallation(
        organization_id=organization_id,
        component_id=component_id,
        asset_id=asset_id,
        installed_at=now,
        installed_by=actor_user_id,
    )
    db.add(installation)
    db.flush()
    record_audit_event(
        db,
        organization_id=organization_id,
        user_id=actor_user_id,
        action="component.installed",
        entity_type="Component",
        entity_id=component.id,
        metadata={"asset_id": str(asset_id), "installation_id": str(installation.id)},
    )
    db.commit()
    db.refresh(component)
    return component


def remove_component(
    db: Session,
    *,
    organization_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    component_id: uuid.UUID,
    asset_id: uuid.UUID,
) -> Component:
    component = db.execute(
        select(Component).where(
            Component.id == component_id, Component.organization_id == organization_id
        )
    ).scalar_one_or_none()
    if component is None:
        raise NotFoundError("Component not found")

    installation = db.execute(
        select(ComponentInstallation).where(
            ComponentInstallation.component_id == component_id,
            ComponentInstallation.asset_id == asset_id,
            ComponentInstallation.organization_id == organization_id,
            ComponentInstallation.removed_at.is_(None),
        )
    ).scalar_one_or_none()
    if installation is None or component.asset_id != asset_id:
        raise ConflictError(
            "Component is not actively installed on this asset", code="component_not_installed"
        )

    now = datetime.now(UTC)
    installation.removed_at = now
    installation.removed_by = actor_user_id
    db.add(installation)

    component.asset_id = None
    component.status = "REMOVED"
    db.add(component)
    db.flush()
    record_audit_event(
        db,
        organization_id=organization_id,
        user_id=actor_user_id,
        action="component.removed",
        entity_type="Component",
        entity_id=component.id,
        metadata={"asset_id": str(asset_id), "installation_id": str(installation.id)},
    )
    db.commit()
    db.refresh(component)
    return component


def list_battery_history(
    db: Session,
    *,
    organization_id: uuid.UUID,
    battery_id: uuid.UUID,
    limit: int = LIFECYCLE_HISTORY_DEFAULT_LIMIT,
    offset: int = 0,
) -> tuple[list[BatteryInstallation], int]:
    limit = max(1, min(limit, LIFECYCLE_HISTORY_MAX_LIMIT))
    offset = max(0, offset)

    filters = (
        BatteryInstallation.battery_id == battery_id,
        BatteryInstallation.organization_id == organization_id,
    )
    total = db.execute(
        select(func.count()).select_from(BatteryInstallation).where(*filters)
    ).scalar_one()
    # installed_at is the domain event time; id (a UUID, not chronological)
    # is only a deterministic tiebreak when two rows share a timestamp --
    # same precedent as audit_service.list_audit_events's (created_at, id)
    # sort.
    stmt = (
        select(BatteryInstallation)
        .where(*filters)
        .order_by(BatteryInstallation.installed_at.desc(), BatteryInstallation.id.desc())
        .limit(limit)
        .offset(offset)
    )
    items = list(db.execute(stmt).scalars().all())
    return items, total


def list_component_history(
    db: Session,
    *,
    organization_id: uuid.UUID,
    component_id: uuid.UUID,
    limit: int = LIFECYCLE_HISTORY_DEFAULT_LIMIT,
    offset: int = 0,
) -> tuple[list[ComponentInstallation], int]:
    limit = max(1, min(limit, LIFECYCLE_HISTORY_MAX_LIMIT))
    offset = max(0, offset)

    filters = (
        ComponentInstallation.component_id == component_id,
        ComponentInstallation.organization_id == organization_id,
    )
    total = db.execute(
        select(func.count()).select_from(ComponentInstallation).where(*filters)
    ).scalar_one()
    stmt = (
        select(ComponentInstallation)
        .where(*filters)
        .order_by(ComponentInstallation.installed_at.desc(), ComponentInstallation.id.desc())
        .limit(limit)
        .offset(offset)
    )
    items = list(db.execute(stmt).scalars().all())
    return items, total


def list_asset_lifecycle_history(
    db: Session,
    *,
    organization_id: uuid.UUID,
    asset_id: uuid.UUID,
    limit: int = LIFECYCLE_HISTORY_DEFAULT_LIMIT,
    offset: int = 0,
) -> tuple[list[AssetLifecycleEvent], int]:
    """Unified battery+component lifecycle timeline for one asset. Confirms
    the asset belongs to this tenant first (cross-tenant IDOR otherwise --
    same precedent as every other asset-scoped read in this file).

    Two queries total, both scoped to a single asset_id (never
    organization-wide) -- no per-event query. Each installation row expands
    to one INSTALLATION event, plus a REMOVAL event if removed_at is set;
    the resulting event list is sorted and paginated in Python, which is
    deliberately simple rather than pushed into SQL: a merge-sort across two
    heterogeneous tables' rows would need a UNION with a synthetic
    discriminator column for little practical benefit, since the input size
    here is bounded by how many batteries/components one asset has ever
    carried -- not by organization-wide history.
    """
    drone_service.get_drone(db, organization_id=organization_id, asset_id=asset_id)

    limit = max(1, min(limit, LIFECYCLE_HISTORY_MAX_LIMIT))
    offset = max(0, offset)

    battery_installations = list(
        db.execute(
            select(BatteryInstallation).where(
                BatteryInstallation.organization_id == organization_id,
                BatteryInstallation.asset_id == asset_id,
            )
        )
        .scalars()
        .all()
    )
    component_installations = list(
        db.execute(
            select(ComponentInstallation).where(
                ComponentInstallation.organization_id == organization_id,
                ComponentInstallation.asset_id == asset_id,
            )
        )
        .scalars()
        .all()
    )

    events: list[AssetLifecycleEvent] = []
    for inst in battery_installations:
        events.append(
            AssetLifecycleEvent(
                event_type=LifecycleEventType.BATTERY_INSTALLATION,
                occurred_at=inst.installed_at,
                asset_id=inst.asset_id,
                installation_id=inst.id,
                battery_id=inst.battery_id,
                component_id=None,
                actor_user_id=inst.installed_by,
            )
        )
        if inst.removed_at is not None:
            events.append(
                AssetLifecycleEvent(
                    event_type=LifecycleEventType.BATTERY_REMOVAL,
                    occurred_at=inst.removed_at,
                    asset_id=inst.asset_id,
                    installation_id=inst.id,
                    battery_id=inst.battery_id,
                    component_id=None,
                    actor_user_id=inst.removed_by,
                )
            )
    for comp_inst in component_installations:
        events.append(
            AssetLifecycleEvent(
                event_type=LifecycleEventType.COMPONENT_INSTALLATION,
                occurred_at=comp_inst.installed_at,
                asset_id=comp_inst.asset_id,
                installation_id=comp_inst.id,
                battery_id=None,
                component_id=comp_inst.component_id,
                actor_user_id=comp_inst.installed_by,
            )
        )
        if comp_inst.removed_at is not None:
            events.append(
                AssetLifecycleEvent(
                    event_type=LifecycleEventType.COMPONENT_REMOVAL,
                    occurred_at=comp_inst.removed_at,
                    asset_id=comp_inst.asset_id,
                    installation_id=comp_inst.id,
                    battery_id=None,
                    component_id=comp_inst.component_id,
                    actor_user_id=comp_inst.removed_by,
                )
            )

    # Newest first; installation_id as a deterministic tiebreak (stable,
    # not chronological) when two events share occurred_at exactly.
    events.sort(key=lambda e: (e.occurred_at, str(e.installation_id)), reverse=True)

    total = len(events)
    page = events[offset : offset + limit]
    return page, total
