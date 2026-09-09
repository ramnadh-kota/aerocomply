import uuid

import pytest

from app.core.errors import NotFoundError
from app.models.work_order import WorkOrder
from app.services import tat_service


class _FakeScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value

    def scalar_one(self):
        return self._value


class _FakeSession:
    """Minimal Session stand-in returning canned results in call order,
    mirroring the FakeSession pattern in test_inspection_lifecycle.py."""

    def __init__(self, results):
        self._results = list(results)

    def execute(self, _stmt):
        return self._results.pop(0)


def _work_order(**overrides) -> WorkOrder:
    defaults = dict(
        id=uuid.uuid4(),
        organization_id=uuid.uuid4(),
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


def test_work_order_tat_status_is_unknown_when_no_due_date_field_exists():
    org_id = uuid.uuid4()
    wo = _work_order(organization_id=org_id)
    db = _FakeSession([_FakeScalarResult(wo)])

    result = tat_service.get_work_order_tat_status(
        db, organization_id=org_id, work_order_id=wo.id
    )

    assert result.status == "UNKNOWN"
    assert result.due_date is None
    assert result.days_remaining is None
    assert result.days_overdue is None
    assert result.reason


def test_work_order_tat_status_raises_not_found():
    org_id = uuid.uuid4()
    db = _FakeSession([_FakeScalarResult(None)])

    with pytest.raises(NotFoundError):
        tat_service.get_work_order_tat_status(
            db, organization_id=org_id, work_order_id=uuid.uuid4()
        )


def test_fleet_tat_status_reports_all_unknown():
    org_id = uuid.uuid4()
    db = _FakeSession([_FakeScalarResult(5)])

    result = tat_service.get_fleet_tat_status(db, organization_id=org_id)

    assert result.total_work_orders == 5
    assert result.unknown_count == 5
    assert result.on_track_count == 0
    assert result.at_risk_count == 0
    assert result.delayed_count == 0


def test_fleet_tat_status_with_zero_work_orders():
    org_id = uuid.uuid4()
    db = _FakeSession([_FakeScalarResult(0)])

    result = tat_service.get_fleet_tat_status(db, organization_id=org_id)

    assert result.total_work_orders == 0
    assert result.unknown_count == 0
