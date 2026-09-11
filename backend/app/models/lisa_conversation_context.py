import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TenantScopedMixin, TimestampMixin, UUIDPKMixin


class LisaConversationContext(UUIDPKMixin, TenantScopedMixin, TimestampMixin, Base):
    """One active operational conversation context per (organization, user).

    Deliberately not a full multi-conversation/session-history table — this
    product has one Lisa chat per user at a time (see AIConsole.tsx), so a
    single active row keyed by (organization_id, user_id) is the smallest
    real model that supports cross-turn entity/reference resolution without
    inventing a conversation-thread concept the frontend doesn't have.

    Every current_*_id column stores a real backend record's primary key —
    never a fabricated identifier. `recent_entities` and `recent_questions`
    are plain JSON-encoded text (small bounded lists, trimmed on write) —
    structured facts only, never chain-of-thought or raw tool output.
    """

    __tablename__ = "lisa_conversation_contexts"
    __table_args__ = (
        UniqueConstraint("organization_id", "user_id", name="uq_lisa_context_org_user"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )

    current_aircraft_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    current_work_order_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    current_task_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    current_part_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    current_part_requirement_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    current_procurement_request_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    current_vendor_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    current_purchase_order_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    current_technician_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    current_aog_event_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )

    # JSON-encoded list[dict] of {entity_type, entity_id, display, resolved_at}
    # — most-recent-last, trimmed to a small bounded length on write.
    recent_entities: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    previous_question: Mapped[str | None] = mapped_column(Text, nullable=True)
    # JSON-encoded list[str], most-recent-last, trimmed to 5 on write.
    recent_questions: Mapped[str] = mapped_column(Text, nullable=False, default="[]")

    context_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    last_activity_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
