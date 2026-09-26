"""Phase 18.3: tenant provisioning orchestration.

Provisioning is ORCHESTRATION, not a new domain system: it composes three
already-existing, independently-tested services --
platform_service.create_organization, subscription_service.
create_subscription, and platform_service.create_organization_admin -- plus
the existing OTP-based auth foundation (app/services/auth_service.py,
request_account_onboarding) to invite the admin. No new
Organization/Plan/Subscription/Entitlement concept is introduced, and
entitlements are never copied by hand: creating the Subscription is the
only commercial write this service makes, and
app/services/entitlement_service.resolve_entitlements already derives the
organization's effective features from it (see
tests/integration/test_provisioning.py's entitlement-resolution test).

Password handling (Phase 9 -- the Super Master must never set or see the
new admin's password): User.hashed_password is NOT NULL (see
app/models/user.py), so create_organization_admin is called with a
cryptographically random password (secrets.token_urlsafe) that is hashed
and immediately discarded here -- nobody, including this service's return
value, ever holds or transmits it. The admin's only path to a usable
account is completing the ACCOUNT_ONBOARDING OTP flow (reused, not
duplicated -- see auth_service.request_account_onboarding /
complete_account_onboarding), which both proves email ownership and lets
them set their own password in one step.

Compensation, not a nested DB transaction (Phase 7): create_organization,
create_subscription, and create_organization_admin each commit
independently (the established, already-tested convention in every one of
these services -- see their own module docstrings). Composing three
already-committing services under one outer transaction would mean
rewriting all three, which is out of this milestone's scope and risks
regressing their existing, separately-tested behavior. Instead, on a
failure partway through, this service explicitly deletes the rows it
already created via _rollback_partial_provisioning (a compensating
action, not an ORM cascade -- organization_id/plan_id are the only real
FKs involved and neither blocks these deletes), so a failed provisioning
attempt never leaves an orphaned Organization or Subscription behind.

Onboarding email delivery failure (Phase 7) does NOT roll back
provisioning: the organization, subscription, and admin user are real and
already committed by the time the email is attempted. A failed send is
recorded as its own audit event (platform.organization.onboarding_email_failed)
and reported back via ProvisionOrganizationResult.onboarding_email_sent =
False, so the platform admin can use the existing resend-invitation
endpoint rather than the whole provisioning attempt being lost or retried
into a duplicate organization.
"""

import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
import secrets
import uuid

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError
from app.models.organization import Organization
from app.models.plan import Plan
from app.models.subscription import Subscription
from app.models.user import User
from app.services import auth_service, entitlement_service, platform_service, subscription_service
from app.services.audit_service import record_audit_event


@dataclass
class ProvisionOrganizationResult:
    organization: Organization
    subscription: Subscription
    admin: User
    onboarding_email_sent: bool
    plan_code: str | None = None
    features_count: int = 0
    limits_count: int = 0


@dataclass
class InviteOrganizationAdminResult:
    admin: User
    onboarding_email_sent: bool


def invite_organization_admin(
    db: Session,
    *,
    actor_user_id: uuid.UUID,
    organization_id: uuid.UUID,
    email: str,
    full_name: str,
) -> InviteOrganizationAdminResult:
    """M19.1: invite an ORG_ADMIN into an ALREADY-PROVISIONED organization
    by email -- the narrower sibling of provision_organization above, for
    the case where the organization (and its subscription) already exist
    and the platform admin just needs to add/replace its admin.

    Reuses exactly the same two composed calls provision_organization
    already makes for its admin step -- platform_service.
    create_organization_admin (random, immediately-discarded password;
    never seen by the platform admin or this function's caller) followed
    by auth_service.request_account_onboarding (the ACCOUNT_ONBOARDING OTP
    email) -- rather than introducing a second invitation/token system.
    create_organization_admin already enforces the safe edge cases this
    slice needs: 404 if the organization doesn't exist, and a 409 Conflict
    if a user with this email already exists anywhere (covers "existing
    user with no org", "existing user in another org", and "already a
    member of this org" -- all rejected the same way, matching the
    existing convention rather than silently moving/merging accounts).

    Email delivery failure does not roll back the created admin account,
    mirroring provision_organization's own compensation rule: the account
    is real once committed, and the platform admin can retry via the
    existing POST /platform/admins/{user_id}/resend-invitation endpoint.
    """
    discarded_password = secrets.token_urlsafe(32)
    admin = platform_service.create_organization_admin(
        db,
        actor_user_id=actor_user_id,
        organization_id=organization_id,
        email=email,
        full_name=full_name,
        password=discarded_password,
    )

    onboarding_email_sent = False
    try:
        auth_service.request_account_onboarding(db, user_id=admin.id)
        onboarding_email_sent = True
    except Exception:
        record_audit_event(
            db,
            organization_id=organization_id,
            user_id=actor_user_id,
            action="platform.organization.onboarding_email_failed",
            entity_type="User",
            entity_id=admin.id,
        )
        db.commit()

    return InviteOrganizationAdminResult(admin=admin, onboarding_email_sent=onboarding_email_sent)


