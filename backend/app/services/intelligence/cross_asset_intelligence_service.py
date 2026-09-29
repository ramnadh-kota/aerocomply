"""M14.15 & M14.16: Cross-Asset Intelligence Service.

Computes fleet-level degradation trends, cross-asset anomaly correlation, and repeat failure
patterns grounded strictly in authoritative PostgreSQL records within tenant isolation boundaries.

H8.1 EXTENSION (this module remains the sole owner of cross-asset
DESCRIPTIVE analytics -- see docs/H8_CROSS_ASSET_INTELLIGENCE.md):
Adds HUMS coverage, telemetry freshness, population statistics, component
distribution, exceedance distribution, diagnostic distribution, and
prognostic distribution -- all AGGREGATIONS of already-authoritative H1-H5
records, never a new scoring/diagnosis/RUL algorithm. Fleet-level HEALTH
distribution is derived from bulk queries over persisted M7
ProactiveSignalRecord health-degradation signals (created by H3's
health_service.sync_health_signal) plus HUMS sensor presence -- NOT by
re-running H3's health engine per asset (that engine has write side
effects -- it persists ProactiveSignalRecord/diagnostic/prognostic rows on
every call -- which would be inappropriate to trigger fleet-wide from a
read-only analytics endpoint). This module still does NOT own fleet
signal detection, fleet attention ranking, or fleet MRO rollup -- those
remain M7's (attention/signals) and a future H8 milestone's (MRO rollup)
responsibility respectively.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.aircraft import Aircraft
from app.models.asset import Asset
from app.models.component import Component
from app.models.finding import Finding
from app.models.flight import Flight
from app.models.hums import HUMSDiagnosticCandidate, HUMSExceedance, HUMSFeature, HUMSPrognosticRecord, HUMSSensor
from app.models.mro_intelligence import MaintenanceIntelligenceCandidate, MROCandidateStatus
from app.models.proactive_signal import ProactiveSignalRecord
from app.services import digital_twin_service
from app.services import mro_intelligence_service
from app.services.telemetry_service import resolve_effective_freshness_policy
import structlog

log = structlog.get_logger(__name__)

# Bounded per-organization cap on how many H7-affected assets get bounded
# per-asset H7 calls (get_compliance_impact / get_readiness_impact /
# detect_conflicts) for H8.4 -- mirrors H8.3's _MAX_TWIN_LOOKUPS pattern:
# these H7 functions are asset-scoped with no bulk path, so calling them
# fleet-wide would reintroduce N+1 at fleet scale.
_MAX_MRO_PER_ASSET_LOOKUPS = 50
_ACTIVE_CANDIDATE_STATUSES = (MROCandidateStatus.OPEN, MROCandidateStatus.UNDER_REVIEW, MROCandidateStatus.DEFERRED)

_DIAGNOSTIC_NON_TERMINAL_STATUSES_EXCLUDED = ("REJECTED", "RESOLVED")
# Bounded per-organization cap on how many affected assets get a
# digital-twin component-tree lookup (H8.3 -- see
# evaluate_fleet_hums_correlation's docstring for why this is scoped to
# the affected-asset set rather than the whole fleet).
_MAX_TWIN_LOOKUPS = 50

_OPEN_SIGNAL_STATUSES = ("OPEN", "ACKNOWLEDGED", "IN_REVIEW")
_SEVERITY_RANK = {"CRITICAL": 3, "HIGH": 2, "MEDIUM": 1, "LOW": 0}


@dataclass
class RecurringFaultPattern:
    component_or_sensor: str
    affected_asset_count: int
    total_occurrences: int
    severity: str
    sample_finding_titles: list[str] = field(default_factory=list)


@dataclass
class FleetHealthDistribution:
    """Descriptive bucket counts over ALREADY-COMPUTED H3 health state.

    Derived from persisted ProactiveSignalRecord (signal_type=
    HUMS_HEALTH_DEGRADATION) rows -- H3's health_service only ever creates
    one of these for DEGRADED/WARNING/CRITICAL component health, never for
    HEALTHY/WATCH (see health_service.sync_health_signal). An asset with
    active HUMS sensors and no open degradation signal is bucketed
    'healthy'; an asset with no HUMS sensors at all has no health basis and
    is bucketed 'unknown' rather than assumed healthy.
    """

    healthy_count: int
    degraded_count: int  # open signal severity MEDIUM
    attention_count: int  # open signal severity HIGH or CRITICAL
    unknown_count: int  # no HUMS sensors on the asset -- no health basis
    availability: str  # AVAILABLE | DATA_UNAVAILABLE


@dataclass
class FleetHUMSCoverage:
    assets_total: int
    assets_with_hums: int
    assets_without_hums: int
    coverage_percentage: float


@dataclass
class FleetTelemetryFreshness:
    fresh_count: int
    stale_count: int
    missing_count: int
    unknown_count: int
    availability: str


@dataclass
class FleetPopulationStatistics:
    asset_count: int
    active_asset_count: int
    component_count: int
    assets_with_hums: int
    assets_with_recent_telemetry: int
    assets_with_stale_telemetry: int
    assets_with_missing_telemetry: int


@dataclass
class ComponentTypeDistributionEntry:
    component_type: str
    component_count: int
    affected_component_count: int  # components with >=1 exceedance in the lookback window


@dataclass
class ExceedanceDistribution:
    total_exceedances: int
    affected_assets: int
    exceedances_by_type: dict[str, int]
    exceedances_by_asset: dict[str, int]


@dataclass
class DiagnosticDistribution:
    """Descriptive counts only -- never a new classification/confidence
    calculation. Sourced directly from HUMSDiagnosticCandidate (H4's own
    authoritative rows), bulk-queried, not recomputed."""

    diagnostic_candidate_count: int
    affected_assets: int
    by_fault_domain: dict[str, int]
    by_severity: dict[str, int]


@dataclass
class PrognosticDistribution:
    """Descriptive counts only -- never a new RUL calculation. Sourced
    directly from HUMSPrognosticRecord (H5's own authoritative
    is_current=True rows), bulk-queried, not recomputed."""

    assets_with_rul: int
    rul_distribution: dict[str, int]  # buckets: "<25", "25-100", "100-500", ">=500"
    low_confidence_count: int


@dataclass
class FleetIntelligenceSummary:
    organization_id: uuid.UUID
    total_assets: int
    active_hums_sensors: int
    exceedances_last_30d: int
    recurring_patterns: list[RecurringFaultPattern]
    fleet_health_status: str  # HEALTHY | ATTENTION | DEGRADED | INSUFFICIENT_DATA
    confidence_note: str
    # H8.1 additions (all descriptive, all derived at read time):
    health_distribution: FleetHealthDistribution | None = None
    hums_coverage: FleetHUMSCoverage | None = None
    telemetry_freshness: FleetTelemetryFreshness | None = None
    population_statistics: FleetPopulationStatistics | None = None
    component_distribution: list[ComponentTypeDistributionEntry] = field(default_factory=list)
    exceedance_distribution: ExceedanceDistribution | None = None
    diagnostic_distribution: DiagnosticDistribution | None = None
    prognostic_distribution: PrognosticDistribution | None = None


@dataclass
class FleetSignalByAsset:
    asset_id: uuid.UUID
    asset_registration: str | None
    active_signal_count: int
    highest_severity: str | None


@dataclass
class FleetSignalSummary:
    """H8.2: Descriptive aggregation of M7's OWN persisted
    ProactiveSignalRecord rows -- bulk-queried, read-only. M7
    (app.services.intelligence.proactive_intelligence_service) remains the
    sole owner of signal detection, severity/priority assignment,
    lifecycle, attention ranking, and fleet pattern detection; this
    dataclass buckets/tallies M7's existing output and passes through M7's
    existing FLEET_PATTERN signal rows unmodified -- it computes nothing
    that M7 did not already decide.
    """

    availability: str  # AVAILABLE | DATA_UNAVAILABLE
    total_active_signals: int
    severity_distribution: dict[str, int]
    signal_type_distribution: dict[str, int]
    affected_asset_count: int
    affected_component_count: int
    signals_by_asset: list[FleetSignalByAsset]
    recent_signals: list[ProactiveSignalRecord]
    fleet_patterns: list[ProactiveSignalRecord]
    # M7 signal aggregation composed with M14 population stats (H8.1's
    # FleetPopulationStatistics.asset_count) -- the ONLY correlation H8.2
    # builds; deeper multi-domain correlation is H8.3's job.
    assets_with_signals_ratio: str | None


def _compute_fleet_signal_summary(
    db: Session, *, organization_id: uuid.UUID, assets: list[Asset], asset_count_for_ratio: int
) -> FleetSignalSummary:
    """Bulk-queries M7's persisted ProactiveSignalRecord table for the
    organization (a single query, no per-asset loop calling M7). Buckets
    the rows by M7's own `severity` and `signal_type` fields, counts
    distinct affected assets/components, and returns M7's own
    FLEET_PATTERN rows as-is. Never calls
    proactive_intelligence_service.sync_and_get_signals /
    get_proactive_summary -- those recompute-and-persist signals on every
    call (a write side effect inappropriate for a read-only fleet
    aggregation); this function only reads the table M7 already wrote to.
    """
    records = list(
        db.execute(
            select(ProactiveSignalRecord).where(
                ProactiveSignalRecord.organization_id == organization_id,
                ProactiveSignalRecord.status.in_(_OPEN_SIGNAL_STATUSES),
            )
        ).scalars().all()
    )

    reg_by_asset: dict[uuid.UUID, str | None] = {a.id: getattr(a, "registration", None) or a.serial_number for a in assets}
    aircraft_regs = {
        a.asset_id: a.registration
        for a in db.execute(
            select(Aircraft).where(Aircraft.organization_id == organization_id)
        ).scalars().all()
        if a.asset_id
    }
    reg_by_asset.update({k: v for k, v in aircraft_regs.items() if v})

    severity_distribution: dict[str, int] = {}
    signal_type_distribution: dict[str, int] = {}
    affected_assets: set[uuid.UUID] = set()
    affected_components: set[uuid.UUID] = set()
    by_asset: dict[uuid.UUID, list[ProactiveSignalRecord]] = {}
    fleet_patterns: list[ProactiveSignalRecord] = []

    for r in records:
        severity_distribution[r.severity] = severity_distribution.get(r.severity, 0) + 1
        signal_type_distribution[r.signal_type] = signal_type_distribution.get(r.signal_type, 0) + 1
        if r.asset_id is not None:
            affected_assets.add(r.asset_id)
            by_asset.setdefault(r.asset_id, []).append(r)
        if r.component_id is not None:
            affected_components.add(r.component_id)
        if r.signal_type == "FLEET_PATTERN":
            fleet_patterns.append(r)

    signals_by_asset = []
    for asset_id, asset_records in sorted(by_asset.items(), key=lambda kv: str(kv[0])):
        highest = max((rec.severity for rec in asset_records), key=lambda sev: _SEVERITY_RANK.get(sev, -1), default=None)
        signals_by_asset.append(
            FleetSignalByAsset(
                asset_id=asset_id,
                asset_registration=reg_by_asset.get(asset_id),
                active_signal_count=len(asset_records),
                highest_severity=highest,
            )
        )

    recent_signals = sorted(records, key=lambda r: r.detected_at, reverse=True)[:10]

    # Zero active signals is a valid, successfully-checked AVAILABLE state
    # (the fleet has no open M7 signals), never DATA_UNAVAILABLE -- that
    # is reserved for when the underlying query itself cannot be answered
    # (never the case here: an empty organization still queries cleanly).
    availability = "AVAILABLE"

    ratio = None
    if asset_count_for_ratio > 0:
        ratio = f"{len(affected_assets)}/{asset_count_for_ratio}"

    return FleetSignalSummary(
        availability=availability,
        total_active_signals=len(records),
        severity_distribution=severity_distribution,
        signal_type_distribution=signal_type_distribution,
        affected_asset_count=len(affected_assets),
        affected_component_count=len(affected_components),
        signals_by_asset=signals_by_asset,
        recent_signals=recent_signals,
        fleet_patterns=fleet_patterns,
        assets_with_signals_ratio=ratio,
    )


def evaluate_fleet_signal_aggregation(
    db: Session, *, organization_id: uuid.UUID
) -> FleetSignalSummary:
    """H8.2 entry point: M7 signal aggregation composed with M14 fleet
    population stats. Read-only -- bulk-queries Asset + M7's persisted
    ProactiveSignalRecord, never mutates either."""
    assets = list(
        db.execute(
            select(Asset).where(
                Asset.organization_id == organization_id,
                Asset.deleted_at.is_(None),
            )
        ).scalars().all()
    )
    return _compute_fleet_signal_summary(
        db, organization_id=organization_id, assets=assets, asset_count_for_ratio=len(assets)
    )


def _compute_health_distribution(
    db: Session, *, organization_id: uuid.UUID, assets: list[Asset], sensors: list[HUMSSensor]
) -> FleetHealthDistribution:
    """Bulk-derives fleet health buckets from persisted M7 signals + HUMS
    sensor presence -- a single query per input, no per-asset H3 recompute."""
    assets_with_sensors = {s.asset_id for s in sensors}

    open_health_signals = list(
        db.execute(
            select(ProactiveSignalRecord).where(
                ProactiveSignalRecord.organization_id == organization_id,
                ProactiveSignalRecord.signal_type == "HUMS_HEALTH_DEGRADATION",
                ProactiveSignalRecord.status.in_(_OPEN_SIGNAL_STATUSES),
            )
        ).scalars().all()
    )

    # Worst open severity per asset.
    worst_by_asset: dict[uuid.UUID, str] = {}
    _rank = {"MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}
    for sig in open_health_signals:
        if sig.asset_id is None:
            continue
        current = worst_by_asset.get(sig.asset_id)
        if current is None or _rank.get(sig.severity, 0) > _rank.get(current, 0):
            worst_by_asset[sig.asset_id] = sig.severity

    healthy = degraded = attention = unknown = 0
    for asset in assets:
        if asset.id not in assets_with_sensors:
            unknown += 1
            continue
        sev = worst_by_asset.get(asset.id)
        if sev in ("HIGH", "CRITICAL"):
            attention += 1
        elif sev == "MEDIUM":
            degraded += 1
        else:
            healthy += 1

    availability = "AVAILABLE" if assets_with_sensors else "DATA_UNAVAILABLE"
    return FleetHealthDistribution(
        healthy_count=healthy, degraded_count=degraded, attention_count=attention,
        unknown_count=unknown, availability=availability,
    )


def _compute_hums_coverage(*, assets: list[Asset], sensors: list[HUMSSensor]) -> FleetHUMSCoverage:
    assets_with_hums = {s.asset_id for s in sensors}
    total = len(assets)
    with_hums = len([a for a in assets if a.id in assets_with_hums])
    without_hums = total - with_hums
    pct = round((with_hums / total) * 100, 2) if total else 0.0
    return FleetHUMSCoverage(
        assets_total=total, assets_with_hums=with_hums, assets_without_hums=without_hums,
        coverage_percentage=pct,
    )


def _compute_telemetry_freshness(
    db: Session, *, organization_id: uuid.UUID, assets: list[Asset]
) -> FleetTelemetryFreshness:
    """Reuses telemetry_service.resolve_effective_freshness_policy's exact
    threshold semantics (never a new threshold). Last-received timestamps
    are bulk-fetched in one grouped query; only the (lightweight, indexed)
    policy resolution is done per asset -- there is no existing bulk
    "resolve policy for N assets" path in telemetry_service today, so a
    per-asset policy lookup is accepted here as a foundation-phase
    limitation (no writes, no extra full-table scans).
    """
    from app.models.telemetry import TelemetryEventLog

    if not assets:
        return FleetTelemetryFreshness(fresh_count=0, stale_count=0, missing_count=0, unknown_count=0, availability="DATA_UNAVAILABLE")

    last_seen_rows = db.execute(
        select(TelemetryEventLog.asset_id, func.max(TelemetryEventLog.event_timestamp))
        .where(
            TelemetryEventLog.organization_id == organization_id,
            TelemetryEventLog.asset_id.is_not(None),
        )
        .group_by(TelemetryEventLog.asset_id)
    ).all()
    last_seen: dict[uuid.UUID, datetime] = {row[0]: row[1] for row in last_seen_rows}

    now = datetime.now(UTC)
    fresh = stale = missing = unknown = 0
    for asset in assets:
        last_received = last_seen.get(asset.id)
        if last_received is None:
            missing += 1
            continue
        try:
            policy = resolve_effective_freshness_policy(db, organization_id, asset_id=asset.id)
        except Exception:
            unknown += 1
            continue
        if not policy.get("is_active", True):
            fresh += 1
            continue
        if last_received.tzinfo is None:
            last_received = last_received.replace(tzinfo=UTC)
        if (now - last_received) > timedelta(days=policy["warning_threshold_days"]):
            stale += 1
        else:
            fresh += 1

    availability = "AVAILABLE" if last_seen else "DATA_UNAVAILABLE"
    return FleetTelemetryFreshness(fresh_count=fresh, stale_count=stale, missing_count=missing, unknown_count=unknown, availability=availability)


def _compute_component_distribution(
    db: Session, *, organization_id: uuid.UUID, exceedances: list[HUMSExceedance]
) -> list[ComponentTypeDistributionEntry]:
    components = list(
        db.execute(
            select(Component).where(Component.organization_id == organization_id)
        ).scalars().all()
    )
    if not components:
        return []

    affected_component_ids = {e.component_id for e in exceedances if e.component_id}
    by_type: dict[str, list[Component]] = {}
    for c in components:
        by_type.setdefault(c.component_type, []).append(c)

    entries = []
    for ctype, comps in sorted(by_type.items()):
        affected = len([c for c in comps if c.id in affected_component_ids])
        entries.append(ComponentTypeDistributionEntry(component_type=ctype, component_count=len(comps), affected_component_count=affected))
    return entries


def _compute_exceedance_distribution(exceedances: list[HUMSExceedance]) -> ExceedanceDistribution:
    by_type: dict[str, int] = {}
    by_asset: dict[str, int] = {}
    for e in exceedances:
        by_type[e.parameter] = by_type.get(e.parameter, 0) + 1
        by_asset[str(e.asset_id)] = by_asset.get(str(e.asset_id), 0) + 1
    return ExceedanceDistribution(
        total_exceedances=len(exceedances),
        affected_assets=len(by_asset),
        exceedances_by_type=by_type,
        exceedances_by_asset=by_asset,
    )


def _compute_diagnostic_distribution(db: Session, *, organization_id: uuid.UUID) -> DiagnosticDistribution:
    """Bulk-queries H4's own authoritative table directly -- no
    per-asset service loop, no independent scoring/classification."""
    candidates = list(
        db.execute(
            select(HUMSDiagnosticCandidate).where(
                HUMSDiagnosticCandidate.organization_id == organization_id,
                HUMSDiagnosticCandidate.status.not_in(["REJECTED", "RESOLVED"]),
            )
        ).scalars().all()
    )
    by_domain: dict[str, int] = {}
    by_severity: dict[str, int] = {}
    affected_assets = set()
    for c in candidates:
        by_domain[c.fault_domain] = by_domain.get(c.fault_domain, 0) + 1
        by_severity[c.severity] = by_severity.get(c.severity, 0) + 1
        affected_assets.add(c.asset_id)
    return DiagnosticDistribution(
        diagnostic_candidate_count=len(candidates), affected_assets=len(affected_assets),
        by_fault_domain=by_domain, by_severity=by_severity,
    )


def _compute_prognostic_distribution(db: Session, *, organization_id: uuid.UUID) -> PrognosticDistribution:
    """Bulk-queries H5's own authoritative is_current rows directly -- no
    per-asset service loop, no independent RUL calculation."""
    records = list(
        db.execute(
            select(HUMSPrognosticRecord).where(
                HUMSPrognosticRecord.organization_id == organization_id,
                HUMSPrognosticRecord.is_current.is_(True),
            )
        ).scalars().all()
    )
    assets_with_rul = {r.asset_id for r in records if r.rul_estimate is not None}
    buckets = {"<25": 0, "25-100": 0, "100-500": 0, ">=500": 0}
    low_confidence = 0
    for r in records:
        if r.rul_estimate is not None:
            if r.rul_estimate < 25:
                buckets["<25"] += 1
            elif r.rul_estimate < 100:
                buckets["25-100"] += 1
            elif r.rul_estimate < 500:
                buckets["100-500"] += 1
            else:
                buckets[">=500"] += 1
        if r.confidence == "LOW" or r.status in ("LOW_CONFIDENCE", "LIMITED", "INSUFFICIENT_DATA"):
            low_confidence += 1
    return PrognosticDistribution(
        assets_with_rul=len(assets_with_rul), rul_distribution=buckets, low_confidence_count=low_confidence,
    )


def evaluate_cross_asset_intelligence(
    db: Session,
    *,
    organization_id: uuid.UUID,
) -> FleetIntelligenceSummary:
    """Evaluates cross-asset failure patterns and degradation trends for an organization."""
    # 1. Asset count
    assets = list(
        db.execute(
            select(Asset).where(
                Asset.organization_id == organization_id,
                Asset.deleted_at.is_(None),
            )
        ).scalars().all()
    )
    total_assets = len(assets)

    if total_assets == 0:
        return FleetIntelligenceSummary(
            organization_id=organization_id,
            total_assets=0,
            active_hums_sensors=0,
            exceedances_last_30d=0,
            recurring_patterns=[],
            fleet_health_status="INSUFFICIENT_DATA",
            confidence_note="No registered fleet assets found in tenant organization.",
            health_distribution=FleetHealthDistribution(healthy_count=0, degraded_count=0, attention_count=0, unknown_count=0, availability="DATA_UNAVAILABLE"),
            hums_coverage=FleetHUMSCoverage(assets_total=0, assets_with_hums=0, assets_without_hums=0, coverage_percentage=0.0),
            telemetry_freshness=FleetTelemetryFreshness(fresh_count=0, stale_count=0, missing_count=0, unknown_count=0, availability="DATA_UNAVAILABLE"),
            population_statistics=FleetPopulationStatistics(
                asset_count=0, active_asset_count=0, component_count=0, assets_with_hums=0,
                assets_with_recent_telemetry=0, assets_with_stale_telemetry=0, assets_with_missing_telemetry=0,
            ),
            component_distribution=[],
            exceedance_distribution=ExceedanceDistribution(total_exceedances=0, affected_assets=0, exceedances_by_type={}, exceedances_by_asset={}),
            diagnostic_distribution=DiagnosticDistribution(diagnostic_candidate_count=0, affected_assets=0, by_fault_domain={}, by_severity={}),
            prognostic_distribution=PrognosticDistribution(assets_with_rul=0, rul_distribution={"<25": 0, "25-100": 0, "100-500": 0, ">=500": 0}, low_confidence_count=0),
        )

    # 2. Active sensors
    sensor_count = db.execute(
        select(func.count(HUMSSensor.id)).where(
            HUMSSensor.organization_id == organization_id,
            HUMSSensor.status == "ACTIVE",
        )
    ).scalar_one()

    all_sensors = list(
        db.execute(
            select(HUMSSensor).where(HUMSSensor.organization_id == organization_id)
        ).scalars().all()
    )

    # 3. Exceedances in last 30 days
    cutoff = datetime.now(UTC) - timedelta(days=30)
    recent_exceedances = list(
        db.execute(
            select(HUMSExceedance).where(
                HUMSExceedance.organization_id == organization_id,
                HUMSExceedance.window_end >= cutoff,
            )
        ).scalars().all()
    )

    # 4. Findings clustered by component/title
    findings = list(
        db.execute(
            select(Finding).where(
                Finding.organization_id == organization_id,
                Finding.created_at >= cutoff,
            )
        ).scalars().all()
    )

    # Group findings to detect cross-asset repeats
    cluster_map: dict[str, list[Finding]] = {}
    for f in findings:
        key = f.title.strip()
        cluster_map.setdefault(key, []).append(f)

    recurring_patterns = []
    for title_key, grouped in cluster_map.items():
        if len(grouped) >= 2:
            unique_assets = {f.asset_id or f.aircraft_id for f in grouped if (f.asset_id or f.aircraft_id)}
            max_sev = max((f.severity for f in grouped), default="MINOR")
            recurring_patterns.append(
                RecurringFaultPattern(
                    component_or_sensor=title_key,
                    affected_asset_count=len(unique_assets),
                    total_occurrences=len(grouped),
                    severity=str(max_sev),
                    sample_finding_titles=[f.title for f in grouped[:3]],
                )
            )

    # Determine health state
    if sensor_count == 0 and len(findings) == 0:
        health_status = "INSUFFICIENT_DATA"
        note = "Insufficient operational telemetry and maintenance history for fleet-level inference."
    elif len(recent_exceedances) > 5 or any(p.severity in ("MAJOR", "CRITICAL") for p in recurring_patterns):
        health_status = "DEGRADED"
        note = f"Elevated exceedance frequency ({len(recent_exceedances)}) and repeat anomalies identified across {len(recurring_patterns)} component groups."
    elif len(recent_exceedances) > 0 or len(recurring_patterns) > 0:
        health_status = "ATTENTION"
        note = "Mild anomaly clustering detected across fleet assets. Recommend pre-flight checks."
    else:
        health_status = "HEALTHY"
        note = "All active fleet assets operating within baseline statistical parameters."

    health_distribution = _compute_health_distribution(db, organization_id=organization_id, assets=assets, sensors=all_sensors)
    hums_coverage = _compute_hums_coverage(assets=assets, sensors=all_sensors)
    telemetry_freshness = _compute_telemetry_freshness(db, organization_id=organization_id, assets=assets)
    component_distribution = _compute_component_distribution(db, organization_id=organization_id, exceedances=recent_exceedances)
    exceedance_distribution = _compute_exceedance_distribution(recent_exceedances)
    diagnostic_distribution = _compute_diagnostic_distribution(db, organization_id=organization_id)
    prognostic_distribution = _compute_prognostic_distribution(db, organization_id=organization_id)

    active_asset_count = len([a for a in assets if getattr(a, "status", None) not in ("RETIRED", "INACTIVE", "DECOMMISSIONED")])
    component_count = sum(e.component_count for e in component_distribution)
    population_statistics = FleetPopulationStatistics(
        asset_count=total_assets,
        active_asset_count=active_asset_count,
        component_count=component_count,
        assets_with_hums=hums_coverage.assets_with_hums,
        assets_with_recent_telemetry=telemetry_freshness.fresh_count,
        assets_with_stale_telemetry=telemetry_freshness.stale_count,
        assets_with_missing_telemetry=telemetry_freshness.missing_count,
    )

    return FleetIntelligenceSummary(
        organization_id=organization_id,
        total_assets=total_assets,
        active_hums_sensors=sensor_count,
        exceedances_last_30d=len(recent_exceedances),
        recurring_patterns=recurring_patterns,
        fleet_health_status=health_status,
        confidence_note=note,
        health_distribution=health_distribution,
        hums_coverage=hums_coverage,
        telemetry_freshness=telemetry_freshness,
        population_statistics=population_statistics,
        component_distribution=component_distribution,
        exceedance_distribution=exceedance_distribution,
        diagnostic_distribution=diagnostic_distribution,
        prognostic_distribution=prognostic_distribution,
    )


# ---------------------------------------------------------------------------
# H8.3: Fleet HUMS Correlation
#
# CONSUMES existing intelligence only -- M7 (ProactiveSignalRecord), M14
# (this module's own H8.1/H8.2 population + signal aggregations), H4
# (HUMSDiagnosticCandidate), H5 (HUMSPrognosticRecord), and H6
# (digital_twin_service's read-only component-tree lookup). It does NOT
# recompute health, diagnose faults, calculate RUL, fit degradation
# models, detect signals, or rank attention -- see module docstring and
# docs/H8_FLEET_HUMS_INTELLIGENCE.md's H8.3 section for the full
# reuse map and the deterministic correlation rules below.
# ---------------------------------------------------------------------------


@dataclass
class ComponentTypeCorrelation:
    component_type: str
    model: str | None
    correlated_component_count: int
    asset_ids: list[uuid.UUID]
    signal_count: int
    diagnostic_count: int
    prognostic_count: int
    basis: str


@dataclass
class SignalDiagnosticAssociation:
    signal_id: uuid.UUID
    diagnostic_candidate_id: uuid.UUID
    asset_id: uuid.UUID
    component_id: uuid.UUID | None
    basis: str


@dataclass
class SignalPrognosticAssociation:
    signal_id: uuid.UUID
    prognostic_record_id: uuid.UUID
    asset_id: uuid.UUID
    component_id: uuid.UUID | None
    basis: str


@dataclass
class AssetCorrelation:
    asset_id: uuid.UUID
    asset_registration: str | None
    active_signal_count: int
    highest_signal_severity: str | None
    diagnostic_candidate_count: int
    prognostic_record_count: int
    has_rul_estimate: bool
    component_context_available: bool
    component_count: int | None
    evidence_completeness: str  # COMPLETE | PARTIAL | INSUFFICIENT_DATA
    evidence_note: str


@dataclass
class FleetCorrelationSummary:
    availability: str
    total_fleet_assets: int
    affected_asset_count: int
    affected_asset_percentage: float | None
    total_active_signal_count: int
    asset_correlations: list[AssetCorrelation]
    component_correlations: list[ComponentTypeCorrelation]
    signal_diagnostic_associations: list[SignalDiagnosticAssociation]
    signal_prognostic_associations: list[SignalPrognosticAssociation]
    explanation: list[str]


def _fetch_active_diagnostic_candidates(db: Session, *, organization_id: uuid.UUID) -> list[HUMSDiagnosticCandidate]:
    """Bulk read of H4's own authoritative table -- mirrors
    _compute_diagnostic_distribution's non-terminal-status filter. Never
    calls diagnostic_service (which has write side effects)."""
    return list(
        db.execute(
            select(HUMSDiagnosticCandidate).where(
                HUMSDiagnosticCandidate.organization_id == organization_id,
                HUMSDiagnosticCandidate.status.not_in(_DIAGNOSTIC_NON_TERMINAL_STATUSES_EXCLUDED),
            )
        ).scalars().all()
    )


def _fetch_current_prognostic_records(db: Session, *, organization_id: uuid.UUID) -> list[HUMSPrognosticRecord]:
    """Bulk read of H5's own authoritative is_current rows -- mirrors
    _compute_prognostic_distribution. Never calls prognostic_service
    (which has write side effects)."""
    return list(
        db.execute(
            select(HUMSPrognosticRecord).where(
                HUMSPrognosticRecord.organization_id == organization_id,
                HUMSPrognosticRecord.is_current.is_(True),
            )
        ).scalars().all()
    )


def _correlate_signals_to_diagnostics(
    signals: list[ProactiveSignalRecord], candidates: list[HUMSDiagnosticCandidate]
) -> list[SignalDiagnosticAssociation]:
    """Deterministic rule: a signal and a diagnostic candidate are
    associated when they share the same asset_id, and -- when both rows
    have a component_id set -- the same component_id too. Never a
    fabricated score; the association is the shared identity itself."""
    associations: list[SignalDiagnosticAssociation] = []
    by_asset: dict[uuid.UUID, list[HUMSDiagnosticCandidate]] = {}
    for c in candidates:
        by_asset.setdefault(c.asset_id, []).append(c)

    for sig in signals:
        if sig.asset_id is None:
            continue
        for cand in by_asset.get(sig.asset_id, []):
            if sig.component_id is not None and cand.component_id is not None:
                if sig.component_id != cand.component_id:
                    continue
                basis = "SAME_ASSET_AND_COMPONENT"
            else:
                basis = "SAME_ASSET"
            associations.append(
                SignalDiagnosticAssociation(
                    signal_id=sig.id, diagnostic_candidate_id=cand.id,
                    asset_id=sig.asset_id, component_id=sig.component_id or cand.component_id,
                    basis=basis,
                )
            )
    return associations


def _correlate_signals_to_prognostics(
    signals: list[ProactiveSignalRecord], records: list[HUMSPrognosticRecord]
) -> list[SignalPrognosticAssociation]:
    """Same deterministic same-asset[-and-component] rule as
    _correlate_signals_to_diagnostics, applied to H5's records."""
    associations: list[SignalPrognosticAssociation] = []
    by_asset: dict[uuid.UUID, list[HUMSPrognosticRecord]] = {}
    for r in records:
        by_asset.setdefault(r.asset_id, []).append(r)

    for sig in signals:
        if sig.asset_id is None:
            continue
        for rec in by_asset.get(sig.asset_id, []):
            if sig.component_id is not None and rec.component_id is not None:
                if sig.component_id != rec.component_id:
                    continue
                basis = "SAME_ASSET_AND_COMPONENT"
            else:
                basis = "SAME_ASSET"
            associations.append(
                SignalPrognosticAssociation(
                    signal_id=sig.id, prognostic_record_id=rec.id,
                    asset_id=sig.asset_id, component_id=sig.component_id or rec.component_id,
                    basis=basis,
                )
            )
    return associations


