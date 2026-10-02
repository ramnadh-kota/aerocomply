"""C5: geofence configuration -- tenant-scoped CRUD with immutable version history and audit events.

Every read/write filters by the caller's organization (taken from the authenticated user, never from the request).
Geofences are deactivated, not deleted, so alert evidence that cites a geofence version stays resolvable."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import AeroComplyError, ConflictError, NotFoundError
from app.models.asset import Asset, AssetType
from app.models.geofence import Geofence, GeofenceVersion
from app.schemas.geofence import GeofenceCreate, GeofenceUpdate
from app.services import audit_service, geo

MAX_GEOFENCES_PER_ORG = 200
_CONFIG_FIELDS = (
    "name", "description", "kind", "geometry_type", "geometry", "altitude_reference", "alt_min_m", "alt_max_m",
    "severity", "proximity_buffer_m", "boundary_tolerance_m", "confirm_count", "asset_ids", "active_from",
    "active_until", "is_active",
)


def _invalid(msg: str) -> AeroComplyError:
    return AeroComplyError(msg, code="invalid_geofence", status_code=422)


def _snapshot(g: Geofence) -> dict[str, Any]:
    def enc(v: Any) -> Any:
        return v.isoformat() if isinstance(v, datetime) else v

    return {f: enc(getattr(g, f)) for f in _CONFIG_FIELDS} | {"version": g.version}


def _validate_assets(db: Session, organization_id: uuid.UUID, asset_ids: list[uuid.UUID] | None) -> list[str] | None:
    if asset_ids is None:
        return None
    ids = list(dict.fromkeys(asset_ids))
    found = set(db.execute(
        select(Asset.id).where(
            Asset.organization_id == organization_id, Asset.id.in_(ids), Asset.asset_type == AssetType.DRONE.value,
            Asset.deleted_at.is_(None),
        )
    ).scalars())
    if len(found) != len(ids):
        raise _invalid("asset_ids must all be drones of this organization")  # same answer for foreign and missing ids
    return [str(i) for i in ids]


def _normalize(geometry_type: str, geometry: dict[str, Any]) -> dict[str, Any]:
    try:
        return geo.normalize_geometry(geometry_type, geometry)
    except geo.GeometryError as exc:
        raise _invalid(str(exc)) from exc


def _record_version(db: Session, g: Geofence, change_type: str, user_id: uuid.UUID | None, reason: str | None = None) -> None:
    db.add(GeofenceVersion(
        organization_id=g.organization_id, geofence_id=g.id, version=g.version, change_type=change_type,
        snapshot=_snapshot(g), changed_by_user_id=user_id,
    ))
    audit_service.record_audit_event(
        db, organization_id=g.organization_id, user_id=user_id, action=f"geofence.{change_type.lower()}",
        entity_type="Geofence", entity_id=g.id,
        metadata={"version": g.version, "name": g.name, "kind": g.kind, **({"reason": reason} if reason else {})},
    )


def get_geofence(db: Session, *, organization_id: uuid.UUID, geofence_id: uuid.UUID) -> Geofence:
    g = db.execute(
        select(Geofence).where(Geofence.id == geofence_id, Geofence.organization_id == organization_id)
    ).scalar_one_or_none()
    if g is None:
        raise NotFoundError("Geofence not found", code="geofence_not_found")
    return g


def list_geofences(db: Session, *, organization_id: uuid.UUID, include_inactive: bool = False) -> list[Geofence]:
    q = select(Geofence).where(Geofence.organization_id == organization_id)
    if not include_inactive:
        q = q.where(Geofence.is_active.is_(True))
    return list(db.execute(q.order_by(Geofence.name, Geofence.id)).scalars())


def list_versions(db: Session, *, organization_id: uuid.UUID, geofence_id: uuid.UUID) -> list[GeofenceVersion]:
    get_geofence(db, organization_id=organization_id, geofence_id=geofence_id)
    return list(db.execute(
        select(GeofenceVersion).where(
            GeofenceVersion.organization_id == organization_id, GeofenceVersion.geofence_id == geofence_id
        ).order_by(GeofenceVersion.version.desc())
    ).scalars())


def create_geofence(db: Session, *, organization_id: uuid.UUID, user_id: uuid.UUID, payload: GeofenceCreate) -> Geofence:
    count = db.scalar(select(func.count(Geofence.id)).where(Geofence.organization_id == organization_id))
    if (count or 0) >= MAX_GEOFENCES_PER_ORG:
        raise ConflictError(f"Geofence limit ({MAX_GEOFENCES_PER_ORG}) reached", code="geofence_limit_reached")
    data = payload.model_dump(exclude={"asset_ids"})
    data["geometry"] = _normalize(payload.geometry_type, payload.geometry)
    g = Geofence(
        organization_id=organization_id, asset_ids=_validate_assets(db, organization_id, payload.asset_ids),
        version=1, created_by_user_id=user_id, updated_by_user_id=user_id, **data,
    )
    db.add(g)
    db.flush()
    _record_version(db, g, "CREATED", user_id)
    return g


def update_geofence(
    db: Session, *, organization_id: uuid.UUID, user_id: uuid.UUID, geofence_id: uuid.UUID, payload: GeofenceUpdate
) -> Geofence:
    g = db.execute(
        select(Geofence).where(Geofence.id == geofence_id, Geofence.organization_id == organization_id).with_for_update()
    ).scalar_one_or_none()
    if g is None:
        raise NotFoundError("Geofence not found", code="geofence_not_found")
    changes = payload.model_dump(exclude_unset=True, exclude={"reason"})
    if "geometry_type" in changes and "geometry" not in changes and changes["geometry_type"] != g.geometry_type:
        raise _invalid("geometry is required when geometry_type changes")
    for non_null in ("name", "kind", "geometry_type", "altitude_reference", "severity", "proximity_buffer_m",
                     "boundary_tolerance_m", "confirm_count", "is_active"):
        if non_null in changes and changes[non_null] is None:
            raise _invalid(f"{non_null} cannot be null")
    if "geometry" in changes or "geometry_type" in changes:
        gt = changes.get("geometry_type") or g.geometry_type
        changes["geometry"] = _normalize(gt, changes.get("geometry") if changes.get("geometry") is not None else g.geometry)
        changes["geometry_type"] = gt
    if "asset_ids" in changes:
        changes["asset_ids"] = _validate_assets(db, organization_id, payload.asset_ids)
    before = _snapshot(g)
    for k, v in changes.items():
        setattr(g, k, v)
    amin, amax, af, au = g.alt_min_m, g.alt_max_m, g.active_from, g.active_until
    if amin is not None and amax is not None and amin >= amax:
        raise _invalid("alt_min_m must be below alt_max_m")
    if af and au and af >= au:
        raise _invalid("active_from must be before active_until")
    if _snapshot(g) == before:
        return g  # no effective change: no new version, no audit noise
    if before["is_active"] != g.is_active:
        change_type = "REACTIVATED" if g.is_active else "DEACTIVATED"
    else:
        change_type = "UPDATED"
    g.version += 1
    g.updated_by_user_id = user_id
    g.updated_at = datetime.now(UTC)
    db.flush()
    _record_version(db, g, change_type, user_id, payload.reason)
    return g


def deactivate_geofence(db: Session, *, organization_id: uuid.UUID, user_id: uuid.UUID, geofence_id: uuid.UUID,
                        reason: str | None = None) -> Geofence:
    return update_geofence(
        db, organization_id=organization_id, user_id=user_id, geofence_id=geofence_id,
        payload=GeofenceUpdate(is_active=False, reason=reason),
    )
