"""Phase 18.6: Drone Operations vertical slice
(drone_service/battery_service/component_service/flight_service/
readiness_service + /api/v1/drones).

Covers create/get/list/update, tenant isolation, permission enforcement,
utilization calculation, existing Aircraft/MRO behavior unaffected, and
deterministic deployment readiness (ready, grounded, maintenance overdue,
battery critical, failed inspection, and multiple blockers combined).
"""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.core.security import hash_password
from app.models.audit_event import AuditEvent
from app.models.inspection_requirement import InspectionRequirement, InspectionRequirementStatus
from app.models.maintenance_requirement import (
    MaintenanceAccomplishment,
    MaintenanceRequirement,
    MaintenanceRequirementApplicability,
)
from app.models.plan import Plan, PlanFeature
from app.models.subscription import Subscription, SubscriptionStatus
from app.models.user import User, UserRole
from app.models.work_order import WorkOrder


def _entitle_drone_ops(db_session, org_id):
    """M21.5: GET /api/v1/drones and GET /api/v1/drones/{id} are now gated
    by require_feature("drone_fleet_management") in addition to
    Permission.DRONE_READ (see app/api/v1/drones.py). Pre-existing tests in
    this file registered organizations with no subscription at all, which
    require_feature correctly denies -- this helper is test-fixture
    maintenance, not a product behavior change, giving the org a real
    ACTIVE subscription on a plan that includes the feature so the tests
    keep exercising what they always meant to exercise (RBAC/tenancy on the
    drone endpoints), not the newly-added entitlement gate."""
    plan = Plan(name=f"Drone-Test-Plan-{org_id}", code=f"drone-test-{org_id}", is_active=True)
    db_session.add(plan)
    db_session.commit()
    db_session.refresh(plan)
    db_session.add(
        PlanFeature(plan_id=plan.id, feature_key="drone_fleet_management", enabled=True)
    )
    db_session.add(
        Subscription(
            organization_id=org_id,
            plan_id=plan.id,
            status=SubscriptionStatus.ACTIVE,
            starts_at=datetime.now(UTC) - timedelta(days=1),
            ends_at=None,
        )
    )
    db_session.commit()


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
    def test_create_get_list_drone(self, client, db_session):
        tokens = _register(client, "Drone Org 1", "drone-admin1@example.com")
        org_id = uuid.UUID(
            client.get("/api/v1/auth/me", headers=_auth(tokens["access_token"])).json()[
                "organization_id"
            ]
        )
        _entitle_drone_ops(db_session, org_id)
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

    def test_existing_aircraft_asset_not_listed_as_drone(self, client, db_session):
        tokens = _register(client, "Drone Org 3", "drone-admin3@example.com")
        org_id = uuid.UUID(
            client.get("/api/v1/auth/me", headers=_auth(tokens["access_token"])).json()[
                "organization_id"
            ]
        )
        _entitle_drone_ops(db_session, org_id)
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
        _entitle_drone_ops(db_session, org_id)
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

    def test_cross_tenant_get_drone_returns_404(self, client, db_session):
        org_a = _register(client, "Drone Isolation Org A", "drone-iso-a@example.com")
        org_b = _register(client, "Drone Isolation Org B", "drone-iso-b@example.com")
        org_b_id = uuid.UUID(
            client.get("/api/v1/auth/me", headers=_auth(org_b["access_token"])).json()[
                "organization_id"
            ]
        )
        _entitle_drone_ops(db_session, org_b_id)
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


