"""D2.2 Aerospace Intelligence & Decision Layer -- readiness and risk schemas.

These schemas are pure aggregation/derived views. Nothing here is persisted;
every field is computed on read from authoritative Developer 1 / D2.1 / D2.3
records (see app/services/intelligence/readiness_intelligence_service.py and
risk_intelligence_service.py for the source logic and the domain invariants
those modules enforce).
"""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from app.schemas.aerospace_state import IntelligenceBlocker, IntelligenceWarning

ReadinessState = Literal["READY", "BLOCKED", "UNKNOWN"]
RiskLevel = Literal["CRITICAL", "HIGH", "MEDIUM", "LOW", "UNKNOWN"]
KleeneFactorValue = Literal["TRUE", "FALSE", "UNKNOWN"]
BlockerSourceDomain = Literal["AEROSPACE_STATE", "WORK_ORDER", "DEPLOYMENT"]

# Priority reuses the exact RiskLevel vocabulary rather than inventing a
# second CRITICAL/HIGH/MEDIUM/LOW tier system -- the repository has no
# pre-existing priority enum (WorkOrder/PartRequirement/ComplianceObligation
# .priority are all free-form strings with inconsistent defaults), so the
# only real precedent to build on is D2.2's own Pass-1 risk tier vocabulary.
PriorityLevel = RiskLevel

# Decision states answer a different question ("what should happen next")
# than intelligence state (NOMINAL/.../UNKNOWN_INTEL, "what is true") or
# risk/priority tier ("how severe") -- so this is a third, deliberately
# distinct vocabulary, not a competing restatement of either upstream one.
DecisionState = Literal[
    "INSUFFICIENT_DATA",
    "IMMEDIATE_ACTION_REQUIRED",
    "ACTION_REQUIRED",
    "MONITOR",
    "NO_ACTION_REQUIRED",
]


class ReadinessIntelligenceBlocker(BaseModel):
    """One unified blocker, normalized from whichever authoritative domain
    service produced it (compliance intelligence, release readiness, drone
    deployment readiness). Never a new fact -- always a pointer back to the
    source record that already exists in that domain.
    """

    source_domain: BlockerSourceDomain
    category: str
    description: str
    related_record_id: uuid.UUID | None = None
    related_record_type: str | None = None
    # Populated only for AEROSPACE_STATE-domain blockers, carried forward
    # verbatim from D2.1's own IntelligenceBlocker (app/schemas/
    # aerospace_state.py) -- never fabricated. WORK_ORDER/DEPLOYMENT-domain
    # blockers (release_readiness_service.Blocker, and the drone deployment
    # readiness blocker strings) carry no such authoritative action field in
    # their own source schema, so these stay None there; `description` is
    # the only guidance available for those two domains.
    required_action: str | None = None
    resolution_action: str | None = None
    regulatory_reference: str | None = None


class AssetReadinessIntelligence(BaseModel):
    """Explainable, asset-level synthesis of readiness across compliance,
    open work orders, and (for drones) deployment readiness. Never a second
    readiness engine -- every blocker traces to Developer 1's or D2.3's own
    readiness/compliance services; this layer only aggregates and explains.
    """

    asset_id: uuid.UUID
    aircraft_id: uuid.UUID | None = None
    operational_state: str
    readiness_state: ReadinessState
    blockers: list[ReadinessIntelligenceBlocker] = []
    contributing_factors: dict[str, int | str] = {}
    explanation: list[str] = []
    data_completeness: str
    evaluated_at: datetime


class RiskFactor(BaseModel):
    """One deterministic risk input, expressed in Kleene tri-state terms so
    that "we don't have enough data to know" is never silently treated as
    "not a risk" (UNKNOWN != FALSE, see
    app/services/applicability/kleene.py).
    """

    name: str
    value: KleeneFactorValue
    explanation: str


class AssetRiskIntelligence(BaseModel):
    """Deterministic, explainable risk assessment for an asset, derived
    entirely from AssetReadinessIntelligence and countable domain facts.
    Never a numeric score invented without a documented model -- see
    app/services/intelligence/risk_intelligence_service.py's module
    docstring for the exact rule table.
    """

    asset_id: uuid.UUID
    risk_level: RiskLevel
    readiness_state: ReadinessState
    factors: list[RiskFactor] = []
    contributing_counts: dict[str, int] = {}
    explanation: list[str] = []
    evaluated_at: datetime


