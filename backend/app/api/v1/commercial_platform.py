"""M14: Commercial Platform API Endpoints.

Provides cross-asset intelligence, decision simulation, tenant data export,
and customer onboarding lifecycle management.
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.deps import (
    get_current_user,
    get_db_session,
    require_any_permission,
    require_permission,
)
from app.core.errors import ConflictError
from app.core.permissions import Permission
from app.models.organization import OnboardingStage, Organization
from app.schemas.auth import CurrentUser
from app.services.audit_service import record_audit_event
from app.services.export_service import export_tenant_data_package
from app.services.intelligence.cross_asset_intelligence_service import (
    FleetIntelligenceSummary,
    evaluate_cross_asset_intelligence,
)
from app.services.intelligence.decision_simulation_service import (
    DecisionSimulationResult,
    simulate_decision_scenarios,
)

router = APIRouter(prefix="/commercial", tags=["Commercial Platform & Scale"])


class OnboardingStageUpdateRequest(BaseModel):
    stage: str


# M20 forensic fix: every handler in this router used to call
# `current_user.require_permission(Permission.X)` -- CurrentUser has no such
# method and most of the named permissions (FLEET_READ, MAINTENANCE_READ,
# ORGANIZATION_READ, ORGANIZATION_ADMIN) do not exist, so all five endpoints
# raised AttributeError (HTTP 500). They now use the standard RBAC dependencies
# with real permissions. Reads of fleet data need an asset-read permission;
# exporting tenant data and changing the onboarding stage need ORG_MANAGE.
_FLEET_READ = (Permission.AIRCRAFT_READ, Permission.DRONE_READ)


@router.get("/cross-asset-intelligence")
def get_cross_asset_intelligence(
    current_user: CurrentUser = Depends(require_any_permission(*_FLEET_READ)),
    db: Session = Depends(get_db_session),
) -> Any:
    return evaluate_cross_asset_intelligence(
        db,
        organization_id=current_user.organization_id,
    )


@router.post("/decision-simulation/{signal_id}")
def run_decision_simulation(
    signal_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_any_permission(*_FLEET_READ)),
    db: Session = Depends(get_db_session),
) -> Any:
    return simulate_decision_scenarios(
        db,
        organization_id=current_user.organization_id,
        signal_id=signal_id,
    )


@router.post("/export")
def generate_tenant_export(
    categories: list[str] | None = Query(None),
    current_user: CurrentUser = Depends(require_permission(Permission.ORG_MANAGE)),
    db: Session = Depends(get_db_session),
) -> dict[str, Any]:
    return export_tenant_data_package(
        db,
        organization_id=current_user.organization_id,
        actor_user_id=current_user.id,
        include_categories=categories,
    )


@router.get("/onboarding-stage")
def get_onboarding_stage(
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db_session),
) -> dict[str, Any]:
    org = db.query(Organization).filter(Organization.id == current_user.organization_id).first()
    return {
        "organization_id": str(current_user.organization_id),
        "onboarding_stage": org.onboarding_stage if org else "ACTIVE",
    }


@router.patch("/onboarding-stage")
def update_onboarding_stage(
    payload: OnboardingStageUpdateRequest,
    current_user: CurrentUser = Depends(require_permission(Permission.ORG_MANAGE)),
    db: Session = Depends(get_db_session),
) -> dict[str, Any]:
    valid_stages = {
        v for k, v in vars(OnboardingStage).items() if k.isupper() and isinstance(v, str)
    }
    if payload.stage not in valid_stages:
        raise ConflictError(
            f"Invalid onboarding stage {payload.stage!r}", code="invalid_onboarding_stage"
        )
    org = db.query(Organization).filter(Organization.id == current_user.organization_id).first()
    if org:
        org.onboarding_stage = payload.stage
        db.flush()
        record_audit_event(
            db,
            action="organization.onboarding_stage_updated",
            entity_type="organization",
            entity_id=org.id,
            organization_id=org.id,
            user_id=current_user.id,
            metadata={"stage": payload.stage},
        )
        db.commit()
    return {
        "organization_id": str(current_user.organization_id),
        "onboarding_stage": org.onboarding_stage if org else payload.stage,
    }
