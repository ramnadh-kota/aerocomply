"""M17.5A/B: usage-based maintenance for serialized Battery/Component,
extending the same MaintenanceRequirement architecture used by M17.4 for
the asset(Drone) level. Flight records + BatteryInstallation/
ComponentInstallation remain the sole sources of truth -- this file never
sets up fake usage counters, only real flights and real install/remove
operations via installation_service (matching M17.2A/M17.3B's own test
convention).
"""

import uuid

from app.services import installation_service


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


def _drone(client, token, registration="DRN-BCM-001"):
    resp = client.post(
        "/api/v1/drones", headers=_auth(token), json={"registration": registration}
    )
    assert resp.status_code == 201
    return resp.json()


def _battery(client, token, drone_id, serial="BATT-BCM-1"):
    resp = client.post(
        f"/api/v1/drones/{drone_id}/batteries",
        headers=_auth(token),
        json={"serial_number": serial},
    )
    assert resp.status_code == 201
    return resp.json()


def _component(client, token, drone_id, serial="COMP-BCM-1"):
    resp = client.post(
        f"/api/v1/drones/{drone_id}/components",
        headers=_auth(token),
        json={"component_type": "GPS", "name": "GPS", "serial_number": serial},
    )
    assert resp.status_code == 201
    return resp.json()


def _requirement(client, token, interval_type, **interval_kwargs):
    payload = {
        "description": "Cell inspection",
        "ata_chapter": "24",
        "interval_type": interval_type,
        **interval_kwargs,
    }
    resp = client.post("/api/v1/maintenance-requirements", headers=_auth(token), json=payload)
    assert resp.status_code == 201
    return resp.json()


def _fly(client, token, drone_id, minutes, cycles=1, flown_at="2030-01-01T10:00:00Z"):
    resp = client.post(
        f"/api/v1/drones/{drone_id}/flights",
        headers=_auth(token),
        json={"flown_at": flown_at, "duration_minutes": minutes, "cycles": cycles},
    )
    assert resp.status_code == 201
    return resp.json()


