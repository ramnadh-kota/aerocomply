"""LLM provider abstraction for the Lisa agent.

Two implementations:
- NotConfiguredProvider: used whenever ANTHROPIC_API_KEY is unset. Its
  complete() always raises AIProviderNotConfiguredError — it never
  fabricates or silently substitutes a fake response.
- AnthropicProvider: real implementation over the Anthropic Messages API
  with tool use, a hard round-trip cap, a request timeout, and a single
  retry on transient errors.

get_ai_provider() is the only factory callers should use; which concrete
class it returns depends solely on whether an API key is configured.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class AIProviderNotConfiguredError(Exception):
    """Raised by NotConfiguredProvider.complete(). Never caught and papered
    over with fake data — callers must surface this as ai_not_configured."""


class AIProviderError(Exception):
    """Raised for real provider failures (timeout, exhausted retries, API error)."""


@dataclass
class AIToolCall:
    id: str
    name: str
    input: dict[str, Any]


@dataclass
class AIProviderResponse:
    """Either a request for more tool calls, or a final text answer."""

    stop_reason: str  # "tool_use" | "end_turn" | other Anthropic stop reasons
    text: str = ""
    tool_calls: list[AIToolCall] = field(default_factory=list)
    raw: Any = None


class AIProvider(ABC):
    @abstractmethod
    async def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        tool_choice: dict[str, Any] | None = None,
    ) -> AIProviderResponse:
        """Send one turn of the conversation to the model."""
        raise NotImplementedError


class NotConfiguredProvider(AIProvider):
    async def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        tool_choice: dict[str, Any] | None = None,
    ) -> AIProviderResponse:
        raise AIProviderNotConfiguredError(
            "AI model is not configured. Set ANTHROPIC_API_KEY to enable the real agent."
        )


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
    """Factory: real provider iff ANTHROPIC_API_KEY is set, else the honest
    not-configured stub. This is the ONLY place that decision is made."""
    settings = get_settings()
    api_key = (settings.anthropic_api_key or "").strip()
    if not api_key:
        return NotConfiguredProvider()
    return AnthropicProvider(
        api_key=api_key,
        model=settings.anthropic_model,
        timeout_seconds=settings.ai_request_timeout_seconds,
    )
