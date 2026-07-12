"""Prepare deterministic Russian narration segments before any AI33 request."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from translator_tts import (
    clean_text_for_narration_and_karaoke, ru_int_to_words, ru_plural_form,
)


RISKY_NUMBER_PATTERNS = (
    ("clock_time", re.compile(r"(?<!\w)\d{1,2}:\d{2}(?!\w)")),
    ("decimal", re.compile(r"(?<!\w)\d+[.,]\d+(?!\w)")),
    ("currency", re.compile(r"(?:[$€£₽]\s?\d|\d\s?(?:руб(?:\.|лей)?|доллар(?:ов|а)?|евро))", re.I)),
    ("date", re.compile(r"(?<!\w)\d{1,2}[./-]\d{1,2}[./-]\d{2,4}(?!\w)")),
    ("contextual_year", re.compile(r"(?<!\w)(?:19|20)\d{2}\s+(?:году|год|г\.)", re.I)),
)


class NarrationPreflightError(RuntimeError):
    pass


def normalize_ru_clock_times(text: str) -> tuple[str, int]:
    changes = 0

    def replace(match: re.Match[str]) -> str:
        nonlocal changes
        hour, minute = int(match.group(1)), int(match.group(2))
        if hour > 23 or minute > 59:
            return match.group(0)
        changes += 1
        hour_words = ru_int_to_words(hour)
        hour_unit = ru_plural_form(hour, ("час", "часа", "часов"))
        if minute == 0:
            return f"{hour_words} {hour_unit} ровно"
        minute_words = ru_int_to_words(minute)
        minute_unit = ru_plural_form(minute, ("минута", "минуты", "минут"))
        return f"{hour_words} {hour_unit} {minute_words} {minute_unit}"

    pattern = re.compile(r"(?<!\w)(\d{1,2}):(\d{2})(?!\w)")
    return pattern.sub(replace, str(text or "")), changes


def narration_preflight(text: str) -> dict[str, Any]:
    original = str(text or "")
    clock_safe, clock_changes = normalize_ru_clock_times(original)
    cleaned, changes = clean_text_for_narration_and_karaoke(clock_safe, "ru")
    changes += clock_changes
    issues: list[dict[str, str]] = []
    if re.search(r"(?i)https?://|www\.", cleaned):
        issues.append({"kind": "raw_url", "token": "URL"})
    for kind, pattern in RISKY_NUMBER_PATTERNS:
        for match in pattern.finditer(clock_safe):
            issues.append({"kind": kind, "token": match.group(0)[:80]})
    return {
        "status": "PASS" if not issues else "BLOCKED",
        "narration_text": cleaned,
        "sanitization_changes": changes,
        "issues": issues,
    }


def build_compilation_segments(compilation: dict[str, Any]) -> list[dict[str, Any]]:
    ordered: list[tuple[str, str]] = [("intro", str(compilation.get("intro_ru") or ""))]
    stories = compilation.get("stories") or []
    for index, story in enumerate(stories, start=1):
        snapshot = story.get("source_snapshot") if isinstance(story, dict) else {}
        post_id = str((snapshot or {}).get("post_id") or index)
        ordered.append((f"story_{post_id}", str(story.get("narration_ru") or "")))
        if index < len(stories):
            ordered.append((f"transition_{index:02d}", str(story.get("transition_after_ru") or "")))
    ordered.append(("outro", str(compilation.get("outro_ru") or "")))

    segments: list[dict[str, Any]] = []
    for segment_id, text in ordered:
        if not text.strip():
            if segment_id.startswith("transition_"):
                continue
            raise NarrationPreflightError(f"{segment_id} narration is empty")
        result = narration_preflight(text)
        if result["status"] != "PASS":
            kinds = ", ".join(item["kind"] for item in result["issues"])
            raise NarrationPreflightError(f"{segment_id} narration needs explicit spoken forms: {kinds}")
        sanitized = result["narration_text"]
        segments.append({
            "segment_id": segment_id,
            "text": sanitized,
            "text_sha256": hashlib.sha256(sanitized.encode("utf-8")).hexdigest(),
            "required_model_id": "eleven_v3",
            "status": "READY_FOR_TTS",
        })
    return segments


def manifest_hash(segments: list[dict[str, Any]]) -> str:
    value = json.dumps(segments, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
