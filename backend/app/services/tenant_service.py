import uuid
from datetime import UTC, datetime

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, ForbiddenError, NotFoundError
from app.core.permissions import ROLE_PERMISSIONS, Role
from app.core.security import hash_password
from app.models.asset import Asset
from app.models.audit_event import AuditEvent
from app.models.auth_verification import AuthVerificationCode, VerificationPurpose
from app.models.facility import Facility
from app.models.organization import Organization
from app.models.user import User, UserRole
from app.schemas.tenant import (
    TenantDashboardAttentionItem,
    TenantDashboardResponse,
    TenantInvitationRequest,
    TenantInvitationResponse,
    TenantProfileResponse,
    TenantProfileUpdateRequest,
    TenantRoleInfo,
    TenantSettingsResponse,
    TenantSettingsUpdateRequest,
    TenantTeamMember,
    TenantTeamResponse,
    TenantUsageMetricItem,
    TenantUsageResponse,
    TenantUserResponse,
)
from app.services import auth_service
from app.services.audit_service import record_audit_event
from app.services.entitlement_service import resolve_entitlements

# Supported customer tenant roles (PLATFORM_ADMIN, PLATFORM_STAFF are strictly excluded)
SUPPORTED_TENANT_ROLES: list[Role] = [
    Role.ORG_ADMIN,
    Role.CAMO_MANAGER,
    Role.COMPLIANCE_MANAGER,
    Role.QUALITY_MANAGER,
    Role.MAINTENANCE_ENGINEER,
    Role.VIEWER,
]

ROLE_DESCRIPTIONS: dict[Role, str] = {
    Role.ORG_ADMIN: "Full administrative authority over the customer organization, users, and operational configuration.",
    Role.CAMO_MANAGER: "Continuing Airworthiness Management Organization lead; oversees maintenance scheduling, fleet reliability, and work orders.",
    Role.COMPLIANCE_MANAGER: "Regulatory compliance officer; oversees assessment frameworks, regulatory registries, and audit readiness.",
    Role.QUALITY_MANAGER: "Quality assurance manager; inspects maintenance findings, RII approvals, and safety governance.",
    Role.MAINTENANCE_ENGINEER: "Licensed maintenance personnel; signs off tasks, uploads documentary evidence, and executes work orders.",
    Role.VIEWER: "Read-only stakeholder access to fleet health, documentation, and compliance status.",
}


def get_tenant_profile(db: Session, *, organization_id: uuid.UUID) -> TenantProfileResponse:
    org = db.get(Organization, organization_id)
    if org is None:
        raise NotFoundError("Organization not found")

    # Primary contact is the earliest created ORG_ADMIN or user
    primary_user = db.execute(
        select(User)
        .where(User.organization_id == organization_id)
        .order_by(User.created_at.asc())
        .limit(1)
    ).scalar_one_or_none()

    return TenantProfileResponse(
        id=org.id,
        name=org.name,
        status=org.status,
        industry=org.industry,
        created_at=org.created_at,
        primary_contact_email=primary_user.email if primary_user else None,
        primary_contact_name=primary_user.full_name if primary_user else None,
    )


def update_tenant_profile(
    db: Session,
    *,
    organization_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    payload: TenantProfileUpdateRequest,
) -> TenantProfileResponse:
    org = db.get(Organization, organization_id)
    if org is None:
        raise NotFoundError("Organization not found")

    changes: dict[str, str] = {}
    if payload.name is not None and payload.name.strip():
        old_name = org.name
        org.name = payload.name.strip()
        changes["name"] = f"{old_name} -> {org.name}"

    if payload.industry is not None:
        old_ind = org.industry
        org.industry = payload.industry
        changes["industry"] = f"{old_ind} -> {org.industry}"

    if changes:
        record_audit_event(
            db,
            organization_id=organization_id,
            user_id=actor_user_id,
            action="tenant.profile.updated",
            entity_type="Organization",
            entity_id=organization_id,
            metadata=changes,
        )
        db.commit()
        db.refresh(org)

    return get_tenant_profile(db, organization_id=organization_id)


