"""Canonical identity for paid provider requests persisted in call journals."""

from __future__ import annotations

import hashlib
import json
from typing import Any


def provider_request_sha256(
    *,
    prompt: str,
    model: Any,
    max_output_tokens: Any = None,
    voice_id: Any = None,
    service_tier: Any = None,
) -> str:
    """Hash the stable paid-request fields shared by journals and resumable stages."""
    payload = {
        "prompt": str(prompt or ""),
        "model": model,
        "max_output_tokens": max_output_tokens,
        "voice_id": voice_id,
        "service_tier": service_tier,
    }
    return hashlib.sha256(json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")).hexdigest()