def _correlate_component_types(
    *,
    components: list[Component],
    signals: list[ProactiveSignalRecord],
    candidates: list[HUMSDiagnosticCandidate],
    records: list[HUMSPrognosticRecord],
) -> list[ComponentTypeCorrelation]:
    """Deterministic rule: components sharing the SAME component_type AND
    (when both set) the SAME model are grouped as one population-level
    correlation entry, ONLY when more than one distinct component (i.e.
    more than one asset/installation) in that group has at least one M7
    signal, H4 candidate, or H5 record referencing it. Never asserts a
    shared root cause -- purely a same-type/model observation across the
    affected population.
    """
    by_component_id: dict[uuid.UUID, Component] = {c.id: c for c in components}

    referenced_component_ids: set[uuid.UUID] = set()
    signal_count_by_component: dict[uuid.UUID, int] = {}
    for s in signals:
        if s.component_id is not None:
            referenced_component_ids.add(s.component_id)
            signal_count_by_component[s.component_id] = signal_count_by_component.get(s.component_id, 0) + 1
    diagnostic_count_by_component: dict[uuid.UUID, int] = {}
    for c in candidates:
        if c.component_id is not None:
            referenced_component_ids.add(c.component_id)
            diagnostic_count_by_component[c.component_id] = diagnostic_count_by_component.get(c.component_id, 0) + 1
    prognostic_count_by_component: dict[uuid.UUID, int] = {}
    for r in records:
        if r.component_id is not None:
            referenced_component_ids.add(r.component_id)
            prognostic_count_by_component[r.component_id] = prognostic_count_by_component.get(r.component_id, 0) + 1

    referenced_components = [by_component_id[cid] for cid in referenced_component_ids if cid in by_component_id]

    groups: dict[tuple[str, str | None], list[Component]] = {}
    for c in referenced_components:
        key = (c.component_type, c.model)
        groups.setdefault(key, []).append(c)

    entries: list[ComponentTypeCorrelation] = []
    for (ctype, model), comps in sorted(groups.items(), key=lambda kv: (kv[0][0], kv[0][1] or "")):
        if len(comps) < 2:
            continue
        asset_ids = sorted({c.asset_id for c in comps if c.asset_id is not None}, key=str)
        entries.append(
            ComponentTypeCorrelation(
                component_type=ctype,
                model=model,
                correlated_component_count=len(comps),
                asset_ids=asset_ids,
                signal_count=sum(signal_count_by_component.get(c.id, 0) for c in comps),
                diagnostic_count=sum(diagnostic_count_by_component.get(c.id, 0) for c in comps),
                prognostic_count=sum(prognostic_count_by_component.get(c.id, 0) for c in comps),
                basis="SAME_COMPONENT_TYPE_AND_MODEL" if model else "SAME_COMPONENT_TYPE",
            )
        )
    return entries


