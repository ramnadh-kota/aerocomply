"""M7: Proactive Aerospace Intelligence, Risk & Decision Automation Service.

Implements the deterministic early-warning engine, threshold monitors, recurring finding detector,
utilization trend analyzer, compliance & evidence gap identifier, readiness degradation explainer,
fleet pattern detector, and signal lifecycle management.
"""

from __future__ import annotations

import datetime
import uuid
from typing import Any

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.models.aircraft import Aircraft
from app.models.asset import Asset, AssetType
from app.models.asset_baseline import AssetHistoricalBaseline
from app.models.battery import Battery, BatteryStatus
from app.models.compliance import ComplianceAssessment, ComplianceAssessmentStatus, ComplianceObligation, ComplianceState
from app.models.component import Component, ComponentStatus
from app.models.evidence import Evidence, EvidenceFile
from app.models.task import Task
from app.models.finding import Finding, FindingSeverity, FindingStatus
from app.models.flight import Flight
from app.models.hums import HUMSExceedance, HUMSSensor, HUMSSensorReading
from app.models.inspection_requirement import InspectionRequirement
from app.models.installation_history import ComponentInstallation
from app.models.proactive_signal import ProactiveSignalRecord
from app.models.work_order import WorkOrder
from app.schemas.intelligence_signal import (
    ProactiveIntelligenceSummary,
    ProactiveSignalResponse,
    SignalActionItem,
    SignalEvidenceRef,
    SignalPriority,
    SignalSeverity,
    SignalStatus,
    SignalType,
)
from app.services import flight_service
from app.services.intelligence import readiness_intelligence_service, risk_intelligence_service

_SEVERITY_WEIGHTS = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}


def _get_asset_utilization(db: Session, organization_id: uuid.UUID, asset_id: uuid.UUID) -> tuple[float, int]:
    """Computes total flight hours and cycles: Historical Baseline + Verified Flights without double counting."""
    util = flight_service.get_utilization(db, organization_id=organization_id, asset_id=asset_id)
    total_hours = round(float(util["total_minutes"]) / 60.0, 2)
    total_cycles = int(util["total_cycles"])
    return total_hours, total_cycles