def get_tenant_settings(db: Session, *, organization_id: uuid.UUID) -> TenantSettingsResponse:
    # Organization-level operational settings defaults
    org = db.get(Organization, organization_id)
    if org is None:
        raise NotFoundError("Organization not found")

    default_asset = "DRONE" if org.industry == "DRONE_UAV" else "AIRCRAFT"
    return TenantSettingsResponse(
        organization_id=organization_id,
        timezone="UTC",
        operational_mode="STANDARD",
        default_asset_type=default_asset,
        notification_email=None,
    )


def update_tenant_settings(
    db: Session,
    *,
    organization_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    payload: TenantSettingsUpdateRequest,
) -> TenantSettingsResponse:
    org = db.get(Organization, organization_id)
    if org is None:
        raise NotFoundError("Organization not found")

    record_audit_event(
        db,
        organization_id=organization_id,
        user_id=actor_user_id,
        action="tenant.settings.updated",
        entity_type="Organization",
        entity_id=organization_id,
        metadata={k: str(v) for k, v in payload.model_dump(exclude_unset=True).items()},
    )
    db.commit()

    return TenantSettingsResponse(
        organization_id=organization_id,
        timezone=payload.timezone or "UTC",
        operational_mode=payload.operational_mode or "STANDARD",
        default_asset_type=payload.default_asset_type or "AIRCRAFT",
        notification_email=payload.notification_email,
    )


def list_tenant_users(db: Session, *, organization_id: uuid.UUID) -> list[TenantUserResponse]:
    users = list(
        db.execute(
            select(User)
            .where(User.organization_id == organization_id)
            .order_by(User.created_at.asc())
        )
        .scalars()
        .all()
    )

    roles_by_user: dict[uuid.UUID, list[str]] = {}
    for user_id, role_name in db.execute(
        select(UserRole.user_id, UserRole.role_name).where(
            UserRole.organization_id == organization_id
        )
    ).all():
        roles_by_user.setdefault(user_id, []).append(role_name)

    return [
        TenantUserResponse(
            id=u.id,
            email=u.email,
            full_name=u.full_name,
            is_active=u.is_active,
            roles=roles_by_user.get(u.id, []),
            created_at=u.created_at,
        )
        for u in users
    ]


def get_tenant_user(
    db: Session, *, organization_id: uuid.UUID, user_id: uuid.UUID
) -> TenantUserResponse:
    user = db.get(User, user_id)
    if user is None or user.organization_id != organization_id:
        raise NotFoundError("User not found in this organization")

    roles = list(
        db.execute(
            select(UserRole.role_name).where(
                UserRole.user_id == user_id, UserRole.organization_id == organization_id
            )
        )
        .scalars()
        .all()
    )

    return TenantUserResponse(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        is_active=user.is_active,
        roles=roles,
        created_at=user.created_at,
    )


def update_tenant_user_roles(
    db: Session,
    *,
    organization_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    user_id: uuid.UUID,
    roles: list[str],
) -> TenantUserResponse:
    user = db.get(User, user_id)
    if user is None or user.organization_id != organization_id:
        raise NotFoundError("User not found in this organization")

    # Disallow assigning platform roles or invalid roles
    allowed_role_names = {r.value for r in SUPPORTED_TENANT_ROLES}
    for r in roles:
        if r not in allowed_role_names:
            raise ForbiddenError(
                f"Role '{r}' cannot be assigned by Tenant Administrator. "
                "Only customer tenant roles may be assigned."
            )

    # Safety check: if removing ORG_ADMIN, ensure at least one other active ORG_ADMIN remains
    current_roles = set(
        db.execute(
            select(UserRole.role_name).where(
                UserRole.user_id == user_id, UserRole.organization_id == organization_id
            )
        )
        .scalars()
        .all()
    )
    if Role.ORG_ADMIN.value in current_roles and Role.ORG_ADMIN.value not in roles:
        other_admins = db.execute(
            select(func.count(UserRole.user_id)).where(
                UserRole.organization_id == organization_id,
                UserRole.role_name == Role.ORG_ADMIN.value,
                UserRole.user_id != user_id,
            )
        ).scalar_one()
        if other_admins == 0:
            raise ConflictError("Cannot remove the only Organization Administrator.")

    # Replace user roles
    db.execute(
        delete(UserRole).where(
            UserRole.user_id == user_id, UserRole.organization_id == organization_id
        )
    )
    for r in roles:
        db.add(UserRole(user_id=user_id, role_name=r, organization_id=organization_id))

    record_audit_event(
        db,
        organization_id=organization_id,
        user_id=actor_user_id,
        action="tenant.user.roles_updated",
        entity_type="User",
        entity_id=user_id,
        metadata={"previous_roles": list(current_roles), "new_roles": roles},
    )
    db.commit()

    return get_tenant_user(db, organization_id=organization_id, user_id=user_id)


