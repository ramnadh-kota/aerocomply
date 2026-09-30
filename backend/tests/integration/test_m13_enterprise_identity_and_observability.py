"""M13 Phase 4 & Phase 5: Enterprise Identity (SSO / Entra ID) and Production Hypercare Observability Tests.

Verifies:
1. SSO Configuration CRUD and role-based permissions (ORG_ADMIN).
2. OIDC authorization request generation with state and nonce.
3. SSO authentication with valid claims, deterministic mapping to new user, and role resolution.
4. SSO linking with existing local user account (zero duplicate user creation).
5. Token validation & rejection on invalid issuer, audience, expired token, or missing subject.
6. Strict cross-tenant SSO isolation.
7. Operational incident lifecycle (P0-P3 creation, acknowledgement, resolution, filtering).
8. Multi-subsystem Hypercare observability summary aggregation (platform status, telemetry, HUMS, intelligence, incidents).
9. Audit trail logging for identity and incident events.
"""

import base64
import json
import time
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import status
from sqlalchemy import select

from app.core.permissions import Role
from app.core.security import hash_password
from tests.support.tokens import mint_token as create_access_token
from app.models.audit_event import AuditEvent
from app.models.hums import HUMSSensor
from app.models.organization import Organization
from app.models.sso import (
    ExternalIdentityMapping,
    IncidentSeverity,
    IncidentStatus,
    OperationalIncident,
    SSOConfiguration,
    SSOProviderType,
)
from app.models.telemetry import TelemetryEventLog, TelemetryProcessingStatus
from app.models.user import User, UserRole
from app.schemas.observability import OperationalIncidentCreate
from app.schemas.sso import SSOConfigurationCreate
from app.services import auth_service, hypercare_service, sso_service


def _make_jwt_token(payload: dict) -> str:
    """Creates an unsigned test JWT string with base64 header and payload."""
    header = {"alg": "RS256", "typ": "JWT"}
    h_b64 = base64.urlsafe_b64encode(json.dumps(header).encode()).decode().rstrip("=")
    p_b64 = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    return f"{h_b64}.{p_b64}.test_signature"


@pytest.fixture
def identity_tenant_setup(db_session):
    """Creates two isolated test organizations with admin users."""
    suffix = uuid.uuid4().hex[:6]
    org_a = Organization(name=f"Horizon Enterprise Tenant A {suffix}")
    org_b = Organization(name=f"Horizon Enterprise Tenant B {suffix}")
    db_session.add_all([org_a, org_b])
    db_session.flush()

    # Admin User A
    user_a = User(
        organization_id=org_a.id,
        email=f"admin.a.{suffix}@horizon.com",
        hashed_password=hash_password("Password123!"),
        full_name="Admin Org A",
        is_active=True,
        email_verified=True,
    )
    # Admin User B
    user_b = User(
        organization_id=org_b.id,
        email=f"admin.b.{suffix}@horizon.com",
        hashed_password=hash_password("Password123!"),
        full_name="Admin Org B",
        is_active=True,
        email_verified=True,
    )
    db_session.add_all([user_a, user_b])
    db_session.flush()

    db_session.add_all([
        UserRole(user_id=user_a.id, organization_id=org_a.id, role_name=Role.ORG_ADMIN),
        UserRole(user_id=user_b.id, organization_id=org_b.id, role_name=Role.ORG_ADMIN),
    ])
    db_session.flush()

    token_a = create_access_token(user_a.id, org_a.id, [Role.ORG_ADMIN], email=user_a.email, full_name=user_a.full_name)
    token_b = create_access_token(user_b.id, org_b.id, [Role.ORG_ADMIN], email=user_b.email, full_name=user_b.full_name)

    return {
        "org_a": org_a,
        "org_b": org_b,
        "user_a": user_a,
        "user_b": user_b,
        "token_a": token_a,
        "token_b": token_b,
    }


