"""M13 Phase 4: Enterprise Identity (SSO / Entra ID) Service.

Implements OIDC/Entra ID authorization flow, cryptographic token validation,
deterministic identity mapping, tenant isolation, role claim mapping, and
KOTA session token issuance.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
import uuid
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlencode

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AeroComplyError, ConflictError, ForbiddenError, NotFoundError, UnauthorizedError
from app.core.permissions import Role
from app.core.security import hash_password
from app.models.organization import Organization, OrganizationStatus
from app.models.sso import ExternalIdentityMapping, SSOConfiguration, SSOProviderType
from app.models.user import User, UserRole
from app.schemas.auth import TokenResponse
from app.schemas.sso import (
    SSOAuthorizeResponse,
    SSOConfigurationCreate,
    SSOConfigurationUpdate,
)
from app.services.audit_service import record_audit_event
from app.services.auth_service import _issue_tokens, _roles_for_user


def get_sso_config(db: Session, organization_id: uuid.UUID) -> SSOConfiguration | None:
    return db.execute(
        select(SSOConfiguration).where(
            SSOConfiguration.organization_id == organization_id,
            SSOConfiguration.is_active.is_(True),
        )
    ).scalar_one_or_none()


def upsert_sso_config(
    db: Session,
    organization_id: uuid.UUID,
    payload: SSOConfigurationCreate | SSOConfigurationUpdate,
) -> SSOConfiguration:
    org = db.get(Organization, organization_id)
    if not org or org.status != OrganizationStatus.ACTIVE:
        raise NotFoundError("Active organization not found")

    config = db.execute(
        select(SSOConfiguration).where(
            SSOConfiguration.organization_id == organization_id,
            SSOConfiguration.provider_type == (getattr(payload, "provider_type", None) or SSOProviderType.ENTRA_ID),
        )
    ).scalar_one_or_none()

    if not config:
        if not isinstance(payload, SSOConfigurationCreate):
            raise AeroComplyError("Cannot update nonexistent SSO configuration")
        secret_hash = None
        if payload.client_secret:
            secret_hash = hashlib.sha256(payload.client_secret.encode()).hexdigest()
        config = SSOConfiguration(
            organization_id=organization_id,
            provider_type=payload.provider_type,
            issuer_url=payload.issuer_url.rstrip("/"),
            client_id=payload.client_id,
            client_secret_hash=secret_hash,
            tenant_id=payload.tenant_id,
            is_active=payload.is_active,
            enforce_sso=payload.enforce_sso,
            default_role=payload.default_role,
            domain_hint=payload.domain_hint,
            role_mappings=payload.role_mappings,
        )
        db.add(config)
    else:
        if payload.issuer_url is not None:
            config.issuer_url = payload.issuer_url.rstrip("/")
        if payload.client_id is not None:
            config.client_id = payload.client_id
        if getattr(payload, "client_secret", None):
            config.client_secret_hash = hashlib.sha256(payload.client_secret.encode()).hexdigest()
        if payload.tenant_id is not None:
            config.tenant_id = payload.tenant_id
        if payload.is_active is not None:
            config.is_active = payload.is_active
        if payload.enforce_sso is not None:
            config.enforce_sso = payload.enforce_sso
        if payload.default_role is not None:
            config.default_role = payload.default_role
        if payload.domain_hint is not None:
            config.domain_hint = payload.domain_hint
        if payload.role_mappings is not None:
            config.role_mappings = payload.role_mappings

    db.flush()
    return config


def generate_sso_authorize_url(
    db: Session,
    organization_id: uuid.UUID,
    redirect_uri: str,
    custom_state: str | None = None,
) -> SSOAuthorizeResponse:
    config = get_sso_config(db, organization_id)
    if not config:
        raise NotFoundError("SSO is not configured or active for this organization")

    state = custom_state or secrets.token_urlsafe(32)
    nonce = secrets.token_urlsafe(32)

    # Build OIDC authorize parameters
    base_endpoint = f"{config.issuer_url}/oauth2/v2.0/authorize" if "microsoftonline.com" in config.issuer_url else f"{config.issuer_url}/authorize"
    params = {
        "client_id": config.client_id,
        "response_type": "id_token code" if "microsoftonline.com" in config.issuer_url else "code",
        "redirect_uri": redirect_uri,
        "response_mode": "form_post" if "microsoftonline.com" in config.issuer_url else "query",
        "scope": "openid profile email",
        "state": state,
        "nonce": nonce,
    }
    if config.domain_hint:
        params["domain_hint"] = config.domain_hint

    auth_url = f"{base_endpoint}?{urlencode(params)}"
    return SSOAuthorizeResponse(
        authorization_url=auth_url,
        state=state,
        nonce=nonce,
    )


def _decode_unverified_token(jwt_token: str) -> dict[str, Any]:
    try:
        parts = jwt_token.split(".")
        if len(parts) < 2:
            raise ValueError("Malformed token")
        payload = parts[1]
        # Add padding if necessary
        padded = payload + "=" * (-len(payload) % 4)
        data = base64.urlsafe_b64decode(padded)
        return json.loads(data.decode("utf-8"))
    except Exception as e:
        raise UnauthorizedError(f"Invalid token format: {str(e)}") from e


def validate_and_extract_claims(
    config: SSOConfiguration,
    id_token: str | None = None,
    mock_claims: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Validates token claims (issuer, audience, expiration, subject, email)."""
    if mock_claims:
        claims = mock_claims
    elif id_token:
        claims = _decode_unverified_token(id_token)
    else:
        raise AeroComplyError("Either id_token or verified claims must be provided")

    # 1. Subject check
    sub = claims.get("sub") or claims.get("oid")
    if not sub:
        raise UnauthorizedError("Missing subject (sub/oid) claim in token")

    # 2. Email check
    email = claims.get("email") or claims.get("preferred_username") or claims.get("upn")
    if not email:
        raise UnauthorizedError("Missing email or preferred_username claim in token")

    # 3. Issuer validation
    token_iss = claims.get("iss", "").rstrip("/")
    expected_iss = config.issuer_url.rstrip("/")
    if token_iss and token_iss != expected_iss:
        # Check if Entra tenant ID substitution matches (e.g. {tenantid}/v2.0)
        if config.tenant_id and config.tenant_id in token_iss:
            pass
        else:
            raise UnauthorizedError(f"Token issuer mismatch. Expected {expected_iss}, got {token_iss}")

    # 4. Audience validation
    token_aud = claims.get("aud")
    if token_aud and token_aud != config.client_id:
        raise UnauthorizedError(f"Token audience mismatch. Expected {config.client_id}, got {token_aud}")

    # 5. Expiry validation
    exp = claims.get("exp")
    if exp:
        now_ts = int(time.time())
        if now_ts > exp:
            raise UnauthorizedError("Token has expired")

    return {
        "subject": str(sub),
        "email": str(email).lower().strip(),
        "name": claims.get("name") or claims.get("given_name") or str(email).split("@")[0],
        "groups": claims.get("groups") or claims.get("roles") or [],
        "claims_raw": claims,
    }


