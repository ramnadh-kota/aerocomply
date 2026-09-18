"""M17.2B: battery/component lifecycle read APIs (current state, per-item
history, asset-scoped unified timeline). Install/remove operations
themselves are exercised directly against installation_service (as in
test_installation_lifecycle.py, M17.2A) -- this file is only for the new
read API surface added on top: GET /batteries/{id}, GET
/batteries/{id}/history, GET /components/{id}, GET
/components/{id}/history, GET /drones/{asset_id}/lifecycle-history.
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


def _drone(client, token, registration="DRN-API-001"):
    resp = client.post(
        "/api/v1/drones",
        headers=_auth(token),
        json={"registration": registration, "manufacturer": "DJI", "model": "M300"},
    )
    assert resp.status_code == 201
    return resp.json()


def _battery(client, token, drone_id, serial="BATT-API-1"):
    resp = client.post(
        f"/api/v1/drones/{drone_id}/batteries",
        headers=_auth(token),
        json={"serial_number": serial},
    )
    assert resp.status_code == 201
    return resp.json()


def _component(client, token, drone_id, serial="COMP-API-1"):
    resp = client.post(
        f"/api/v1/drones/{drone_id}/components",
        headers=_auth(token),
        json={"component_type": "GPS", "name": "GPS", "serial_number": serial},
    )
    assert resp.status_code == 201
    return resp.json()


class TestBatteryLifecycleAPI:
    def test_get_battery_current_state(self, client):
        tokens = _register(client, "API Org 1", "api-admin1@example.com")
        drone = _drone(client, tokens["access_token"], "DRN-API-A1")
        battery = _battery(client, tokens["access_token"], drone["id"])

        resp = client.get(
            f"/api/v1/batteries/{battery['id']}", headers=_auth(tokens["access_token"])
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["id"] == battery["id"]
        assert body["asset_id"] == drone["id"]

    def test_battery_history_empty_before_install(self, client):
        tokens = _register(client, "API Org 2", "api-admin2@example.com")
        drone = _drone(client, tokens["access_token"], "DRN-API-A2")
        battery = _battery(client, tokens["access_token"], drone["id"])

        resp = client.get(
            f"/api/v1/batteries/{battery['id']}/history", headers=_auth(tokens["access_token"])
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["items"] == []
        assert body["total"] == 0
        assert body["limit"] > 0
        assert body["offset"] == 0

    def test_battery_history_install_remove_reinstall_ordering(self, client, db_session):
        tokens = _register(client, "API Org 3", "api-admin3@example.com")
        org_id = _org_id(client, tokens["access_token"])
        drone_a = _drone(client, tokens["access_token"], "DRN-API-A3")
        drone_b = _drone(client, tokens["access_token"], "DRN-API-B3")
        battery = _battery(client, tokens["access_token"], drone_a["id"])
        battery_id = uuid.UUID(battery["id"])
        asset_a = uuid.UUID(drone_a["id"])
        asset_b = uuid.UUID(drone_b["id"])

        installation_service.install_battery(
            db_session, organization_id=org_id, actor_user_id=None,
            battery_id=battery_id, asset_id=asset_a,
        )
        installation_service.remove_battery(
            db_session, organization_id=org_id, actor_user_id=None,
            battery_id=battery_id, asset_id=asset_a,
        )
        installation_service.install_battery(
            db_session, organization_id=org_id, actor_user_id=None,
            battery_id=battery_id, asset_id=asset_b,
        )

        resp = client.get(
            f"/api/v1/batteries/{battery_id}/history", headers=_auth(tokens["access_token"])
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 2
        items = body["items"]
        assert len(items) == 2
        # Newest (open) installation first.
        assert items[0]["asset_id"] == str(asset_b)
        assert items[0]["removed_at"] is None
        assert items[0]["installed_at"] is not None
        assert items[1]["asset_id"] == str(asset_a)
        assert items[1]["removed_at"] is not None


class TestComponentLifecycleAPI:
    def test_get_component_current_state(self, client):
        tokens = _register(client, "API Org 4", "api-admin4@example.com")
        drone = _drone(client, tokens["access_token"], "DRN-API-A4")
        component = _component(client, tokens["access_token"], drone["id"])

        resp = client.get(
            f"/api/v1/components/{component['id']}", headers=_auth(tokens["access_token"])
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["id"] == component["id"]
        assert body["asset_id"] == drone["id"]

    def test_component_history_empty_before_install(self, client):
        tokens = _register(client, "API Org 5", "api-admin5@example.com")
        drone = _drone(client, tokens["access_token"], "DRN-API-A5")
        component = _component(client, tokens["access_token"], drone["id"])

        resp = client.get(
            f"/api/v1/components/{component['id']}/history", headers=_auth(tokens["access_token"])
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["items"] == []
        assert body["total"] == 0

    def test_component_history_install_remove_reinstall_ordering(self, client, db_session):
        tokens = _register(client, "API Org 6", "api-admin6@example.com")
        org_id = _org_id(client, tokens["access_token"])
        drone_a = _drone(client, tokens["access_token"], "DRN-API-A6")
        drone_b = _drone(client, tokens["access_token"], "DRN-API-B6")
        component = _component(client, tokens["access_token"], drone_a["id"])
        component_id = uuid.UUID(component["id"])
        asset_a = uuid.UUID(drone_a["id"])
        asset_b = uuid.UUID(drone_b["id"])

        installation_service.install_component(
            db_session, organization_id=org_id, actor_user_id=None,
            component_id=component_id, asset_id=asset_a,
        )
        installation_service.remove_component(
            db_session, organization_id=org_id, actor_user_id=None,
            component_id=component_id, asset_id=asset_a,
        )
        installation_service.install_component(
            db_session, organization_id=org_id, actor_user_id=None,
            component_id=component_id, asset_id=asset_b,
        )

        resp = client.get(
            f"/api/v1/components/{component_id}/history", headers=_auth(tokens["access_token"])
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 2
        items = body["items"]
        assert items[0]["asset_id"] == str(asset_b)
        assert items[0]["removed_at"] is None
        assert items[1]["asset_id"] == str(asset_a)
        assert items[1]["removed_at"] is not None


class TestAssetLifecycleAPI:
    def test_asset_lifecycle_empty(self, client):
        tokens = _register(client, "API Org 7", "api-admin7@example.com")
        drone = _drone(client, tokens["access_token"], "DRN-API-A7")

        resp = client.get(
            f"/api/v1/drones/{drone['id']}/lifecycle-history", headers=_auth(tokens["access_token"])
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["items"] == []
        assert body["total"] == 0

    def test_asset_lifecycle_combines_battery_and_component_events(self, client, db_session):
        tokens = _register(client, "API Org 8", "api-admin8@example.com")
        org_id = _org_id(client, tokens["access_token"])
        drone = _drone(client, tokens["access_token"], "DRN-API-A8")
        asset_id = uuid.UUID(drone["id"])
        battery = _battery(client, tokens["access_token"], drone["id"])
        component = _component(client, tokens["access_token"], drone["id"])
        battery_id = uuid.UUID(battery["id"])
        component_id = uuid.UUID(component["id"])

        installation_service.install_battery(
            db_session, organization_id=org_id, actor_user_id=None,
            battery_id=battery_id, asset_id=asset_id,
        )
        installation_service.remove_battery(
            db_session, organization_id=org_id, actor_user_id=None,
            battery_id=battery_id, asset_id=asset_id,
        )
        installation_service.install_component(
            db_session, organization_id=org_id, actor_user_id=None,
            component_id=component_id, asset_id=asset_id,
        )

        resp = client.get(
            f"/api/v1/drones/{asset_id}/lifecycle-history", headers=_auth(tokens["access_token"])
        )
        assert resp.status_code == 200
        body = resp.json()
        # BATTERY_INSTALLATION + BATTERY_REMOVAL + COMPONENT_INSTALLATION
        assert body["total"] == 3
        event_types = [e["event_type"] for e in body["items"]]
        assert event_types.count("BATTERY_INSTALLATION") == 1
        assert event_types.count("BATTERY_REMOVAL") == 1
        assert event_types.count("COMPONENT_INSTALLATION") == 1
        # Newest first: the component install (last action) leads.
        assert event_types[0] == "COMPONENT_INSTALLATION"
        # Ordering is non-increasing by occurred_at across the whole page.
        occurred = [e["occurred_at"] for e in body["items"]]
        assert occurred == sorted(occurred, reverse=True)
        for event in body["items"]:
            assert event["asset_id"] == str(asset_id)
            if event["event_type"].startswith("BATTERY"):
                assert event["battery_id"] == str(battery_id)
                assert event["component_id"] is None
            else:
                assert event["component_id"] == str(component_id)
                assert event["battery_id"] is None


class TestLifecycleTenantIsolation:
    def test_cross_tenant_battery_get_returns_404(self, client):
        org_a = _register(client, "API Iso Org A1", "api-iso-a1@example.com")
        org_b = _register(client, "API Iso Org B1", "api-iso-b1@example.com")
        drone = _drone(client, org_a["access_token"], "DRN-API-ISO-A1")
        battery = _battery(client, org_a["access_token"], drone["id"])

        resp = client.get(
            f"/api/v1/batteries/{battery['id']}", headers=_auth(org_b["access_token"])
        )
        assert resp.status_code == 404

    def test_cross_tenant_battery_history_returns_404(self, client):
        org_a = _register(client, "API Iso Org A2", "api-iso-a2@example.com")
        org_b = _register(client, "API Iso Org B2", "api-iso-b2@example.com")
        drone = _drone(client, org_a["access_token"], "DRN-API-ISO-A2")
        battery = _battery(client, org_a["access_token"], drone["id"])

        resp = client.get(
            f"/api/v1/batteries/{battery['id']}/history", headers=_auth(org_b["access_token"])
        )
        assert resp.status_code == 404

    def test_cross_tenant_component_get_and_history_404(self, client):
        org_a = _register(client, "API Iso Org A3", "api-iso-a3@example.com")
        org_b = _register(client, "API Iso Org B3", "api-iso-b3@example.com")
        drone = _drone(client, org_a["access_token"], "DRN-API-ISO-A3")
        component = _component(client, org_a["access_token"], drone["id"])

        resp1 = client.get(
            f"/api/v1/components/{component['id']}", headers=_auth(org_b["access_token"])
        )
        assert resp1.status_code == 404
        resp2 = client.get(
            f"/api/v1/components/{component['id']}/history", headers=_auth(org_b["access_token"])
        )
        assert resp2.status_code == 404

    def test_cross_tenant_asset_lifecycle_history_returns_404(self, client):
        org_a = _register(client, "API Iso Org A4", "api-iso-a4@example.com")
        org_b = _register(client, "API Iso Org B4", "api-iso-b4@example.com")
        drone = _drone(client, org_a["access_token"], "DRN-API-ISO-A4")

        resp = client.get(
            f"/api/v1/drones/{drone['id']}/lifecycle-history", headers=_auth(org_b["access_token"])
        )
        assert resp.status_code == 404

    def test_no_cross_tenant_data_leaks_into_own_org_response(self, client, db_session):
        # Two orgs, each with their own drone+battery lifecycle; confirm
        # org A's asset lifecycle response contains only its own events.
        org_a = _register(client, "API Iso Org A5", "api-iso-a5@example.com")
        org_b = _register(client, "API Iso Org B5", "api-iso-b5@example.com")
        org_a_id = _org_id(client, org_a["access_token"])
        org_b_id = _org_id(client, org_b["access_token"])

        drone_a = _drone(client, org_a["access_token"], "DRN-API-ISO-A5")
        drone_b = _drone(client, org_b["access_token"], "DRN-API-ISO-B5")
        battery_a = _battery(client, org_a["access_token"], drone_a["id"], "BATT-ISO-A5")
        battery_b = _battery(client, org_b["access_token"], drone_b["id"], "BATT-ISO-B5")

        installation_service.install_battery(
            db_session, organization_id=org_a_id, actor_user_id=None,
            battery_id=uuid.UUID(battery_a["id"]), asset_id=uuid.UUID(drone_a["id"]),
        )
        installation_service.install_battery(
            db_session, organization_id=org_b_id, actor_user_id=None,
            battery_id=uuid.UUID(battery_b["id"]), asset_id=uuid.UUID(drone_b["id"]),
        )

        resp = client.get(
            f"/api/v1/drones/{drone_a['id']}/lifecycle-history",
            headers=_auth(org_a["access_token"]),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 1
        assert body["items"][0]["battery_id"] == battery_a["id"]


class TestLifecycleRBAC:
    def test_viewer_can_read_lifecycle(self, client, db_session):
        tokens = _register(client, "API RBAC Org 1", "api-rbac-owner1@example.com")
        org_id = _org_id(client, tokens["access_token"])
        drone = _drone(client, tokens["access_token"], "DRN-API-RBAC-1")
        battery = _battery(client, tokens["access_token"], drone["id"])
        viewer = _add_role_user(db_session, org_id, "api-rbac-viewer1@example.com", "VIEWER")
        viewer_tokens = _login(client, viewer.email)

        assert (
            client.get(
                f"/api/v1/batteries/{battery['id']}", headers=_auth(viewer_tokens["access_token"])
            ).status_code
            == 200
        )
        assert (
            client.get(
                f"/api/v1/drones/{drone['id']}/lifecycle-history",
                headers=_auth(viewer_tokens["access_token"]),
            ).status_code
            == 200
        )

    def test_unauthorized_role_cannot_read_lifecycle(self, client, db_session):
        tokens = _register(client, "API RBAC Org 2", "api-rbac-owner2@example.com")
        org_id = _org_id(client, tokens["access_token"])
        drone = _drone(client, tokens["access_token"], "DRN-API-RBAC-2")
        battery = _battery(client, tokens["access_token"], drone["id"])
        # PLATFORM_STAFF is deliberately minimal (see app/core/permissions.py)
        # and does not include DRONE_READ.
        staff = _add_role_user(db_session, org_id, "api-rbac-staff2@example.com", "PLATFORM_STAFF")
        staff_tokens = _login(client, staff.email)

        resp = client.get(
            f"/api/v1/batteries/{battery['id']}", headers=_auth(staff_tokens["access_token"])
        )
        assert resp.status_code == 403


class TestSourceOfTruthUnchangedByReads:
    def test_get_apis_do_not_mutate_state(self, client, db_session):
        from app.models.battery import Battery

        tokens = _register(client, "API SoT Org 1", "api-sot1@example.com")
        org_id = _org_id(client, tokens["access_token"])
        drone = _drone(client, tokens["access_token"], "DRN-API-SOT-1")
        battery = _battery(client, tokens["access_token"], drone["id"])
        battery_id = uuid.UUID(battery["id"])
        asset_id = uuid.UUID(drone["id"])

        installation_service.install_battery(
            db_session, organization_id=org_id, actor_user_id=None,
            battery_id=battery_id, asset_id=asset_id,
        )

        for _ in range(3):
            client.get(
                f"/api/v1/batteries/{battery_id}/history", headers=_auth(tokens["access_token"])
            )
            client.get(
                f"/api/v1/drones/{asset_id}/lifecycle-history", headers=_auth(tokens["access_token"])
            )

        db_battery = db_session.get(Battery, battery_id)
        assert db_battery.asset_id == asset_id

        history, total = installation_service.list_battery_history(
            db_session, organization_id=org_id, battery_id=battery_id
        )
        # Repeated GETs must not create additional installation rows.
        assert total == 1
        assert len(history) == 1


class TestLifecycleValidation:
    def test_invalid_uuid_returns_422(self, client):
        tokens = _register(client, "API Val Org 1", "api-val1@example.com")
        resp = client.get(
            "/api/v1/batteries/not-a-uuid", headers=_auth(tokens["access_token"])
        )
        assert resp.status_code == 422

    def test_missing_battery_returns_404(self, client):
        tokens = _register(client, "API Val Org 2", "api-val2@example.com")
        resp = client.get(
            f"/api/v1/batteries/{uuid.uuid4()}", headers=_auth(tokens["access_token"])
        )
        assert resp.status_code == 404

    def test_missing_component_returns_404(self, client):
        tokens = _register(client, "API Val Org 3", "api-val3@example.com")
        resp = client.get(
            f"/api/v1/components/{uuid.uuid4()}", headers=_auth(tokens["access_token"])
        )
        assert resp.status_code == 404

    def test_missing_asset_lifecycle_returns_404(self, client):
        tokens = _register(client, "API Val Org 4", "api-val4@example.com")
        resp = client.get(
            f"/api/v1/drones/{uuid.uuid4()}/lifecycle-history", headers=_auth(tokens["access_token"])
        )
        assert resp.status_code == 404

    def test_pagination_limit_is_clamped_and_offset_applies(self, client, db_session):
        tokens = _register(client, "API Val Org 5", "api-val5@example.com")
        org_id = _org_id(client, tokens["access_token"])
        drones = [
            _drone(client, tokens["access_token"], f"DRN-API-VAL-{i}") for i in range(3)
        ]
        battery = _battery(client, tokens["access_token"], drones[0]["id"], "BATT-VAL-1")
        battery_id = uuid.UUID(battery["id"])

        # Three install/remove spans across three assets, so battery
        # history has three rows to paginate over.
        for i, drone in enumerate(drones):
            asset_id = uuid.UUID(drone["id"])
            installation_service.install_battery(
                db_session, organization_id=org_id, actor_user_id=None,
                battery_id=battery_id, asset_id=asset_id,
            )
            if i < len(drones) - 1:
                installation_service.remove_battery(
                    db_session, organization_id=org_id, actor_user_id=None,
                    battery_id=battery_id, asset_id=asset_id,
                )

        resp = client.get(
            f"/api/v1/batteries/{battery_id}/history?limit=1&offset=1",
            headers=_auth(tokens["access_token"]),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 3
        assert body["limit"] == 1
        assert body["offset"] == 1
        assert len(body["items"]) == 1

        # A limit above the server-side max is clamped, never honored as-is.
        resp2 = client.get(
            f"/api/v1/batteries/{battery_id}/history?limit=99999",
            headers=_auth(tokens["access_token"]),
        )
        assert resp2.status_code == 200
        assert resp2.json()["limit"] == installation_service.LIFECYCLE_HISTORY_MAX_LIMIT