def update_tenant_user_status(
    db: Session,
    *,
    organization_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    user_id: uuid.UUID,
    is_active: bool,
) -> TenantUserResponse:
    user = db.get(User, user_id)
    if user is None or user.organization_id != organization_id:
        raise NotFoundError("User not found in this organization")

    if user_id == actor_user_id and not is_active:
        raise ConflictError("You cannot deactivate your own account.")

    old_status = user.is_active
    user.is_active = is_active
    db.add(user)

    record_audit_event(
        db,
        organization_id=organization_id,
        user_id=actor_user_id,
        action="tenant.user.status_updated",
        entity_type="User",
        entity_id=user_id,
        metadata={"is_active": is_active, "previous_status": old_status},
    )
    db.commit()

    return get_tenant_user(db, organization_id=organization_id, user_id=user_id)


def list_tenant_roles() -> list[TenantRoleInfo]:
    result: list[TenantRoleInfo] = []
    for r in SUPPORTED_TENANT_ROLES:
        perms = sorted([p.value for p in ROLE_PERMISSIONS.get(r, set())])
        result.append(
            TenantRoleInfo(
                role_name=r.value,
                display_name=r.value.replace("_", " ").title(),
                description=ROLE_DESCRIPTIONS.get(r, ""),
                permissions=perms,
                is_system_role=True,
            )
        )
    return result


def list_tenant_invitations(
    db: Session, *, organization_id: uuid.UUID
) -> list[TenantInvitationResponse]:
    # Pending/recent onboarding codes for users in this tenant
    now = datetime.now(UTC)
    stmt = (
        select(AuthVerificationCode, User)
        .join(User, AuthVerificationCode.user_id == User.id)
        .where(
            User.organization_id == organization_id,
            AuthVerificationCode.purpose == VerificationPurpose.ACCOUNT_ONBOARDING,
        )
        .order_by(AuthVerificationCode.created_at.desc())
    )

    rows = db.execute(stmt).all()
    results: list[TenantInvitationResponse] = []
    seen_users: set[uuid.UUID] = set()

    for code, user in rows:
        if user.id in seen_users:
            continue
        seen_users.add(user.id)

        user_role = (
            db.execute(
                select(UserRole.role_name).where(
                    UserRole.user_id == user.id, UserRole.organization_id == organization_id
                )
            ).scalar_one_or_none()
            or Role.VIEWER.value
        )

        if code.consumed_at is not None:
            status = "ACCEPTED" if user.email_verified else "CANCELLED"
            can_resend = False
            can_cancel = False
        elif now > code.expires_at:
            status = "EXPIRED"
            can_resend = True
            can_cancel = False
        else:
            status = "PENDING"
            can_resend = True
            can_cancel = True

        results.append(
            TenantInvitationResponse(
                id=code.id,
                user_id=user.id,
                email=user.email,
                full_name=user.full_name,
                role=user_role,
                status=status,
                created_at=code.created_at,
                expires_at=code.expires_at,
                can_resend=can_resend,
                can_cancel=can_cancel,
            )
        )

    return results


