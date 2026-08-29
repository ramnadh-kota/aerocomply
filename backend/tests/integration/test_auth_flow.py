def test_register_login_me_roundtrip(client):
    register_resp = client.post(
        "/api/v1/auth/register-organization",
        json={
            "organization_name": "Test Airline",
            "admin_email": "admin@testairline.com",
            "admin_full_name": "Ada Admin",
            "admin_password": "supersecret123",
        },
    )
    assert register_resp.status_code == 201
    tokens = register_resp.json()
    assert "access_token" in tokens and "refresh_token" in tokens

    login_resp = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@testairline.com", "password": "supersecret123"},
    )
    assert login_resp.status_code == 200

    access_token = login_resp.json()["access_token"]
    me_resp = client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {access_token}"}
    )
    assert me_resp.status_code == 200
    body = me_resp.json()
    assert body["email"] == "admin@testairline.com"
    assert "ORG_ADMIN" in body["roles"]


def test_login_wrong_password_rejected(client):
    client.post(
        "/api/v1/auth/register-organization",
        json={
            "organization_name": "Test Airline 2",
            "admin_email": "admin2@testairline.com",
            "admin_full_name": "Ada Admin",
            "admin_password": "supersecret123",
        },
    )
    resp = client.post(
        "/api/v1/auth/login",
        json={"email": "admin2@testairline.com", "password": "wrong-password"},
    )
    assert resp.status_code == 401


def test_me_requires_bearer_token(client):
    resp = client.get("/api/v1/auth/me")
    assert resp.status_code == 401


def test_duplicate_organization_email_rejected(client):
    payload = {
        "organization_name": "Dup Airline",
        "admin_email": "dup@testairline.com",
        "admin_full_name": "Dup Admin",
        "admin_password": "supersecret123",
    }
    first = client.post("/api/v1/auth/register-organization", json=payload)
    assert first.status_code == 201
    second = client.post("/api/v1/auth/register-organization", json=payload)
    assert second.status_code == 409
