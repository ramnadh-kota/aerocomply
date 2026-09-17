"""Phase 18.6: Drone Operations vertical slice
(drone_service/battery_service/component_service/flight_service/
readiness_service + /api/v1/drones).

Covers create/get/list/update, tenant isolation, permission enforcement,
utilization calculation, existing Aircraft/MRO behavior unaffected, and
deterministic deployment readiness (ready, grounded, maintenance overdue,
battery critical, failed inspection, and multiple blockers combined).
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import select

from app.core.security import hash_password
from app.models.audit_event import AuditEvent
from app.models.inspection_requirement import InspectionRequirement, InspectionRequirementStatus
from app.models.maintenance_requirement import (
    MaintenanceAccomplishment,
    MaintenanceRequirement,
    MaintenanceRequirementApplicability,
)
from app.models.user import User, UserRole
from app.models.work_order import WorkOrder


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


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


def _drone_payload(*, registration="DRN-001"):
    return {"registration": registration, "manufacturer": "DJI", "model": "M300"}


class TestDroneCRUD:
    def test_create_get_list_drone(self, client):
        tokens = _register(client, "Drone Org 1", "drone-admin1@example.com")
        create = client.post(
            "/api/v1/drones", headers=_auth(tokens["access_token"]), json=_drone_payload()
        )
        assert create.status_code == 201
        body = create.json()
        assert body["asset_type"] == "DRONE"
        assert body["registration"] == "DRN-001"
        assert body["status"] == "ACTIVE"

        get_resp = client.get(f"/api/v1/drones/{body['id']}", headers=_auth(tokens["access_token"]))
        assert get_resp.status_code == 200

        listing = client.get("/api/v1/drones", headers=_auth(tokens["access_token"]))
        assert listing.status_code == 200
        assert any(d["id"] == body["id"] for d in listing.json())

    def test_update_drone(self, client):
        tokens = _register(client, "Drone Org 2", "drone-admin2@example.com")
        created = client.post(
            "/api/v1/drones", headers=_auth(tokens["access_token"]), json=_drone_payload()
        )
        asset_id = created.json()["id"]

        resp = client.patch(
            f"/api/v1/drones/{asset_id}",
            headers=_auth(tokens["access_token"]),
            json={"status": "GROUNDED"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "GROUNDED"

    def test_existing_aircraft_asset_not_listed_as_drone(self, client):
        tokens = _register(client, "Drone Org 3", "drone-admin3@example.com")
        client.post(
            "/api/v1/aircraft",
            headers=_auth(tokens["access_token"]),
            json={
                "registration": "N1DRN",
                "msn": "MSN-D1",
                "aircraft_type": "A320",
                "status": "ACTIVE",
            },
        )
        listing = client.get("/api/v1/drones", headers=_auth(tokens["access_token"]))
        assert listing.json() == []


class TestDroneTenantIsolationAndPermissions:
    def test_unauthenticated_rejected(self, client):
        resp = client.get("/api/v1/drones")
        assert resp.status_code == 401

    def test_viewer_can_read_not_write(self, client, db_session):
        tokens = _register(client, "Drone Viewer Org", "drone-viewer-owner@example.com")
        org_id = uuid.UUID(
            client.get("/api/v1/auth/me", headers=_auth(tokens["access_token"])).json()[
                "organization_id"
            ]
        )
        viewer = _add_viewer(db_session, org_id, "drone-viewer@example.com")
        viewer_tokens = _login(client, viewer.email)

        assert (
            client.get("/api/v1/drones", headers=_auth(viewer_tokens["access_token"])).status_code
            == 200
        )
        assert (
            client.post(
                "/api/v1/drones",
                headers=_auth(viewer_tokens["access_token"]),
                json=_drone_payload(),
            ).status_code
            == 403
        )

    def test_cross_tenant_get_drone_returns_404(self, client):
        org_a = _register(client, "Drone Isolation Org A", "drone-iso-a@example.com")
        org_b = _register(client, "Drone Isolation Org B", "drone-iso-b@example.com")
        created = client.post(
            "/api/v1/drones", headers=_auth(org_a["access_token"]), json=_drone_payload()
        )
        asset_id = created.json()["id"]

        resp = client.get(f"/api/v1/drones/{asset_id}", headers=_auth(org_b["access_token"]))
        assert resp.status_code == 404

    def test_cross_tenant_cannot_attach_battery(self, client):
        org_a = _register(client, "Drone Battery Iso Org A", "drone-batt-iso-a@example.com")
        org_b = _register(client, "Drone Battery Iso Org B", "drone-batt-iso-b@example.com")
        created = client.post(
            "/api/v1/drones", headers=_auth(org_a["access_token"]), json=_drone_payload()
        )
        asset_id = created.json()["id"]

        resp = client.post(
            f"/api/v1/drones/{asset_id}/batteries",
            headers=_auth(org_b["access_token"]),
            json={"serial_number": "BATT-HACK"},
        )
        assert resp.status_code == 404

    def test_cross_tenant_cannot_record_flight(self, client):
        org_a = _register(client, "Drone Flight Iso Org A", "drone-flight-iso-a@example.com")
        org_b = _register(client, "Drone Flight Iso Org B", "drone-flight-iso-b@example.com")
        created = client.post(
            "/api/v1/drones", headers=_auth(org_a["access_token"]), json=_drone_payload()
        )
        asset_id = created.json()["id"]

        resp = client.post(
            f"/api/v1/drones/{asset_id}/flights",
            headers=_auth(org_b["access_token"]),
            json={"flown_at": "2026-01-01T10:00:00Z", "duration_minutes": 20},
        )
        assert resp.status_code == 404

    def test_cross_tenant_cannot_read_readiness(self, client):
        org_a = _register(client, "Drone Readiness Iso Org A", "drone-ready-iso-a@example.com")
        org_b = _register(client, "Drone Readiness Iso Org B", "drone-ready-iso-b@example.com")
        created = client.post(
            "/api/v1/drones", headers=_auth(org_a["access_token"]), json=_drone_payload()
        )
        asset_id = created.json()["id"]

        resp = client.get(
            f"/api/v1/drones/{asset_id}/deployment-readiness", headers=_auth(org_b["access_token"])
        )
        assert resp.status_code == 404


class TestBatteryAndComponent:
    def test_attach_and_list_battery(self, client):
        tokens = _register(client, "Battery Org 1", "battery-admin1@example.com")
        drone = client.post(
            "/api/v1/drones", headers=_auth(tokens["access_token"]), json=_drone_payload()
        ).json()

        resp = client.post(
            f"/api/v1/drones/{drone['id']}/batteries",
            headers=_auth(tokens["access_token"]),
            json={"serial_number": "BATT-1", "manufacturer": "DJI", "capacity_mah": 5000},
        )
        assert resp.status_code == 201
        assert resp.json()["status"] == "GOOD"
        assert resp.json()["cycle_count"] == 0

        listing = client.get(
            f"/api/v1/drones/{drone['id']}/batteries", headers=_auth(tokens["access_token"])
        )
        assert len(listing.json()) == 1

    def test_update_battery_status(self, client):
        tokens = _register(client, "Battery Org 2", "battery-admin2@example.com")
        drone = client.post(
            "/api/v1/drones", headers=_auth(tokens["access_token"]), json=_drone_payload()
        ).json()
        battery = client.post(
            f"/api/v1/drones/{drone['id']}/batteries",
            headers=_auth(tokens["access_token"]),
            json={"serial_number": "BATT-2"},
        ).json()

        resp = client.patch(
            f"/api/v1/batteries/{battery['id']}",
            headers=_auth(tokens["access_token"]),
            json={"status": "CRITICAL", "health_percent": 40},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "CRITICAL"
        assert resp.json()["health_percent"] == 40

    def test_attach_component(self, client):
        tokens = _register(client, "Component Org 1", "component-admin1@example.com")
        drone = client.post(
            "/api/v1/drones", headers=_auth(tokens["access_token"]), json=_drone_payload()
        ).json()

        resp = client.post(
            f"/api/v1/drones/{drone['id']}/components",
            headers=_auth(tokens["access_token"]),
            json={"component_type": "GPS", "name": "Primary GPS", "serial_number": "GPS-1"},
        )
        assert resp.status_code == 201
        assert resp.json()["component_type"] == "GPS"

    def test_cross_tenant_cannot_attach_component(self, client):
        org_a = _register(client, "Component Iso Org A", "component-iso-a@example.com")
        org_b = _register(client, "Component Iso Org B", "component-iso-b@example.com")
        drone = client.post(
            "/api/v1/drones", headers=_auth(org_a["access_token"]), json=_drone_payload()
        ).json()

        resp = client.post(
            f"/api/v1/drones/{drone['id']}/components",
            headers=_auth(org_b["access_token"]),
            json={"component_type": "GPS", "name": "Hack GPS"},
        )
        assert resp.status_code == 404


class TestFlightAndUtilization:
    def test_record_flight_and_utilization_sums_correctly(self, client):
        tokens = _register(client, "Flight Org 1", "flight-admin1@example.com")
        drone = client.post(
            "/api/v1/drones", headers=_auth(tokens["access_token"]), json=_drone_payload()
        ).json()

        for minutes in (20, 35):
            resp = client.post(
                f"/api/v1/drones/{drone['id']}/flights",
                headers=_auth(tokens["access_token"]),
                json={"flown_at": "2026-01-01T10:00:00Z", "duration_minutes": minutes, "cycles": 1},
            )
            assert resp.status_code == 201

        util = client.get(
            f"/api/v1/drones/{drone['id']}/utilization", headers=_auth(tokens["access_token"])
        ).json()
        assert util["total_flights"] == 2
        assert util["total_minutes"] == 55
        assert util["total_cycles"] == 2

    def test_flight_increments_attached_battery_cycle_count(self, client):
        tokens = _register(client, "Flight Org 2", "flight-admin2@example.com")
        drone = client.post(
            "/api/v1/drones", headers=_auth(tokens["access_token"]), json=_drone_payload()
        ).json()
        client.post(
            f"/api/v1/drones/{drone['id']}/batteries",
            headers=_auth(tokens["access_token"]),
            json={"serial_number": "BATT-CYCLE"},
        )
        client.post(
            f"/api/v1/drones/{drone['id']}/flights",
            headers=_auth(tokens["access_token"]),
            json={"flown_at": "2026-01-01T10:00:00Z", "duration_minutes": 20, "cycles": 3},
        )

        batteries = client.get(
            f"/api/v1/drones/{drone['id']}/batteries", headers=_auth(tokens["access_token"])
        ).json()
        assert batteries[0]["cycle_count"] == 3

    def test_existing_aircraft_work_order_flow_unaffected(self, client):
        """Regression: this milestone does not touch Aircraft/WorkOrder
        behavior -- confirms the existing aircraft-based work order flow
        still works exactly as before Phase 18.6."""
        tokens = _register(client, "Regression Org 1", "regression-admin1@example.com")
        aircraft = client.post(
            "/api/v1/aircraft",
            headers=_auth(tokens["access_token"]),
            json={
                "registration": "N9REG",
                "msn": "MSN-REG",
                "aircraft_type": "A320",
                "status": "ACTIVE",
            },
        ).json()
        wo = client.post(
            "/api/v1/work-orders",
            headers=_auth(tokens["access_token"]),
            json={"aircraft_id": aircraft["id"], "work_order_number": "WO-REG-1"},
        )
        assert wo.status_code == 201


class TestDeploymentReadiness:
    def _drone_with_good_battery(self, client, token):
        drone = client.post("/api/v1/drones", headers=_auth(token), json=_drone_payload()).json()
        client.post(
            f"/api/v1/drones/{drone['id']}/batteries",
            headers=_auth(token),
            json={"serial_number": "BATT-READY"},
        )
        return drone

    def test_ready_drone_returns_ready(self, client):
        tokens = _register(client, "Readiness Org 1", "readiness-admin1@example.com")
        drone = self._drone_with_good_battery(client, tokens["access_token"])

        resp = client.get(
            f"/api/v1/drones/{drone['id']}/deployment-readiness",
            headers=_auth(tokens["access_token"]),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "READY"
        assert body["blockers"] == []

    def test_grounded_drone_returns_blocked(self, client):
        tokens = _register(client, "Readiness Org 2", "readiness-admin2@example.com")
        drone = self._drone_with_good_battery(client, tokens["access_token"])
        client.patch(
            f"/api/v1/drones/{drone['id']}",
            headers=_auth(tokens["access_token"]),
            json={"status": "GROUNDED"},
        )

        resp = client.get(
            f"/api/v1/drones/{drone['id']}/deployment-readiness",
            headers=_auth(tokens["access_token"]),
        )
        body = resp.json()
        assert body["status"] == "BLOCKED"
        assert any("not active" in b for b in body["blockers"])

    def test_no_battery_returns_blocked(self, client):
        tokens = _register(client, "Readiness Org 3", "readiness-admin3@example.com")
        drone = client.post(
            "/api/v1/drones", headers=_auth(tokens["access_token"]), json=_drone_payload()
        ).json()

        resp = client.get(
            f"/api/v1/drones/{drone['id']}/deployment-readiness",
            headers=_auth(tokens["access_token"]),
        )
        body = resp.json()
        assert body["status"] == "BLOCKED"
        assert "No battery assigned" in body["blockers"]

    def test_battery_critical_returns_blocked(self, client):
        tokens = _register(client, "Readiness Org 4", "readiness-admin4@example.com")
        drone = client.post(
            "/api/v1/drones", headers=_auth(tokens["access_token"]), json=_drone_payload()
        ).json()
        battery = client.post(
            f"/api/v1/drones/{drone['id']}/batteries",
            headers=_auth(tokens["access_token"]),
            json={"serial_number": "BATT-CRIT"},
        ).json()
        client.patch(
            f"/api/v1/batteries/{battery['id']}",
            headers=_auth(tokens["access_token"]),
            json={"status": "CRITICAL"},
        )

        resp = client.get(
            f"/api/v1/drones/{drone['id']}/deployment-readiness",
            headers=_auth(tokens["access_token"]),
        )
        body = resp.json()
        assert body["status"] == "BLOCKED"
        assert "Battery critical" in body["blockers"]

    def test_maintenance_overdue_returns_blocked(self, client, db_session):
        tokens = _register(client, "Readiness Org 5", "readiness-admin5@example.com")
        org_id = uuid.UUID(
            client.get("/api/v1/auth/me", headers=_auth(tokens["access_token"])).json()[
                "organization_id"
            ]
        )
        drone = self._drone_with_good_battery(client, tokens["access_token"])
        asset_id = uuid.UUID(drone["id"])

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
                organization_id=org_id,
                requirement_id=requirement.id,
                aircraft_id=None,
                asset_id=asset_id,
            )
        )
        db_session.commit()
        db_session.add(
            MaintenanceAccomplishment(
                organization_id=org_id,
                requirement_id=requirement.id,
                aircraft_id=None,
                asset_id=asset_id,
                accomplished_at=datetime(2020, 1, 1, tzinfo=UTC).date(),
            )
        )
        db_session.commit()

        resp = client.get(
            f"/api/v1/drones/{drone['id']}/deployment-readiness",
            headers=_auth(tokens["access_token"]),
        )
        body = resp.json()
        assert body["status"] == "BLOCKED"
        assert "Maintenance overdue" in body["blockers"]

    def test_failed_inspection_returns_blocked(self, client, db_session):
        tokens = _register(client, "Readiness Org 6", "readiness-admin6@example.com")
        org_id = uuid.UUID(
            client.get("/api/v1/auth/me", headers=_auth(tokens["access_token"])).json()[
                "organization_id"
            ]
        )
        drone = self._drone_with_good_battery(client, tokens["access_token"])
        asset_id = uuid.UUID(drone["id"])

        work_order = WorkOrder(
            organization_id=org_id,
            asset_id=asset_id,
            aircraft_id=None,
            work_order_number="WO-INSP-1",
            status="OPEN",
            priority="NORMAL",
        )
        db_session.add(work_order)
        db_session.commit()
        db_session.add(
            InspectionRequirement(
                organization_id=org_id,
                work_order_id=work_order.id,
                required=True,
                status=InspectionRequirementStatus.REJECTED.value,
                rejection_reason="Damaged rotor",
            )
        )
        db_session.commit()

        resp = client.get(
            f"/api/v1/drones/{drone['id']}/deployment-readiness",
            headers=_auth(tokens["access_token"]),
        )
        body = resp.json()
        assert body["status"] == "BLOCKED"
        assert "Failed inspection" in body["blockers"]

    def test_multiple_blockers_returned_together(self, client):
        tokens = _register(client, "Readiness Org 7", "readiness-admin7@example.com")
        drone = client.post(
            "/api/v1/drones", headers=_auth(tokens["access_token"]), json=_drone_payload()
        ).json()
        client.patch(
            f"/api/v1/drones/{drone['id']}",
            headers=_auth(tokens["access_token"]),
            json={"status": "GROUNDED"},
        )

        resp = client.get(
            f"/api/v1/drones/{drone['id']}/deployment-readiness",
            headers=_auth(tokens["access_token"]),
        )
        body = resp.json()
        assert body["status"] == "BLOCKED"
        assert len(body["blockers"]) >= 2  # grounded + no battery


class TestAudit:
    def test_drone_and_battery_and_flight_record_audit_events(self, client, db_session):
        tokens = _register(client, "Audit Org 1", "drone-audit-admin1@example.com")
        drone = client.post(
            "/api/v1/drones", headers=_auth(tokens["access_token"]), json=_drone_payload()
        ).json()
        asset_id = uuid.UUID(drone["id"])
        client.post(
            f"/api/v1/drones/{drone['id']}/batteries",
            headers=_auth(tokens["access_token"]),
            json={"serial_number": "BATT-AUDIT"},
        )
        client.post(
            f"/api/v1/drones/{drone['id']}/flights",
            headers=_auth(tokens["access_token"]),
            json={"flown_at": "2026-01-01T10:00:00Z", "duration_minutes": 15},
        )

        actions = (
            db_session.execute(select(AuditEvent.action).where(AuditEvent.entity_id == asset_id))
            .scalars()
            .all()
        )
        assert "drone.created" in actions

        all_actions = db_session.execute(select(AuditEvent.action)).scalars().all()
        assert "battery.attached" in all_actions
        assert "flight.recorded" in all_actions