def _evaluate_maintenance_thresholds(
    db: Session, organization_id: uuid.UUID, asset: Asset, reg_label: str
) -> list[dict[str, Any]]:
    signals: list[dict[str, Any]] = []
    total_hours, total_cycles = _get_asset_utilization(db, organization_id, asset.id)

    # 1. Evaluate open Work Orders with upcoming or overdue due_at
    now = datetime.datetime.now(datetime.UTC)
    today = now.date()

    work_orders = db.execute(
        select(WorkOrder).where(
            WorkOrder.organization_id == organization_id,
            WorkOrder.asset_id == asset.id,
            WorkOrder.status.in_(["OPEN", "IN_PROGRESS", "AWAITING_PARTS", "SCHEDULED"]),
        )
    ).scalars().all()

    for wo in work_orders:
        if wo.due_at:
            due_date = wo.due_at.date() if isinstance(wo.due_at, datetime.datetime) else wo.due_at
            days_remaining = (due_date - today).days
            if days_remaining < 0:
                # Overdue Work Order
                signals.append({
                    "signal_key": f"maint_overdue:{asset.id}:{wo.id}",
                    "signal_type": "MAINTENANCE_THRESHOLD",
                    "severity": "CRITICAL",
                    "priority": "CRITICAL",
                    "title": f"Maintenance Overdue — {wo.work_order_number}",
                    "headline": f"Work order {wo.work_order_number} on {reg_label} passed due date ({days_remaining * -1} days overdue).",
                    "explanation": [
                        f"Work order {wo.work_order_number} ('{wo.title}') was scheduled for completion by {due_date.isoformat()}.",
                        f"Current status is '{wo.status}', causing operational readiness restriction.",
                    ],
                    "asset_id": asset.id,
                    "evidence": [
                        SignalEvidenceRef(
                            source_type="WorkOrder",
                            source_id=str(wo.id),
                            label=f"Work Order {wo.work_order_number}",
                            metric="due_date",
                            current_value=due_date.isoformat(),
                            threshold_value=today.isoformat(),
                            details=f"Status: {wo.status}, Priority: {wo.priority}",
                        ),
                    ],
                    "contributing_factors": {
                        "work_order_id": str(wo.id),
                        "days_overdue": days_remaining * -1,
                        "status": wo.status,
                    },
                    "recommended_actions": [
                        SignalActionItem(
                            action_type="CREATE_WORK_ORDER",
                            title="Expedite Work Order",
                            description=f"Assign technicians and expedite work order {wo.work_order_number}.",
                            target_url=f"/maintenance/work-orders/{wo.id}",
                            requires_authorization=True,
                        ),
                        SignalActionItem(
                            action_type="ASK_LISA",
                            title="Ask LISA Root Cause",
                            description=f"Investigate work order blockers for {wo.work_order_number}.",
                            target_url=f"/ai?q=Why is {reg_label} blocked by {wo.work_order_number}",
                            requires_authorization=False,
                        ),
                    ],
                })
            elif days_remaining <= 7:
                # Approaching due date
                signals.append({
                    "signal_key": f"maint_due_soon:{asset.id}:{wo.id}",
                    "signal_type": "MAINTENANCE_THRESHOLD",
                    "severity": "HIGH" if days_remaining <= 2 else "MEDIUM",
                    "priority": "HIGH" if days_remaining <= 2 else "MEDIUM",
                    "title": f"Maintenance Due in {days_remaining} Days — {wo.work_order_number}",
                    "headline": f"Work order {wo.work_order_number} on {reg_label} is due on {due_date.isoformat()} ({days_remaining} days remaining).",
                    "explanation": [
                        f"Work order {wo.work_order_number} ('{wo.title}') is scheduled for {due_date.isoformat()}.",
                        "Timely completion is required to prevent maintenance grounding.",
                    ],
                    "asset_id": asset.id,
                    "evidence": [
                        SignalEvidenceRef(
                            source_type="WorkOrder",
                            source_id=str(wo.id),
                            label=f"Work Order {wo.work_order_number}",
                            metric="days_remaining",
                            current_value=days_remaining,
                            threshold_value=7,
                            details=f"Scheduled Due Date: {due_date.isoformat()}",
                        ),
                    ],
                    "contributing_factors": {
                        "work_order_id": str(wo.id),
                        "days_remaining": days_remaining,
                    },
                    "recommended_actions": [
                        SignalActionItem(
                            action_type="CREATE_WORK_ORDER",
                            title="Review Work Order",
                            description=f"Verify material availability and technician scheduling for {wo.work_order_number}.",
                            target_url=f"/maintenance/work-orders/{wo.id}",
                            requires_authorization=False,
                        ),
                    ],
                })

    # 2. Evaluate Battery Cycle / Health thresholds (for drones/eVTOL)
    batteries = db.execute(
        select(Battery).where(
            Battery.organization_id == organization_id,
            Battery.asset_id == asset.id,
        )
    ).scalars().all()

    for bat in batteries:
        cycle_limit = getattr(bat, "max_cycles", None) or 300
        cycles_left = cycle_limit - bat.cycle_count
        if bat.health_percent is not None and bat.health_percent <= 80.0:
            signals.append({
                "signal_key": f"bat_health_degraded:{asset.id}:{bat.id}",
                "signal_type": "MAINTENANCE_THRESHOLD",
                "severity": "HIGH",
                "priority": "HIGH",
                "title": f"Battery Degradation Alert — SN {bat.serial_number}",
                "headline": f"Battery {bat.serial_number} health degraded to {bat.health_percent}% (threshold 80%).",
                "explanation": [
                    f"Battery SN {bat.serial_number} capacity has degraded to {bat.health_percent}%.",
                    f"Total cycles logged: {bat.cycle_count}/{cycle_limit}.",
                    "Degraded pack capacity introduces in-flight power drop risk.",
                ],
                "asset_id": asset.id,
                "evidence": [
                    SignalEvidenceRef(
                        source_type="Battery",
                        source_id=str(bat.id),
                        label=f"Battery {bat.serial_number}",
                        metric="health_percent",
                        current_value=bat.health_percent,
                        threshold_value=80.0,
                        details=f"Cycles: {bat.cycle_count}/{cycle_limit}",
                    ),
                ],
                "contributing_factors": {
                    "battery_id": str(bat.id),
                    "health_percent": bat.health_percent,
                    "cycle_count": bat.cycle_count,
                },
                "recommended_actions": [
                    SignalActionItem(
                        action_type="INSPECT_COMPONENT",
                        title="Schedule Battery Replacement",
                        description=f"Inspect and cycle-test battery {bat.serial_number} or replace before flight operations.",
                        target_url=f"/components",
                        requires_authorization=True,
                    ),
                ],
            })
        elif cycles_left <= 25:
            signals.append({
                "signal_key": f"bat_cycles_limit:{asset.id}:{bat.id}",
                "signal_type": "MAINTENANCE_THRESHOLD",
                "severity": "HIGH" if cycles_left <= 10 else "MEDIUM",
                "priority": "HIGH" if cycles_left <= 10 else "MEDIUM",
                "title": f"Battery Cycle Limit Approaching — SN {bat.serial_number}",
                "headline": f"Battery {bat.serial_number} has {cycles_left} cycles remaining ({bat.cycle_count}/{cycle_limit} cycles).",
                "explanation": [
                    f"Battery SN {bat.serial_number} has accrued {bat.cycle_count} charge cycles.",
                    f"Service threshold limit is {cycle_limit} cycles.",
                ],
                "asset_id": asset.id,
                "evidence": [
                    SignalEvidenceRef(
                        source_type="Battery",
                        source_id=str(bat.id),
                        label=f"Battery {bat.serial_number}",
                        metric="cycles_remaining",
                        current_value=cycles_left,
                        threshold_value=25,
                        details=f"Current: {bat.cycle_count}, Max: {cycle_limit}",
                    ),
                ],
                "contributing_factors": {
                    "battery_id": str(bat.id),
                    "cycle_count": bat.cycle_count,
                    "cycles_remaining": cycles_left,
                },
                "recommended_actions": [
                    SignalActionItem(
                        action_type="INSPECT_COMPONENT",
                        title="Order Replacement Pack",
                        description=f"Stage procurement for replacement battery pack before {cycles_left} cycles expire.",
                        target_url="/procurement",
                        requires_authorization=False,
                    ),
                ],
            })

    return signals


from app.models.maintenance_requirement import (
    MaintenanceIntervalType,
    MaintenanceRequirement,
    MaintenanceRequirementApplicability,
)


