"""Base abstractions and error types for Lisa AI model providers.

This module establishes the vendor-agnostic interface for LLM providers in AeroComply.
All concrete providers (Anthropic, OpenAI-compatible local/remote, etc.) implement
AIProvider. complete() returns a structured AIProviderResponse containing either
text output or requested tool calls.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


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

    stop_reason: str  # "tool_use" | "end_turn" | other stop reasons
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
    def __init__(self, message: str | None = None) -> None:
        self._message = message or (
            "AI model is not configured. Set AI_BASE_URL and AI_MODEL (for local inference) "
            "or ANTHROPIC_API_KEY to enable the real agent."
        )

    async def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        tool_choice: dict[str, Any] | None = None,
    ) -> AIProviderResponse:
        raise AIProviderNotConfiguredError(self._message)


__all__ = [
    "AIProvider",
    "AIProviderError",
    "AIProviderNotConfiguredError",
    "AIProviderResponse",
    "AIToolCall",
    "NotConfiguredProvider",
]
