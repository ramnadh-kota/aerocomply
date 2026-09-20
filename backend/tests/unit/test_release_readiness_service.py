import datetime
import uuid

import pytest

from app.core.errors import NotFoundError
from app.models.compliance import ComplianceAssessment, ComplianceAssessmentStatus
from app.models.evidence import Evidence, EvidenceStatus
from app.models.finding import Finding, FindingSeverity, FindingStatus
from app.models.inspection_requirement import InspectionRequirement, InspectionRequirementStatus
from app.models.part_requirement import PartRequirement, PartRequirementStatus
from app.models.task import Task
from app.models.work_order import WorkOrder
from app.services import release_readiness_service


class _FakeScalarsResult:
    def __init__(self, values):
        self._values = values

    def all(self):
        return self._values


class _FakeExecResult:
    def __init__(self, *, scalar=None, scalars_values=None):
        self._scalar = scalar
        self._scalars_values = scalars_values or []

    def scalar_one_or_none(self):
        return self._scalar

    def scalars(self):
        return _FakeScalarsResult(self._scalars_values)


class _FakeSession:
    """Returns canned results in call order — one entry per db.execute() call
    the service under test makes, mirroring test_inspection_lifecycle.py's
    FakeSession pattern."""

    def __init__(self, results):
        self._results = list(results)

    def execute(self, _stmt):
        return self._results.pop(0)


def _work_order(org_id, **overrides) -> WorkOrder:
    defaults = dict(
        id=uuid.uuid4(),
        organization_id=org_id,
        aircraft_id=uuid.uuid4(),
        work_order_number="WO-1",
        status="OPEN",
        priority="NORMAL",
        created_by_user_id=None,
    )
    defaults.update(overrides)
    wo = WorkOrder()
    for key, value in defaults.items():
        setattr(wo, key, value)
    return wo


def _task(org_id, wo_id, **overrides) -> Task:
    defaults = dict(
        id=uuid.uuid4(),
        organization_id=org_id,
        work_order_id=wo_id,
        description="Do the thing",
        execution_state="PENDING",
        evidence_required=False,
    )
    defaults.update(overrides)
    task = Task()
    for key, value in defaults.items():
        setattr(task, key, value)
    return task


def _part_requirement(org_id, wo_id, **overrides) -> PartRequirement:
    defaults = dict(
        id=uuid.uuid4(),
        organization_id=org_id,
        work_order_id=wo_id,
        task_id=None,
        part_id=uuid.uuid4(),
        required_quantity=1,
        fulfilled_quantity=0,
        status=PartRequirementStatus.REQUIRED,
        priority="NORMAL",
        created_by_user_id=None,
    )
    defaults.update(overrides)
    req = PartRequirement()
    for key, value in defaults.items():
        setattr(req, key, value)
    return req


def _assessment(org_id, asset_id, requirement_id=None, **overrides) -> ComplianceAssessment:
    defaults = dict(
        id=uuid.uuid4(),
        organization_id=org_id,
        aircraft_id=uuid.uuid4(),
        asset_id=asset_id,
        requirement_id=requirement_id or uuid.uuid4(),
        status=ComplianceAssessmentStatus.COMPLIANT,
        evaluated_at=datetime.date(2026, 1, 1),
        created_at=datetime.datetime(2026, 1, 1),
        evaluated_by_user_id=None,
        notes=None,
        override_reason=None,
        overridden_by_user_id=None,
    )
    defaults.update(overrides)
    assessment = ComplianceAssessment()
    for key, value in defaults.items():
        setattr(assessment, key, value)
    return assessment


def _evidence(org_id, task_id, **overrides) -> Evidence:
    defaults = dict(
        id=uuid.uuid4(),
        organization_id=org_id,
        task_id=task_id,
        uploaded_by_user_id=uuid.uuid4(),
        status=EvidenceStatus.UPLOADED.value,
        reviewer_user_id=None,
        rejection_reason=None,
    )
    defaults.update(overrides)
    evidence = Evidence()
    for key, value in defaults.items():
        setattr(evidence, key, value)
    return evidence


