"""M17.3B: Flight APIs + History + Usage Integration.

Extends the pre-existing Flight foundation (Phase 18.6 / commit 0ca5df6,
app/models/flight.py + app/services/flight_service.py) rather than
rebuilding it. Covers the genuine gaps identified by inspection:
- GET /drones/{asset_id}/flights was unbounded (`list[FlightResponse]`) --
  now paginated with the same {items, total, limit, offset} envelope as
  every other lifecycle-history endpoint in this codebase.
- No deterministic secondary sort existed for flights sharing the same
  flown_at timestamp.
- No single-flight GET existed (battery/component already have one).
- Cross-tenant battery-cycle-isolation and flight-RBAC boundaries were
  exercised only indirectly by existing tests -- made explicit here.
"""

import uuid

from app.core.deps import get_db_session
from app.main import app
from app.services import flight_service


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


def _drone(client, token, registration="DRN-FLT-001"):
    resp = client.post(
        "/api/v1/drones",
        headers=_auth(token),
        json={"registration": registration, "manufacturer": "DJI", "model": "M300"},
    )
    assert resp.status_code == 201
    return resp.json()


def _record_flight(client, token, drone_id, minutes=10, cycles=1, flown_at="2026-01-01T10:00:00Z"):
    resp = client.post(
        f"/api/v1/drones/{drone_id}/flights",
        headers=_auth(token),
        json={"flown_at": flown_at, "duration_minutes": minutes, "cycles": cycles},
    )
    assert resp.status_code == 201
    return resp.json()


