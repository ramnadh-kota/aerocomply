"""Backend-authoritative proactive alerts and daily brief.

Every alert here is derived by composing EXISTING domain services (M2/M3) —
no calculation is duplicated, and no alert is emitted without a real
backing record. This deliberately covers fewer categories than the
frontend's getProactiveAlerts()/getDailyBrief() (frontend/lib/mock/ai/
proactive.ts), which also surfaces TAT/OVERDUE, PROCUREMENT_DELAY,
RECEIVING_DELAY, and VENDOR_RISK alerts — those all require either a
due-date column that doesn't exist anywhere in this schema (see
tat_service.py's documented reason) or a procurement/receiving timeliness
signal this backend does not track yet. Emitting those categories here
would mean fabricating urgency from data that doesn't exist, so they are
listed explicitly in DailyBrief.not_implemented rather than silently
skipped.
"""

import datetime
import uuid

from sqlalchemy.orm import Session

from app.models.aog_event import AogEventStatus
from app.models.compliance import ComplianceAssessmentStatus
from app.models.deferred_item import DeferredItemStatus
from app.models.part_requirement import PartRequirementStatus
from app.schemas.proactive import DailyBrief, ProactiveAlert
from app.services import (
    aircraft_service,
    aog_service,
    compliance_service,
    deferred_item_service,
    part_requirement_service,
    release_readiness_service,
    work_order_service,
)

_SEVERITY_ORDER = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2}

NOT_IMPLEMENTED_CATEGORIES = [
    "TAT / OVERDUE — no due_date column exists on WorkOrder in this schema (see tat_service.py)",
    "PROCUREMENT_DELAY — no expected-approval-time signal is tracked",
    "RECEIVING_DELAY — no expected-delivery-vs-actual comparison is tracked",
    "REGULATORY — no live regulatory feed is configured (see regulatory_service."
    "get_provider_status)",
    "VENDOR_RISK — no vendor performance/risk scoring beyond vendor_fit_service exists",
]


def get_proactive_alerts(db: Session, *, organization_id: uuid.UUID) -> list[ProactiveAlert]:
    alerts: list[ProactiveAlert] = []

    # AOG — every DECLARED/IN_RECOVERY event is CRITICAL.
    for event in aog_service.list_aog_events(db, organization_id=organization_id):
        if event.status not in (AogEventStatus.DECLARED, AogEventStatus.IN_RECOVERY):
            continue
        aircraft = aircraft_service.get_aircraft(
            db, organization_id=organization_id, aircraft_id=event.aircraft_id
        )
        alerts.append(
            ProactiveAlert(
                id=f"aog-{event.id}",
                category="AOG",
                severity="CRITICAL",
                title=f"{aircraft.registration} is AOG",
                message=event.root_cause or "AOG event declared, no root cause on file.",
                source_type="AogEvent",
                source_id=event.id,
                aircraft_id=event.aircraft_id,
            )
        )

    work_orders = work_order_service.list_work_orders(db, organization_id=organization_id)
    open_work_orders = [wo for wo in work_orders if wo.status != "COMPLETED"]

    for work_order in open_work_orders:
        # PART_SHORTAGE — one alert per SHORT part requirement on this WO.
        requirements = part_requirement_service.list_part_requirements_for_work_order(
            db, organization_id=organization_id, work_order_id=work_order.id
        )
        for requirement in requirements:
            if requirement.status != PartRequirementStatus.SHORT:
                continue
            alerts.append(
                ProactiveAlert(
                    id=f"shortage-{requirement.id}",
                    category="PART_SHORTAGE",
                    severity="HIGH",
                    title=f"Part shortage on {work_order.work_order_number}",
                    message=(
                        f"Requires {requirement.required_quantity}, "
                        f"{requirement.fulfilled_quantity} fulfilled — SHORT."
                    ),
                    source_type="PartRequirement",
                    source_id=requirement.id,
                    aircraft_id=work_order.aircraft_id,
                    work_order_id=work_order.id,
                )
            )

        # RELEASE_BLOCKER — one alert per work order with a BLOCKED result,
        # summarizing the categories actually returned by the deterministic
        # gate (never re-derived here).
        readiness = release_readiness_service.get_release_readiness_for_work_order(
            db, organization_id=organization_id, work_order_id=work_order.id
        )
        if readiness.status == "BLOCKED":
            categories = sorted({b.category for b in readiness.blockers})
            alerts.append(
                ProactiveAlert(
                    id=f"release-blocker-{work_order.id}",
                    category="RELEASE_BLOCKER",
                    severity="HIGH",
                    title=f"{work_order.work_order_number} is BLOCKED for release",
                    message=f"{len(readiness.blockers)} blocker(s): {', '.join(categories)}.",
                    source_type="WorkOrder",
                    source_id=work_order.id,
                    aircraft_id=work_order.aircraft_id,
                    work_order_id=work_order.id,
                )
            )

    # DEFERRED_MEL — open items, overdue (CRITICAL) or due within 30 days (MEDIUM).
    today = datetime.date.today()
    for item in deferred_item_service.list_fleet_deferred_items(
        db, organization_id=organization_id, open_only=True
    ):
        if item.status != DeferredItemStatus.OPEN or item.due_at is None:
            continue
        days_until_due = (item.due_at - today).days
        if days_until_due < 0:
            severity = "CRITICAL"
            message = f"Due date {item.due_at.isoformat()} has passed."
        elif days_until_due <= 30:
            severity = "MEDIUM"
            message = f"Due date {item.due_at.isoformat()} is within 30 days."
        else:
            continue
        alerts.append(
            ProactiveAlert(
                id=f"deferred-{item.id}",
                category="DEFERRED_MEL",
                severity=severity,
                title=f"Deferred item {'overdue' if severity == 'CRITICAL' else 'due soon'}",
                message=message,
                source_type="DeferredItem",
                source_id=item.id,
                aircraft_id=item.aircraft_id,
            )
        )

    # COMPLIANCE — NON_COMPLIANT assessments.
    for assessment in compliance_service.list_all_assessments(db, organization_id=organization_id):
        if assessment.status != ComplianceAssessmentStatus.NON_COMPLIANT:
            continue
        alerts.append(
            ProactiveAlert(
                id=f"compliance-{assessment.id}",
                category="COMPLIANCE",
                severity="HIGH",
                title="Non-compliant assessment",
                message=assessment.notes or "Assessment marked NON_COMPLIANT.",
                source_type="ComplianceAssessment",
                source_id=assessment.id,
                aircraft_id=assessment.aircraft_id,
            )
        )

    alerts.sort(key=lambda a: _SEVERITY_ORDER.get(a.severity, 99))
    return alerts


def get_daily_brief(db: Session, *, organization_id: uuid.UUID) -> DailyBrief:
    alerts = get_proactive_alerts(db, organization_id=organization_id)
    critical = [a for a in alerts if a.severity == "CRITICAL"]
    high = [a for a in alerts if a.severity == "HIGH"]
    medium = [a for a in alerts if a.severity == "MEDIUM"]
    return DailyBrief(
        generated_at=datetime.datetime.now(datetime.UTC),
        critical_count=len(critical),
        high_count=len(high),
        medium_count=len(medium),
        total_count=len(alerts),
        top_priorities=alerts[:5],
        not_implemented=NOT_IMPLEMENTED_CATEGORIES,
    )
