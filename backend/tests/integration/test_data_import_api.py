"""API-layer test for the bulk import HTTP endpoints: upload -> validate ->
preview -> confirm -> import -> history, and tenant isolation of jobs."""


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


def test_full_aircraft_import_flow_via_api(client):
    tokens = _register(client, "Import Flow MRO", "admin@import-flow-mro.com")
    headers = _auth(tokens["access_token"])

    csv_content = (
        b"registration,msn,aircraft_type,status\n"
        b"N100IF,MSN-IF-1,A320,ACTIVE\n"
        b",MSN-IF-2,A320,ACTIVE\n"
    )

    validate_resp = client.post(
        "/api/v1/data-import/aircraft/validate",
        files={"file": ("aircraft.csv", csv_content, "text/csv")},
        headers=headers,
    )
    assert validate_resp.status_code == 201
    job = validate_resp.json()
    assert job["rows_total"] == 2
    assert job["rows_valid"] == 1
    assert job["rows_invalid"] == 1
    assert job["status"] == "VALIDATED"

    history_resp = client.get("/api/v1/data-import/jobs", headers=headers)
    assert history_resp.status_code == 200
    assert len(history_resp.json()) == 1

    commit_resp = client.post(f"/api/v1/data-import/jobs/{job['id']}/commit", headers=headers)
    assert commit_resp.status_code == 200
    completed = commit_resp.json()
    assert completed["status"] == "COMPLETED"
    assert completed["rows_created"] == 1

    aircraft_list = client.get("/api/v1/aircraft", headers=headers)
    assert aircraft_list.status_code == 200
    assert len(aircraft_list.json()) == 1
    assert aircraft_list.json()[0]["registration"] == "N100IF"


def test_import_job_not_visible_to_other_tenant(client):
    tokens_a = _register(client, "Import Tenant A", "admin@import-tenant-a.com")
    tokens_b = _register(client, "Import Tenant B", "admin@import-tenant-b.com")

    csv_content = b"registration,msn,aircraft_type,status\nN200IT,MSN-IT-1,A320,ACTIVE\n"
    validate_resp = client.post(
        "/api/v1/data-import/aircraft/validate",
        files={"file": ("aircraft.csv", csv_content, "text/csv")},
        headers=_auth(tokens_a["access_token"]),
    )
    job_id = validate_resp.json()["id"]

    get_resp = client.get(
        f"/api/v1/data-import/jobs/{job_id}", headers=_auth(tokens_b["access_token"])
    )
    assert get_resp.status_code == 404

    list_resp = client.get("/api/v1/data-import/jobs", headers=_auth(tokens_b["access_token"]))
    assert list_resp.json() == []
