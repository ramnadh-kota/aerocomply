"""D2.2 Readiness Intelligence.

Consumes -- never re-derives -- the D2.1/D2.3 Aerospace Intelligence State
contract (app/services/aerospace_state_service.py::
evaluate_aerospace_intelligence_state), which already synthesizes
operational, compliance, evidence, inspection, and finding dimensions for an
asset. That module's own docstring is explicit that it is "the ONLY function
that Developer 2.2 should call to obtain intelligence state" and that
Developer 2.2 "must NOT query intelligence tables directly" -- this module
honors that boundary.

On top of that state, this module adds the two readiness signals the
Aerospace Intelligence State contract deliberately does not cover (per-asset
readiness, not per-obligation compliance):
  - WORK_ORDER: app/services/release_readiness_service.py::
    get_release_readiness_for_work_order, for every open work order touching
    this asset (Developer 1's release gate).
  - DEPLOYMENT: app/services/readiness_service.py::
    evaluate_deployment_readiness, for drone assets only (Developer 1's
    drone deployment gate).

readiness_state derivation (deterministic):
  1. aerospace_intelligence_status in (RESTRICTED, GROUNDED_INTEL), or any
     WORK_ORDER/DEPLOYMENT blocker present -> "BLOCKED".
  2. Otherwise, aerospace_intelligence_status == UNKNOWN_INTEL -> "UNKNOWN"
     (never silently resolved to READY -- mirrors Invariant #23).
  3. Otherwise (NOMINAL or DEGRADED, no extra blockers) -> "READY".
"""

import datetime
import uuid

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.models.asset import AssetType
from app.models.work_order import WorkOrder, WorkOrderStatus
from app.schemas.aerospace_state import AerospaceIntelligenceStatus
from app.schemas.intelligence import (
    AssetReadinessIntelligence,
    ReadinessIntelligenceBlocker,
    ReadinessState,
)
from app.services import asset_service, readiness_service, release_readiness_service
from app.services.aerospace_state_service import evaluate_aerospace_intelligence_state

_TERMINAL_WORK_ORDER_STATUSES = {
    WorkOrderStatus.COMPLETED,
    WorkOrderStatus.CLOSED,
    WorkOrderStatus.CANCELLED,
}

_BLOCKING_AEROSPACE_STATUSES = {
    AerospaceIntelligenceStatus.RESTRICTED,
    AerospaceIntelligenceStatus.GROUNDED_INTEL,
}

_DATA_COMPLETENESS = (
    "Synthesized from the Aerospace Intelligence State contract (operational, "
    "compliance, evidence, inspection, finding dimensions), per-work-order "
    "release readiness (Developer 1), and drone deployment readiness "
    "(Developer 1, drone assets only). Authorization sign-off is not yet "
    "backend-tracked (see release_readiness_service._DATA_COMPLETENESS)."
)