def _requirement(org_id, **overrides) -> InspectionRequirement:
    defaults = dict(
        id=uuid.uuid4(),
        organization_id=org_id,
        task_id=None,
        work_order_id=None,
        required=True,
        inspector_user_id=None,
        status=InspectionRequirementStatus.PENDING.value,
        rejection_reason=None,
    )
    defaults.update(overrides)
    req = InspectionRequirement()
    for key, value in defaults.items():
        setattr(req, key, value)
    return req


def _finding(org_id, **overrides) -> Finding:
    defaults = dict(
        id=uuid.uuid4(),
        organization_id=org_id,
        aircraft_id=None,
        asset_id=None,
        component_id=None,
        inspection_requirement_id=None,
        work_order_id=None,
        task_id=None,
        title="Cracked bracket",
        description="Found during inspection",
        severity=FindingSeverity.MAJOR,
        status=FindingStatus.OPEN,
    )
    defaults.update(overrides)
    finding = Finding()
    for key, value in defaults.items():
        setattr(finding, key, value)
    return finding


def test_not_found_when_work_order_missing():
    org_id = uuid.uuid4()
    db = _FakeSession([_FakeExecResult(scalar=None)])

    with pytest.raises(NotFoundError):
        release_readiness_service.get_release_readiness_for_work_order(
            db, organization_id=org_id, work_order_id=uuid.uuid4()
        )


def test_zero_blockers_is_ready():
    org_id = uuid.uuid4()
    wo = _work_order(org_id)
    db = _FakeSession(
        [
            _FakeExecResult(scalar=wo),
            _FakeExecResult(scalars_values=[]),  # tasks
            _FakeExecResult(scalars_values=[]),  # inspection requirements (no task_ids)
            _FakeExecResult(scalars_values=[]),  # part requirements
            _FakeExecResult(scalars_values=[]),  # findings
        ]
    )

    result = release_readiness_service.get_release_readiness_for_work_order(
        db, organization_id=org_id, work_order_id=wo.id
    )

    assert result.status == "READY"
    assert result.blockers == []
    assert "not yet backend-tracked" in result.data_completeness


def test_task_execution_blocker_when_task_not_completed():
    org_id = uuid.uuid4()
    wo = _work_order(org_id)
    task = _task(org_id, wo.id, execution_state="PENDING")
    db = _FakeSession(
        [
            _FakeExecResult(scalar=wo),
            _FakeExecResult(scalars_values=[task]),
            _FakeExecResult(scalars_values=[]),  # evidence
            _FakeExecResult(scalars_values=[]),  # inspections
            _FakeExecResult(scalars_values=[]),  # part requirements
            _FakeExecResult(scalars_values=[]),  # findings
        ]
    )

    result = release_readiness_service.get_release_readiness_for_work_order(
        db, organization_id=org_id, work_order_id=wo.id
    )

    assert result.status == "BLOCKED"
    assert len(result.blockers) == 1
    assert result.blockers[0].category == "TASK_EXECUTION"
    assert result.blockers[0].related_record_id == task.id


def test_evidence_blocker_when_not_accepted():
    org_id = uuid.uuid4()
    wo = _work_order(org_id)
    task = _task(org_id, wo.id, execution_state="COMPLETED")
    evidence = _evidence(org_id, task.id, status=EvidenceStatus.SUBMITTED.value)
    db = _FakeSession(
        [
            _FakeExecResult(scalar=wo),
            _FakeExecResult(scalars_values=[task]),
            _FakeExecResult(scalars_values=[evidence]),
            _FakeExecResult(scalars_values=[]),  # inspections
            _FakeExecResult(scalars_values=[]),  # part requirements
            _FakeExecResult(scalars_values=[]),  # findings
        ]
    )

    result = release_readiness_service.get_release_readiness_for_work_order(
        db, organization_id=org_id, work_order_id=wo.id
    )

    assert result.status == "BLOCKED"
    assert len(result.blockers) == 1
    assert result.blockers[0].category == "EVIDENCE"
    assert result.blockers[0].related_record_id == evidence.id


