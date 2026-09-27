"""Aerospace Intelligence State Schemas — D2-4.

This module defines the **stable contract boundary** between Developer 2.1
(Aerospace State Engine) and Developer 2.2 (Readiness / Risk / Decision /
AI presentation).

Design principles:
- Deterministic: same source data → same output. No LLM, no probability.
- Traceable: every intelligence conclusion carries source record provenance.
- Unknown ≠ False: UNKNOWN/INSUFFICIENT_DATA is never silently collapsed to
  NOT_APPLICABLE or READY (Invariant #23).
- No readiness scoring, no risk scoring, no decision recommendations —
  those belong to Developer 2.2.
- No duplicate operational state — operational truth comes from Developer 1's
  compute_operational_state (asset_service.py).

Intelligence State Vocabulary (D2-4):
    NOMINAL          — all intelligence dimensions are clean; no blockers.
    DEGRADED         — at least one warning present but no hard blockers.
    RESTRICTED       — one or more intelligence conditions restrict operations
                       (compliance, evidence, inspection, finding blockers).
    GROUNDED_INTEL   — intelligence confirms an operational grounding condition
                       (AOG, GROUNDED, or critical unresolved compliance state).
    UNKNOWN_INTEL    — insufficient data to determine intelligence state;
                       MUST NOT be treated as NOMINAL.

These labels are intelligence interpretations of operational facts and
compliance state — they are deliberately distinct from Developer 1's
operational state vocabulary (AVAILABLE / MAINTENANCE / AOG / etc.) to
prevent confusion between operational fact and intelligence interpretation.
"""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Intelligence State Vocabulary
# ---------------------------------------------------------------------------

class AerospaceIntelligenceStatus:
    """Controlled vocabulary for Aerospace Intelligence State.

    Separated from Developer 1's operational state vocabulary by design.
    Developer 2.2 must consume these as intelligence facts, not operational
    commands.
    """
    NOMINAL = "NOMINAL"              # No intelligence blockers or warnings
    DEGRADED = "DEGRADED"            # Warnings present; no hard blockers
    RESTRICTED = "RESTRICTED"        # Intelligence conditions restrict operations
    GROUNDED_INTEL = "GROUNDED_INTEL"  # Intelligence confirms grounding condition
    UNKNOWN_INTEL = "UNKNOWN_INTEL"  # Insufficient data; must not be treated as NOMINAL


# ---------------------------------------------------------------------------
# Intelligence Dimension vocabulary
# ---------------------------------------------------------------------------

class IntelligenceDimensionStatus:
    """Status per intelligence dimension."""
    CLEAR = "CLEAR"                  # Dimension is fully resolved; no issues
    WARNING = "WARNING"              # Non-blocking concern
    RESTRICTED = "RESTRICTED"        # Hard blocker present in this dimension
    UNKNOWN = "UNKNOWN"              # Insufficient data for determination


# ---------------------------------------------------------------------------
# Blocker / Warning Categories
# ---------------------------------------------------------------------------

class IntelligenceBlockerCategory:
    """Controlled vocabulary for intelligence blocker categories."""
    # Compliance-derived
    NON_COMPLIANT_OBLIGATION = "NON_COMPLIANT_OBLIGATION"
    OVERDUE_OBLIGATION = "OVERDUE_OBLIGATION"
    BLOCKED_OBLIGATION = "BLOCKED_OBLIGATION"
    REVIEW_REQUIRED_OBLIGATION = "REVIEW_REQUIRED_OBLIGATION"
    # Evidence-derived
    MISSING_EVIDENCE = "MISSING_EVIDENCE"
    REJECTED_EVIDENCE = "REJECTED_EVIDENCE"
    UNVERIFIED_EVIDENCE = "UNVERIFIED_EVIDENCE"
    # Inspection-derived
    FAILED_INSPECTION = "FAILED_INSPECTION"
    PENDING_RII = "PENDING_RII"
    INCOMPLETE_INSPECTION = "INCOMPLETE_INSPECTION"
    # Finding-derived
    CRITICAL_FINDING = "CRITICAL_FINDING"
    MAJOR_FINDING = "MAJOR_FINDING"
    SAFETY_SIGNIFICANT_FINDING = "SAFETY_SIGNIFICANT_FINDING"
    # Applicability-derived
    INSUFFICIENT_APPLICABILITY_DATA = "INSUFFICIENT_APPLICABILITY_DATA"
    # Operational context
    OPERATIONAL_GROUNDING = "OPERATIONAL_GROUNDING"   # AOG/GROUNDED from Dev 1
    LIFECYCLE_RESTRICTION = "LIFECYCLE_RESTRICTION"   # RETIRED/INACTIVE