class TestBatteryUsageEvaluation:
    def test_battery_cycles_not_due(self, client):
        tokens = _register(client, "BCM Org 1", "bcm1@example.com")
        drone = _drone(client, tokens["access_token"])
        battery = _battery(client, tokens["access_token"], drone["id"])
        requirement = _requirement(
            client, tokens["access_token"], "BATTERY_CYCLES", fc_interval=100
        )
        resp = client.post(
            f"/api/v1/batteries/{battery['id']}/maintenance-requirements/{requirement['id']}/applicability",
            headers=_auth(tokens["access_token"]),
        )
        assert resp.status_code == 201

        _fly(client, tokens["access_token"], drone["id"], minutes=10, cycles=50)

        due = client.get(
            f"/api/v1/batteries/{battery['id']}/maintenance-due",
            headers=_auth(tokens["access_token"]),
        ).json()
        assert due[0]["due_status"] == "NOT_DUE"
        assert due[0]["current_usage"] == 50.0
        assert due[0]["lifetime_usage"] == 50.0

    def test_battery_cycles_due_soon_and_overdue(self, client):
        tokens = _register(client, "BCM Org 2", "bcm2@example.com")
        drone = _drone(client, tokens["access_token"])
        battery = _battery(client, tokens["access_token"], drone["id"])
        requirement = _requirement(
            client, tokens["access_token"], "BATTERY_CYCLES", fc_interval=100
        )
        client.post(
            f"/api/v1/batteries/{battery['id']}/maintenance-requirements/{requirement['id']}/applicability",
            headers=_auth(tokens["access_token"]),
        )
        _fly(client, tokens["access_token"], drone["id"], minutes=10, cycles=92)

        due = client.get(
            f"/api/v1/batteries/{battery['id']}/maintenance-due",
            headers=_auth(tokens["access_token"]),
        ).json()
        assert due[0]["due_status"] == "DUE_SOON"

        _fly(
            client, tokens["access_token"], drone["id"],
            minutes=10, cycles=10, flown_at="2030-01-02T10:00:00Z",
        )
        due2 = client.get(
            f"/api/v1/batteries/{battery['id']}/maintenance-due",
            headers=_auth(tokens["access_token"]),
        ).json()
        assert due2[0]["due_status"] == "OVERDUE"
        assert due2[0]["lifetime_usage"] == 102.0

    def test_lifetime_usage_never_reset_by_accomplishment(self, client):
        # The critical domain rule: lifetime usage != usage since last
        # maintenance. Accomplishing maintenance resets current_usage
        # (and therefore due_status) but never Battery.cycle_count.
        tokens = _register(client, "BCM Org 3", "bcm3@example.com")
        drone = _drone(client, tokens["access_token"])
        battery = _battery(client, tokens["access_token"], drone["id"])
        requirement = _requirement(
            client, tokens["access_token"], "BATTERY_CYCLES", fc_interval=100
        )
        client.post(
            f"/api/v1/batteries/{battery['id']}/maintenance-requirements/{requirement['id']}/applicability",
            headers=_auth(tokens["access_token"]),
        )
        _fly(client, tokens["access_token"], drone["id"], minutes=10, cycles=110)

        accomplish = client.post(
            f"/api/v1/batteries/{battery['id']}/maintenance-requirements/{requirement['id']}/accomplishments",
            headers=_auth(tokens["access_token"]),
            json={"accomplished_at": "2030-01-02"},
        )
        assert accomplish.status_code == 201

        due = client.get(
            f"/api/v1/batteries/{battery['id']}/maintenance-due",
            headers=_auth(tokens["access_token"]),
        ).json()
        assert due[0]["due_status"] == "NOT_DUE"
        assert due[0]["current_usage"] == 0.0
        # Lifetime usage (Battery.cycle_count) is untouched by the
        # accomplishment -- still the full 110 cycles ever flown.
        assert due[0]["lifetime_usage"] == 110.0

        battery_after = client.get(
            f"/api/v1/drones/{drone['id']}/batteries", headers=_auth(tokens["access_token"])
        ).json()[0]
        assert battery_after["cycle_count"] == 110


class TestComponentUsageEvaluation:
    def test_component_hours_not_due(self, client):
        tokens = _register(client, "BCM Org 4", "bcm4@example.com")
        drone = _drone(client, tokens["access_token"])
        component = _component(client, tokens["access_token"], drone["id"])
        requirement = _requirement(
            client, tokens["access_token"], "COMPONENT_HOURS", fh_interval=500
        )
        client.post(
            f"/api/v1/components/{component['id']}/maintenance-requirements/{requirement['id']}/applicability",
            headers=_auth(tokens["access_token"]),
        )
        _fly(client, tokens["access_token"], drone["id"], minutes=60 * 10)

        due = client.get(
            f"/api/v1/components/{component['id']}/maintenance-due",
            headers=_auth(tokens["access_token"]),
        ).json()
        assert due[0]["due_status"] == "NOT_DUE"
        assert due[0]["current_usage"] == 10.0
        assert due[0]["lifetime_usage"] == 10.0

    def test_component_cycles_overdue(self, client):
        tokens = _register(client, "BCM Org 5", "bcm5@example.com")
        drone = _drone(client, tokens["access_token"])
        component = _component(client, tokens["access_token"], drone["id"])
        requirement = _requirement(
            client, tokens["access_token"], "COMPONENT_CYCLES", fc_interval=250
        )
        client.post(
            f"/api/v1/components/{component['id']}/maintenance-requirements/{requirement['id']}/applicability",
            headers=_auth(tokens["access_token"]),
        )
        _fly(client, tokens["access_token"], drone["id"], minutes=30, cycles=260)

        due = client.get(
            f"/api/v1/components/{component['id']}/maintenance-due",
            headers=_auth(tokens["access_token"]),
        ).json()
        assert due[0]["due_status"] == "OVERDUE"