def evaluate_fleet_hums_correlation(
    db: Session, *, organization_id: uuid.UUID
) -> FleetCorrelationSummary:
    """H8.3 entry point: correlates M7 signals + M14 population + H4
    diagnostic candidates + H5 prognostic/RUL records + H6 component
    context into a single descriptive fleet correlation. Bulk-queries
    each domain once (no per-asset loop calling any mutating service);
    the only per-asset call is a BOUNDED (<= _MAX_TWIN_LOOKUPS) read-only
    digital_twin_service.get_asset_component_tree lookup, scoped to the
    affected-asset set only -- never the whole fleet -- to avoid N+1 at
    fleet scale (see this module's H8.3 section docstring / the H8.3 spec
    escalation note on H6 scoping).
    """
    assets = list(
        db.execute(
            select(Asset).where(
                Asset.organization_id == organization_id,
                Asset.deleted_at.is_(None),
            )
        ).scalars().all()
    )
    total_fleet_assets = len(assets)

    if total_fleet_assets == 0:
        return FleetCorrelationSummary(
            availability="DATA_UNAVAILABLE",
            total_fleet_assets=0,
            affected_asset_count=0,
            affected_asset_percentage=None,
            total_active_signal_count=0,
            asset_correlations=[],
            component_correlations=[],
            signal_diagnostic_associations=[],
            signal_prognostic_associations=[],
            explanation=["No registered fleet assets found in tenant organization."],
        )

    reg_by_asset: dict[uuid.UUID, str | None] = {a.id: getattr(a, "registration", None) or a.serial_number for a in assets}
    aircraft_regs = {
        a.asset_id: a.registration
        for a in db.execute(select(Aircraft).where(Aircraft.organization_id == organization_id)).scalars().all()
        if a.asset_id
    }
    reg_by_asset.update({k: v for k, v in aircraft_regs.items() if v})

    # M7 (bulk, read-only -- reuses H8.2's own bulk-read helper).
    signal_summary = _compute_fleet_signal_summary(
        db, organization_id=organization_id, assets=assets, asset_count_for_ratio=total_fleet_assets
    )
    open_signals = list(
        db.execute(
            select(ProactiveSignalRecord).where(
                ProactiveSignalRecord.organization_id == organization_id,
                ProactiveSignalRecord.status.in_(_OPEN_SIGNAL_STATUSES),
            )
        ).scalars().all()
    )

    # H4 / H5 (bulk, read-only).
    diagnostic_candidates = _fetch_active_diagnostic_candidates(db, organization_id=organization_id)
    prognostic_records = _fetch_current_prognostic_records(db, organization_id=organization_id)

    # Components (bulk, read-only) -- used both for H8.3's own component
    # correlation and to answer H6 component-count context per asset.
    components = list(
        db.execute(select(Component).where(Component.organization_id == organization_id)).scalars().all()
    )
    components_by_asset: dict[uuid.UUID, list[Component]] = {}
    for c in components:
        if c.asset_id is not None:
            components_by_asset.setdefault(c.asset_id, []).append(c)

    # --- Affected-asset determination (deterministic: >=1 open M7 signal,
    # OR >=1 non-terminal H4 candidate, OR >=1 current H5 record). ---
    diag_by_asset: dict[uuid.UUID, list[HUMSDiagnosticCandidate]] = {}
    for c in diagnostic_candidates:
        diag_by_asset.setdefault(c.asset_id, []).append(c)
    prog_by_asset: dict[uuid.UUID, list[HUMSPrognosticRecord]] = {}
    for r in prognostic_records:
        prog_by_asset.setdefault(r.asset_id, []).append(r)
    sig_by_asset: dict[uuid.UUID, list[ProactiveSignalRecord]] = {}
    for s in open_signals:
        if s.asset_id is not None:
            sig_by_asset.setdefault(s.asset_id, []).append(s)

    affected_asset_ids = sorted(
        set(sig_by_asset) | set(diag_by_asset) | set(prog_by_asset), key=str
    )

    # --- H6 (bounded, read-only per-asset twin lookup for the affected
    # set only). ---
    twin_component_counts: dict[uuid.UUID, int] = {}
    twin_lookup_ids = affected_asset_ids[:_MAX_TWIN_LOOKUPS]
    for asset_id in twin_lookup_ids:
        try:
            with db.begin_nested():
                nodes = digital_twin_service.get_asset_component_tree(db, organization_id=organization_id, asset_id=asset_id)
                twin_component_counts[asset_id] = len(nodes)
        except Exception:
            log.warning("cross_asset.sub_query_failed", asset_id=str(asset_id), exc_info=True)
            continue

    asset_correlations: list[AssetCorrelation] = []
    for asset_id in affected_asset_ids:
        sigs = sig_by_asset.get(asset_id, [])
        diags = diag_by_asset.get(asset_id, [])
        progs = prog_by_asset.get(asset_id, [])
        highest = max((s.severity for s in sigs), key=lambda sev: _SEVERITY_RANK.get(sev, -1), default=None)
        has_rul = any(r.rul_estimate is not None for r in progs)
        component_context_available = asset_id in twin_component_counts
        component_count = twin_component_counts.get(asset_id)
        if not component_context_available:
            component_count = len(components_by_asset.get(asset_id, [])) or None

        sources_present = sum([bool(sigs), bool(diags), bool(progs)])
        if sources_present == 0:
            completeness = "INSUFFICIENT_DATA"
            note = "No M7/H4/H5 evidence available for this asset; correlation is a population-membership entry only."
        elif sources_present >= 2:
            completeness = "COMPLETE"
            note = "Multiple independent evidence sources (M7/H4/H5) available for this asset."
        else:
            completeness = "PARTIAL"
            note = "Only one evidence source (M7 signal, H4 candidate, or H5 record) available for this asset."

        asset_correlations.append(
            AssetCorrelation(
                asset_id=asset_id,
                asset_registration=reg_by_asset.get(asset_id),
                active_signal_count=len(sigs),
                highest_signal_severity=highest,
                diagnostic_candidate_count=len(diags),
                prognostic_record_count=len(progs),
                has_rul_estimate=has_rul,
                component_context_available=component_context_available,
                component_count=component_count,
                evidence_completeness=completeness,
                evidence_note=note,
            )
        )

    component_correlations = _correlate_component_types(
        components=components, signals=open_signals, candidates=diagnostic_candidates, records=prognostic_records,
    )
    signal_diagnostic_associations = _correlate_signals_to_diagnostics(open_signals, diagnostic_candidates)
    signal_prognostic_associations = _correlate_signals_to_prognostics(open_signals, prognostic_records)

    affected_pct = round((len(affected_asset_ids) / total_fleet_assets) * 100, 2) if total_fleet_assets else None

    explanation = [
        f"{len(affected_asset_ids)} of {total_fleet_assets} fleet assets have at least one associated "
        "M7 signal, H4 diagnostic candidate, or H5 prognostic record.",
        "Correlations are deterministic (same asset / same component / same component type-model) -- "
        "no new fleet health, risk, or attention score is computed by H8.3.",
    ]
    if len(affected_asset_ids) > _MAX_TWIN_LOOKUPS:
        explanation.append(
            f"Digital-twin (H6) component context was retrieved for the first {_MAX_TWIN_LOOKUPS} affected "
            f"assets only, out of {len(affected_asset_ids)} affected; remaining assets fall back to a direct "
            "component count."
        )

    return FleetCorrelationSummary(
        availability="AVAILABLE",
        total_fleet_assets=total_fleet_assets,
        affected_asset_count=len(affected_asset_ids),
        affected_asset_percentage=affected_pct,
        total_active_signal_count=len(open_signals),
        asset_correlations=asset_correlations,
        component_correlations=component_correlations,
        signal_diagnostic_associations=signal_diagnostic_associations,
        signal_prognostic_associations=signal_prognostic_associations,
        explanation=explanation,
    )


