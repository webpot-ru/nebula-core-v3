"""Prepare deterministic Russian narration segments before any AI33 request."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from acc1_episode_contract import truth_disclosure_ru
from acc1_episode_manifest import EpisodeManifestError, disclosure_for_truth_mode
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


def truth_disclosure_text(story: dict[str, Any]) -> str:
    """Return the exact audible/metadata disclosure for one Reddit source."""

    snapshot = story.get("source_snapshot") if isinstance(story, dict) else None
    if not isinstance(snapshot, dict):
        raise NarrationPreflightError("story source_snapshot is required for truth disclosure")
    post_id = str(snapshot.get("source_id") or snapshot.get("post_id") or "").strip()
    if not post_id:
        raise NarrationPreflightError("story source_snapshot.post_id is required")
    try:
        return disclosure_for_truth_mode(str(snapshot.get("truth_mode") or ""))
    except EpisodeManifestError as exc:
        raise NarrationPreflightError(f"story {post_id} has no valid truth_mode") from exc


def episode_truth_disclosure(compilation: dict[str, Any]) -> dict[str, str]:
    """Validate one exact truth mode and one intro disclosure per episode."""

    stories = compilation.get("stories")
    if not isinstance(stories, list) or not stories:
        raise NarrationPreflightError("episode requires at least one source for truth disclosure")
    modes: set[str] = set()
    for story in stories:
        snapshot = story.get("source_snapshot") if isinstance(story, dict) else None
        if not isinstance(snapshot, dict):
            raise NarrationPreflightError("story source_snapshot is required for truth disclosure")
        mode = str(snapshot.get("truth_mode") or "").strip()
        try:
            disclosure_for_truth_mode(mode)
        except EpisodeManifestError as exc:
            post_id = str(snapshot.get("source_id") or snapshot.get("post_id") or "unknown")
            raise NarrationPreflightError(f"story {post_id} has no valid truth_mode") from exc
        modes.add(mode)
    if len(modes) != 1:
        raise NarrationPreflightError(
            "one episode must not mix fiction and unverified personal accounts"
        )
    truth_mode = next(iter(modes))
    expected = truth_disclosure_ru(modes, source_count=len(stories))
    declared = " ".join(str(compilation.get("truth_disclosure_ru") or "").split())
    if declared != expected:
        raise NarrationPreflightError(
            "truth_disclosure_ru must exactly match the episode truth_mode"
        )
    intro = " ".join(str(compilation.get("intro_ru") or "").split())
    all_parts = [intro]
    for story in stories:
        all_parts.append(" ".join(str(story.get("narration_ru") or "").split()))
        all_parts.append(" ".join(str(story.get("transition_after_ru") or "").split()))
    all_parts.append(" ".join(str(compilation.get("outro_ru") or "").split()))
    if intro.count(expected) != 1:
        raise NarrationPreflightError(
            "truth disclosure must appear exactly once in intro_ru"
        )
    if " ".join(all_parts).count(expected) != 1:
        raise NarrationPreflightError(
            "truth disclosure must appear exactly once per episode"
        )
    return {"truth_mode": truth_mode, "text": expected}


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
    disclosure = episode_truth_disclosure(compilation)
    ordered: list[dict[str, Any]] = [{
        "segment_id": "intro",
        "kind": "intro",
        "voice_role": "narrator",
        "truth_mode": disclosure["truth_mode"],
        "truth_disclosure_text": disclosure["text"],
        "text": str(compilation.get("intro_ru") or ""),
    }]
    stories = compilation.get("stories") or []
    for index, story in enumerate(stories, start=1):
        snapshot = story.get("source_snapshot") if isinstance(story, dict) else {}
        post_id = str(
            (snapshot or {}).get("source_id") or (snapshot or {}).get("post_id") or index
        )
        voice_role = str(story.get("narration_role") or "narrator").strip().lower()
        if voice_role not in {"narrator", "comment"}:
            raise NarrationPreflightError(
                f"story {post_id} narration_role must be narrator or comment"
            )
        ordered.append({
            "segment_id": f"story_{post_id}",
            "kind": "story",
            "voice_role": voice_role,
            "source_post_id": post_id,
            "text": str(story.get("narration_ru") or ""),
        })
        if index < len(stories):
            ordered.append({
                "segment_id": f"transition_{index:02d}",
                "kind": "transition",
                "voice_role": "narrator",
                "text": str(story.get("transition_after_ru") or ""),
            })
    ordered.append({
        "segment_id": "outro",
        "kind": "outro",
        "voice_role": "narrator",
        "text": str(compilation.get("outro_ru") or ""),
    })

    segments: list[dict[str, Any]] = []
    for item in ordered:
        segment_id = item["segment_id"]
        text = item["text"]
        if not text.strip():
            if segment_id.startswith("transition_"):
                continue
            raise NarrationPreflightError(f"{segment_id} narration is empty")
        result = narration_preflight(text)
        if result["status"] != "PASS":
            kinds = ", ".join(item["kind"] for item in result["issues"])
            raise NarrationPreflightError(f"{segment_id} narration needs explicit spoken forms: {kinds}")
        sanitized = result["narration_text"]
        segment = {
            "segment_id": segment_id,
            "kind": item["kind"],
            "voice_role": item["voice_role"],
            "text": sanitized,
            "text_sha256": hashlib.sha256(sanitized.encode("utf-8")).hexdigest(),
            "required_model_id": "eleven_v3",
            "status": "READY_FOR_TTS",
        }
        for field in ("source_post_id", "truth_mode", "truth_disclosure_text"):
            if field in item:
                segment[field] = item[field]
        segments.append(segment)
    return segments


def manifest_hash(segments: list[dict[str, Any]]) -> str:
    value = json.dumps(segments, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
