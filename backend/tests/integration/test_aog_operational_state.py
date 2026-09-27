"""Live AOG -> operational-state integration test (Developer 1 Lifecycle
sprint, Phase 9). Declaring an AogEvent (backend/app/models/aog_event.py)
is the actual domain path that puts an asset into AOG -- there is no direct
"set asset to AOG" transition; AOG is derived by asset_service.
compute_operational_state() checking for an active (DECLARED/IN_RECOVERY)
AogEvent against the asset. This test exercises that real path end to end
and confirms the same state is visible through both the asset-context
endpoint and the fleet-wide Command Center summary.
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
    assert resp.status_code == 201, resp.text
    return resp.json()


def _aircraft(client, headers, registration="N-AOG-1"):
    resp = client.post(
        "/api/v1/aircraft",
        headers=headers,
        json={"registration": registration, "msn": f"MSN-{registration}", "aircraft_type": "B737"},
    )
    assert resp.status_code == 201, resp.text
    aircraft = resp.json()

    # AircraftResponse deliberately omits asset_id (see its schema docstring)
    # for backward-compatibility reasons unrelated to this test -- resolve it
    # via the generic Asset registry instead, matching how work_order_service
    # etc. already do this resolution server-side.
    assets_resp = client.get(f"/api/v1/assets?search={registration}", headers=headers)
    assert assets_resp.status_code == 200, assets_resp.text
    matches = [a for a in assets_resp.json() if a["registration"] == registration]
    assert len(matches) == 1, f"expected exactly one asset for {registration}, got {matches}"
    aircraft["asset_id"] = matches[0]["id"]
    return aircraft


def test_declared_aog_event_drives_operational_state_and_propagates(client):
    tokens = _register(client, "Airline AOG1", "admin@airline-aog1.com")
    headers = _auth(tokens["access_token"])

    aircraft = _aircraft(client, headers)
    asset_id = aircraft["asset_id"]
    assert asset_id is not None, "aircraft must resolve to an asset_id for compute_operational_state"

    # Before AOG: fresh aircraft is AVAILABLE.
    ctx = client.get(f"/api/v1/assets/{asset_id}/context", headers=headers)
    assert ctx.status_code == 200
    assert ctx.json()["operational_status"] == "AVAILABLE"

    # 1. Create asset (done above) 2. valid operational conditions (a fresh,
    # active aircraft) 3. transition into AOG via the actual supported
    # domain path: declaring an AogEvent.
    aog_resp = client.post(
        "/api/v1/aog-events",
        headers=headers,
        json={"aircraft_id": aircraft["id"], "severity": "CRITICAL", "root_cause": "Hydraulic leak on approach"},
    )
    assert aog_resp.status_code == 201, aog_resp.text
    aog_event_id = aog_resp.json()["id"]

    # 4-5. Query operational state, verify AOG.
    ctx_after = client.get(f"/api/v1/assets/{asset_id}/context", headers=headers)
    assert ctx_after.status_code == 200
    assert ctx_after.json()["operational_status"] == "AOG"

    # 6. Command Center reflects AOG (both the per-asset row and the
    # fleet-wide 8-value distribution).
    fleet_resp = client.get("/api/v1/control-center/fleet", headers=headers)
    assert fleet_resp.status_code == 200
    row = next(r for r in fleet_resp.json() if r["aircraft_id"] == aircraft["id"])
    assert row["operational_status"] == "AOG"
    assert row["active_aog_event_id"] == aog_event_id

    summary_resp = client.get("/api/v1/control-center/summary", headers=headers)
    assert summary_resp.status_code == 200
    summary = summary_resp.json()
    assert summary["aog"] == 1
    assert summary["operational_states"]["AOG"] == 1

    # 8. Lifecycle/audit evidence exists for the AOG declaration.
    timeline_resp = client.get(f"/api/v1/assets/{asset_id}/history", headers=headers)
    assert timeline_resp.status_code == 200
    actions = {e["metadata"].get("action") for e in timeline_resp.json()["events"] if e["event_type"] == "AUDIT_EVENT"}
    # AOG audit events are recorded under entity_type "AogEvent", not "Asset",
    # so they are not expected to appear in the Asset-scoped audit rows of
    # the timeline; confirm the AogEvent's own audit trail directly instead.
    from app.models.audit_event import AuditEvent

    db_session = next(app.dependency_overrides[get_db_session]())
    audit_rows = (
        db_session.query(AuditEvent)
        .filter(AuditEvent.entity_type == "AogEvent", AuditEvent.entity_id == uuid.UUID(aog_event_id))
        .all()
    )
    assert len(audit_rows) >= 1, "declaring AOG must be audited"

    # 9. Tenant isolation: a second org cannot see this AOG event or asset.
    tokens_b = _register(client, "Airline AOG1B", "admin@airline-aog1b.com")
    headers_b = _auth(tokens_b["access_token"])
    assert client.get(f"/api/v1/assets/{asset_id}/context", headers=headers_b).status_code == 404
    cross_fleet = client.get("/api/v1/control-center/fleet", headers=headers_b)
    assert cross_fleet.status_code == 200
    assert cross_fleet.json() == []


def test_recovered_aog_event_returns_to_available(client):
    tokens = _register(client, "Airline AOG2", "admin@airline-aog2.com")
    headers = _auth(tokens["access_token"])
    aircraft = _aircraft(client, headers, registration="N-AOG-2")
    asset_id = aircraft["asset_id"]

    aog_resp = client.post(
        "/api/v1/aog-events",
        headers=headers,
        json={"aircraft_id": aircraft["id"]},
    )
    aog_event_id = aog_resp.json()["id"]
    assert client.get(f"/api/v1/assets/{asset_id}/context", headers=headers).json()["operational_status"] == "AOG"

    start_recovery_resp = client.post(f"/api/v1/aog-events/{aog_event_id}/start-recovery", headers=headers)
    assert start_recovery_resp.status_code == 200, start_recovery_resp.text
    # IN_RECOVERY is still an active AOG state per
    # asset_service.compute_operational_state's AogEventStatus check.
    assert client.get(f"/api/v1/assets/{asset_id}/context", headers=headers).json()["operational_status"] == "AOG"

    recovered_resp = client.post(f"/api/v1/aog-events/{aog_event_id}/mark-recovered", headers=headers)
    assert recovered_resp.status_code == 200, recovered_resp.text

    ctx_after = client.get(f"/api/v1/assets/{asset_id}/context", headers=headers)
    assert ctx_after.json()["operational_status"] == "AVAILABLE"
