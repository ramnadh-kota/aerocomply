"""Regression test for a confirmed defect found during the security audit:
get_current_user only decoded the JWT and never re-checked the caller's
organization status, so an access token issued BEFORE an organization was
suspended kept working, at full privilege, for the rest of its TTL (up to
ACCESS_TOKEN_EXPIRE_MINUTES). Login and refresh already refused a
suspended org (app/services/auth_service.py) — this proves the same
refusal now applies to a request using an already-issued access token.
"""

from app.core.security import create_access_token
from app.models.organization import Organization, OrganizationStatus
from app.models.user import User, UserRole


def _register(client, org_name, email):
    resp = client.post(
        "/api/v1/auth/register-organization",
        json={
            "organization_name": org_name,
            "admin_email": email,
            "admin_full_name": "Admin",
            "admin_password": "supersecret123",
        },
    )
    assert resp.status_code == 201
    return resp.json()


def test_existing_access_token_is_rejected_after_organization_is_suspended(client, db_session):
    tokens = _register(client, "Revocation Test MRO", "admin@revocation-test.com")
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}

    # The token works before suspension.
    ok = client.get("/api/v1/aircraft", headers=headers)
    assert ok.status_code == 200

    org = db_session.query(Organization).filter(Organization.name == "Revocation Test MRO").one()
    org.status = OrganizationStatus.SUSPENDED
    db_session.add(org)
    db_session.commit()

    # The SAME already-issued access token must now be refused — not
    # merely refresh/login, but every authenticated request.
    blocked = client.get("/api/v1/aircraft", headers=headers)
    assert blocked.status_code == 401


def test_platform_admin_own_org_suspension_also_revokes_their_token(db_session, client):
    """PLATFORM_MANAGE is unrelated to this check — even a platform admin's
    own organization being suspended must revoke their in-flight token,
    proving the check is unconditional or on organization_id, not gated by
    role."""
    org = Organization(name="Platform Ops Revocation Test")
    db_session.add(org)
    db_session.flush()
    user = User(
        organization_id=org.id,
        email="ops-revoke@kotas-aerospace-internal.com",
        hashed_password="$argon2id$v=19$m=65536,t=3,p=4$placeholder",
        full_name="Platform Admin",
        is_active=True,
    )
    db_session.add(user)
    db_session.flush()
    db_session.add(UserRole(user_id=user.id, role_name="PLATFORM_ADMIN", organization_id=org.id))
    db_session.commit()

    token = create_access_token(user.id, org.id, ["PLATFORM_ADMIN"], email=user.email)
    headers = {"Authorization": f"Bearer {token}"}

    ok = client.get("/api/v1/platform/organizations", headers=headers)
    assert ok.status_code == 200

    org.status = OrganizationStatus.SUSPENDED
    db_session.add(org)
    db_session.commit()

    blocked = client.get("/api/v1/platform/organizations", headers=headers)
    assert blocked.status_code == 401
