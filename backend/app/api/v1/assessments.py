import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.deps import get_db_session, require_permission
from app.core.errors import NotFoundError
from app.core.permissions import Permission
from app.schemas.assessment import (
    AssessmentCreateRequest,
    AssessmentFindingResponse,
    AssessmentGapResponse,
    AssessmentRecommendationResponse,
    AssessmentResponse,
    AssessmentRiskResponse,
    AssessmentRoadmapItemResponse,
    AssessmentSnapshotComparisonResponse,
    AssessmentSnapshotResponse,
)
from app.schemas.auth import CurrentUser
from app.services.assessment import engine

router = APIRouter(prefix="/assessments", tags=["assessments"])


@router.post("", response_model=AssessmentResponse, status_code=201)
def create_assessment(
    payload: AssessmentCreateRequest,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.ASSESSMENT_WRITE)),
) -> AssessmentResponse:
    assessment = engine.create_assessment(
        db,
        organization_id=current_user.organization_id,
        actor_user_id=current_user.id,
        payload=payload,
    )
    return AssessmentResponse.model_validate(assessment)


@router.get("", response_model=list[AssessmentResponse])
def list_assessments(
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.ASSESSMENT_READ)),
) -> list[AssessmentResponse]:
    assessments = engine.list_assessments(db, organization_id=current_user.organization_id)
    return [AssessmentResponse.model_validate(a) for a in assessments]


@router.get("/{assessment_id}", response_model=AssessmentResponse)
def get_assessment(
    assessment_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.ASSESSMENT_READ)),
) -> AssessmentResponse:
    assessment = engine.get_assessment(
        db, organization_id=current_user.organization_id, assessment_id=assessment_id
    )
    return AssessmentResponse.model_validate(assessment)


@router.post("/{assessment_id}/run", response_model=AssessmentSnapshotResponse)
def run_assessment(
    assessment_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.ASSESSMENT_WRITE)),
) -> AssessmentSnapshotResponse:
    snapshot = engine.run_assessment(
        db,
        organization_id=current_user.organization_id,
        actor_user_id=current_user.id,
        assessment_id=assessment_id,
    )
    return AssessmentSnapshotResponse.model_validate(snapshot)


@router.get("/{assessment_id}/snapshot", response_model=AssessmentSnapshotResponse)
def get_latest_snapshot(
    assessment_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.ASSESSMENT_READ)),
) -> AssessmentSnapshotResponse:
    engine.get_assessment(
        db, organization_id=current_user.organization_id, assessment_id=assessment_id
    )
    snapshot = engine.get_latest_snapshot(
        db, organization_id=current_user.organization_id, assessment_id=assessment_id
    )
    if snapshot is None:
        raise NotFoundError("This assessment has not been run yet — no snapshot exists.")
    return AssessmentSnapshotResponse.model_validate(snapshot)


@router.get("/{assessment_id}/findings", response_model=list[AssessmentFindingResponse])
def get_findings(
    assessment_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.ASSESSMENT_READ)),
) -> list[AssessmentFindingResponse]:
    engine.get_assessment(
        db, organization_id=current_user.organization_id, assessment_id=assessment_id
    )
    snapshot = engine.get_latest_snapshot(
        db, organization_id=current_user.organization_id, assessment_id=assessment_id
    )
    if snapshot is None:
        return []
    return [AssessmentFindingResponse.model_validate(f) for f in snapshot.findings]


@router.get("/{assessment_id}/risks", response_model=list[AssessmentRiskResponse])
def get_risks(
    assessment_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.ASSESSMENT_READ)),
) -> list[AssessmentRiskResponse]:
    engine.get_assessment(
        db, organization_id=current_user.organization_id, assessment_id=assessment_id
    )
    snapshot = engine.get_latest_snapshot(
        db, organization_id=current_user.organization_id, assessment_id=assessment_id
    )
    if snapshot is None:
        return []
    return [AssessmentRiskResponse.model_validate(r) for r in snapshot.risks]


@router.get("/{assessment_id}/gaps", response_model=list[AssessmentGapResponse])
def get_gaps(
    assessment_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.ASSESSMENT_READ)),
) -> list[AssessmentGapResponse]:
    engine.get_assessment(
        db, organization_id=current_user.organization_id, assessment_id=assessment_id
    )
    snapshot = engine.get_latest_snapshot(
        db, organization_id=current_user.organization_id, assessment_id=assessment_id
    )
    if snapshot is None:
        return []
    return [AssessmentGapResponse.model_validate(g) for g in snapshot.gaps]


@router.get(
    "/{assessment_id}/recommendations", response_model=list[AssessmentRecommendationResponse]
)
def get_recommendations(
    assessment_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.ASSESSMENT_READ)),
) -> list[AssessmentRecommendationResponse]:
    engine.get_assessment(
        db, organization_id=current_user.organization_id, assessment_id=assessment_id
    )
    snapshot = engine.get_latest_snapshot(
        db, organization_id=current_user.organization_id, assessment_id=assessment_id
    )
    if snapshot is None:
        return []
    return [AssessmentRecommendationResponse.model_validate(r) for r in snapshot.recommendations]


@router.get("/{assessment_id}/roadmap", response_model=list[AssessmentRoadmapItemResponse])
def get_roadmap(
    assessment_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.ASSESSMENT_READ)),
) -> list[AssessmentRoadmapItemResponse]:
    engine.get_assessment(
        db, organization_id=current_user.organization_id, assessment_id=assessment_id
    )
    snapshot = engine.get_latest_snapshot(
        db, organization_id=current_user.organization_id, assessment_id=assessment_id
    )
    if snapshot is None:
        return []
    return sorted(
        [AssessmentRoadmapItemResponse.model_validate(r) for r in snapshot.roadmap_items],
        key=lambda r: r.sequence,
    )


@router.get(
    "/compare/{snapshot_id_a}/{snapshot_id_b}",
    response_model=AssessmentSnapshotComparisonResponse,
)
def compare_snapshots(
    snapshot_id_a: uuid.UUID,
    snapshot_id_b: uuid.UUID,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.ASSESSMENT_READ)),
) -> AssessmentSnapshotComparisonResponse:
    comparison = engine.compare_snapshots(
        db,
        organization_id=current_user.organization_id,
        snapshot_id_a=snapshot_id_a,
        snapshot_id_b=snapshot_id_b,
    )
    return AssessmentSnapshotComparisonResponse(
        from_version=comparison.from_version,
        to_version=comparison.to_version,
        score_delta=comparison.score_delta,
        new_findings=[AssessmentFindingResponse.model_validate(f) for f in comparison.new_findings],
        resolved_findings=comparison.resolved_findings,
    )