# ---------------------------------------------------------------------------
# H8.4: Fleet MRO Intelligence
#
# AGGREGATES existing H7 asset-level MRO intelligence only -- H7
# (app.services.mro_intelligence_service) remains the sole owner of
# maintenance-candidate generation, compliance-impact classification,
# readiness-impact classification, operational-impact classification, and
# conflict detection. H8.4 never recomputes any of that logic and never
# calls any H7 lifecycle mutation (generate_maintenance_candidates /
# accept_candidate / reject_candidate / review_candidate /
# defer_candidate). See module docstring and
# docs/H8_FLEET_HUMS_INTELLIGENCE.md's H8.4 section for the full reuse
# map and the critical no-inference safety boundary.
# ---------------------------------------------------------------------------


@dataclass
class MROCandidateAggregation:
    availability: str
    candidate_count: int
    by_severity: dict[str, int]
    by_type: dict[str, int]
    by_status: dict[str, int]
    affected_asset_count: int
    affected_component_count: int


@dataclass
class MROComponentCorrelation:
    component_id: uuid.UUID
    component_type: str | None
    candidate_count: int
    affected_asset_count: int
    candidate_types: list[str]


@dataclass
class MROComplianceImpactAggregation:
    availability: str
    by_impact: dict[str, int]
    evidence_missing_asset_count: int
    bounded_asset_count: int
    total_candidate_asset_count: int
    explanation: list[str]


