#!/usr/bin/env python3
"""Create or reuse the checksum-bound acc1 pronunciation dictionary in AI33."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

import requests

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from acc1_pronunciation_dictionary import load_acc1_pronunciation_dictionary


BASE_URL = "https://api.ai33.pro/v3/dictionaries"


class DictionarySetupError(RuntimeError):
    """Remote dictionary state is unsafe or incompatible."""


def _json_response(response: requests.Response, action: str) -> dict[str, Any]:
    try:
        payload = response.json()
    except ValueError as exc:
        raise DictionarySetupError(f"AI33 {action} returned non-JSON HTTP {response.status_code}") from exc
    if not response.ok or not isinstance(payload, dict) or payload.get("success") is False:
        raise DictionarySetupError(f"AI33 {action} failed with HTTP {response.status_code}")
    return payload


def _dictionary_items(payload: dict[str, Any]) -> list[dict[str, Any]]:
    candidates: Any = payload.get("dictionaries")
    if candidates is None and isinstance(payload.get("data"), dict):
        candidates = payload["data"].get("dictionaries") or payload["data"].get("items")
    if candidates is None:
        candidates = payload.get("items") or payload.get("data")
    if not isinstance(candidates, list):
        raise DictionarySetupError("AI33 dictionary list has an unsupported shape")
    return [item for item in candidates if isinstance(item, dict)]


def _normalized_rules(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [{
        "from": str(item.get("from") or ""),
        "to": str(item.get("to") or ""),
        "matchType": str(item.get("matchType") or "word"),
        "caseSensitive": bool(item.get("caseSensitive", False)),
    } for item in value if isinstance(item, dict)]


def configure(*, api_key: str, output_path: Path, apply: bool) -> dict[str, Any]:
    spec = load_acc1_pronunciation_dictionary()
    public_spec = {key: spec[key] for key in ("name", "rules")}
    if not apply:
        result = {
            "status": "DRY_RUN",
            "would_call_ai33": False,
            "dictionary_name": spec["name"],
            "dictionary_sha256": spec["sha256"],
        }
    else:
        if not api_key:
            raise DictionarySetupError("AI33_API_KEY is required")
        headers = {"xi-api-key": api_key}
        listed = _json_response(
            requests.get(BASE_URL, headers=headers, timeout=60), "dictionary list",
        )
        same_name = [item for item in _dictionary_items(listed) if item.get("name") == spec["name"]]
        matching = [item for item in same_name if _normalized_rules(item.get("rules")) == spec["rules"]]
        if len(matching) > 1:
            raise DictionarySetupError("multiple identical AI33 dictionaries exist; refusing ambiguity")
        if same_name and not matching:
            raise DictionarySetupError("AI33 dictionary name exists with different rules")
        created = False
        if matching:
            dictionary = matching[0]
        else:
            payload = _json_response(
                requests.post(BASE_URL, headers={**headers, "Content-Type": "application/json"}, json=public_spec, timeout=60),
                "dictionary create",
            )
            dictionary = payload.get("dictionary")
            if not isinstance(dictionary, dict):
                raise DictionarySetupError("AI33 create response has no dictionary object")
            created = True
        try:
            dictionary_id = int(dictionary.get("id"))
        except (TypeError, ValueError) as exc:
            raise DictionarySetupError("AI33 dictionary has no positive integer id") from exc
        if dictionary_id <= 0:
            raise DictionarySetupError("AI33 dictionary has no positive integer id")
        readback = _json_response(
            requests.get(f"{BASE_URL}/{dictionary_id}", headers=headers, timeout=60),
            "dictionary readback",
        )
        remote = readback.get("dictionary") or readback.get("data")
        if not isinstance(remote, dict):
            raise DictionarySetupError("AI33 dictionary readback has an unsupported shape")
        if remote.get("name") != spec["name"] or _normalized_rules(remote.get("rules")) != spec["rules"]:
            raise DictionarySetupError("AI33 dictionary readback does not match the local contract")
        result = {
            "status": "CREATED" if created else "REUSED",
            "dictionary_id": dictionary_id,
            "dictionary_name": spec["name"],
            "dictionary_sha256": spec["sha256"],
            "readback_verified": True,
            "publication_authorized": False,
            "youtube_called": False,
        }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm-create", action="store_true")
    args = parser.parse_args()
    if args.apply and not args.confirm_create:
        raise DictionarySetupError("--apply requires --confirm-create")
    result = configure(
        api_key=str(os.environ.get("AI33_API_KEY") or ""),
        output_path=Path(args.output),
        apply=args.apply,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
