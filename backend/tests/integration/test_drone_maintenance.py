"""M17.4A/B: usage-based maintenance for Drone (Asset), extending the
existing MaintenanceRequirement/MaintenanceRequirementApplicability/
MaintenanceAccomplishment architecture (originally aircraft-only) rather
than duplicating it. Flight records (M17.3) remain the sole utilization
source of truth -- maintenance_service never independently counts hours
or cycles, it only calls flight_service.get_utilization.
"""

import uuid

from app.core.deps import get_db_session
from app.main import app


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


def _org_id(client, token):
    return uuid.UUID(client.get("/api/v1/auth/me", headers=_auth(token)).json()["organization_id"])


def _add_role_user(db_session, org_id, email, role_name):
    from app.core.security import hash_password
    from app.models.user import User, UserRole

    user = User(
        organization_id=org_id,
        email=email,
        hashed_password=hash_password("supersecret123"),
        full_name="Role User",
        is_active=True,
    )
    db_session.add(user)
    db_session.flush()
    db_session.add(UserRole(user_id=user.id, role_name=role_name, organization_id=org_id))
    db_session.commit()
    return user


def _drone(client, token, registration="DRN-MX-001"):
    resp = client.post(
        "/api/v1/drones", headers=_auth(token), json={"registration": registration}
    )
    assert resp.status_code == 201
    return resp.json()


def _requirement(client, token, interval_type, **interval_kwargs):
    payload = {
        "description": "Rotor inspection",
        "ata_chapter": "61",
        "interval_type": interval_type,
        **interval_kwargs,
    }
    resp = client.post("/api/v1/maintenance-requirements", headers=_auth(token), json=payload)
    assert resp.status_code == 201
    return resp.json()


def _fly(client, token, drone_id, minutes, cycles=1, flown_at="2026-01-01T10:00:00Z"):
    resp = client.post(
        f"/api/v1/drones/{drone_id}/flights",
        headers=_auth(token),
        json={"flown_at": flown_at, "duration_minutes": minutes, "cycles": cycles},
    )
    assert resp.status_code == 201
    return resp.json()


class TestApplicability:
    def test_link_requirement_to_drone(self, client):
        tokens = _register(client, "MX Org 1", "mx1@example.com")
        drone = _drone(client, tokens["access_token"])
        requirement = _requirement(client, tokens["access_token"], "FLIGHT_HOURS", fh_interval=100)

        resp = client.post(
            f"/api/v1/drones/{drone['id']}/maintenance-requirements/{requirement['id']}/applicability",
            headers=_auth(tokens["access_token"]),
        )
        assert resp.status_code == 201
        assert resp.json()["id"] == requirement["id"]

    def test_cross_tenant_applicability_rejected(self, client):
        org_a = _register(client, "MX Iso Org A1", "mx-iso-a1@example.com")
        org_b = _register(client, "MX Iso Org B1", "mx-iso-b1@example.com")
        drone_a = _drone(client, org_a["access_token"], "DRN-MX-ISO-A1")
        requirement_b = _requirement(client, org_b["access_token"], "FLIGHT_HOURS", fh_interval=100)

        resp = client.post(
            f"/api/v1/drones/{drone_a['id']}/maintenance-requirements/{requirement_b['id']}/applicability",
            headers=_auth(org_a["access_token"]),
        )
        assert resp.status_code == 404

    def test_write_requires_drone_write_permission(self, client, db_session):
        tokens = _register(client, "MX RBAC Org 1", "mx-rbac-owner1@example.com")
        org_id = _org_id(client, tokens["access_token"])
        drone = _drone(client, tokens["access_token"], "DRN-MX-RBAC-1")
        requirement = _requirement(client, tokens["access_token"], "FLIGHT_HOURS", fh_interval=100)
        viewer = _add_role_user(db_session, org_id, "mx-rbac-viewer1@example.com", "VIEWER")
        viewer_tokens = _login(client, viewer.email)

        resp = client.post(
            f"/api/v1/drones/{drone['id']}/maintenance-requirements/{requirement['id']}/applicability",
            headers=_auth(viewer_tokens["access_token"]),
        )
        assert resp.status_code == 403


