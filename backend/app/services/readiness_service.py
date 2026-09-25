"""Phase 18.6: deterministic Deployment Readiness evaluation.

Pure backend domain logic -- never AI-derived (a future Lisa tool like
get_drone_deployment_readiness may CALL this, but must never compute
readiness itself). Reuses existing signals rather than building a second
maintenance/inspection engine:
  - Asset.status (existing lifecycle field)
  - Battery.status / presence (Phase 18.6)
  - maintenance_service.has_overdue_maintenance_for_asset (reuses the
    existing due-status calculation, asset_id-filtered)
  - InspectionRequirement.status via its existing work_order_id -> WorkOrder
    .asset_id path (Phase 1B) -- no new inspection-to-asset relationship
    was added; this is the one that already exists.

Deliberately deferred (documented, not attempted): a standing "assigned
pilot" attribute (no reasonable place to store this yet -- flight creation
already accepts pilot_user_id per-flight, which is the actual pilot
concept this milestone introduces) and an "open work order" blocker (the
repository has no single canonical "is this work order open" status
vocabulary confirmed across the codebase; adding a guessed one risks a
wrong blocker being reported, which is worse than omitting it here).
"""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.battery import Battery, BatteryStatus
from app.models.finding import Finding, FindingStatus
from app.models.inspection_requirement import InspectionRequirement, InspectionRequirementStatus
from app.models.work_order import WorkOrder
from app.services import drone_service, maintenance_service


def evaluate_deployment_readiness(
    db: Session, *, organization_id: uuid.UUID, asset_id: uuid.UUID
) -> dict:
    drone = drone_service.get_drone(db, organization_id=organization_id, asset_id=asset_id)
    blockers: list[str] = []

    if drone.status != "ACTIVE":
        blockers.append(f"Drone is not active (status: {drone.status})")

    battery = (
        db.execute(
            select(Battery)
            .where(Battery.organization_id == organization_id, Battery.asset_id == asset_id)
            .order_by(Battery.created_at.desc())
        )
        .scalars()
        .first()
    )
    if battery is None:
        blockers.append("No battery assigned")
    elif battery.status == BatteryStatus.CRITICAL:
        blockers.append("Battery critical")

    if maintenance_service.has_overdue_maintenance_for_asset(
        db, organization_id=organization_id, asset_id=asset_id
    ):
        blockers.append("Maintenance overdue")

    failed_inspection = db.execute(
        select(InspectionRequirement.id)
        .join(WorkOrder, WorkOrder.id == InspectionRequirement.work_order_id)
        .where(
            WorkOrder.organization_id == organization_id,
            WorkOrder.asset_id == asset_id,
            WorkOrder.deleted_at.is_(None),
            InspectionRequirement.status == InspectionRequirementStatus.REJECTED.value,
        )
        .limit(1)
    ).scalar_one_or_none()
    if failed_inspection is not None:
        blockers.append("Failed inspection")

    # M21.1: unresolved Findings (status OPEN or IN_PROGRESS, i.e. not
    # CLOSED) linked to this asset via Finding.asset_id -- reuses the
    # existing Finding model/status vocabulary (app/models/finding.py)
    # exactly as-is, no new severity scoring. Single query, one blocker per
    # unresolved finding (never collapsed). Severity is surfaced for
    # explainability only; it is never used to decide whether a finding
    # blocks.
    unresolved_findings = list(
        db.execute(
            select(Finding).where(
                Finding.organization_id == organization_id,
                Finding.asset_id == asset_id,
                Finding.status != FindingStatus.CLOSED,
            )
        ).scalars().all()
    )
    finding_blockers = [
        {
            "finding_id": finding.id,
            "title": finding.title,
            "severity": finding.severity,
            "status": finding.status,
        }
        for finding in unresolved_findings
    ]
    for finding in unresolved_findings:
        blockers.append(f"Unresolved finding ({finding.severity}): {finding.title}")

    return {
        "asset_id": asset_id,
        "status": "BLOCKED" if blockers else "READY",
        "blockers": blockers,
        "finding_blockers": finding_blockers,
    }
