"""Shared authentication foundation: email verification + forgot/reset
password OTP.

ONE table (`AuthVerificationCode`) backs both flows rather than two
separate tables, because both are the exact same primitive at the data
level -- "issue a short-lived, single-use, hashed code that proves the
holder currently controls this user's registered email" -- and both are
consumed the same way (look up by user+purpose, verify hash, check
expiry/attempts, mark consumed). `purpose` is the only thing that differs.
This mirrors the milestone's core instruction: ONE authentication system
for every user (tenant or platform), not a system per role and not a
system per flow.

Deliberately NOT reusing app.models.audit_event.AuditEvent for this: an
audit event is an immutable historical record; a verification code is
live, mutable state (attempts increment, consumed_at gets set) that must
never appear in an audit trail's semantics. record_audit_event() is still
called by the service layer alongside this table for the historical side.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPKMixin


class VerificationPurpose:
    EMAIL_VERIFICATION = "email_verification"
    PASSWORD_RESET = "password_reset"
    # Phase 18.3: sent to an admin created via platform tenant provisioning
    # (see app/services/provisioning_service.py), whose account starts with
    # a random, immediately-discarded password (User.hashed_password is
    # NOT NULL, so some value must exist -- see that module's docstring).
    # Reuses the exact same _issue_code/_consume_code machinery as the two
    # purposes above under a third purpose rather than a new OTP system;
    # completing it (auth_service.complete_account_onboarding) both proves
    # the admin controls the invited email AND lets them set their own
    # first real password in one step.
    ACCOUNT_ONBOARDING = "account_onboarding"
    EMAIL_CHANGE = "email_change"


class AuthVerificationCode(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "auth_verification_codes"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    purpose: Mapped[str] = mapped_column(String(32), nullable=False)
    # Hashed via app.core.security.hash_password (argon2) -- the plaintext
    # OTP is only ever held in memory long enough to email it and hash it.
    code_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Wrong-code attempts against this specific code; a code is invalidated
    # (treated as if expired) once this exceeds MAX_VERIFY_ATTEMPTS in the
    # service layer, so brute-forcing a 6-digit code requires a fresh
    # request each time, which is itself rate-limited.
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