@dataclass
class MROReadinessImpactAggregation:
    availability: str
    by_readiness_impact: dict[str, int]
    by_authoritative_readiness_state: dict[str, int]
    bounded_asset_count: int
    explanation: list[str]


@dataclass
class MROOperationalImpactAggregation:
    availability: str
    by_impact_level: dict[str, int]
    candidate_count: int


@dataclass
class MROConflictAggregation:
    availability: str
    conflict_count: int
    by_check_type: dict[str, int]
    affected_asset_count: int
    bounded_asset_count: int
    explanation: list[str]


@dataclass
class FleetMROAttentionComparisonResult:
    mro_candidate_severity_distribution: dict[str, int]
    proactive_signal_severity_distribution: dict[str, int]
    note: str


@dataclass
class HUMSOnlyAsset:
    asset_id: uuid.UUID
    asset_registration: str | None
    active_signal_count: int
    diagnostic_candidate_count: int
    prognostic_record_count: int
    has_rul_estimate: bool
    note: str


@dataclass
class FleetMROSummary:
    availability: str
    total_fleet_assets: int
    candidates: MROCandidateAggregation
    component_correlations: list[MROComponentCorrelation]
    compliance_impact: MROComplianceImpactAggregation
    readiness_impact: MROReadinessImpactAggregation
    operational_impact: MROOperationalImpactAggregation
    conflicts: MROConflictAggregation
    attention_comparison: FleetMROAttentionComparisonResult
    hums_only_assets: list[HUMSOnlyAsset]
    explanation: list[str]