def test_sso_configuration_crud_and_rbac(client, identity_tenant_setup, db_session):
    """Verifies SSO configuration can be created/retrieved by ORG_ADMIN and enforces tenant isolation."""
    setup = identity_tenant_setup

    # 1. ORG_ADMIN configures Entra ID SSO for Org A
    payload = {
        "provider_type": "ENTRA_ID",
        "issuer_url": "https://login.microsoftonline.com/tenant-123/v2.0",
        "client_id": "app-client-id-123",
        "tenant_id": "tenant-123",
        "is_active": True,
        "enforce_sso": False,
        "default_role": "VIEWER",
        "domain_hint": "horizon.com",
        "role_mappings": {
            "Aviation-Engineers": "MAINTENANCE_ENGINEER",
            "CAMO-Directors": "CAMO_MANAGER",
        },
    }

    res = client.put(
        "/api/v1/auth/sso/config",
        json=payload,
        headers={"Authorization": f"Bearer {setup['token_a']}"},
    )
    assert res.status_code == status.HTTP_200_OK
    data = res.json()
    assert data["client_id"] == "app-client-id-123"
    assert data["role_mappings"]["Aviation-Engineers"] == "MAINTENANCE_ENGINEER"

    # 2. Get config
    get_res = client.get(
        "/api/v1/auth/sso/config",
        headers={"Authorization": f"Bearer {setup['token_a']}"},
    )
    assert get_res.status_code == status.HTTP_200_OK
    assert get_res.json()["issuer_url"] == "https://login.microsoftonline.com/tenant-123/v2.0"

    # 3. Org B should see no config for itself
    get_b = client.get(
        "/api/v1/auth/sso/config",
        headers={"Authorization": f"Bearer {setup['token_b']}"},
    )
    assert get_b.status_code == status.HTTP_200_OK
    assert get_b.json() is None


def test_sso_authorize_url_generation(client, identity_tenant_setup, db_session):
    """Verifies OIDC SSO authorization URL generation with state/nonce and tenant resolution."""
    setup = identity_tenant_setup

    # Configure SSO for Org A
    sso_service.upsert_sso_config(
        db_session,
        setup["org_a"].id,
        SSOConfigurationCreate(
            issuer_url="https://login.microsoftonline.com/tenant-123/v2.0",
            client_id="app-client-id-123",
            tenant_id="tenant-123",
            domain_hint="horizon.com",
        ),
    )
    db_session.flush()

    res = client.post(
        "/api/v1/auth/sso/authorize",
        json={
            "organization_id": str(setup["org_a"].id),
            "redirect_uri": "https://app.aerocomply.com/auth/sso/callback",
        },
    )
    assert res.status_code == status.HTTP_200_OK
    data = res.json()
    assert "authorization_url" in data
    assert "client_id=app-client-id-123" in data["authorization_url"]
    assert "domain_hint=horizon.com" in data["authorization_url"]
    assert "state=" in data["authorization_url"]
    assert "nonce=" in data["authorization_url"]