def test_inspection_blocker_when_not_completed_or_not_required():
    org_id = uuid.uuid4()
    wo = _work_order(org_id)
    task = _task(org_id, wo.id, execution_state="COMPLETED")
    requirement = _requirement(
        org_id, work_order_id=wo.id, status=InspectionRequirementStatus.PENDING.value
    )
    db = _FakeSession(
        [
            _FakeExecResult(scalar=wo),
            _FakeExecResult(scalars_values=[task]),
            _FakeExecResult(scalars_values=[]),  # evidence
            _FakeExecResult(scalars_values=[requirement]),
            _FakeExecResult(scalars_values=[]),  # part requirements
            _FakeExecResult(scalars_values=[]),  # findings
        ]
    )

    result = release_readiness_service.get_release_readiness_for_work_order(
        db, organization_id=org_id, work_order_id=wo.id
    )

    assert result.status == "BLOCKED"
    assert len(result.blockers) == 1
    assert result.blockers[0].category == "INSPECTION"
    assert result.blockers[0].related_record_id == requirement.id


def test_accepted_evidence_and_completed_inspection_do_not_block():
    org_id = uuid.uuid4()
    wo = _work_order(org_id)
    task = _task(org_id, wo.id, execution_state="COMPLETED")
    evidence = _evidence(org_id, task.id, status=EvidenceStatus.ACCEPTED.value)
    requirement = _requirement(
        org_id, work_order_id=wo.id, status=InspectionRequirementStatus.COMPLETED.value
    )
    db = _FakeSession(
        [
            _FakeExecResult(scalar=wo),
            _FakeExecResult(scalars_values=[task]),
            _FakeExecResult(scalars_values=[evidence]),
            _FakeExecResult(scalars_values=[requirement]),
            _FakeExecResult(scalars_values=[]),  # part requirements
            _FakeExecResult(scalars_values=[]),  # findings
        ]
    )

    result = release_readiness_service.get_release_readiness_for_work_order(
        db, organization_id=org_id, work_order_id=wo.id
    )

    assert result.status == "READY"
    assert result.blockers == []


def test_evidence_required_but_missing_blocks():
    org_id = uuid.uuid4()
    wo = _work_order(org_id)
    task = _task(org_id, wo.id, execution_state="COMPLETED", evidence_required=True)
    db = _FakeSession(
        [
            _FakeExecResult(scalar=wo),
            _FakeExecResult(scalars_values=[task]),
            _FakeExecResult(scalars_values=[]),  # evidence -- none submitted
            _FakeExecResult(scalars_values=[]),  # inspections
            _FakeExecResult(scalars_values=[]),  # part requirements
            _FakeExecResult(scalars_values=[]),  # findings
        ]
    )

    result = release_readiness_service.get_release_readiness_for_work_order(
        db, organization_id=org_id, work_order_id=wo.id
    )

    assert result.status == "BLOCKED"
    assert len(result.blockers) == 1
    assert result.blockers[0].category == "EVIDENCE"
    assert result.blockers[0].related_record_id == task.id


def test_evidence_required_satisfied_by_accepted_evidence():
    org_id = uuid.uuid4()
    wo = _work_order(org_id)
    task = _task(org_id, wo.id, execution_state="COMPLETED", evidence_required=True)
    evidence = _evidence(org_id, task.id, status=EvidenceStatus.ACCEPTED.value)
    db = _FakeSession(
        [
            _FakeExecResult(scalar=wo),
            _FakeExecResult(scalars_values=[task]),
            _FakeExecResult(scalars_values=[evidence]),
            _FakeExecResult(scalars_values=[]),  # inspections
            _FakeExecResult(scalars_values=[]),  # part requirements
            _FakeExecResult(scalars_values=[]),  # findings
        ]
    )

    result = release_readiness_service.get_release_readiness_for_work_order(
        db, organization_id=org_id, work_order_id=wo.id
    )

    assert result.status == "READY"
    assert result.blockers == []


