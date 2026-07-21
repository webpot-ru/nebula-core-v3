"""Fail-closed local contract for the acc1 AI33 pronunciation dictionary."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
SPEC_PATH = ROOT / "specs/acc1-pronunciation-dictionary-v1.json"
DICTIONARY_ID_ENV = "AI33_PRONUNCIATION_DICTIONARY_ID"


class PronunciationDictionaryError(RuntimeError):
    """The local or remote pronunciation-dictionary binding is invalid."""


def canonical_hash(value: object) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def load_acc1_pronunciation_dictionary() -> dict[str, Any]:
    try:
        spec = json.loads(SPEC_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PronunciationDictionaryError("acc1 pronunciation dictionary is unreadable") from exc
    if spec.get("version") != 1 or spec.get("channel") != "acc1":
        raise PronunciationDictionaryError("acc1 pronunciation dictionary contract is incompatible")
    if not str(spec.get("name") or "").strip() or spec.get("language") != "ru-RU":
        raise PronunciationDictionaryError("acc1 pronunciation dictionary metadata is invalid")
    rules = spec.get("rules")
    if not isinstance(rules, list) or not rules:
        raise PronunciationDictionaryError("acc1 pronunciation dictionary requires rules")
    seen: set[tuple[str, bool]] = set()
    for rule in rules:
        if not isinstance(rule, dict):
            raise PronunciationDictionaryError("pronunciation dictionary rule must be an object")
        source = str(rule.get("from") or "")
        replacement = str(rule.get("to") or "")
        match_type = rule.get("matchType")
        case_sensitive = rule.get("caseSensitive")
        if not source.strip() or not replacement.strip():
            raise PronunciationDictionaryError("pronunciation dictionary rule cannot be empty")
        if match_type not in {"word", "contains"} or not isinstance(case_sensitive, bool):
            raise PronunciationDictionaryError("pronunciation dictionary rule options are invalid")
        identity = (source if case_sensitive else source.casefold(), case_sensitive)
        if identity in seen:
            raise PronunciationDictionaryError("pronunciation dictionary contains a duplicate source")
        seen.add(identity)
    return {**spec, "sha256": canonical_hash(spec)}


def resolve_acc1_pronunciation_dictionary_id(*, required: bool) -> int | None:
    raw = str(os.environ.get(DICTIONARY_ID_ENV) or "").strip()
    if not raw:
        if required:
            raise PronunciationDictionaryError(f"{DICTIONARY_ID_ENV} is required for new acc1 TTS submissions")
        return None
    try:
        value = int(raw)
    except ValueError as exc:
        raise PronunciationDictionaryError(f"{DICTIONARY_ID_ENV} must be a positive integer") from exc
    if value <= 0:
        raise PronunciationDictionaryError(f"{DICTIONARY_ID_ENV} must be a positive integer")
    return value


def preview_pronunciation(text: str, rules: list[dict[str, Any]]) -> str:
    """Apply the documented AI33 word/contains semantics for a no-network preview."""
    import re

    result = str(text)
    for rule in rules:
        flags = 0 if rule["caseSensitive"] else re.IGNORECASE
        source = re.escape(rule["from"])
        pattern = rf"(?<!\w){source}(?!\w)" if rule["matchType"] == "word" else source
        result = re.sub(pattern, lambda _match, value=rule["to"]: value, result, flags=flags)
    return result