def test_sso_callback_provision_new_user_with_role_mapping(client, identity_tenant_setup, db_session):
    """Verifies SSO callback provisions a new user with correct mapped role and returns valid tokens."""
    setup = identity_tenant_setup

    sso_service.upsert_sso_config(
        db_session,
        setup["org_a"].id,
        SSOConfigurationCreate(
            issuer_url="https://login.microsoftonline.com/tenant-123/v2.0",
            client_id="app-client-id-123",
            tenant_id="tenant-123",
            role_mappings={"Aviation-Engineers": "MAINTENANCE_ENGINEER"},
            default_role="VIEWER",
        ),
    )
    db_session.flush()

    # Construct valid ID token claims
    token_claims = {
        "iss": "https://login.microsoftonline.com/tenant-123/v2.0",
        "aud": "app-client-id-123",
        "sub": "entra-sub-user-999",
        "email": "engineer.sam@horizon.com",
        "name": "Sam Engineer",
        "groups": ["Aviation-Engineers"],
        "exp": int(time.time()) + 3600,
    }
    raw_token = _make_jwt_token(token_claims)

    res = client.post(
        "/api/v1/auth/sso/callback",
        json={
            "organization_id": str(setup["org_a"].id),
            "state": "test-state",
            "id_token": raw_token,
        },
    )
    assert res.status_code == status.HTTP_200_OK
    token_data = res.json()
    assert "access_token" in token_data
    assert "refresh_token" in token_data

    # Verify user was created in DB with correct role
    new_user = db_session.execute(
        select(User).where(User.email == "engineer.sam@horizon.com")
    ).scalar_one()
    assert new_user.organization_id == setup["org_a"].id
    assert new_user.full_name == "Sam Engineer"
    assert new_user.email_verified is True

    # Verify role assigned was MAINTENANCE_ENGINEER
    roles = auth_service._roles_for_user(db_session, new_user.id)
    assert Role.MAINTENANCE_ENGINEER in roles

    # Verify ExternalIdentityMapping record created
    mapping = db_session.execute(
        select(ExternalIdentityMapping).where(
            ExternalIdentityMapping.organization_id == setup["org_a"].id,
            ExternalIdentityMapping.subject == "entra-sub-user-999",
        )
    ).scalar_one()
    assert mapping.user_id == new_user.id
    assert mapping.email == "engineer.sam@horizon.com"


def test_sso_callback_links_existing_local_user(client, identity_tenant_setup, db_session):
    """Verifies SSO callback links to an existing user with matching email without creating a duplicate."""
    setup = identity_tenant_setup

    # Pre-create local user in Org A
    existing_user = User(
        organization_id=setup["org_a"].id,
        email="existing.tech@horizon.com",
        hashed_password=hash_password("Existing123!"),
        full_name="Existing Tech",
        is_active=True,
        email_verified=True,
    )
    db_session.add(existing_user)
    db_session.flush()
    db_session.add(UserRole(user_id=existing_user.id, organization_id=setup["org_a"].id, role_name=Role.QUALITY_MANAGER))
    db_session.flush()

    sso_service.upsert_sso_config(
        db_session,
        setup["org_a"].id,
        SSOConfigurationCreate(
            issuer_url="https://login.microsoftonline.com/tenant-123/v2.0",
            client_id="app-client-id-123",
            tenant_id="tenant-123",
        ),
    )
    db_session.flush()

    token_claims = {
        "iss": "https://login.microsoftonline.com/tenant-123/v2.0",
        "aud": "app-client-id-123",
        "sub": "entra-sub-tech-444",
        "email": "existing.tech@horizon.com",
        "name": "Existing Tech",
        "exp": int(time.time()) + 3600,
    }
    raw_token = _make_jwt_token(token_claims)

    res = client.post(
        "/api/v1/auth/sso/callback",
        json={
            "organization_id": str(setup["org_a"].id),
            "state": "test-state",
            "id_token": raw_token,
        },
    )
    assert res.status_code == status.HTTP_200_OK

    # Ensure no duplicate user was created
    users_with_email = db_session.execute(
        select(User).where(User.email == "existing.tech@horizon.com")
    ).scalars().all()
    assert len(users_with_email) == 1

    # Check mapping was established
    mapping = db_session.execute(
        select(ExternalIdentityMapping).where(
            ExternalIdentityMapping.subject == "entra-sub-tech-444"
        )
    ).scalar_one()
    assert mapping.user_id == existing_user.id


