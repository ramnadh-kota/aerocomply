"""OpenAI-compatible HTTP provider for local/self-hosted or remote LLMs.

Communicates with any inference server supporting the OpenAI /v1/chat/completions API
specification, such as:
- vLLM (high throughput on-premises server)
- Ollama (local open-weight runtime)
- Any OpenAI-compatible gateway

The provider translates AeroComply tool definitions and multi-turn message blocks into
OpenAI function-calling wire format, executes asynchronous HTTP requests with transient
retry support, and parses tool calls into standardized AIToolCall dataclass instances.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any

import httpx

from app.core.logging import get_logger
from app.services.ai.providers.base import (
    AIProvider,
    AIProviderError,
    AIProviderResponse,
    AIToolCall,
)

logger = get_logger(__name__)


class OpenAICompatibleProvider(AIProvider):
    """OpenAI-compatible Chat Completions API provider.

    Accepts base_url, model name, optional API key, and timeout.
    Translates tool definitions and tool results between AeroComply's internal
    representation and the standard OpenAI wire format.
    """

    def __init__(
        self,
        base_url: str,
        model: str,
        api_key: str | None = None,
        timeout_seconds: float = 30.0,
    ) -> None:
        if not base_url or not base_url.strip():
            raise AIProviderError("OpenAICompatibleProvider requires a non-empty base_url")
        if not model or not model.strip():
            raise AIProviderError("OpenAICompatibleProvider requires a non-empty model name")

        self._base_url = base_url.strip()
        self._model = model.strip()
        self._api_key = (api_key or "").strip()
        self._timeout_seconds = timeout_seconds
        self._endpoint = self._normalize_endpoint(self._base_url)

    @staticmethod
    def _normalize_endpoint(base_url: str) -> str:
        clean = base_url.strip().rstrip("/")
        if clean.endswith("/chat/completions"):
            return clean
        if clean.endswith("/v1"):
            return f"{clean}/chat/completions"
        return f"{clean}/v1/chat/completions"

    @property
    def endpoint(self) -> str:
        return self._endpoint

    @property
    def model(self) -> str:
        return self._model

    def _build_headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        return headers

    def _convert_tools(self, tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
        converted: list[dict[str, Any]] = []
        for tool in tools:
            if "type" in tool and tool["type"] == "function":
                converted.append(tool)
            else:
                params = (
                    tool.get("input_schema")
                    or tool.get("parameters")
                    or {"type": "object", "properties": {}}
                )
                converted.append(
                    {
                        "type": "function",
                        "function": {
                            "name": tool["name"],
                            "description": tool.get("description", ""),
                            "parameters": params,
                        },
                    }
                )
        return converted

    def _convert_messages(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        openai_messages: list[dict[str, Any]] = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content")

            if isinstance(content, str):
                openai_messages.append({"role": role, "content": content})
            elif isinstance(content, list):
                # Handle Anthropic-style tool_result content blocks from user
                if role == "user" and any(
                    isinstance(b, dict) and b.get("type") == "tool_result" for b in content
                ):
                    for block in content:
                        if isinstance(block, dict) and block.get("type") == "tool_result":
                            openai_messages.append(
                                {
                                    "role": "tool",
                                    "tool_call_id": block.get("tool_use_id", ""),
                                    "content": str(block.get("content", "")),
                                }
                            )
                        elif isinstance(block, dict) and block.get("type") == "text":
                            openai_messages.append(
                                {"role": "user", "content": block.get("text", "")}
                            )
                # Handle Anthropic-style assistant content blocks (text + tool_use)
                elif role == "assistant":
                    text_parts: list[str] = []
                    tool_calls: list[dict[str, Any]] = []
                    for block in content:
                        if isinstance(block, dict):
                            btype = block.get("type")
                            if btype == "text":
                                text_parts.append(block.get("text", ""))
                            elif btype == "tool_use":
                                raw_input = block.get("input", {})
                                args_str = (
                                    json.dumps(raw_input)
                                    if isinstance(raw_input, (dict, list))
                                    else str(raw_input)
                                )
                                tool_calls.append(
                                    {
                                        "id": block.get("id", ""),
                                        "type": "function",
                                        "function": {
                                            "name": block.get("name", ""),
                                            "arguments": args_str,
                                        },
                                    }
                                )
                    asst_msg: dict[str, Any] = {
                        "role": "assistant",
                        "content": "\n".join(text_parts) if text_parts else None,
                    }
                    if tool_calls:
                        asst_msg["tool_calls"] = tool_calls
                    openai_messages.append(asst_msg)
                else:
                    joined = "\n".join(
                        str(b.get("text", b)) if isinstance(b, dict) else str(b) for b in content
                    )
                    openai_messages.append({"role": role, "content": joined})
            elif isinstance(content, dict) and role == "tool":
                openai_messages.append(msg)
            else:
                openai_messages.append(
                    {"role": role, "content": str(content) if content is not None else None}
                )
        return openai_messages

    async def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        tool_choice: dict[str, Any] | None = None,
    ) -> AIProviderResponse:
        payload: dict[str, Any] = {
            "model": self._model,
            "messages": self._convert_messages(messages),
        }
        if tools:
            payload["tools"] = self._convert_tools(tools)
        if tool_choice:
            payload["tool_choice"] = tool_choice

        headers = self._build_headers()
        last_error: Exception | None = None

        # Retry once on transient errors (connection / timeout / 5xx).
        async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
            for attempt in range(2):
                try:
                    response = await client.post(
                        self._endpoint,
                        json=payload,
                        headers=headers,
                    )
                    if response.status_code >= 400:
                        error_body = response.text
                        if response.status_code >= 500 and attempt == 0:
                            logger.warning(
                                "ai_provider_server_error_retry",
                                attempt=attempt,
                                status_code=response.status_code,
                            )
                            await asyncio.sleep(0.5)
                            continue
                        raise AIProviderError(
                            f"OpenAI-compatible API returned status {response.status_code}: "
                            f"{error_body}"
                        )

                    data = response.json()
                    break
                except (httpx.TimeoutException, httpx.ConnectError, httpx.ConnectTimeout) as exc:
                    last_error = exc
                    logger.warning(
                        "ai_provider_network_error",
                        attempt=attempt,
                        error=type(exc).__name__,
                    )
                    if attempt == 0:
                        await asyncio.sleep(0.5)
                        continue
                    raise AIProviderError(
                        f"OpenAI-compatible connection failed after retry: {exc}"
                    ) from exc
                except httpx.HTTPError as exc:
                    raise AIProviderError(f"OpenAI-compatible HTTP client error: {exc}") from exc
                except json.JSONDecodeError as exc:
                    raise AIProviderError(
                        f"OpenAI-compatible returned invalid JSON: {exc}"
                    ) from exc
            else:  # pragma: no cover
                raise AIProviderError(f"OpenAI-compatible request failed: {last_error}")

        if not isinstance(data, dict) or "choices" not in data or not data["choices"]:
            raise AIProviderError("OpenAI-compatible response missing or empty 'choices' list")

        choice = data["choices"][0]
        message = choice.get("message", {})
        finish_reason = choice.get("finish_reason", "stop")

        text_content = message.get("content") or ""
        raw_tool_calls = message.get("tool_calls") or []

        tool_calls: list[AIToolCall] = []
        for tc in raw_tool_calls:
            tc_id = tc.get("id") or f"call-{uuid.uuid4().hex[:12]}"
            fn = tc.get("function", {})
            fn_name = fn.get("name", "")
            raw_args = fn.get("arguments", {})
            if isinstance(raw_args, str):
                try:
                    parsed_args = json.loads(raw_args) if raw_args.strip() else {}
                except json.JSONDecodeError:
                    parsed_args = {"_raw": raw_args}
            elif isinstance(raw_args, dict):
                parsed_args = raw_args
            else:
                parsed_args = {}
            tool_calls.append(AIToolCall(id=tc_id, name=fn_name, input=parsed_args))

        if tool_calls or finish_reason == "tool_calls":
            stop_reason = "tool_use"
        else:
            stop_reason = "end_turn"

        return AIProviderResponse(
            stop_reason=stop_reason,
            text=text_content,
            tool_calls=tool_calls,
            raw=data,
        )


__all__ = ["OpenAICompatibleProvider"]
