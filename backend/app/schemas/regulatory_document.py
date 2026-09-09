import datetime
import uuid

from pydantic import BaseModel, Field


class RegulatoryDocumentCreateRequest(BaseModel):
    authority: str = Field(max_length=16)
    doc_type: str = Field(max_length=16)
    doc_number: str = Field(min_length=1, max_length=64)
    title: str = Field(min_length=1, max_length=255)
    revision: str | None = Field(default=None, max_length=32)
    publication_date: datetime.date | None = None
    effective_date: datetime.date | None = None
    source_status: str = Field(default="PUBLISHED", max_length=16)
    source_url: str | None = Field(default=None, max_length=512)


class RegulatoryDocumentResponse(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    authority: str
    doc_type: str
    doc_number: str
    title: str
    revision: str | None
    publication_date: datetime.date | None
    effective_date: datetime.date | None
    source_status: str
    source_url: str | None
    sync_status: str

    class Config:
        from_attributes = True


class RegulatoryProviderStatus(BaseModel):
    authority: str
    status: str
    reason: str
