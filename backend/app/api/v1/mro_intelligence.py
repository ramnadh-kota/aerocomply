"""H7: MRO + Compliance + Readiness Intelligence Integration API.

Read-mostly correlation layer over existing authoritative services -- see
app/services/mro_intelligence_service.py's module docstring. Only the
candidate lifecycle endpoints (review/accept/reject/defer) write anything,
and they only ever mutate this module's own MaintenanceIntelligenceCandidate
table plus AuditEvent, never any authoritative domain table.
"""

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.deps import get_db_session, require_feature, require_permission
from app.core.permissions import Permission
from app.schemas.auth import CurrentUser
from app.schemas.mro_intelligence import (
    AssetMROIntelligence,
    CandidateActionRequest,
    CandidateDraftWorkOrderRequest,
    CandidateDraftWorkOrderResponse,
    ComplianceImpactResult,
    IntegrationConflict,
    MaintenanceCandidateOut,
    OperationalImpactResult,
    ReadinessImpactResult,
    ReconciliationResult,
)
from app.services import mro_intelligence_service

router = APIRouter(
    prefix="/mro-intelligence",
    tags=["mro-intelligence"],
    dependencies=[Depends(require_feature("mro_intelligence"))],
)


@router.get("/assets/{asset_id}", response_model=AssetMROIntelligence)
def get_asset_mro_intelligence(
    asset_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.MRO_INTELLIGENCE_READ)),
) -> AssetMROIntelligence:
    result = mro_intelligence_service.get_asset_mro_intelligence(db, organization_id=current_user.organization_id, asset_id=asset_id)
    db.commit()
    return result


@router.get("/assets/{asset_id}/maintenance-candidates", response_model=list[MaintenanceCandidateOut])
def list_maintenance_candidates(
    asset_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.MRO_INTELLIGENCE_READ)),
) -> list[MaintenanceCandidateOut]:
    generated = mro_intelligence_service.generate_maintenance_candidates(db, organization_id=current_user.organization_id, asset_id=asset_id)
    existing = mro_intelligence_service.list_asset_candidates(db, organization_id=current_user.organization_id, asset_id=asset_id)
    db.commit()
    seen = {c.id for c in generated}
    merged = list(generated) + [c for c in existing if c.id not in seen]
    return [MaintenanceCandidateOut.model_validate(c) for c in merged]


@router.get("/assets/{asset_id}/compliance-impact", response_model=ComplianceImpactResult)
def get_compliance_impact(
    asset_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.MRO_INTELLIGENCE_READ)),
) -> ComplianceImpactResult:
    return mro_intelligence_service.get_compliance_impact(db, organization_id=current_user.organization_id, asset_id=asset_id)


@router.get("/assets/{asset_id}/readiness-impact", response_model=ReadinessImpactResult)
def get_readiness_impact(
    asset_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.MRO_INTELLIGENCE_READ)),
) -> ReadinessImpactResult:
    result = mro_intelligence_service.get_readiness_impact(db, organization_id=current_user.organization_id, asset_id=asset_id)
    db.commit()
    return result


@router.get("/assets/{asset_id}/operational-impact", response_model=OperationalImpactResult)
def get_operational_impact(
    asset_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.MRO_INTELLIGENCE_READ)),
) -> OperationalImpactResult:
    result = mro_intelligence_service.get_operational_impact(db, organization_id=current_user.organization_id, asset_id=asset_id)
    db.commit()
    return result


@router.get("/assets/{asset_id}/conflicts", response_model=list[IntegrationConflict])
def get_conflicts(
    asset_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.MRO_INTELLIGENCE_READ)),
) -> list[IntegrationConflict]:
    return mro_intelligence_service.detect_conflicts(db, organization_id=current_user.organization_id, asset_id=asset_id)


@router.post("/assets/{asset_id}/reconcile", response_model=ReconciliationResult)
def reconcile_asset(
    asset_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.MRO_INTELLIGENCE_REVIEW)),
) -> ReconciliationResult:
    result = mro_intelligence_service.reconcile_asset_mro_intelligence(db, organization_id=current_user.organization_id, asset_id=asset_id)
    db.commit()
    return result


@router.get("/components/{component_id}")
def get_component_mro_intelligence(
    component_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.MRO_INTELLIGENCE_READ)),
) -> dict:
    return mro_intelligence_service.get_component_mro_intelligence(db, organization_id=current_user.organization_id, component_id=component_id)


