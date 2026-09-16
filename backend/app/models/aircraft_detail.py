import uuid

from sqlalchemy import ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AircraftDetail(Base):
    """Aircraft-specific fields extending a generic Asset (Phase 1A).

    1:1 with Asset via a shared primary key (asset_id), not a surrogate PK
    plus a unique FK -- there is exactly one AircraftDetail per Aircraft-typed
    Asset, so the FK column doubling as the PK makes that invariant
    structural rather than merely enforced by a unique constraint.

    organization_id/registration/status deliberately do NOT live here: they
    are Asset-level fields (see app/models/asset.py) shared by every future
    asset type, not aircraft-specific. Only msn/aircraft_type -- the fields
    that genuinely have no meaning for a non-aircraft asset -- stay here.
    """

    __tablename__ = "aircraft_details"

    asset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("assets.id"), primary_key=True
    )
    msn: Mapped[str] = mapped_column(String(64), nullable=False)
    aircraft_type: Mapped[str] = mapped_column(String(128), nullable=False)
