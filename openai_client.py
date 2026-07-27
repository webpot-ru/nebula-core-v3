"""Minimal fail-closed OpenAI JSON client for the acc1 translation lane."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Any

import requests

from openai_flex_recovery import FLEX_RESOURCE_UNAVAILABLE_MESSAGE


OPENAI_CHAT_COMPLETIONS_URL = "https://api.openai.com/v1/chat/completions"
OPENAI_MODEL = "gpt-5.4-2026-03-05"
DEFAULT_MAX_COMPLETION_TOKENS = 16_384
# Flex has the same price schedule as Batch, but stays synchronous.  OpenAI's
# Flex guidance uses a fifteen-minute request timeout because this tier can be
# slower than standard processing.  The bound is still finite: an unavailable
# request blocks the episode for human adjudication instead of silently falling
# back to a different tier or holding the whole render indefinitely.
DEFAULT_TIMEOUT_SECONDS = 900
REQUIRED_SERVICE_TIER = "flex"
PROMPT_CACHE_KEY = "acc1-translation-json-v1"


class OpenAIClientError(RuntimeError):
    """Raised when an OpenAI request or response cannot be proven safe."""


class OpenAIFlexResourceUnavailableError(OpenAIClientError):
    """A confirmed HTTP 429 rejection from the explicitly requested Flex tier."""

    status_code = 429
    service_tier = REQUIRED_SERVICE_TIER


@dataclass(frozen=True)
class OpenAIUsage:
    input_tokens: int
    cached_input_tokens: int
    output_tokens: int
    total_tokens: int
    reasoning_tokens: int


@dataclass(frozen=True)
class OpenAIJSONResult:
    payload: dict[str, Any]
    usage: OpenAIUsage
    service_tier: str
    response_id: str | None = None


def _nonnegative_int(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise OpenAIClientError(f"OpenAI usage {label} must be a non-negative integer")
    return value


def _parse_usage(value: Any) -> OpenAIUsage:
    if not isinstance(value, dict):
        raise OpenAIClientError("OpenAI response is missing required token usage")
    input_tokens = _nonnegative_int(value.get("prompt_tokens"), "prompt_tokens")
    output_tokens = _nonnegative_int(value.get("completion_tokens"), "completion_tokens")
    total_tokens = _nonnegative_int(value.get("total_tokens"), "total_tokens")
    details = value.get("completion_tokens_details")
    if details is None:
        reasoning_tokens = 0
    elif isinstance(details, dict):
        reasoning_tokens = _nonnegative_int(
            details.get("reasoning_tokens", 0), "reasoning_tokens",
        )
    else:
        raise OpenAIClientError(
            "OpenAI usage completion_tokens_details must be an object"
        )
    if total_tokens != input_tokens + output_tokens:
        raise OpenAIClientError(
            "OpenAI usage total_tokens does not equal input_tokens + output_tokens"
        )
    if reasoning_tokens > output_tokens:
        raise OpenAIClientError(
            "OpenAI usage reasoning_tokens exceeds output_tokens"
        )
    input_details = value.get("prompt_tokens_details")
    if input_details is None:
        cached_input_tokens = 0
    elif isinstance(input_details, dict):
        cached_input_tokens = _nonnegative_int(
            input_details.get("cached_tokens", 0), "prompt_tokens_details.cached_tokens",
        )
    else:
        raise OpenAIClientError(
            "OpenAI usage prompt_tokens_details must be an object"
        )
    if cached_input_tokens > input_tokens:
        raise OpenAIClientError(
            "OpenAI usage cached input tokens exceed input tokens"
        )
    return OpenAIUsage(
        input_tokens=input_tokens,
        cached_input_tokens=cached_input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
        reasoning_tokens=reasoning_tokens,
    )


def _sanitize_error(value: Any, *, api_key: str) -> str:
    text = str(value or "OpenAI request failed").replace(api_key, "[REDACTED]")
    text = re.sub(r"(?i)authorization\s*:\s*bearer\s+\S+", "Authorization: [REDACTED]", text)
    text = re.sub(r"\bsk-[A-Za-z0-9_-]{8,}\b", "[REDACTED]", text)
    text = " ".join(text.split())
    return text[:800] or "OpenAI request failed"


def _http_error_message(response: requests.Response, *, api_key: str) -> str:
    message: Any = "OpenAI request failed"
    try:
        body = response.json()
        if isinstance(body, dict):
            error = body.get("error")
            if isinstance(error, dict):
                message = error.get("message") or message
    except (ValueError, TypeError):
        pass
    return _sanitize_error(message, api_key=api_key)


def _completion_limit(
    max_completion_tokens: int | None,
    max_output_tokens: int | None,
) -> int:
    if (
        max_completion_tokens is not None
        and max_output_tokens is not None
        and max_completion_tokens != max_output_tokens
    ):
        raise OpenAIClientError(
            "max_completion_tokens and max_output_tokens must match when both are set"
        )
    value = (
        max_completion_tokens
        if max_completion_tokens is not None
        else max_output_tokens
    )
    if value is None:
        value = DEFAULT_MAX_COMPLETION_TOKENS
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise OpenAIClientError("max_completion_tokens must be a positive integer")
    return value


def call_openai_json(
    *,
    prompt: str,
    model: str = OPENAI_MODEL,
    system_instruction: str = "Return strict JSON only. Do not use Markdown.",
    max_completion_tokens: int | None = None,
    max_output_tokens: int | None = None,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    retries: int = 0,
    temperature: float | None = None,
) -> OpenAIJSONResult:
    """Call the exact approved model once and parse one strict JSON object.

    ``max_output_tokens`` and ``temperature`` are accepted for compatibility
    with the repository's provider interface. The former maps to Chat
    Completions ``max_completion_tokens``; the latter is intentionally omitted
    because the approved reasoning-model contract uses ``reasoning_effort=none``.
    """
    del temperature
    if not isinstance(prompt, str) or not prompt.strip():
        raise OpenAIClientError("OpenAI prompt is required")
    if model != OPENAI_MODEL:
        raise OpenAIClientError(f"OpenAI model must be exactly {OPENAI_MODEL}")
    if isinstance(retries, bool) or retries != 0:
        raise OpenAIClientError("OpenAI automatic retries must be exactly zero")
    if isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, int) or timeout_seconds < 1:
        raise OpenAIClientError("timeout_seconds must be a positive integer")
    api_key = str(os.environ.get("OPENAI_API_KEY") or "").strip()
    if not api_key:
        raise OpenAIClientError("Missing OPENAI_API_KEY")

    request_body = {
        "model": OPENAI_MODEL,
        "messages": [
            {"role": "system", "content": system_instruction},
            {"role": "user", "content": prompt},
        ],
        "reasoning_effort": "none",
        "response_format": {"type": "json_object"},
        "max_completion_tokens": _completion_limit(
            max_completion_tokens, max_output_tokens,
        ),
        "service_tier": REQUIRED_SERVICE_TIER,
        # Prompt caching is automatic when the repeated prefix is long enough.
        # The key improves routing, but never makes a cache hit a correctness
        # dependency; actual cached tokens are recorded below.
        "prompt_cache_key": PROMPT_CACHE_KEY,
    }
    try:
        response = requests.post(
            OPENAI_CHAT_COMPLETIONS_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=request_body,
            timeout=timeout_seconds,
        )
    except requests.RequestException as exc:
        raise OpenAIClientError(
            _sanitize_error(f"OpenAI transport error: {exc}", api_key=api_key)
        ) from exc
    if not 200 <= response.status_code < 300:
        error_message = _http_error_message(response, api_key=api_key)
        full_message = f"OpenAI HTTP {response.status_code}: {error_message}"
        if (
            response.status_code == 429
            and FLEX_RESOURCE_UNAVAILABLE_MESSAGE in error_message
        ):
            raise OpenAIFlexResourceUnavailableError(full_message)
        raise OpenAIClientError(full_message)
    try:
        data = response.json()
    except ValueError as exc:
        raise OpenAIClientError("OpenAI returned invalid response JSON") from exc
    if not isinstance(data, dict):
        raise OpenAIClientError("OpenAI response must be a JSON object")
    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise OpenAIClientError("OpenAI response is missing completion content") from exc
    if not isinstance(content, str) or not content.strip():
        raise OpenAIClientError("OpenAI completion content is empty")
    try:
        payload = json.loads(content)
    except json.JSONDecodeError as exc:
        raise OpenAIClientError("OpenAI completion is not strict JSON") from exc
    if not isinstance(payload, dict):
        raise OpenAIClientError("OpenAI completion JSON must be an object")

    usage = _parse_usage(data.get("usage"))
    response_id = data.get("id")
    if response_id is not None and not isinstance(response_id, str):
        raise OpenAIClientError("OpenAI response id must be a string when present")
    service_tier = data.get("service_tier")
    if service_tier != REQUIRED_SERVICE_TIER:
        raise OpenAIClientError(
            "OpenAI did not confirm the required Flex service tier"
        )
    return OpenAIJSONResult(
        payload=payload,
        usage=usage,
        response_id=response_id or None,
        service_tier=service_tier,
    )