def test_evidence_not_required_and_missing_does_not_block():
    org_id = uuid.uuid4()
    wo = _work_order(org_id)
    task = _task(org_id, wo.id, execution_state="COMPLETED", evidence_required=False)
    db = _FakeSession(
        [
            _FakeExecResult(scalar=wo),
            _FakeExecResult(scalars_values=[task]),
            _FakeExecResult(scalars_values=[]),  # evidence
            _FakeExecResult(scalars_values=[]),  # inspections
            _FakeExecResult(scalars_values=[]),  # part requirements
            _FakeExecResult(scalars_values=[]),  # findings
        ]
    )

    result = release_readiness_service.get_release_readiness_for_work_order(
        db, organization_id=org_id, work_order_id=wo.id
    )

    assert result.status == "READY"
    assert result.blockers == []


def test_material_blocker_when_short():
    org_id = uuid.uuid4()
    wo = _work_order(org_id)
    part_req = _part_requirement(
        org_id, wo.id, required_quantity=3, fulfilled_quantity=1, status=PartRequirementStatus.SHORT
    )
    db = _FakeSession(
        [
            _FakeExecResult(scalar=wo),
            _FakeExecResult(scalars_values=[]),  # tasks
            _FakeExecResult(scalars_values=[]),  # inspections
            _FakeExecResult(scalars_values=[part_req]),
            _FakeExecResult(scalars_values=[]),  # findings
        ]
    )

    result = release_readiness_service.get_release_readiness_for_work_order(
        db, organization_id=org_id, work_order_id=wo.id
    )

    assert result.status == "BLOCKED"
    assert len(result.blockers) == 1
    assert result.blockers[0].category == "MATERIAL"
    assert result.blockers[0].related_record_id == part_req.id


def test_material_no_blocker_when_fulfilled_quantity_met():
    org_id = uuid.uuid4()
    wo = _work_order(org_id)
    part_req = _part_requirement(
        org_id,
        wo.id,
        required_quantity=2,
        fulfilled_quantity=2,
        status=PartRequirementStatus.RECEIVED,
    )
    db = _FakeSession(
        [
            _FakeExecResult(scalar=wo),
            _FakeExecResult(scalars_values=[]),
            _FakeExecResult(scalars_values=[]),
            _FakeExecResult(scalars_values=[part_req]),
            _FakeExecResult(scalars_values=[]),  # findings
        ]
    )

    result = release_readiness_service.get_release_readiness_for_work_order(
        db, organization_id=org_id, work_order_id=wo.id
    )

    assert result.status == "READY"
    assert result.blockers == []


def test_material_no_blocker_when_cancelled_even_if_short():
    org_id = uuid.uuid4()
    wo = _work_order(org_id)
    part_req = _part_requirement(
        org_id,
        wo.id,
        required_quantity=5,
        fulfilled_quantity=0,
        status=PartRequirementStatus.CANCELLED,
    )
    db = _FakeSession(
        [
            _FakeExecResult(scalar=wo),
            _FakeExecResult(scalars_values=[]),
            _FakeExecResult(scalars_values=[]),
            _FakeExecResult(scalars_values=[part_req]),
            _FakeExecResult(scalars_values=[]),  # findings
        ]
    )

    result = release_readiness_service.get_release_readiness_for_work_order(
        db, organization_id=org_id, work_order_id=wo.id
    )

    assert result.status == "READY"
    assert result.blockers == []