@router.get("/candidates/{candidate_id}", response_model=MaintenanceCandidateOut)
def get_candidate(
    candidate_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.MRO_INTELLIGENCE_READ)),
) -> MaintenanceCandidateOut:
    return MaintenanceCandidateOut.model_validate(
        mro_intelligence_service.get_candidate(db, organization_id=current_user.organization_id, candidate_id=candidate_id)
    )


@router.post("/candidates/{candidate_id}/review", response_model=MaintenanceCandidateOut)
def review_candidate(
    candidate_id: uuid.UUID,
    body: CandidateActionRequest = CandidateActionRequest(),
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.MRO_INTELLIGENCE_REVIEW)),
) -> MaintenanceCandidateOut:
    candidate = mro_intelligence_service.review_candidate(db, organization_id=current_user.organization_id, candidate_id=candidate_id, user_id=current_user.id, notes=body.notes)
    db.commit()
    return MaintenanceCandidateOut.model_validate(candidate)


@router.post("/candidates/{candidate_id}/accept", response_model=MaintenanceCandidateOut)
def accept_candidate(
    candidate_id: uuid.UUID,
    body: CandidateActionRequest = CandidateActionRequest(),
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.MRO_INTELLIGENCE_REVIEW)),
) -> MaintenanceCandidateOut:
    candidate = mro_intelligence_service.accept_candidate(db, organization_id=current_user.organization_id, candidate_id=candidate_id, user_id=current_user.id, notes=body.notes)
    db.commit()
    return MaintenanceCandidateOut.model_validate(candidate)


@router.post("/candidates/{candidate_id}/reject", response_model=MaintenanceCandidateOut)
def reject_candidate(
    candidate_id: uuid.UUID,
    body: CandidateActionRequest = CandidateActionRequest(),
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.MRO_INTELLIGENCE_REVIEW)),
) -> MaintenanceCandidateOut:
    candidate = mro_intelligence_service.reject_candidate(db, organization_id=current_user.organization_id, candidate_id=candidate_id, user_id=current_user.id, notes=body.notes)
    db.commit()
    return MaintenanceCandidateOut.model_validate(candidate)


@router.post("/candidates/{candidate_id}/defer", response_model=MaintenanceCandidateOut)
def defer_candidate(
    candidate_id: uuid.UUID,
    body: CandidateActionRequest = CandidateActionRequest(),
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.MRO_INTELLIGENCE_REVIEW)),
) -> MaintenanceCandidateOut:
    candidate = mro_intelligence_service.defer_candidate(db, organization_id=current_user.organization_id, candidate_id=candidate_id, user_id=current_user.id, notes=body.notes)
    db.commit()
    return MaintenanceCandidateOut.model_validate(candidate)


@router.get("/candidates", response_model=list[MaintenanceCandidateOut])
def list_candidates(
    status: str | None = Query(None, description="Filter by candidate status"),
    candidate_type: str | None = Query(None, description="Filter by candidate type"),
    priority: str | None = Query(None, description="Filter by priority (HIGH, MEDIUM, LOW)"),
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.MRO_INTELLIGENCE_READ)),
) -> list[MaintenanceCandidateOut]:
    """Lists predictive maintenance recommendation candidates across the fleet with optional filtering."""
    candidates = mro_intelligence_service.list_fleet_candidates(
        db,
        organization_id=current_user.organization_id,
        status=status,
        candidate_type=candidate_type,
        priority=priority,
    )
    return [MaintenanceCandidateOut.model_validate(c) for c in candidates]


@router.post("/candidates/{candidate_id}/draft-work-order", response_model=CandidateDraftWorkOrderResponse)
def draft_work_order_from_candidate(
    candidate_id: uuid.UUID,
    body: CandidateDraftWorkOrderRequest = CandidateDraftWorkOrderRequest(),
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.MRO_INTELLIGENCE_REVIEW)),
) -> CandidateDraftWorkOrderResponse:
    """Human-authorized predictive maintenance drafting workflow (H8.7).
    Converts a reviewed candidate into a formal drafted work order using Developer 1's work order contract.
    """
    candidate, work_order = mro_intelligence_service.draft_work_order_from_candidate(
        db,
        organization_id=current_user.organization_id,
        candidate_id=candidate_id,
        user_id=current_user.id,
        title=body.title,
        priority=body.priority,
        due_at=body.due_at,
        notes=body.notes,
    )
    db.commit()
    return CandidateDraftWorkOrderResponse(
        candidate=MaintenanceCandidateOut.model_validate(candidate),
        work_order_id=work_order.id,
        work_order_number=work_order.work_order_number,
        work_order_status=work_order.status,
        work_order_priority=work_order.priority,
        work_order_title=work_order.title,
    )

