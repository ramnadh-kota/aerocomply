import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, get_db_session, require_permission
from app.core.permissions import Permission
from app.schemas.auth import CurrentUser, MessageResponse
from app.schemas.deletion import OrganizationDeletionRequest
from app.schemas.platform import AuditEventResponse
from app.schemas.tenant import (
    TenantDashboardResponse,
    TenantInvitationRequest,
    TenantInvitationResponse,
    TenantProfileResponse,
    TenantProfileUpdateRequest,
    TenantRoleInfo,
    TenantSettingsResponse,
    TenantSettingsUpdateRequest,
    TenantTeamResponse,
    TenantUsageResponse,
    TenantUserResponse,
    TenantUserRoleUpdateRequest,
    TenantUserStatusUpdateRequest,
)
from app.services import deletion_service, tenant_service

router = APIRouter(prefix="/tenant", tags=["tenant"])


# --- DASHBOARD & PROFILE ---


@router.get("/dashboard", response_model=TenantDashboardResponse)
def get_tenant_dashboard(
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(get_current_user),
) -> TenantDashboardResponse:
    return tenant_service.get_tenant_dashboard(
        db, organization_id=current_user.organization_id
    )


@router.get("/profile", response_model=TenantProfileResponse)
def get_tenant_profile(
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(get_current_user),
) -> TenantProfileResponse:
    return tenant_service.get_tenant_profile(
        db, organization_id=current_user.organization_id
    )


@router.patch("/profile", response_model=TenantProfileResponse)
def update_tenant_profile(
    payload: TenantProfileUpdateRequest,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.ORG_MANAGE)),
) -> TenantProfileResponse:
    return tenant_service.update_tenant_profile(
        db,
        organization_id=current_user.organization_id,
        actor_user_id=current_user.id,
        payload=payload,
    )


@router.get("/settings", response_model=TenantSettingsResponse)
def get_tenant_settings(
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(get_current_user),
) -> TenantSettingsResponse:
    return tenant_service.get_tenant_settings(
        db, organization_id=current_user.organization_id
    )


@router.patch("/settings", response_model=TenantSettingsResponse)
def update_tenant_settings(
    payload: TenantSettingsUpdateRequest,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.ORG_MANAGE)),
) -> TenantSettingsResponse:
    return tenant_service.update_tenant_settings(
        db,
        organization_id=current_user.organization_id,
        actor_user_id=current_user.id,
        payload=payload,
    )


# --- DELETION REQUEST (Platform Control Plane) ---
#
# Soft-deletes this Tenant Admin's OWN organization -- there is no way to
# name a different organization_id here (see get_current_user's own
# docstring). Once submitted, every subsequent request from every user in
# this organization is refused (app/core/deps.py's get_current_user, plus
# login/refresh in app/services/auth_service.py), including the admin who
# just submitted it -- there is no tenant-facing undo. Only Platform Admin
# can reverse this (POST /platform/deleted-records/organizations/{id}/
# restore) or approve permanent deletion.


@router.post("/deletion-request", response_model=MessageResponse)
def request_organization_deletion(
    payload: OrganizationDeletionRequest,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.ORG_MANAGE)),
) -> MessageResponse:
    deletion_service.request_organization_deletion(
        db,
        organization_id=current_user.organization_id,
        actor_user_id=current_user.id,
        payload=payload,
    )
    return MessageResponse(
        message="Deletion requested. Your organization is now pending Platform Admin review."
    )


# --- USERS & ROLES ---


@router.get("/users", response_model=list[TenantUserResponse])
def list_tenant_users(
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(get_current_user),
) -> list[TenantUserResponse]:
    return tenant_service.list_tenant_users(
        db, organization_id=current_user.organization_id
    )


@router.get("/users/{user_id}", response_model=TenantUserResponse)
def get_tenant_user(
    user_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(get_current_user),
) -> TenantUserResponse:
    return tenant_service.get_tenant_user(
        db, organization_id=current_user.organization_id, user_id=user_id
    )


@router.patch("/users/{user_id}/roles", response_model=TenantUserResponse)
def update_tenant_user_roles(
    user_id: uuid.UUID,
    payload: TenantUserRoleUpdateRequest,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.USER_MANAGE)),
) -> TenantUserResponse:
    return tenant_service.update_tenant_user_roles(
        db,
        organization_id=current_user.organization_id,
        actor_user_id=current_user.id,
        user_id=user_id,
        roles=payload.roles,
    )


@router.patch("/users/{user_id}/status", response_model=TenantUserResponse)
def update_tenant_user_status(
    user_id: uuid.UUID,
    payload: TenantUserStatusUpdateRequest,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.USER_MANAGE)),
) -> TenantUserResponse:
    return tenant_service.update_tenant_user_status(
        db,
        organization_id=current_user.organization_id,
        actor_user_id=current_user.id,
        user_id=user_id,
        is_active=payload.is_active,
    )


@router.get("/roles", response_model=list[TenantRoleInfo])
def list_tenant_roles(
    current_user: CurrentUser = Depends(get_current_user),
) -> list[TenantRoleInfo]:
    return tenant_service.list_tenant_roles()


# --- INVITATIONS ---


@router.get("/invitations", response_model=list[TenantInvitationResponse])
def list_tenant_invitations(
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.USER_MANAGE)),
) -> list[TenantInvitationResponse]:
    return tenant_service.list_tenant_invitations(
        db, organization_id=current_user.organization_id
    )


@router.post(
    "/invitations", response_model=TenantInvitationResponse, status_code=status.HTTP_201_CREATED
)
def invite_tenant_user(
    payload: TenantInvitationRequest,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.USER_MANAGE)),
) -> TenantInvitationResponse:
    return tenant_service.invite_tenant_user(
        db,
        organization_id=current_user.organization_id,
        actor_user_id=current_user.id,
        payload=payload,
    )


@router.post("/invitations/{user_id}/resend", response_model=MessageResponse)
def resend_tenant_invitation(
    user_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.USER_MANAGE)),
) -> MessageResponse:
    tenant_service.resend_tenant_invitation(
        db,
        organization_id=current_user.organization_id,
        actor_user_id=current_user.id,
        user_id=user_id,
    )
    return MessageResponse(message="Invitation code resent.")


@router.post("/invitations/{user_id}/cancel", response_model=MessageResponse)
def cancel_tenant_invitation(
    user_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.USER_MANAGE)),
) -> MessageResponse:
    tenant_service.cancel_tenant_invitation(
        db,
        organization_id=current_user.organization_id,
        actor_user_id=current_user.id,
        user_id=user_id,
    )
    return MessageResponse(message="Invitation cancelled.")


# --- TEAMS & USAGE ---


@router.get("/teams", response_model=list[TenantTeamResponse])
def get_tenant_teams(
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(get_current_user),
) -> list[TenantTeamResponse]:
    return tenant_service.get_tenant_teams(
        db, organization_id=current_user.organization_id
    )


@router.get("/usage", response_model=TenantUsageResponse)
def get_tenant_usage(
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(get_current_user),
) -> TenantUsageResponse:
    return tenant_service.get_tenant_usage(
        db, organization_id=current_user.organization_id
    )


# --- AUDIT ---


@router.get("/audit", response_model=list[AuditEventResponse])
def list_tenant_audit_events(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.AUDIT_READ)),
) -> list[AuditEventResponse]:
    events = tenant_service.list_tenant_audit_events(
        db,
        organization_id=current_user.organization_id,
        limit=limit,
        offset=offset,
    )
    return [AuditEventResponse.model_validate(e) for e in events]