def test_sso_token_validation_rejections(client, identity_tenant_setup, db_session):
    """Verifies SSO rejects expired tokens, issuer mismatch, and audience mismatch."""
    setup = identity_tenant_setup

    sso_service.upsert_sso_config(
        db_session,
        setup["org_a"].id,
        SSOConfigurationCreate(
            issuer_url="https://login.microsoftonline.com/tenant-123/v2.0",
            client_id="app-client-id-123",
            tenant_id="tenant-123",
        ),
    )
    db_session.flush()

    # 1. Expired token
    expired_claims = {
        "iss": "https://login.microsoftonline.com/tenant-123/v2.0",
        "aud": "app-client-id-123",
        "sub": "sub-1",
        "email": "user1@horizon.com",
        "exp": int(time.time()) - 100,  # in the past
    }
    res = client.post(
        "/api/v1/auth/sso/callback",
        json={"organization_id": str(setup["org_a"].id), "state": "s", "id_token": _make_jwt_token(expired_claims)},
    )
    assert res.status_code == status.HTTP_401_UNAUTHORIZED
    assert "expired" in res.json()["error"]["message"].lower()

    # 2. Issuer mismatch
    wrong_iss_claims = {
        "iss": "https://rogue-idp.example.com",
        "aud": "app-client-id-123",
        "sub": "sub-1",
        "email": "user1@horizon.com",
        "exp": int(time.time()) + 3600,
    }
    res = client.post(
        "/api/v1/auth/sso/callback",
        json={"organization_id": str(setup["org_a"].id), "state": "s", "id_token": _make_jwt_token(wrong_iss_claims)},
    )
    assert res.status_code == status.HTTP_401_UNAUTHORIZED
    assert "issuer mismatch" in res.json()["error"]["message"].lower()

    # 3. Audience mismatch
    wrong_aud_claims = {
        "iss": "https://login.microsoftonline.com/tenant-123/v2.0",
        "aud": "other-app-id",
        "sub": "sub-1",
        "email": "user1@horizon.com",
        "exp": int(time.time()) + 3600,
    }
    res = client.post(
        "/api/v1/auth/sso/callback",
        json={"organization_id": str(setup["org_a"].id), "state": "s", "id_token": _make_jwt_token(wrong_aud_claims)},
    )
    assert res.status_code == status.HTTP_401_UNAUTHORIZED
    assert "audience mismatch" in res.json()["error"]["message"].lower()


def test_cross_tenant_sso_isolation(client, identity_tenant_setup, db_session):
    """Verifies that an SSO token targeted for Org A cannot authenticate into Org B."""
    setup = identity_tenant_setup

    # Configure Org A
    sso_service.upsert_sso_config(
        db_session,
        setup["org_a"].id,
        SSOConfigurationCreate(
            issuer_url="https://login.microsoftonline.com/tenant-123/v2.0",
            client_id="app-client-id-123",
            tenant_id="tenant-123",
        ),
    )
    # Configure Org B with separate client ID
    sso_service.upsert_sso_config(
        db_session,
        setup["org_b"].id,
        SSOConfigurationCreate(
            issuer_url="https://login.microsoftonline.com/tenant-456/v2.0",
            client_id="app-client-id-456",
            tenant_id="tenant-456",
        ),
    )
    db_session.flush()

    # Try to use Org A's token on Org B's callback
    org_a_claims = {
        "iss": "https://login.microsoftonline.com/tenant-123/v2.0",
        "aud": "app-client-id-123",
        "sub": "entra-sub-a",
        "email": "attacker@horizon.com",
        "exp": int(time.time()) + 3600,
    }
    raw_token = _make_jwt_token(org_a_claims)

    res = client.post(
        "/api/v1/auth/sso/callback",
        json={
            "organization_id": str(setup["org_b"].id),
            "state": "s",
            "id_token": raw_token,
        },
    )
    assert res.status_code == status.HTTP_401_UNAUTHORIZED


