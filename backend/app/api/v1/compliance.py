import uuid
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.deps import require_feature, get_db_session, require_any_permission, require_permission
from app.core.permissions import Permission
from app.schemas.auth import CurrentUser
from app.schemas.compliance import (
    ComplianceAssessmentCreateRequest,
    ComplianceAssessmentOverrideRequest,
    ComplianceAssessmentResponse,
    ComplianceObligationCreateRequest,
    ComplianceObligationResponse,
    ComplianceObligationUpdateRequest,
    ComplianceOverviewResponse,
    ComplianceTraceabilityResponse,
    RegulatoryRequirementCreateRequest,
    RegulatoryRequirementResponse,
)
from app.schemas.compliance_intelligence import (
    AssetComplianceImpactResponse,
    ComplianceReadinessContribution,
    FindingComplianceImpactResponse,
    InspectionComplianceImpactResponse,
)
from app.schemas.evidence import EvidenceCreateRequest, EvidenceResponse
from app.services import compliance_service, evidence_service
from app.services.compliance import intelligence_service, obligation_service

router = APIRouter(tags=["compliance"], dependencies=[Depends(require_feature("compliance_management"))])
@router.post(
    "/regulatory-requirements", response_model=RegulatoryRequirementResponse, status_code=201
)
def create_requirement(
    payload: RegulatoryRequirementCreateRequest,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.REGULATION_WRITE)),
) -> RegulatoryRequirementResponse:
    requirement = compliance_service.create_requirement(
        db,
        organization_id=current_user.organization_id,
        actor_user_id=current_user.id,
        payload=payload,
    )
    return RegulatoryRequirementResponse.model_validate(requirement)


@router.get("/regulatory-requirements", response_model=list[RegulatoryRequirementResponse])
def list_requirements(
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.REGULATION_READ)),
) -> list[RegulatoryRequirementResponse]:
    requirements = compliance_service.list_requirements(
        db, organization_id=current_user.organization_id
    )
    return [RegulatoryRequirementResponse.model_validate(r) for r in requirements]


@router.get(
    "/regulatory-requirements/{requirement_id}",
    response_model=RegulatoryRequirementResponse,
)
def get_requirement(
    requirement_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.REGULATION_READ)),
) -> RegulatoryRequirementResponse:
    requirement = compliance_service.get_requirement(
        db, organization_id=current_user.organization_id, requirement_id=requirement_id
    )
    return RegulatoryRequirementResponse.model_validate(requirement)


@router.post(
    "/compliance-assessments", response_model=ComplianceAssessmentResponse, status_code=201
)
def create_assessment(
    payload: ComplianceAssessmentCreateRequest,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.COMPLIANCE_ASSESS)),
) -> ComplianceAssessmentResponse:
    assessment = compliance_service.create_assessment(
        db,
        organization_id=current_user.organization_id,
        actor_user_id=current_user.id,
        payload=payload,
    )
    return ComplianceAssessmentResponse.model_validate(assessment)


@router.get("/compliance-assessments/{assessment_id}", response_model=ComplianceAssessmentResponse)
def get_assessment(
    assessment_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.COMPLIANCE_ASSESS)),
) -> ComplianceAssessmentResponse:
    assessment = compliance_service.get_assessment(
        db, organization_id=current_user.organization_id, assessment_id=assessment_id
    )
    return ComplianceAssessmentResponse.model_validate(assessment)


@router.post(
    "/compliance-assessments/{assessment_id}/override",
    response_model=ComplianceAssessmentResponse,
)
def override_assessment(
    assessment_id: uuid.UUID,
    payload: ComplianceAssessmentOverrideRequest,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.COMPLIANCE_DECIDE)),
) -> ComplianceAssessmentResponse:
    assessment = compliance_service.override_assessment(
        db,
        organization_id=current_user.organization_id,
        actor_user_id=current_user.id,
        assessment_id=assessment_id,
        payload=payload,
    )
    return ComplianceAssessmentResponse.model_validate(assessment)


