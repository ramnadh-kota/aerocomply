"""M4: Common Aerospace Domain API Router.

Provides domain-neutral, tenant-scoped endpoints across all aerospace asset types
(Fixed-Wing Aircraft, Drone UAVs, Rotorcraft/Helicopters, and extensible eVTOL/AAM).
Enforces server-side tenant isolation and RBAC.
"""

import uuid
from typing import Any

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, get_db_session
from app.core.errors import ForbiddenError
from app.core.permissions import Permission, permissions_for_roles
from app.schemas.asset import (
    AssetComponentResponse,
    AssetConfigurationResponse,
    AssetCreateRequest,
    AssetDomainContextResponse,
    AssetFlightCreateRequest,
    AssetFlightResponse,
    AssetHistoryResponse,
    AssetInstallComponentRequest,
    AssetOperationsResponse,
    AssetReadinessResponse,
    AssetResponse,
    AssetUpdateRequest,
    AssetUtilizationResponse,
)
from app.schemas.auth import CurrentUser
from app.schemas.deletion import AssetDeleteRequest
from app.services import asset_service, deletion_service

router = APIRouter(prefix="/assets", tags=["assets"])


def require_asset_read(current_user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    granted = permissions_for_roles(current_user.roles)
    if (
        Permission.AIRCRAFT_READ.value not in granted
        and Permission.DRONE_READ.value not in granted
    ):
        raise ForbiddenError("Missing required asset read permission")
    return current_user


def require_asset_write(current_user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    granted = permissions_for_roles(current_user.roles)
    if (
        Permission.AIRCRAFT_WRITE.value not in granted
        and Permission.DRONE_WRITE.value not in granted
        and Permission.ORG_MANAGE.value not in granted
    ):
        raise ForbiddenError("Missing required asset write permission")
    return current_user


# ---------------------------------------------------------------------------
# Asset Registry & Core CRUD
# ---------------------------------------------------------------------------

@router.get("", response_model=list[AssetResponse])
def list_assets(
    asset_type: str | None = Query(default=None, description="AIRCRAFT, DRONE, HELICOPTER, EVTOL, AAM"),
    status: str | None = Query(default=None),
    search: str | None = Query(default=None),
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_asset_read),
) -> list[AssetResponse]:
    assets = asset_service.list_assets(
        db,
        organization_id=current_user.organization_id,
        asset_type=asset_type,
        status=status,
        search=search,
    )
    return [AssetResponse.model_validate(a) for a in assets]


@router.post("", response_model=AssetResponse, status_code=status.HTTP_201_CREATED)
def create_asset(
    payload: AssetCreateRequest,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_asset_write),
) -> AssetResponse:
    asset = asset_service.create_asset(
        db,
        organization_id=current_user.organization_id,
        actor_user_id=current_user.id,
        payload=payload,
    )
    return AssetResponse.model_validate(asset)


@router.get("/{asset_id}", response_model=AssetResponse)
def get_asset(
    asset_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_asset_read),
) -> AssetResponse:
    asset = asset_service.get_asset(
        db, organization_id=current_user.organization_id, asset_id=asset_id
    )
    return AssetResponse.model_validate(asset)


@router.patch("/{asset_id}", response_model=AssetResponse)
def update_asset(
    asset_id: uuid.UUID,
    payload: AssetUpdateRequest,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_asset_write),
) -> AssetResponse:
    asset = asset_service.update_asset(
        db,
        organization_id=current_user.organization_id,
        actor_user_id=current_user.id,
        asset_id=asset_id,
        payload=payload,
    )
    return AssetResponse.model_validate(asset)


@router.delete("/{asset_id}", response_model=AssetResponse)
def delete_asset(
    asset_id: uuid.UUID,
    reason: str | None = Query(default=None, max_length=500),
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_asset_write),
) -> AssetResponse:
    # Soft delete only (Platform Control Plane) -- never a physical row
    # delete from a tenant-facing endpoint. The asset immediately stops
    # appearing in every tenant-facing read (list_assets/get_asset and the
    # drone/aircraft verticals built on them); Platform Admin can see it in
    # GET /platform/deleted-records and restore or permanently delete it.
    # `reason` is a query param (not a request body) -- a DELETE with a body
    # is awkward across HTTP clients/proxies, and this optional, short field
    # doesn't need one.
    asset = deletion_service.soft_delete_asset(
        db,
        organization_id=current_user.organization_id,
        actor_user_id=current_user.id,
        asset_id=asset_id,
        payload=AssetDeleteRequest(reason=reason),
    )
    return AssetResponse.model_validate(asset)


# ---------------------------------------------------------------------------
# Domain Context & Multi-Dimensional Readiness
# ---------------------------------------------------------------------------

@router.get("/{asset_id}/context", response_model=AssetDomainContextResponse)
def get_asset_context(
    asset_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_asset_read),
) -> AssetDomainContextResponse:
    return asset_service.get_asset_domain_context(
        db, organization_id=current_user.organization_id, asset_id=asset_id
    )