def invite_tenant_user(
    db: Session,
    *,
    organization_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    payload: TenantInvitationRequest,
) -> TenantInvitationResponse:
    # Disallow platform roles
    allowed_roles = {r.value for r in SUPPORTED_TENANT_ROLES}
    if payload.role not in allowed_roles:
        raise ForbiddenError(f"Role '{payload.role}' cannot be assigned in customer invitations.")

    # Check for existing email in tenant
    existing_user = db.execute(
        select(User).where(User.email == payload.email, User.organization_id == organization_id)
    ).scalar_one_or_none()

    if existing_user is not None:
        raise ConflictError(f"User with email '{payload.email}' already exists in this organization.")

    # Create user with a random unhashed password (discarded immediately)
    dummy_pass = str(uuid.uuid4())
    new_user = User(
        organization_id=organization_id,
        email=payload.email,
        full_name=payload.full_name,
        hashed_password=hash_password(dummy_pass),
        is_active=True,
        email_verified=False,
    )
    db.add(new_user)
    db.flush()

    # Assign role
    db.add(
        UserRole(
            user_id=new_user.id,
            role_name=payload.role,
            organization_id=organization_id,
        )
    )

    # Trigger onboarding OTP
    auth_service.request_account_onboarding(db, user_id=new_user.id)

    record_audit_event(
        db,
        organization_id=organization_id,
        user_id=actor_user_id,
        action="tenant.user.invited",
        entity_type="User",
        entity_id=new_user.id,
        metadata={"email": payload.email, "role": payload.role},
    )
    db.commit()

    # Retrieve code
    latest_code = db.execute(
        select(AuthVerificationCode)
        .where(
            AuthVerificationCode.user_id == new_user.id,
            AuthVerificationCode.purpose == VerificationPurpose.ACCOUNT_ONBOARDING,
        )
        .order_by(AuthVerificationCode.created_at.desc())
        .limit(1)
    ).scalar_one()

    return TenantInvitationResponse(
        id=latest_code.id,
        user_id=new_user.id,
        email=new_user.email,
        full_name=new_user.full_name,
        role=payload.role,
        status="PENDING",
        created_at=latest_code.created_at,
        expires_at=latest_code.expires_at,
        can_resend=True,
        can_cancel=True,
    )


def resend_tenant_invitation(
    db: Session,
    *,
    organization_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    user_id: uuid.UUID,
) -> None:
    user = db.get(User, user_id)
    if user is None or user.organization_id != organization_id:
        raise NotFoundError("User not found in this organization")

    auth_service.request_account_onboarding(db, user_id=user.id)
    record_audit_event(
        db,
        organization_id=organization_id,
        user_id=actor_user_id,
        action="tenant.user.invitation_resent",
        entity_type="User",
        entity_id=user.id,
    )
    db.commit()


def cancel_tenant_invitation(
    db: Session,
    *,
    organization_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    user_id: uuid.UUID,
) -> None:
    user = db.get(User, user_id)
    if user is None or user.organization_id != organization_id:
        raise NotFoundError("User not found in this organization")

    auth_service.revoke_account_onboarding(db, actor_user_id=actor_user_id, user_id=user.id)


