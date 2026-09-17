"""M17.2A: Serialized Battery & Component installation history.

Tests the service layer directly (installation_service) since this
milestone deliberately has no REST API yet -- routes are deferred to
M17.2B. Organizations/drones/batteries/components are created through the
real API (matching test_drone_operations.py's convention) so tenant setup
stays realistic; the install/remove/history calls under test go straight
to the service functions with an explicit db_session.
"""

import uuid

import pytest
from sqlalchemy import select

from app.core.errors import ConflictError, NotFoundError
from app.models.audit_event import AuditEvent
from app.models.battery import Battery
from app.models.component import Component
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


def _org_id(client, token):
    return uuid.UUID(client.get("/api/v1/auth/me", headers=_auth(token)).json()["organization_id"])


def _drone(client, token, registration="DRN-LC-001"):
    resp = client.post(
        "/api/v1/drones",
        headers=_auth(token),
        json={"registration": registration, "manufacturer": "DJI", "model": "M300"},
    )
    assert resp.status_code == 201
    return resp.json()


def _battery(client, token, drone_id, serial="BATT-LC-1"):
    resp = client.post(
        f"/api/v1/drones/{drone_id}/batteries",
        headers=_auth(token),
        json={"serial_number": serial},
    )
    assert resp.status_code == 201
    return resp.json()


def _component(client, token, drone_id, serial="COMP-LC-1"):
    resp = client.post(
        f"/api/v1/drones/{drone_id}/components",
        headers=_auth(token),
        json={"component_type": "GPS", "name": "GPS", "serial_number": serial},
    )
    assert resp.status_code == 201
    return resp.json()


class TestBatteryLifecycle:
    def test_install_remove_reinstall_preserves_history(self, client, db_session):
        tokens = _register(client, "Lifecycle Org 1", "lc-admin1@example.com")
        org_id = _org_id(client, tokens["access_token"])
        drone_a = _drone(client, tokens["access_token"], "DRN-LC-A1")
        drone_b = _drone(client, tokens["access_token"], "DRN-LC-B1")
        battery = _battery(client, tokens["access_token"], drone_a["id"])
        battery_id = uuid.UUID(battery["id"])
        asset_a = uuid.UUID(drone_a["id"])
        asset_b = uuid.UUID(drone_b["id"])

        installation_service.install_battery(
            db_session,
            organization_id=org_id,
            actor_user_id=None,
            battery_id=battery_id,
            asset_id=asset_a,
        )
        installation_service.remove_battery(
            db_session,
            organization_id=org_id,
            actor_user_id=None,
            battery_id=battery_id,
            asset_id=asset_a,
        )
        installation_service.install_battery(
            db_session,
            organization_id=org_id,
            actor_user_id=None,
            battery_id=battery_id,
            asset_id=asset_b,
        )

        db_battery = db_session.get(Battery, battery_id)
        assert db_battery.asset_id == asset_b

        history = installation_service.list_battery_history(
            db_session, organization_id=org_id, battery_id=battery_id
        )
        assert len(history) == 2
        assert history[0].asset_id == asset_b
        assert history[0].removed_at is None
        assert history[1].asset_id == asset_a
        assert history[1].removed_at is not None

    def test_duplicate_active_installation_rejected(self, client, db_session):
        tokens = _register(client, "Lifecycle Org 2", "lc-admin2@example.com")
        org_id = _org_id(client, tokens["access_token"])
        drone = _drone(client, tokens["access_token"], "DRN-LC-A2")
        battery = _battery(client, tokens["access_token"], drone["id"])
        battery_id = uuid.UUID(battery["id"])
        asset_id = uuid.UUID(drone["id"])

        installation_service.install_battery(
            db_session,
            organization_id=org_id,
            actor_user_id=None,
            battery_id=battery_id,
            asset_id=asset_id,
        )
        with pytest.raises(ConflictError):
            installation_service.install_battery(
                db_session,
                organization_id=org_id,
                actor_user_id=None,
                battery_id=battery_id,
                asset_id=asset_id,
            )

    def test_wrong_asset_removal_rejected(self, client, db_session):
        tokens = _register(client, "Lifecycle Org 3", "lc-admin3@example.com")
        org_id = _org_id(client, tokens["access_token"])
        drone_a = _drone(client, tokens["access_token"], "DRN-LC-A3")
        drone_b = _drone(client, tokens["access_token"], "DRN-LC-B3")
        battery = _battery(client, tokens["access_token"], drone_a["id"])
        battery_id = uuid.UUID(battery["id"])
        asset_a = uuid.UUID(drone_a["id"])
        asset_b = uuid.UUID(drone_b["id"])

        installation_service.install_battery(
            db_session,
            organization_id=org_id,
            actor_user_id=None,
            battery_id=battery_id,
            asset_id=asset_a,
        )
        with pytest.raises(ConflictError):
            installation_service.remove_battery(
                db_session,
                organization_id=org_id,
                actor_user_id=None,
                battery_id=battery_id,
                asset_id=asset_b,
            )


