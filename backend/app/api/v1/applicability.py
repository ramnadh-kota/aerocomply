"""API endpoints for Aerospace Applicability & Condition Tree Engine."""

import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import (
    get_db_session,
    require_any_permission,
    require_feature,
    require_permission,
)
from app.core.errors import NotFoundError
from app.core.permissions import Permission
from app.models.applicability import ApplicabilityEvaluation
from app.schemas.applicability import (
    ApplicabilityEvaluationRequest,
    ApplicabilityEvaluationResponse,
    ApplicabilityRuleCreateRequest,
    ApplicabilityRuleResponse,
)
from app.schemas.auth import CurrentUser
from app.services import applicability as applicability_service

router = APIRouter(tags=["applicability"])


@router.post(
    "/rules",
    response_model=ApplicabilityRuleResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create applicability rule with condition tree",
)
def create_applicability_rule(
    payload: ApplicabilityRuleCreateRequest,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(
        require_any_permission(Permission.REGULATION_WRITE, Permission.COMPLIANCE_ASSESS)
    ),
    _entitled: CurrentUser = Depends(require_feature("compliance_management")),
) -> ApplicabilityRuleResponse:
    rule = applicability_service.create_rule(
        db,
        organization_id=current_user.organization_id,
        actor_user_id=current_user.id,
        payload=payload,
    )
    return ApplicabilityRuleResponse.model_validate(rule)


@router.get(
    "/rules",
    response_model=list[ApplicabilityRuleResponse],
    summary="List tenant applicability rules",
)
def list_applicability_rules(
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(
        require_any_permission(Permission.REGULATION_READ, Permission.COMPLIANCE_ASSESS)
    ),
    _entitled: CurrentUser = Depends(require_feature("compliance_management")),
) -> list[ApplicabilityRuleResponse]:
    rules = applicability_service.list_rules(
        db,
        organization_id=current_user.organization_id,
    )
    return [ApplicabilityRuleResponse.model_validate(r) for r in rules]


@router.get(
    "/rules/{rule_id}",
    response_model=ApplicabilityRuleResponse,
    summary="Get single applicability rule detail",
)
def get_applicability_rule(
    rule_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(
        require_any_permission(Permission.REGULATION_READ, Permission.COMPLIANCE_ASSESS)
    ),
    _entitled: CurrentUser = Depends(require_feature("compliance_management")),
) -> ApplicabilityRuleResponse:
    rule = applicability_service.get_rule(
        db,
        organization_id=current_user.organization_id,
        rule_id=rule_id,
    )
    return ApplicabilityRuleResponse.model_validate(rule)


@router.post(
    "/evaluate",
    response_model=ApplicabilityEvaluationResponse,
    status_code=status.HTTP_200_OK,
    summary="Evaluate applicability of a rule against an aircraft/asset",
)
def evaluate_applicability(
    payload: ApplicabilityEvaluationRequest,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.COMPLIANCE_ASSESS)),
    _entitled: CurrentUser = Depends(require_feature("compliance_management")),
) -> ApplicabilityEvaluationResponse:
    evaluation = applicability_service.evaluate_applicability(
        db,
        organization_id=current_user.organization_id,
        actor_user_id=current_user.id,
        payload=payload,
    )
    return ApplicabilityEvaluationResponse.model_validate(evaluation)


@router.get(
    "/evaluations/{evaluation_id}",
    response_model=ApplicabilityEvaluationResponse,
    summary="Retrieve an immutable historical applicability evaluation snapshot",
)
def get_evaluation(
    evaluation_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.COMPLIANCE_ASSESS)),
    _entitled: CurrentUser = Depends(require_feature("compliance_management")),
) -> ApplicabilityEvaluationResponse:
    evaluation = db.execute(
        select(ApplicabilityEvaluation).where(
            ApplicabilityEvaluation.id == evaluation_id,
            ApplicabilityEvaluation.organization_id == current_user.organization_id,
        )
    ).scalar_one_or_none()

    if evaluation is None:
        raise NotFoundError(f"Evaluation {evaluation_id} not found.")

    return ApplicabilityEvaluationResponse.model_validate(evaluation)
