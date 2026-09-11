import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class LisaConversationContextResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    user_id: uuid.UUID
    current_aircraft_id: uuid.UUID | None
    current_work_order_id: uuid.UUID | None
    current_task_id: uuid.UUID | None
    current_part_id: uuid.UUID | None
    current_part_requirement_id: uuid.UUID | None
    current_procurement_request_id: uuid.UUID | None
    current_vendor_id: uuid.UUID | None
    current_purchase_order_id: uuid.UUID | None
    current_technician_user_id: uuid.UUID | None
    current_aog_event_id: uuid.UUID | None
    previous_question: str | None
    context_version: int
    last_activity_at: datetime


class ResolvedEntityResponse(BaseModel):
    entity_type: str
    entity_id: str
    display: str