def get_tenant_teams(db: Session, *, organization_id: uuid.UUID) -> list[TenantTeamResponse]:
    # Resolve personnel by functional team mapping from UserRole and User
    users = list_tenant_users(db, organization_id=organization_id)

    team_definitions = [
        {
            "id": "team-flight-ops",
            "name": "Flight Operations",
            "description": "Pilots, flight crew, and dispatch officers responsible for missions and aircraft readiness.",
            "lead_role": "CHIEF_PILOT",
            "roles": {"PILOT", "CHIEF_PILOT"},
        },
        {
            "id": "team-maintenance",
            "name": "Maintenance & CAMO",
            "description": "CAMO managers, licensed engineers, and technicians executing work orders and AOG recovery.",
            "lead_role": "CAMO_MANAGER",
            "roles": {"CAMO_MANAGER", "MAINTENANCE_ENGINEER", "TECHNICIAN"},
        },
        {
            "id": "team-inspection",
            "name": "Quality & Inspection",
            "description": "Quality assurance inspectors performing RII sign-offs and maintenance verification.",
            "lead_role": "QUALITY_MANAGER",
            "roles": {"QUALITY_MANAGER", "INSPECTOR"},
        },
        {
            "id": "team-compliance",
            "name": "Regulatory & Safety Compliance",
            "description": "Compliance managers auditing requirements against CAA, EASA, and FAA frameworks.",
            "lead_role": "COMPLIANCE_MANAGER",
            "roles": {"COMPLIANCE_MANAGER"},
        },
        {
            "id": "team-admin",
            "name": "Organization Administration",
            "description": "Tenant administrators managing personnel, commercial plans, facilities, and access.",
            "lead_role": "ORG_ADMIN",
            "roles": {"ORG_ADMIN", "SUPER_ADMIN"},
        },
        {
            "id": "team-viewers",
            "name": "Stakeholders & Viewers",
            "description": "External and internal stakeholders with read-only operational visibility.",
            "lead_role": "VIEWER",
            "roles": {"VIEWER"},
        },
    ]

    result: list[TenantTeamResponse] = []
    for tdef in team_definitions:
        matching_members: list[TenantTeamMember] = []
        for u in users:
            # Check if any role matches
            if any(r in tdef["roles"] for r in u.roles):
                matching_members.append(
                    TenantTeamMember(
                        user_id=u.id,
                        full_name=u.full_name,
                        email=u.email,
                        role=u.roles[0] if u.roles else "MEMBER",
                    )
                )

        result.append(
            TenantTeamResponse(
                id=tdef["id"],
                name=tdef["name"],
                description=tdef["description"],
                lead_role=tdef["lead_role"],
                member_count=len(matching_members),
                members=matching_members,
            )
        )

    return result


def get_tenant_usage(db: Session, *, organization_id: uuid.UUID) -> TenantUsageResponse:
    # Live database counts
    user_count = db.execute(
        select(func.count(User.id)).where(User.organization_id == organization_id)
    ).scalar_one()

    aircraft_count = db.execute(
        select(func.count(Asset.id)).where(
            Asset.organization_id == organization_id, Asset.asset_type == "AIRCRAFT"
        )
    ).scalar_one()

    drone_count = db.execute(
        select(func.count(Asset.id)).where(
            Asset.organization_id == organization_id, Asset.asset_type == "DRONE"
        )
    ).scalar_one()

    facility_count = db.execute(
        select(func.count(Facility.id)).where(Facility.organization_id == organization_id)
    ).scalar_one()

    metrics = [
        TenantUsageMetricItem(
            key="user_seats",
            label="User Accounts",
            tracked=True,
            value=user_count,
            limit=25,
            is_unlimited=False,
            unit="Seats",
            status="TRACKED",
        ),
        TenantUsageMetricItem(
            key="aircraft_assets",
            label="Fixed-Wing Aircraft",
            tracked=True,
            value=aircraft_count,
            limit=10,
            is_unlimited=False,
            unit="Aircraft",
            status="TRACKED",
        ),
        TenantUsageMetricItem(
            key="drone_assets",
            label="Drone UAV Fleet",
            tracked=True,
            value=drone_count,
            limit=50,
            is_unlimited=False,
            unit="Drones",
            status="TRACKED",
        ),
        TenantUsageMetricItem(
            key="facilities",
            label="Operational Facilities",
            tracked=True,
            value=facility_count,
            limit=5,
            is_unlimited=False,
            unit="Sites",
            status="TRACKED",
        ),
        # Unmetered dimensions explicitly labeled NOT_TRACKED per prompt Section 13/15
        TenantUsageMetricItem(
            key="blob_storage",
            label="Document / Evidence Blob Storage",
            tracked=False,
            value=None,
            limit=None,
            is_unlimited=False,
            unit="GB",
            status="NOT_TRACKED",
        ),
        TenantUsageMetricItem(
            key="api_bandwidth",
            label="API Traffic & Query Volume",
            tracked=False,
            value=None,
            limit=None,
            is_unlimited=False,
            unit="Req/mo",
            status="NOT_TRACKED",
        ),
        TenantUsageMetricItem(
            key="lisa_ai_tokens",
            label="LISA AI Copilot Inference Tokens",
            tracked=False,
            value=None,
            limit=None,
            is_unlimited=False,
            unit="Tokens",
            status="NOT_TRACKED",
        ),
    ]

    return TenantUsageResponse(organization_id=organization_id, metrics=metrics)


