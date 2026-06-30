#!/usr/bin/env python3
"""Read AI33 voice-library metadata without generating audio."""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Iterable
from typing import Any


VOICE_PREFIXES = ("elevenlabs_", "minimax_", "clone_", "edge_", "kokoro_")
SAFE_FIELDS = {
    "id",
    "voice_id",
    "voiceId",
    "name",
    "display_name",
    "displayName",
    "provider",
    "source",
    "category",
    "language",
    "languages",
    "language_code",
    "languageCode",
    "locale",
    "locales",
    "accent",
    "accent_code",
    "accentCode",
    "labels",
    "tags",
    "description",
    "gender",
    "age",
    "use_case",
    "useCase",
}


def raw_voice_id(voice_id: str) -> str:
    for prefix in VOICE_PREFIXES:
        if voice_id.startswith(prefix):
            return voice_id[len(prefix) :]
    return voice_id


def prefixed_voice_id(voice_id: str) -> str:
    return voice_id if voice_id.startswith(VOICE_PREFIXES) else f"elevenlabs_{voice_id}"


def request_json(url: str, headers: dict[str, str], timeout: int) -> tuple[int, Any, str]:
    request = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8", errors="replace")
            return response.status, parse_json(body), body[:300]
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        return exc.code, parse_json(body), body[:300]
    except urllib.error.URLError as exc:
        return 0, None, str(exc)[:300]


def parse_json(body: str) -> Any:
    if not body:
        return None
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        return None


def iter_dicts(value: Any) -> Iterable[dict[str, Any]]:
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from iter_dicts(child)
    elif isinstance(value, list):
        for item in value:
            yield from iter_dicts(item)


def value_contains_voice(value: Any, needles: set[str]) -> bool:
    if isinstance(value, str):
        return any(needle and needle in value for needle in needles)
    if isinstance(value, dict):
        return any(value_contains_voice(child, needles) for child in value.values())
    if isinstance(value, list):
        return any(value_contains_voice(child, needles) for child in value)
    return False


def sanitize_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): sanitize_value(v) for k, v in value.items() if str(k) in SAFE_FIELDS}
    if isinstance(value, list):
        return [sanitize_value(item) for item in value[:30]]
    if isinstance(value, str):
        compact = " ".join(value.split())
        return compact[:500]
    return value


def sanitize_voice_object(obj: dict[str, Any]) -> dict[str, Any]:
    sanitized = {str(k): sanitize_value(v) for k, v in obj.items() if str(k) in SAFE_FIELDS}
    if sanitized:
        return sanitized
    fallback: dict[str, Any] = {}
    for key, value in obj.items():
        if isinstance(value, (str, int, float, bool)) or value is None:
            fallback[str(key)] = sanitize_value(value)
        if len(fallback) >= 10:
            break
    return fallback


def auth_headers(api_key: str) -> list[tuple[str, dict[str, str]]]:
    return [
        ("xi-api-key", {"xi-api-key": api_key, "accept": "application/json"}),
        ("Authorization", {"Authorization": api_key, "accept": "application/json"}),
        ("Bearer", {"Authorization": f"Bearer {api_key}", "accept": "application/json"}),
    ]


def build_urls(base_url: str, voice_id: str, provider: str) -> list[tuple[str, str]]:
    raw = raw_voice_id(voice_id)
    prefixed = prefixed_voice_id(voice_id)
    ids = [prefixed, raw]
    urls: list[tuple[str, str]] = []
    for candidate in ids:
        quoted = urllib.parse.quote(candidate, safe="")
        provider_qs = urllib.parse.urlencode({"provider": provider})
        urls.append(
            (
                f"voices?provider={provider}&voice_id={candidate}",
                f"{base_url}/v3/voices?{provider_qs}&voice_id={quoted}",
            )
        )
        urls.append(
            (
                f"voices?provider={provider}&id={candidate}",
                f"{base_url}/v3/voices?{provider_qs}&id={quoted}",
            )
        )
        for search_param in ("search", "q", "query"):
            urls.append(
                (
                    f"voices?provider={provider}&{search_param}={candidate}",
                    f"{base_url}/v3/voices?{provider_qs}&{search_param}={quoted}",
                )
            )
    return urls


