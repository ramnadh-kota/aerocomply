"""Unit tests for the OpenAI-compatible local AI provider."""

from __future__ import annotations

import json
from unittest.mock import patch

import httpx
import pytest

from app.services.ai.providers.base import (
    AIProviderError,
    AIProviderResponse,
    AIToolCall,
)
from app.services.ai.providers.openai_compatible import OpenAICompatibleProvider


def test_provider_initialization_and_endpoint_normalization():
    # Various valid base URLs
    p1 = OpenAICompatibleProvider(base_url="http://localhost:11434/v1", model="qwen2.5:14b")
    assert p1.endpoint == "http://localhost:11434/v1/chat/completions"
    assert p1.model == "qwen2.5:14b"

    p2 = OpenAICompatibleProvider(base_url="http://localhost:11434", model="llama3.3:70b")
    assert p2.endpoint == "http://localhost:11434/v1/chat/completions"

    p3 = OpenAICompatibleProvider(
        base_url="http://vllm-server:8000/v1/chat/completions", model="mistral"
    )
    assert p3.endpoint == "http://vllm-server:8000/v1/chat/completions"

    # Stripping whitespace
    p4 = OpenAICompatibleProvider(base_url="  http://localhost:11434/v1/  ", model="  qwen  ")
    assert p4.endpoint == "http://localhost:11434/v1/chat/completions"
    assert p4.model == "qwen"


def test_provider_initialization_invalid_arguments():
    with pytest.raises(AIProviderError) as exc:
        OpenAICompatibleProvider(base_url="", model="model-name")
    assert "non-empty base_url" in str(exc.value)

    with pytest.raises(AIProviderError) as exc:
        OpenAICompatibleProvider(base_url="http://localhost:11434", model="   ")
    assert "non-empty model name" in str(exc.value)


def test_headers_with_and_without_api_key():
    p_no_key = OpenAICompatibleProvider(base_url="http://localhost:11434/v1", model="test-model")
    headers_no_key = p_no_key._build_headers()
    assert headers_no_key == {"Content-Type": "application/json"}
    assert "Authorization" not in headers_no_key

    p_with_key = OpenAICompatibleProvider(
        base_url="http://localhost:11434/v1", model="test-model", api_key="secret-token-123"
    )
    headers_with_key = p_with_key._build_headers()
    assert headers_with_key["Authorization"] == "Bearer secret-token-123"


def test_tool_conversion():
    provider = OpenAICompatibleProvider(base_url="http://localhost:11434/v1", model="test-model")

    raw_tools = [
        {
            "name": "get_aircraft",
            "description": "Get aircraft details",
            "input_schema": {
                "type": "object",
                "properties": {"aircraft_id": {"type": "string"}},
                "required": ["aircraft_id"],
            },
        },
        {
            "type": "function",
            "function": {
                "name": "already_converted",
                "description": "Already formatted",
                "parameters": {},
            },
        },
    ]

    converted = provider._convert_tools(raw_tools)
    assert len(converted) == 2
    assert converted[0] == {
        "type": "function",
        "function": {
            "name": "get_aircraft",
            "description": "Get aircraft details",
            "parameters": {
                "type": "object",
                "properties": {"aircraft_id": {"type": "string"}},
                "required": ["aircraft_id"],
            },
        },
    }
    assert converted[1] == raw_tools[1]


def test_message_conversion_multi_turn_with_tool_use_and_results():
    provider = OpenAICompatibleProvider(base_url="http://localhost:11434/v1", model="test-model")

    messages = [
        {"role": "user", "content": "Check aircraft status"},
        {
            "role": "assistant",
            "content": [
                {"type": "text", "text": "I will check the aircraft."},
                {
                    "type": "tool_use",
                    "id": "call_123",
                    "name": "get_aircraft",
                    "input": {"aircraft_id": "plane-uuid"},
                },
            ],
        },
        {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": "call_123",
                    "content": "{'registration': 'N123'}",
                }
            ],
        },
    ]

    converted = provider._convert_messages(messages)
    assert len(converted) == 3

    assert converted[0] == {"role": "user", "content": "Check aircraft status"}

    assert converted[1] == {
        "role": "assistant",
        "content": "I will check the aircraft.",
        "tool_calls": [
            {
                "id": "call_123",
                "type": "function",
                "function": {
                    "name": "get_aircraft",
                    "arguments": json.dumps({"aircraft_id": "plane-uuid"}),
                },
            }
        ],
    }

    assert converted[2] == {
        "role": "tool",
        "tool_call_id": "call_123",
        "content": "{'registration': 'N123'}",
    }


