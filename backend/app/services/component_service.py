import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.component import Component
from app.services import drone_service
from app.services.audit_service import record_audit_event


def attach_component(
    db: Session,
    *,
    organization_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    asset_id: uuid.UUID,
    component_type: str,
    name: str,
    serial_number: str | None,
    manufacturer: str | None,
    model: str | None,
) -> Component:
    # Confirms the drone belongs to this tenant before attaching a
    # component to it (cross-tenant IDOR otherwise).
    drone_service.get_drone(db, organization_id=organization_id, asset_id=asset_id)

    component = Component(
        organization_id=organization_id,
        asset_id=asset_id,
        component_type=component_type,
        name=name,
        serial_number=serial_number,
        manufacturer=manufacturer,
        model=model,
    )
    db.add(component)
    db.flush()
    record_audit_event(
        db,
        organization_id=organization_id,
        user_id=actor_user_id,
        action="component.attached",
        entity_type="Component",
        entity_id=component.id,
        metadata={"asset_id": str(asset_id), "component_type": component_type},
    )
    db.commit()
    db.refresh(component)
    return component


def list_components_for_asset(
    db: Session, *, organization_id: uuid.UUID, asset_id: uuid.UUID
) -> list[Component]:
    drone_service.get_drone(db, organization_id=organization_id, asset_id=asset_id)
    return list(
        db.execute(
            select(Component).where(
                Component.organization_id == organization_id, Component.asset_id == asset_id
            )
        )
        .scalars()
        .all()
    )