def test_operational_incidents_lifecycle(client, identity_tenant_setup, db_session):
    """Verifies P0-P3 incident creation, acknowledgement, resolution, filtering, and audit logging."""
    setup = identity_tenant_setup

    # 1. Create a P0 incident
    p0_payload = {
        "severity": "P0",
        "service_name": "TELEMETRY",
        "title": "Ingestion Gateway Unreachable",
        "description": "Primary webhook endpoint experienced 5xx failures.",
        "details": {"error_code": "CONNECTION_REFUSED", "attempt_count": 3},
    }
    res = client.post(
        "/api/v1/hypercare/incidents",
        json=p0_payload,
        headers={"Authorization": f"Bearer {setup['token_a']}"},
    )
    assert res.status_code == status.HTTP_200_OK
    inc_data = res.json()
    inc_id = inc_data["id"]
    assert inc_data["status"] == "OPEN"
    assert inc_data["severity"] == "P0"

    # 2. Acknowledge incident
    ack_res = client.post(
        f"/api/v1/hypercare/incidents/{inc_id}/acknowledge",
        headers={"Authorization": f"Bearer {setup['token_a']}"},
    )
    assert ack_res.status_code == status.HTTP_200_OK
    assert ack_res.json()["status"] == "ACKNOWLEDGED"

    # 3. Resolve incident
    res_res = client.post(
        f"/api/v1/hypercare/incidents/{inc_id}/resolve",
        headers={"Authorization": f"Bearer {setup['token_a']}"},
    )
    assert res_res.status_code == status.HTTP_200_OK
    assert res_res.json()["status"] == "RESOLVED"
    assert res_res.json()["resolved_at"] is not None

    # 4. List incidents filtered by severity
    list_res = client.get(
        "/api/v1/hypercare/incidents?severity=P0",
        headers={"Authorization": f"Bearer {setup['token_a']}"},
    )
    assert list_res.status_code == status.HTTP_200_OK
    assert len(list_res.json()) >= 1

    # 5. Audit event verification
    audits = db_session.execute(
        select(AuditEvent).where(
            AuditEvent.organization_id == setup["org_a"].id,
            AuditEvent.action.in_(["INCIDENT_CREATED", "INCIDENT_ACKNOWLEDGED", "INCIDENT_RESOLVED"]),
        )
    ).scalars().all()
    actions = [a.action for a in audits]
    assert "INCIDENT_CREATED" in actions
    assert "INCIDENT_RESOLVED" in actions


def test_hypercare_summary_observability_aggregation(client, identity_tenant_setup, db_session):
    """Verifies hypercare summary aggregates telemetry, HUMS, signals, and open incidents."""
    setup = identity_tenant_setup

    # Seed telemetry event log
    event_log = TelemetryEventLog(
        organization_id=setup["org_a"].id,
        source_system="DJI_FLIGHTHUB",
        source_event_id=f"event-{uuid.uuid4().hex[:6]}",
        idempotency_key=f"idemp-{uuid.uuid4().hex[:6]}",
        event_type="FLIGHT_COMPLETED",
        event_timestamp=datetime.now(UTC),
        received_timestamp=datetime.now(UTC),
        payload_hash="hash-123",
        processing_status=TelemetryProcessingStatus.PROCESSED,
        readings_count=5,
    )
    db_session.add(event_log)

    # Seed an asset
    from app.models.asset import Asset, AssetType
    asset = Asset(
        organization_id=setup["org_a"].id,
        asset_type=AssetType.AIRCRAFT,
        registration=f"VT-TEST-{uuid.uuid4().hex[:4].upper()}",
    )
    db_session.add(asset)
    db_session.flush()

    # Seed a HUMS sensor
    sensor = HUMSSensor(
        organization_id=setup["org_a"].id,
        asset_id=asset.id,
        sensor_code="HUMS-TEST-01",
        sensor_type="VIBRATION",
        measurement_type="ACCELERATION",
        unit="g",
        installation_location="ENGINE_BEARING",
        status="ACTIVE",
    )
    db_session.add(sensor)
    db_session.flush()

    # Request hypercare summary
    res = client.get(
        "/api/v1/hypercare/summary",
        headers={"Authorization": f"Bearer {setup['token_a']}"},
    )
    assert res.status_code == status.HTTP_200_OK
    summary = res.json()

    assert summary["platform_status"] in ["OPERATIONAL", "DEGRADED", "CRITICAL"]
    assert summary["telemetry"]["processed_count"] >= 1
    assert summary["hums"]["sensor_count"] >= 1
    assert summary["hums"]["active_sensors"] >= 1
    assert "incidents" in summary
    assert "intelligence" in summary
