import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.models.compliance import ComplianceAssessment, RegulatoryRequirement
from app.schemas.compliance import (
    ComplianceAssessmentCreateRequest,
    ComplianceAssessmentOverrideRequest,
    RegulatoryRequirementCreateRequest,
)
from app.services import aircraft_service
from app.services.audit_service import record_audit_event


def create_requirement(
    db: Session,
    *,
    organization_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    payload: RegulatoryRequirementCreateRequest,
) -> RegulatoryRequirement:
    requirement = RegulatoryRequirement(
        organization_id=organization_id,
        authority=payload.authority,
        regulatory_document_id=payload.regulatory_document_id,
        requirement_number=payload.requirement_number,
        title=payload.title,
        description=payload.description,
        effective_date=payload.effective_date,
        compliance_time=payload.compliance_time,
        source_url=payload.source_url,
    )
    db.add(requirement)
    db.flush()
    record_audit_event(
        db,
        organization_id=organization_id,
        user_id=actor_user_id,
        action="regulatory_requirement.created",
        entity_type="RegulatoryRequirement",
        entity_id=requirement.id,
    )
    db.commit()
    db.refresh(requirement)
    return requirement


def get_requirement(
    db: Session, *, organization_id: uuid.UUID, requirement_id: uuid.UUID
) -> RegulatoryRequirement:
    requirement = db.execute(
        select(RegulatoryRequirement).where(
            RegulatoryRequirement.id == requirement_id,
            RegulatoryRequirement.organization_id == organization_id,
        )
    ).scalar_one_or_none()
    if requirement is None:
        raise NotFoundError("Regulatory requirement not found")
    return requirement


def list_requirements(
    db: Session, *, organization_id: uuid.UUID
) -> list[RegulatoryRequirement]:
    return list(
        db.execute(
            select(RegulatoryRequirement).where(
                RegulatoryRequirement.organization_id == organization_id
            )
        )
        .scalars()
        .all()
    )


def create_assessment(
    db: Session,
    *,
    organization_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    payload: ComplianceAssessmentCreateRequest,
) -> ComplianceAssessment:
    aircraft_service.get_aircraft(
        db, organization_id=organization_id, aircraft_id=payload.aircraft_id
    )
    get_requirement(db, organization_id=organization_id, requirement_id=payload.requirement_id)

    assessment = ComplianceAssessment(
        organization_id=organization_id,
        aircraft_id=payload.aircraft_id,
        requirement_id=payload.requirement_id,
        status=payload.status,
        evaluated_at=payload.evaluated_at,
        evaluated_by_user_id=actor_user_id,
        notes=payload.notes,
    )
    db.add(assessment)
    db.flush()
    record_audit_event(
        db,
        organization_id=organization_id,
        user_id=actor_user_id,
        action="compliance_assessment.created",
        entity_type="ComplianceAssessment",
        entity_id=assessment.id,
        metadata={"status": payload.status},
    )
    db.commit()
    db.refresh(assessment)
    return assessment


def get_assessment(
    db: Session, *, organization_id: uuid.UUID, assessment_id: uuid.UUID
) -> ComplianceAssessment:
    assessment = db.execute(
        select(ComplianceAssessment).where(
            ComplianceAssessment.id == assessment_id,
            ComplianceAssessment.organization_id == organization_id,
        )
    ).scalar_one_or_none()
    if assessment is None:
        raise NotFoundError("Compliance assessment not found")
    return assessment


def list_assessments_for_aircraft(
    db: Session, *, organization_id: uuid.UUID, aircraft_id: uuid.UUID
) -> list[ComplianceAssessment]:
    return list(
        db.execute(
            select(ComplianceAssessment).where(
                ComplianceAssessment.organization_id == organization_id,
                ComplianceAssessment.aircraft_id == aircraft_id,
            )
        )
        .scalars()
        .all()
    )


def override_assessment(
    db: Session,
    *,
    organization_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    assessment_id: uuid.UUID,
    payload: ComplianceAssessmentOverrideRequest,
) -> ComplianceAssessment:
    assessment = get_assessment(
        db, organization_id=organization_id, assessment_id=assessment_id
    )
    previous_status = assessment.status
    assessment.status = payload.status
    assessment.override_reason = payload.override_reason
    assessment.overridden_by_user_id = actor_user_id
    db.add(assessment)
    record_audit_event(
        db,
        organization_id=organization_id,
        user_id=actor_user_id,
        action="compliance_assessment.overridden",
        entity_type="ComplianceAssessment",
        entity_id=assessment.id,
        metadata={
            "from_status": previous_status,
            "to_status": payload.status,
            "reason": payload.override_reason,
        },
    )
    db.commit()
    db.refresh(assessment)
    return assessment


def get_compliance_analytics(
    db: Session, *, organization_id: uuid.UUID, aircraft_id: uuid.UUID
) -> dict[str, int]:
    """Aggregate assessment counts by status for one aircraft — the honest,
    directly-countable version of getComplianceAnalytics; this slice does not
    attempt the frontend's fuller analytics (which also factor in condition-
    tree confidence scores that have no backend equivalent yet).
    """
    assessments = list_assessments_for_aircraft(
        db, organization_id=organization_id, aircraft_id=aircraft_id
    )
    counts: dict[str, int] = {}
    for assessment in assessments:
        counts[assessment.status] = counts.get(assessment.status, 0) + 1
    return counts