@router.get(
    "/aircraft/{aircraft_id}/compliance-assessments",
    response_model=list[ComplianceAssessmentResponse],
)
def list_assessments_for_aircraft(
    aircraft_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.COMPLIANCE_ASSESS)),
) -> list[ComplianceAssessmentResponse]:
    assessments = compliance_service.list_assessments_for_aircraft(
        db, organization_id=current_user.organization_id, aircraft_id=aircraft_id
    )
    return [ComplianceAssessmentResponse.model_validate(a) for a in assessments]


@router.get("/aircraft/{aircraft_id}/compliance-analytics", response_model=dict[str, int])
def get_compliance_analytics(
    aircraft_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.COMPLIANCE_ASSESS)),
) -> dict[str, int]:
    return compliance_service.get_compliance_analytics(
        db, organization_id=current_user.organization_id, aircraft_id=aircraft_id
    )


@router.get(
    "/assets/{asset_id}/compliance-assessments",
    response_model=list[ComplianceAssessmentResponse],
)
def list_assessments_for_asset(
    asset_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.COMPLIANCE_ASSESS)),
) -> list[ComplianceAssessmentResponse]:
    assessments = compliance_service.list_assessments_for_asset(
        db, organization_id=current_user.organization_id, asset_id=asset_id
    )
    return [ComplianceAssessmentResponse.model_validate(a) for a in assessments]


@router.get("/assets/{asset_id}/compliance-analytics", response_model=dict[str, int])
def get_compliance_analytics_for_asset(
    asset_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.COMPLIANCE_ASSESS)),
) -> dict[str, int]:
    return compliance_service.get_compliance_analytics_for_asset(
        db, organization_id=current_user.organization_id, asset_id=asset_id
    )


@router.get(
    "/drones/{asset_id}/compliance-assessments",
    response_model=list[ComplianceAssessmentResponse],
)
def list_assessments_for_drone(
    asset_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.COMPLIANCE_ASSESS)),
) -> list[ComplianceAssessmentResponse]:
    assessments = compliance_service.list_assessments_for_asset(
        db, organization_id=current_user.organization_id, asset_id=asset_id
    )
    return [ComplianceAssessmentResponse.model_validate(a) for a in assessments]


# =========================================================================
# COMPLIANCE OBLIGATIONS & EVIDENCE DIGITAL THREAD (Milestone D2-2)
# =========================================================================


@router.get("/compliance/overview", response_model=ComplianceOverviewResponse)
def get_compliance_overview(
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(
        require_any_permission(Permission.COMPLIANCE_ASSESS, Permission.REGULATION_READ)
    ),
) -> ComplianceOverviewResponse:
    return obligation_service.get_compliance_overview(
        db, organization_id=current_user.organization_id
    )


@router.get("/compliance/obligations", response_model=list[ComplianceObligationResponse])
def list_obligations(
    asset_id: uuid.UUID | None = None,
    aircraft_id: uuid.UUID | None = None,
    requirement_id: uuid.UUID | None = None,
    status: str | None = None,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(
        require_any_permission(Permission.COMPLIANCE_ASSESS, Permission.REGULATION_READ)
    ),
) -> list[ComplianceObligationResponse]:
    obligations = obligation_service.list_obligations(
        db,
        organization_id=current_user.organization_id,
        asset_id=asset_id,
        aircraft_id=aircraft_id,
        requirement_id=requirement_id,
        status=status,
    )
    return [ComplianceObligationResponse.model_validate(o) for o in obligations]


@router.post("/compliance/obligations", response_model=ComplianceObligationResponse, status_code=201)
def create_obligation(
    payload: ComplianceObligationCreateRequest,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(
        require_any_permission(Permission.COMPLIANCE_ASSESS, Permission.COMPLIANCE_DECIDE)
    ),
) -> ComplianceObligationResponse:
    obligation = obligation_service.create_obligation(
        db,
        organization_id=current_user.organization_id,
        actor_user_id=current_user.id,
        payload=payload,
    )
    return ComplianceObligationResponse.model_validate(obligation)


