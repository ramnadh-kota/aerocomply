import datetime
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AeroComplyError, NotFoundError
from app.models.mission import Mission, MissionStatus
from app.models.user import User
from app.schemas.mission import MissionAuthorizeRequest, MissionCreateRequest, MissionUpdateRequest
from app.services import asset_service
from app.services.audit_service import record_audit_event

MISSION_LIST_DEFAULT_LIMIT = 50
MISSION_LIST_MAX_LIMIT = 100


def create_mission(
    db: Session,
    *,
    organization_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    payload: MissionCreateRequest,
) -> Mission:
    # 1. Tenant ownership validation: asset must belong to the caller organization
    asset_service.get_asset(db, organization_id=organization_id, asset_id=payload.asset_id)

    # 2. Pilot ownership validation: pilot must belong to caller organization
    if payload.pilot_user_id is not None:
        pilot = db.execute(
            select(User).where(
                User.id == payload.pilot_user_id,
                User.organization_id == organization_id,
            )
        ).scalar_one_or_none()
        if pilot is None:
            raise NotFoundError("Pilot user not found in organization")

    mission = Mission(
        organization_id=organization_id,
        asset_id=payload.asset_id,
        pilot_user_id=payload.pilot_user_id,
        status=MissionStatus.PLANNED,
        purpose=payload.purpose,
        operating_area=payload.operating_area,
        planned_start=payload.planned_start,
        planned_end=payload.planned_end,
        notes=payload.notes,
    )
    db.add(mission)
    db.flush()

    record_audit_event(
        db,
        organization_id=organization_id,
        user_id=actor_user_id,
        action="mission.created",
        entity_type="Mission",
        entity_id=mission.id,
        metadata={"asset_id": str(payload.asset_id), "status": MissionStatus.PLANNED},
    )
    db.commit()
    db.refresh(mission)
    return mission


def get_mission(db: Session, *, organization_id: uuid.UUID, mission_id: uuid.UUID) -> Mission:
    mission = db.execute(
        select(Mission).where(Mission.id == mission_id, Mission.organization_id == organization_id)
    ).scalar_one_or_none()
    if mission is None:
        raise NotFoundError("Mission not found")
    return mission


def list_missions(
    db: Session,
    *,
    organization_id: uuid.UUID,
    asset_id: uuid.UUID | None = None,
    status: str | None = None,
    limit: int = MISSION_LIST_DEFAULT_LIMIT,
    offset: int = 0,
) -> tuple[list[Mission], int]:
    bounded_limit = max(1, min(limit, MISSION_LIST_MAX_LIMIT))
    bounded_offset = max(0, offset)

    query = select(Mission).where(Mission.organization_id == organization_id)
    if asset_id is not None:
        query = query.where(Mission.asset_id == asset_id)
    if status is not None:
        query = query.where(Mission.status == status)

    # Fetch total
    all_matching = db.execute(query).scalars().all()
    total = len(all_matching)

    items = list(
        db.execute(
            query.order_by(Mission.created_at.desc()).limit(bounded_limit).offset(bounded_offset)
        )
        .scalars()
        .all()
    )
    return items, total


def update_mission(
    db: Session,
    *,
    organization_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    mission_id: uuid.UUID,
    payload: MissionUpdateRequest,
) -> Mission:
    mission = get_mission(db, organization_id=organization_id, mission_id=mission_id)

    if payload.pilot_user_id is not None:
        pilot = db.execute(
            select(User).where(
                User.id == payload.pilot_user_id,
                User.organization_id == organization_id,
            )
        ).scalar_one_or_none()
        if pilot is None:
            raise NotFoundError("Pilot user not found in organization")
        mission.pilot_user_id = payload.pilot_user_id

    if payload.purpose is not None:
        mission.purpose = payload.purpose
    if payload.operating_area is not None:
        mission.operating_area = payload.operating_area
    if payload.planned_start is not None:
        mission.planned_start = payload.planned_start
    if payload.planned_end is not None:
        mission.planned_end = payload.planned_end
    if payload.status is not None:
        mission.status = payload.status
    if payload.notes is not None:
        mission.notes = payload.notes

    db.add(mission)
    record_audit_event(
        db,
        organization_id=organization_id,
        user_id=actor_user_id,
        action="mission.updated",
        entity_type="Mission",
        entity_id=mission.id,
        metadata={"status": mission.status},
    )
    db.commit()
    db.refresh(mission)
    return mission


def authorize_mission(
    db: Session,
    *,
    organization_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    mission_id: uuid.UUID,
    payload: MissionAuthorizeRequest | None = None,
) -> Mission:
    mission = get_mission(db, organization_id=organization_id, mission_id=mission_id)

    if mission.status == MissionStatus.CANCELLED or mission.status == MissionStatus.COMPLETED:
        raise AeroComplyError(f"Cannot authorize a mission in {mission.status} status")

    mission.status = MissionStatus.AUTHORIZED
    mission.authorized_at = datetime.datetime.now(datetime.timezone.utc)
    mission.authorized_by_user_id = actor_user_id
    if payload and payload.notes:
        mission.notes = (mission.notes or "") + f"\n[Authorization Note]: {payload.notes}".strip()

    db.add(mission)
    record_audit_event(
        db,
        organization_id=organization_id,
        user_id=actor_user_id,
        action="mission.authorized",
        entity_type="Mission",
        entity_id=mission.id,
        metadata={"status": MissionStatus.AUTHORIZED},
    )
    db.commit()
    db.refresh(mission)
    return mission