class IntelligenceWarningRef(BaseModel):
    """A non-blocking intelligence concern surfaced for traceability, flattened
    from the D2-4 IntelligenceWarning contract
    (app/schemas/aerospace_state.py) -- read-only passthrough, never a new
    warning source.
    """

    warning_id: str
    category: str
    dimension: str
    message: str
    source_type: str | None = None
    source_id: uuid.UUID | None = None
    source_label: str | None = None


class AssetPriorityIntelligence(BaseModel):
    """Deterministic priority grading for an asset, derived from
    AssetRiskIntelligence plus blocker/warning breadth. See
    app/services/intelligence/priority_intelligence_service.py's module
    docstring for the exact rule table. Never a numeric score -- priority
    reuses the same bounded CRITICAL/HIGH/MEDIUM/LOW/UNKNOWN vocabulary as
    risk (see PriorityLevel).
    """

    asset_id: uuid.UUID
    aircraft_id: uuid.UUID | None = None
    priority_level: PriorityLevel
    risk_level: RiskLevel
    readiness_state: ReadinessState
    escalated: bool
    blocker_count: int
    distinct_blocker_domains: int
    warning_count: int
    blockers: list[ReadinessIntelligenceBlocker] = []
    warnings: list[IntelligenceWarningRef] = []
    explanation: list[str] = []
    evaluated_at: datetime


class AssetDecision(BaseModel):
    """Deterministic decision-support state for an asset -- NOT an
    autonomous action and NOT a recommendation (that is D2.2 Pass 3). See
    app/services/intelligence/decision_service.py's module docstring for the
    exact rule table. Answers "what decision state follows from the current
    priority/readiness/risk picture," never "what specific action to take."
    """

    asset_id: uuid.UUID
    aircraft_id: uuid.UUID | None = None
    decision_state: DecisionState
    decision_reason: str
    priority_level: PriorityLevel
    risk_level: RiskLevel
    readiness_state: ReadinessState
    required_information: list[str] = []
    blockers: list[ReadinessIntelligenceBlocker] = []
    warnings: list[IntelligenceWarningRef] = []
    explanation: list[str] = []
    evaluated_at: datetime


# Reuses the exact "NO_ACTION_REQUIRED" literal already established by
# app/models/finding.py's DispositionType (CORRECTIVE_ACTION/
# NO_ACTION_REQUIRED/DEFERRED) and by DecisionState -- the only other
# categories are grounded directly in what a source blocker either does or
# does not carry: an authoritative required_action (PERFORM_REQUIRED_ACTION)
# versus none (RESOLVE_BLOCKER, falling back to the blocker's own
# description), plus the two non-blocker decision branches
# (OBTAIN_MISSING_INFORMATION for INSUFFICIENT_DATA, MONITOR_CONDITION for
# MONITOR warnings).
RecommendationActionCategory = Literal[
    "OBTAIN_MISSING_INFORMATION",
    "PERFORM_REQUIRED_ACTION",
    "RESOLVE_BLOCKER",
    "MONITOR_CONDITION",
    "NO_ACTION_REQUIRED",
]


class RecommendationItem(BaseModel):
    """One deterministic, advisory next step. `action` and
    `resolution_condition` are never invented -- see
    app/services/intelligence/recommendation_service.py's module docstring
    for exactly which source field each is copied from.
    """

    action_category: RecommendationActionCategory
    action: str
    resolution_condition: str | None = None
    source_blocker: ReadinessIntelligenceBlocker | None = None


class AssetRecommendation(BaseModel):
    """Advisory, non-autonomous recommendation for an asset, derived
    entirely from AssetDecision (this is D2.2 Pass 3 -- the final stage
    before human action / future AI explanation). Never mutates operational,
    compliance, evidence, or readiness state; never invents an action a
    source record does not already establish.
    """

    asset_id: uuid.UUID
    aircraft_id: uuid.UUID | None = None
    recommendation_state: DecisionState
    priority_level: PriorityLevel
    risk_level: RiskLevel
    readiness_state: ReadinessState
    items: list[RecommendationItem] = []
    required_information: list[str] = []
    blockers: list[ReadinessIntelligenceBlocker] = []
    warnings: list[IntelligenceWarningRef] = []
    explanation: list[str] = []
    evaluated_at: datetime


