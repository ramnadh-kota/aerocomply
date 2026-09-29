"""Enterprise Identity & SSO API endpoints (M13 Phase 4)."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, get_db_session, require_permission
from app.core.permissions import Permission
from app.models.organization import Organization
from app.schemas.auth import CurrentUser, TokenResponse
from app.schemas.sso import (
    SSOAuthorizeRequest,
    SSOAuthorizeResponse,
    SSOCallbackRequest,
    SSOConfigurationCreate,
    SSOConfigurationResponse,
    SSOConfigurationUpdate,
)
from app.services import sso_service

router = APIRouter(prefix="/auth/sso", tags=["enterprise-sso"])


@router.get("/config", response_model=SSOConfigurationResponse | None)
def get_sso_configuration(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db_session)],
) -> SSOConfigurationResponse | None:
    """Retrieve SSO configuration for the current organization."""
    config = sso_service.get_sso_config(db, current_user.organization_id)
    if not config:
        return None
    return SSOConfigurationResponse.model_validate(config)


@router.put("/config", response_model=SSOConfigurationResponse)
def upsert_sso_configuration(
    payload: SSOConfigurationCreate,
    current_user: Annotated[CurrentUser, Depends(require_permission(Permission.ORG_MANAGE))],
    db: Annotated[Session, Depends(get_db_session)],
) -> SSOConfigurationResponse:
    """Configure or update enterprise SSO (Entra ID) for the organization."""
    config = sso_service.upsert_sso_config(db, current_user.organization_id, payload)
    return SSOConfigurationResponse.model_validate(config)


@router.post("/authorize", response_model=SSOAuthorizeResponse)
def initiate_sso_authorization(
    payload: SSOAuthorizeRequest,
    db: Annotated[Session, Depends(get_db_session)],
) -> SSOAuthorizeResponse:
    """Generate an OIDC SSO authorization URL for an organization."""
    target_org_id = payload.organization_id
    if not target_org_id and payload.organization_name:
        from sqlalchemy import select
        org = db.execute(
            select(Organization).where(Organization.name == payload.organization_name)
        ).scalar_one_or_none()
        if org:
            target_org_id = org.id

    if not target_org_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Either organization_id or valid organization_name is required",
        )

    return sso_service.generate_sso_authorize_url(
        db, target_org_id, payload.redirect_uri, custom_state=payload.state
    )


@router.post("/callback", response_model=TokenResponse)
def process_sso_callback(
    payload: SSOCallbackRequest,
    db: Annotated[Session, Depends(get_db_session)],
) -> TokenResponse:
    """Process IdP callback / ID token, validate cryptographic claims, map user, and issue KOTA tokens."""
    if not payload.organization_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="organization_id is required for tenant isolation",
        )

    config = sso_service.get_sso_config(db, payload.organization_id)
    if not config:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="SSO is not enabled for this organization",
        )

    claims = sso_service.validate_and_extract_claims(config, id_token=payload.id_token)
    return sso_service.authenticate_sso_user(db, payload.organization_id, claims)
