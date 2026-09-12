import uuid
from datetime import datetime

from pydantic import BaseModel


class OrganizationUserResponse(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str
    is_active: bool
    roles: list[str]
    created_at: datetime

    class Config:
        from_attributes = True