# ---------------------------------------------------------------------------
# Intelligence Traceability
# ---------------------------------------------------------------------------

class IntelligenceSourceRef(BaseModel):
    """Provenance reference linking an intelligence conclusion to a source record."""

    source_type: str
    """Type of source record: ComplianceObligation, Finding, InspectionRequirement,
    Evidence, ApplicabilityEvaluation, RegulatoryRequirement, Asset, Mission."""

    source_id: uuid.UUID
    """Primary key of the source record."""

    source_label: str | None = None
    """Human-readable label for the source record (requirement number, finding title, etc.)."""


class IntelligenceBlocker(BaseModel):
    """An explicit, explainable intelligence condition that restricts the asset.

    Answers all 13-point explainability questions:
    1. what_condition:        What is wrong?
    2. why_condition:         Why is it a blocker?
    3. category:              Classification of the blocker.
    4. dimension:             Which intelligence dimension raised this.
    5. source_ref:            Source record provenance.
    6. regulatory_ref_number: Which regulation / AD / SB.
    7. regulatory_ref_title:  Regulatory requirement title.
    8. required_action:       What action is needed.
    9. resolution_action:     Specific step to resolve this blocker.
    10. missing_evidence_desc: Description of required evidence if applicable.
    11. asset_id:             Which asset.
    12. aircraft_id:          Which aircraft (if applicable).
    13. blocker_id:           Unique stable identifier for this blocker.
    """

    blocker_id: str
    category: str
    dimension: str  # COMPLIANCE, EVIDENCE, INSPECTION, FINDING, APPLICABILITY, OPERATIONAL
    what_condition: str
    why_condition: str
    source_ref: IntelligenceSourceRef
    regulatory_ref_number: str | None = None
    regulatory_ref_title: str | None = None
    required_action: str | None = None
    resolution_action: str
    missing_evidence_desc: str | None = None
    asset_id: uuid.UUID | None = None
    aircraft_id: uuid.UUID | None = None


class IntelligenceWarning(BaseModel):
    """A non-blocking intelligence concern (does not restrict operations alone)."""

    warning_id: str
    category: str
    dimension: str
    message: str
    source_ref: IntelligenceSourceRef | None = None


# ---------------------------------------------------------------------------
# Per-Dimension Intelligence Summaries
# ---------------------------------------------------------------------------

class OperationalIntelligenceDimension(BaseModel):
    """Developer 1's operational state as consumed by the intelligence layer.

    This does NOT duplicate or replace Developer 1's engine. It records the
    operational state fact as observed by the intelligence system.
    """
    status: str  # CLEAR | WARNING | RESTRICTED | UNKNOWN
    operational_state: str
    """Verbatim value from compute_operational_state:
    AVAILABLE | IN_MISSION | UNDER_INSPECTION | MAINTENANCE | GROUNDED | AOG | INACTIVE | RETIRED."""
    lifecycle_status: str
    summary: str


class ComplianceIntelligenceDimension(BaseModel):
    """Compliance intelligence dimension derived from D2-1 / D2-2."""
    status: str  # CLEAR | WARNING | RESTRICTED | UNKNOWN
    obligations_total: int = 0
    obligations_compliant: int = 0
    obligations_non_compliant: int = 0
    obligations_overdue: int = 0
    obligations_blocked: int = 0
    obligations_review_required: int = 0
    summary: str


class EvidenceIntelligenceDimension(BaseModel):
    """Evidence intelligence dimension derived from D2-2."""
    status: str  # CLEAR | WARNING | RESTRICTED | UNKNOWN
    evidence_total: int = 0
    evidence_accepted: int = 0
    evidence_missing: int = 0
    evidence_rejected: int = 0
    evidence_unverified: int = 0
    summary: str