def _empty_fleet_mro_summary(*, availability: str, total_fleet_assets: int, note: str) -> FleetMROSummary:
    return FleetMROSummary(
        availability=availability,
        total_fleet_assets=total_fleet_assets,
        candidates=MROCandidateAggregation(
            availability=availability, candidate_count=0, by_severity={}, by_type={}, by_status={},
            affected_asset_count=0, affected_component_count=0,
        ),
        component_correlations=[],
        compliance_impact=MROComplianceImpactAggregation(
            availability="DATA_UNAVAILABLE", by_impact={}, evidence_missing_asset_count=0,
            bounded_asset_count=0, total_candidate_asset_count=0, explanation=[note],
        ),
        readiness_impact=MROReadinessImpactAggregation(
            availability="DATA_UNAVAILABLE", by_readiness_impact={}, by_authoritative_readiness_state={},
            bounded_asset_count=0, explanation=[note],
        ),
        operational_impact=MROOperationalImpactAggregation(
            availability="DATA_UNAVAILABLE", by_impact_level={}, candidate_count=0,
        ),
        conflicts=MROConflictAggregation(
            availability="DATA_UNAVAILABLE", conflict_count=0, by_check_type={}, affected_asset_count=0,
            bounded_asset_count=0, explanation=[note],
        ),
        attention_comparison=FleetMROAttentionComparisonResult(
            mro_candidate_severity_distribution={}, proactive_signal_severity_distribution={},
            note="Two separate evidence streams; never combined into a single fleet maintenance score.",
        ),
        hums_only_assets=[],
        explanation=[note],
    )


