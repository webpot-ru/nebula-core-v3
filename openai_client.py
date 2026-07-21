"""Minimal fail-closed OpenAI JSON client for the acc1 translation lane."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Any

import requests


OPENAI_CHAT_COMPLETIONS_URL = "https://api.openai.com/v1/chat/completions"
OPENAI_TERRA_MODEL = "gpt-5.6-terra"
OPENAI_SOL_MODEL = "gpt-5.6-sol"
OPENAI_TERRA_DAILY_TOKEN_CAP = 3_000_000
OPENAI_SOL_DAILY_TOKEN_CAP = 500_000
OPENAI_MODEL = OPENAI_TERRA_MODEL
APPROVED_OPENAI_MODELS = frozenset({OPENAI_TERRA_MODEL, OPENAI_SOL_MODEL})
DEFAULT_MAX_COMPLETION_TOKENS = 16_384
DEFAULT_TIMEOUT_SECONDS = 120


class OpenAIClientError(RuntimeError):
    """Raised when an OpenAI request or response cannot be proven safe."""


@dataclass(frozen=True)
class OpenAIUsage:
    input_tokens: int
    output_tokens: int
    total_tokens: int
    reasoning_tokens: int


@dataclass(frozen=True)
class OpenAIJSONResult:
    payload: dict[str, Any]
    usage: OpenAIUsage
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
    return OpenAIUsage(
        input_tokens=input_tokens,
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
    if model not in APPROVED_OPENAI_MODELS:
        raise OpenAIClientError(
            "OpenAI model must be one of: " + ", ".join(sorted(APPROVED_OPENAI_MODELS))
        )
    if isinstance(retries, bool) or retries != 0:
        raise OpenAIClientError("OpenAI automatic retries must be exactly zero")
    if isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, int) or timeout_seconds < 1:
        raise OpenAIClientError("timeout_seconds must be a positive integer")
    api_key = str(os.environ.get("OPENAI_API_KEY") or "").strip()
    if not api_key:
        raise OpenAIClientError("Missing OPENAI_API_KEY")

    request_body = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_instruction},
            {"role": "user", "content": prompt},
        ],
        "reasoning_effort": "none",
        "response_format": {"type": "json_object"},
        "max_completion_tokens": _completion_limit(
            max_completion_tokens, max_output_tokens,
        ),
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
        raise OpenAIClientError(
            f"OpenAI HTTP {response.status_code}: "
            f"{_http_error_message(response, api_key=api_key)}"
        )
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
    return OpenAIJSONResult(
        payload=payload,
        usage=usage,
        response_id=response_id or None,
    )
