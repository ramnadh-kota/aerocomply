"""Type-specific detail rows for rotorcraft and eVTOL/AAM assets (1:1 with Asset, shared primary key), mirroring
AircraftDetail. Identity, registration, status and tenant ownership stay on Asset."""

from __future__ import annotations

import uuid

from sqlalchemy import CheckConstraint, Float, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class RotorSystem:
    SINGLE_MAIN_TAIL = "SINGLE_MAIN_TAIL"
    TANDEM = "TANDEM"
    COAXIAL = "COAXIAL"
    NOTAR = "NOTAR"
    TILTROTOR = "TILTROTOR"
    OTHER = "OTHER"
    ALL = frozenset({SINGLE_MAIN_TAIL, TANDEM, COAXIAL, NOTAR, TILTROTOR, OTHER})


class EvtolConfiguration:
    MULTICOPTER = "MULTICOPTER"
    LIFT_CRUISE = "LIFT_CRUISE"
    VECTORED_THRUST = "VECTORED_THRUST"
    TILTROTOR = "TILTROTOR"
    OTHER = "OTHER"
    ALL = frozenset({MULTICOPTER, LIFT_CRUISE, VECTORED_THRUST, TILTROTOR, OTHER})


class HelicopterDetail(Base):
    __tablename__ = "helicopter_details"
    __table_args__ = (
        CheckConstraint("engine_count IS NULL OR engine_count BETWEEN 1 AND 4", name="ck_helicopter_engine_count"),
        CheckConstraint("main_rotor_blade_count IS NULL OR main_rotor_blade_count BETWEEN 2 AND 12",
                        name="ck_helicopter_blade_count"),
        CheckConstraint("max_takeoff_weight_kg IS NULL OR max_takeoff_weight_kg > 0", name="ck_helicopter_mtow"),
    )

    asset_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("assets.id"), primary_key=True)
    rotor_system: Mapped[str] = mapped_column(String(32), nullable=False, default=RotorSystem.SINGLE_MAIN_TAIL)
    main_rotor_blade_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    engine_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_takeoff_weight_kg: Mapped[float | None] = mapped_column(Float, nullable=True)


class EvtolDetail(Base):
    __tablename__ = "evtol_details"
    __table_args__ = (
        CheckConstraint("propulsor_count IS NULL OR propulsor_count BETWEEN 1 AND 64", name="ck_evtol_propulsors"),
        CheckConstraint("battery_nominal_energy_kwh IS NULL OR battery_nominal_energy_kwh > 0", name="ck_evtol_energy"),
        CheckConstraint("hv_bus_nominal_voltage_v IS NULL OR hv_bus_nominal_voltage_v > 0", name="ck_evtol_hv_bus"),
        CheckConstraint("max_takeoff_weight_kg IS NULL OR max_takeoff_weight_kg > 0", name="ck_evtol_mtow"),
        CheckConstraint("passenger_capacity IS NULL OR passenger_capacity >= 0", name="ck_evtol_pax"),
    )

    asset_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("assets.id"), primary_key=True)
    configuration: Mapped[str] = mapped_column(String(32), nullable=False, default=EvtolConfiguration.MULTICOPTER)
    propulsor_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    battery_nominal_energy_kwh: Mapped[float | None] = mapped_column(Float, nullable=True)
    hv_bus_nominal_voltage_v: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_takeoff_weight_kg: Mapped[float | None] = mapped_column(Float, nullable=True)
    passenger_capacity: Mapped[int | None] = mapped_column(Integer, nullable=True)
