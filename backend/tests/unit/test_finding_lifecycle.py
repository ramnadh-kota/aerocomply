import uuid

import pytest

from app.core.errors import ConflictError
from app.models.finding import Finding, FindingDisposition, FindingStatus
from app.services.finding_service import add_disposition, close_finding


def _finding(**overrides) -> Finding:
    defaults = dict(
        id=uuid.uuid4(),
        organization_id=uuid.uuid4(),
        title="Cracked bracket",
        description="Hairline crack observed on bracket",
        severity="MAJOR",
        status=FindingStatus.OPEN,
    )
    defaults.update(overrides)
    f = Finding()
    for key, value in defaults.items():
        setattr(f, key, value)
    f.dispositions = []
    return f


class _FakeSession:
    def add(self, _obj):
        pass

    def commit(self):
        pass

    def refresh(self, _obj):
        pass


def test_add_disposition_moves_open_to_in_progress():
    f = _finding()
    db = _FakeSession()
    result = add_disposition(
        db,
        f,
        actor_user_id=uuid.uuid4(),
        disposition_type="CORRECTIVE_ACTION",
        corrective_action="Replaced bracket",
        evidence_id=None,
    )
    assert result.status == FindingStatus.IN_PROGRESS
    assert len(result.dispositions) == 1


def test_corrective_action_requires_description():
    f = _finding()
    db = _FakeSession()
    with pytest.raises(ConflictError):
        add_disposition(
            db,
            f,
            actor_user_id=uuid.uuid4(),
            disposition_type="CORRECTIVE_ACTION",
            corrective_action=None,
            evidence_id=None,
        )


def test_cannot_disposition_a_closed_finding():
    f = _finding(status=FindingStatus.CLOSED)
    db = _FakeSession()
    with pytest.raises(ConflictError):
        add_disposition(
            db,
            f,
            actor_user_id=uuid.uuid4(),
            disposition_type="NO_ACTION_REQUIRED",
            corrective_action=None,
            evidence_id=None,
        )


def test_invalid_disposition_type_rejected():
    f = _finding()
    db = _FakeSession()
    with pytest.raises(ConflictError):
        add_disposition(
            db,
            f,
            actor_user_id=uuid.uuid4(),
            disposition_type="NOT_A_REAL_TYPE",
            corrective_action=None,
            evidence_id=None,
        )


def test_close_requires_a_disposition_first():
    f = _finding()
    db = _FakeSession()
    with pytest.raises(ConflictError):
        close_finding(db, f, actor_user_id=uuid.uuid4())


def test_close_sets_status_and_closure_metadata_on_latest_disposition():
    f = _finding()
    db = _FakeSession()
    f = add_disposition(
        db,
        f,
        actor_user_id=uuid.uuid4(),
        disposition_type="NO_ACTION_REQUIRED",
        corrective_action=None,
        evidence_id=None,
    )
    closer_id = uuid.uuid4()
    f = close_finding(db, f, actor_user_id=closer_id)
    assert f.status == FindingStatus.CLOSED
    assert f.dispositions[-1].closed_by_user_id == closer_id
    assert f.dispositions[-1].closed_at is not None


def test_cannot_close_an_already_closed_finding():
    f = _finding()
    db = _FakeSession()
    f = add_disposition(
        db,
        f,
        actor_user_id=uuid.uuid4(),
        disposition_type="NO_ACTION_REQUIRED",
        corrective_action=None,
        evidence_id=None,
    )
    f = close_finding(db, f, actor_user_id=uuid.uuid4())
    with pytest.raises(ConflictError):
        close_finding(db, f, actor_user_id=uuid.uuid4())