def _aggregate_mro_candidates(
    candidates: list[MaintenanceIntelligenceCandidate],
) -> tuple[MROCandidateAggregation, list[MaintenanceIntelligenceCandidate], set[uuid.UUID]]:
    """Buckets H7's OWN persisted candidate rows by H7's OWN
    priority/candidate_type/status vocabulary. `by_status` covers ALL
    statuses (full lifecycle, reporting only -- H8.4 never transitions a
    status); `by_severity`/`by_type` are computed over the ACTIVE subset
    (OPEN/UNDER_REVIEW/DEFERRED) only, mirroring H7's own
    _list_open_candidates definition of 'currently relevant'.
    """
    by_status: dict[str, int] = {}
    by_severity: dict[str, int] = {}
    by_type: dict[str, int] = {}
    affected_assets: set[uuid.UUID] = set()
    affected_components: set[uuid.UUID] = set()
    active_candidates: list[MaintenanceIntelligenceCandidate] = []

    for c in candidates:
        by_status[c.status] = by_status.get(c.status, 0) + 1
        affected_assets.add(c.asset_id)
        if c.component_id is not None:
            affected_components.add(c.component_id)
        if c.status in _ACTIVE_CANDIDATE_STATUSES:
            by_severity[c.priority] = by_severity.get(c.priority, 0) + 1
            by_type[c.candidate_type] = by_type.get(c.candidate_type, 0) + 1
            active_candidates.append(c)

    aggregation = MROCandidateAggregation(
        availability="AVAILABLE",
        candidate_count=len(candidates),
        by_severity=by_severity,
        by_type=by_type,
        by_status=by_status,
        affected_asset_count=len(affected_assets),
        affected_component_count=len(affected_components),
    )
    return aggregation, active_candidates, affected_assets


def _correlate_mro_components(
    db: Session, *, organization_id: uuid.UUID, active_candidates: list[MaintenanceIntelligenceCandidate]
) -> list[MROComponentCorrelation]:
    """Aggregates ACTIVE candidates by component_id -- descriptive only
    ('associated with N existing MRO intelligence candidates'), never
    'defective'/'failed' language."""
    by_component: dict[uuid.UUID, list[MaintenanceIntelligenceCandidate]] = {}
    for c in active_candidates:
        if c.component_id is not None:
            by_component.setdefault(c.component_id, []).append(c)
    if not by_component:
        return []

    components = list(
        db.execute(
            select(Component).where(
                Component.organization_id == organization_id,
                Component.id.in_(by_component.keys()),
            )
        ).scalars().all()
    )
    component_by_id = {c.id: c for c in components}

    entries: list[MROComponentCorrelation] = []
    for component_id, cands in sorted(by_component.items(), key=lambda kv: str(kv[0])):
        comp = component_by_id.get(component_id)
        entries.append(
            MROComponentCorrelation(
                component_id=component_id,
                component_type=comp.component_type if comp else None,
                candidate_count=len(cands),
                affected_asset_count=len({c.asset_id for c in cands}),
                candidate_types=sorted({c.candidate_type for c in cands}),
            )
        )
    return entries


def _aggregate_mro_compliance_impact(
    db: Session, *, organization_id: uuid.UUID, bounded_asset_ids: list[uuid.UUID], total_candidate_asset_count: int
) -> MROComplianceImpactAggregation:
    """Bounded per-asset calls to H7's OWN get_compliance_impact (no bulk
    path exists on H7's compliance model today -- ComplianceObligation
    carries no persisted 'impact' field to bulk-read directly). Preserves
    H7's EVIDENCE_MISSING (UNKNOWN) semantics exactly -- never folded into
    NON_COMPLIANT."""
    if not bounded_asset_ids:
        return MROComplianceImpactAggregation(
            availability="AVAILABLE", by_impact={}, evidence_missing_asset_count=0,
            bounded_asset_count=0, total_candidate_asset_count=total_candidate_asset_count,
            explanation=["No assets with active MRO candidates; compliance impact aggregation is empty."],
        )

    by_impact: dict[str, int] = {}
    evidence_missing = 0
    for asset_id in bounded_asset_ids:
        try:
            with db.begin_nested():
                result = mro_intelligence_service.get_compliance_impact(db, organization_id=organization_id, asset_id=asset_id)
        except Exception:
            log.warning("cross_asset.sub_query_failed", asset_id=str(asset_id), exc_info=True)
            continue
        by_impact[result.overall_impact] = by_impact.get(result.overall_impact, 0) + 1
        if result.overall_impact == "UNKNOWN":
            evidence_missing += 1

    explanation = [
        f"Compliance impact aggregated over {len(bounded_asset_ids)} asset(s) with active H7 MRO candidates "
        "via H7's own get_compliance_impact (per-asset, bounded)."
    ]
    if total_candidate_asset_count > len(bounded_asset_ids):
        explanation.append(
            f"Bounded to the first {_MAX_MRO_PER_ASSET_LOOKUPS} candidate-bearing assets out of "
            f"{total_candidate_asset_count} to avoid N+1 at fleet scale."
        )

    return MROComplianceImpactAggregation(
        availability="AVAILABLE", by_impact=by_impact, evidence_missing_asset_count=evidence_missing,
        bounded_asset_count=len(bounded_asset_ids), total_candidate_asset_count=total_candidate_asset_count,
        explanation=explanation,
    )


def _aggregate_mro_readiness_impact(
    db: Session, *, organization_id: uuid.UUID, bounded_asset_ids: list[uuid.UUID], total_candidate_asset_count: int
) -> MROReadinessImpactAggregation:
    """Bounded per-asset calls to H7's OWN get_readiness_impact. Keeps
    authoritative readiness_state and H7's readiness_impact as two
    SEPARATE distributions -- never merged, mirroring H7's own
    ReadinessImpactResult convention and AssetMROIntelligence's pattern."""
    if not bounded_asset_ids:
        return MROReadinessImpactAggregation(
            availability="AVAILABLE", by_readiness_impact={}, by_authoritative_readiness_state={},
            bounded_asset_count=0,
            explanation=["No assets with active MRO candidates; readiness impact aggregation is empty."],
        )

    by_readiness_impact: dict[str, int] = {}
    by_authoritative: dict[str, int] = {}
    for asset_id in bounded_asset_ids:
        try:
            with db.begin_nested():
                result = mro_intelligence_service.get_readiness_impact(db, organization_id=organization_id, asset_id=asset_id)
        except Exception:
            log.warning("cross_asset.sub_query_failed", asset_id=str(asset_id), exc_info=True)
            continue
        by_readiness_impact[result.readiness_impact] = by_readiness_impact.get(result.readiness_impact, 0) + 1
        by_authoritative[result.authoritative_readiness_state] = by_authoritative.get(result.authoritative_readiness_state, 0) + 1

    explanation = [
        f"Readiness impact aggregated over {len(bounded_asset_ids)} asset(s) with active H7 MRO candidates "
        "via H7's own get_readiness_impact (per-asset, bounded). Authoritative readiness_state and H7's "
        "readiness_impact classification are reported as separate distributions, never merged into one "
        "fleet readiness score."
    ]
    if total_candidate_asset_count > len(bounded_asset_ids):
        explanation.append(
            f"Bounded to the first {_MAX_MRO_PER_ASSET_LOOKUPS} candidate-bearing assets out of "
            f"{total_candidate_asset_count} to avoid N+1 at fleet scale."
        )

    return MROReadinessImpactAggregation(
        availability="AVAILABLE", by_readiness_impact=by_readiness_impact,
        by_authoritative_readiness_state=by_authoritative, bounded_asset_count=len(bounded_asset_ids),
        explanation=explanation,
    )


def _aggregate_mro_operational_impact(active_candidates: list[MaintenanceIntelligenceCandidate]) -> MROOperationalImpactAggregation:
    """Counts H7's OWN persisted candidate.operational_impact field --
    never a per-asset H7 call, never an independent optimization score.
    H7 currently sets this field to None at candidate creation (see
    mro_intelligence_service.generate_maintenance_candidates); those rows
    are bucketed 'NOT_SET' rather than silently dropped or assumed LOW."""
    by_impact_level: dict[str, int] = {}
    for c in active_candidates:
        level = c.operational_impact or "NOT_SET"
        by_impact_level[level] = by_impact_level.get(level, 0) + 1
    return MROOperationalImpactAggregation(
        availability="AVAILABLE", by_impact_level=by_impact_level, candidate_count=len(active_candidates),
    )