def test_material_multiple_outstanding_requirements_each_block():
    org_id = uuid.uuid4()
    wo = _work_order(org_id)
    part_req_1 = _part_requirement(org_id, wo.id, required_quantity=2, fulfilled_quantity=0)
    part_req_2 = _part_requirement(org_id, wo.id, required_quantity=1, fulfilled_quantity=0)
    db = _FakeSession(
        [
            _FakeExecResult(scalar=wo),
            _FakeExecResult(scalars_values=[]),
            _FakeExecResult(scalars_values=[]),
            _FakeExecResult(scalars_values=[part_req_1, part_req_2]),
            _FakeExecResult(scalars_values=[]),  # findings
        ]
    )

    result = release_readiness_service.get_release_readiness_for_work_order(
        db, organization_id=org_id, work_order_id=wo.id
    )

    assert result.status == "BLOCKED"
    assert len(result.blockers) == 2
    assert {b.category for b in result.blockers} == {"MATERIAL"}


def test_compliance_blocker_when_non_compliant():
    org_id = uuid.uuid4()
    asset_id = uuid.uuid4()
    wo = _work_order(org_id, asset_id=asset_id)
    assessment = _assessment(org_id, asset_id, status=ComplianceAssessmentStatus.NON_COMPLIANT)
    db = _FakeSession(
        [
            _FakeExecResult(scalar=wo),
            _FakeExecResult(scalars_values=[]),  # tasks
            _FakeExecResult(scalars_values=[]),  # inspections
            _FakeExecResult(scalars_values=[]),  # part requirements
            _FakeExecResult(scalars_values=[assessment]),
            _FakeExecResult(scalars_values=[]),  # findings
        ]
    )

    result = release_readiness_service.get_release_readiness_for_work_order(
        db, organization_id=org_id, work_order_id=wo.id
    )

    assert result.status == "BLOCKED"
    assert len(result.blockers) == 1
    assert result.blockers[0].category == "COMPLIANCE"
    assert result.blockers[0].related_record_id == assessment.id


def test_compliance_no_blocker_when_compliant():
    org_id = uuid.uuid4()
    asset_id = uuid.uuid4()
    wo = _work_order(org_id, asset_id=asset_id)
    assessment = _assessment(org_id, asset_id, status=ComplianceAssessmentStatus.COMPLIANT)
    db = _FakeSession(
        [
            _FakeExecResult(scalar=wo),
            _FakeExecResult(scalars_values=[]),
            _FakeExecResult(scalars_values=[]),
            _FakeExecResult(scalars_values=[]),
            _FakeExecResult(scalars_values=[assessment]),
            _FakeExecResult(scalars_values=[]),  # findings
        ]
    )

    result = release_readiness_service.get_release_readiness_for_work_order(
        db, organization_id=org_id, work_order_id=wo.id
    )

    assert result.status == "READY"
    assert result.blockers == []


def test_compliance_pending_assessment_does_not_block():
    org_id = uuid.uuid4()
    asset_id = uuid.uuid4()
    wo = _work_order(org_id, asset_id=asset_id)
    assessment = _assessment(org_id, asset_id, status=ComplianceAssessmentStatus.REVIEW_REQUIRED)
    db = _FakeSession(
        [
            _FakeExecResult(scalar=wo),
            _FakeExecResult(scalars_values=[]),
            _FakeExecResult(scalars_values=[]),
            _FakeExecResult(scalars_values=[]),
            _FakeExecResult(scalars_values=[assessment]),
            _FakeExecResult(scalars_values=[]),  # findings
        ]
    )

    result = release_readiness_service.get_release_readiness_for_work_order(
        db, organization_id=org_id, work_order_id=wo.id
    )

    assert result.status == "READY"
    assert result.blockers == []


