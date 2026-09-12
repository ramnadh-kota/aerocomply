from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPKMixin


class OrganizationStatus:
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"


class Organization(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "organizations"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # Platform-managed tenant lifecycle status — never a billing/subscription
    # engine (none exists in this codebase); a plain field a platform admin
    # toggles. A SUSPENDED organization's users are refused at login (see
    # auth_service) rather than merely hidden in the UI.
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=OrganizationStatus.ACTIVE
    )