class TestInstallationAwareUsage:
    def test_battery_replacement_usage_does_not_transfer(self, client, db_session):
        from app.models.battery import Battery

        tokens = _register(client, "BCM Org 6", "bcm6@example.com")
        org_id = _org_id(client, tokens["access_token"])
        drone_a = _drone(client, tokens["access_token"], "DRN-BCM-A6")
        requirement = _requirement(
            client, tokens["access_token"], "BATTERY_CYCLES", fc_interval=100
        )
        asset_a_id = uuid.UUID(drone_a["id"])

        # Created directly (unattached inventory item, no asset_id yet) and
        # installed via installation_service -- matching M17.2A's own test
        # convention (test_installation_lifecycle.py) -- so both batteries
        # have real BatteryInstallation rows from the start, unlike the
        # POST /drones/{id}/batteries "attach" path used elsewhere in this
        # file, which sets asset_id directly with no installation row (the
        # attach-vs-install inconsistency the fallback window in
        # _installation_windows exists to cover for a never-removed item;
        # this test exercises the fully-tracked install/remove/reinstall
        # path instead).
        battery_a = Battery(organization_id=org_id, serial_number="BATT-BCM-A6")
        battery_b = Battery(organization_id=org_id, serial_number="BATT-BCM-B6")
        db_session.add(battery_a)
        db_session.add(battery_b)
        db_session.commit()
        battery_a_id, battery_b_id = battery_a.id, battery_b.id

        installation_service.install_battery(
            db_session,
            organization_id=org_id,
            actor_user_id=None,
            battery_id=battery_a_id,
            asset_id=asset_a_id,
        )

        client.post(
            f"/api/v1/batteries/{battery_a_id}/maintenance-requirements/{requirement['id']}/applicability",
            headers=_auth(tokens["access_token"]),
        )
        client.post(
            f"/api/v1/batteries/{battery_b_id}/maintenance-requirements/{requirement['id']}/applicability",
            headers=_auth(tokens["access_token"]),
        )

        # Battery A accumulates 60 cycles on Drone A, then is removed.
        _fly(client, tokens["access_token"], drone_a["id"], minutes=10, cycles=60)

        # Battery B (a completely different battery) is installed on
        # Drone A afterward -- its usage must start from zero, never
        # inheriting Battery A's 60 cycles.
        installation_service.remove_battery(
            db_session,
            organization_id=org_id,
            actor_user_id=None,
            battery_id=battery_a_id,
            asset_id=asset_a_id,
        )
        installation_service.install_battery(
            db_session,
            organization_id=org_id,
            actor_user_id=None,
            battery_id=battery_b_id,
            asset_id=asset_a_id,
        )

        _fly(
            client, tokens["access_token"], drone_a["id"],
            minutes=10, cycles=15, flown_at="2030-01-02T10:00:00Z",
        )

        due_a = client.get(
            f"/api/v1/batteries/{battery_a_id}/maintenance-due",
            headers=_auth(tokens["access_token"]),
        ).json()
        due_b = client.get(
            f"/api/v1/batteries/{battery_b_id}/maintenance-due",
            headers=_auth(tokens["access_token"]),
        ).json()
        # Battery A's usage stopped at 60 -- unaffected by post-removal flights.
        assert due_a[0]["lifetime_usage"] == 60.0
        # Battery B's usage is only the 15 cycles flown while it was
        # actually installed, never the pre-existing 60 from Battery A.
        assert due_b[0]["lifetime_usage"] == 15.0