class TestComponentLifecycle:
    def test_install_remove_reinstall_preserves_history(self, client, db_session):
        tokens = _register(client, "Lifecycle Org 4", "lc-admin4@example.com")
        org_id = _org_id(client, tokens["access_token"])
        drone_a = _drone(client, tokens["access_token"], "DRN-LC-A4")
        drone_b = _drone(client, tokens["access_token"], "DRN-LC-B4")
        component = _component(client, tokens["access_token"], drone_a["id"])
        component_id = uuid.UUID(component["id"])
        asset_a = uuid.UUID(drone_a["id"])
        asset_b = uuid.UUID(drone_b["id"])

        installation_service.install_component(
            db_session,
            organization_id=org_id,
            actor_user_id=None,
            component_id=component_id,
            asset_id=asset_a,
        )
        installation_service.remove_component(
            db_session,
            organization_id=org_id,
            actor_user_id=None,
            component_id=component_id,
            asset_id=asset_a,
        )
        installation_service.install_component(
            db_session,
            organization_id=org_id,
            actor_user_id=None,
            component_id=component_id,
            asset_id=asset_b,
        )

        db_component = db_session.get(Component, component_id)
        assert db_component.asset_id == asset_b
        assert db_component.status == "INSTALLED"

        history = installation_service.list_component_history(
            db_session, organization_id=org_id, component_id=component_id
        )
        assert len(history) == 2
        assert history[0].removed_at is None
        assert history[1].removed_at is not None

    def test_duplicate_active_installation_rejected(self, client, db_session):
        tokens = _register(client, "Lifecycle Org 5", "lc-admin5@example.com")
        org_id = _org_id(client, tokens["access_token"])
        drone = _drone(client, tokens["access_token"], "DRN-LC-A5")
        component = _component(client, tokens["access_token"], drone["id"])
        component_id = uuid.UUID(component["id"])
        asset_id = uuid.UUID(drone["id"])

        installation_service.install_component(
            db_session,
            organization_id=org_id,
            actor_user_id=None,
            component_id=component_id,
            asset_id=asset_id,
        )
        with pytest.raises(ConflictError):
            installation_service.install_component(
                db_session,
                organization_id=org_id,
                actor_user_id=None,
                component_id=component_id,
                asset_id=asset_id,
            )

    def test_wrong_asset_removal_rejected(self, client, db_session):
        tokens = _register(client, "Lifecycle Org 6", "lc-admin6@example.com")
        org_id = _org_id(client, tokens["access_token"])
        drone_a = _drone(client, tokens["access_token"], "DRN-LC-A6")
        drone_b = _drone(client, tokens["access_token"], "DRN-LC-B6")
        component = _component(client, tokens["access_token"], drone_a["id"])
        component_id = uuid.UUID(component["id"])
        asset_a = uuid.UUID(drone_a["id"])
        asset_b = uuid.UUID(drone_b["id"])

        installation_service.install_component(
            db_session,
            organization_id=org_id,
            actor_user_id=None,
            component_id=component_id,
            asset_id=asset_a,
        )
        with pytest.raises(ConflictError):
            installation_service.remove_component(
                db_session,
                organization_id=org_id,
                actor_user_id=None,
                component_id=component_id,
                asset_id=asset_b,
            )


