"""End-to-end /lisa/ask tests for the deterministic context/entity/reference
resolution layer — verifies it runs (and persists) even though no
ANTHROPIC_API_KEY is configured in this environment, since resolution
happens entirely before the AI provider is ever called. Also verifies the
ambiguous-match short-circuit never reaches the provider at all.
"""

from app.core.config import get_settings


def _register(client, org_name="Lisa Context Airline", email="context-admin@lisatest.com"):
    resp = client.post(
        "/api/v1/auth/register-organization",
        json={
            "organization_name": org_name,
            "admin_email": email,
            "admin_password": "supersecret123",
            "admin_full_name": "Context Admin",
        },
    )
    assert resp.status_code == 201
    return resp.json()["access_token"]


def test_ask_resolves_and_persists_context_even_without_ai_provider(client):
    settings = get_settings()
    assert not settings.anthropic_api_key

    token = _register(client)
    headers = {"Authorization": f"Bearer {token}"}

    ac_resp = client.post(
        "/api/v1/aircraft",
        json={"registration": "VT-CTX", "msn": "MSN-CTX", "aircraft_type": "A320"},
        headers=headers,
    )
    assert ac_resp.status_code == 201
    aircraft_id = ac_resp.json()["id"]

    ask_resp = client.post(
        "/api/v1/lisa/ask",
        json={"question": "Why is VT-CTX still AOG?"},
        headers=headers,
    )
    # No AI provider configured -> honest 503, but resolution/context work
    # happens BEFORE the provider is called, so it must still have run.
    assert ask_resp.status_code == 503

    context_resp = client.get("/api/v1/lisa/context", headers=headers)
    assert context_resp.status_code == 200
    body = context_resp.json()
    assert body["current_aircraft_id"] == aircraft_id
    assert body["previous_question"] == "Why is VT-CTX still AOG?"


def test_ask_returns_clarification_for_ambiguous_aircraft_without_calling_provider(client):
    token = _register(client, org_name="Lisa Ambiguity Airline", email="ambig-admin@lisatest.com")
    headers = {"Authorization": f"Bearer {token}"}

    for msn in ("MSN-DUP-1", "MSN-DUP-2"):
        resp = client.post(
            "/api/v1/aircraft",
            json={"registration": "VT-DUP2", "msn": msn, "aircraft_type": "A320"},
            headers=headers,
        )
        assert resp.status_code == 201

    ask_resp = client.post(
        "/api/v1/lisa/ask",
        json={"question": "Why is VT-DUP2 AOG?"},
        headers=headers,
    )
    # Ambiguous match short-circuits BEFORE the provider call, so this
    # succeeds (200) even with no AI provider configured.
    assert ask_resp.status_code == 200
    body = ask_resp.json()
    assert body["confidenceState"] == "AMBIGUOUS"
    assert body["actionCategory"] == "CLARIFICATION_NEEDED"
    assert len(body["whatIFound"]) == 2


def test_lisa_context_reset_clears_active_entities(client):
    token = _register(client, org_name="Lisa Reset Airline", email="reset-admin@lisatest.com")
    headers = {"Authorization": f"Bearer {token}"}

    client.post(
        "/api/v1/aircraft",
        json={"registration": "VT-RS2", "msn": "MSN-RS2", "aircraft_type": "A320"},
        headers=headers,
    )
    client.post(
        "/api/v1/lisa/ask",
        json={"question": "Why is VT-RS2 still AOG?"},
        headers=headers,
    )
    context_resp = client.get("/api/v1/lisa/context", headers=headers)
    assert context_resp.json()["current_aircraft_id"] is not None

    reset_resp = client.post("/api/v1/lisa/context/reset", headers=headers)
    assert reset_resp.status_code == 200
    assert reset_resp.json()["current_aircraft_id"] is None


def test_lisa_context_requires_auth(client):
    resp = client.get("/api/v1/lisa/context")
    assert resp.status_code == 401
