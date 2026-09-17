import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError, UnauthorizedError
from app.core.permissions import Role
from app.core.security import (
    DUMMY_PASSWORD_HASH,
    InvalidTokenError,
    create_access_token,
    create_refresh_token,
    decode_token,
    generate_otp_code,
    hash_password,
    verify_password,
)
from app.models.auth_verification import AuthVerificationCode, VerificationPurpose
from app.models.organization import Organization, OrganizationStatus
from app.models.user import User, UserRole
from app.schemas.auth import RegisterOrganizationRequest, TokenResponse
from app.services.audit_service import record_audit_event
from app.services.email_service import send_verification_code_email

# Both OTP flows share these constants -- one shared authentication
# foundation, not a system per flow (see app/models/auth_verification.py).
OTP_TTL_MINUTES = 10
OTP_MAX_ATTEMPTS = 5
# Minimum time between two codes for the same user+purpose, enforced
# independent of (and in addition to) the per-IP rate_limit() dependency on
# the route -- see app/api/v1/auth.py. This is what makes "OTP resend" safe:
# resend reuses the same request-code endpoint, and this cooldown is what
# stops it being spammed.
OTP_RESEND_COOLDOWN_SECONDS = 60


def _roles_for_user(db: Session, user_id: uuid.UUID) -> list[str]:
    rows = db.execute(select(UserRole.role_name).where(UserRole.user_id == user_id)).scalars().all()
    return list(rows)


def _issue_tokens(user: User, roles: list[str]) -> TokenResponse:
    return TokenResponse(
        access_token=create_access_token(
            user.id,
            user.organization_id,
            roles,
            email=user.email,
            full_name=user.full_name,
            email_verified=user.email_verified,
        ),
        refresh_token=create_refresh_token(user.id, user.organization_id),
    )


def register_organization(db: Session, payload: RegisterOrganizationRequest) -> TokenResponse:
    """Bootstrap a new tenant: creates the Organization and its first ORG_ADMIN user."""
    existing = db.execute(
        select(User).where(User.email == payload.admin_email)
    ).scalar_one_or_none()
    if existing is not None:
        raise ConflictError("A user with this email already exists")

    org = Organization(name=payload.organization_name)
    db.add(org)
    db.flush()  # populate org.id

    user = User(
        organization_id=org.id,
        email=payload.admin_email,
        hashed_password=hash_password(payload.admin_password),
        full_name=payload.admin_full_name,
        is_active=True,
    )
    db.add(user)
    db.flush()

    db.add(UserRole(user_id=user.id, role_name=Role.ORG_ADMIN.value, organization_id=org.id))

    record_audit_event(
        db,
        organization_id=org.id,
        user_id=user.id,
        action="organization.register",
        entity_type="Organization",
        entity_id=org.id,
    )

    db.commit()
    return _issue_tokens(user, [Role.ORG_ADMIN.value])


def authenticate(db: Session, email: str, password: str) -> TokenResponse:
    user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    # M17.2: always run a real argon2 verify, even when no such user exists,
    # against a fixed dummy hash -- so a nonexistent email costs the same
    # wall-clock time as a wrong password for a real one. Without this, the
    # `user is None` short-circuit below would let response timing alone
    # reveal whether a given email is registered, regardless of the
    # response body already being identical either way.
    password_ok = verify_password(password, user.hashed_password if user else DUMMY_PASSWORD_HASH)
    if user is None or not user.is_active or not password_ok:
        raise UnauthorizedError("Invalid email or password")

    org = db.get(Organization, user.organization_id)
    if org is not None and org.status == OrganizationStatus.SUSPENDED:
        raise UnauthorizedError("This organization has been suspended")

    roles = _roles_for_user(db, user.id)

    record_audit_event(
        db,
        organization_id=user.organization_id,
        user_id=user.id,
        action="auth.login",
        entity_type="User",
        entity_id=user.id,
    )
    db.commit()

    return _issue_tokens(user, roles)


