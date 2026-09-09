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
    aircraft_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("aircraft.id"), nullable=False, index=True
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
    aircraft_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("aircraft.id"), nullable=False, index=True
    )
    accomplished_at: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    work_order_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("work_orders.id"), nullable=True
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