def _aggregate_mro_conflicts(
    db: Session, *, organization_id: uuid.UUID, bounded_asset_ids: list[uuid.UUID], total_candidate_asset_count: int
) -> MROConflictAggregation:
    """Bounded per-asset calls to H7's OWN detect_conflicts (no bulk path
    exists -- conflicts are computed, not persisted). Reports only; never
    auto-resolves a conflict."""
    if not bounded_asset_ids:
        return MROConflictAggregation(
            availability="AVAILABLE", conflict_count=0, by_check_type={}, affected_asset_count=0,
            bounded_asset_count=0, explanation=["No assets with active MRO candidates; conflict aggregation is empty."],
        )

    by_check_type: dict[str, int] = {}
    affected_assets: set[uuid.UUID] = set()
    total_conflicts = 0
    for asset_id in bounded_asset_ids:
        try:
            with db.begin_nested():
                conflicts = mro_intelligence_service.detect_conflicts(db, organization_id=organization_id, asset_id=asset_id)
        except Exception:
            log.warning("cross_asset.sub_query_failed", asset_id=str(asset_id), exc_info=True)
            continue
        if conflicts:
            affected_assets.add(asset_id)
        for conflict in conflicts:
            by_check_type[conflict.check] = by_check_type.get(conflict.check, 0) + 1
            total_conflicts += 1

    explanation = [
        f"Conflicts aggregated over {len(bounded_asset_ids)} asset(s) with active H7 MRO candidates via H7's "
        "own detect_conflicts (per-asset, bounded). Conflicts are reported only -- never auto-resolved."
    ]
    if total_candidate_asset_count > len(bounded_asset_ids):
        explanation.append(
            f"Bounded to the first {_MAX_MRO_PER_ASSET_LOOKUPS} candidate-bearing assets out of "
            f"{total_candidate_asset_count} to avoid N+1 at fleet scale."
        )

    return MROConflictAggregation(
        availability="AVAILABLE", conflict_count=total_conflicts, by_check_type=by_check_type,
        affected_asset_count=len(affected_assets), bounded_asset_count=len(bounded_asset_ids),
        explanation=explanation,
    )


def _identify_hums_only_assets(
    *, correlation: FleetCorrelationSummary, all_candidate_asset_ids: set[uuid.UUID]
) -> list[HUMSOnlyAsset]:
    """THE critical H8.4 safety boundary: an asset with M7/H4/H5 evidence
    (per H8.3's own deterministic correlation) but NO H7
    MaintenanceIntelligenceCandidate of ANY status (open or otherwise) is
    reported here as HUMS context ONLY. H8.4 never creates, infers, or
    implies that a maintenance candidate exists for these assets -- it
    only surfaces H8.3's own already-computed evidence counts, verbatim.
    """
    entries: list[HUMSOnlyAsset] = []
    for asset_corr in correlation.asset_correlations:
        if asset_corr.asset_id in all_candidate_asset_ids:
            continue
        entries.append(
            HUMSOnlyAsset(
                asset_id=asset_corr.asset_id,
                asset_registration=asset_corr.asset_registration,
                active_signal_count=asset_corr.active_signal_count,
                diagnostic_candidate_count=asset_corr.diagnostic_candidate_count,
                prognostic_record_count=asset_corr.prognostic_record_count,
                has_rul_estimate=asset_corr.has_rul_estimate,
                note=(
                    "No H7 maintenance intelligence candidate exists for this asset. HUMS signal/diagnostic/"
                    "prognostic evidence is reported for context only; no maintenance candidate is implied."
                ),
            )
        )
    return entries


def evaluate_fleet_mro_aggregation(db: Session, *, organization_id: uuid.UUID) -> FleetMROSummary:
    """H8.4 entry point: aggregates H7's own persisted
    MaintenanceIntelligenceCandidate rows (bulk query) composed with H7's
    own compliance/readiness/operational-impact/conflict read functions
    (bounded per-asset, mirroring H8.3's twin-lookup cap) and H8.3's own
    fleet correlation (for the no-inference safety boundary). Read-only --
    never calls generate_maintenance_candidates / accept_candidate /
    reject_candidate / review_candidate / defer_candidate.
    """
    assets = list(
        db.execute(
            select(Asset).where(
                Asset.organization_id == organization_id,
                Asset.deleted_at.is_(None),
            )
        ).scalars().all()
    )
    total_fleet_assets = len(assets)

    if total_fleet_assets == 0:
        return _empty_fleet_mro_summary(
            availability="DATA_UNAVAILABLE", total_fleet_assets=0,
            note="No registered fleet assets found in tenant organization.",
        )

    candidates = list(
        db.execute(
            select(MaintenanceIntelligenceCandidate).where(
                MaintenanceIntelligenceCandidate.organization_id == organization_id,
            )
        ).scalars().all()
    )

    candidate_agg, active_candidates, all_candidate_asset_ids = _aggregate_mro_candidates(candidates)
    component_correlations = _correlate_mro_components(db, organization_id=organization_id, active_candidates=active_candidates)

    active_asset_ids = sorted({c.asset_id for c in active_candidates}, key=str)
    bounded_asset_ids = active_asset_ids[:_MAX_MRO_PER_ASSET_LOOKUPS]

    compliance_impact = _aggregate_mro_compliance_impact(
        db, organization_id=organization_id, bounded_asset_ids=bounded_asset_ids,
        total_candidate_asset_count=len(active_asset_ids),
    )
    readiness_impact = _aggregate_mro_readiness_impact(
        db, organization_id=organization_id, bounded_asset_ids=bounded_asset_ids,
        total_candidate_asset_count=len(active_asset_ids),
    )
    operational_impact = _aggregate_mro_operational_impact(active_candidates)
    conflicts = _aggregate_mro_conflicts(
        db, organization_id=organization_id, bounded_asset_ids=bounded_asset_ids,
        total_candidate_asset_count=len(active_asset_ids),
    )

    # M7 attention distribution, reused as-is (H8.2) -- kept as a SEPARATE
    # evidence stream from H7's own candidate severity distribution; never
    # combined into a single fleet maintenance priority/risk/urgency score.
    signal_summary = _compute_fleet_signal_summary(
        db, organization_id=organization_id, assets=assets, asset_count_for_ratio=total_fleet_assets
    )
    attention_comparison = FleetMROAttentionComparisonResult(
        mro_candidate_severity_distribution=dict(candidate_agg.by_severity),
        proactive_signal_severity_distribution=dict(signal_summary.severity_distribution),
        note=(
            "Two separate evidence streams (H7 MRO candidate priority distribution and M7 proactive signal "
            "severity distribution) -- H8.4 does not compute a combined fleet maintenance priority/risk/"
            "urgency score."
        ),
    )

    # H8.3 correlation, reused as-is, for the no-inference safety boundary.
    correlation = evaluate_fleet_hums_correlation(db, organization_id=organization_id)
    hums_only_assets = _identify_hums_only_assets(correlation=correlation, all_candidate_asset_ids=all_candidate_asset_ids)

    explanation = [
        f"{candidate_agg.candidate_count} MRO intelligence candidate(s) across {candidate_agg.affected_asset_count} "
        f"of {total_fleet_assets} fleet asset(s), aggregated from H7's own MaintenanceIntelligenceCandidate table.",
        "Compliance/readiness/operational-impact/conflict aggregation reuses H7's own read functions verbatim -- "
        "H8.4 introduces no new compliance, readiness, operational, or conflict logic.",
        f"{len(hums_only_assets)} asset(s) have M7/H4/H5 HUMS evidence but no H7 MRO candidate; reported as "
        "context only, never as an implied maintenance requirement.",
    ]

    return FleetMROSummary(
        availability="AVAILABLE",
        total_fleet_assets=total_fleet_assets,
        candidates=candidate_agg,
        component_correlations=component_correlations,
        compliance_impact=compliance_impact,
        readiness_impact=readiness_impact,
        operational_impact=operational_impact,
        conflicts=conflicts,
        attention_comparison=attention_comparison,
        hums_only_assets=hums_only_assets,
        explanation=explanation,
    )
