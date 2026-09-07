import uuid
from enum import StrEnum

from sqlalchemy import Boolean, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TenantScopedMixin, TimestampMixin, UUIDPKMixin


class InspectionRequirementStatus(StrEnum):
    """Inspection requirement lifecycle.

    ``required`` (a separate column) says whether this task/work order needs an
    independent inspection at all — the checklist-review vs. RII (Required
    Inspection Item) distinction the frontend draws in
    frontend/lib/mock/ai/analytics.ts::isInspectionRequired /
    getInspectionRequirement. When ``required`` is False this row is a plain
    checklist review and NOT_REQUIRED is reachable directly. When ``required``
    is True, COMPLETED can only be reached with an inspector who is
    independent of whoever executed the work (see
    app/services/inspection_service.py::_assert_independent_inspector) — that
    is the RII safety property, mirroring the frontend's exclusion of
    ``assignedTechnicianId`` from ``getEligibleInspectorsForWorkOrder``.
    """

    PENDING = "PENDING"
    NOT_REQUIRED = "NOT_REQUIRED"
    COMPLETED = "COMPLETED"
    REJECTED = "REJECTED"


class InspectionRequirement(UUIDPKMixin, TenantScopedMixin, TimestampMixin, Base):
    __tablename__ = "inspection_requirements"

    task_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tasks.id"), nullable=True, index=True
    )
    work_order_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("work_orders.id"), nullable=True, index=True
    )
    required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    inspector_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=InspectionRequirementStatus.PENDING.value
    )
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