def _evaluate_inspection_thresholds(
    db: Session, organization_id: uuid.UUID, asset: Asset, reg_label: str
) -> list[dict[str, Any]]:
    signals: list[dict[str, Any]] = []
    total_hours, total_cycles = _get_asset_utilization(db, organization_id, asset.id)

    # Find aircraft ID if present
    aircraft = db.execute(
        select(Aircraft).where(
            Aircraft.organization_id == organization_id,
            Aircraft.asset_id == asset.id,
        )
    ).scalar_one_or_none()

    # Applicable maintenance requirement IDs
    from sqlalchemy import or_
    app_filters = [MaintenanceRequirementApplicability.asset_id == asset.id]
    if aircraft is not None:
        app_filters.append(MaintenanceRequirementApplicability.aircraft_id == aircraft.id)

    app_req_ids = db.execute(
        select(MaintenanceRequirementApplicability.requirement_id).where(
            MaintenanceRequirementApplicability.organization_id == organization_id,
            or_(*app_filters),
        )
    ).scalars().all()

    if app_req_ids:
        maint_reqs = db.execute(
            select(MaintenanceRequirement).where(
                MaintenanceRequirement.organization_id == organization_id,
                MaintenanceRequirement.id.in_(app_req_ids),
            )
        ).scalars().all()
    else:
        maint_reqs = db.execute(
            select(MaintenanceRequirement).where(
                MaintenanceRequirement.organization_id == organization_id,
            )
        ).scalars().all()

    for req in maint_reqs:
        # Check flight hour interval
        interval_hours = float(req.fh_interval) if req.fh_interval else None
        if interval_hours and interval_hours > 0:
            hours_since_check = total_hours % interval_hours if total_hours >= interval_hours else total_hours
            hours_remaining = round(interval_hours - hours_since_check, 1)

            if hours_remaining <= 0 or (total_hours >= interval_hours and hours_since_check < 0.1):
                # Overdue / due now
                signals.append({
                    "signal_key": f"insp_due:{asset.id}:{req.id}",
                    "signal_type": "INSPECTION_THRESHOLD",
                    "severity": "CRITICAL",
                    "priority": "CRITICAL",
                    "title": f"Mandatory Inspection Overdue — {req.description}",
                    "headline": f"{req.description} on {reg_label} has reached the {interval_hours} FH threshold ({total_hours} total FH).",
                    "explanation": [
                        f"{req.description} threshold is {interval_hours} FH.",
                        f"Asset {reg_label} has accrued {total_hours} flight hours.",
                        "Airworthiness regulations mandate inspection sign-off before further flight dispatch.",
                    ],
                    "asset_id": asset.id,
                    "evidence": [
                        SignalEvidenceRef(
                            source_type="MaintenanceRequirement",
                            source_id=str(req.id),
                            label=req.description,
                            metric="flight_hours",
                            current_value=total_hours,
                            threshold_value=interval_hours,
                            details=f"Mandatory Interval: {interval_hours} FH",
                        ),
                        SignalEvidenceRef(
                            source_type="Flight",
                            source_id=None,
                            label="Total Accrued Utilization",
                            metric="flight_hours",
                            current_value=total_hours,
                            threshold_value=interval_hours,
                        ),
                    ],
                    "contributing_factors": {
                        "inspection_id": str(req.id),
                        "total_flight_hours": total_hours,
                        "interval_hours": interval_hours,
                    },
                    "recommended_actions": [
                        SignalActionItem(
                            action_type="SCHEDULE_INSPECTION",
                            title="Schedule Inspection Gate",
                            description=f"Open and assign {req.description} inspection work order.",
                            target_url=f"/maintenance/inspections/{req.id}",
                            requires_authorization=True,
                        ),
                    ],
                })
            elif hours_remaining <= 25.0:
                # Approaching within 25 flight hours
                signals.append({
                    "signal_key": f"insp_approaching:{asset.id}:{req.id}",
                    "signal_type": "INSPECTION_THRESHOLD",
                    "severity": "HIGH" if hours_remaining <= 10.0 else "MEDIUM",
                    "priority": "HIGH" if hours_remaining <= 10.0 else "MEDIUM",
                    "title": f"Inspection Threshold Approaching — {req.description}",
                    "headline": f"{req.description} due in {hours_remaining} FH on {reg_label} ({total_hours}/{interval_hours} FH).",
                    "explanation": [
                        f"{req.description} interval is {interval_hours} FH.",
                        f"Asset has operated {total_hours} FH, leaving {hours_remaining} FH before mandatory gate.",
                        "Schedule upcoming maintenance window to prevent flight disruptions.",
                    ],
                    "asset_id": asset.id,
                    "evidence": [
                        SignalEvidenceRef(
                            source_type="MaintenanceRequirement",
                            source_id=str(req.id),
                            label=req.description,
                            metric="remaining_hours",
                            current_value=hours_remaining,
                            threshold_value=25.0,
                            details=f"Accrued: {total_hours} FH / Target: {interval_hours} FH",
                        ),
                    ],
                    "contributing_factors": {
                        "inspection_id": str(req.id),
                        "hours_remaining": hours_remaining,
                        "total_flight_hours": total_hours,
                    },
                    "recommended_actions": [
                        SignalActionItem(
                            action_type="SCHEDULE_INSPECTION",
                            title="Plan Inspection Window",
                            description=f"Reserve hangar slot for {req.description} before {hours_remaining} FH are consumed.",
                            target_url="/maintenance/planning",
                            requires_authorization=False,
                        ),
                    ],
                })

    return signals


def _evaluate_recurring_findings(
    db: Session, organization_id: uuid.UUID, asset: Asset, reg_label: str
) -> list[dict[str, Any]]:
    signals: list[dict[str, Any]] = []
    cutoff = datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=90)

    # Query all findings on this asset in rolling 90 days
    findings = db.execute(
        select(Finding).where(
            Finding.organization_id == organization_id,
            Finding.asset_id == asset.id,
            Finding.created_at >= cutoff,
        ).order_by(Finding.created_at.desc())
    ).scalars().all()

    # Group findings by category or component or system keyword
    SYSTEM_KEYWORDS = ["HYDRAULIC", "AVIONICS", "ENGINE", "BRAKE", "ELECTRICAL", "LANDING GEAR", "FUEL", "TRANSPONDER", "TCAS", "FLIGHT CONTROL", "CABIN", "STRUCTURAL"]

    category_map: dict[str, list[Finding]] = {}
    for f in findings:
        cat = getattr(f, "category", None) or getattr(f, "safety_significance", None)
        if not cat:
            combined_text = f"{f.title} {f.description or ''}".upper()
            matched = False
            for kw in SYSTEM_KEYWORDS:
                if kw in combined_text:
                    cat = kw
                    matched = True
                    break
            if not matched:
                cat = (f.title or "UNSPECIFIED").split()[0].upper()
        else:
            cat = str(cat).strip().upper()
        category_map.setdefault(cat, []).append(f)

    for cat, items in category_map.items():
        if len(items) >= 2:
            open_count = sum(1 for i in items if i.status != FindingStatus.CLOSED)
            severities = [i.severity for i in items]
            has_critical = FindingSeverity.CRITICAL in severities

            evidence_refs = [
                SignalEvidenceRef(
                    source_type="Finding",
                    source_id=str(item.id),
                    label=f"Finding {getattr(item, 'finding_number', None) or str(item.id)[:8]}",
                    metric="severity",
                    current_value=str(item.severity),
                    threshold_value="RECURRING",
                    details=f"{item.created_at.strftime('%Y-%m-%d')}: {item.title}",
                )
                for item in items[:4]
            ]

            signals.append({
                "signal_key": f"recurring_finding:{asset.id}:{cat}",
                "signal_type": "RECURRING_FINDING",
                "severity": "CRITICAL" if has_critical else ("HIGH" if open_count > 0 else "MEDIUM"),
                "priority": "CRITICAL" if has_critical else "HIGH",
                "title": f"Recurring {cat.title()} Finding Pattern ({len(items)} Occurrences)",
                "headline": f"{len(items)} related '{cat}' findings observed on {reg_label} in the past 90 days.",
                "explanation": [
                    f"{len(items)} discrepancies recorded under category '{cat}' within a 90-day observation window.",
                    f"{open_count} finding(s) remain currently open or in-progress.",
                    "Repeated observation suggests potential recurrent wear or component stress rather than isolated event.",
                ],
                "asset_id": asset.id,
                "evidence": evidence_refs,
                "contributing_factors": {
                    "category": cat,
                    "total_occurrences": len(items),
                    "open_occurrences": open_count,
                    "has_critical": has_critical,
                },
                "recommended_actions": [
                    SignalActionItem(
                        action_type="REVIEW_FINDING",
                        title=f"Review Recurring {cat} Findings",
                        description="Inspect prior technical log entries and verify corrective action efficacy.",
                        target_url=f"/maintenance/defects?assetId={asset.id}",
                        requires_authorization=False,
                    ),
                    SignalActionItem(
                        action_type="ASK_LISA",
                        title="Analyze Finding History with LISA",
                        description="Query LISA intelligence for historical patterns on this subsystem.",
                        target_url=f"/ai?q=Analyze recurring {cat} findings on {reg_label}",
                        requires_authorization=False,
                    ),
                ],
            })

    return signals


