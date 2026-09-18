import datetime
import uuid

from sqlalchemy import Date, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TenantScopedMixin, TimestampMixin, UUIDPKMixin


class MaintenanceIntervalType:
    FLIGHT_HOURS = "FLIGHT_HOURS"
    FLIGHT_CYCLES = "FLIGHT_CYCLES"
    CALENDAR = "CALENDAR"
    # M17.5A: battery/component life-limit metrics. Reuse the existing
    # fc_interval/fh_interval integer columns below (no new interval
    # columns) -- BATTERY_CYCLES and COMPONENT_CYCLES both read
    # fc_interval, COMPONENT_HOURS reads fh_interval. Which column applies
    # is determined entirely by interval_type, same as the FLIGHT_*
    # pair already does for the asset-level path.
    BATTERY_CYCLES = "BATTERY_CYCLES"
    COMPONENT_HOURS = "COMPONENT_HOURS"
    COMPONENT_CYCLES = "COMPONENT_CYCLES"


class MaintenanceRequirement(UUIDPKMixin, TenantScopedMixin, TimestampMixin, Base):
    __tablename__ = "maintenance_requirements"

    description: Mapped[str] = mapped_column(Text, nullable=False)
    ata_chapter: Mapped[str] = mapped_column(String(16), nullable=False)
    interval_type: Mapped[str] = mapped_column(String(16), nullable=False)
    fh_interval: Mapped[int | None] = mapped_column(Integer, nullable=True)
    fc_interval: Mapped[int | None] = mapped_column(Integer, nullable=True)
    calendar_interval_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    task_reference: Mapped[str | None] = mapped_column(String(64), nullable=True)

    applicabilities: Mapped[list["MaintenanceRequirementApplicability"]] = relationship(
        back_populates="requirement", cascade="all, delete-orphan"
    )


class MaintenanceRequirementApplicability(UUIDPKMixin, TenantScopedMixin, TimestampMixin, Base):
    __tablename__ = "maintenance_requirement_applicabilities"

    requirement_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("maintenance_requirements.id"), nullable=False, index=True
    )
    # Phase 18.6 (migration 0032): loosened to nullable -- a Drone
    # applicability has no Aircraft row. asset_id is canonical for those.
    aircraft_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("aircraft.id"), nullable=True, index=True
    )
    # Phase 1B compatibility mapping (migration 0031) -- see
    # app/models/work_order.py's asset_id for the full rationale.
    asset_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("assets.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    # M17.5A (migration 0034): a requirement applying to a specific
    # serialized Battery/Component, not the asset it happens to be
    # installed on right now. Exactly one of aircraft_id/asset_id/
    # battery_id/component_id is set per row.
    battery_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("batteries.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    component_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("components.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )

    requirement: Mapped[MaintenanceRequirement] = relationship(back_populates="applicabilities")


class MaintenanceAccomplishment(UUIDPKMixin, TenantScopedMixin, TimestampMixin, Base):
    """Proof a requirement was actually performed on a specific aircraft — the
    due-status engine (maintenance_service.get_due_status_for_aircraft) reads
    ONLY these records, never a work order's status alone, matching the
    frontend's own documented rule (frontend/lib/mock/types.ts
    MaintenanceAccomplishment).
    """

    __tablename__ = "maintenance_accomplishments"

    requirement_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("maintenance_requirements.id"), nullable=False, index=True
    )
    # Phase 18.6 (migration 0032): loosened to nullable -- a Drone
    # accomplishment has no Aircraft row. asset_id is canonical for those.
    aircraft_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("aircraft.id"), nullable=True, index=True
    )
    # Phase 1B compatibility mapping (migration 0031) -- see
    # app/models/work_order.py's asset_id for the full rationale.
    asset_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("assets.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    # M17.5A (migration 0034): see MaintenanceRequirementApplicability's
    # battery_id/component_id docstring -- same pairing convention.
    battery_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("batteries.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    component_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("components.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    accomplished_at: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    work_order_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("work_orders.id"), nullable=True
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
