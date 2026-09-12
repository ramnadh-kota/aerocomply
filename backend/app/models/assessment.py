"""MRO Assessment & Impact Intelligence domain.

A normalized, backend-authoritative assessment engine that sits ABOVE the
existing operational graph (Aircraft -> WorkOrder -> Task -> Part ->
Procurement -> PurchaseOrder -> Receiving -> Technician -> Evidence ->
Inspection -> Compliance -> Release). It never re-implements that graph's
business logic — see app/services/assessment/engine.py, which reads
findings exclusively through the existing canonical services
(aog_recovery_service, release_readiness_service, technician_service).

Deliberately NOT built: a separate AssessmentDependency join table. Every
Finding/RoadmapItem already carries entity_type/entity_id plus a free-text
`source` field naming the real record(s) it came from, and RoadmapItem
carries prerequisite_sequence_numbers (a plain int list, not a table) —
dependency ordering here follows the same real critical-path ordering
aog_recovery_service already computes, so a join table would only
duplicate identifiers already present on the finding/roadmap rows.

An Assessment is a named, reusable configuration ("Fleet Operational
Assessment", scoped to one aircraft, etc). Each time it is run, it produces
one new AssessmentSnapshot (immutable, versioned) — reruns never overwrite
history, so before/after comparison (Phase 11/21 of the build) is a plain
query across two snapshot rows.
"""

import uuid

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TenantScopedMixin, TimestampMixin, UUIDPKMixin


class AssessmentScopeType:
    FLEET = "FLEET"
    AIRCRAFT = "AIRCRAFT"
    WORK_ORDER = "WORK_ORDER"


class AssessmentStatus:
    DRAFT = "DRAFT"
    RUNNING = "RUNNING"
    COMPLETE = "COMPLETE"
    FAILED = "FAILED"


class Assessment(UUIDPKMixin, TenantScopedMixin, TimestampMixin, Base):
    __tablename__ = "assessments"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    scope_type: Mapped[str] = mapped_column(
        String(32), nullable=False, default=AssessmentScopeType.FLEET
    )
    # Real backend UUID this assessment is scoped to (an Aircraft.id or
    # WorkOrder.id) — null for FLEET scope. Never a fabricated identifier;
    # the engine resolves and validates it against the tenant before running.
    scope_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default=AssessmentStatus.DRAFT)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )

    snapshots: Mapped[list["AssessmentSnapshot"]] = relationship(
        back_populates="assessment", order_by="AssessmentSnapshot.version"
    )


class AssessmentSnapshot(UUIDPKMixin, TenantScopedMixin, TimestampMixin, Base):
    """One immutable run of an Assessment. `overall_score` and
    `maturity_band` are deterministic aggregates over this snapshot's own
    findings — never fabricated when there are zero findings (score is
    then simply 100 / HEALTHY, an honest "nothing found" result, not
    withheld).
    """

    __tablename__ = "assessment_snapshots"

    assessment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("assessments.id"), nullable=False, index=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    overall_score: Mapped[float] = mapped_column(nullable=False)
    maturity_band: Mapped[str] = mapped_column(String(32), nullable=False)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    finding_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    critical_finding_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    assessment: Mapped[Assessment] = relationship(back_populates="snapshots")
    findings: Mapped[list["AssessmentFinding"]] = relationship(
        back_populates="snapshot", cascade="all, delete-orphan"
    )
    risks: Mapped[list["AssessmentRisk"]] = relationship(
        back_populates="snapshot", cascade="all, delete-orphan"
    )
    gaps: Mapped[list["AssessmentGap"]] = relationship(
        back_populates="snapshot", cascade="all, delete-orphan"
    )
    recommendations: Mapped[list["AssessmentRecommendation"]] = relationship(
        back_populates="snapshot", cascade="all, delete-orphan"
    )
    roadmap_items: Mapped[list["AssessmentRoadmapItem"]] = relationship(
        back_populates="snapshot", cascade="all, delete-orphan"
    )
    metrics: Mapped[list["AssessmentMetric"]] = relationship(
        back_populates="snapshot", cascade="all, delete-orphan"
    )


class AssessmentFinding(UUIDPKMixin, TenantScopedMixin, TimestampMixin, Base):
    """A single real observation, always traceable to a real entity via
    entity_type/entity_id and a human-readable `source` naming the record
    (e.g. "AogEvent 58d685e1... blocker") — never free-standing prose.
    """

    __tablename__ = "assessment_findings"

    snapshot_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("assessment_snapshots.id"), nullable=False, index=True
    )
    category: Mapped[str] = mapped_column(String(64), nullable=False)
    severity: Mapped[str] = mapped_column(String(32), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(64), nullable=False)
    materiality_score: Mapped[float] = mapped_column(nullable=False)
    complexity_band: Mapped[str] = mapped_column(String(32), nullable=False)
    dependency_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    impact_dimensions: Mapped[list[str]] = mapped_column(
        ARRAY(String(32)), nullable=False, default=list
    )
    priority_rank: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    resolved: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    snapshot: Mapped[AssessmentSnapshot] = relationship(back_populates="findings")