class TestUsageBasedEvaluation:
    def test_flight_hours_not_due(self, client):
        tokens = _register(client, "MX Org 2", "mx2@example.com")
        drone = _drone(client, tokens["access_token"])
        requirement = _requirement(client, tokens["access_token"], "FLIGHT_HOURS", fh_interval=100)
        client.post(
            f"/api/v1/drones/{drone['id']}/maintenance-requirements/{requirement['id']}/applicability",
            headers=_auth(tokens["access_token"]),
        )
        _fly(client, tokens["access_token"], drone["id"], minutes=60 * 10)  # 10 hours

        resp = client.get(
            f"/api/v1/drones/{drone['id']}/maintenance-due", headers=_auth(tokens["access_token"])
        )
        assert resp.status_code == 200
        item = resp.json()[0]
        assert item["due_status"] == "NOT_DUE"
        assert item["current_usage"] == 10.0
        assert item["remaining_usage"] == 90.0

    def test_flight_hours_due_soon_at_90_percent(self, client):
        tokens = _register(client, "MX Org 3", "mx3@example.com")
        drone = _drone(client, tokens["access_token"])
        requirement = _requirement(client, tokens["access_token"], "FLIGHT_HOURS", fh_interval=100)
        client.post(
            f"/api/v1/drones/{drone['id']}/maintenance-requirements/{requirement['id']}/applicability",
            headers=_auth(tokens["access_token"]),
        )
        _fly(client, tokens["access_token"], drone["id"], minutes=60 * 92)  # 92 hours

        resp = client.get(
            f"/api/v1/drones/{drone['id']}/maintenance-due", headers=_auth(tokens["access_token"])
        )
        item = resp.json()[0]
        assert item["due_status"] == "DUE_SOON"
        assert item["current_usage"] == 92.0
        assert item["remaining_usage"] == 8.0

    def test_flight_hours_overdue_at_threshold(self, client):
        tokens = _register(client, "MX Org 4", "mx4@example.com")
        drone = _drone(client, tokens["access_token"])
        requirement = _requirement(client, tokens["access_token"], "FLIGHT_HOURS", fh_interval=100)
        client.post(
            f"/api/v1/drones/{drone['id']}/maintenance-requirements/{requirement['id']}/applicability",
            headers=_auth(tokens["access_token"]),
        )
        _fly(client, tokens["access_token"], drone["id"], minutes=60 * 100)  # exactly 100 hours

        resp = client.get(
            f"/api/v1/drones/{drone['id']}/maintenance-due", headers=_auth(tokens["access_token"])
        )
        item = resp.json()[0]
        assert item["due_status"] == "OVERDUE"
        assert item["remaining_usage"] == 0.0

    def test_flight_cycles_evaluation(self, client):
        tokens = _register(client, "MX Org 5", "mx5@example.com")
        drone = _drone(client, tokens["access_token"])
        requirement = _requirement(client, tokens["access_token"], "FLIGHT_CYCLES", fc_interval=200)
        client.post(
            f"/api/v1/drones/{drone['id']}/maintenance-requirements/{requirement['id']}/applicability",
            headers=_auth(tokens["access_token"]),
        )
        _fly(client, tokens["access_token"], drone["id"], minutes=30, cycles=185)

        resp = client.get(
            f"/api/v1/drones/{drone['id']}/maintenance-due", headers=_auth(tokens["access_token"])
        )
        item = resp.json()[0]
        assert item["due_status"] == "DUE_SOON"
        assert item["current_usage"] == 185.0
        assert item["remaining_usage"] == 15.0

    def test_no_flights_yet_is_not_due(self, client):
        tokens = _register(client, "MX Org 6", "mx6@example.com")
        drone = _drone(client, tokens["access_token"])
        requirement = _requirement(client, tokens["access_token"], "FLIGHT_HOURS", fh_interval=100)
        client.post(
            f"/api/v1/drones/{drone['id']}/maintenance-requirements/{requirement['id']}/applicability",
            headers=_auth(tokens["access_token"]),
        )

        resp = client.get(
            f"/api/v1/drones/{drone['id']}/maintenance-due", headers=_auth(tokens["access_token"])
        )
        item = resp.json()[0]
        assert item["due_status"] == "NOT_DUE"
        assert item["current_usage"] == 0.0

    def test_no_applicable_requirements_returns_empty_list(self, client):
        tokens = _register(client, "MX Org 7", "mx7@example.com")
        drone = _drone(client, tokens["access_token"])

        resp = client.get(
            f"/api/v1/drones/{drone['id']}/maintenance-due", headers=_auth(tokens["access_token"])
        )
        assert resp.status_code == 200
        assert resp.json() == []


class TestAccomplishmentResetsInterval:
    def test_accomplishment_resets_usage_baseline(self, client):
        tokens = _register(client, "MX Org 8", "mx8@example.com")
        drone = _drone(client, tokens["access_token"])
        requirement = _requirement(client, tokens["access_token"], "FLIGHT_HOURS", fh_interval=100)
        client.post(
            f"/api/v1/drones/{drone['id']}/maintenance-requirements/{requirement['id']}/applicability",
            headers=_auth(tokens["access_token"]),
        )
        _fly(
            client, tokens["access_token"], drone["id"],
            minutes=60 * 100, flown_at="2026-01-01T10:00:00Z",
        )

        due = client.get(
            f"/api/v1/drones/{drone['id']}/maintenance-due", headers=_auth(tokens["access_token"])
        ).json()[0]
        assert due["due_status"] == "OVERDUE"

        # Record the accomplishment (maintenance performed) after the flight.
        accomplish_resp = client.post(
            f"/api/v1/drones/{drone['id']}/maintenance-requirements/{requirement['id']}/accomplishments",
            headers=_auth(tokens["access_token"]),
            json={"accomplished_at": "2026-01-02"},
        )
        assert accomplish_resp.status_code == 201

        # A flight logged BEFORE the accomplishment must not count toward
        # the new interval -- only usage since the accomplishment date.
        _fly(
            client, tokens["access_token"], drone["id"],
            minutes=60 * 5, flown_at="2026-01-03T10:00:00Z",
        )
        due_after = client.get(
            f"/api/v1/drones/{drone['id']}/maintenance-due", headers=_auth(tokens["access_token"])
        ).json()[0]
        assert due_after["due_status"] == "NOT_DUE"
        assert due_after["current_usage"] == 5.0
        assert due_after["last_accomplished_at"] == "2026-01-02"


