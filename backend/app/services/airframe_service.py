"""Helicopter and eVTOL/AAM airframes.

Like drones, these are NOT new identity tables: an airframe is an Asset (asset_type HELICOPTER / EVTOL) plus a 1:1
detail row (app/models/airframe_details.py). Flights, utilization, components, batteries and maintenance reuse the
existing shared services (parameterised by asset_type); this module owns creation, validation and detail data.

What is intentionally NOT here: rotorcraft- or eVTOL-specific analytics (e.g. rotor track-and-balance, gearbox
condition indicators, propulsor efficiency models). Those need vendor/engineering data this repository does not have;
HUMS runs the same deterministic feature/threshold engine on whatever sensors the operator configures (see
hums_templates)."""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError
from app.models.airframe_details import EvtolConfiguration, EvtolDetail, HelicopterDetail, RotorSystem
from app.models.asset import Asset, AssetLifecycleStatus, AssetType
from app.services import drone_service, facility_service
from app.services.audit_service import record_audit_event
from app.services.limit_enforcement_service import check_asset_creation_limit

HELICOPTER = AssetType.HELICOPTER.value
EVTOL = AssetType.EVTOL.value

_DETAIL_MODEL = {HELICOPTER: HelicopterDetail, EVTOL: EvtolDetail}
_DETAIL_FIELDS: dict[str, dict[str, type]] = {
    HELICOPTER: {"rotor_system": str, "main_rotor_blade_count": int, "engine_count": int, "max_takeoff_weight_kg": float},
    EVTOL: {"configuration": str, "propulsor_count": int, "battery_nominal_energy_kwh": float,
            "hv_bus_nominal_voltage_v": float, "max_takeoff_weight_kg": float, "passenger_capacity": int},
}
# (min, max) inclusive; None = unbounded. Mirrors the table CHECK constraints so bad input is a clean 422, never an
# IntegrityError misreported as a duplicate registration.
_RANGES: dict[str, tuple[float | None, float | None]] = {
    "main_rotor_blade_count": (2, 12), "engine_count": (1, 4), "propulsor_count": (1, 64), "passenger_capacity": (0, None),
    "max_takeoff_weight_kg": (0.000001, None), "battery_nominal_energy_kwh": (0.000001, None),
    "hv_bus_nominal_voltage_v": (0.000001, None),
}
_ENUMS = {(HELICOPTER, "rotor_system"): RotorSystem.ALL, (EVTOL, "configuration"): EvtolConfiguration.ALL}
_LABEL = {HELICOPTER: "helicopter", EVTOL: "evtol"}


class AirframeValidationError(ValueError):
    """Bad client input (mapped to HTTP 422 by the API layer)."""


def _clean_detail(asset_type: str, detail: dict[str, Any] | None) -> dict[str, Any]:
    out: dict[str, Any] = {}
    allowed = _DETAIL_FIELDS[asset_type]
    for key, value in (detail or {}).items():
        if key not in allowed:
            raise AirframeValidationError(f"unknown {_LABEL[asset_type]} field {key!r}")
        if value is None:
            out[key] = None
            continue
        try:
            value = allowed[key](value)
        except (TypeError, ValueError) as exc:
            raise AirframeValidationError(f"{key} must be {allowed[key].__name__}") from exc
        lo, hi = _RANGES.get(key, (None, None))
        if (lo is not None and value < lo) or (hi is not None and value > hi):
            raise AirframeValidationError(f"{key} is out of range")
        valid = _ENUMS.get((asset_type, key))
        if valid is not None and value not in valid:
            raise AirframeValidationError(f"{key} must be one of {sorted(valid)}")
        out[key] = value
    return out


def _check_facility(db: Session, organization_id: uuid.UUID, facility_id: uuid.UUID | None) -> None:
    facility_service.require_owned_facility(db, organization_id=organization_id, facility_id=facility_id)


