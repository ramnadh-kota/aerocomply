"""H6: Digital Asset & Component Twin API.

Read-only aggregation over existing authoritative services — see
app/services/digital_twin_service.py's module docstring. No write
endpoints: all lifecycle/state mutations go through the existing per-domain
endpoints (assets, hums, work_orders, ...).
"""

import uuid
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.deps import get_db_session, require_feature, require_permission
from app.core.permissions import Permission
from app.schemas.auth import CurrentUser
from app.schemas.digital_twin import (
    DigitalTwinAssetSnapshot,
    DigitalTwinComponentNode,
    DigitalTwinComponentSnapshot,
    DigitalTwinConsistencyWarning,
    DigitalTwinGenealogyEntry,
    DigitalTwinTimelineEvent,
)
from app.services import digital_twin_service, knowledge_graph

router = APIRouter(
    prefix="/digital-twin",
    tags=["digital-twin"],
    dependencies=[Depends(require_feature("digital_twin"))],
)


@router.get("/assets/{asset_id}/snapshot", response_model=DigitalTwinAssetSnapshot)
def get_asset_snapshot(
    asset_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.DIGITAL_TWIN_READ)),
) -> DigitalTwinAssetSnapshot:
    result = digital_twin_service.get_asset_snapshot(db, organization_id=current_user.organization_id, asset_id=asset_id)
    db.commit()  # H3/H4/H5 evaluation triggered by the health/diagnostics/prognostics calls may persist refreshed state
    return result


@router.get("/assets/{asset_id}/components", response_model=list[DigitalTwinComponentNode])
def get_asset_components(
    asset_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.DIGITAL_TWIN_READ)),
) -> list[DigitalTwinComponentNode]:
    return digital_twin_service.get_asset_component_tree(db, organization_id=current_user.organization_id, asset_id=asset_id)


@router.get("/assets/{asset_id}/timeline", response_model=list[DigitalTwinTimelineEvent])
def get_asset_timeline(
    asset_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.DIGITAL_TWIN_READ)),
) -> list[DigitalTwinTimelineEvent]:
    return digital_twin_service.get_asset_timeline(db, organization_id=current_user.organization_id, asset_id=asset_id)


@router.get("/assets/{asset_id}/consistency", response_model=list[DigitalTwinConsistencyWarning])
def get_asset_consistency(
    asset_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.DIGITAL_TWIN_READ)),
) -> list[DigitalTwinConsistencyWarning]:
    return digital_twin_service.check_asset_consistency(db, organization_id=current_user.organization_id, asset_id=asset_id)


@router.get("/components/{component_id}", response_model=DigitalTwinComponentSnapshot)
def get_component_snapshot(
    component_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.DIGITAL_TWIN_READ)),
) -> DigitalTwinComponentSnapshot:
    return digital_twin_service.get_component_snapshot(db, organization_id=current_user.organization_id, component_id=component_id)


@router.get("/components/{component_id}/genealogy", response_model=list[DigitalTwinGenealogyEntry])
def get_component_genealogy(
    component_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.DIGITAL_TWIN_READ)),
) -> list[DigitalTwinGenealogyEntry]:
    return digital_twin_service.get_component_genealogy(db, organization_id=current_user.organization_id, component_id=component_id)


@router.get("/components/{component_id}/timeline", response_model=list[DigitalTwinTimelineEvent])
def get_component_timeline(
    component_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.DIGITAL_TWIN_READ)),
) -> list[DigitalTwinTimelineEvent]:
    return digital_twin_service.get_component_timeline(db, organization_id=current_user.organization_id, component_id=component_id)


@router.get("/graph")
def get_lineage_graph(
    node_type: str = Query(description="ASSET, COMPONENT, SENSOR, EXCEEDANCE, FINDING, SIGNAL or WORK_ORDER"),
    node_id: uuid.UUID = Query(),
    depth: int = Query(default=2, ge=0, le=knowledge_graph.MAX_DEPTH),
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.DIGITAL_TWIN_READ)),
) -> dict[str, Any]:
    """Evidence-lineage / impact subgraph around one entity, computed from PostgreSQL (the only store) and scoped to
    the caller's organization. Bounded by depth and node count; `truncated` says when the cap was hit."""
    return knowledge_graph.to_dict(
        knowledge_graph.get_subgraph(db, organization_id=current_user.organization_id,
                                     node_type=node_type, node_id=node_id, depth=depth)
    )