@router.get(
    "/compliance/obligations/{obligation_id}",
    response_model=ComplianceObligationResponse,
)
def get_obligation(
    obligation_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(
        require_any_permission(Permission.COMPLIANCE_ASSESS, Permission.REGULATION_READ)
    ),
) -> ComplianceObligationResponse:
    obligation = obligation_service.get_obligation(
        db, organization_id=current_user.organization_id, obligation_id=obligation_id
    )
    return ComplianceObligationResponse.model_validate(obligation)


@router.patch(
    "/compliance/obligations/{obligation_id}",
    response_model=ComplianceObligationResponse,
)
def update_obligation(
    obligation_id: uuid.UUID,
    payload: ComplianceObligationUpdateRequest,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(
        require_any_permission(Permission.COMPLIANCE_ASSESS, Permission.COMPLIANCE_DECIDE)
    ),
) -> ComplianceObligationResponse:
    obligation = obligation_service.update_obligation(
        db,
        organization_id=current_user.organization_id,
        actor_user_id=current_user.id,
        obligation_id=obligation_id,
        payload=payload,
    )
    return ComplianceObligationResponse.model_validate(obligation)


@router.post(
    "/compliance/obligations/{obligation_id}/evaluate",
    response_model=ComplianceObligationResponse,
)
def evaluate_obligation(
    obligation_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(
        require_any_permission(Permission.COMPLIANCE_ASSESS, Permission.COMPLIANCE_DECIDE)
    ),
) -> ComplianceObligationResponse:
    obligation = obligation_service.evaluate_and_sync_obligation(
        db,
        organization_id=current_user.organization_id,
        actor_user_id=current_user.id,
        obligation_id=obligation_id,
    )
    return ComplianceObligationResponse.model_validate(obligation)


@router.get(
    "/compliance/obligations/{obligation_id}/traceability",
    response_model=ComplianceTraceabilityResponse,
)
def get_obligation_traceability(
    obligation_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(
        require_any_permission(Permission.COMPLIANCE_ASSESS, Permission.REGULATION_READ)
    ),
) -> ComplianceTraceabilityResponse:
    return obligation_service.get_obligation_traceability(
        db, organization_id=current_user.organization_id, obligation_id=obligation_id
    )


@router.get(
    "/compliance/obligations/{obligation_id}/evidence",
    response_model=list[EvidenceResponse],
)
def list_evidence_for_obligation(
    obligation_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(
        require_any_permission(Permission.EVIDENCE_READ, Permission.COMPLIANCE_ASSESS)
    ),
) -> list[EvidenceResponse]:
    # Check obligation exists and belongs to tenant
    obligation_service.get_obligation(
        db, organization_id=current_user.organization_id, obligation_id=obligation_id
    )
    evidence_list = evidence_service.list_evidence_for_obligation(
        db, organization_id=current_user.organization_id, obligation_id=obligation_id
    )
    return [EvidenceResponse.model_validate(e) for e in evidence_list]


@router.post(
    "/compliance/obligations/{obligation_id}/evidence",
    response_model=EvidenceResponse,
    status_code=201,
)
def attach_evidence_to_obligation(
    obligation_id: uuid.UUID,
    payload: EvidenceCreateRequest,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.EVIDENCE_WRITE)),
) -> EvidenceResponse:
    # Check obligation exists and belongs to tenant
    obligation = obligation_service.get_obligation(
        db, organization_id=current_user.organization_id, obligation_id=obligation_id
    )
    evidence = evidence_service.create_evidence(
        db,
        organization_id=current_user.organization_id,
        task_id=payload.task_id,
        uploaded_by_user_id=current_user.id,
        compliance_obligation_id=obligation.id,
        regulatory_requirement_id=obligation.requirement_id,
        asset_id=obligation.asset_id or payload.asset_id,
        aircraft_id=obligation.aircraft_id or payload.aircraft_id,
        component_id=payload.component_id,
        inspection_requirement_id=payload.inspection_requirement_id,
        finding_id=payload.finding_id,
        work_order_id=payload.work_order_id,
        title=payload.title,
        description=payload.description,
        evidence_type=payload.evidence_type,
        source=payload.source,
        captured_at=payload.captured_at,
        provenance=payload.provenance,
    )
    return EvidenceResponse.model_validate(evidence)


