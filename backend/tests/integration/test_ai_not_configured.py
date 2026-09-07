"""Confirms POST /lisa/ask returns the honest 503 ai_not_configured error
when no ANTHROPIC_API_KEY is set (the case in this environment). This test
must pass here — it asserts the honest failure mode, not a real LLM call."""

from app.core.config import get_settings


def test_lisa_ask_returns_ai_not_configured_without_api_key(client):
    settings = get_settings()
    assert not settings.anthropic_api_key, "test assumes no ANTHROPIC_API_KEY is configured"

    register_resp = client.post(
        "/api/v1/auth/register-organization",
        json={
            "organization_name": "Lisa Test Airline",
            "admin_email": "admin@lisatest.com",
            "admin_full_name": "Ada Admin",
            "admin_password": "supersecret123",
        },
    )
    assert register_resp.status_code == 201
    access_token = register_resp.json()["access_token"]

    resp = client.post(
        "/api/v1/lisa/ask",
        json={"question": "What is the status of work order WO-1042?"},
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert resp.status_code == 503
    body = resp.json()
    assert body["error"]["code"] == "ai_not_configured"
    assert "ANTHROPIC_API_KEY" in body["error"]["message"]


def test_lisa_ask_requires_auth(client):
    resp = client.post("/api/v1/lisa/ask", json={"question": "hello"})
    assert resp.status_code == 401