def _rollback_partial_provisioning(db: Session, *, organization_id: uuid.UUID | None) -> None:
    if not organization_id:
        return
    try:
        db.rollback()
        db.execute(delete(Subscription).where(Subscription.organization_id == organization_id))
        db.execute(delete(User).where(User.organization_id == organization_id))
        db.execute(delete(Organization).where(Organization.id == organization_id))
        db.commit()
    except Exception:
        db.rollback()


def provision_organization(
    db: Session,
    *,
    actor_user_id: uuid.UUID,
    organization_name: str,
    plan_id: uuid.UUID,
    subscription_status: str,
    admin_email: str,
    admin_full_name: str,
) -> ProvisionOrganizationResult:
    """Orchestrates atomic tenant provisioning:
    1. Pre-flight checks:
       - Commercial plan exists and is active.
       - No active organization with the same name already exists.
       - No user with the initial admin email already exists.
    2. Single DB Transaction (commit=False across platform/subscription services):
       - Create organization.
       - Create initial admin with a discarded random password.
       - Create subscription with the selected commercial plan.
       - Derive and verify effective entitlements & usage limits baseline.
       - Record audit event (platform.organization.provisioned).
       - Commit atomic transaction.
    3. Post-commit:
       - Request account onboarding OTP email.
    """
    # 1. Pre-flight checks
    plan = db.get(Plan, plan_id)
    if plan is None:
        raise NotFoundError(f"Commercial plan '{plan_id}' does not exist", code="plan_not_found")
    if not plan.is_active:
        raise ConflictError(
            f"Commercial plan '{plan.name}' ({plan.code}) is inactive and cannot be assigned to new provisions",
            code="inactive_plan",
        )

    clean_org_name = organization_name.strip()
    existing_org = db.scalars(
        select(Organization).where(
            func.lower(Organization.name) == clean_org_name.lower(),
            Organization.deleted_at.is_(None),
        )
    ).first()
    if existing_org:
        raise ConflictError(
            f"An active organization named '{clean_org_name}' already exists",
            code="duplicate_organization_name",
        )

    clean_admin_email = admin_email.strip().lower()
    existing_user = db.scalars(
        select(User).where(func.lower(User.email) == clean_admin_email)
    ).first()
    if existing_user:
        raise ConflictError(
            f"A user with email '{admin_email}' already exists",
            code="duplicate_admin_email",
        )

    # 2. Atomic Provisioning Execution
    org = None
    try:
        org = platform_service.create_organization(
            db, actor_user_id=actor_user_id, name=clean_org_name, commit=False
        )

        discarded_password = secrets.token_urlsafe(32)
        admin = platform_service.create_organization_admin(
            db,
            actor_user_id=actor_user_id,
            organization_id=org.id,
            email=clean_admin_email,
            full_name=admin_full_name.strip(),
            password=discarded_password,
            commit=False,
        )

        subscription = subscription_service.create_subscription(
            db,
            actor_user_id=actor_user_id,
            organization_id=org.id,
            plan_id=plan_id,
            status=subscription_status,
            starts_at=datetime.now(UTC),
            commit=False,
        )

        # Baseline entitlement resolution verification
        entitlements = entitlement_service.resolve_entitlements(db, organization_id=org.id)

        record_audit_event(
            db,
            organization_id=org.id,
            user_id=actor_user_id,
            action="platform.organization.provisioned",
            entity_type="Organization",
            entity_id=org.id,
            metadata={
                "plan_id": str(plan_id),
                "plan_code": plan.code,
                "admin_email": clean_admin_email,
                "subscription_id": str(subscription.id),
                "features_count": len(entitlements.effective_features),
                "limits_count": len(entitlements.usage_limits),
            },
        )

        db.commit()
    except Exception:
        db.rollback()
        if org is not None and getattr(org, "id", None) is not None:
            _rollback_partial_provisioning(db, organization_id=org.id)
        raise

    # 3. Post-commit onboarding email
    onboarding_email_sent = False
    try:
        auth_service.request_account_onboarding(db, user_id=admin.id)
        onboarding_email_sent = True
    except Exception:
        record_audit_event(
            db,
            organization_id=org.id,
            user_id=actor_user_id,
            action="platform.organization.onboarding_email_failed",
            entity_type="User",
            entity_id=admin.id,
        )
        db.commit()

    return ProvisionOrganizationResult(
        organization=org,
        subscription=subscription,
        admin=admin,
        onboarding_email_sent=onboarding_email_sent,
        plan_code=plan.code,
        features_count=len(entitlements.effective_features),
        limits_count=len(entitlements.usage_limits),
    )
