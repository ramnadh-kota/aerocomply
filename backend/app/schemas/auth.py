import uuid

from pydantic import BaseModel, EmailStr, Field


class RegisterOrganizationRequest(BaseModel):
    organization_name: str = Field(min_length=1, max_length=255)
    admin_email: EmailStr
    admin_full_name: str = Field(min_length=1, max_length=255)
    admin_password: str = Field(min_length=8, max_length=128)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


class CurrentUser(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    email: str
    full_name: str
    roles: list[str]
