"""Verifies the organization_id embedded in a user's token matches their own
organization and never another tenant's — the foundational multi-tenancy
guarantee described in FOUNDATION.md §9.
"""


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


def test_two_orgs_get_distinct_organization_ids(client):
    tokens_a = _register(client, "Airline A", "admin@airline-a.com")
    tokens_b = _register(client, "Airline B", "admin@airline-b.com")

    me_a = client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {tokens_a['access_token']}"}
    ).json()
    me_b = client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {tokens_b['access_token']}"}
    ).json()

    assert me_a["organization_id"] != me_b["organization_id"]
    assert me_a["email"] == "admin@airline-a.com"
    assert me_b["email"] == "admin@airline-b.com"
