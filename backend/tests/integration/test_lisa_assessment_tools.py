"""Tests for the new Lisa assessment tools (app/services/ai/tools.py):
RBAC enforcement, tenant isolation, and the ASSESSMENT intent/investigator
that wires them into deterministic orchestration.
"""
import uuid

import pytest

from app.core.errors import ForbiddenError, NotFoundError
from app.models.organization import Organization
from app.models.user import User
from app.schemas.assessment import AssessmentCreateRequest
from app.schemas.auth import CurrentUser
from app.services.ai.tools import execute_tool
from app.services.assessment import engine
from app.services.lisa.intent_service import Intent, classify_intent
from app.services.lisa.message_resolution_service import resolve_message
from app.services.lisa.orchestration_service import investigate


def _user(org_id: uuid.UUID, roles: list[str]) -> CurrentUser:
    return CurrentUser(
        id=uuid.uuid4(),
        organization_id=org_id,
        email="lisa-assessment-test@example.com",
        full_name="Assessment Tool Test User",
        roles=roles,
    )


def _create_org_user(db_session, org_id):
    if db_session.get(Organization, org_id) is None:
        db_session.add(Organization(id=org_id, name="Test Org"))
        db_session.commit()
    user = User(
        organization_id=org_id,
        email=f"{uuid.uuid4()}@example.com",
        hashed_password="not-a-real-hash",
        full_name="Test User",
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def test_intent_classifies_assessment_questions():
    assert classify_intent("What are our biggest operational risks?") == Intent.ASSESSMENT
    assert classify_intent("Show me the roadmap") == Intent.ASSESSMENT
    assert classify_intent("What should we improve first?") == Intent.ASSESSMENT


def test_get_assessments_tool_scoped_to_tenant(db_session):
    org_a = uuid.uuid4()
    org_b = uuid.uuid4()
    _create_org_user(db_session, org_a)
    engine.create_assessment(
        db_session,
        organization_id=org_a,
        actor_user_id=None,
        payload=AssessmentCreateRequest(name="Org A Assessment"),
    )
    user_b = _user(org_b, ["ORG_ADMIN"])
    result = execute_tool(db_session, user_b, "get_assessments", {})
    assert result["assessments"] == []


def test_viewer_can_read_but_not_run_assessment(db_session):
    org_id = uuid.uuid4()
    _create_org_user(db_session, org_id)
    assessment = engine.create_assessment(
        db_session,
        organization_id=org_id,
        actor_user_id=None,
        payload=AssessmentCreateRequest(name="Fleet Assessment"),
    )
    viewer = _user(org_id, ["VIEWER"])

    result = execute_tool(
        db_session, viewer, "get_assessment", {"assessment_id": str(assessment.id)}
    )
    assert result["assessment"]["name"] == "Fleet Assessment"

    with pytest.raises(ForbiddenError):
        execute_tool(db_session, viewer, "run_assessment", {"assessment_id": str(assessment.id)})


def test_get_assessment_tool_tenant_isolated(db_session):
    org_a = uuid.uuid4()
    org_b = uuid.uuid4()
    _create_org_user(db_session, org_a)
    assessment = engine.create_assessment(
        db_session,
        organization_id=org_a,
        actor_user_id=None,
        payload=AssessmentCreateRequest(name="Org A Assessment"),
    )
    user_b = _user(org_b, ["ORG_ADMIN"])
    with pytest.raises(NotFoundError):
        execute_tool(db_session, user_b, "get_assessment", {"assessment_id": str(assessment.id)})


def test_run_assessment_tool_produces_snapshot_and_findings(db_session):
    org_id = uuid.uuid4()
    _create_org_user(db_session, org_id)
    assessment = engine.create_assessment(
        db_session,
        organization_id=org_id,
        actor_user_id=None,
        payload=AssessmentCreateRequest(name="Fleet Assessment"),
    )
    admin = _user(org_id, ["ORG_ADMIN"])
    run_result = execute_tool(
        db_session, admin, "run_assessment", {"assessment_id": str(assessment.id)}
    )
    assert run_result["snapshot"]["version"] == 1
    assert run_result["snapshot"]["finding_count"] == 0

    findings_result = execute_tool(
        db_session, admin, "get_assessment_findings", {"assessment_id": str(assessment.id)}
    )
    assert findings_result["findings"] == []

    risks_result = execute_tool(
        db_session, admin, "get_assessment_risks", {"assessment_id": str(assessment.id)}
    )
    assert risks_result["risks"] == []

    roadmap_result = execute_tool(
        db_session, admin, "get_assessment_roadmap", {"assessment_id": str(assessment.id)}
    )
    assert roadmap_result["roadmap"] == []


def test_compare_assessment_snapshots_tool(db_session):
    org_id = uuid.uuid4()
    _create_org_user(db_session, org_id)
    assessment = engine.create_assessment(
        db_session,
        organization_id=org_id,
        actor_user_id=None,
        payload=AssessmentCreateRequest(name="Fleet Assessment"),
    )
    admin = _user(org_id, ["ORG_ADMIN"])
    snap1 = execute_tool(db_session, admin, "run_assessment", {"assessment_id": str(assessment.id)})
    snap2 = execute_tool(db_session, admin, "run_assessment", {"assessment_id": str(assessment.id)})

    comparison = execute_tool(
        db_session,
        admin,
        "compare_assessment_snapshots",
        {
            "snapshot_id_a": snap1["snapshot"]["id"],
            "snapshot_id_b": snap2["snapshot"]["id"],
        },
    )
    assert comparison["from_version"] == 1
    assert comparison["to_version"] == 2
    assert comparison["new_findings"] == []
    assert comparison["resolved_findings"] == []


def test_assessment_investigator_answers_when_no_assessments_exist(db_session):
    org_id = uuid.uuid4()
    db_user = _create_org_user(db_session, org_id)
    user = _user(org_id, ["ORG_ADMIN"])
    resolution = resolve_message(
        db_session,
        organization_id=org_id,
        user_id=db_user.id,
        question="What are our biggest operational risks?",
    )

    result = investigate(
        db_session, user, question="What are our biggest operational risks?", resolution=resolution
    )
    assert result is not None
    assert result.intent == Intent.ASSESSMENT.value
    assert result.status == "ANSWERED"
    assert "No assessments" in result.headline


def test_assessment_investigator_surfaces_top_finding(db_session):
    org_id = uuid.uuid4()
    db_user = _create_org_user(db_session, org_id)
    assessment = engine.create_assessment(
        db_session,
        organization_id=org_id,
        actor_user_id=None,
        payload=AssessmentCreateRequest(name="Fleet Assessment"),
    )
    admin = _user(org_id, ["ORG_ADMIN"])
    execute_tool(db_session, admin, "run_assessment", {"assessment_id": str(assessment.id)})

    resolution = resolve_message(
        db_session,
        organization_id=org_id,
        user_id=db_user.id,
        question="What should we improve first?",
    )
    result = investigate(
        db_session, admin, question="What should we improve first?", resolution=resolution
    )
    assert result is not None
    assert result.status == "ANSWERED"
    assert "finding" in result.headline.lower() or "score" in result.headline.lower()
