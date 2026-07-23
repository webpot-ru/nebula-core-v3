"""Prepare deterministic Russian narration segments before any AI33 request."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from acc1_narration_profiles import (
    NarrationProfileError,
    resolve_narration_profile,
)
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
    (
        "contextual_year",
        re.compile(r"(?<!\w)(?:19|20)\d{2}\s+(?:году|год(?![а-яё])|г\.)", re.I),
    ),
)


class NarrationPreflightError(RuntimeError):
    pass


def resolve_compilation_narration_profile(
    compilation: dict[str, Any],
    narration_profile_id: str | None = None,
) -> dict[str, Any] | None:
    """Resolve an explicit/declared profile without changing the legacy path."""

    declared = str(compilation.get("narration_profile_id") or "").strip()
    explicit = str(narration_profile_id or "").strip()
    if declared and explicit and declared != explicit:
        raise NarrationPreflightError(
            "narration_profile_id argument does not match the compilation declaration"
        )
    selected = explicit or declared
    if not selected:
        return None
    try:
        return resolve_narration_profile(
            selected,
            pillar_id=compilation.get("pillar"),
        )
    except NarrationProfileError as exc:
        raise NarrationPreflightError(str(exc)) from exc


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


def normalize_ru_emergency_numbers(text: str) -> tuple[str, int]:
    """Make the Russian emergency number unambiguous for TTS."""

    normalized, count = re.subn(
        r"(?<!\d)911(?!\d)", "девять один один", str(text or ""),
    )
    return normalized, count


def narration_preflight(text: str) -> dict[str, Any]:
    original = str(text or "")
    clock_safe, clock_changes = normalize_ru_clock_times(original)
    emergency_safe, emergency_changes = normalize_ru_emergency_numbers(clock_safe)
    cleaned, changes = clean_text_for_narration_and_karaoke(emergency_safe, "ru")
    changes += clock_changes + emergency_changes
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


def _canonical_text(value: object) -> str:
    return " ".join(str(value or "").split())


def _semantic_units(
    *,
    segment_id: str,
    sanitized_text: str,
    explicit_beats: Any = None,
    max_chars: int | None = None,
) -> list[dict[str, Any]]:
    units: list[str] = []
    boundary_source = "whole_segment"
    if explicit_beats:
        if not isinstance(explicit_beats, list):
            raise NarrationPreflightError(
                f"{segment_id} explicit story beats must be a list"
            )
        for index, item in enumerate(explicit_beats, start=1):
            if isinstance(item, str):
                raw_text = item
            elif isinstance(item, dict):
                raw_text = str(
                    item.get("narration_text")
                    or item.get("text")
                    or item.get("body")
                    or ""
                )
            else:
                raise NarrationPreflightError(
                    f"{segment_id} story beat {index} must contain narration text"
                )
            result = narration_preflight(raw_text)
            if result["status"] != "PASS" or not result["narration_text"].strip():
                raise NarrationPreflightError(
                    f"{segment_id} story beat {index} is not narration-safe"
                )
            units.append(result["narration_text"].strip())
        if _canonical_text(" ".join(units)) != _canonical_text(sanitized_text):
            raise NarrationPreflightError(
                f"{segment_id} explicit story beats must preserve exact sanitized narration"
            )
        boundary_source = "explicit_story_beat"
    else:
        paragraphs = [
            value.strip()
            for value in re.split(r"\n\s*\n+", sanitized_text)
            if value.strip()
        ]
        if len(paragraphs) > 1:
            boundary_source = "paragraph"
        if not paragraphs:
            paragraphs = [sanitized_text.strip()]
        if max_chars is None:
            units = paragraphs
        else:
            if max_chars < 1:
                raise NarrationPreflightError("semantic max_chars must be positive")
            units = []
            current: list[str] = []
            for paragraph in paragraphs:
                candidate = "\n\n".join([*current, paragraph])
                if current and len(candidate) > max_chars:
                    units.append("\n\n".join(current))
                    current = [paragraph]
                else:
                    current.append(paragraph)
            if current:
                units.append("\n\n".join(current))

    return [
        {
            "semantic_beat_id": f"{segment_id}__beat_{index:03d}",
            "semantic_beat_index": index,
            "boundary_source": boundary_source,
            "text": text,
            "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        }
        for index, text in enumerate(units, start=1)
    ]


def build_compilation_segments(
    compilation: dict[str, Any],
    narration_profile_id: str | None = None,
) -> list[dict[str, Any]]:
    profile = resolve_compilation_narration_profile(
        compilation, narration_profile_id,
    )
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
    mid_story_cta = str(compilation.get("mid_story_cta_ru") or "").strip()
    mid_story_cta_after = max(1, len(stories) // 2) if mid_story_cta and stories else 0
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
            "_explicit_beats": story.get("story_beats") or story.get("beats"),
        })
        if index < len(stories):
            ordered.append({
                "segment_id": f"transition_{index:02d}",
                "kind": "transition",
                "voice_role": "narrator",
                "text": str(story.get("transition_after_ru") or ""),
            })
        if index == mid_story_cta_after:
            ordered.append({
                "segment_id": "mid_story_cta",
                "kind": "mid_story_cta",
                "voice_role": "narrator",
                "text": mid_story_cta,
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
        if profile is not None:
            segment["narration_profile_id"] = profile["profile_id"]
            segment["narration_profile_sha256"] = profile["profile_sha256"]
            segment["semantic_chunk_policy"] = profile["semantic_chunk_policy"]
            segment["semantic_units"] = _semantic_units(
                segment_id=segment_id,
                sanitized_text=sanitized,
                explicit_beats=item.get("_explicit_beats"),
                max_chars=int(profile["semantic_chunk_policy"]["max_chars"]),
            )
        segments.append(segment)
    return segments


def manifest_hash(segments: list[dict[str, Any]]) -> str:
    value = json.dumps(segments, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