def refresh_access_token(db: Session, refresh_token: str) -> TokenResponse:
    try:
        payload = decode_token(refresh_token)
    except InvalidTokenError as exc:
        raise UnauthorizedError("Invalid or expired refresh token") from exc

    if payload.get("type") != "refresh":
        raise UnauthorizedError("Token is not a refresh token")

    user_id = uuid.UUID(payload["sub"])
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise UnauthorizedError("User no longer active")

    org = db.get(Organization, user.organization_id)
    if org is not None and org.status == OrganizationStatus.SUSPENDED:
        raise UnauthorizedError("This organization has been suspended")

    roles = _roles_for_user(db, user.id)
    return _issue_tokens(user, roles)


def _issue_code(db: Session, *, user: User, purpose: str) -> str:
    """Shared by both request_email_verification and request_password_reset
    -- generates, hashes, and persists one OTP, enforcing the resend
    cooldown against the most recent unconsumed code for this user+purpose."""
    latest = db.execute(
        select(AuthVerificationCode)
        .where(AuthVerificationCode.user_id == user.id, AuthVerificationCode.purpose == purpose)
        .order_by(AuthVerificationCode.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()
    if latest is not None and latest.consumed_at is None:
        elapsed = (datetime.now(UTC) - latest.created_at).total_seconds()
        if elapsed < OTP_RESEND_COOLDOWN_SECONDS:
            raise ConflictError(
                "A code was already sent recently. Please wait before requesting another.",
                code="otp_cooldown",
            )

    code = generate_otp_code()
    db.add(
        AuthVerificationCode(
            user_id=user.id,
            purpose=purpose,
            code_hash=hash_password(code),
            expires_at=datetime.now(UTC) + timedelta(minutes=OTP_TTL_MINUTES),
        )
    )
    return code


def _consume_code(db: Session, *, user: User, purpose: str, code: str) -> None:
    """Shared verification logic: look up the most recent unconsumed code
    for this user+purpose, enforce expiry and attempt limits, and mark it
    consumed on success. Raises UnauthorizedError on any failure -- the same
    generic error regardless of *why* the code was rejected (expired, wrong,
    already used, or missing entirely), so a response never becomes an
    oracle for which case occurred."""
    row = db.execute(
        select(AuthVerificationCode)
        .where(AuthVerificationCode.user_id == user.id, AuthVerificationCode.purpose == purpose)
        .order_by(AuthVerificationCode.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()

    invalid = UnauthorizedError("Invalid or expired code")

    if row is None or row.consumed_at is not None:
        raise invalid
    if row.attempts >= OTP_MAX_ATTEMPTS:
        raise invalid
    if row.expires_at < datetime.now(UTC):
        raise invalid

    if not verify_password(code, row.code_hash):
        row.attempts += 1
        db.add(row)
        db.commit()
        raise invalid

    row.consumed_at = datetime.now(UTC)
    db.add(row)


def request_email_verification(db: Session, *, user_id: uuid.UUID) -> None:
    user = db.get(User, user_id)
    if user is None:
        raise NotFoundError("User not found")
    if user.email_verified:
        raise ConflictError("Email is already verified", code="already_verified")

    code = _issue_code(db, user=user, purpose=VerificationPurpose.EMAIL_VERIFICATION)
    record_audit_event(
        db,
        organization_id=user.organization_id,
        user_id=user.id,
        action="auth.email_verification_requested",
        entity_type="User",
        entity_id=user.id,
    )
    db.commit()
    send_verification_code_email(to=user.email, code=code, purpose_label="Email verification")


def confirm_email_verification(db: Session, *, user_id: uuid.UUID, code: str) -> None:
    user = db.get(User, user_id)
    if user is None:
        raise NotFoundError("User not found")

    _consume_code(db, user=user, purpose=VerificationPurpose.EMAIL_VERIFICATION, code=code)
    user.email_verified = True
    db.add(user)
    record_audit_event(
        db,
        organization_id=user.organization_id,
        user_id=user.id,
        action="auth.email_verified",
        entity_type="User",
        entity_id=user.id,
    )
    db.commit()


def request_password_reset(db: Session, *, email: str) -> None:
    """Deliberately returns None (never raises, never reveals whether the
    email exists) -- the route always responds with the same generic
    message regardless of what happens here, matching this codebase's
    established anti-enumeration convention (see authenticate()'s
    DUMMY_PASSWORD_HASH comment)."""
    user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if user is None or not user.is_active:
        return

    try:
        code = _issue_code(db, user=user, purpose=VerificationPurpose.PASSWORD_RESET)
    except ConflictError:
        # Cooldown already covered by an earlier request -- still a no-op
        # from the caller's perspective, same as the "user is None" case.
        return

    record_audit_event(
        db,
        organization_id=user.organization_id,
        user_id=user.id,
        action="auth.password_reset_requested",
        entity_type="User",
        entity_id=user.id,
    )
    db.commit()
    send_verification_code_email(to=user.email, code=code, purpose_label="Password reset")


def reset_password(db: Session, *, email: str, code: str, new_password: str) -> None:
    user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if user is None or not user.is_active:
        # Same timing-parity technique as authenticate()'s DUMMY_PASSWORD_HASH:
        # still pay the cost of an argon2 verify before rejecting, so a
        # nonexistent/inactive email doesn't respond measurably faster than
        # a real one with a wrong code.
        verify_password(code, DUMMY_PASSWORD_HASH)
        raise UnauthorizedError("Invalid or expired code")

    _consume_code(db, user=user, purpose=VerificationPurpose.PASSWORD_RESET, code=code)
    user.hashed_password = hash_password(new_password)
    db.add(user)
    record_audit_event(
        db,
        organization_id=user.organization_id,
        user_id=user.id,
        action="auth.password_reset_completed",
        entity_type="User",
        entity_id=user.id,
    )
    db.commit()


def request_account_onboarding(db: Session, *, user_id: uuid.UUID) -> None:
    """Sent by platform tenant provisioning right after an invited admin
    user is created (see app/services/provisioning_service.py) -- reuses
    the exact same OTP machinery as email verification / password reset
    under the ACCOUNT_ONBOARDING purpose (see VerificationPurpose's
    docstring), not a new invitation system. Unlike
    request_email_verification, this is called by the platform admin
    (server-side), not the invited user themselves -- the invited user has
    no access token yet, since their account starts with a random,
    immediately-discarded password."""
    user = db.get(User, user_id)
    if user is None:
        raise NotFoundError("User not found")

    code = _issue_code(db, user=user, purpose=VerificationPurpose.ACCOUNT_ONBOARDING)
    record_audit_event(
        db,
        organization_id=user.organization_id,
        user_id=user.id,
        action="auth.onboarding_email_requested",
        entity_type="User",
        entity_id=user.id,
    )
    db.commit()
    send_verification_code_email(to=user.email, code=code, purpose_label="Account setup")


def complete_account_onboarding(db: Session, *, email: str, code: str, new_password: str) -> None:
    """The invited admin's own confirmation step (public endpoint, no
    bearer auth -- see app/api/v1/auth.py's /auth/onboarding/complete).
    Completing this proves the admin controls the invited email address
    (the same guarantee email_verification provides) AND lets them set
    their own first real password in one step, rather than requiring two
    separate OTP round trips for what is functionally one onboarding act
    -- see VerificationPurpose.ACCOUNT_ONBOARDING's docstring."""
    user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if user is None or not user.is_active:
        verify_password(code, DUMMY_PASSWORD_HASH)
        raise UnauthorizedError("Invalid or expired code")

    _consume_code(db, user=user, purpose=VerificationPurpose.ACCOUNT_ONBOARDING, code=code)
    user.hashed_password = hash_password(new_password)
    user.email_verified = True
    db.add(user)
    record_audit_event(
        db,
        organization_id=user.organization_id,
        user_id=user.id,
        action="auth.onboarding_completed",
        entity_type="User",
        entity_id=user.id,
    )
    db.commit()