def _evaluate_utilization_trends(
    db: Session, organization_id: uuid.UUID, asset: Asset, reg_label: str
) -> list[dict[str, Any]]:
    signals: list[dict[str, Any]] = []
    now = datetime.datetime.now(datetime.UTC)
    t14 = now - datetime.timedelta(days=14)
    t28 = now - datetime.timedelta(days=28)

    # Query flight hours in [now-14d, now] vs [now-28d, now-14d]
    recent_hours_res = db.execute(
        select(func.coalesce(func.sum(Flight.duration_minutes), 0), func.count(Flight.id)).where(
            Flight.organization_id == organization_id,
            Flight.asset_id == asset.id,
            Flight.flown_at >= t14,
        )
    ).one()

    prior_hours_res = db.execute(
        select(func.coalesce(func.sum(Flight.duration_minutes), 0), func.count(Flight.id)).where(
            Flight.organization_id == organization_id,
            Flight.asset_id == asset.id,
            Flight.flown_at >= t28,
            Flight.flown_at < t14,
        )
    ).one()

    recent_hours = round(float(recent_hours_res[0]) / 60.0, 1)
    recent_sorties = int(recent_hours_res[1])
    prior_hours = round(float(prior_hours_res[0]) / 60.0, 1)

    if recent_hours >= 15.0 and (prior_hours == 0 or recent_hours >= prior_hours * 1.5):
        surge_pct = round(((recent_hours - prior_hours) / (prior_hours or 1.0)) * 100, 1)
        signals.append({
            "signal_key": f"utilization_surge:{asset.id}",
            "signal_type": "UTILIZATION_TREND",
            "severity": "MEDIUM",
            "priority": "MEDIUM",
            "title": f"Accelerated Utilization Pace (+{surge_pct}%)",
            "headline": f"{reg_label} logged {recent_hours} FH in last 14 days ({recent_sorties} sorties, surge of +{surge_pct}%).",
            "explanation": [
                f"Operational intensity increased from {prior_hours} FH to {recent_hours} FH over consecutive 14-day intervals.",
                "Accelerated flight hour accumulation will advance scheduled maintenance and inspection milestones earlier than forecasted.",
            ],
            "asset_id": asset.id,
            "evidence": [
                SignalEvidenceRef(
                    source_type="Flight",
                    source_id=None,
                    label="Recent 14-Day Sorties",
                    metric="recent_flight_hours",
                    current_value=recent_hours,
                    threshold_value=prior_hours,
                    details=f"{recent_sorties} sorties flown since {t14.strftime('%Y-%m-%d')}",
                ),
            ],
            "contributing_factors": {
                "recent_14d_hours": recent_hours,
                "prior_14d_hours": prior_hours,
                "surge_percentage": surge_pct,
            },
            "recommended_actions": [
                SignalActionItem(
                    action_type="MONITOR_ASSET",
                    title="Review Maintenance Forecast",
                    description="Recalculate upcoming component TSO and inspection schedules based on accelerated pace.",
                    target_url=f"/assets/{asset.id}",
                    requires_authorization=False,
                ),
            ],
        })

    return signals


