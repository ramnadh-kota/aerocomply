from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, get_db_session, require_permission
from app.core.permissions import Permission
from app.core.rate_limit import rate_limit
from app.schemas.auth import (
    ConfirmEmailChangeRequest,
    ConfirmEmailVerificationRequest,
    CurrentUser,
    ForgotPasswordRequest,
    LoginRequest,
    MessageResponse,
    RefreshRequest,
    RegisterOrganizationRequest,
    RequestEmailChangeRequest,
    ResetPasswordRequest,
    TokenResponse,
    UpdateProfileRequest,
)
from app.services import auth_service

router = APIRouter(prefix="/auth", tags=["auth"])

# M17.2: the three highest-risk unauthenticated endpoints in this router --
# credential-stuffing/brute-force against login, refresh-token guessing, and
# registration abuse -- each get their own independent per-IP budget. See
# app/core/rate_limit.py for the process-local-only limitation.
_AUTH_RATE_LIMIT = 20
_AUTH_RATE_WINDOW_SECONDS = 60

# Auth foundation (forgot password / email verification OTP): tighter than
# the general auth budget above, since these endpoints exist specifically to
# trigger an outbound email -- a much cheaper abuse target than a login
# attempt. Independent per-IP buckets, same rate_limit() primitive; the
# per-user resend cooldown (app/services/auth_service.py
# OTP_RESEND_COOLDOWN_SECONDS) is a second, independent layer on top of this.
_OTP_RATE_LIMIT = 5
_OTP_RATE_WINDOW_SECONDS = 300

# The *confirm* endpoints (verify-email/confirm, reset-password) don't send
# email, so they don't need the tight email-triggering budget above -- and
# they need enough headroom for a legitimate user to exhaust
# auth_service.OTP_MAX_ATTEMPTS (5) wrong guesses and then still submit the
# correct code within the same window. The per-code attempt counter in
# AuthVerificationCode is what actually bounds brute-forcing a 6-digit code,
# not this IP budget.
_OTP_CONFIRM_RATE_LIMIT = 15
_OTP_CONFIRM_RATE_WINDOW_SECONDS = 300


@router.post(
    "/register-organization",
    response_model=TokenResponse,
    status_code=201,
    dependencies=[
        Depends(
            rate_limit(
                "auth_register", limit=_AUTH_RATE_LIMIT, window_seconds=_AUTH_RATE_WINDOW_SECONDS
            )
        )
    ],
)
def register_organization(
    payload: RegisterOrganizationRequest,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.PLATFORM_MANAGE)),
) -> TokenResponse:
    # Gated to PLATFORM_MANAGE: this is a platform-administrative bootstrap
    # primitive, not a public signup endpoint. See /platform/organizations/provision
    # for the standard admin-initiated org+admin provisioning flow, which this
    # endpoint predates and is retained alongside for internal/test use.
    return auth_service.register_organization(db, payload)


@router.post(
    "/login",
    response_model=TokenResponse,
    dependencies=[
        Depends(
            rate_limit(
                "auth_login", limit=_AUTH_RATE_LIMIT, window_seconds=_AUTH_RATE_WINDOW_SECONDS
            )
        )
    ],
)
def login(payload: LoginRequest, db: Session = Depends(get_db_session)) -> TokenResponse:
    return auth_service.authenticate(db, payload.email, payload.password)


@router.post(
    "/refresh",
    response_model=TokenResponse,
    dependencies=[
        Depends(
            rate_limit(
                "auth_refresh", limit=_AUTH_RATE_LIMIT, window_seconds=_AUTH_RATE_WINDOW_SECONDS
            )
        )
    ],
)
def refresh(payload: RefreshRequest, db: Session = Depends(get_db_session)) -> TokenResponse:
    return auth_service.refresh_access_token(db, payload.refresh_token)


@router.get("/me", response_model=CurrentUser)
def me(
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db_session),
) -> CurrentUser:
    return auth_service.get_user_profile(db, user_id=current_user.id)


@router.patch("/me", response_model=CurrentUser)
def update_me(
    payload: UpdateProfileRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db_session),
) -> CurrentUser:
    return auth_service.update_user_profile(
        db,
        user_id=current_user.id,
        full_name=payload.full_name,
        phone_number=payload.phone_number,
    )


@router.post("/me/photo", response_model=CurrentUser)
async def upload_photo(
    file: UploadFile = File(...),
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db_session),
) -> CurrentUser:
    content = await file.read()
    return auth_service.upload_profile_photo(
        db,
        user_id=current_user.id,
        content=content,
        content_type=file.content_type or "application/octet-stream",
        filename=file.filename or "avatar.png",
    )


@router.delete("/me/photo", response_model=CurrentUser)
def delete_photo(
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db_session),
) -> CurrentUser:
    return auth_service.delete_profile_photo(db, user_id=current_user.id)


