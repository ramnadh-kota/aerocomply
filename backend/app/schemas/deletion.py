import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class AssetDeleteRequest(BaseModel):
    """Tenant-facing soft-delete request body. Optional -- a tenant is never
    required to explain a delete, but Platform Admin's deleted-records queue
    shows the reason when one was given."""

    reason: str | None = Field(default=None, max_length=500)


class OrganizationDeletionRequest(BaseModel):
    """Tenant Admin's POST /tenant/deletion-request body. Same optional-
    reason shape as AssetDeleteRequest -- consistent with the rest of this
    module, a tenant is never required to explain a delete."""

    reason: str | None = Field(default=None, max_length=500)


class WorkOrderDeleteRequest(BaseModel):
    """Tenant-facing soft-delete request body for DELETE /work-orders/{id}.
    Same optional-reason shape as AssetDeleteRequest."""

    reason: str | None = Field(default=None, max_length=500)


class DeletedRecordResponse(BaseModel):
    """One row in Platform Admin's soft-delete governance queue. Deliberately
    generic across entity_type ("ASSET" or "ORGANIZATION" today -- see
    restoration_service.list_deleted_records) so the same shape covers
    further soft-deletable entities later without a breaking change.
    asset_type is populated only for entity_type="ASSET"."""

    model_config = ConfigDict(from_attributes=True)

    entity_type: str
    entity_id: uuid.UUID
    organization_id: uuid.UUID
    identifier: str | None
    asset_type: str | None = None
    status: str
    deleted_at: datetime
    deleted_by: uuid.UUID | None
    deletion_reason: str | None
    restored_at: datetime | None = None
    restored_by: uuid.UUID | None = None


class DeletedRecordListResponse(BaseModel):
    items: list[DeletedRecordResponse]
    total: int
    limit: int
    offset: int


class PermanentDeleteRequest(BaseModel):
    """Permanent deletion is irreversible -- `confirm` must be explicitly
    true (never defaulted) so a client can't trigger it by omission, and
    `reason` is required (unlike the tenant-facing soft-delete, where it's
    optional) since this is the privileged, audited step the record's
    history stops at."""

    reason: str = Field(min_length=1, max_length=500)
    confirm: bool = Field(...)
