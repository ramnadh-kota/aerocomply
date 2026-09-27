"""Unit tests for the Work Order Lifecycle state machine, validation rules,
and Turnaround Time (TAT) calculations.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.models.work_order import WorkOrder, WorkOrderStatus
from app.services import tat_service
from app.services.work_order_service import _ALLOWED_TRANSITIONS


def test_allowed_transitions_graph():
    """Verify that every defined state transition adheres to the authorized lifecycle."""
    assert _ALLOWED_TRANSITIONS[WorkOrderStatus.DRAFT] == {
        WorkOrderStatus.OPEN,
        WorkOrderStatus.CANCELLED,
    }
    assert _ALLOWED_TRANSITIONS[WorkOrderStatus.OPEN] == {
        WorkOrderStatus.PLANNED,
        WorkOrderStatus.ASSIGNED,
        WorkOrderStatus.CANCELLED,
    }
    assert _ALLOWED_TRANSITIONS[WorkOrderStatus.PLANNED] == {
        WorkOrderStatus.ASSIGNED,
        WorkOrderStatus.CANCELLED,
    }
    assert _ALLOWED_TRANSITIONS[WorkOrderStatus.ASSIGNED] == {
        WorkOrderStatus.IN_PROGRESS,
        WorkOrderStatus.PLANNED,
        WorkOrderStatus.CANCELLED,
    }
    assert _ALLOWED_TRANSITIONS[WorkOrderStatus.IN_PROGRESS] == {
        WorkOrderStatus.ON_HOLD,
        WorkOrderStatus.INSPECTION,
        WorkOrderStatus.CANCELLED,
    }
    assert _ALLOWED_TRANSITIONS[WorkOrderStatus.ON_HOLD] == {
        WorkOrderStatus.IN_PROGRESS,
        WorkOrderStatus.CANCELLED,
    }
    assert _ALLOWED_TRANSITIONS[WorkOrderStatus.INSPECTION] == {
        WorkOrderStatus.IN_PROGRESS,
        WorkOrderStatus.COMPLETED,
        WorkOrderStatus.CANCELLED,
    }
    assert _ALLOWED_TRANSITIONS[WorkOrderStatus.COMPLETED] == {
        WorkOrderStatus.CLOSED,
    }
    # CLOSED and CANCELLED are terminal states
    assert _ALLOWED_TRANSITIONS[WorkOrderStatus.CLOSED] == set()
    assert _ALLOWED_TRANSITIONS[WorkOrderStatus.CANCELLED] == set()


def test_invalid_transitions():
    """Ensure arbitrary or skipping status jumps are rejected."""
    # Cannot jump DRAFT -> IN_PROGRESS
    assert WorkOrderStatus.IN_PROGRESS not in _ALLOWED_TRANSITIONS[WorkOrderStatus.DRAFT]
    # Cannot jump DRAFT -> CLOSED
    assert WorkOrderStatus.CLOSED not in _ALLOWED_TRANSITIONS[WorkOrderStatus.DRAFT]
    # Cannot jump OPEN -> COMPLETED
    assert WorkOrderStatus.COMPLETED not in _ALLOWED_TRANSITIONS[WorkOrderStatus.OPEN]
    # Cannot transition out of CLOSED
    assert len(_ALLOWED_TRANSITIONS[WorkOrderStatus.CLOSED]) == 0
    # Cannot transition out of CANCELLED
    assert len(_ALLOWED_TRANSITIONS[WorkOrderStatus.CANCELLED]) == 0


def test_tat_status_due_date_calculations():
    """Verify TAT calculations on mock work orders."""
    now = datetime(2026, 3, 15, 12, 0, 0, tzinfo=UTC)

    # 1. No due date -> UNKNOWN
    wo_no_due = WorkOrder(
        id=uuid.uuid4(),
        organization_id=uuid.uuid4(),
        work_order_number="WO-TAT-1",
        status=WorkOrderStatus.IN_PROGRESS,
        due_at=None,
    )
    tat_no_due = tat_service.calculate_tat_for_work_order(wo_no_due, now=now)
    assert tat_no_due.status == "UNKNOWN"
    assert tat_no_due.due_date is None
    assert tat_no_due.days_remaining is None

    # 2. Due date in the past -> DELAYED
    wo_past = WorkOrder(
        id=uuid.uuid4(),
        organization_id=uuid.uuid4(),
        work_order_number="WO-TAT-2",
        status=WorkOrderStatus.IN_PROGRESS,
        due_at=now - timedelta(days=2),
    )
    tat_past = tat_service.calculate_tat_for_work_order(wo_past, now=now)
    assert tat_past.status == "DELAYED"
    assert tat_past.days_overdue is not None
    assert tat_past.days_overdue >= 1

    # 3. Due date within 3 days -> AT_RISK
    wo_soon = WorkOrder(
        id=uuid.uuid4(),
        organization_id=uuid.uuid4(),
        work_order_number="WO-TAT-3",
        status=WorkOrderStatus.IN_PROGRESS,
        due_at=now + timedelta(days=2),
    )
    tat_soon = tat_service.calculate_tat_for_work_order(wo_soon, now=now)
    assert tat_soon.status == "AT_RISK"
    assert tat_soon.days_remaining is not None

    # 4. Due date > 3 days -> ON_TRACK
    wo_future = WorkOrder(
        id=uuid.uuid4(),
        organization_id=uuid.uuid4(),
        work_order_number="WO-TAT-4",
        status=WorkOrderStatus.IN_PROGRESS,
        due_at=now + timedelta(days=7),
    )
    tat_future = tat_service.calculate_tat_for_work_order(wo_future, now=now)
    assert tat_future.status == "ON_TRACK"
    assert tat_future.days_remaining == 7

    # 5. Completed work order -> ON_TRACK
    wo_completed = WorkOrder(
        id=uuid.uuid4(),
        organization_id=uuid.uuid4(),
        work_order_number="WO-TAT-5",
        status=WorkOrderStatus.COMPLETED,
        due_at=now - timedelta(days=1),
        completed_at=now - timedelta(days=2),
    )
    tat_completed = tat_service.calculate_tat_for_work_order(wo_completed, now=now)
    assert tat_completed.status == "ON_TRACK"
