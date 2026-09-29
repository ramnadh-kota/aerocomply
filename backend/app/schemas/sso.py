"""Schemas for M13 Phase 4 Enterprise Identity & SSO."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class SSOConfigurationBase(BaseModel):
    provider_type: str = "ENTRA_ID"
    issuer_url: str = Field(..., max_length=512)
    client_id: str = Field(..., max_length=255)
    tenant_id: str | None = Field(None, max_length=255)
    is_active: bool = True
    enforce_sso: bool = False
    default_role: str = "VIEWER"
    domain_hint: str | None = Field(None, max_length=255)
    role_mappings: dict[str, Any] = Field(default_factory=dict)


class SSOConfigurationCreate(SSOConfigurationBase):
    client_secret: str | None = None


class SSOConfigurationUpdate(BaseModel):
    issuer_url: str | None = Field(None, max_length=512)
    client_id: str | None = Field(None, max_length=255)
    client_secret: str | None = None
    tenant_id: str | None = Field(None, max_length=255)
    is_active: bool | None = None
    enforce_sso: bool | None = None
    default_role: str | None = None
    domain_hint: str | None = None
    role_mappings: dict[str, Any] | None = None


class SSOConfigurationResponse(SSOConfigurationBase):
    id: uuid.UUID
    organization_id: uuid.UUID
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class SSOAuthorizeRequest(BaseModel):
    organization_name: str | None = None
    organization_id: uuid.UUID | None = None
    redirect_uri: str
    state: str | None = None


class SSOAuthorizeResponse(BaseModel):
    authorization_url: str
    state: str
    nonce: str


class SSOCallbackRequest(BaseModel):
    organization_id: uuid.UUID | None = None
    state: str
    code: str | None = None
    id_token: str | None = None
    redirect_uri: str | None = None


class ExternalIdentityMappingResponse(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    user_id: uuid.UUID
    provider_type: str
    issuer: str
    subject: str
    email: str
    is_active: bool
    last_authenticated_at: datetime | None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)