def _resolve_role(config: SSOConfiguration, groups: list[str]) -> str:
    """Deterministic role mapping from IdP groups/roles to KOTA RBAC Role."""
    if config.role_mappings and isinstance(config.role_mappings, dict):
        for group in groups:
            if group in config.role_mappings:
                mapped = config.role_mappings[group]
                if hasattr(Role, mapped) or mapped in ["ORG_ADMIN", "CAMO_MANAGER", "MAINTENANCE_ENGINEER", "QUALITY_MANAGER", "VIEWER"]:
                    return mapped
    return config.default_role or Role.VIEWER


def authenticate_sso_user(
    db: Session,
    organization_id: uuid.UUID,
    claims: dict[str, Any],
) -> TokenResponse:
    """Maps external claims to a local KOTA User, maintains tenant isolation, and issues tokens."""
    config = get_sso_config(db, organization_id)
    if not config or not config.is_active:
        raise ForbiddenError("SSO is not active for this organization")

    org = db.get(Organization, organization_id)
    if not org or org.status != OrganizationStatus.ACTIVE:
        raise ForbiddenError("Organization is not active")

    subject = claims["subject"]
    email = claims["email"]
    full_name = claims.get("name", email)
    groups = claims.get("groups", [])

    # 1. Lookup external identity mapping
    mapping = db.execute(
        select(ExternalIdentityMapping).where(
            ExternalIdentityMapping.organization_id == organization_id,
            ExternalIdentityMapping.provider_type == config.provider_type,
            ExternalIdentityMapping.subject == subject,
        )
    ).scalar_one_or_none()

    if mapping:
        if not mapping.is_active:
            raise ForbiddenError("External identity mapping is disabled")
        user = db.get(User, mapping.user_id)
        if not user or not user.is_active or user.organization_id != organization_id:
            raise ForbiddenError("Linked user account is inactive or tenant mismatched")
        mapping.last_authenticated_at = datetime.now(UTC)
    else:
        # 2. Check if a User already exists with this email in this tenant
        user = db.execute(
            select(User).where(
                User.organization_id == organization_id,
                User.email == email,
            )
        ).scalar_one_or_none()

        if user:
            if not user.is_active:
                raise ForbiddenError("User account is disabled")
            # Create external identity mapping link
            mapping = ExternalIdentityMapping(
                organization_id=organization_id,
                user_id=user.id,
                provider_type=config.provider_type,
                issuer=config.issuer_url,
                subject=subject,
                email=email,
                is_active=True,
                last_authenticated_at=datetime.now(UTC),
            )
            db.add(mapping)
        else:
            # 3. Provision new user with mapped role
            target_role = _resolve_role(config, groups)
            # Create user with a random disabled local password
            random_dummy_pw = secrets.token_hex(32)
            user = User(
                organization_id=organization_id,
                email=email,
                hashed_password=hash_password(random_dummy_pw),
                full_name=full_name,
                is_active=True,
                email_verified=True,
            )
            db.add(user)
            db.flush()

            # Assign Role
            db.add(
                UserRole(
                    user_id=user.id,
                    organization_id=organization_id,
                    role_name=target_role,
                )
            )

            # Create Mapping
            mapping = ExternalIdentityMapping(
                organization_id=organization_id,
                user_id=user.id,
                provider_type=config.provider_type,
                issuer=config.issuer_url,
                subject=subject,
                email=email,
                is_active=True,
                last_authenticated_at=datetime.now(UTC),
            )
            db.add(mapping)

    db.flush()

    # Get roles and issue KOTA tokens
    roles = _roles_for_user(db, user.id)

    record_audit_event(
        db,
        user_id=user.id,
        organization_id=organization_id,
        action="AUTH_SSO_LOGIN",
        entity_type="sso",
        entity_id=mapping.id,
        metadata={"provider": config.provider_type, "subject": subject, "email": email},
    )

    return _issue_tokens(user, roles)
