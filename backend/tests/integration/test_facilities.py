"""Phase 18.4: Facilities Foundation
(app/services/facility_service.py + /api/v1/facilities).

Confirms tenant scoping, duplicate-code handling (per-org, not global),
cross-tenant IDOR rejection, permission enforcement, audit behavior, and
Asset.facility_id integration.
"""

import uuid

from sqlalchemy import select

from app.core.deps import get_db_session
from app.core.security import hash_password
from app.main import app
from app.models.asset import Asset, AssetType
from app.models.audit_event import AuditEvent
from app.models.facility import Facility
from app.models.organization import Organization
from app.models.user import User, UserRole


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _register(client, org_name, email):
    from tests.integration.conftest import make_platform_admin_headers

    db_session = next(app.dependency_overrides[get_db_session]())
    headers = make_platform_admin_headers(client, db_session)
    resp = client.post(
        "/api/v1/auth/register-organization",
        json={
            "organization_name": org_name,
            "admin_email": email,
            "admin_full_name": "Admin",
            "admin_password": "supersecret123",
        },
        headers=headers,
    )
    assert resp.status_code == 201
    return resp.json()


def _login(client, email, password="supersecret123"):
    resp = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200
    return resp.json()


def _add_viewer(db_session, org_id, email):
    user = User(
        organization_id=org_id,
        email=email,
        hashed_password=hash_password("supersecret123"),
        full_name="Viewer",
        is_active=True,
    )
    db_session.add(user)
    db_session.flush()
    db_session.add(UserRole(user_id=user.id, role_name="VIEWER", organization_id=org_id))
    db_session.commit()
    return user


def _facility_payload(*, code="HGR-01", facility_type="HANGAR"):
    return {
        "code": code,
        "name": "Main Hangar",
        "facility_type": facility_type,
        "description": "Primary maintenance hangar",
    }