class AssessmentRisk(UUIDPKMixin, TenantScopedMixin, TimestampMixin, Base):
    __tablename__ = "assessment_risks"

    snapshot_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("assessment_snapshots.id"), nullable=False, index=True
    )
    finding_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("assessment_findings.id"), nullable=True
    )
    risk_level: Mapped[str] = mapped_column(String(32), nullable=False)
    # Likelihood is explicitly UNKNOWN in this engine — no historical
    # failure-rate data exists to compute it from. risk_level here is
    # impact-driven only; this field documents that rather than hiding it.
    likelihood: Mapped[str] = mapped_column(String(32), nullable=False, default="UNKNOWN")
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(64), nullable=False)
    mitigation: Mapped[str | None] = mapped_column(Text, nullable=True)
    owner_role: Mapped[str | None] = mapped_column(String(64), nullable=True)

    snapshot: Mapped[AssessmentSnapshot] = relationship(back_populates="risks")


class AssessmentGap(UUIDPKMixin, TenantScopedMixin, TimestampMixin, Base):
    __tablename__ = "assessment_gaps"

    snapshot_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("assessment_snapshots.id"), nullable=False, index=True
    )
    finding_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("assessment_findings.id"), nullable=True
    )
    category: Mapped[str] = mapped_column(String(64), nullable=False)
    severity: Mapped[str] = mapped_column(String(32), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(64), nullable=False)
    expected_condition: Mapped[str] = mapped_column(Text, nullable=False)
    current_condition: Mapped[str] = mapped_column(Text, nullable=False)
    recommended_action: Mapped[str] = mapped_column(Text, nullable=False)

    snapshot: Mapped[AssessmentSnapshot] = relationship(back_populates="gaps")


class AssessmentRecommendation(UUIDPKMixin, TenantScopedMixin, TimestampMixin, Base):
    __tablename__ = "assessment_recommendations"

    snapshot_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("assessment_snapshots.id"), nullable=False, index=True
    )
    finding_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("assessment_findings.id"), nullable=True
    )
    recommendation: Mapped[str] = mapped_column(Text, nullable=False)
    why: Mapped[str] = mapped_column(Text, nullable=False)
    priority: Mapped[str] = mapped_column(String(32), nullable=False)
    responsible_role: Mapped[str | None] = mapped_column(String(64), nullable=True)
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="OPEN")

    snapshot: Mapped[AssessmentSnapshot] = relationship(back_populates="recommendations")


class AssessmentRoadmapItem(UUIDPKMixin, TenantScopedMixin, TimestampMixin, Base):
    __tablename__ = "assessment_roadmap_items"

    snapshot_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("assessment_snapshots.id"), nullable=False, index=True
    )
    finding_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("assessment_findings.id"), nullable=True
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(String(64), nullable=False)
    priority: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="PLANNED")
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(64), nullable=False)
    prerequisite_sequence_numbers: Mapped[list[int]] = mapped_column(
        ARRAY(Integer), nullable=False, default=list
    )
    owner_role: Mapped[str | None] = mapped_column(String(64), nullable=True)
    estimated_effort_band: Mapped[str] = mapped_column(
        String(32), nullable=False, default="UNKNOWN"
    )
    effort_confidence: Mapped[str] = mapped_column(String(32), nullable=False, default="LOW")
    expected_impact: Mapped[str] = mapped_column(Text, nullable=False)
    risk_if_delayed: Mapped[str] = mapped_column(Text, nullable=False)

    snapshot: Mapped[AssessmentSnapshot] = relationship(back_populates="roadmap_items")


class AssessmentMetric(UUIDPKMixin, TenantScopedMixin, TimestampMixin, Base):
    """A single named, sourced dimension value (a materiality/complexity/
    impact input) — normalized so every score in the engine can point back
    to the exact inputs that produced it. `state` distinguishes an actual
    computed VALUE from UNKNOWN/NOT_TRACKED (no fabricated numeric filler).
    """

    __tablename__ = "assessment_metrics"

    snapshot_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("assessment_snapshots.id"), nullable=False, index=True
    )
    metric_key: Mapped[str] = mapped_column(String(128), nullable=False)
    state: Mapped[str] = mapped_column(String(32), nullable=False)  # VALUE | UNKNOWN | NOT_TRACKED
    value: Mapped[float | None] = mapped_column(nullable=True)
    unit: Mapped[str | None] = mapped_column(String(32), nullable=True)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)

    snapshot: Mapped[AssessmentSnapshot] = relationship(back_populates="metrics")


__all__ = [
    "Assessment",
    "AssessmentScopeType",
    "AssessmentStatus",
    "AssessmentSnapshot",
    "AssessmentFinding",
    "AssessmentRisk",
    "AssessmentGap",
    "AssessmentRecommendation",
    "AssessmentRoadmapItem",
    "AssessmentMetric",
]
