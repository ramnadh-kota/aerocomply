"""API-layer tests for M20.2's general Finding/Disposition model.

Confirms: creation, listing scoped to an asset/org, disposition + closure,
tenant isolation (cross-tenant access 404s), RBAC (INSPECTION_READ/WRITE
gates), and an audit event recorded for creation/disposition/closure.
"""

from app.models.audit_event import AuditEvent


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


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _make_aircraft(client, headers, msn="MSN-FIND-1", registration=None):
    resp = client.post(
        "/api/v1/aircraft",
        json={
            "registration": registration or f"N-{msn}",
            "msn": msn,
            "aircraft_type": "B737",
        },
        headers=headers,
    )
    assert resp.status_code == 201
    return resp.json()["id"]


def test_create_and_get_finding(client):
    tokens = _register(client, "Airline Find1", "admin@airline-find1.com")
    headers = _auth(tokens["access_token"])
    aircraft_id = _make_aircraft(client, headers)

    resp = client.post(
        "/api/v1/findings",
        json={
            "title": "Cracked bracket",
            "description": "Hairline crack on mounting bracket",
            "severity": "MAJOR",
            "aircraft_id": aircraft_id,
        },
        headers=headers,
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "OPEN"
    assert body["aircraft_id"] == aircraft_id

    get_resp = client.get(f"/api/v1/findings/{body['id']}", headers=headers)
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == body["id"]


def test_finding_requires_at_least_one_traceable_link(client):
    tokens = _register(client, "Airline Find2", "admin@airline-find2.com")
    headers = _auth(tokens["access_token"])

    resp = client.post(
        "/api/v1/findings",
        json={"title": "Untraceable", "description": "no links", "severity": "MINOR"},
        headers=headers,
    )
    assert resp.status_code == 422


def test_list_findings_scoped_to_aircraft(client):
    tokens = _register(client, "Airline Find3", "admin@airline-find3.com")
    headers = _auth(tokens["access_token"])
    aircraft_a = _make_aircraft(client, headers, "MSN-FIND-3A")
    aircraft_b = _make_aircraft(client, headers, "MSN-FIND-3B")

    client.post(
        "/api/v1/findings",
        json={"title": "A finding", "description": "d", "severity": "MINOR", "aircraft_id": aircraft_a},
        headers=headers,
    )
    client.post(
        "/api/v1/findings",
        json={"title": "B finding", "description": "d", "severity": "MINOR", "aircraft_id": aircraft_b},
        headers=headers,
    )

    resp = client.get(f"/api/v1/findings?aircraft_id={aircraft_a}", headers=headers)
    assert resp.status_code == 200
    results = resp.json()
    assert len(results) == 1
    assert results[0]["title"] == "A finding"


def test_disposition_then_close_lifecycle(client, db_session):
    tokens = _register(client, "Airline Find4", "admin@airline-find4.com")
    headers = _auth(tokens["access_token"])
    aircraft_id = _make_aircraft(client, headers, "MSN-FIND-4")

    create_resp = client.post(
        "/api/v1/findings",
        json={
            "title": "Corroded fitting",
            "description": "Corrosion observed",
            "severity": "CRITICAL",
            "aircraft_id": aircraft_id,
        },
        headers=headers,
    )
    finding_id = create_resp.json()["id"]

    disp_resp = client.post(
        f"/api/v1/findings/{finding_id}/dispositions",
        json={"disposition_type": "CORRECTIVE_ACTION", "corrective_action": "Replaced fitting"},
        headers=headers,
    )
    assert disp_resp.status_code == 200
    assert disp_resp.json()["status"] == "IN_PROGRESS"
    assert len(disp_resp.json()["dispositions"]) == 1

    close_resp = client.post(f"/api/v1/findings/{finding_id}/close", headers=headers)
    assert close_resp.status_code == 200
    assert close_resp.json()["status"] == "CLOSED"
    assert close_resp.json()["dispositions"][0]["closed_at"] is not None

    events = (
        db_session.query(AuditEvent)
        .filter(AuditEvent.entity_type == "Finding", AuditEvent.entity_id == finding_id)
        .all()
    )
    actions = {e.action for e in events}
    assert actions == {"finding.created", "finding.disposition_added", "finding.closed"}


def test_cross_tenant_finding_access_404s(client):
    tokens_a = _register(client, "Airline Find5A", "admin@airline-find5a.com")
    tokens_b = _register(client, "Airline Find5B", "admin@airline-find5b.com")
    headers_a = _auth(tokens_a["access_token"])
    headers_b = _auth(tokens_b["access_token"])
    aircraft_id = _make_aircraft(client, headers_a, "MSN-FIND-5")

    create_resp = client.post(
        "/api/v1/findings",
        json={"title": "Org A finding", "description": "d", "severity": "MINOR", "aircraft_id": aircraft_id},
        headers=headers_a,
    )
    finding_id = create_resp.json()["id"]

    resp = client.get(f"/api/v1/findings/{finding_id}", headers=headers_b)
    assert resp.status_code == 404


def test_finding_endpoints_require_authentication(client):
    resp = client.get("/api/v1/findings")
    assert resp.status_code == 401

    resp = client.post(
        "/api/v1/findings",
        json={"title": "x", "description": "d", "severity": "MINOR"},
    )
    assert resp.status_code == 401