class TestFlightHistoryPagination:
    def test_flight_history_is_paginated_and_bounded(self, client):
        tokens = _register(client, "Flight API Org 1", "flight-api-1@example.com")
        drone = _drone(client, tokens["access_token"])
        for i in range(3):
            _record_flight(
                client,
                tokens["access_token"],
                drone["id"],
                minutes=10 + i,
                flown_at=f"2026-01-0{i + 1}T10:00:00Z",
            )

        resp = client.get(
            f"/api/v1/drones/{drone['id']}/flights?limit=2&offset=1",
            headers=_auth(tokens["access_token"]),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 3
        assert body["limit"] == 2
        assert body["offset"] == 1
        assert len(body["items"]) == 2

    def test_flight_history_offset_beyond_total_returns_empty_page(self, client):
        tokens = _register(client, "Flight API Org 1b", "flight-api-1b@example.com")
        drone = _drone(client, tokens["access_token"])
        _record_flight(client, tokens["access_token"], drone["id"])

        resp = client.get(
            f"/api/v1/drones/{drone['id']}/flights?offset=500",
            headers=_auth(tokens["access_token"]),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 1
        assert body["items"] == []

    def test_flight_history_limit_is_clamped_to_max(self, client):
        tokens = _register(client, "Flight API Org 2", "flight-api-2@example.com")
        drone = _drone(client, tokens["access_token"])
        _record_flight(client, tokens["access_token"], drone["id"])

        resp = client.get(
            f"/api/v1/drones/{drone['id']}/flights?limit=99999",
            headers=_auth(tokens["access_token"]),
        )
        assert resp.status_code == 200
        assert resp.json()["limit"] == flight_service.FLIGHT_HISTORY_MAX_LIMIT

    def test_flight_history_ordering_is_deterministic_newest_first(self, client):
        tokens = _register(client, "Flight API Org 3", "flight-api-3@example.com")
        drone = _drone(client, tokens["access_token"])
        _record_flight(client, tokens["access_token"], drone["id"], flown_at="2026-01-01T10:00:00Z")
        _record_flight(client, tokens["access_token"], drone["id"], flown_at="2026-01-03T10:00:00Z")
        _record_flight(client, tokens["access_token"], drone["id"], flown_at="2026-01-02T10:00:00Z")

        resp = client.get(
            f"/api/v1/drones/{drone['id']}/flights", headers=_auth(tokens["access_token"])
        )
        body = resp.json()
        flown_ats = [item["flown_at"] for item in body["items"]]
        assert flown_ats == sorted(flown_ats, reverse=True)

    def test_empty_flight_history(self, client):
        tokens = _register(client, "Flight API Org 4", "flight-api-4@example.com")
        drone = _drone(client, tokens["access_token"])

        resp = client.get(
            f"/api/v1/drones/{drone['id']}/flights", headers=_auth(tokens["access_token"])
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["items"] == []
        assert body["total"] == 0


class TestFlightDetail:
    def test_get_flight_by_id(self, client):
        tokens = _register(client, "Flight API Org 5", "flight-api-5@example.com")
        drone = _drone(client, tokens["access_token"])
        flight = _record_flight(client, tokens["access_token"], drone["id"], minutes=42)

        resp = client.get(
            f"/api/v1/flights/{flight['id']}", headers=_auth(tokens["access_token"])
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["id"] == flight["id"]
        assert body["duration_minutes"] == 42

    def test_get_nonexistent_flight_returns_404(self, client):
        tokens = _register(client, "Flight API Org 6", "flight-api-6@example.com")
        resp = client.get(
            f"/api/v1/flights/{uuid.uuid4()}", headers=_auth(tokens["access_token"])
        )
        assert resp.status_code == 404

    def test_get_flight_invalid_uuid_returns_422(self, client):
        tokens = _register(client, "Flight API Org 7", "flight-api-7@example.com")
        resp = client.get("/api/v1/flights/not-a-uuid", headers=_auth(tokens["access_token"]))
        assert resp.status_code == 422

    def test_cross_tenant_flight_get_returns_404(self, client):
        org_a = _register(client, "Flight API Iso Org A1", "flight-iso-a1@example.com")
        org_b = _register(client, "Flight API Iso Org B1", "flight-iso-b1@example.com")
        drone = _drone(client, org_a["access_token"], "DRN-FLT-ISO-A1")
        flight = _record_flight(client, org_a["access_token"], drone["id"])

        resp = client.get(
            f"/api/v1/flights/{flight['id']}", headers=_auth(org_b["access_token"])
        )
        assert resp.status_code == 404


class TestFlightHistoryTenantIsolation:
    def test_cross_tenant_flight_history_returns_404(self, client):
        org_a = _register(client, "Flight API Iso Org A2", "flight-iso-a2@example.com")
        org_b = _register(client, "Flight API Iso Org B2", "flight-iso-b2@example.com")
        drone = _drone(client, org_a["access_token"], "DRN-FLT-ISO-A2")
        _record_flight(client, org_a["access_token"], drone["id"])

        resp = client.get(
            f"/api/v1/drones/{drone['id']}/flights", headers=_auth(org_b["access_token"])
        )
        assert resp.status_code == 404

    def test_no_cross_tenant_flight_leakage_in_own_history(self, client):
        org_a = _register(client, "Flight API Iso Org A3", "flight-iso-a3@example.com")
        org_b = _register(client, "Flight API Iso Org B3", "flight-iso-b3@example.com")
        drone_a = _drone(client, org_a["access_token"], "DRN-FLT-ISO-A3")
        drone_b = _drone(client, org_b["access_token"], "DRN-FLT-ISO-B3")
        _record_flight(client, org_a["access_token"], drone_a["id"])
        _record_flight(client, org_b["access_token"], drone_b["id"])

        resp = client.get(
            f"/api/v1/drones/{drone_a['id']}/flights", headers=_auth(org_a["access_token"])
        )
        body = resp.json()
        assert body["total"] == 1
        assert body["items"][0]["asset_id"] == drone_a["id"]


class TestBatteryCycleTenantIsolation:
    def test_recording_flight_never_increments_another_tenants_battery(self, client):
        org_a = _register(client, "Flight Battery Iso Org A", "flight-batt-iso-a@example.com")
        org_b = _register(client, "Flight Battery Iso Org B", "flight-batt-iso-b@example.com")
        drone_a = _drone(client, org_a["access_token"], "DRN-FLT-BATT-A")
        drone_b = _drone(client, org_b["access_token"], "DRN-FLT-BATT-B")

        battery_a = client.post(
            f"/api/v1/drones/{drone_a['id']}/batteries",
            headers=_auth(org_a["access_token"]),
            json={"serial_number": "BATT-FLT-A"},
        ).json()
        battery_b = client.post(
            f"/api/v1/drones/{drone_b['id']}/batteries",
            headers=_auth(org_b["access_token"]),
            json={"serial_number": "BATT-FLT-B"},
        ).json()

        _record_flight(client, org_a["access_token"], drone_a["id"], cycles=5)

        batteries_b = client.get(
            f"/api/v1/drones/{drone_b['id']}/batteries", headers=_auth(org_b["access_token"])
        ).json()
        assert batteries_b[0]["id"] == battery_b["id"]
        assert batteries_b[0]["cycle_count"] == 0

        batteries_a = client.get(
            f"/api/v1/drones/{drone_a['id']}/batteries", headers=_auth(org_a["access_token"])
        ).json()
        assert batteries_a[0]["id"] == battery_a["id"]
        assert batteries_a[0]["cycle_count"] == 5

    def test_recording_flight_with_no_attached_battery_does_not_error(self, client):
        tokens = _register(client, "Flight No Battery Org", "flight-no-batt@example.com")
        drone = _drone(client, tokens["access_token"])
        resp = client.post(
            f"/api/v1/drones/{drone['id']}/flights",
            headers=_auth(tokens["access_token"]),
            json={"flown_at": "2026-01-01T10:00:00Z", "duration_minutes": 15, "cycles": 1},
        )
        assert resp.status_code == 201


class TestFlightRBAC:
    def test_viewer_can_list_and_get_flights_but_not_record(self, client, db_session):
        tokens = _register(client, "Flight RBAC Org 1", "flight-rbac-owner1@example.com")
        org_id = _org_id(client, tokens["access_token"])
        drone = _drone(client, tokens["access_token"])
        flight = _record_flight(client, tokens["access_token"], drone["id"])
        viewer = _add_role_user(db_session, org_id, "flight-rbac-viewer1@example.com", "VIEWER")
        viewer_tokens = _login(client, viewer.email)

        list_resp = client.get(
            f"/api/v1/drones/{drone['id']}/flights", headers=_auth(viewer_tokens["access_token"])
        )
        assert list_resp.status_code == 200

        get_resp = client.get(
            f"/api/v1/flights/{flight['id']}", headers=_auth(viewer_tokens["access_token"])
        )
        assert get_resp.status_code == 200

        record_resp = client.post(
            f"/api/v1/drones/{drone['id']}/flights",
            headers=_auth(viewer_tokens["access_token"]),
            json={"flown_at": "2026-01-01T10:00:00Z", "duration_minutes": 10, "cycles": 1},
        )
        assert record_resp.status_code == 403

    def test_unauthorized_role_cannot_read_flights(self, client, db_session):
        tokens = _register(client, "Flight RBAC Org 2", "flight-rbac-owner2@example.com")
        org_id = _org_id(client, tokens["access_token"])
        drone = _drone(client, tokens["access_token"])
        # PLATFORM_STAFF is deliberately minimal and lacks DRONE_READ (see
        # app/core/permissions.py) -- same precedent used in
        # test_drone_lifecycle_api.py.
        staff = _add_role_user(
            db_session, org_id, "flight-rbac-staff2@example.com", "PLATFORM_STAFF"
        )
        staff_tokens = _login(client, staff.email)

        resp = client.get(
            f"/api/v1/drones/{drone['id']}/flights", headers=_auth(staff_tokens["access_token"])
        )
        assert resp.status_code == 403


class TestFlightValidation:
    def test_negative_duration_rejected(self, client):
        tokens = _register(client, "Flight Val Org 1", "flight-val-1@example.com")
        drone = _drone(client, tokens["access_token"])
        resp = client.post(
            f"/api/v1/drones/{drone['id']}/flights",
            headers=_auth(tokens["access_token"]),
            json={"flown_at": "2026-01-01T10:00:00Z", "duration_minutes": -5, "cycles": 1},
        )
        assert resp.status_code == 422

    def test_negative_cycles_rejected(self, client):
        tokens = _register(client, "Flight Val Org 2", "flight-val-2@example.com")
        drone = _drone(client, tokens["access_token"])
        resp = client.post(
            f"/api/v1/drones/{drone['id']}/flights",
            headers=_auth(tokens["access_token"]),
            json={"flown_at": "2026-01-01T10:00:00Z", "duration_minutes": 10, "cycles": -1},
        )
        assert resp.status_code == 422

    def test_zero_duration_rejected(self, client):
        tokens = _register(client, "Flight Val Org 3", "flight-val-3@example.com")
        drone = _drone(client, tokens["access_token"])
        resp = client.post(
            f"/api/v1/drones/{drone['id']}/flights",
            headers=_auth(tokens["access_token"]),
            json={"flown_at": "2026-01-01T10:00:00Z", "duration_minutes": 0, "cycles": 1},
        )
        assert resp.status_code == 422

    def test_invalid_pagination_offset_rejected(self, client):
        tokens = _register(client, "Flight Val Org 4", "flight-val-4@example.com")
        drone = _drone(client, tokens["access_token"])
        resp = client.get(
            f"/api/v1/drones/{drone['id']}/flights?offset=-1", headers=_auth(tokens["access_token"])
        )
        assert resp.status_code == 422

    def test_invalid_pagination_limit_rejected(self, client):
        tokens = _register(client, "Flight Val Org 5", "flight-val-5@example.com")
        drone = _drone(client, tokens["access_token"])
        resp = client.get(
            f"/api/v1/drones/{drone['id']}/flights?limit=0", headers=_auth(tokens["access_token"])
        )
        assert resp.status_code == 422


class TestUtilizationRegression:
    def test_utilization_still_correct_after_pagination_change(self, client):
        tokens = _register(client, "Flight Util Org 1", "flight-util-1@example.com")
        drone = _drone(client, tokens["access_token"])
        _record_flight(
            client, tokens["access_token"], drone["id"],
            minutes=20, cycles=2, flown_at="2026-01-01T10:00:00Z",
        )
        _record_flight(
            client, tokens["access_token"], drone["id"],
            minutes=30, cycles=3, flown_at="2026-01-02T10:00:00Z",
        )

        util = client.get(
            f"/api/v1/drones/{drone['id']}/utilization", headers=_auth(tokens["access_token"])
        ).json()
        assert util["total_flights"] == 2
        assert util["total_minutes"] == 50
        assert util["total_cycles"] == 5
