"""Turnaround-time (TAT) status for a work order and across the fleet.

Scope decision: neither WorkOrder nor Task currently has a due_date (or any
other schedule) column (see app/models/work_order.py, app/models/task.py).
Rather than add a schema migration to backfill a due date that does not exist
anywhere in the system today, this service always reports status='UNKNOWN'
with an explicit reason. This is a deliberate, minimal-risk choice: fabricating
a due date (or a predicted duration) would violate the "never predict" rule
this codebase follows elsewhere (see app/services/evidence_service.py and
app/services/inspection_service.py docstrings) even more directly than a
missing status would. When a due_date column is added to WorkOrder in a
future milestone, the thresholds below (AT_RISK = due within 3 days,
DELAYED = due date has passed, ON_TRACK = otherwise) are ready to be wired in
without changing this module's public shape.
"""
import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.models.work_order import WorkOrder
from app.schemas.tat import FleetTatSummary, TatStatus

_NO_DUE_DATE_REASON = (
    "No due date is recorded for this work order yet. WorkOrder has no "
    "due_date field in the current schema, so TAT status cannot be computed "
    "from real data — it is reported as UNKNOWN rather than fabricated."
)

_FLEET_REASON = (
    "No work order carries a due date in the current schema, so every work "
    "order is reported as UNKNOWN rather than fabricating a TAT status."
)


def get_work_order_tat_status(
    db: Session, *, organization_id: uuid.UUID, work_order_id: uuid.UUID
) -> TatStatus:
    work_order = db.execute(
        select(WorkOrder).where(
            WorkOrder.id == work_order_id, WorkOrder.organization_id == organization_id
        )
    ).scalar_one_or_none()
    if work_order is None:
        raise NotFoundError("Work order not found")

    # WorkOrder has no due_date column today (see module docstring) — always
    # UNKNOWN. This is a pure, deterministic statement about missing data,
    # never a predicted or estimated due date.
    return TatStatus(
        work_order_id=work_order.id,
        status="UNKNOWN",
        due_date=None,
        days_remaining=None,
        days_overdue=None,
        reason=_NO_DUE_DATE_REASON,
    )


def get_fleet_tat_status(db: Session, *, organization_id: uuid.UUID) -> FleetTatSummary:
    total = db.execute(
        select(func.count())
        .select_from(WorkOrder)
        .where(WorkOrder.organization_id == organization_id)
    ).scalar_one()

    # Every work order is UNKNOWN today for the same reason as the per-work-order
    # case above: there is no due_date to compare against.
    return FleetTatSummary(
        organization_id=organization_id,
        on_track_count=0,
        at_risk_count=0,
        delayed_count=0,
        unknown_count=total,
        total_work_orders=total,
        reason=_FLEET_REASON,
    )