class TestFindingReadinessIntegration:
    """M21.1: unresolved Findings (app/models/finding.py) now contribute a
    blocker to drone deployment-readiness (readiness_service.py), reusing
    the existing Finding model/API end-to-end rather than any new engine."""

    def _drone_with_good_battery(self, client, token):
        drone = client.post("/api/v1/drones", headers=_auth(token), json=_drone_payload()).json()
        client.post(
            f"/api/v1/drones/{drone['id']}/batteries",
            headers=_auth(token),
            json={"serial_number": "BATT-READY"},
        )
        return drone

    def _create_finding(self, client, token, asset_id, **overrides):
        payload = {
            "title": "Propeller nick observed",
            "description": "Found during pre-flight inspection",
            "severity": "MAJOR",
            "asset_id": asset_id,
        }
        payload.update(overrides)
        resp = client.post("/api/v1/findings", headers=_auth(token), json=payload)
        assert resp.status_code == 201
        return resp.json()

    def test_no_findings_no_finding_blocker(self, client):
        tokens = _register(client, "Finding Readiness Org 1", "finding-ready-1@example.com")
        drone = self._drone_with_good_battery(client, tokens["access_token"])

        resp = client.get(
            f"/api/v1/drones/{drone['id']}/deployment-readiness",
            headers=_auth(tokens["access_token"]),
        )
        body = resp.json()
        assert body["status"] == "READY"
        assert body.get("finding_blockers", []) == []

    def test_unresolved_finding_produces_blocker(self, client):
        tokens = _register(client, "Finding Readiness Org 2", "finding-ready-2@example.com")
        drone = self._drone_with_good_battery(client, tokens["access_token"])
        finding = self._create_finding(client, tokens["access_token"], drone["id"])

        resp = client.get(
            f"/api/v1/drones/{drone['id']}/deployment-readiness",
            headers=_auth(tokens["access_token"]),
        )
        body = resp.json()
        assert body["status"] == "BLOCKED"
        assert any("Unresolved finding" in b for b in body["blockers"])
        assert len(body["finding_blockers"]) == 1
        assert body["finding_blockers"][0]["finding_id"] == finding["id"]
        assert body["finding_blockers"][0]["severity"] == "MAJOR"
        assert body["finding_blockers"][0]["status"] == "OPEN"

    def test_closed_finding_produces_no_blocker(self, client):
        tokens = _register(client, "Finding Readiness Org 3", "finding-ready-3@example.com")
        drone = self._drone_with_good_battery(client, tokens["access_token"])
        finding = self._create_finding(client, tokens["access_token"], drone["id"])

        client.post(
            f"/api/v1/findings/{finding['id']}/dispositions",
            headers=_auth(tokens["access_token"]),
            json={"disposition_type": "NO_ACTION_REQUIRED"},
        )
        close_resp = client.post(
            f"/api/v1/findings/{finding['id']}/close", headers=_auth(tokens["access_token"])
        )
        assert close_resp.status_code == 200

        resp = client.get(
            f"/api/v1/drones/{drone['id']}/deployment-readiness",
            headers=_auth(tokens["access_token"]),
        )
        body = resp.json()
        assert body["status"] == "READY"
        assert body.get("finding_blockers", []) == []

    def test_multiple_findings_mixed_resolution_only_unresolved_block(self, client):
        tokens = _register(client, "Finding Readiness Org 4", "finding-ready-4@example.com")
        drone = self._drone_with_good_battery(client, tokens["access_token"])
        open_finding = self._create_finding(
            client, tokens["access_token"], drone["id"], title="Open finding"
        )
        closed_finding = self._create_finding(
            client, tokens["access_token"], drone["id"], title="Closed finding"
        )
        client.post(
            f"/api/v1/findings/{closed_finding['id']}/dispositions",
            headers=_auth(tokens["access_token"]),
            json={"disposition_type": "NO_ACTION_REQUIRED"},
        )
        client.post(
            f"/api/v1/findings/{closed_finding['id']}/close", headers=_auth(tokens["access_token"])
        )

        resp = client.get(
            f"/api/v1/drones/{drone['id']}/deployment-readiness",
            headers=_auth(tokens["access_token"]),
        )
        body = resp.json()
        assert body["status"] == "BLOCKED"
        assert len(body["finding_blockers"]) == 1
        assert body["finding_blockers"][0]["finding_id"] == open_finding["id"]

    def test_finding_lifecycle_reflected_in_fresh_readiness_call(self, client):
        tokens = _register(client, "Finding Readiness Org 5", "finding-ready-5@example.com")
        drone = self._drone_with_good_battery(client, tokens["access_token"])

        ready_before = client.get(
            f"/api/v1/drones/{drone['id']}/deployment-readiness",
            headers=_auth(tokens["access_token"]),
        ).json()
        assert ready_before["status"] == "READY"

        finding = self._create_finding(client, tokens["access_token"], drone["id"])
        blocked = client.get(
            f"/api/v1/drones/{drone['id']}/deployment-readiness",
            headers=_auth(tokens["access_token"]),
        ).json()
        assert blocked["status"] == "BLOCKED"

        client.post(
            f"/api/v1/findings/{finding['id']}/dispositions",
            headers=_auth(tokens["access_token"]),
            json={"disposition_type": "NO_ACTION_REQUIRED"},
        )
        client.post(
            f"/api/v1/findings/{finding['id']}/close", headers=_auth(tokens["access_token"])
        )
        ready_after = client.get(
            f"/api/v1/drones/{drone['id']}/deployment-readiness",
            headers=_auth(tokens["access_token"]),
        ).json()
        assert ready_after["status"] == "READY"

    def test_cross_org_finding_never_leaks_into_other_org_readiness(self, client):
        org_a = _register(client, "Finding Readiness Org A", "finding-ready-a@example.com")
        org_b = _register(client, "Finding Readiness Org B", "finding-ready-b@example.com")
        drone_a = self._drone_with_good_battery(client, org_a["access_token"])
        drone_b = self._drone_with_good_battery(client, org_b["access_token"])
        self._create_finding(client, org_a["access_token"], drone_a["id"])

        resp_a = client.get(
            f"/api/v1/drones/{drone_a['id']}/deployment-readiness",
            headers=_auth(org_a["access_token"]),
        ).json()
        assert resp_a["status"] == "BLOCKED"

        resp_b = client.get(
            f"/api/v1/drones/{drone_b['id']}/deployment-readiness",
            headers=_auth(org_b["access_token"]),
        ).json()
        assert resp_b["status"] == "READY"
        assert resp_b.get("finding_blockers", []) == []


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