@pytest.mark.asyncio
async def test_complete_text_response():
    provider = OpenAICompatibleProvider(base_url="http://localhost:11434/v1", model="qwen2.5:14b")

    mock_response = {
        "id": "chatcmpl-1",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": "RII stands for Required Inspection Item.",
                },
                "finish_reason": "stop",
            }
        ],
    }

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == "http://localhost:11434/v1/chat/completions"
        payload = json.loads(request.content.decode())
        assert payload["model"] == "qwen2.5:14b"
        assert payload["messages"][0]["content"] == "what is RII?"
        return httpx.Response(200, json=mock_response)

    transport = httpx.MockTransport(handler)
    with patch("httpx.AsyncClient", return_value=httpx.AsyncClient(transport=transport)):
        result = await provider.complete(
            messages=[{"role": "user", "content": "what is RII?"}], tools=[]
        )

    assert isinstance(result, AIProviderResponse)
    assert result.stop_reason == "end_turn"
    assert result.text == "RII stands for Required Inspection Item."
    assert result.tool_calls == []


@pytest.mark.asyncio
async def test_complete_tool_calls_response():
    provider = OpenAICompatibleProvider(base_url="http://localhost:11434/v1", model="qwen2.5:14b")

    mock_response = {
        "id": "chatcmpl-2",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call_abc123",
                            "type": "function",
                            "function": {
                                "name": "get_aircraft",
                                "arguments": '{"aircraft_id": "plane-456"}',
                            },
                        },
                        {
                            "id": "call_xyz789",
                            "type": "function",
                            "function": {
                                "name": "get_work_order",
                                "arguments": {"work_order_id": "wo-101"},
                            },
                        },
                    ],
                },
                "finish_reason": "tool_calls",
            }
        ],
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=mock_response)

    transport = httpx.MockTransport(handler)
    with patch("httpx.AsyncClient", return_value=httpx.AsyncClient(transport=transport)):
        result = await provider.complete(
            messages=[{"role": "user", "content": "Check status of plane-456"}],
            tools=[{"name": "get_aircraft", "description": "...", "input_schema": {}}],
        )

    assert isinstance(result, AIProviderResponse)
    assert result.stop_reason == "tool_use"
    assert len(result.tool_calls) == 2
    assert result.tool_calls[0] == AIToolCall(
        id="call_abc123", name="get_aircraft", input={"aircraft_id": "plane-456"}
    )
    assert result.tool_calls[1] == AIToolCall(
        id="call_xyz789", name="get_work_order", input={"work_order_id": "wo-101"}
    )


@pytest.mark.asyncio
async def test_complete_http_4xx_error():
    provider = OpenAICompatibleProvider(base_url="http://localhost:11434/v1", model="test-model")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, text="Model 'unknown-model' not found")

    transport = httpx.MockTransport(handler)
    with patch("httpx.AsyncClient", return_value=httpx.AsyncClient(transport=transport)):
        with pytest.raises(AIProviderError) as exc:
            await provider.complete(messages=[{"role": "user", "content": "hi"}], tools=[])
        assert "status 404" in str(exc.value)
        assert "Model 'unknown-model' not found" in str(exc.value)


@pytest.mark.asyncio
async def test_complete_http_5xx_error_retries_and_raises():
    provider = OpenAICompatibleProvider(base_url="http://localhost:11434/v1", model="test-model")
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(500, text="Internal Server Error in inference runtime")

    transport = httpx.MockTransport(handler)
    with patch("httpx.AsyncClient", return_value=httpx.AsyncClient(transport=transport)):
        with pytest.raises(AIProviderError) as exc:
            await provider.complete(messages=[{"role": "user", "content": "hi"}], tools=[])
        assert attempts == 2
        assert "status 500" in str(exc.value)


@pytest.mark.asyncio
async def test_complete_timeout_error():
    provider = OpenAICompatibleProvider(base_url="http://localhost:11434/v1", model="test-model")

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("Request timed out after 30s")

    transport = httpx.MockTransport(handler)
    with patch("httpx.AsyncClient", return_value=httpx.AsyncClient(transport=transport)):
        with pytest.raises(AIProviderError) as exc:
            await provider.complete(messages=[{"role": "user", "content": "hi"}], tools=[])
        assert "connection failed after retry" in str(exc.value).lower()


@pytest.mark.asyncio
async def test_complete_invalid_json():
    provider = OpenAICompatibleProvider(base_url="http://localhost:11434/v1", model="test-model")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="NOT JSON AT ALL")

    transport = httpx.MockTransport(handler)
    with patch("httpx.AsyncClient", return_value=httpx.AsyncClient(transport=transport)):
        with pytest.raises(AIProviderError) as exc:
            await provider.complete(messages=[{"role": "user", "content": "hi"}], tools=[])
        assert "invalid json" in str(exc.value).lower()


@pytest.mark.asyncio
async def test_complete_missing_choices():
    provider = OpenAICompatibleProvider(base_url="http://localhost:11434/v1", model="test-model")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": []})

    transport = httpx.MockTransport(handler)
    with patch("httpx.AsyncClient", return_value=httpx.AsyncClient(transport=transport)):
        with pytest.raises(AIProviderError) as exc:
            await provider.complete(messages=[{"role": "user", "content": "hi"}], tools=[])
        assert "missing or empty 'choices'" in str(exc.value).lower()