def test_compliance_historical_non_compliant_does_not_override_current_compliant():
    org_id = uuid.uuid4()
    asset_id = uuid.uuid4()
    requirement_id = uuid.uuid4()
    wo = _work_order(org_id, asset_id=asset_id)
    old_non_compliant = _assessment(
        org_id,
        asset_id,
        requirement_id=requirement_id,
        status=ComplianceAssessmentStatus.NON_COMPLIANT,
        evaluated_at=datetime.date(2025, 1, 1),
        created_at=datetime.datetime(2025, 1, 1),
    )
    newer_compliant = _assessment(
        org_id,
        asset_id,
        requirement_id=requirement_id,
        status=ComplianceAssessmentStatus.COMPLIANT,
        evaluated_at=datetime.date(2026, 6, 1),
        created_at=datetime.datetime(2026, 6, 1),
    )
    db = _FakeSession(
        [
            _FakeExecResult(scalar=wo),
            _FakeExecResult(scalars_values=[]),
            _FakeExecResult(scalars_values=[]),
            _FakeExecResult(scalars_values=[]),
            _FakeExecResult(scalars_values=[old_non_compliant, newer_compliant]),
            _FakeExecResult(scalars_values=[]),  # findings
        ]
    )

    result = release_readiness_service.get_release_readiness_for_work_order(
        db, organization_id=org_id, work_order_id=wo.id
    )

    assert result.status == "READY"
    assert result.blockers == []


def test_compliance_not_evaluated_when_work_order_has_no_asset():
    org_id = uuid.uuid4()
    wo = _work_order(org_id)  # no asset_id
    db = _FakeSession(
        [
            _FakeExecResult(scalar=wo),
            _FakeExecResult(scalars_values=[]),
            _FakeExecResult(scalars_values=[]),
            _FakeExecResult(scalars_values=[]),
            # No fifth result: compliance query must not run without asset_id.
            _FakeExecResult(scalars_values=[]),  # findings
        ]
    )

    result = release_readiness_service.get_release_readiness_for_work_order(
        db, organization_id=org_id, work_order_id=wo.id
    )

    assert result.status == "READY"
    assert result.blockers == []


def test_multiple_blocker_categories_coexist_and_are_independent():
    org_id = uuid.uuid4()
    asset_id = uuid.uuid4()
    wo = _work_order(org_id, asset_id=asset_id)
    task = _task(org_id, wo.id, execution_state="PENDING")
    part_req = _part_requirement(org_id, wo.id, required_quantity=1, fulfilled_quantity=0)
    assessment = _assessment(org_id, asset_id, status=ComplianceAssessmentStatus.NON_COMPLIANT)
    db = _FakeSession(
        [
            _FakeExecResult(scalar=wo),
            _FakeExecResult(scalars_values=[task]),
            _FakeExecResult(scalars_values=[]),  # evidence
            _FakeExecResult(scalars_values=[]),  # inspections
            _FakeExecResult(scalars_values=[part_req]),
            _FakeExecResult(scalars_values=[assessment]),
            _FakeExecResult(scalars_values=[]),  # findings
        ]
    )

    result = release_readiness_service.get_release_readiness_for_work_order(
        db, organization_id=org_id, work_order_id=wo.id
    )

    assert result.status == "BLOCKED"
    categories = {b.category for b in result.blockers}
    assert categories == {"TASK_EXECUTION", "MATERIAL", "COMPLIANCE"}


def test_finding_blocker_when_unresolved_and_linked_via_work_order_id():
    org_id = uuid.uuid4()
    wo = _work_order(org_id)
    finding = _finding(org_id, work_order_id=wo.id, status=FindingStatus.OPEN)
    db = _FakeSession(
        [
            _FakeExecResult(scalar=wo),
            _FakeExecResult(scalars_values=[]),  # tasks
            _FakeExecResult(scalars_values=[]),  # inspections
            _FakeExecResult(scalars_values=[]),  # part requirements
            _FakeExecResult(scalars_values=[finding]),  # findings
        ]
    )

    result = release_readiness_service.get_release_readiness_for_work_order(
        db, organization_id=org_id, work_order_id=wo.id
    )

    assert result.status == "BLOCKED"
    assert len(result.blockers) == 1
    assert result.blockers[0].category == "FINDING"
    assert result.blockers[0].related_record_id == finding.id


