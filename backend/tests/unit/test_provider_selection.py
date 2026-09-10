"""Unit tests for the LISA AI provider selection factory."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from app.core.config import Settings
from app.services.ai.provider import (
    AIProviderNotConfiguredError,
    AnthropicProvider,
    NotConfiguredProvider,
    OpenAICompatibleProvider,
    get_ai_provider,
)


def _mock_settings(**kwargs) -> Settings:
    return Settings(
        app_name="AeroComply",
        environment="development",
        debug=False,
        database_url="postgresql+psycopg://postgres:aerocomplydevpw@localhost:55432/aerocomply_test",
        jwt_secret_key="dev-secret",
        **kwargs,
    )


def test_factory_returns_not_configured_when_no_provider_configured():
    settings = _mock_settings(
        ai_provider="auto",
        ai_base_url="",
        ai_model="",
        anthropic_api_key="",
    )
    with patch("app.services.ai.provider.get_settings", return_value=settings):
        provider = get_ai_provider()
        assert isinstance(provider, NotConfiguredProvider)


@pytest.mark.asyncio
async def test_not_configured_provider_raises_honest_error():
    provider = NotConfiguredProvider("Test not configured")
    with pytest.raises(AIProviderNotConfiguredError) as exc:
        await provider.complete(messages=[], tools=[])
    assert "Test not configured" in str(exc.value)


def test_factory_returns_openai_compatible_when_base_url_and_model_set():
    settings = _mock_settings(
        ai_provider="auto",
        ai_base_url="http://localhost:11434/v1",
        ai_model="qwen2.5:14b",
        ai_api_key="optional-key",
    )
    with patch("app.services.ai.provider.get_settings", return_value=settings):
        provider = get_ai_provider()
        assert isinstance(provider, OpenAICompatibleProvider)
        assert provider.endpoint == "http://localhost:11434/v1/chat/completions"
        assert provider.model == "qwen2.5:14b"


def test_factory_returns_anthropic_when_only_anthropic_key_set():
    settings = _mock_settings(
        ai_provider="auto",
        ai_base_url="",
        ai_model="",
        anthropic_api_key="sk-ant-test-key",
    )
    with patch("app.services.ai.provider.get_settings", return_value=settings):
        provider = get_ai_provider()
        assert isinstance(provider, AnthropicProvider)


def test_factory_explicit_openai_compatible_without_config_returns_not_configured():
    settings = _mock_settings(
        ai_provider="openai_compatible",
        ai_base_url="",
        ai_model="",
    )
    with patch("app.services.ai.provider.get_settings", return_value=settings):
        provider = get_ai_provider()
        assert isinstance(provider, NotConfiguredProvider)


def test_factory_explicit_anthropic_without_key_returns_not_configured():
    settings = _mock_settings(
        ai_provider="anthropic",
        anthropic_api_key="",
    )
    with patch("app.services.ai.provider.get_settings", return_value=settings):
        provider = get_ai_provider()
        assert isinstance(provider, NotConfiguredProvider)


def test_factory_explicit_none_returns_not_configured():
    settings = _mock_settings(
        ai_provider="none",
        ai_base_url="http://localhost:11434/v1",
        ai_model="qwen2.5:14b",
        anthropic_api_key="sk-ant-test-key",
    )
    with patch("app.services.ai.provider.get_settings", return_value=settings):
        provider = get_ai_provider()
        assert isinstance(provider, NotConfiguredProvider)


def test_factory_auto_mode_prefers_local_openai_compatible_over_anthropic():
    # If both local OpenAI-compatible and Anthropic are set, auto mode prefers local
    settings = _mock_settings(
        ai_provider="auto",
        ai_base_url="http://localhost:11434/v1",
        ai_model="qwen2.5:14b",
        anthropic_api_key="sk-ant-test-key",
    )
    with patch("app.services.ai.provider.get_settings", return_value=settings):
        provider = get_ai_provider()
        assert isinstance(provider, OpenAICompatibleProvider)
