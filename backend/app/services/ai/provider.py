"""LLM provider abstraction for the Lisa agent.

Provides factory and provider implementations for:
- NotConfiguredProvider: used whenever no AI provider is configured. complete()
  always raises AIProviderNotConfiguredError — never fabricates a response.
- OpenAICompatibleProvider: for self-hosted/local inference (vLLM, Ollama) or
  OpenAI-compatible endpoints over asynchronous HTTP.
- AnthropicProvider: for Anthropic Messages API (optional, lazy loaded).

get_ai_provider() is the central factory callers use to obtain the configured provider.
"""

from __future__ import annotations

import time
from typing import Any

from app.core.config import get_settings
from app.core.logging import get_logger
from app.services.ai.providers.base import (
    AIProvider,
    AIProviderError,
    AIProviderNotConfiguredError,
    AIProviderResponse,
    AIToolCall,
    NotConfiguredProvider,
)
from app.services.ai.providers.openai_compatible import OpenAICompatibleProvider

logger = get_logger(__name__)


class AnthropicProvider(AIProvider):
    """Real Anthropic Messages API provider. Only imports the `anthropic`
    package lazily, at construction time, so environments without a key
    configured (and thus without ever instantiating this class) never pay
    an import cost or require the package to be importable."""

    MAX_TOOL_ROUND_TRIPS = 6

    def __init__(self, api_key: str, model: str, timeout_seconds: float) -> None:
        import anthropic  # local import: only needed when actually configured

        self._client = anthropic.AsyncAnthropic(api_key=api_key, timeout=timeout_seconds)
        self._model = model
        self._timeout_seconds = timeout_seconds

    async def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        tool_choice: dict[str, Any] | None = None,
    ) -> AIProviderResponse:
        import anthropic

        kwargs: dict[str, Any] = {
            "model": self._model,
            "max_tokens": 2048,
            "messages": messages,
        }
        if tools:
            kwargs["tools"] = tools
        if tool_choice:
            kwargs["tool_choice"] = tool_choice

        last_error: Exception | None = None
        # Retry once on transient errors (timeout / connection / 5xx / overload).
        for attempt in range(2):
            try:
                response = await self._client.messages.create(**kwargs)
                break
            except (
                anthropic.APITimeoutError,
                anthropic.APIConnectionError,
                anthropic.InternalServerError,
                anthropic.RateLimitError,
            ) as exc:
                last_error = exc
                logger.warning("ai_provider_transient_error", attempt=attempt, error=str(exc))
                if attempt == 0:
                    time.sleep(0.5)
                    continue
                raise AIProviderError(f"Anthropic API call failed after retry: {exc}") from exc
            except anthropic.APIError as exc:
                raise AIProviderError(f"Anthropic API error: {exc}") from exc
        else:  # pragma: no cover - loop always breaks or raises
            raise AIProviderError(f"Anthropic API call failed: {last_error}")

        text_parts: list[str] = []
        tool_calls: list[AIToolCall] = []
        for block in response.content:
            if block.type == "text":
                text_parts.append(block.text)
            elif block.type == "tool_use":
                tool_calls.append(AIToolCall(id=block.id, name=block.name, input=block.input or {}))

        return AIProviderResponse(
            stop_reason=response.stop_reason or "end_turn",
            text="\n".join(text_parts),
            tool_calls=tool_calls,
            raw=response,
        )


def get_ai_provider() -> AIProvider:
    """Factory: resolves the active AI provider based on configuration.

    Supports:
    - OpenAI-compatible local/remote providers (vLLM, Ollama, etc.) via AI_BASE_URL and AI_MODEL
    - Anthropic Claude via ANTHROPIC_API_KEY
    - Explicit AI_PROVIDER setting ('openai_compatible', 'anthropic', 'none', 'auto')
    - Honest NotConfiguredProvider whenever required configurations are absent.
    """
    settings = get_settings()
    provider_type = (settings.ai_provider or "auto").strip().lower()

    if provider_type == "none":
        return NotConfiguredProvider("AI provider is explicitly disabled.")

    if provider_type == "openai_compatible":
        base_url = (settings.ai_base_url or "").strip()
        model = (settings.ai_model or "").strip()
        if not base_url or not model:
            return NotConfiguredProvider(
                "OpenAI-compatible AI provider is selected but not configured. "
                "Set AI_BASE_URL and AI_MODEL."
            )
        return OpenAICompatibleProvider(
            base_url=base_url,
            model=model,
            api_key=settings.ai_api_key or None,
            timeout_seconds=settings.ai_request_timeout_seconds,
        )

    if provider_type == "anthropic":
        api_key = (settings.anthropic_api_key or "").strip()
        if not api_key:
            return NotConfiguredProvider(
                "Anthropic AI provider is selected but not configured. Set ANTHROPIC_API_KEY."
            )
        return AnthropicProvider(
            api_key=api_key,
            model=settings.anthropic_model,
            timeout_seconds=settings.ai_request_timeout_seconds,
        )

    # "auto" detection mode:
    # 1. Prefer OpenAI-compatible if AI_BASE_URL and AI_MODEL are configured
    base_url = (settings.ai_base_url or "").strip()
    model = (settings.ai_model or "").strip()
    if base_url and model:
        return OpenAICompatibleProvider(
            base_url=base_url,
            model=model,
            api_key=settings.ai_api_key or None,
            timeout_seconds=settings.ai_request_timeout_seconds,
        )

    # 2. Fall back to Anthropic if ANTHROPIC_API_KEY is configured
    api_key = (settings.anthropic_api_key or "").strip()
    if api_key:
        return AnthropicProvider(
            api_key=api_key,
            model=settings.anthropic_model,
            timeout_seconds=settings.ai_request_timeout_seconds,
        )

    # 3. Otherwise return the honest not-configured provider
    return NotConfiguredProvider()


__all__ = [
    "AIProvider",
    "AIProviderError",
    "AIProviderNotConfiguredError",
    "AIProviderResponse",
    "AIToolCall",
    "AnthropicProvider",
    "NotConfiguredProvider",
    "OpenAICompatibleProvider",
    "get_ai_provider",
]