class TestCrossTenantSecurity:
    def test_cross_tenant_installation_rejected(self, client, db_session):
        org_a = _register(client, "Lifecycle Iso Org A", "lc-iso-a@example.com")
        org_b = _register(client, "Lifecycle Iso Org B", "lc-iso-b@example.com")
        org_b_id = _org_id(client, org_b["access_token"])

        drone_a = _drone(client, org_a["access_token"], "DRN-LC-ISO-A")
        battery_a = _battery(client, org_a["access_token"], drone_a["id"])

        with pytest.raises(NotFoundError):
            installation_service.install_battery(
                db_session,
                organization_id=org_b_id,
                actor_user_id=None,
                battery_id=uuid.UUID(battery_a["id"]),
                asset_id=uuid.UUID(drone_a["id"]),
            )

    def test_cross_tenant_removal_rejected(self, client, db_session):
        org_a = _register(client, "Lifecycle Iso Org C", "lc-iso-c@example.com")
        org_b = _register(client, "Lifecycle Iso Org D", "lc-iso-d@example.com")
        org_a_id = _org_id(client, org_a["access_token"])
        org_b_id = _org_id(client, org_b["access_token"])

        drone_a = _drone(client, org_a["access_token"], "DRN-LC-ISO-C")
        battery_a = _battery(client, org_a["access_token"], drone_a["id"])
        battery_id = uuid.UUID(battery_a["id"])
        asset_id = uuid.UUID(drone_a["id"])

        installation_service.install_battery(
            db_session,
            organization_id=org_a_id,
            actor_user_id=None,
            battery_id=battery_id,
            asset_id=asset_id,
        )

        with pytest.raises(NotFoundError):
            installation_service.remove_battery(
                db_session,
                organization_id=org_b_id,
                actor_user_id=None,
                battery_id=battery_id,
                asset_id=asset_id,
            )

    def test_cross_tenant_history_access_rejected(self, client, db_session):
        org_a = _register(client, "Lifecycle Iso Org E", "lc-iso-e@example.com")
        org_b = _register(client, "Lifecycle Iso Org F", "lc-iso-f@example.com")
        org_a_id = _org_id(client, org_a["access_token"])
        org_b_id = _org_id(client, org_b["access_token"])

        drone_a = _drone(client, org_a["access_token"], "DRN-LC-ISO-E")
        battery_a = _battery(client, org_a["access_token"], drone_a["id"])
        battery_id = uuid.UUID(battery_a["id"])
        asset_id = uuid.UUID(drone_a["id"])

        installation_service.install_battery(
            db_session,
            organization_id=org_a_id,
            actor_user_id=None,
            battery_id=battery_id,
            asset_id=asset_id,
        )

        history = installation_service.list_battery_history(
            db_session, organization_id=org_b_id, battery_id=battery_id
        )
        assert history == []


class TestTransactionIntegrity:
    def test_install_records_audit_event_atomically(self, client, db_session):
        tokens = _register(client, "Lifecycle Org 7", "lc-admin7@example.com")
        org_id = _org_id(client, tokens["access_token"])
        drone = _drone(client, tokens["access_token"], "DRN-LC-A7")
        battery = _battery(client, tokens["access_token"], drone["id"])
        battery_id = uuid.UUID(battery["id"])
        asset_id = uuid.UUID(drone["id"])

        installation_service.install_battery(
            db_session,
            organization_id=org_id,
            actor_user_id=None,
            battery_id=battery_id,
            asset_id=asset_id,
        )

        actions = (
            db_session.execute(
                select(AuditEvent.action).where(AuditEvent.entity_id == battery_id)
            )
            .scalars()
            .all()
        )
        assert "battery.installed" in actions

        history = installation_service.list_battery_history(
            db_session, organization_id=org_id, battery_id=battery_id
        )
        db_battery = db_session.get(Battery, battery_id)
        assert len(history) == 1
        assert db_battery.asset_id == asset_id

    def test_failed_duplicate_install_leaves_state_unchanged(self, client, db_session):
        tokens = _register(client, "Lifecycle Org 8", "lc-admin8@example.com")
        org_id = _org_id(client, tokens["access_token"])
        drone = _drone(client, tokens["access_token"], "DRN-LC-A8")
        battery = _battery(client, tokens["access_token"], drone["id"])
        battery_id = uuid.UUID(battery["id"])
        asset_id = uuid.UUID(drone["id"])

        installation_service.install_battery(
            db_session,
            organization_id=org_id,
            actor_user_id=None,
            battery_id=battery_id,
            asset_id=asset_id,
        )
        with pytest.raises(ConflictError):
            installation_service.install_battery(
                db_session,
                organization_id=org_id,
                actor_user_id=None,
                battery_id=battery_id,
                asset_id=asset_id,
            )

        history = installation_service.list_battery_history(
            db_session, organization_id=org_id, battery_id=battery_id
        )
        assert len(history) == 1
