"""Phase 18.4: mutation/read layer for tenant Facilities.

Follows the exact create/flush/audit/commit transaction pattern established
by app/services/warehouse_service.py and app/services/plan_service.py:
mutate, flush inside a try/except that translates a unique-constraint
IntegrityError into a clean ConflictError, record the (still-uncommitted)
audit event, then commit.

Tenant isolation: every read/write here takes organization_id as an
explicit parameter derived from the authenticated caller (see
app/api/v1/facilities.py, which passes current_user.organization_id -- the
client's request body/query never supplies it) and every query filters by
it. A facility_id that exists but belongs to a different organization is
treated identically to a nonexistent one (NotFoundError), never a
distinguishable 403 -- this deliberately avoids leaking cross-tenant
existence, matching this codebase's established pattern elsewhere (e.g.
app/services/platform_service.py's organization-scoped lookups).
"""

import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError
from app.models.facility import Facility, FacilityStatus, FacilityType
from app.schemas.facility import FacilityCreateRequest, FacilityUpdateRequest
from app.services.audit_service import record_audit_event

_VALID_TYPES = {
    FacilityType.HANGAR,
    FacilityType.WORKSHOP,
    FacilityType.WAREHOUSE,
    FacilityType.STATION,
    FacilityType.OFFICE,
    FacilityType.STORE,
    FacilityType.OTHER,
}
_VALID_STATUSES = {FacilityStatus.ACTIVE, FacilityStatus.INACTIVE}


def _validate_type(facility_type: str) -> None:
    if facility_type not in _VALID_TYPES:
        raise ConflictError(
            f"Invalid facility type {facility_type!r}", code="invalid_facility_type"
        )


def list_facilities(db: Session, *, organization_id: uuid.UUID) -> list[Facility]:
    return list(
        db.execute(
            select(Facility)
            .where(Facility.organization_id == organization_id)
            .order_by(Facility.code)
        )
        .scalars()
        .all()
    )


def get_facility(db: Session, *, organization_id: uuid.UUID, facility_id: uuid.UUID) -> Facility:
    facility = db.execute(
        select(Facility).where(
            Facility.id == facility_id, Facility.organization_id == organization_id
        )
    ).scalar_one_or_none()
    if facility is None:
        raise NotFoundError("Facility not found")
    return facility


def create_facility(
    db: Session,
    *,
    organization_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    payload: FacilityCreateRequest,
) -> Facility:
    _validate_type(payload.facility_type)

    existing = db.execute(
        select(Facility).where(
            Facility.organization_id == organization_id, Facility.code == payload.code
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise ConflictError(
            f"Facility code {payload.code!r} already in use", code="duplicate_facility_code"
        )

    facility = Facility(
        organization_id=organization_id,
        code=payload.code,
        name=payload.name,
        facility_type=payload.facility_type,
        status=FacilityStatus.ACTIVE,
        description=payload.description,
    )
    db.add(facility)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise ConflictError(
            f"Facility code {payload.code!r} already in use", code="duplicate_facility_code"
        ) from exc

    record_audit_event(
        db,
        organization_id=organization_id,
        user_id=actor_user_id,
        action="facility.created",
        entity_type="Facility",
        entity_id=facility.id,
        metadata={"code": payload.code, "facility_type": payload.facility_type},
    )
    db.commit()
    db.refresh(facility)
    return facility


def update_facility(
    db: Session,
    *,
    organization_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    facility_id: uuid.UUID,
    payload: FacilityUpdateRequest,
) -> Facility:
    facility = get_facility(db, organization_id=organization_id, facility_id=facility_id)

    updates: dict = {}
    if payload.name is not None:
        facility.name = payload.name
        updates["name"] = payload.name
    if payload.facility_type is not None:
        _validate_type(payload.facility_type)
        facility.facility_type = payload.facility_type
        updates["facility_type"] = payload.facility_type
    if payload.status is not None:
        if payload.status not in _VALID_STATUSES:
            raise ConflictError(
                f"Invalid facility status {payload.status!r}", code="invalid_facility_status"
            )
        facility.status = payload.status
        updates["status"] = payload.status
    if payload.description is not None:
        facility.description = payload.description
        updates["description"] = payload.description

    db.add(facility)
    if updates:
        db.flush()
        record_audit_event(
            db,
            organization_id=organization_id,
            user_id=actor_user_id,
            action="facility.updated",
            entity_type="Facility",
            entity_id=facility.id,
            metadata=updates,
        )
    db.commit()
    db.refresh(facility)
    return facility