@router.get("/{asset_id}/readiness", response_model=AssetReadinessResponse)
def get_asset_readiness(
    asset_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_asset_read),
) -> AssetReadinessResponse:
    return asset_service.get_asset_readiness(
        db, organization_id=current_user.organization_id, asset_id=asset_id
    )


# ---------------------------------------------------------------------------
# Configuration & Components
# ---------------------------------------------------------------------------

@router.get("/{asset_id}/configuration", response_model=AssetConfigurationResponse)
def get_asset_configuration(
    asset_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_asset_read),
) -> AssetConfigurationResponse:
    return asset_service.get_asset_configuration(
        db, organization_id=current_user.organization_id, asset_id=asset_id
    )


@router.get("/{asset_id}/components", response_model=list[AssetComponentResponse])
def get_asset_components(
    asset_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_asset_read),
) -> list[AssetComponentResponse]:
    return asset_service.get_asset_components(
        db, organization_id=current_user.organization_id, asset_id=asset_id
    )


@router.post("/{asset_id}/components", response_model=AssetComponentResponse, status_code=status.HTTP_201_CREATED)
def install_asset_component(
    asset_id: uuid.UUID,
    payload: AssetInstallComponentRequest,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_asset_write),
) -> AssetComponentResponse:
    return asset_service.install_asset_component(
        db,
        organization_id=current_user.organization_id,
        actor_user_id=current_user.id,
        asset_id=asset_id,
        payload=payload,
    )


@router.post("/{asset_id}/components/{component_id}/remove", response_model=AssetComponentResponse)
def remove_asset_component(
    asset_id: uuid.UUID,
    component_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_asset_write),
) -> AssetComponentResponse:
    return asset_service.remove_asset_component(
        db,
        organization_id=current_user.organization_id,
        actor_user_id=current_user.id,
        asset_id=asset_id,
        component_id=component_id,
    )


# ---------------------------------------------------------------------------
# Operations & Utilization
# ---------------------------------------------------------------------------

@router.get("/{asset_id}/operations", response_model=AssetOperationsResponse)
def get_asset_operations(
    asset_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_asset_read),
) -> AssetOperationsResponse:
    return asset_service.get_asset_operations(
        db, organization_id=current_user.organization_id, asset_id=asset_id
    )


@router.post("/{asset_id}/flights", response_model=AssetFlightResponse, status_code=status.HTTP_201_CREATED)
def record_asset_flight(
    asset_id: uuid.UUID,
    payload: AssetFlightCreateRequest,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_asset_write),
) -> AssetFlightResponse:
    return asset_service.record_asset_flight(
        db,
        organization_id=current_user.organization_id,
        actor_user_id=current_user.id,
        asset_id=asset_id,
        payload=payload,
    )


@router.get("/{asset_id}/utilization", response_model=AssetUtilizationResponse)
def get_asset_utilization(
    asset_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_asset_read),
) -> AssetUtilizationResponse:
    return asset_service.get_asset_utilization(
        db, organization_id=current_user.organization_id, asset_id=asset_id
    )


# ---------------------------------------------------------------------------
# Maintenance, Inspections, Evidence, Findings, Compliance, History
# ---------------------------------------------------------------------------

@router.get("/{asset_id}/maintenance")
def get_asset_maintenance(
    asset_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_asset_read),
) -> dict[str, Any]:
    return asset_service.get_asset_maintenance(
        db, organization_id=current_user.organization_id, asset_id=asset_id
    )


@router.get("/{asset_id}/inspections")
def get_asset_inspections(
    asset_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_asset_read),
) -> dict[str, Any]:
    return asset_service.get_asset_inspections(
        db, organization_id=current_user.organization_id, asset_id=asset_id
    )


@router.get("/{asset_id}/evidence")
def get_asset_evidence(
    asset_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_asset_read),
) -> dict[str, Any]:
    return asset_service.get_asset_evidence(
        db, organization_id=current_user.organization_id, asset_id=asset_id
    )


@router.get("/{asset_id}/findings")
def get_asset_findings(
    asset_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_asset_read),
) -> dict[str, Any]:
    return asset_service.get_asset_findings(
        db, organization_id=current_user.organization_id, asset_id=asset_id
    )


@router.get("/{asset_id}/compliance")
def get_asset_compliance(
    asset_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_asset_read),
) -> dict[str, Any]:
    return asset_service.get_asset_compliance(
        db, organization_id=current_user.organization_id, asset_id=asset_id
    )


@router.get("/{asset_id}/history", response_model=AssetHistoryResponse)
def get_asset_history(
    asset_id: uuid.UUID,
    limit: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_asset_read),
) -> AssetHistoryResponse:
    return asset_service.get_asset_history(
        db, organization_id=current_user.organization_id, asset_id=asset_id, limit=limit
    )