class FleetAssetIntelligence(BaseModel):
    """One asset's intelligence summary within a fleet-wide view (M4.2).

    Every field here is copied from the same per-asset readiness/risk/
    priority/decision/recommendation services Pass 1-3 already expose
    individually -- this is a fleet-scoped aggregation of their existing
    output, not a sixth intelligence engine. See
    app/services/intelligence/fleet_intelligence_service.py.
    """

    asset_id: uuid.UUID
    registration: str | None = None
    asset_type: str
    operational_state: str
    aerospace_intelligence_status: str
    readiness_state: ReadinessState
    risk_level: RiskLevel
    priority_level: PriorityLevel
    decision_state: DecisionState
    decision_reason: str
    top_recommendation_action: str | None = None
    blocker_count: int
    warning_count: int
    blockers: list[ReadinessIntelligenceBlocker] = []
    warnings: list[IntelligenceWarningRef] = []
    evaluated_at: datetime


class FleetIntelligenceSummary(BaseModel):
    """Fleet-wide intelligence view -- one row per tenant asset. Read-only,
    derived entirely from existing per-asset D2.2 services; no new
    persistence, no new intelligence rules.
    """

    total_assets: int
    assets: list[FleetAssetIntelligence] = []
    evaluated_at: datetime


# ---------------------------------------------------------------------------
# M4.5 -- Intelligence Context Contract
# ---------------------------------------------------------------------------
#
# IntelligenceContext is a read-only projection of deterministic aerospace
# intelligence. It does not create, override, or reinterpret aerospace
# truth. It is a pure composition of six existing read-only service calls
# (evaluate_aerospace_intelligence_state, get_asset_readiness_intelligence,
# get_asset_risk_intelligence, get_asset_priority_intelligence,
# get_asset_decision, get_asset_recommendation) -- zero new domain queries,
# zero new intelligence rules. See
# app/services/intelligence/context_service.py.
#
# The aerospace_state section reuses D2.1's own IntelligenceBlocker/
# IntelligenceWarning types verbatim (not the D2.2-flattened
# ReadinessIntelligenceBlocker) because those are the only place
# blocker_id/what_condition survive -- D2.2's own flattening (Pass 1,
# readiness_intelligence_service.py) drops both when it maps into
# ReadinessIntelligenceBlocker. Reusing the existing type rather than
# inventing a parallel one satisfies "use the repository's actual contract
# rather than inventing a parallel vocabulary."


class IntelligenceTenantContext(BaseModel):
    organization_id: uuid.UUID


class IntelligenceAssetContext(BaseModel):
    asset_id: uuid.UUID
    aircraft_id: uuid.UUID | None = None
    asset_type: str
    registration: str | None = None
    operational_state: str


class IntelligenceAerospaceStateContext(BaseModel):
    """Verbatim D2.1 output -- full traceability detail (blocker_id,
    what_condition) that D2.2's own flattened blockers do not carry.
    """

    status: str
    blockers: list[IntelligenceBlocker] = []
    warnings: list[IntelligenceWarning] = []
    evaluation_version: str
    disclaimer: str


class IntelligenceReadinessContext(BaseModel):
    state: ReadinessState
    blockers: list[ReadinessIntelligenceBlocker] = []
    data_completeness: str


class IntelligenceRiskContext(BaseModel):
    level: RiskLevel
    factors: list[RiskFactor] = []


class IntelligencePriorityContext(BaseModel):
    level: PriorityLevel
    escalated: bool
    rationale: list[str] = []


class IntelligenceDecisionContext(BaseModel):
    state: DecisionState
    rationale: str
    required_information: list[str] = []


class IntelligenceRecommendationContext(BaseModel):
    state: DecisionState
    items: list[RecommendationItem] = []


class IntelligenceContext(BaseModel):
    """M4.5 -- the formal, versioned, read-only handoff contract from the
    deterministic intelligence chain (D1 -> D2.1 -> D2.2) to the future
    Kota Intelligence / AI Assistant (M5). The AI consumes this contract to
    explain, summarize, answer, navigate, and present -- it must never
    determine compliance, applicability, airworthiness, readiness, risk,
    priority, decision, or recommendation itself. Those five sections below
    are always the deterministic backend's own conclusions, copied here
    unchanged.
    """

    contract_version: str = "1.0"
    generated_at: datetime
    tenant: IntelligenceTenantContext
    asset: IntelligenceAssetContext
    aerospace_state: IntelligenceAerospaceStateContext
    readiness: IntelligenceReadinessContext
    risk: IntelligenceRiskContext
    priority: IntelligencePriorityContext
    decision: IntelligenceDecisionContext
    recommendation: IntelligenceRecommendationContext
    # Explicit, always-present (possibly empty) list of what remains
    # unresolved across every section -- UNKNOWN/UNKNOWN_INTEL/
    # INSUFFICIENT_DATA conditions are surfaced here, never silently
    # resolved into a positive conclusion.
    uncertainty: list[str] = []
