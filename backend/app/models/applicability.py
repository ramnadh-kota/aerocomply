"""Applicability Rules, Condition Trees, and Immutable Evaluation Snapshots.

Domain Invariants:
- Deterministic 3-valued (Kleene) logic: UNKNOWN != FALSE.
- Missing configuration information produces UNKNOWN / INSUFFICIENT_DATA.
- Immutable evaluation results: configuration_snapshot and reasoning_trace represent
  the exact state at evaluation time and must never mutate upon subsequent asset changes.
- Strict tenant isolation: rules, conditions, and evaluations are tenant-scoped.
"""

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TenantScopedMixin, TimestampMixin, UUIDPKMixin


class ConditionType(StrEnum):
    AIRCRAFT_VARIANT = "AIRCRAFT_VARIANT"
    MSN_RANGE = "MSN_RANGE"
    ENGINE_TYPE = "ENGINE_TYPE"
    AND = "AND"
    OR = "OR"
    NOT = "NOT"


class EvaluationResult(StrEnum):
    APPLICABLE = "APPLICABLE"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"


class ApplicabilityRule(UUIDPKMixin, TenantScopedMixin, TimestampMixin, Base):
    """A formal applicability rule specifying applicability criteria for an asset/aircraft.

    Can be linked to a RegulatoryRequirement or stand alone. Evaluated via a hierarchical
    ApplicabilityCondition tree.
    """

    __tablename__ = "applicability_rules"

    rule_code: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    regulatory_requirement_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("regulatory_requirements.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    root_condition_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("applicability_conditions.id", ondelete="SET NULL", use_alter=True),
        nullable=True,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    conditions = relationship(
        "ApplicabilityCondition",
        back_populates="rule",
        foreign_keys="ApplicabilityCondition.rule_id",
        cascade="all, delete-orphan",
    )
    evaluations = relationship("ApplicabilityEvaluation", back_populates="rule")


class ApplicabilityCondition(UUIDPKMixin, TenantScopedMixin, TimestampMixin, Base):
    """Hierarchical condition tree node.

    Leaf nodes represent domain checks (AIRCRAFT_VARIANT, MSN_RANGE, ENGINE_TYPE).
    Internal nodes represent Kleene combinators (AND, OR, NOT).
    """

    __tablename__ = "applicability_conditions"

    rule_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("applicability_rules.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    parent_condition_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("applicability_conditions.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    condition_type: Mapped[str] = mapped_column(String(32), nullable=False)
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    parameters: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    rule = relationship("ApplicabilityRule", back_populates="conditions", foreign_keys=[rule_id])
    children = relationship(
        "ApplicabilityCondition",
        foreign_keys=[parent_condition_id],
        order_by="ApplicabilityCondition.sequence",
        cascade="all, delete-orphan",
    )


class ApplicabilityEvaluation(UUIDPKMixin, TenantScopedMixin, TimestampMixin, Base):
    """Immutable record of an applicability evaluation performed at a specific point in time.

    Contains:
    - system_result (APPLICABLE, NOT_APPLICABLE, INSUFFICIENT_DATA, REVIEW_REQUIRED)
    - configuration_snapshot: exact state of aircraft/components at evaluation time.
    - reasoning_trace: audit trace of every condition node, input, and Kleene outcome.
    """

    __tablename__ = "applicability_evaluations"

    rule_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("applicability_rules.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    aircraft_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("aircraft.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    asset_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("assets.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    evaluated_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    system_result: Mapped[str] = mapped_column(String(32), nullable=False)
    evaluated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    configuration_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False)
    reasoning_trace: Mapped[dict] = mapped_column(JSONB, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    rule = relationship("ApplicabilityRule", back_populates="evaluations")