class TestTenantIsolation:
    def test_cross_tenant_maintenance_due_returns_404(self, client):
        org_a = _register(client, "MX Iso Org A2", "mx-iso-a2@example.com")
        org_b = _register(client, "MX Iso Org B2", "mx-iso-b2@example.com")
        drone_a = _drone(client, org_a["access_token"], "DRN-MX-ISO-A2")

        resp = client.get(
            f"/api/v1/drones/{drone_a['id']}/maintenance-due", headers=_auth(org_b["access_token"])
        )
        assert resp.status_code == 404

    def test_cross_tenant_accomplishment_rejected(self, client):
        org_a = _register(client, "MX Iso Org A3", "mx-iso-a3@example.com")
        org_b = _register(client, "MX Iso Org B3", "mx-iso-b3@example.com")
        drone_a = _drone(client, org_a["access_token"], "DRN-MX-ISO-A3")
        requirement_a = _requirement(client, org_a["access_token"], "FLIGHT_HOURS", fh_interval=100)

        resp = client.post(
            f"/api/v1/drones/{drone_a['id']}/maintenance-requirements/{requirement_a['id']}/accomplishments",
            headers=_auth(org_b["access_token"]),
            json={"accomplished_at": "2026-01-01"},
        )
        assert resp.status_code == 404

    def test_org_b_usage_never_affects_org_a_evaluation(self, client):
        org_a = _register(client, "MX Iso Org A4", "mx-iso-a4@example.com")
        org_b = _register(client, "MX Iso Org B4", "mx-iso-b4@example.com")
        drone_a = _drone(client, org_a["access_token"], "DRN-MX-ISO-A4")
        drone_b = _drone(client, org_b["access_token"], "DRN-MX-ISO-B4")
        req_a = _requirement(client, org_a["access_token"], "FLIGHT_HOURS", fh_interval=100)
        client.post(
            f"/api/v1/drones/{drone_a['id']}/maintenance-requirements/{req_a['id']}/applicability",
            headers=_auth(org_a["access_token"]),
        )
        _fly(client, org_a["access_token"], drone_a["id"], minutes=60 * 5)
        # Org B logs a large amount of usage on ITS OWN drone -- must never
        # leak into org A's evaluation.
        _fly(client, org_b["access_token"], drone_b["id"], minutes=60 * 500)

        due_a = client.get(
            f"/api/v1/drones/{drone_a['id']}/maintenance-due", headers=_auth(org_a["access_token"])
        ).json()[0]
        assert due_a["current_usage"] == 5.0


class TestDeploymentReadinessRegression:
    def test_calendar_deployment_readiness_still_works(self, client, db_session):
        # Regression: the existing has_overdue_maintenance_for_asset ->
        # deployment-readiness path (calendar-based, pre-M17.4) must be
        # unaffected by the _evaluate_for_asset refactor.
        tokens = _register(client, "MX Readiness Org 1", "mx-readiness1@example.com")
        org_id = _org_id(client, tokens["access_token"])
        drone = _drone(client, tokens["access_token"], "DRN-MX-READY-1")
        client.post(
            f"/api/v1/drones/{drone['id']}/batteries",
            headers=_auth(tokens["access_token"]),
            json={"serial_number": "BATT-MX-READY"},
        )
        asset_id = uuid.UUID(drone["id"])

        from datetime import UTC, datetime

        from app.models.maintenance_requirement import (
            MaintenanceAccomplishment,
            MaintenanceRequirement,
            MaintenanceRequirementApplicability,
        )

        requirement = MaintenanceRequirement(
            organization_id=org_id,
            description="Overdue check",
            ata_chapter="05",
            interval_type="CALENDAR",
            calendar_interval_days=30,
        )
        db_session.add(requirement)
        db_session.commit()
        db_session.add(
            MaintenanceRequirementApplicability(
                organization_id=org_id, requirement_id=requirement.id, asset_id=asset_id
            )
        )
        db_session.commit()
        db_session.add(
            MaintenanceAccomplishment(
                organization_id=org_id,
                requirement_id=requirement.id,
                asset_id=asset_id,
                accomplished_at=datetime(2020, 1, 1, tzinfo=UTC).date(),
            )
        )
        db_session.commit()

        resp = client.get(
            f"/api/v1/drones/{drone['id']}/deployment-readiness",
            headers=_auth(tokens["access_token"]),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "BLOCKED"
        assert "Maintenance overdue" in body["blockers"]

        # Also verify the new full maintenance-due listing surfaces the
        # same OVERDUE status for this calendar requirement.
        due = client.get(
            f"/api/v1/drones/{drone['id']}/maintenance-due", headers=_auth(tokens["access_token"])
        ).json()
        assert due[0]["due_status"] == "OVERDUE"
        assert due[0]["due_date"] is not None