def test_finding_blocker_when_linked_via_asset_id():
    org_id = uuid.uuid4()
    asset_id = uuid.uuid4()
    wo = _work_order(org_id, asset_id=asset_id)
    finding = _finding(org_id, asset_id=asset_id, status=FindingStatus.IN_PROGRESS)
    db = _FakeSession(
        [
            _FakeExecResult(scalar=wo),
            _FakeExecResult(scalars_values=[]),
            _FakeExecResult(scalars_values=[]),
            _FakeExecResult(scalars_values=[]),
            _FakeExecResult(scalars_values=[]),  # compliance (asset_id set)
            _FakeExecResult(scalars_values=[finding]),  # findings
        ]
    )

    result = release_readiness_service.get_release_readiness_for_work_order(
        db, organization_id=org_id, work_order_id=wo.id
    )

    assert result.status == "BLOCKED"
    assert len(result.blockers) == 1
    assert result.blockers[0].category == "FINDING"
    assert result.blockers[0].related_record_id == finding.id


def test_closed_finding_does_not_block():
    org_id = uuid.uuid4()
    wo = _work_order(org_id)
    db = _FakeSession(
        [
            _FakeExecResult(scalar=wo),
            _FakeExecResult(scalars_values=[]),
            _FakeExecResult(scalars_values=[]),
            _FakeExecResult(scalars_values=[]),
            # The service filters Finding.status != CLOSED in the query
            # itself, so a CLOSED finding never comes back here at all.
            _FakeExecResult(scalars_values=[]),  # findings
        ]
    )

    result = release_readiness_service.get_release_readiness_for_work_order(
        db, organization_id=org_id, work_order_id=wo.id
    )

    assert result.status == "READY"
    assert result.blockers == []


def test_multiple_unresolved_findings_each_produce_their_own_blocker():
    org_id = uuid.uuid4()
    wo = _work_order(org_id)
    finding_1 = _finding(org_id, work_order_id=wo.id, title="Finding A")
    finding_2 = _finding(org_id, work_order_id=wo.id, title="Finding B")
    db = _FakeSession(
        [
            _FakeExecResult(scalar=wo),
            _FakeExecResult(scalars_values=[]),
            _FakeExecResult(scalars_values=[]),
            _FakeExecResult(scalars_values=[]),
            _FakeExecResult(scalars_values=[finding_1, finding_2]),
        ]
    )

    result = release_readiness_service.get_release_readiness_for_work_order(
        db, organization_id=org_id, work_order_id=wo.id
    )

    assert result.status == "BLOCKED"
    assert len(result.blockers) == 2
    assert {b.related_record_id for b in result.blockers} == {finding_1.id, finding_2.id}
    assert {b.category for b in result.blockers} == {"FINDING"}


def test_finding_lifecycle_transition_reflected_in_fresh_call():
    org_id = uuid.uuid4()
    wo = _work_order(org_id)
    finding = _finding(org_id, work_order_id=wo.id, status=FindingStatus.OPEN)

    db_open = _FakeSession(
        [
            _FakeExecResult(scalar=wo),
            _FakeExecResult(scalars_values=[]),
            _FakeExecResult(scalars_values=[]),
            _FakeExecResult(scalars_values=[]),
            _FakeExecResult(scalars_values=[finding]),
        ]
    )
    result_open = release_readiness_service.get_release_readiness_for_work_order(
        db_open, organization_id=org_id, work_order_id=wo.id
    )
    assert result_open.status == "BLOCKED"

    # Finding closed -- the query itself excludes CLOSED, so a fresh call
    # simply gets nothing back for it.
    db_closed = _FakeSession(
        [
            _FakeExecResult(scalar=wo),
            _FakeExecResult(scalars_values=[]),
            _FakeExecResult(scalars_values=[]),
            _FakeExecResult(scalars_values=[]),
            _FakeExecResult(scalars_values=[]),
        ]
    )
    result_closed = release_readiness_service.get_release_readiness_for_work_order(
        db_closed, organization_id=org_id, work_order_id=wo.id
    )
    assert result_closed.status == "READY"
    assert result_closed.blockers == []
