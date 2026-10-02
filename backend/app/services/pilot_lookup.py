"""Tenant-scoped pilot display-name resolution shared by missions and flights.

Only users.full_name is returned (never email/phone). A pilot id that does not
belong to the caller's organization (other tenant, deleted user) simply does not
resolve, so callers fall back to a generic label -- there is no cross-tenant
lookup and no existence oracle.
"""

import uuid
from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.user import User


def resolve_pilot_names(
    db: Session, *, organization_id: uuid.UUID, pilot_ids: Iterable[uuid.UUID | None]
) -> dict[uuid.UUID, str]:
    ids = {p for p in pilot_ids if p is not None}
    if not ids:
        return {}
    rows = db.execute(
        select(User.id, User.full_name).where(User.id.in_(ids), User.organization_id == organization_id)
    ).all()
    return {uid: name for uid, name in rows if name}


def with_pilot_names(db: Session, *, organization_id: uuid.UUID, records: list, response_cls) -> list:
    """Validate ORM rows (having pilot_user_id) into response_cls, adding pilot_name."""
    names = resolve_pilot_names(
        db, organization_id=organization_id, pilot_ids=(r.pilot_user_id for r in records)
    )
    out = []
    for r in records:
        item = response_cls.model_validate(r)
        item.pilot_name = names.get(r.pilot_user_id) if r.pilot_user_id else None
        out.append(item)
    return out
