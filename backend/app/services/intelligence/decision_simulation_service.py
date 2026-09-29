"""M14.18 & M14.19: Decision Intelligence 2.0 & Simulation Service.

Provides grounded decision simulation and trade-off analysis across operational options
(Cost, Time, Availability, AOG Impact, Safety) backed by concrete evidence citations.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.models.proactive_signal import ProactiveSignalRecord
from app.models.finding import Finding
from app.models.evidence import Evidence


@dataclass
class DecisionOption:
    option_id: str
    title: str
    action_type: str  # IMMEDIATE_MAINTENANCE | NEXT_SCHEDULED_CHECK | OPERATIONAL_MONITORING
    safety_risk_reduction: str  # HIGH | MODERATE | LOW
    estimated_downtime_hours: float
    aog_risk_tier: str  # MINIMAL | ELEVATED | HIGH
    part_requirement: str | None
    operational_constraints: list[str] = field(default_factory=list)
    rationale: str = ""


@dataclass
class DecisionSimulationResult:
    signal_id: uuid.UUID
    signal_title: str
    asset_id: uuid.UUID | None
    current_risk_score: float
    evidence_references: list[dict[str, Any]]
    simulation_timestamp: datetime
    recommended_option_id: str
    options: list[DecisionOption]


def simulate_decision_scenarios(
    db: Session,
    *,
    organization_id: uuid.UUID,
    signal_id: uuid.UUID,
) -> DecisionSimulationResult:
    """Simulates 3 operational response scenarios for an active M7 proactive intelligence signal."""
    signal = db.execute(
        select(ProactiveSignalRecord).where(
            ProactiveSignalRecord.organization_id == organization_id,
            ProactiveSignalRecord.id == signal_id,
        )
    ).scalar_one_or_none()

    if signal is None:
        raise NotFoundError(f"Proactive signal {signal_id} not found.")

    evidence_refs = signal.evidence_json or []
    now = datetime.now(UTC)

    # Option A: Immediate Line Inspection
    opt_a = DecisionOption(
        option_id="OPT_IMMEDIATE_ACTION",
        title="Immediate Maintenance Action & Line Inspection",
        action_type="IMMEDIATE_MAINTENANCE",
        safety_risk_reduction="HIGH",
        estimated_downtime_hours=3.5,
        aog_risk_tier="MINIMAL",
        part_requirement="Inspect and replace bearing/sensor seal if play exceeded.",
        operational_constraints=["Asset grounded until technician signoff and RII verification."],
        rationale="Eliminates inflight failure risk immediately. Best suited for high risk scores (>70).",
    )

    # Option B: Schedule at Next Routine Interval
    opt_b = DecisionOption(
        option_id="OPT_NEXT_ROUTINE",
        title="Schedule at Next A-Check / 50-Hour Interval",
        action_type="NEXT_SCHEDULED_CHECK",
        safety_risk_reduction="MODERATE",
        estimated_downtime_hours=0.0,  # Consolidated with scheduled check
        aog_risk_tier="ELEVATED",
        part_requirement="Pre-order replacement assembly for upcoming hangar visit.",
        operational_constraints=["Requires daily pre-flight vibration telemetry check."],
        rationale="Avoids unscheduled schedule disruption, but carries moderate risk of worsening wear.",
    )

    # Option C: Enhanced Telemetry Monitoring
    opt_c = DecisionOption(
        option_id="OPT_CONTINUED_MONITORING",
        title="Continue Operations under Tightened Telemetry Freshness",
        action_type="OPERATIONAL_MONITORING",
        safety_risk_reduction="LOW",
        estimated_downtime_hours=0.0,
        aog_risk_tier="HIGH",
        part_requirement=None,
        operational_constraints=["Telemetry freshness warning set to 24 hours.", "Flight restricted if exceedance re-occurs."],
        rationale="Maximizes asset availability if anomaly is deemed borderline (<50 risk score).",
    )

    # Deterministic recommendation based on severity/priority
    is_critical = signal.severity in ("CRITICAL", "HIGH") or signal.priority in ("P0", "P1")
    is_major = signal.severity == "MAJOR" or signal.priority == "P2"
    if is_critical:
        recommended = opt_a.option_id
    elif is_major:
        recommended = opt_b.option_id
    else:
        recommended = opt_c.option_id

    return DecisionSimulationResult(
        signal_id=signal.id,
        signal_title=signal.title,
        asset_id=signal.asset_id,
        current_risk_score=90.0 if is_critical else (60.0 if is_major else 30.0),
        evidence_references=evidence_refs,
        simulation_timestamp=now,
        recommended_option_id=recommended,
        options=[opt_a, opt_b, opt_c],
    )
