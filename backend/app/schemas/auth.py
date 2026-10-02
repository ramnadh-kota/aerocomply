import uuid

from pydantic import BaseModel, EmailStr, Field, computed_field

from app.core.permissions import permissions_for_roles


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
    email_verified: bool = False
    phone_number: str | None = None
    profile_photo_url: str | None = None
    pending_email: str | None = None
    # Display name of the caller's own organization (filled by /auth/me; None when built from a token).
    organization_name: str | None = None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def permissions(self) -> list[str]:
        """Effective RBAC permissions, derived from `roles` by the SAME function require_permission() uses, so the
        frontend (navigation / route guards) and the API can never disagree. Display aid only: the API enforces."""
        return sorted(permissions_for_roles(self.roles))


class UpdateProfileRequest(BaseModel):
    full_name: str | None = Field(default=None, min_length=1, max_length=255)
    phone_number: str | None = Field(default=None, max_length=32)


class RequestEmailChangeRequest(BaseModel):
    new_email: EmailStr


class ConfirmEmailChangeRequest(BaseModel):
    code: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")


class ConfirmEmailVerificationRequest(BaseModel):
    code: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    email: EmailStr
    code: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")
    new_password: str = Field(min_length=8, max_length=128)


class MessageResponse(BaseModel):
    message: str
