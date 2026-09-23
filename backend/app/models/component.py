import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TenantScopedMixin, TimestampMixin, UUIDPKMixin


class ComponentType:
    """Standardized aerospace component type vocabulary.
    
    Covers propulsion, avionics, flight controls, structures, and systems
    across Fixed-Wing Aircraft, Drone UAVs, and Rotorcraft/Helicopters.
    """

    # Aircraft & Rotorcraft primary systems
    ENGINE = "ENGINE"
    AVIONICS = "AVIONICS"
    TRANSMISSION = "TRANSMISSION"
    ROTOR = "ROTOR"
    APU = "APU"
    ACTUATOR = "ACTUATOR"
    HYDRAULIC = "HYDRAULIC"
    LANDING_GEAR = "LANDING_GEAR"

    # Drone & electric propulsion systems
    MOTOR = "MOTOR"
    ESC = "ESC"
    PROPELLER = "PROPELLER"
    FLIGHT_CONTROLLER = "FLIGHT_CONTROLLER"
    BATTERY = "BATTERY"

    # Avionics, sensors & payloads
    GPS = "GPS"
    CAMERA = "CAMERA"
    GIMBAL = "GIMBAL"
    RADIO = "RADIO"
    PAYLOAD = "PAYLOAD"
    NAVIGATION = "NAVIGATION"
    SENSOR = "SENSOR"
    OTHER = "OTHER"


class ComponentStatus:
    INSTALLED = "INSTALLED"
    REMOVED = "REMOVED"
    IN_MAINTENANCE = "IN_MAINTENANCE"
    QUARANTINED = "QUARANTINED"
    SCRAPPED = "SCRAPPED"


class Component(UUIDPKMixin, TenantScopedMixin, TimestampMixin, Base):
    """Phase 18.6: a serialized asset component (motor, ESC, GPS, ...).
    Same asset_id-is-the-single-source-of-truth pattern as Battery -- see
    that model's docstring and alembic/versions/0032_drone_operations.py."""

    __tablename__ = "components"

    asset_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("assets.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    component_type: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    serial_number: Mapped[str | None] = mapped_column(String(128), nullable=True)
    manufacturer: Mapped[str | None] = mapped_column(String(128), nullable=True)
    model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=ComponentStatus.INSTALLED
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