class TestMaintenanceRBACAndTenantIsolation:
    def test_write_requires_drone_write_permission(self, client, db_session):
        tokens = _register(client, "BCM RBAC Org 1", "bcm-rbac-owner1@example.com")
        org_id = _org_id(client, tokens["access_token"])
        drone = _drone(client, tokens["access_token"], "DRN-BCM-RBAC-1")
        battery = _battery(client, tokens["access_token"], drone["id"])
        requirement = _requirement(
            client, tokens["access_token"], "BATTERY_CYCLES", fc_interval=100
        )
        viewer = _add_role_user(db_session, org_id, "bcm-rbac-viewer1@example.com", "VIEWER")
        viewer_tokens = _login(client, viewer.email)

        resp = client.post(
            f"/api/v1/batteries/{battery['id']}/maintenance-requirements/{requirement['id']}/applicability",
            headers=_auth(viewer_tokens["access_token"]),
        )
        assert resp.status_code == 403

    def test_viewer_can_read_battery_maintenance_due(self, client, db_session):
        tokens = _register(client, "BCM RBAC Org 2", "bcm-rbac-owner2@example.com")
        org_id = _org_id(client, tokens["access_token"])
        drone = _drone(client, tokens["access_token"], "DRN-BCM-RBAC-2")
        battery = _battery(client, tokens["access_token"], drone["id"])
        viewer = _add_role_user(db_session, org_id, "bcm-rbac-viewer2@example.com", "VIEWER")
        viewer_tokens = _login(client, viewer.email)

        resp = client.get(
            f"/api/v1/batteries/{battery['id']}/maintenance-due",
            headers=_auth(viewer_tokens["access_token"]),
        )
        assert resp.status_code == 200

    def test_cross_tenant_battery_applicability_rejected(self, client):
        org_a = _register(client, "BCM Iso Org A1", "bcm-iso-a1@example.com")
        org_b = _register(client, "BCM Iso Org B1", "bcm-iso-b1@example.com")
        drone_a = _drone(client, org_a["access_token"], "DRN-BCM-ISO-A1")
        battery_a = _battery(client, org_a["access_token"], drone_a["id"])
        requirement_b = _requirement(
            client, org_b["access_token"], "BATTERY_CYCLES", fc_interval=100
        )

        resp = client.post(
            f"/api/v1/batteries/{battery_a['id']}/maintenance-requirements/{requirement_b['id']}/applicability",
            headers=_auth(org_a["access_token"]),
        )
        assert resp.status_code == 404

    def test_cross_tenant_battery_maintenance_due_rejected(self, client):
        org_a = _register(client, "BCM Iso Org A2", "bcm-iso-a2@example.com")
        org_b = _register(client, "BCM Iso Org B2", "bcm-iso-b2@example.com")
        drone_a = _drone(client, org_a["access_token"], "DRN-BCM-ISO-A2")
        battery_a = _battery(client, org_a["access_token"], drone_a["id"])

        resp = client.get(
            f"/api/v1/batteries/{battery_a['id']}/maintenance-due",
            headers=_auth(org_b["access_token"]),
        )
        assert resp.status_code == 404

    def test_cross_tenant_component_maintenance_due_rejected(self, client):
        org_a = _register(client, "BCM Iso Org A3", "bcm-iso-a3@example.com")
        org_b = _register(client, "BCM Iso Org B3", "bcm-iso-b3@example.com")
        drone_a = _drone(client, org_a["access_token"], "DRN-BCM-ISO-A3")
        component_a = _component(client, org_a["access_token"], drone_a["id"])

        resp = client.get(
            f"/api/v1/components/{component_a['id']}/maintenance-due",
            headers=_auth(org_b["access_token"]),
        )
        assert resp.status_code == 404


class TestValidation:
    def test_no_applicable_requirements_returns_empty_list(self, client):
        tokens = _register(client, "BCM Val Org 1", "bcm-val1@example.com")
        drone = _drone(client, tokens["access_token"])
        battery = _battery(client, tokens["access_token"], drone["id"])

        resp = client.get(
            f"/api/v1/batteries/{battery['id']}/maintenance-due",
            headers=_auth(tokens["access_token"]),
        )
        assert resp.status_code == 200
        assert resp.json() == []

    def test_missing_battery_returns_404(self, client):
        tokens = _register(client, "BCM Val Org 2", "bcm-val2@example.com")
        resp = client.get(
            f"/api/v1/batteries/{uuid.uuid4()}/maintenance-due",
            headers=_auth(tokens["access_token"]),
        )
        assert resp.status_code == 404