class TestFacilityCRUD:
    def test_create_and_list_facility(self, client):
        tokens = _register(client, "Facility Org 1", "facility-admin1@example.com")
        create = client.post(
            "/api/v1/facilities", headers=_auth(tokens["access_token"]), json=_facility_payload()
        )
        assert create.status_code == 201
        body = create.json()
        assert body["code"] == "HGR-01"
        assert body["facility_type"] == "HANGAR"
        assert body["status"] == "ACTIVE"

        listing = client.get("/api/v1/facilities", headers=_auth(tokens["access_token"]))
        assert listing.status_code == 200
        assert any(f["id"] == body["id"] for f in listing.json())

    def test_get_facility(self, client):
        tokens = _register(client, "Facility Org 2", "facility-admin2@example.com")
        create = client.post(
            "/api/v1/facilities", headers=_auth(tokens["access_token"]), json=_facility_payload()
        )
        facility_id = create.json()["id"]

        resp = client.get(
            f"/api/v1/facilities/{facility_id}", headers=_auth(tokens["access_token"])
        )
        assert resp.status_code == 200
        assert resp.json()["id"] == facility_id

    def test_update_facility_name_and_status(self, client):
        tokens = _register(client, "Facility Org 3", "facility-admin3@example.com")
        create = client.post(
            "/api/v1/facilities", headers=_auth(tokens["access_token"]), json=_facility_payload()
        )
        facility_id = create.json()["id"]

        resp = client.patch(
            f"/api/v1/facilities/{facility_id}",
            headers=_auth(tokens["access_token"]),
            json={"name": "Renamed Hangar", "status": "INACTIVE"},
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "Renamed Hangar"
        assert resp.json()["status"] == "INACTIVE"

    def test_invalid_facility_type_rejected(self, client):
        tokens = _register(client, "Facility Org 4", "facility-admin4@example.com")
        resp = client.post(
            "/api/v1/facilities",
            headers=_auth(tokens["access_token"]),
            json=_facility_payload(facility_type="SPACESHIP"),
        )
        assert resp.status_code == 409

    def test_get_nonexistent_facility_404(self, client):
        tokens = _register(client, "Facility Org 5", "facility-admin5@example.com")
        resp = client.get(
            f"/api/v1/facilities/{uuid.uuid4()}", headers=_auth(tokens["access_token"])
        )
        assert resp.status_code == 404


class TestDuplicateCodeScoping:
    def test_duplicate_code_within_same_org_rejected(self, client):
        tokens = _register(client, "Facility Dup Org", "facility-dup1@example.com")
        first = client.post(
            "/api/v1/facilities", headers=_auth(tokens["access_token"]), json=_facility_payload()
        )
        assert first.status_code == 201

        second = client.post(
            "/api/v1/facilities", headers=_auth(tokens["access_token"]), json=_facility_payload()
        )
        assert second.status_code == 409

    def test_same_code_allowed_across_different_orgs(self, client):
        org_a = _register(client, "Facility Cross Org A", "facility-cross-a@example.com")
        org_b = _register(client, "Facility Cross Org B", "facility-cross-b@example.com")

        resp_a = client.post(
            "/api/v1/facilities", headers=_auth(org_a["access_token"]), json=_facility_payload()
        )
        resp_b = client.post(
            "/api/v1/facilities", headers=_auth(org_b["access_token"]), json=_facility_payload()
        )
        assert resp_a.status_code == 201
        assert resp_b.status_code == 201
        assert resp_a.json()["id"] != resp_b.json()["id"]


class TestTenantIsolation:
    def test_cross_tenant_get_returns_404(self, client):
        org_a = _register(client, "Facility Isolation Org A", "facility-iso-a@example.com")
        org_b = _register(client, "Facility Isolation Org B", "facility-iso-b@example.com")

        created = client.post(
            "/api/v1/facilities", headers=_auth(org_a["access_token"]), json=_facility_payload()
        )
        facility_id = created.json()["id"]

        cross_get = client.get(
            f"/api/v1/facilities/{facility_id}", headers=_auth(org_b["access_token"])
        )
        assert cross_get.status_code == 404

    def test_cross_tenant_patch_returns_404(self, client):
        org_a = _register(client, "Facility Isolation Org C", "facility-iso-c@example.com")
        org_b = _register(client, "Facility Isolation Org D", "facility-iso-d@example.com")

        created = client.post(
            "/api/v1/facilities", headers=_auth(org_a["access_token"]), json=_facility_payload()
        )
        facility_id = created.json()["id"]

        cross_patch = client.patch(
            f"/api/v1/facilities/{facility_id}",
            headers=_auth(org_b["access_token"]),
            json={"name": "Hijacked"},
        )
        assert cross_patch.status_code == 404

    def test_cross_tenant_facility_not_in_list(self, client):
        org_a = _register(client, "Facility Isolation Org E", "facility-iso-e@example.com")
        org_b = _register(client, "Facility Isolation Org F", "facility-iso-f@example.com")

        created = client.post(
            "/api/v1/facilities", headers=_auth(org_a["access_token"]), json=_facility_payload()
        )
        facility_id = created.json()["id"]

        listing_b = client.get("/api/v1/facilities", headers=_auth(org_b["access_token"]))
        assert all(f["id"] != facility_id for f in listing_b.json())

    def test_client_supplied_organization_id_ignored(self, client, db_session):
        """FacilityCreateRequest has no organization_id field -- the server
        always derives it from the authenticated caller. Confirms sending
        one anyway (extra field) is simply ignored, never trusted."""
        tokens = _register(client, "Facility Escape Org", "facility-escape@example.com")
        other_org = Organization(name="Facility Escape Target Org")
        db_session.add(other_org)
        db_session.commit()

        payload = _facility_payload()
        payload["organization_id"] = str(other_org.id)

        resp = client.post(
            "/api/v1/facilities", headers=_auth(tokens["access_token"]), json=payload
        )
        assert resp.status_code == 201
        created_facility = db_session.get(Facility, uuid.UUID(resp.json()["id"]))
        assert created_facility.organization_id != other_org.id


class TestAuthorization:
    def test_unauthenticated_rejected(self, client):
        resp = client.get("/api/v1/facilities")
        assert resp.status_code == 401

        resp2 = client.post("/api/v1/facilities", json=_facility_payload())
        assert resp2.status_code == 401

    def test_viewer_can_read_but_not_write(self, client, db_session):
        tokens = _register(client, "Facility Viewer Org", "facility-viewer-owner@example.com")
        org_id = uuid.UUID(
            client.get("/api/v1/auth/me", headers=_auth(tokens["access_token"])).json()[
                "organization_id"
            ]
        )
        viewer = _add_viewer(db_session, org_id, "facility-viewer@example.com")
        viewer_tokens = _login(client, viewer.email)

        read_resp = client.get("/api/v1/facilities", headers=_auth(viewer_tokens["access_token"]))
        assert read_resp.status_code == 200

        write_resp = client.post(
            "/api/v1/facilities",
            headers=_auth(viewer_tokens["access_token"]),
            json=_facility_payload(),
        )
        assert write_resp.status_code == 403


class TestAudit:
    def test_facility_creation_and_update_record_audit_events(self, client, db_session):
        tokens = _register(client, "Facility Audit Org", "facility-audit@example.com")
        created = client.post(
            "/api/v1/facilities", headers=_auth(tokens["access_token"]), json=_facility_payload()
        )
        facility_id = uuid.UUID(created.json()["id"])

        client.patch(
            f"/api/v1/facilities/{facility_id}",
            headers=_auth(tokens["access_token"]),
            json={"status": "INACTIVE"},
        )

        actions = (
            db_session.execute(
                select(AuditEvent.action).where(
                    AuditEvent.entity_type == "Facility", AuditEvent.entity_id == facility_id
                )
            )
            .scalars()
            .all()
        )
        assert "facility.created" in actions
        assert "facility.updated" in actions


class TestAssetIntegration:
    def test_asset_can_reference_facility(self, client, db_session):
        tokens = _register(client, "Facility Asset Org", "facility-asset@example.com")
        org_id = uuid.UUID(
            client.get("/api/v1/auth/me", headers=_auth(tokens["access_token"])).json()[
                "organization_id"
            ]
        )
        created = client.post(
            "/api/v1/facilities", headers=_auth(tokens["access_token"]), json=_facility_payload()
        )
        facility_id = uuid.UUID(created.json()["id"])

        asset = Asset(
            organization_id=org_id,
            asset_type=AssetType.AIRCRAFT,
            registration="N999FT",
            status="ACTIVE",
            facility_id=facility_id,
        )
        db_session.add(asset)
        db_session.commit()
        db_session.refresh(asset)

        assert asset.facility_id == facility_id

    def test_asset_facility_id_is_nullable(self, client, db_session):
        tokens = _register(client, "Facility Nullable Org", "facility-nullable@example.com")
        org_id = uuid.UUID(
            client.get("/api/v1/auth/me", headers=_auth(tokens["access_token"])).json()[
                "organization_id"
            ]
        )
        asset = Asset(
            organization_id=org_id,
            asset_type=AssetType.AIRCRAFT,
            registration="N888FT",
            status="ACTIVE",
        )
        db_session.add(asset)
        db_session.commit()
        db_session.refresh(asset)

        assert asset.facility_id is None
