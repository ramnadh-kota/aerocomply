import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.deps import get_db_session, require_permission
from app.core.permissions import Permission
from app.schemas.auth import CurrentUser
from app.schemas.compliance import (
    ComplianceAssessmentCreateRequest,
    ComplianceAssessmentOverrideRequest,
    ComplianceAssessmentResponse,
    RegulatoryRequirementCreateRequest,
    RegulatoryRequirementResponse,
)
from app.services import compliance_service

router = APIRouter(tags=["compliance"])


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