@router.post(
    "/me/change-email/request",
    response_model=MessageResponse,
    dependencies=[
        Depends(
            rate_limit(
                "auth_change_email_request",
                limit=_OTP_RATE_LIMIT,
                window_seconds=_OTP_RATE_WINDOW_SECONDS,
            )
        )
    ],
)
def request_email_change(
    payload: RequestEmailChangeRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db_session),
) -> MessageResponse:
    auth_service.request_email_change(
        db, user_id=current_user.id, new_email=payload.new_email
    )
    return MessageResponse(
        message=f"Verification code sent to {payload.new_email}. Confirm code to complete update."
    )


@router.post(
    "/me/change-email/confirm",
    response_model=CurrentUser,
    dependencies=[
        Depends(
            rate_limit(
                "auth_change_email_confirm",
                limit=_OTP_CONFIRM_RATE_LIMIT,
                window_seconds=_OTP_CONFIRM_RATE_WINDOW_SECONDS,
            )
        )
    ],
)
def confirm_email_change(
    payload: ConfirmEmailChangeRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db_session),
) -> CurrentUser:
    return auth_service.confirm_email_change(
        db, user_id=current_user.id, code=payload.code
    )


@router.post("/me/change-email/cancel", response_model=CurrentUser)
def cancel_email_change(
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db_session),
) -> CurrentUser:
    return auth_service.cancel_email_change(db, user_id=current_user.id)


@router.post(
    "/verify-email/request",
    response_model=MessageResponse,
    dependencies=[
        Depends(
            rate_limit(
                "auth_verify_email_request",
                limit=_OTP_RATE_LIMIT,
                window_seconds=_OTP_RATE_WINDOW_SECONDS,
            )
        )
    ],
)
def request_email_verification(
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db_session),
) -> MessageResponse:
    auth_service.request_email_verification(db, user_id=current_user.id)
    return MessageResponse(message="A verification code has been sent to your email.")


@router.post(
    "/verify-email/confirm",
    response_model=MessageResponse,
    dependencies=[
        Depends(
            rate_limit(
                "auth_verify_email_confirm",
                limit=_OTP_CONFIRM_RATE_LIMIT,
                window_seconds=_OTP_CONFIRM_RATE_WINDOW_SECONDS,
            )
        )
    ],
)
def confirm_email_verification(
    payload: ConfirmEmailVerificationRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db_session),
) -> MessageResponse:
    auth_service.confirm_email_verification(db, user_id=current_user.id, code=payload.code)
    return MessageResponse(message="Email verified.")


@router.post(
    "/forgot-password",
    response_model=MessageResponse,
    dependencies=[
        Depends(
            rate_limit(
                "auth_forgot_password",
                limit=_OTP_RATE_LIMIT,
                window_seconds=_OTP_RATE_WINDOW_SECONDS,
            )
        )
    ],
)
def forgot_password(
    payload: ForgotPasswordRequest, db: Session = Depends(get_db_session)
) -> MessageResponse:
    # Always the same response regardless of whether the email exists --
    # auth_service.request_password_reset() is a deliberate no-op silently
    # for a nonexistent/inactive account (see its own docstring).
    auth_service.request_password_reset(db, email=payload.email)
    return MessageResponse(message="If that email is registered, a reset code has been sent.")


@router.post(
    "/reset-password",
    response_model=MessageResponse,
    dependencies=[
        Depends(
            rate_limit(
                "auth_reset_password",
                limit=_OTP_CONFIRM_RATE_LIMIT,
                window_seconds=_OTP_CONFIRM_RATE_WINDOW_SECONDS,
            )
        )
    ],
)
def reset_password(
    payload: ResetPasswordRequest, db: Session = Depends(get_db_session)
) -> MessageResponse:
    auth_service.reset_password(
        db, email=payload.email, code=payload.code, new_password=payload.new_password
    )
    return MessageResponse(message="Password has been reset. You can now sign in.")


@router.post(
    "/onboarding/complete",
    response_model=MessageResponse,
    dependencies=[
        Depends(
            rate_limit(
                "auth_onboarding_complete",
                limit=_OTP_CONFIRM_RATE_LIMIT,
                window_seconds=_OTP_CONFIRM_RATE_WINDOW_SECONDS,
            )
        )
    ],
)
def complete_onboarding(
    payload: ResetPasswordRequest, db: Session = Depends(get_db_session)
) -> MessageResponse:
    # Reuses ResetPasswordRequest's exact shape (email, code, new_password)
    # -- completing platform-provisioned onboarding is the same primitive
    # as a password reset (prove code ownership, then set a password), see
    # auth_service.complete_account_onboarding's docstring.
    auth_service.complete_account_onboarding(
        db, email=payload.email, code=payload.code, new_password=payload.new_password
    )
    return MessageResponse(message="Account set up. You can now sign in.")