def create_airframe(
    db: Session, *, asset_type: str, organization_id: uuid.UUID, actor_user_id: uuid.UUID | None, registration: str,
    manufacturer: str | None, model: str | None, serial_number: str | None, facility_id: uuid.UUID | None,
    detail: dict[str, Any] | None,
) -> tuple[Asset, Any]:
    fields = _clean_detail(asset_type, detail)
    _check_facility(db, organization_id, facility_id)
    check_asset_creation_limit(db, organization_id=organization_id)
    reg = registration.strip().upper()
    if not reg:
        raise AirframeValidationError("registration is required")
    dup = db.execute(select(Asset.id).where(Asset.organization_id == organization_id, Asset.registration == reg)).first()
    if dup is not None:
        raise ConflictError(f"Asset registration {reg!r} already in use", code="duplicate_registration")
    asset = Asset(organization_id=organization_id, asset_type=asset_type, registration=reg, manufacturer=manufacturer,
                  model=model, serial_number=serial_number, status="ACTIVE", facility_id=facility_id)
    try:
        with db.begin_nested():
            db.add(asset)
            db.flush()
            row = _DETAIL_MODEL[asset_type](asset_id=asset.id, **fields)
            db.add(row)
            db.flush()
    except IntegrityError as exc:
        if "uq_assets_organization_id_registration" not in str(exc.orig):
            raise
        raise ConflictError(f"Asset registration {reg!r} already in use", code="duplicate_registration") from exc
    record_audit_event(db, organization_id=organization_id, user_id=actor_user_id,
                       action=f"{_LABEL[asset_type]}.created", entity_type="Asset", entity_id=asset.id,
                       metadata={"registration": reg, **fields})
    db.commit()
    db.refresh(asset)
    return asset, row


def get_airframe(db: Session, *, asset_type: str, organization_id: uuid.UUID, asset_id: uuid.UUID) -> tuple[Asset, Any]:
    asset = drone_service.get_airframe(db, organization_id=organization_id, asset_id=asset_id, asset_type=asset_type)
    model = _DETAIL_MODEL[asset_type]
    row = db.get(model, asset.id)
    if row is None:                                          # asset created by a generic path: lazily give it a detail row
        row = model(asset_id=asset.id)
        db.add(row)
        db.flush()
    return asset, row


def list_airframes(db: Session, *, asset_type: str, organization_id: uuid.UUID) -> list[tuple[Asset, Any]]:
    assets = db.execute(select(Asset).where(
        Asset.organization_id == organization_id, Asset.asset_type == asset_type, Asset.deleted_at.is_(None)
    ).order_by(Asset.registration)).scalars().all()
    model = _DETAIL_MODEL[asset_type]
    details = {d.asset_id: d for d in db.execute(select(model).where(model.asset_id.in_([a.id for a in assets]))).scalars()}
    return [(a, details.get(a.id)) for a in assets]


def update_airframe(
    db: Session, *, asset_type: str, organization_id: uuid.UUID, actor_user_id: uuid.UUID | None, asset_id: uuid.UUID,
    manufacturer: str | None = None, model: str | None = None, status: str | None = None,
    facility_id: uuid.UUID | None = None, detail: dict[str, Any] | None = None,
) -> tuple[Asset, Any]:
    fields = _clean_detail(asset_type, detail)
    if status is not None and status not in {s.value for s in AssetLifecycleStatus}:
        raise AirframeValidationError(f"status must be one of {sorted(s.value for s in AssetLifecycleStatus)}")
    _check_facility(db, organization_id, facility_id)
    asset, row = get_airframe(db, asset_type=asset_type, organization_id=organization_id, asset_id=asset_id)
    changes: dict[str, Any] = {}
    for name, value in (("manufacturer", manufacturer), ("model", model), ("status", status), ("facility_id", facility_id)):
        if value is not None and getattr(asset, name) != value:
            changes[name] = {"from": str(getattr(asset, name)), "to": str(value)}     # previous value preserved
            setattr(asset, name, value)
    for key, value in fields.items():
        if getattr(row, key) != value:
            changes[key] = {"from": getattr(row, key), "to": value}
            setattr(row, key, value)
    if changes:
        db.flush()
        record_audit_event(db, organization_id=organization_id, user_id=actor_user_id,
                           action=f"{_LABEL[asset_type]}.updated", entity_type="Asset", entity_id=asset.id, metadata=changes)
    db.commit()
    db.refresh(asset)
    return asset, row