class InspectionIntelligenceDimension(BaseModel):
    """Inspection intelligence dimension derived from D2-3."""
    status: str  # CLEAR | WARNING | RESTRICTED | UNKNOWN
    inspections_total: int = 0
    inspections_completed: int = 0
    inspections_pending: int = 0
    inspections_rejected: int = 0
    rii_pending: int = 0
    summary: str


class FindingIntelligenceDimension(BaseModel):
    """Finding intelligence dimension derived from D2-3."""
    status: str  # CLEAR | WARNING | RESTRICTED | UNKNOWN
    findings_open: int = 0
    findings_critical: int = 0
    findings_major: int = 0
    findings_minor: int = 0
    findings_closed: int = 0
    summary: str


# ---------------------------------------------------------------------------
# Core Aerospace Intelligence State Contract
# ---------------------------------------------------------------------------

class AerospaceIntelligenceState(BaseModel):
    """The Aerospace Intelligence State — D2-4 primary output contract.

    This is the stable interface Developer 2.2 (Readiness / Risk / Decision / AI)
    must consume. Developer 2.2 MUST NOT query Developer 2.1's private tables
    directly; it must consume this contract.

    This contract:
    - Consumes Developer 1's operational state (operational_dimension)
    - Consumes D2-1 applicability (embedded in compliance_dimension)
    - Consumes D2-2 compliance + evidence (compliance_dimension, evidence_dimension)
    - Consumes D2-3 inspection + finding intelligence (inspection_dimension, finding_dimension)
    - Derives a deterministic aerospace_intelligence_status
    - Exposes full blocker explainability (13-point)
    - Exposes source record traceability

    What this contract does NOT contain:
    - Readiness scores (Developer 2.2)
    - Risk scores (Developer 2.2)
    - Recommendations (Developer 2.2)
    - Decision logic (Developer 2.2)
    - AI-generated narrative (Developer 2.2)
    """

    model_config = ConfigDict(from_attributes=True)

    # Identity
    asset_id: uuid.UUID
    aircraft_id: uuid.UUID | None = None
    asset_type: str
    registration: str | None = None

    # Core intelligence status
    aerospace_intelligence_status: str = Field(
        description=(
            "AerospaceIntelligenceStatus vocabulary: "
            "NOMINAL | DEGRADED | RESTRICTED | GROUNDED_INTEL | UNKNOWN_INTEL"
        )
    )

    # Intelligence dimensions
    operational_dimension: OperationalIntelligenceDimension
    compliance_dimension: ComplianceIntelligenceDimension
    evidence_dimension: EvidenceIntelligenceDimension
    inspection_dimension: InspectionIntelligenceDimension
    finding_dimension: FindingIntelligenceDimension

    # Blockers and warnings
    blockers: list[IntelligenceBlocker] = Field(
        default_factory=list,
        description="All active intelligence blockers. Empty iff status is NOMINAL or DEGRADED.",
    )
    warnings: list[IntelligenceWarning] = Field(
        default_factory=list,
        description="Non-blocking intelligence warnings.",
    )

    # Aggregate counts for quick summary
    total_blocker_count: int = 0
    total_warning_count: int = 0
    compliance_blocker_count: int = 0
    evidence_blocker_count: int = 0
    inspection_blocker_count: int = 0
    finding_blocker_count: int = 0

    # Traceability
    source_records: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Source records that contributed to the intelligence evaluation.",
    )

    # Metadata
    evaluated_at: datetime
    evaluation_version: str = "D2.4.1"
    """Semantic version of the Aerospace State Engine evaluation logic.
    Allows Developer 2.2 to detect engine upgrades and invalidate cached states."""

    disclaimer: str = (
        "Aerospace Intelligence State is a deterministic interpretation of repository facts. "
        "It does not constitute an electronic Release to Service (RTS) signature and "
        "must not be used as a substitute for qualified engineer sign-off."
    )


# ---------------------------------------------------------------------------
# Query Contract (for API consumers)
# ---------------------------------------------------------------------------

class AerospaceIntelligenceStateQuery(BaseModel):
    """Optional query filters for requesting an intelligence state evaluation."""
    include_closed_findings: bool = False
    include_source_records: bool = False
