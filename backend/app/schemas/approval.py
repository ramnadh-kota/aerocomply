"""M14: request/response schemas for governance approval requests.

Neutral terminology only (Requested / Pending review / Approved / Rejected
/ Canceled / Reviewed by) -- never "security team", "two-person approval",
or "compliance approved" anywhere in these schemas or their consumers,
because the backend does not actually implement any of those things (see
app/services/approval_service.py's module docstring on self-approval).
"""
import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

RequestType = Literal["feature_override_expansion", "usage_limit_expansion"]
ApprovalStatus = Literal["PENDING", "APPROVED", "REJECTED", "CANCELED"]


class ApprovalRequestCreateRequest(BaseModel):
    request_type: RequestType
    feature_key: str = Field(min_length=1, max_length=128)
    reason: str | None = None

    # feature_override_expansion
    requested_enabled: bool | None = None

    # usage_limit_expansion
    limit_key: str | None = Field(default=None, max_length=128)
    requested_limit_value: int | None = None
    requested_is_unlimited: bool | None = None

    @model_validator(mode="after")
    def _validate_shape(self) -> "ApprovalRequestCreateRequest":
        if self.request_type == "feature_override_expansion":
            if self.requested_enabled is not True:
                raise ValueError(
                    "feature_override_expansion requires requested_enabled=true "
                    "(disabling a feature is never expansive and never needs approval)"
                )
        elif self.request_type == "usage_limit_expansion":
            if not self.limit_key:
                raise ValueError("usage_limit_expansion requires limit_key")
            if self.requested_is_unlimited is not True and self.requested_limit_value is None:
                raise ValueError(
                    "usage_limit_expansion requires requested_is_unlimited=true or a "
                    "requested_limit_value"
                )
        return self


class ApprovalDecisionRequest(BaseModel):
    decision_reason: str | None = None


class ApprovalRequestResponse(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    request_type: RequestType
    status: ApprovalStatus
    feature_key: str
    requested_enabled: bool | None
    limit_key: str | None
    requested_limit_value: int | None
    requested_is_unlimited: bool | None
    reason: str | None
    requested_by_user_id: uuid.UUID | None
    reviewed_by_user_id: uuid.UUID | None
    reviewed_at: datetime | None
    decision_reason: str | None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ApprovalRequestListResponse(BaseModel):
    items: list[ApprovalRequestResponse]
    total: int
    limit: int
    offset: int
