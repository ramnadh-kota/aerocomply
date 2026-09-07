import uuid

import pytest

from app.core.errors import ConflictError
from app.models.inspection_requirement import InspectionRequirement, InspectionRequirementStatus
from app.services.inspection_service import (
    _assert_independent_inspector,
    _executing_technician_ids,
    can_transition,
    satisfies_completion_gate,
)

S = InspectionRequirementStatus


def _requirement(**overrides) -> InspectionRequirement:
    defaults = dict(
        id=uuid.uuid4(),
        organization_id=uuid.uuid4(),
        task_id=uuid.uuid4(),
        work_order_id=None,
        required=True,
        inspector_user_id=None,
        status=S.PENDING.value,
        rejection_reason=None,
    )
    defaults.update(overrides)
    req = InspectionRequirement()
    for key, value in defaults.items():
        setattr(req, key, value)
    return req


def test_pending_can_move_to_completed_not_required_or_rejected():
    assert can_transition(S.PENDING, S.COMPLETED)
    assert can_transition(S.PENDING, S.NOT_REQUIRED)
    assert can_transition(S.PENDING, S.REJECTED)


def test_completed_and_not_required_are_terminal():
    for status in S:
        assert not can_transition(S.COMPLETED, status)
        assert not can_transition(S.NOT_REQUIRED, status)


def test_rejected_can_only_return_to_pending():
    assert can_transition(S.REJECTED, S.PENDING)
    assert not can_transition(S.REJECTED, S.COMPLETED)
    assert not can_transition(S.REJECTED, S.NOT_REQUIRED)


def test_cannot_skip_or_self_transition():
    assert not can_transition(S.PENDING, S.PENDING)
    for status in S:
        assert not can_transition(status, status)


def test_only_completed_or_not_required_satisfy_completion_gate():
    assert satisfies_completion_gate(S.COMPLETED) is True
    assert satisfies_completion_gate(S.NOT_REQUIRED) is True
    assert satisfies_completion_gate(S.PENDING) is False
    assert satisfies_completion_gate(S.REJECTED) is False
    assert satisfies_completion_gate("COMPLETED") is True
    assert satisfies_completion_gate("PENDING") is False


class _FakeScalarsResult:
    def __init__(self, values):
        self._values = values

    def all(self):
        return self._values


class _FakeExecResult:
    def __init__(self, values):
        self._values = values

    def scalars(self):
        return _FakeScalarsResult(self._values)


class _FakeSession:
    """Minimal stand-in for a Session that only needs to answer the
    executing-technician lookup query with a canned set of uploader ids.
    """

    def __init__(self, uploader_ids):
        self._uploader_ids = uploader_ids

    def execute(self, _stmt):
        return _FakeExecResult(self._uploader_ids)


def test_executing_technician_ids_empty_when_no_task():
    req = _requirement(task_id=None)
    db = _FakeSession([])
    assert _executing_technician_ids(db, req) == set()


def test_executing_technician_ids_returns_evidence_uploaders():
    req = _requirement()
    tech_id = uuid.uuid4()
    db = _FakeSession([tech_id])
    assert _executing_technician_ids(db, req) == {tech_id}


def test_rii_independence_rejects_same_person_as_executor():
    req = _requirement(required=True)
    tech_id = uuid.uuid4()
    db = _FakeSession([tech_id])
    with pytest.raises(ConflictError):
        _assert_independent_inspector(db, req, tech_id)


def test_rii_independence_allows_a_different_inspector():
    req = _requirement(required=True)
    tech_id = uuid.uuid4()
    inspector_id = uuid.uuid4()
    db = _FakeSession([tech_id])
    # Should not raise.
    _assert_independent_inspector(db, req, inspector_id)


def test_rii_independence_requires_an_inspector():
    req = _requirement(required=True)
    db = _FakeSession([])
    with pytest.raises(ConflictError):
        _assert_independent_inspector(db, req, None)


def test_checklist_review_has_no_independence_constraint():
    """required=False is a plain checklist review, not RII — no inspector
    identity constraint applies."""
    req = _requirement(required=False)
    db = _FakeSession([])
    # Should not raise even with no inspector at all.
    _assert_independent_inspector(db, req, None)


def test_rii_skips_check_when_no_evidence_exists_yet():
    """Cannot fabricate an executor when there is no evidence yet — the
    independence check is skipped (not a false pass, just nothing to
    compare against), and any named inspector is accepted."""
    req = _requirement(required=True)
    db = _FakeSession([])
    inspector_id = uuid.uuid4()
    _assert_independent_inspector(db, req, inspector_id)
