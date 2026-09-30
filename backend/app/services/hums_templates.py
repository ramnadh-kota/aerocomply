"""Starter HUMS sensor configurations for rotorcraft and eVTOL airframes.

A template is only a list of sensor DEFINITIONS (code, type, measurement, unit, location, component type). It carries
no thresholds, baselines or health claims: the deterministic HUMS engine learns baselines from the operator's own
data, and the shared exceedance limits apply to vibration. Applying a template is idempotent (existing sensor codes
are skipped) and binds each sensor to an installed component of the matching type when exactly one exists."""
from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.airframe_details import EvtolDetail
from app.models.asset import Asset
from app.models.component import Component, ComponentType
from app.models.hums import HUMSSensor
from app.schemas.hums import HUMSSensorCreate
from app.services import hums_service


@dataclass(frozen=True)
class SensorDef:
    code: str
    sensor_type: str
    measurement_type: str
    unit: str
    location: str
    component_type: str | None = None


HELICOPTER_TEMPLATE = [
    SensorDef("MR-VIB", "ACCELEROMETER", "vibration", "mm/s", "Main rotor / airframe", ComponentType.ROTOR),
    SensorDef("TR-VIB", "ACCELEROMETER", "vibration", "mm/s", "Tail rotor gearbox"),
    SensorDef("MGB-VIB", "ACCELEROMETER", "vibration", "mm/s", "Main gearbox", ComponentType.TRANSMISSION),
    SensorDef("MGB-TEMP", "THERMOCOUPLE", "temperature", "degC", "Main gearbox oil", ComponentType.TRANSMISSION),
    SensorDef("ENG1-TRQ", "TORQUE_SENSOR", "torque", "percent", "Engine 1 output", ComponentType.ENGINE),
    SensorDef("NR-RPM", "TACHOMETER", "rpm", "rpm", "Main rotor speed", ComponentType.ROTOR),
]


def evtol_template(propulsor_count: int | None) -> list[SensorDef]:
    n = max(0, min(int(propulsor_count or 0), 16))
    defs = [SensorDef(f"PROP{i}-VIB", "ACCELEROMETER", "vibration", "mm/s", f"Propulsor {i}") for i in range(1, n + 1)]
    defs += [
        SensorDef("MTR-TEMP", "THERMOCOUPLE", "temperature", "degC", "Propulsion motor winding", ComponentType.MOTOR),
        SensorDef("INV-TEMP", "THERMOCOUPLE", "temperature", "degC", "Inverter heat sink"),
        SensorDef("HVBUS-V", "VOLTAGE_SENSOR", "voltage", "V", "High-voltage bus"),
        SensorDef("HVBUS-I", "CURRENT_SENSOR", "current", "A", "High-voltage bus"),
        SensorDef("BATT-TEMP", "THERMOCOUPLE", "temperature", "degC", "Battery pack", ComponentType.BATTERY),
    ]
    return defs


def template_for(db: Session, asset: Asset) -> list[SensorDef]:
    if asset.asset_type == "HELICOPTER":
        return HELICOPTER_TEMPLATE
    if asset.asset_type == "EVTOL":
        detail = db.get(EvtolDetail, asset.id)
        return evtol_template(detail.propulsor_count if detail else None)
    raise ValueError("no HUMS template for this asset type")


def apply_template(db: Session, *, organization_id: uuid.UUID, user_id: uuid.UUID | None, asset: Asset) -> dict:
    existing = set(db.execute(select(HUMSSensor.sensor_code).where(
        HUMSSensor.organization_id == organization_id, HUMSSensor.asset_id == asset.id)).scalars())
    comps = db.execute(select(Component).where(Component.organization_id == organization_id,
                                               Component.asset_id == asset.id)).scalars().all()
    created, skipped = [], []
    for d in template_for(db, asset):
        if d.code in existing:
            skipped.append(d.code)
            continue
        matches = [c for c in comps if d.component_type and c.component_type == d.component_type]
        component_id = matches[0].id if len(matches) == 1 else None       # ambiguous => leave unbound, never guess
        hums_service.create_sensor(db, organization_id=organization_id, user_id=user_id, payload=HUMSSensorCreate(
            asset_id=asset.id, component_id=component_id, sensor_code=d.code, sensor_type=d.sensor_type,
            measurement_type=d.measurement_type, unit=d.unit, installation_location=d.location, source="IMPORTED"))
        created.append(d.code)
    return {"created": created, "skipped": skipped}
