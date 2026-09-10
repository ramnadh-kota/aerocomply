"""Integration test for LISA using the OpenAI-compatible provider."""

from __future__ import annotations

import json
from unittest.mock import patch

import httpx

from app.core.config import Settings
from app.schemas.aircraft import AircraftCreateRequest
from app.services import aircraft_service


def _mock_settings(**kwargs) -> Settings:
    return Settings(
        app_name="AeroComply",
        environment="development",
        debug=False,
        database_url="postgresql+psycopg://postgres:aerocomplydevpw@localhost:55432/aerocomply_test",
        jwt_secret_key="dev-secret",
        ai_provider="openai_compatible",
        ai_base_url="http://localhost:11434/v1",
        ai_model="qwen2.5:14b",
        **kwargs,
    )


def test_lisa_ask_with_openai_compatible_provider_end_to_end(client, db_session):
    # 1. Register organization and login
    resp = client.post(
        "/api/v1/auth/register-organization",
        json={
            "organization_name": "LISA Local AI Airlines",
            "admin_email": "admin@lisalocal.com",
            "admin_full_name": "LISA Admin",
            "admin_password": "supersecretpassword123",
        },
    )
    assert resp.status_code == 201
    token = resp.json()["access_token"]

    # 2. Create an aircraft in database
    me_resp = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    org_id = me_resp.json()["organization_id"]

    aircraft = aircraft_service.create_aircraft(
        db_session,
        organization_id=org_id,
        payload=AircraftCreateRequest(
            registration="VT-LISA", msn="MSN-9999", aircraft_type="A320neo", status="ACTIVE"
        ),
    )

    # 3. Mock the local inference server (turn 1 tool call -> turn 2 final text)
    turn = 0

    def mock_handler(request: httpx.Request) -> httpx.Response:
        nonlocal turn
        payload = json.loads(request.content.decode())
        assert payload["model"] == "qwen2.5:14b"
        turn += 1
        if turn == 1:
            # Model requests tool get_aircraft
            return httpx.Response(
                200,
                json={
                    "id": "chatcmpl-turn1",
                    "choices": [
                        {
                            "index": 0,
                            "message": {
                                "role": "assistant",
                                "content": None,
                                "tool_calls": [
                                    {
                                        "id": "call_1",
                                        "type": "function",
                                        "function": {
                                            "name": "get_aircraft",
                                            "arguments": json.dumps(
                                                {"aircraft_id": str(aircraft.id)}
                                            ),
                                        },
                                    }
                                ],
                            },
                            "finish_reason": "tool_calls",
                        }
                    ],
                },
            )
        else:
            # Model provides final synthesis
            return httpx.Response(
                200,
                json={
                    "id": "chatcmpl-turn2",
                    "choices": [
                        {
                            "index": 0,
                            "message": {
                                "role": "assistant",
                                "content": (
                                    "Aircraft VT-LISA (MSN-9999) is currently ACTIVE.\n"
                                    "Operationally, the aircraft is in normal status.\n"
                                    "Recommended next step: proceed with standard monitoring."
                                ),
                            },
                            "finish_reason": "stop",
                        }
                    ],
                },
            )

    transport = httpx.MockTransport(mock_handler)
    settings = _mock_settings()
    real_async_client = httpx.AsyncClient

    def _client_factory(**kwargs):
        return real_async_client(transport=transport, **kwargs)

    with (
        patch("app.core.config.get_settings", return_value=settings),
        patch("app.services.ai.provider.get_settings", return_value=settings),
        patch("httpx.AsyncClient", side_effect=_client_factory),
    ):
        ask_resp = client.post(
            "/api/v1/lisa/ask",
            headers={"Authorization": f"Bearer {token}"},
            json={"question": "What is the status of VT-LISA?"},
        )

    assert ask_resp.status_code == 200
    data = ask_resp.json()
    assert "VT-LISA" in data["headline"] or "ACTIVE" in data["headline"]
    assert any("VT-LISA" in line for line in data["narrative"])
    assert data["actionCategory"] == "INFORMATION"
    assert data["source"] == "AI_AGENT"