def get_asset_readiness_intelligence(
    db: Session, *, organization_id: uuid.UUID, asset_id: uuid.UUID
) -> AssetReadinessIntelligence:
    asset = asset_service.get_asset(db, organization_id=organization_id, asset_id=asset_id)
    state = evaluate_aerospace_intelligence_state(
        db, organization_id=organization_id, asset_id=asset_id
    )

    blockers: list[ReadinessIntelligenceBlocker] = []
    explanation: list[str] = [
        f"Aerospace Intelligence State is {state.aerospace_intelligence_status} "
        f"({state.total_blocker_count} blocker(s), {state.total_warning_count} warning(s))."
    ]
    for b in state.blockers:
        regulatory_reference = (
            f"{b.regulatory_ref_number}: {b.regulatory_ref_title}"
            if b.regulatory_ref_number
            else None
        )
        blockers.append(
            ReadinessIntelligenceBlocker(
                source_domain="AEROSPACE_STATE",
                category=f"{b.dimension}:{b.category}",
                description=b.why_condition,
                related_record_id=b.source_ref.source_id,
                related_record_type=b.source_ref.source_type,
                required_action=b.required_action,
                resolution_action=b.resolution_action,
                regulatory_reference=regulatory_reference,
            )
        )

    # Open work orders touching this asset, either directly (asset_id) or via
    # the aircraft this asset resolves to -- same dual-relationship pattern
    # release_readiness_service and readiness_service already rely on.
    conditions = [WorkOrder.asset_id == asset_id]
    if state.aircraft_id is not None:
        conditions.append(WorkOrder.aircraft_id == state.aircraft_id)
    open_work_orders = list(
        db.execute(
            select(WorkOrder).where(
                WorkOrder.organization_id == organization_id,
                WorkOrder.deleted_at.is_(None),
                WorkOrder.status.not_in(_TERMINAL_WORK_ORDER_STATUSES),
                or_(*conditions),
            )
        ).scalars().all()
    )

    blocked_work_order_count = 0
    for work_order in open_work_orders:
        release_readiness = release_readiness_service.get_release_readiness_for_work_order(
            db, organization_id=organization_id, work_order_id=work_order.id
        )
        if release_readiness.status == "BLOCKED":
            blocked_work_order_count += 1
            for wb in release_readiness.blockers:
                blockers.append(
                    ReadinessIntelligenceBlocker(
                        source_domain="WORK_ORDER",
                        category=wb.category,
                        description=f"[work_order {work_order.work_order_number}] {wb.description}",
                        related_record_id=wb.related_record_id,
                        related_record_type=wb.category,
                    )
                )
    if blocked_work_order_count:
        explanation.append(
            f"{blocked_work_order_count} of {len(open_work_orders)} open work order(s) "
            "are release-BLOCKED."
        )

    deployment_blocker_count = 0
    if asset.asset_type == AssetType.DRONE.value:
        try:
            deployment = readiness_service.evaluate_deployment_readiness(
                db, organization_id=organization_id, asset_id=asset_id
            )
        except NotFoundError:
            deployment = None
        if deployment is not None and deployment["status"] == "BLOCKED":
            deployment_blocker_count = len(deployment["blockers"])
            for blocker_text in deployment["blockers"]:
                blockers.append(
                    ReadinessIntelligenceBlocker(
                        source_domain="DEPLOYMENT",
                        category="DEPLOYMENT_BLOCKER",
                        description=blocker_text,
                        related_record_id=asset_id,
                        related_record_type="Asset",
                    )
                )
            explanation.append(
                f"Drone deployment readiness reports {deployment_blocker_count} blocker(s)."
            )

    extra_blockers = blocked_work_order_count > 0 or deployment_blocker_count > 0
    if state.aerospace_intelligence_status in _BLOCKING_AEROSPACE_STATUSES or extra_blockers:
        readiness_state: ReadinessState = "BLOCKED"
    elif state.aerospace_intelligence_status == AerospaceIntelligenceStatus.UNKNOWN_INTEL:
        readiness_state = "UNKNOWN"
        explanation.append(
            "Aerospace Intelligence State is UNKNOWN_INTEL -- insufficient data to call "
            "this asset READY."
        )
    else:
        readiness_state = "READY"
        explanation.append(
            "No blockers found across aerospace state, work-order, or deployment gates."
        )

    contributing_factors: dict[str, int | str] = {
        "aerospace_intelligence_status": state.aerospace_intelligence_status,
        "operational_state": state.operational_dimension.operational_state,
        "open_work_orders_count": len(open_work_orders),
        "blocked_work_orders_count": blocked_work_order_count,
        "deployment_blockers_count": deployment_blocker_count,
        "overdue_obligations_count": state.compliance_dimension.obligations_overdue,
        "critical_findings_count": state.finding_dimension.findings_critical,
        "missing_evidence_count": state.evidence_dimension.evidence_missing,
        "rejected_evidence_count": state.evidence_dimension.evidence_rejected,
    }

    return AssetReadinessIntelligence(
        asset_id=asset_id,
        aircraft_id=state.aircraft_id,
        operational_state=state.operational_dimension.operational_state,
        readiness_state=readiness_state,
        blockers=blockers,
        contributing_factors=contributing_factors,
        explanation=explanation,
        data_completeness=_DATA_COMPLETENESS,
        evaluated_at=datetime.datetime.now(datetime.UTC),
    )
