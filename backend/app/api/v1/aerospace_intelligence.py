"""D2-4 Aerospace Intelligence State API.

Exposes the deterministic AerospaceIntelligenceState contract for Developer 2.2
(Readiness / Risk / Decision / AI presentation) and any other authorized consumer.

Routes:
  GET /aerospace-intelligence/assets/{asset_id}/state
      → AerospaceIntelligenceState for a single asset (drone vertical slice primary)
  GET /aerospace-intelligence/assets/{asset_id}/state/summary
      → Compact summary suitable for dashboard cards / list views

Security:
  Requires COMPLIANCE_ASSESS or AIRCRAFT_READ or DRONE_READ permission.
  Organization scoped — tenant isolation enforced in service.

Dev 2.2 Consumption Notes:
  - The `aerospace_intelligence_status` field is the primary dispatch signal.
  - `blockers` list is the authoritative explainability source.
  - `source_records` is returned only when include_source_records=true.
  - `evaluation_version` must be checked if Developer 2.2 caches state.
  - Developer 2.2 must NOT query intelligence tables directly; it must call
    these endpoints or invoke aerospace_state_service.py functions.
"""

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.deps import get_db_session, require_any_permission
from app.core.permissions import Permission
from app.schemas.auth import CurrentUser
from app.schemas.aerospace_state import AerospaceIntelligenceState
from app.services import aerospace_state_service

router = APIRouter(prefix="/aerospace-intelligence", tags=["aerospace-intelligence"])


@router.get(
    "/assets/{asset_id}/state",
    response_model=AerospaceIntelligenceState,
    summary="Evaluate Aerospace Intelligence State for an asset",
    description=(
        "Returns the deterministic AerospaceIntelligenceState aggregating "
        "operational truth (Developer 1), applicability (D2-1), compliance/evidence (D2-2), "
        "and inspection/finding intelligence (D2-3). "
        "This is the primary D2.2 consumption endpoint."
    ),
)
def get_aerospace_intelligence_state(
    asset_id: uuid.UUID,
    include_closed_findings: bool = Query(
        default=False,
        description="Include closed findings in the finding dimension evaluation.",
    ),
    include_source_records: bool = Query(
        default=False,
        description="Include source record provenance list (may be large).",
    ),
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(
        require_any_permission(
            Permission.COMPLIANCE_ASSESS,
            Permission.AIRCRAFT_READ,
            Permission.DRONE_READ,
        )
    ),
) -> AerospaceIntelligenceState:
    return aerospace_state_service.evaluate_aerospace_intelligence_state(
        db,
        organization_id=current_user.organization_id,
        asset_id=asset_id,
        include_closed_findings=include_closed_findings,
        include_source_records=include_source_records,
    )


@router.get(
    "/assets/{asset_id}/state/summary",
    summary="Compact Aerospace Intelligence State summary",
    description=(
        "Returns a compact summary of the aerospace intelligence state, "
        "suitable for dashboard cards and list views. "
        "Omits blocker details and source records for performance."
    ),
)
def get_aerospace_intelligence_state_summary(
    asset_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(
        require_any_permission(
            Permission.COMPLIANCE_ASSESS,
            Permission.AIRCRAFT_READ,
            Permission.DRONE_READ,
        )
    ),
) -> dict:
    state = aerospace_state_service.evaluate_aerospace_intelligence_state(
        db,
        organization_id=current_user.organization_id,
        asset_id=asset_id,
        include_closed_findings=False,
        include_source_records=False,
    )
    return {
        "asset_id": str(state.asset_id),
        "aircraft_id": str(state.aircraft_id) if state.aircraft_id else None,
        "asset_type": state.asset_type,
        "registration": state.registration,
        "aerospace_intelligence_status": state.aerospace_intelligence_status,
        "total_blocker_count": state.total_blocker_count,
        "total_warning_count": state.total_warning_count,
        "compliance_blocker_count": state.compliance_blocker_count,
        "evidence_blocker_count": state.evidence_blocker_count,
        "inspection_blocker_count": state.inspection_blocker_count,
        "finding_blocker_count": state.finding_blocker_count,
        "operational_state": state.operational_dimension.operational_state,
        "compliance_status": state.compliance_dimension.status,
        "evidence_status": state.evidence_dimension.status,
        "inspection_status": state.inspection_dimension.status,
        "finding_status": state.finding_dimension.status,
        "evaluated_at": state.evaluated_at.isoformat(),
        "evaluation_version": state.evaluation_version,
    }