# ---------------------------------------------------------------------------
# Compliance Intelligence, Finding Correlation & Readiness Gate Integration
# ---------------------------------------------------------------------------

@router.get(
    "/compliance/assets/{asset_id}/readiness",
    response_model=ComplianceReadinessContribution,
)
@router.get(
    "/compliance/assets/{asset_id}/readiness-contribution",
    response_model=ComplianceReadinessContribution,
)
@router.get(
    "/assets/{asset_id}/readiness/compliance",
    response_model=ComplianceReadinessContribution,
)
def get_asset_compliance_readiness(
    asset_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(
        require_any_permission(
            Permission.COMPLIANCE_ASSESS, Permission.AIRCRAFT_READ, Permission.DRONE_READ
        )
    ),
) -> ComplianceReadinessContribution:
    return intelligence_service.get_asset_compliance_readiness_contribution(
        db, organization_id=current_user.organization_id, asset_id=asset_id
    )


@router.get(
    "/compliance/assets/{asset_id}/impact",
    response_model=AssetComplianceImpactResponse,
)
@router.get(
    "/assets/{asset_id}/compliance-impact",
    response_model=AssetComplianceImpactResponse,
)
def get_asset_compliance_impact(
    asset_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(
        require_any_permission(
            Permission.COMPLIANCE_ASSESS, Permission.AIRCRAFT_READ, Permission.DRONE_READ
        )
    ),
) -> AssetComplianceImpactResponse:
    return intelligence_service.get_asset_compliance_impact(
        db, organization_id=current_user.organization_id, asset_id=asset_id
    )


@router.get(
    "/compliance/findings/{finding_id}/impact",
    response_model=FindingComplianceImpactResponse,
)
@router.get(
    "/findings/{finding_id}/compliance-impact",
    response_model=FindingComplianceImpactResponse,
)
def get_finding_compliance_impact(
    finding_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(
        require_any_permission(
            Permission.COMPLIANCE_ASSESS, Permission.INSPECTION_READ, Permission.AIRCRAFT_READ
        )
    ),
) -> FindingComplianceImpactResponse:
    return intelligence_service.get_finding_compliance_impact(
        db, organization_id=current_user.organization_id, finding_id=finding_id
    )


@router.get(
    "/compliance/inspections/{inspection_id}/impact",
    response_model=InspectionComplianceImpactResponse,
)
@router.get(
    "/inspections/{inspection_id}/compliance-impact",
    response_model=InspectionComplianceImpactResponse,
)
def get_inspection_compliance_impact(
    inspection_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(
        require_any_permission(
            Permission.COMPLIANCE_ASSESS, Permission.INSPECTION_READ, Permission.AIRCRAFT_READ
        )
    ),
) -> InspectionComplianceImpactResponse:
    return intelligence_service.get_inspection_compliance_impact(
        db, organization_id=current_user.organization_id, inspection_requirement_id=inspection_id
    )


@router.post(
    "/compliance/inspections/{inspection_id}/resolve",
    response_model=dict[str, Any],
)
@router.post(
    "/inspections/{inspection_id}/resolve-compliance",
    response_model=dict[str, Any],
)
def resolve_inspection_compliance(
    inspection_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.INSPECTION_WRITE)),
) -> dict[str, Any]:
    return intelligence_service.resolve_inspection_package_compliance(
        db,
        organization_id=current_user.organization_id,
        actor_user_id=current_user.id,
        inspection_requirement_id=inspection_id,
    )


