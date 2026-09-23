import uuid

import pytest
from pydantic import ValidationError

from app.schemas.work_order import WorkOrderCreateRequest


def test_work_order_accepts_aircraft_only():
    payload = WorkOrderCreateRequest(
        aircraft_id=uuid.uuid4(),
        work_order_number="WO-AIRCRAFT-1",
    )
    assert payload.asset_id is None


def test_work_order_accepts_asset_only():
    payload = WorkOrderCreateRequest(
        asset_id=uuid.uuid4(),
        work_order_number="WO-ASSET-1",
    )
    assert payload.aircraft_id is None


@pytest.mark.parametrize(
    "payload",
    [
        {"work_order_number": "WO-MISSING-1"},
        {
            "aircraft_id": uuid.uuid4(),
            "asset_id": uuid.uuid4(),
            "work_order_number": "WO-BOTH-1",
        },
    ],
)
def test_work_order_requires_exactly_one_primary_asset(payload):
    with pytest.raises(ValidationError, match="Exactly one"):
        WorkOrderCreateRequest(**payload)
