"""Prepare deterministic Russian narration segments before any AI33 request."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from translator_tts import clean_text_for_narration_and_karaoke


RISKY_NUMBER_PATTERNS = (
    ("clock_time", re.compile(r"(?<!\w)\d{1,2}:\d{2}(?!\w)")),
    ("decimal", re.compile(r"(?<!\w)\d+[.,]\d+(?!\w)")),
    ("currency", re.compile(r"(?:[$€£₽]\s?\d|\d\s?(?:руб(?:\.|лей)?|доллар(?:ов|а)?|евро))", re.I)),
    ("date", re.compile(r"(?<!\w)\d{1,2}[./-]\d{1,2}[./-]\d{2,4}(?!\w)")),
    ("contextual_year", re.compile(r"(?<!\w)(?:19|20)\d{2}\s+(?:году|год|г\.)", re.I)),
)


class NarrationPreflightError(RuntimeError):
    pass


def narration_preflight(text: str) -> dict[str, Any]:
    original = str(text or "")
    cleaned, changes = clean_text_for_narration_and_karaoke(text, "ru")
    issues: list[dict[str, str]] = []
    if re.search(r"(?i)https?://|www\.", cleaned):
        issues.append({"kind": "raw_url", "token": "URL"})
    for kind, pattern in RISKY_NUMBER_PATTERNS:
        for match in pattern.finditer(original):
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