def _evaluate_compliance_evidence_gaps(
    db: Session, organization_id: uuid.UUID, asset: Asset, reg_label: str
) -> list[dict[str, Any]]:
    signals: list[dict[str, Any]] = []

    # 1. Unverified or Unknown Compliance Obligations
    unknown_obligations = db.execute(
        select(ComplianceObligation).where(
            ComplianceObligation.organization_id == organization_id,
            ComplianceObligation.asset_id == asset.id,
            ComplianceObligation.status.in_([
                "UNKNOWN",
                ComplianceState.NOT_EVALUATED.value,
                ComplianceState.REVIEW_REQUIRED.value,
                ComplianceState.PENDING.value,
            ]),
        )
    ).scalars().all()

    if unknown_obligations:
        signals.append({
            "signal_key": f"compliance_gap:{asset.id}",
            "signal_type": "COMPLIANCE_RISK",
            "severity": "HIGH",
            "priority": "HIGH",
            "title": f"Compliance Verification Gap ({len(unknown_obligations)} Unverified Obligations)",
            "headline": f"{len(unknown_obligations)} regulatory obligations on {reg_label} are in UNKNOWN evaluation state.",
            "explanation": [
                f"{len(unknown_obligations)} compliance requirements have not completed formal evidence verification.",
                "Kleene 3-valued compliance logic prevents declaring airworthiness without verified documentary proof.",
                "Asset readiness remains restricted until obligations are verified with accepted evidence.",
            ],
            "asset_id": asset.id,
            "evidence": [
                SignalEvidenceRef(
                    source_type="ComplianceObligation",
                    source_id=str(ob.id),
                    label=ob.required_action or f"Obligation {str(ob.id)[:8]}",
                    metric="compliance_state",
                    current_value=ob.status,
                    threshold_value="COMPLIANT",
                    details="Regulatory Compliance Obligation",
                )
                for ob in unknown_obligations[:4]
            ],
            "contributing_factors": {
                "unknown_count": len(unknown_obligations),
            },
            "recommended_actions": [
                SignalActionItem(
                    action_type="VERIFY_COMPLIANCE",
                    title="Verify Compliance Records",
                    description="Upload Form 8130-3 / EASA Form 1 or inspection logbooks to clear unverified obligations.",
                    target_url=f"/compliance/obligations?assetId={asset.id}",
                    requires_authorization=True,
                ),
            ],
        })

    # 2. Missing Evidence on Completed Work Orders
    completed_wo_no_evidence = db.execute(
        select(WorkOrder).where(
            WorkOrder.organization_id == organization_id,
            WorkOrder.asset_id == asset.id,
            WorkOrder.status == "COMPLETED",
        )
    ).scalars().all()

    for wo in completed_wo_no_evidence:
        # Check if evidence file attached
        evidence_count = db.execute(
            # EvidenceFile has no work_order_id (the old filter raised
            # AttributeError for any asset with a completed work order); files
            # reach a work order via Evidence -> Task.
            select(func.count(EvidenceFile.id))
            .join(Evidence, Evidence.id == EvidenceFile.evidence_id)
            .join(Task, Task.id == Evidence.task_id)
            .where(
                EvidenceFile.organization_id == organization_id,
                Task.work_order_id == wo.id,
            )
        ).scalar() or 0

        if evidence_count == 0:
            signals.append({
                "signal_key": f"evidence_gap_wo:{asset.id}:{wo.id}",
                "signal_type": "EVIDENCE_GAP",
                "severity": "MEDIUM",
                "priority": "MEDIUM",
                "title": f"Evidence Gap — Completed Work Order {wo.work_order_number}",
                "headline": f"Work order {wo.work_order_number} marked COMPLETED without attached evidence file.",
                "explanation": [
                    f"Work order {wo.work_order_number} ('{wo.title}') was closed with zero attached evidence files.",
                    "Aerospace regulatory compliance requires signed work order sign-offs, 8130 release certificates, or maintenance logs.",
                ],
                "asset_id": asset.id,
                "evidence": [
                    SignalEvidenceRef(
                        source_type="WorkOrder",
                        source_id=str(wo.id),
                        label=f"Work Order {wo.work_order_number}",
                        metric="attached_evidence_files",
                        current_value=0,
                        threshold_value=1,
                        details=f"Closed with 0 attached files",
                    ),
                ],
                "contributing_factors": {
                    "work_order_id": str(wo.id),
                },
                "recommended_actions": [
                    SignalActionItem(
                        action_type="ATTACH_EVIDENCE",
                        title="Upload Maintenance Sign-off",
                        description=f"Attach signed task card or release certificate for {wo.work_order_number}.",
                        target_url=f"/maintenance/work-orders/{wo.id}",
                        requires_authorization=False,
                    ),
                ],
            })

    return signals


def _evaluate_readiness_degradation(
    db: Session, organization_id: uuid.UUID, asset: Asset, reg_label: str
) -> list[dict[str, Any]]:
    signals: list[dict[str, Any]] = []

    try:
        readiness = readiness_intelligence_service.get_asset_readiness_intelligence(
            db, organization_id=organization_id, asset_id=asset.id
        )
    except Exception:
        return signals

    if readiness.readiness_state == "BLOCKED" and readiness.blockers:
        blocker_descs = [b.description for b in readiness.blockers]
        signals.append({
            "signal_key": f"readiness_blocked:{asset.id}",
            "signal_type": "READINESS_DEGRADATION",
            "severity": "HIGH",
            "priority": "HIGH",
            "title": f"Operational Readiness Restricted — {reg_label}",
            "headline": f"Asset {reg_label} readiness is BLOCKED by {len(readiness.blockers)} active operational condition(s).",
            "explanation": [
                f"Asset operational state is currently '{readiness.operational_state}'.",
                f"Active blockers: {'; '.join(blocker_descs[:3])}.",
                "Readiness engine restricts flight dispatch until all hard blocking conditions are resolved.",
            ],
            "asset_id": asset.id,
            "evidence": [
                SignalEvidenceRef(
                    source_type=b.related_record_type or "ReadinessBlocker",
                    source_id=str(b.related_record_id) if b.related_record_id else None,
                    label=b.category,
                    metric="blocker",
                    current_value="BLOCKED",
                    threshold_value="READY",
                    details=b.description,
                )
                for b in readiness.blockers[:4]
            ],
            "contributing_factors": {
                "readiness_state": readiness.readiness_state,
                "blocker_count": len(readiness.blockers),
            },
            "recommended_actions": [
                SignalActionItem(
                    action_type="MONITOR_ASSET",
                    title="View Readiness Breakdown",
                    description=f"Inspect blocker resolution steps on {reg_label} workspace.",
                    target_url=f"/assets/{asset.id}",
                    requires_authorization=False,
                ),
            ],
        })

    return signals


