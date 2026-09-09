import uuid

import pytest

from app.core.errors import NotFoundError
from app.models.evidence import Evidence, EvidenceStatus
from app.models.inspection_requirement import InspectionRequirement, InspectionRequirementStatus
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
    )
    defaults.update(overrides)
    task = Task()
    for key, value in defaults.items():
        setattr(task, key, value)
    return task


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
        ]
    )

    result = release_readiness_service.get_release_readiness_for_work_order(
        db, organization_id=org_id, work_order_id=wo.id
    )

    assert result.status == "READY"
    assert result.blockers == []