def get_tenant_dashboard(db: Session, *, organization_id: uuid.UUID) -> TenantDashboardResponse:
    profile = get_tenant_profile(db, organization_id=organization_id)

    users = list_tenant_users(db, organization_id=organization_id)
    users_count = len(users)
    active_users_count = len([u for u in users if u.is_active])

    invitations = list_tenant_invitations(db, organization_id=organization_id)
    pending_invitations_count = len([i for i in invitations if i.status == "PENDING"])

    aircraft_count = db.execute(
        select(func.count(Asset.id)).where(
            Asset.organization_id == organization_id, Asset.asset_type == "AIRCRAFT"
        )
    ).scalar_one()

    drone_count = db.execute(
        select(func.count(Asset.id)).where(
            Asset.organization_id == organization_id, Asset.asset_type == "DRONE"
        )
    ).scalar_one()

    fleet_count = aircraft_count + drone_count

    facility_count = db.execute(
        select(func.count(Facility.id)).where(Facility.organization_id == organization_id)
    ).scalar_one()

    teams = get_tenant_teams(db, organization_id=organization_id)
    team_count = len(teams)

    # Entitlements & Subscription
    entitlements = resolve_entitlements(db, organization_id=organization_id)
    effective_features_count = len([v for v in entitlements.effective_features.values() if v])

    attention_items: list[TenantDashboardAttentionItem] = []
    if pending_invitations_count > 0:
        attention_items.append(
            TenantDashboardAttentionItem(
                severity="INFO",
                category="PEOPLE",
                title=f"{pending_invitations_count} Pending Invitation(s)",
                message=f"There are {pending_invitations_count} onboarding invitations waiting to be completed.",
                link_href="/tenant/invitations",
                link_label="Manage Invitations",
            )
        )

    if profile.status == "SUSPENDED":
        attention_items.append(
            TenantDashboardAttentionItem(
                severity="CRITICAL",
                category="GOVERNANCE",
                title="Tenant Suspended by Platform",
                message="This organization is currently suspended. Operational mutations are restricted.",
                link_href="/tenant/profile",
                link_label="Inspect Status",
            )
        )

    if facility_count == 0:
        attention_items.append(
            TenantDashboardAttentionItem(
                severity="WARNING",
                category="OPERATIONS",
                title="No Facilities Configured",
                message="Fleet assets currently have no registered base facilities.",
                link_href="/tenant/facilities",
                link_label="Add Facility",
            )
        )

    return TenantDashboardResponse(
        organization=profile,
        users_count=users_count,
        active_users_count=active_users_count,
        pending_invitations_count=pending_invitations_count,
        fleet_count=fleet_count,
        aircraft_count=aircraft_count,
        drone_count=drone_count,
        facility_count=facility_count,
        team_count=team_count,
        current_plan=entitlements.plan_code,
        subscription_status=entitlements.subscription_status,
        effective_features_count=effective_features_count,
        attention_items=attention_items,
    )


def list_tenant_audit_events(
    db: Session,
    *,
    organization_id: uuid.UUID,
    limit: int = 50,
    offset: int = 0,
) -> list[AuditEvent]:
    # Strictly scoped to organization_id. Excludes internal platform-wide events.
    stmt = (
        select(AuditEvent)
        .where(
            AuditEvent.organization_id == organization_id,
            ~AuditEvent.action.startswith("platform."),
        )
        .order_by(AuditEvent.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    return list(db.execute(stmt).scalars().all())