def _evaluate_hums_telemetry_signals(
    db: Session, organization_id: uuid.UUID, asset: Asset, reg_label: str
) -> list[dict[str, Any]]:
    """Evaluates telemetry freshness and active HUMS exceedances into deterministic early-warning signals."""
    signals: list[dict[str, Any]] = []

    # 1. Active HUMS Exceedances
    exceedances = list(
        db.execute(
            select(HUMSExceedance).where(
                HUMSExceedance.organization_id == organization_id,
                HUMSExceedance.asset_id == asset.id,
            )
        )
        .scalars()
        .all()
    )

    for exc in exceedances:
        sensor = db.execute(
            select(HUMSSensor).where(
                HUMSSensor.id == exc.sensor_id,
                HUMSSensor.organization_id == organization_id,
            )
        ).scalar_one_or_none()

        sensor_code = sensor.sensor_code if sensor else "SENSOR"
        param_name = exc.parameter or (sensor.measurement_type if sensor else "vibration")
        sev = "CRITICAL" if exc.severity == "CRITICAL" else "HIGH"

        signals.append({
            "signal_key": f"hums_exceedance:{asset.id}:{exc.id}",
            "signal_type": "HUMS_VIBRATION_EXCEEDANCE" if "vibration" in param_name.lower() else "HUMS_EXCEEDANCE",
            "severity": sev,
            "priority": sev,
            "title": f"HUMS Exceedance — {sensor_code} ({param_name.title()})",
            "headline": f"{param_name.title()} reading ({exc.observed_value} {exc.threshold_value}) on {reg_label} exceeded threshold limit.",
            "explanation": [
                f"Sensor '{sensor_code}' triggered an active {exc.severity} exceedance.",
                f"Observed value is {exc.observed_value}, exceeding safety threshold limit of {exc.threshold_value}.",
                "Abnormal telemetry readings indicate potential component degradation or structural stress.",
            ],
            "asset_id": asset.id,
            "evidence": [
                SignalEvidenceRef(
                    source_type="HUMSExceedance",
                    source_id=str(exc.id),
                    label=f"Exceedance on {sensor_code}",
                    metric=param_name,
                    current_value=exc.observed_value,
                    threshold_value=exc.threshold_value,
                    details=f"Severity: {exc.severity}",
                ),
            ],
            "contributing_factors": {
                "exceedance_id": str(exc.id),
                "sensor_id": str(exc.sensor_id),
                "sensor_code": sensor_code,
                "parameter": param_name,
                "observed_value": exc.observed_value,
                "threshold_value": exc.threshold_value,
            },
            "recommended_actions": [
                SignalActionItem(
                    action_type="INSPECT_COMPONENT",
                    title="Inspect Sensor & Component",
                    description=f"Perform physical and diagnostic inspection on {reg_label} for sensor {sensor_code}.",
                    target_url=f"/fleet/aircraft/{asset.id}/health",
                    requires_authorization=True,
                ),
                SignalActionItem(
                    action_type="ASK_LISA",
                    title="Ask LISA Telemetry Diagnostic",
                    description=f"Query LISA for telemetry health verdict on {reg_label}.",
                    target_url=f"/ai?q=What is the telemetry health verdict for {reg_label}",
                    requires_authorization=False,
                ),
            ],
        })

    # 2. Telemetry Freshness Evaluation
    sensors = list(
        db.execute(
            select(HUMSSensor).where(
                HUMSSensor.organization_id == organization_id,
                HUMSSensor.asset_id == asset.id,
                HUMSSensor.status == "ACTIVE",
            )
        )
        .scalars()
        .all()
    )

    if sensors:
        latest_reading = db.execute(
            select(HUMSSensorReading)
            .where(
                HUMSSensorReading.organization_id == organization_id,
                HUMSSensorReading.asset_id == asset.id,
            )
            .order_by(HUMSSensorReading.recorded_at.desc())
            .limit(1)
        ).scalar_one_or_none()

        now = datetime.datetime.now(datetime.UTC)
        if latest_reading:
            reading_time = (
                latest_reading.recorded_at
                if latest_reading.recorded_at.tzinfo
                else latest_reading.recorded_at.replace(tzinfo=datetime.UTC)
            )
            days_since = (now - reading_time).days

            # Resolve configurable freshness policy
            from app.services.telemetry_service import resolve_effective_freshness_policy
            freshness_policy = resolve_effective_freshness_policy(db, organization_id, asset_id=asset.id)

            if freshness_policy.get("is_active", True) and days_since >= freshness_policy.get("warning_threshold_days", 7):
                is_critical = days_since >= freshness_policy.get("critical_threshold_days", 14)
                severity_val = "HIGH" if is_critical else "MEDIUM"
                priority_val = "HIGH" if is_critical else "MEDIUM"
                threshold_val = freshness_policy.get("warning_threshold_days", 7)

                signals.append({
                    "signal_key": f"telemetry_stale:{asset.id}",
                    "signal_type": "TELEMETRY_FRESHNESS",
                    "severity": severity_val,
                    "priority": priority_val,
                    "title": f"Telemetry Data Stale ({days_since} Days) — {reg_label}",
                    "headline": f"No telemetry received for {reg_label} since {reading_time.strftime('%Y-%m-%d')} ({days_since} days ago, threshold: {threshold_val}d).",
                    "explanation": [
                        f"Latest telemetry reading on {reg_label} was recorded on {reading_time.isoformat()}.",
                        f"Configured policy threshold is {threshold_val} days (Critical: {freshness_policy.get('critical_threshold_days', 14)}d).",
                        "Absence of fresh telemetry limits real-time health monitoring.",
                        "System marks telemetry state as STALE (does not assert healthy or unserviceable).",
                    ],
                    "asset_id": asset.id,
                    "evidence": [
                        SignalEvidenceRef(
                            source_type="HUMSSensorReading",
                            source_id=str(latest_reading.id),
                            label="Latest Sensor Reading",
                            metric="days_since_reading",
                            current_value=days_since,
                            threshold_value=threshold_val,
                            details=f"Last recorded at {reading_time.isoformat()}",
                        ),
                    ],
                    "contributing_factors": {
                        "latest_reading_id": str(latest_reading.id),
                        "recorded_at": reading_time.isoformat(),
                        "days_since": days_since,
                        "warning_threshold_days": threshold_val,
                        "critical_threshold_days": freshness_policy.get("critical_threshold_days", 14),
                    },
                    "recommended_actions": [
                        SignalActionItem(
                            action_type="MONITOR_ASSET",
                            title="Verify Telemetry Link",
                            description=f"Check telemetry ingest / FlightHub sync status for {reg_label}.",
                            target_url=f"/assets/{asset.id}",
                            requires_authorization=False,
                        ),
                    ],
                })

    return signals


