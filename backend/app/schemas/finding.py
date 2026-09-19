import uuid
from datetime import datetime

from pydantic import BaseModel, Field, model_validator


class FindingCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    description: str = Field(min_length=1)
    severity: str = Field(min_length=1, max_length=32)
    aircraft_id: uuid.UUID | None = None
    asset_id: uuid.UUID | None = None
    component_id: uuid.UUID | None = None
    inspection_requirement_id: uuid.UUID | None = None
    work_order_id: uuid.UUID | None = None
    task_id: uuid.UUID | None = None
    responsible_user_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def _require_some_traceability(self) -> "FindingCreateRequest":
        # Mirrors AssessmentFinding's "never free-standing" rule and
        # InspectionRequirementCreateRequest's own validator shape: a
        # Finding must be linked to at least one real record.
        if not any(
            [
                self.aircraft_id,
                self.asset_id,
                self.component_id,
                self.inspection_requirement_id,
                self.work_order_id,
                self.task_id,
            ]
        ):
            raise ValueError(
                "A finding must reference at least one of: aircraft_id, asset_id, "
                "component_id, inspection_requirement_id, work_order_id, task_id"
            )
        return self


class FindingDispositionRequest(BaseModel):
    disposition_type: str = Field(min_length=1, max_length=32)
    corrective_action: str | None = None
    evidence_id: uuid.UUID | None = None


class FindingDispositionResponse(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    finding_id: uuid.UUID
    disposition_type: str
    corrective_action: str | None
    evidence_id: uuid.UUID | None
    closed_at: datetime | None
    closed_by_user_id: uuid.UUID | None
    created_at: datetime

    class Config:
        from_attributes = True


class FindingResponse(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    aircraft_id: uuid.UUID | None
    asset_id: uuid.UUID | None
    component_id: uuid.UUID | None
    inspection_requirement_id: uuid.UUID | None
    work_order_id: uuid.UUID | None
    task_id: uuid.UUID | None
    title: str
    description: str
    severity: str
    status: str
    discovered_at: datetime
    discovered_by_user_id: uuid.UUID | None
    responsible_user_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime
    dispositions: list[FindingDispositionResponse] = []

    class Config:
        from_attributes = True