def build_list_urls(base_url: str, provider: str) -> list[tuple[str, str]]:
    provider_qs = urllib.parse.urlencode({"provider": provider, "page_size": "100"})
    return [
        (f"voices?provider={provider}", f"{base_url}/v3/voices?{provider_qs}"),
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--voice-id", action="append", required=True, help="Raw or AI33-prefixed voice id.")
    parser.add_argument("--base-url", default=os.environ.get("AI33_API_BASE", "https://api.ai33.pro"))
    parser.add_argument("--api-key-env", default="AI33_API_KEY")
    parser.add_argument("--provider", default="elevenlabs")
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--include-list-endpoints", action="store_true")
    args = parser.parse_args()

    api_key = os.environ.get(args.api_key_env)
    if not api_key:
        print(f"Missing {args.api_key_env}", file=sys.stderr)
        return 2

    base_url = args.base_url.rstrip("/")
    voice_ids = [voice_id.strip() for voice_id in args.voice_id if voice_id.strip()]
    needles = set()
    for voice_id in voice_ids:
        needles.add(raw_voice_id(voice_id))
        needles.add(prefixed_voice_id(voice_id))

    results: dict[str, Any] = {
        "base_url": base_url,
        "requested_voice_ids": voice_ids,
        "matches": [],
        "http_statuses": [],
    }
    seen_matches: set[str] = set()
    successful_auth_modes: set[str] = set()

    targets: list[tuple[str, str]] = []
    for voice_id in voice_ids:
        targets.extend(build_urls(base_url, voice_id, args.provider))
    if args.include_list_endpoints:
        targets.extend(build_list_urls(base_url, args.provider))

    for auth_name, headers in auth_headers(api_key):
        for label, url in targets:
            status, payload, body_excerpt = request_json(url, headers=headers, timeout=args.timeout)
            status_record = {"auth": auth_name, "endpoint": label, "status": status}
            if status == 0:
                status_record["error"] = body_excerpt
            results["http_statuses"].append(status_record)
            if 200 <= status < 300:
                successful_auth_modes.add(auth_name)
            if payload is None:
                continue

            matched = False
            for obj in iter_dicts(payload):
                if not value_contains_voice(obj, needles):
                    continue
                sanitized = sanitize_voice_object(obj)
                key = json.dumps(sanitized, sort_keys=True, ensure_ascii=True)
                if key in seen_matches:
                    continue
                seen_matches.add(key)
                results["matches"].append(
                    {
                        "auth": auth_name,
                        "endpoint": label,
                        "metadata": sanitized,
                    }
                )
                matched = True

            if not matched and 200 <= status < 300 and not label in {"voices", "voice-library"}:
                if isinstance(payload, dict):
                    sanitized = sanitize_voice_object(payload)
                    key = json.dumps(sanitized, sort_keys=True, ensure_ascii=True)
                    if key not in seen_matches:
                        seen_matches.add(key)
                        results["matches"].append(
                            {
                                "auth": auth_name,
                                "endpoint": label,
                                "metadata": sanitized,
                                "note": "Detail endpoint returned 2xx but no exact voice id string was found in the sanitized payload.",
                            }
                        )

    results["successful_auth_modes"] = sorted(successful_auth_modes)
    print(json.dumps(results, ensure_ascii=False, indent=2, sort_keys=True))

    if not successful_auth_modes:
        print("No AI33 voice metadata endpoint accepted the configured API key.", file=sys.stderr)
        return 3
    if not results["matches"]:
        print("AI33 voice metadata endpoints were reachable, but no matching voice metadata was found.", file=sys.stderr)
        return 4
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
