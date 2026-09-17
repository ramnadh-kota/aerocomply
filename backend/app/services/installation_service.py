"""M17.2A: install/remove lifecycle for serialized Battery and Component,
preserving full installation history. Battery.asset_id / Component.asset_id
remain the single source of truth for current placement (see those models'
docstrings) -- this service keeps that column and the corresponding
*_installations history row consistent within one transaction, never one
without the other.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError
from app.models.battery import Battery
from app.models.component import Component
from app.models.installation_history import BatteryInstallation, ComponentInstallation
from app.services import drone_service
from app.services.audit_service import record_audit_event


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
    db: Session, *, organization_id: uuid.UUID, battery_id: uuid.UUID
) -> list[BatteryInstallation]:
    return list(
        db.execute(
            select(BatteryInstallation)
            .where(
                BatteryInstallation.battery_id == battery_id,
                BatteryInstallation.organization_id == organization_id,
            )
            .order_by(BatteryInstallation.installed_at.desc())
        )
        .scalars()
        .all()
    )


def list_component_history(
    db: Session, *, organization_id: uuid.UUID, component_id: uuid.UUID
) -> list[ComponentInstallation]:
    return list(
        db.execute(
            select(ComponentInstallation)
            .where(
                ComponentInstallation.component_id == component_id,
                ComponentInstallation.organization_id == organization_id,
            )
            .order_by(ComponentInstallation.installed_at.desc())
        )
        .scalars()
        .all()
    )