def _evaluate_fleet_patterns(
    db: Session, organization_id: uuid.UUID, asset_signals: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    fleet_signals: list[dict[str, Any]] = []

    # Count recurring finding categories across fleet
    category_counts: dict[str, int] = {}
    for sig in asset_signals:
        if sig.get("signal_type") == "RECURRING_FINDING":
            cat = sig.get("contributing_factors", {}).get("category", "OTHER")
            category_counts[cat] = category_counts.get(cat, 0) + 1

    for cat, count in category_counts.items():
        if count >= 2:
            fleet_signals.append({
                "signal_key": f"fleet_pattern_findings:{cat}",
                "signal_type": "FLEET_PATTERN",
                "severity": "HIGH",
                "priority": "HIGH",
                "title": f"Fleet-Wide Finding Pattern — {cat.title()}",
                "headline": f"{count} distinct assets in the fleet exhibit recurring '{cat}' discrepancies.",
                "explanation": [
                    f"Concentration of '{cat}' technical findings detected across {count} fleet assets.",
                    "Fleet-wide occurrence suggests potential vendor batch defect, environmental exposure, or fleet campaign requirement.",
                ],
                "asset_id": None,
                "evidence": [
                    SignalEvidenceRef(
                        source_type="Finding",
                        source_id=None,
                        label=f"Fleet {cat.title()} Correlation",
                        metric="affected_assets",
                        current_value=count,
                        threshold_value=2,
                        details=f"Observed on {count} distinct aircraft/drones",
                    ),
                ],
                "contributing_factors": {
                    "category": cat,
                    "affected_assets_count": count,
                },
                "recommended_actions": [
                    SignalActionItem(
                        action_type="REVIEW_FINDING",
                        title="Initiate Fleet Technical Audit",
                        description=f"Conduct engineering review across all assets exhibiting {cat} findings.",
                        target_url="/maintenance/defects",
                        requires_authorization=True,
                    ),
                ],
            })

    return fleet_signals


def sync_and_get_signals(
    db: Session,
    *,
    organization_id: uuid.UUID,
    asset_id: uuid.UUID | None = None,
    signal_type: str | None = None,
    severity: str | None = None,
    status: str | None = None,
) -> list[ProactiveSignalResponse]:
    """Evaluates deterministic proactive intelligence, synchronizes persistent signal records,
    and returns filtered signal responses.
    """
    now = datetime.datetime.now(datetime.UTC)

    # 1. Fetch assets in scope
    asset_query = select(Asset).where(
        Asset.organization_id == organization_id,
        Asset.deleted_at.is_(None),
    )
    if asset_id:
        asset_query = asset_query.where(Asset.id == asset_id)

    assets = db.execute(asset_query).scalars().all()

    # Pre-fetch registration lookups
    aircraft_regs = {
        a.asset_id: a.registration
        for a in db.execute(
            select(Aircraft).where(Aircraft.organization_id == organization_id)
        ).scalars().all()
        if a.asset_id
    }

    evaluated_signals: list[dict[str, Any]] = []

    for ast in assets:
        reg = ast.registration or ast.serial_number or aircraft_regs.get(ast.id) or f"Asset {str(ast.id)[:8]}"
        ast_type = ast.asset_type.value if hasattr(ast.asset_type, "value") else str(ast.asset_type)

        evaluated_signals.extend(_evaluate_maintenance_thresholds(db, organization_id, ast, reg))
        evaluated_signals.extend(_evaluate_inspection_thresholds(db, organization_id, ast, reg))
        evaluated_signals.extend(_evaluate_recurring_findings(db, organization_id, ast, reg))
        evaluated_signals.extend(_evaluate_utilization_trends(db, organization_id, ast, reg))
        evaluated_signals.extend(_evaluate_compliance_evidence_gaps(db, organization_id, ast, reg))
        evaluated_signals.extend(_evaluate_readiness_degradation(db, organization_id, ast, reg))
        evaluated_signals.extend(_evaluate_hums_telemetry_signals(db, organization_id, ast, reg))

    # Evaluate fleet-wide patterns if evaluating whole organization
    if not asset_id:
        evaluated_signals.extend(_evaluate_fleet_patterns(db, organization_id, evaluated_signals))

    # 2. Synchronize with persistent DB records
    active_keys: set[str] = set()

    for item in evaluated_signals:
        key = item["signal_key"]
        active_keys.add(key)

        existing = db.execute(
            select(ProactiveSignalRecord).where(
                ProactiveSignalRecord.organization_id == organization_id,
                ProactiveSignalRecord.signal_key == key,
            )
        ).scalar_one_or_none()

        if existing:
            # If open or in-review, update live fields
            if existing.status in ("OPEN", "IN_REVIEW", "ACKNOWLEDGED"):
                existing.severity = item["severity"]
                existing.priority = item["priority"]
                existing.title = item["title"]
                existing.headline = item["headline"]
                existing.explanation_json = item["explanation"]
                existing.evidence_json = [
                    ev.model_dump() if hasattr(ev, "model_dump") else ev for ev in item["evidence"]
                ]
                existing.contributing_factors_json = item["contributing_factors"]
                existing.recommended_actions_json = [
                    act.model_dump() if hasattr(act, "model_dump") else act for act in item["recommended_actions"]
                ]
        else:
            # Insert new signal
            new_record = ProactiveSignalRecord(
                organization_id=organization_id,
                signal_key=key,
                signal_type=item["signal_type"],
                severity=item["severity"],
                priority=item["priority"],
                status="OPEN",
                title=item["title"],
                headline=item["headline"],
                explanation_json=item["explanation"],
                asset_id=item.get("asset_id"),
                detected_at=now,
                evidence_json=[
                    ev.model_dump() if hasattr(ev, "model_dump") else ev for ev in item["evidence"]
                ],
                contributing_factors_json=item["contributing_factors"],
                recommended_actions_json=[
                    act.model_dump() if hasattr(act, "model_dump") else act for act in item["recommended_actions"]
                ],
            )
            db.add(new_record)

    db.flush()

    # 3. Query all signal records for the organization with applied filters
    query = select(ProactiveSignalRecord).where(
        ProactiveSignalRecord.organization_id == organization_id
    )

    if asset_id:
        query = query.where(ProactiveSignalRecord.asset_id == asset_id)
    if signal_type:
        query = query.where(ProactiveSignalRecord.signal_type == signal_type)
    if severity:
        query = query.where(ProactiveSignalRecord.severity == severity)
    if status:
        query = query.where(ProactiveSignalRecord.status == status)

    records = db.execute(query).scalars().all()

    # Map to responses
    responses: list[ProactiveSignalResponse] = []
    for r in records:
        reg = aircraft_regs.get(r.asset_id) if r.asset_id else None
        
        evidence_objs = [
            SignalEvidenceRef(**ev) if isinstance(ev, dict) else ev
            for ev in (r.evidence_json or [])
        ]
        action_objs = [
            SignalActionItem(**act) if isinstance(act, dict) else act
            for act in (r.recommended_actions_json or [])
        ]

        responses.append(
            ProactiveSignalResponse(
                id=r.id,
                organization_id=r.organization_id,
                signal_key=r.signal_key,
                signal_type=r.signal_type,  # type: ignore[arg-type]
                severity=r.severity,  # type: ignore[arg-type]
                priority=r.priority,  # type: ignore[arg-type]
                status=r.status,  # type: ignore[arg-type]
                title=r.title,
                headline=r.headline,
                explanation=r.explanation_json or [],
                asset_id=r.asset_id,
                asset_registration=reg,
                detected_at=r.detected_at,
                evidence=evidence_objs,
                contributing_factors=r.contributing_factors_json or {},
                recommended_actions=action_objs,
                acknowledged_by_user_id=r.acknowledged_by_user_id,
                acknowledged_at=r.acknowledged_at,
                resolved_by_user_id=r.resolved_by_user_id,
                resolved_at=r.resolved_at,
                resolution_notes=r.resolution_notes,
                dismissed_by_user_id=r.dismissed_by_user_id,
                dismissed_at=r.dismissed_at,
                dismissal_reason=r.dismissal_reason,
                created_at=r.created_at,
                updated_at=getattr(r, "updated_at", None) or r.created_at,
            )
        )

    # Sort: Severity (CRITICAL -> HIGH -> MEDIUM -> LOW), then detected_at descending
    responses.sort(
        key=lambda s: (_SEVERITY_WEIGHTS.get(s.severity, 99), s.status != "OPEN", -s.detected_at.timestamp())
    )
    return responses


def get_proactive_summary(
    db: Session, *, organization_id: uuid.UUID
) -> ProactiveIntelligenceSummary:
    """Generates the Command Center Proactive Intelligence Overview."""
    signals = sync_and_get_signals(db, organization_id=organization_id)
    active_signals = [s for s in signals if s.status not in ("RESOLVED", "DISMISSED")]

    critical = [s for s in active_signals if s.severity == "CRITICAL"]
    high = [s for s in active_signals if s.severity == "HIGH"]
    medium = [s for s in active_signals if s.severity == "MEDIUM"]
    low = [s for s in active_signals if s.severity == "LOW"]

    by_type: dict[str, int] = {}
    for s in active_signals:
        by_type[s.signal_type] = by_type.get(s.signal_type, 0) + 1

    return ProactiveIntelligenceSummary(
        total_active_signals=len(active_signals),
        critical_count=len(critical),
        high_count=len(high),
        medium_count=len(medium),
        low_count=len(low),
        by_type=by_type,
        signals=active_signals,
        emerging_risks=[s for s in active_signals if s.severity in ("CRITICAL", "HIGH")],
        upcoming_thresholds=[s for s in active_signals if s.signal_type in ("MAINTENANCE_THRESHOLD", "INSPECTION_THRESHOLD")],
        recurring_findings=[s for s in active_signals if s.signal_type == "RECURRING_FINDING"],
        compliance_evidence_gaps=[s for s in active_signals if s.signal_type in ("COMPLIANCE_RISK", "EVIDENCE_GAP")],
        readiness_changes=[s for s in active_signals if s.signal_type == "READINESS_DEGRADATION"],
        fleet_patterns=[s for s in active_signals if s.signal_type == "FLEET_PATTERN"],
        generated_at=datetime.datetime.now(datetime.UTC),
    )


def acknowledge_signal(
    db: Session, *, organization_id: uuid.UUID, signal_id: uuid.UUID, user_id: uuid.UUID
) -> ProactiveSignalResponse:
    signal = db.execute(
        select(ProactiveSignalRecord).where(
            ProactiveSignalRecord.id == signal_id,
            ProactiveSignalRecord.organization_id == organization_id,
        )
    ).scalar_one_or_none()

    if not signal:
        raise NotFoundError("Signal not found", code="signal_not_found")

    signal.status = "ACKNOWLEDGED"
    signal.acknowledged_by_user_id = user_id
    signal.acknowledged_at = datetime.datetime.now(datetime.UTC)
    db.flush()

    signals = sync_and_get_signals(db, organization_id=organization_id)
    for s in signals:
        if s.id == signal_id:
            return s
    raise NotFoundError("Signal not found", code="signal_not_found")


def set_signal_in_review(
    db: Session, *, organization_id: uuid.UUID, signal_id: uuid.UUID, user_id: uuid.UUID, notes: str | None = None
) -> ProactiveSignalResponse:
    signal = db.execute(
        select(ProactiveSignalRecord).where(
            ProactiveSignalRecord.id == signal_id,
            ProactiveSignalRecord.organization_id == organization_id,
        )
    ).scalar_one_or_none()

    if not signal:
        raise NotFoundError("Signal not found", code="signal_not_found")

    signal.status = "IN_REVIEW"
    if notes:
        signal.resolution_notes = notes
    db.flush()

    signals = sync_and_get_signals(db, organization_id=organization_id)
    for s in signals:
        if s.id == signal_id:
            return s
    raise NotFoundError("Signal not found", code="signal_not_found")


def resolve_signal(
    db: Session, *, organization_id: uuid.UUID, signal_id: uuid.UUID, user_id: uuid.UUID, resolution_notes: str
) -> ProactiveSignalResponse:
    signal = db.execute(
        select(ProactiveSignalRecord).where(
            ProactiveSignalRecord.id == signal_id,
            ProactiveSignalRecord.organization_id == organization_id,
        )
    ).scalar_one_or_none()

    if not signal:
        raise NotFoundError("Signal not found", code="signal_not_found")

    signal.status = "RESOLVED"
    signal.resolved_by_user_id = user_id
    signal.resolved_at = datetime.datetime.now(datetime.UTC)
    signal.resolution_notes = resolution_notes
    db.flush()

    signals = sync_and_get_signals(db, organization_id=organization_id)
    for s in signals:
        if s.id == signal_id:
            return s
    raise NotFoundError("Signal not found", code="signal_not_found")


def dismiss_signal(
    db: Session, *, organization_id: uuid.UUID, signal_id: uuid.UUID, user_id: uuid.UUID, dismissal_reason: str
) -> ProactiveSignalResponse:
    signal = db.execute(
        select(ProactiveSignalRecord).where(
            ProactiveSignalRecord.id == signal_id,
            ProactiveSignalRecord.organization_id == organization_id,
        )
    ).scalar_one_or_none()

    if not signal:
        raise NotFoundError("Signal not found", code="signal_not_found")

    signal.status = "DISMISSED"
    signal.dismissed_by_user_id = user_id
    signal.dismissed_at = datetime.datetime.now(datetime.UTC)
    signal.dismissal_reason = dismissal_reason
    db.flush()

    signals = sync_and_get_signals(db, organization_id=organization_id)
    for s in signals:
        if s.id == signal_id:
            return s
    raise NotFoundError("Signal not found", code="signal_not_found")
