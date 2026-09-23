"""General Finding/Disposition lifecycle: OPEN -> IN_PROGRESS -> CLOSED.

Mirrors inspection_service.py's shape (tenant-scoped fetch-or-404,
server-derived organization_id, audit event per mutation) applied to the
new general-purpose Finding model (app/models/finding.py) rather than the
compliance-assessment-scoped AssessmentFinding.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError
from app.models.aircraft import Aircraft
from app.models.asset import Asset
from app.models.component import Component
from app.models.evidence import Evidence
from app.models.finding import (
    ALL_DISPOSITION_TYPES,
    ALL_FINDING_SEVERITIES,
    DispositionType,
    Finding,
    FindingDisposition,
    FindingStatus,
)
from app.models.user import User
from app.models.inspection_requirement import InspectionRequirement
from app.models.task import Task
from app.models.work_order import WorkOrder
from app.services.audit_service import record_audit_event


def _assert_user_in_organization(db: Session, *, organization_id: uuid.UUID, user_id: uuid.UUID) -> None:
    exists = db.execute(
        select(User.id).where(User.id == user_id, User.organization_id == organization_id)
    ).scalar_one_or_none()
    if exists is None:
        raise ConflictError("Referenced user_id does not belong to this organization")


def _assert_work_order_in_organization(
    db: Session, *, organization_id: uuid.UUID, work_order_id: uuid.UUID
) -> None:
    exists = db.execute(
        select(WorkOrder.id).where(
            WorkOrder.id == work_order_id, WorkOrder.organization_id == organization_id
        )
    ).scalar_one_or_none()
    if exists is None:
        raise NotFoundError("Work order not found")


def _assert_reference_in_organization(
    db: Session, *, organization_id: uuid.UUID, model: type, resource_id: uuid.UUID, label: str
) -> None:
    exists = db.execute(
        select(model.id).where(
            model.id == resource_id, model.organization_id == organization_id
        )
    ).scalar_one_or_none()
    if exists is None:
        raise NotFoundError(f"{label} not found")


def create_finding(
    db: Session,
    *,
    organization_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    title: str,
    description: str,
    severity: str,
    aircraft_id: uuid.UUID | None = None,
    asset_id: uuid.UUID | None = None,
    component_id: uuid.UUID | None = None,
    inspection_requirement_id: uuid.UUID | None = None,
    work_order_id: uuid.UUID | None = None,
    task_id: uuid.UUID | None = None,
    responsible_user_id: uuid.UUID | None = None,
) -> Finding:
    if severity not in ALL_FINDING_SEVERITIES:
        raise ConflictError(f"Invalid severity: {severity}")
    references = (
        (Aircraft, aircraft_id, "Aircraft"),
        (Asset, asset_id, "Asset"),
        (Component, component_id, "Component"),
        (InspectionRequirement, inspection_requirement_id, "Inspection requirement"),
        (Task, task_id, "Task"),
    )
    for model, resource_id, label in references:
        if resource_id is not None:
            _assert_reference_in_organization(
                db,
                organization_id=organization_id,
                model=model,
                resource_id=resource_id,
                label=label,
            )
    if work_order_id is not None:
        _assert_work_order_in_organization(db, organization_id=organization_id, work_order_id=work_order_id)
    if responsible_user_id is not None:
        _assert_user_in_organization(
            db, organization_id=organization_id, user_id=responsible_user_id
        )

    finding = Finding(
        organization_id=organization_id,
        aircraft_id=aircraft_id,
        asset_id=asset_id,
        component_id=component_id,
        inspection_requirement_id=inspection_requirement_id,
        work_order_id=work_order_id,
        task_id=task_id,
        title=title,
        description=description,
        severity=severity,
        status=FindingStatus.OPEN,
        discovered_by_user_id=actor_user_id,
        responsible_user_id=responsible_user_id,
    )
    db.add(finding)
    db.flush()
    record_audit_event(
        db,
        organization_id=organization_id,
        user_id=actor_user_id,
        action="finding.created",
        entity_type="Finding",
        entity_id=finding.id,
        metadata={"severity": severity, "title": title},
    )
    db.commit()
    db.refresh(finding)
    return finding


def get_finding(db: Session, *, organization_id: uuid.UUID, finding_id: uuid.UUID) -> Finding:
    finding = db.execute(
        select(Finding).where(Finding.id == finding_id, Finding.organization_id == organization_id)
    ).scalar_one_or_none()
    if finding is None:
        raise NotFoundError("Finding not found")
    return finding


def list_findings(
    db: Session,
    *,
    organization_id: uuid.UUID,
    aircraft_id: uuid.UUID | None = None,
    asset_id: uuid.UUID | None = None,
    work_order_id: uuid.UUID | None = None,
    status: str | None = None,
) -> list[Finding]:
    stmt = select(Finding).where(Finding.organization_id == organization_id)
    if aircraft_id is not None:
        stmt = stmt.where(Finding.aircraft_id == aircraft_id)
    if asset_id is not None:
        stmt = stmt.where(Finding.asset_id == asset_id)
    if work_order_id is not None:
        stmt = stmt.where(Finding.work_order_id == work_order_id)
    if status is not None:
        stmt = stmt.where(Finding.status == status)
    stmt = stmt.order_by(Finding.discovered_at.desc())
    return list(db.execute(stmt).scalars().all())


def add_disposition(
    db: Session,
    finding: Finding,
    *,
    actor_user_id: uuid.UUID | None,
    disposition_type: str,
    corrective_action: str | None,
    evidence_id: uuid.UUID | None,
) -> Finding:
    """Record a disposition on a finding. NO_ACTION_REQUIRED and
    CORRECTIVE_ACTION (when accompanied by evidence closing the loop) move
    the finding straight to IN_PROGRESS -- explicit closure is a separate
    call (close_finding), matching InspectionRequirement's own
    transition-then-separately-terminal shape, so a disposition can be
    recorded without prematurely closing the finding.
    """
    if finding.status == FindingStatus.CLOSED:
        raise ConflictError("Cannot add a disposition to a closed finding")
    if disposition_type not in ALL_DISPOSITION_TYPES:
        raise ConflictError(f"Invalid disposition_type: {disposition_type}")
    if disposition_type == DispositionType.CORRECTIVE_ACTION and not corrective_action:
        raise ConflictError("corrective_action is required for a CORRECTIVE_ACTION disposition")
    if evidence_id is not None:
        _assert_reference_in_organization(
            db,
            organization_id=finding.organization_id,
            model=Evidence,
            resource_id=evidence_id,
            label="Evidence",
        )

    disposition = FindingDisposition(
        organization_id=finding.organization_id,
        finding_id=finding.id,
        disposition_type=disposition_type,
        corrective_action=corrective_action,
        evidence_id=evidence_id,
    )
    db.add(disposition)
    # Explicit append (not relying solely on the FK assignment above) so the
    # in-memory finding.dispositions list is immediately consistent for the
    # remainder of this call and for callers like close_finding that read
    # finding.dispositions[-1] before any re-fetch from the DB.
    finding.dispositions.append(disposition)

    if finding.status == FindingStatus.OPEN:
        finding.status = FindingStatus.IN_PROGRESS

    record_audit_event(
        db,
        organization_id=finding.organization_id,
        user_id=actor_user_id,
        action="finding.disposition_added",
        entity_type="Finding",
        entity_id=finding.id,
        metadata={"disposition_type": disposition_type},
    )
    db.add(finding)
    db.commit()
    db.refresh(finding)
    return finding


def close_finding(
    db: Session,
    finding: Finding,
    *,
    actor_user_id: uuid.UUID | None,
) -> Finding:
    if finding.status == FindingStatus.CLOSED:
        raise ConflictError("Finding is already closed")
    if not finding.dispositions:
        raise ConflictError("A finding must have at least one disposition before it can be closed")

    latest = finding.dispositions[-1]
    latest.closed_at = datetime.now(timezone.utc)
    latest.closed_by_user_id = actor_user_id
    finding.status = FindingStatus.CLOSED

    record_audit_event(
        db,
        organization_id=finding.organization_id,
        user_id=actor_user_id,
        action="finding.closed",
        entity_type="Finding",
        entity_id=finding.id,
        metadata={"disposition_type": latest.disposition_type},
    )
    db.add(finding)
    db.add(latest)
    db.commit()
    db.refresh(finding)
    return finding
