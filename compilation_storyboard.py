"""Build a deterministic, local-asset storyboard for an acc1 compilation.

Version 2 storyboards turn the accepted narration into short, cumulative Reddit
pages.  ``narration_text`` contains only the words spoken during a slide while
``display_text`` contains the stable text already revealed on the current page.
That distinction lets QA prove narration coverage without counting the repeated
on-screen context.

Incomplete/legacy compilation objects still receive the original static slide
shape so existing artifact inspection remains possible.  Publication QA is
responsible for rejecting that legacy mode.
"""

from __future__ import annotations

from pathlib import Path
import argparse
import hashlib
import json
import math
import re
from typing import Any

from acc1_visual_contract import (
    CONTRACT_VERSION as VISUAL_CONTRACT_VERSION,
    MAX_VISUAL_SCENES,
    MIN_VISUAL_SCENES,
    MASCOT_SAFE_X,
    READABILITY_SHADE_ALPHA,
    STORY_VISUAL_BRIGHTNESS,
    STORY_VISUAL_FEATHER_END_X,
    STORY_VISUAL_FEATHER_START_X,
    TEXT_LEFT_X,
    TEXT_RIGHT_X,
    WORDS_PER_VISUAL_SCENE,
)
from compilation_narration import (
    NarrationPreflightError,
    build_compilation_segments,
    narration_preflight,
)


MAX_CHUNK_WORDS = 22
FIRST_PAGE_WORDS = 48
FIRST_PAGE_CHARS = 340
CONTINUATION_PAGE_WORDS = 62
CONTINUATION_PAGE_CHARS = 440
TIMING_CONTRACT_VERSION = 1
ALLOWED_VIDEO_SUFFIXES = {".mp4", ".mov", ".m4v", ".webm"}
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class CompilationStoryboardError(RuntimeError):
    pass


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _normalized_text(text: str) -> str:
    return " ".join(str(text or "").split())


def _canonical_hash(value: Any) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _spoken_text(text: str) -> str:
    value = str(text or "")
    if not value.strip():
        return ""
    result = narration_preflight(value)
    if result["status"] != "PASS":
        kinds = ", ".join(str(item.get("kind") or "unknown") for item in result.get("issues") or [])
        raise CompilationStoryboardError(f"narration is not safe for timed text: {kinds}")
    return _normalized_text(result["narration_text"])


def narration_text(compilation: dict[str, Any]) -> str:
    """Return the exact role-aware narration accepted by the TTS planner."""
    try:
        segments = build_compilation_segments(compilation)
    except NarrationPreflightError as exc:
        raise CompilationStoryboardError(str(exc)) from exc
    return _normalized_text(" ".join(item["text"] for item in segments))


def narration_sha256(compilation: dict[str, Any]) -> str:
    return hashlib.sha256(narration_text(compilation).encode("utf-8")).hexdigest()


def _path_under_root(raw_path: str | Path, artifact_root: Path, *, label: str) -> Path:
    root = artifact_root.resolve()
    candidate = Path(raw_path).expanduser()
    path = candidate.resolve() if candidate.is_absolute() else (root / candidate).resolve()
    if path == root or root not in path.parents or not path.is_file():
        raise CompilationStoryboardError(f"{label} must be an existing file under artifact_root")
    return path


def _verified_local_images(story: dict[str, Any], artifact_root: Path) -> list[dict[str, Any]]:
    images: list[dict[str, Any]] = []
    snapshot = story.get("source_snapshot") or {}
    for asset in list(snapshot.get("source_media") or []) + list(story.get("generated_media") or []):
        if not isinstance(asset, dict) or asset.get("download_status") != "verified":
            continue
        raw_path = str(asset.get("artifact_path") or asset.get("local_path") or "")
        if not raw_path:
            continue
        path = _path_under_root(raw_path, artifact_root, label="source image")
        images.append({
            "kind": "source_image",
            "local_path": path.relative_to(artifact_root.resolve()).as_posix(),
            "fit": "cover",
            "caption": str(asset.get("caption") or ""),
            "sha256": str(asset.get("sha256") or _sha256(path)),
        })
    return images


def _verified_background_video(raw_path: str | Path, artifact_root: Path) -> dict[str, Any]:
    path = _path_under_root(raw_path, artifact_root, label="background video")
    if path.suffix.casefold() not in ALLOWED_VIDEO_SUFFIXES:
        raise CompilationStoryboardError("background video must be mp4, mov, m4v, or webm")
    return {
        "kind": "background_video",
        "local_path": path.relative_to(artifact_root.resolve()).as_posix(),
        "sha256": _sha256(path),
        "loop": True,
        "audio_policy": "discard",
    }


def _complete_narration(compilation: dict[str, Any]) -> bool:
    stories = compilation.get("stories") or []
    return bool(
        str(compilation.get("intro_ru") or "").strip()
        and str(compilation.get("outro_ru") or "").strip()
        and stories
        and all(isinstance(story, dict) and str(story.get("narration_ru") or "").strip() for story in stories)
    )


def _split_long_words(text: str, limit: int = MAX_CHUNK_WORDS) -> list[str]:
    clauses = [item.strip() for item in re.split(r"(?<=[,;:—])\s+", text) if item.strip()]
    result: list[str] = []
    pending: list[str] = []
    for clause in clauses or [text]:
        words = clause.split()
        if len(words) > limit:
            if pending:
                result.append(" ".join(pending))
                pending = []
            result.extend(" ".join(words[index:index + limit]) for index in range(0, len(words), limit))
            continue
        if pending and len(pending) + len(words) > limit:
            result.append(" ".join(pending))
            pending = []
        pending.extend(words)
    if pending:
        result.append(" ".join(pending))
    return result


def _exact_story_beats(story: dict[str, Any], spoken_narration: str) -> list[str] | None:
    raw_beats = story.get("story_beats") or story.get("beats")
    if not isinstance(raw_beats, list) or not raw_beats:
        return None
    beats: list[str] = []
    for item in raw_beats:
        if isinstance(item, str):
            value = item
        elif isinstance(item, dict):
            value = str(item.get("narration_text") or item.get("text") or item.get("body") or "")
        else:
            return None
        spoken = _spoken_text(value)
        if not spoken:
            return None
        beats.append(spoken)
    return beats if _normalized_text(" ".join(beats)) == _normalized_text(spoken_narration) else None


def _timed_chunks(text: str, *, exact_beats: list[str] | None = None) -> list[tuple[int, str]]:
    """Split exact narration deterministically while retaining paragraph beats."""
    normalized = str(text or "").strip()
    if not normalized:
        return []
    paragraphs = exact_beats or [item.strip() for item in re.split(r"\n\s*\n+", normalized) if item.strip()]
    if not paragraphs:
        paragraphs = [normalized]
    result: list[tuple[int, str]] = []
    for beat_index, paragraph in enumerate(paragraphs, start=1):
        sentences = [item.strip() for item in re.split(r"(?<=[.!?…])\s+", paragraph) if item.strip()]
        if not sentences:
            sentences = [paragraph]
        pending: list[str] = []
        for sentence in sentences:
            sentence_words = sentence.split()
            if len(sentence_words) > MAX_CHUNK_WORDS:
                if pending:
                    result.append((beat_index, " ".join(pending)))
                    pending = []
                result.extend((beat_index, item) for item in _split_long_words(sentence))
                continue
            if pending and len(pending) + len(sentence_words) > MAX_CHUNK_WORDS:
                result.append((beat_index, " ".join(pending)))
                pending = []
            pending.extend(sentence_words)
        if pending:
            result.append((beat_index, " ".join(pending)))
    return result


def reddit_page_text_states(
    text: str, *, exact_beats: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Return the canonical cumulative text states used by Reddit pages.

    This is intentionally timing- and asset-free so the exact production page
    sequence can be measured before image generation or TTS spend.  The timed
    storyboard builder below consumes the same states instead of maintaining a
    second pagination implementation.
    """
    chunks = _timed_chunks(text, exact_beats=exact_beats)
    states: list[dict[str, Any]] = []
    page_index = 1
    page_chunks: list[str] = []
    page_words = 0
    page_chars = 0
    for chunk_index, (beat_index, chunk) in enumerate(chunks):
        chunk_words = len(chunk.split())
        chunk_chars = len(chunk)
        word_limit = FIRST_PAGE_WORDS if page_index == 1 else CONTINUATION_PAGE_WORDS
        char_limit = FIRST_PAGE_CHARS if page_index == 1 else CONTINUATION_PAGE_CHARS
        if page_chunks and (
            page_words + chunk_words > word_limit
            or page_chars + chunk_chars + 1 > char_limit
        ):
            page_index += 1
            page_chunks = []
            page_words = 0
            page_chars = 0
        page_chunks.append(chunk)
        page_words += chunk_words
        page_chars += chunk_chars + (1 if len(page_chunks) > 1 else 0)
        states.append({
            "chunk_index": chunk_index,
            "beat_index": beat_index,
            "page_index": page_index,
            "page_step": len(page_chunks),
            "display_text": _normalized_text(" ".join(page_chunks)),
            "narration_text": _normalized_text(chunk),
        })
    return states


def compilation_text_layout_states(compilation: dict[str, Any]) -> list[dict[str, Any]]:
    """Build every production Reddit-page text state without TTS or media.

    The returned slide-shaped dictionaries carry the same title, presentation,
    cumulative body text, source line and final-action state as the eventual
    version-2 storyboard.  They are the pre-spend input to the renderer's exact
    pixel geometry gate.
    """
    try:
        narration_segments = build_compilation_segments(compilation)
    except NarrationPreflightError as exc:
        raise CompilationStoryboardError(str(exc)) from exc
    segment_by_id = {str(item["segment_id"]): item for item in narration_segments}
    states: list[dict[str, Any]] = []

    def append_segment(
        *, segment_id: str, title: str, presentation: str,
        story_index: int | None = None, story: dict[str, Any] | None = None,
        show_actions_at_end: bool = False,
    ) -> None:
        segment = segment_by_id.get(segment_id)
        if not segment:
            if segment_id.startswith("transition_"):
                return
            raise CompilationStoryboardError(
                f"narration plan is missing layout segment {segment_id}"
            )
        source_story = story or {}
        snapshot = source_story.get("source_snapshot") or {}
        exact_beats = (
            _exact_story_beats(source_story, str(segment["text"]))
            if story is not None else None
        )
        segment_states = reddit_page_text_states(
            str(segment["text"]), exact_beats=exact_beats,
        )
        segment_start = len(states)
        for item in segment_states:
            slide: dict[str, Any] = {
                "slide_id": (
                    f"{segment_id}-page-{item['page_index']:03d}-"
                    f"step-{item['page_step']:02d}"
                ),
                "segment_id": segment_id,
                "kind": "reddit_page",
                "story_index": story_index,
                "beat_index": item["beat_index"],
                "page_index": item["page_index"],
                "page_step": item["page_step"],
                "show_title": item["page_index"] == 1,
                "show_actions": False,
                "presentation": presentation,
                "voice_role": str(segment["voice_role"]),
                "title": title,
                "display_text": item["display_text"],
                "narration_text": item["narration_text"],
            }
            subreddit = str(snapshot.get("subreddit") or "").strip()
            if subreddit:
                slide["subreddit"] = subreddit if subreddit.startswith("r/") else f"r/{subreddit}"
            author = str(snapshot.get("author") or "").strip()
            if author:
                slide["source_author"] = author if author.startswith("u/") else f"u/{author}"
            if isinstance(snapshot.get("score"), int) and not isinstance(snapshot.get("score"), bool):
                slide["source_score"] = snapshot["score"]
            if isinstance(snapshot.get("num_comments"), int) and not isinstance(snapshot.get("num_comments"), bool):
                slide["source_comment_count"] = snapshot["num_comments"]
            states.append(slide)
        if show_actions_at_end and len(states) > segment_start:
            states[-1]["show_actions"] = True

    append_segment(
        segment_id="intro",
        title=str(compilation.get("title_ru") or "Истории с Reddit"),
        presentation="intro",
    )
    stories = compilation.get("stories") or []
    for index, story in enumerate(stories, start=1):
        snapshot = story.get("source_snapshot") or {}
        source_id = str(snapshot.get("source_id") or snapshot.get("post_id") or index)
        append_segment(
            segment_id=f"story_{source_id}",
            title=str(story.get("title_ru") or snapshot.get("title") or f"История {index}"),
            presentation="story",
            story_index=index,
            story=story,
            show_actions_at_end=True,
        )
        if index < len(stories):
            append_segment(
                segment_id=f"transition_{index:02d}",
                title="Следующая история",
                presentation="transition",
                story_index=index,
            )
    append_segment(
        segment_id="outro",
        title="Обсудим в комментариях",
        presentation="outro",
    )
    return states


def _visual_scene_count(
    chunks: list[tuple[int, str]],
    *,
    exact_beats: list[str] | None,
    visuals: list[dict[str, Any]],
) -> int:
    if not chunks or not visuals:
        return 0
    if exact_beats:
        requested = min(MAX_VISUAL_SCENES, len(exact_beats))
    else:
        total_words = sum(len(chunk.split()) for _, chunk in chunks)
        requested = max(MIN_VISUAL_SCENES, math.ceil(total_words / WORDS_PER_VISUAL_SCENE))
        requested = min(MAX_VISUAL_SCENES, requested)
    return max(1, min(len(chunks), requested))


def _visual_scene_for_chunk(
    *,
    chunk_index: int,
    beat_index: int,
    chunk_count: int,
    beat_count: int,
    scene_count: int,
    exact_beats: list[str] | None,
) -> int:
    if scene_count <= 0:
        return 0
    if exact_beats:
        return min(scene_count, ((beat_index - 1) * scene_count) // max(1, beat_count) + 1)
    return min(scene_count, (chunk_index * scene_count) // max(1, chunk_count) + 1)


def _story_visual_schedules(slides: list[dict[str, Any]]) -> list[dict[str, Any]]:
    schedules: list[dict[str, Any]] = []
    segment_ids = list(dict.fromkeys(
        str(slide.get("segment_id") or "")
        for slide in slides
        if _is_story_segment(str(slide.get("segment_id") or "")) and slide.get("visual")
    ))
    for segment_id in segment_ids:
        segment_slides = [
            slide for slide in slides
            if slide.get("segment_id") == segment_id and slide.get("visual")
        ]
        scenes: list[dict[str, Any]] = []
        seen_scene_ids: set[str] = set()
        for slide in segment_slides:
            scene_id = str(slide.get("visual_scene_id") or "")
            if not scene_id or scene_id in seen_scene_ids:
                continue
            seen_scene_ids.add(scene_id)
            visual = slide.get("visual") or {}
            scenes.append({
                "scene_id": scene_id,
                "scene_index": int(slide.get("visual_scene_index") or 0),
                "visual_index": int(slide.get("visual_index") or 0),
                "visual_sha256": str(visual.get("sha256") or ""),
                "first_slide_id": str(slide.get("slide_id") or ""),
            })
        schedules.append({
            "segment_id": segment_id,
            "schedule_source": str(segment_slides[0].get("visual_schedule_source") or ""),
            "scene_count": len(scenes),
            "visual_count": len({scene["visual_sha256"] for scene in scenes}),
            "scenes": scenes,
        })
    return schedules


def _is_story_segment(segment_id: str) -> bool:
    return segment_id.startswith("story-") or segment_id.startswith("story_")


def _bound_tts_state(
    compilation: dict[str, Any], tts_state: dict[str, Any] | None,
) -> dict[str, Any]:
    if not isinstance(tts_state, dict) or tts_state.get("status") != "COMPLETE":
        raise CompilationStoryboardError("complete TTS state is required for production storyboard")
    bindings: dict[str, str] = {}
    for field in ("episode_plan_sha256", "daily_plan_sha256"):
        expected = str(compilation.get(field) or "").strip().lower()
        actual = str(tts_state.get(field) or "").strip().lower()
        if not SHA256_RE.fullmatch(expected) or actual != expected:
            raise CompilationStoryboardError(f"TTS state {field} does not match compilation")
        bindings[field] = expected
    audio_sha256 = str(tts_state.get("final_audio_sha256") or "").strip().lower()
    narration_plan_sha256 = str(
        tts_state.get("narration_plan_sha256") or tts_state.get("plan_sha256") or ""
    ).strip().lower()
    if not SHA256_RE.fullmatch(audio_sha256):
        raise CompilationStoryboardError("TTS state final_audio_sha256 is required")
    if not SHA256_RE.fullmatch(narration_plan_sha256):
        raise CompilationStoryboardError("TTS state narration_plan_sha256 is required")
    if tts_state.get("publication_authorized") is not False:
        raise CompilationStoryboardError("TTS state cannot authorize publication")

    if tts_state.get("timing_contract_version") != TIMING_CONTRACT_VERSION:
        raise CompilationStoryboardError("TTS state timing contract version is required")
    try:
        final_duration = float(tts_state.get("final_audio_duration_sec") or 0)
        raw_duration = float(tts_state.get("raw_chunk_duration_sec") or 0)
        timeline_scale = float(tts_state.get("timeline_scale") or 0)
    except (TypeError, ValueError) as exc:
        raise CompilationStoryboardError("TTS state duration contract is invalid") from exc
    if final_duration <= 0 or raw_duration <= 0 or timeline_scale <= 0:
        raise CompilationStoryboardError("TTS state duration contract must be positive")
    if abs(timeline_scale - final_duration / raw_duration) > 1e-8:
        raise CompilationStoryboardError("TTS state timeline scale does not match final audio")

    chunks = tts_state.get("chunks")
    if not isinstance(chunks, list) or not chunks:
        raise CompilationStoryboardError("TTS state timed chunks are required")
    timing_contract = {
        "version": TIMING_CONTRACT_VERSION,
        "narration_plan_sha256": narration_plan_sha256,
        "final_audio_sha256": audio_sha256,
        "final_audio_duration_sec": tts_state.get("final_audio_duration_sec"),
        "raw_chunk_duration_sec": tts_state.get("raw_chunk_duration_sec"),
        "timeline_scale": tts_state.get("timeline_scale"),
        "chunks": [],
    }
    try:
        expected_segments = build_compilation_segments(compilation)
    except NarrationPreflightError as exc:
        raise CompilationStoryboardError(str(exc)) from exc
    expected_by_id = {str(item["segment_id"]): item for item in expected_segments}
    expected_order = [str(item["segment_id"]) for item in expected_segments]
    grouped: dict[str, dict[str, Any]] = {}
    observed_order: list[str] = []
    observed_raw_duration = 0.0
    for chunk in chunks:
        if not isinstance(chunk, dict):
            raise CompilationStoryboardError("TTS state contains an invalid timed chunk")
        chunk_id = str(chunk.get("chunk_id") or "")
        segment_id = str(chunk.get("logical_segment_id") or "")
        text = str(chunk.get("text") or "")
        text_sha256 = str(chunk.get("text_sha256") or "").lower()
        chunk_audio_sha256 = str(chunk.get("audio_sha256") or "").lower()
        if (
            not chunk_id
            or segment_id not in expected_by_id
            or hashlib.sha256(text.encode("utf-8")).hexdigest() != text_sha256
            or not SHA256_RE.fullmatch(chunk_audio_sha256)
        ):
            raise CompilationStoryboardError("TTS timed chunk identity is not bound to narration/audio")
        expected_role = str(expected_by_id[segment_id].get("voice_role") or "")
        if str(chunk.get("voice_role") or "") != expected_role:
            raise CompilationStoryboardError("TTS timed chunk voice role does not match narration")
        try:
            chunk_index = int(chunk.get("chunk_index") or 0)
            chunk_duration = float(chunk.get("audio_duration_sec") or 0)
        except (TypeError, ValueError) as exc:
            raise CompilationStoryboardError("TTS timed chunk duration/index is invalid") from exc
        words = chunk.get("word_timings")
        timing_source = str(chunk.get("timing_source") or "")
        if (
            chunk_duration <= 0
            or timing_source not in {"ai33", "estimated_from_audio_duration"}
            or not isinstance(words, list)
            or len(words) != len(text.split())
            or chunk.get("word_timings_sha256") != _canonical_hash(words)
        ):
            raise CompilationStoryboardError("TTS timed chunk has incomplete word timing")
        entry = grouped.setdefault(segment_id, {
            "text_parts": [], "words": [], "raw_duration_sec": 0.0,
            "timing_sources": set(), "next_chunk_index": 1,
        })
        if not observed_order or observed_order[-1] != segment_id:
            if segment_id in observed_order:
                raise CompilationStoryboardError("TTS timed chunks split one logical segment")
            observed_order.append(segment_id)
        if chunk_index != entry["next_chunk_index"]:
            raise CompilationStoryboardError("TTS timed chunk order is not contiguous")
        entry["next_chunk_index"] += 1
        raw_offset = float(entry["raw_duration_sec"])
        previous_start = 0.0
        for expected_word, word in zip(text.split(), words):
            try:
                start = float(word["start"])
                end = float(word["end"])
            except (KeyError, TypeError, ValueError) as exc:
                raise CompilationStoryboardError("TTS word timing is invalid") from exc
            if (
                str(word.get("word") or "") != expected_word
                or start < 0
                or end < start
                or start + 0.001 < previous_start
                or end > chunk_duration + 0.001
            ):
                raise CompilationStoryboardError("TTS word timing does not bind to exact chunk text/audio")
            entry["words"].append({
                "word": expected_word,
                "start": (raw_offset + start) * timeline_scale,
                "end": (raw_offset + end) * timeline_scale,
                "timing_source": timing_source,
            })
            previous_start = start
        entry["text_parts"].append(text)
        entry["raw_duration_sec"] = raw_offset + chunk_duration
        entry["timing_sources"].add(timing_source)
        observed_raw_duration += chunk_duration
        timing_contract["chunks"].append({
            "chunk_id": chunk_id,
            "logical_segment_id": segment_id,
            "text_sha256": text_sha256,
            "audio_sha256": chunk_audio_sha256,
            "audio_duration_sec": chunk.get("audio_duration_sec"),
            "timing_source": timing_source,
            "word_timings_sha256": chunk.get("word_timings_sha256"),
        })

    if observed_order != expected_order or abs(observed_raw_duration - raw_duration) > 0.001:
        raise CompilationStoryboardError("TTS timed chunks do not cover the full narration plan")
    contract_sha256 = str(tts_state.get("timing_contract_sha256") or "").lower()
    if not SHA256_RE.fullmatch(contract_sha256) or contract_sha256 != _canonical_hash(timing_contract):
        raise CompilationStoryboardError("TTS timing contract checksum mismatch")

    segment_timings: dict[str, dict[str, Any]] = {}
    for segment_id in expected_order:
        entry = grouped[segment_id]
        expected_text = _normalized_text(expected_by_id[segment_id]["text"])
        observed_text = _normalized_text(" ".join(entry["text_parts"]))
        if observed_text != expected_text:
            raise CompilationStoryboardError("TTS timed chunks changed narration text")
        duration = float(entry["raw_duration_sec"]) * timeline_scale
        timing_sources = entry["timing_sources"]
        segment_timings[segment_id] = {
            "duration_sec": duration,
            "words": entry["words"],
            "timing_source": (
                "ai33" if timing_sources == {"ai33"}
                else "actual_audio_duration_estimate"
                if timing_sources == {"estimated_from_audio_duration"}
                else "mixed_ai33_and_actual_audio_duration_estimate"
            ),
        }
    if abs(sum(item["duration_sec"] for item in segment_timings.values()) - final_duration) > 0.001:
        raise CompilationStoryboardError("TTS segment timings do not cover final audio")
    return {
        "bindings": {
            **bindings,
            "audio_sha256": audio_sha256,
            "narration_plan_sha256": narration_plan_sha256,
            "timing_contract_sha256": contract_sha256,
            "final_audio_duration_sec": round(final_duration, 6),
        },
        "segment_timings": segment_timings,
    }


def _timing_windows(
    chunks: list[tuple[int, str]], segment_timing: dict[str, Any],
) -> list[tuple[float, float]]:
    words = segment_timing.get("words") or []
    expected_words = [word for _, chunk in chunks for word in chunk.split()]
    if [str(item.get("word") or "") for item in words] != expected_words:
        raise CompilationStoryboardError("storyboard chunks do not match TTS word timing")
    duration = float(segment_timing.get("duration_sec") or 0)
    if duration <= 0:
        raise CompilationStoryboardError("storyboard segment timing must be positive")
    boundaries = [0.0]
    consumed = 0
    for _, chunk in chunks[:-1]:
        consumed += len(chunk.split())
        previous_end = float(words[consumed - 1]["end"])
        next_start = float(words[consumed]["start"])
        boundary = max(boundaries[-1], (previous_end + next_start) / 2)
        boundaries.append(min(boundary, duration))
    boundaries.append(duration)
    windows = list(zip(boundaries, boundaries[1:]))
    if any(end - start < 0.5 for start, end in windows):
        raise CompilationStoryboardError(
            "actual audio timing creates a page shorter than renderer minimum"
        )
    return windows


def _append_reddit_pages(
    slides: list[dict[str, Any]],
    *,
    segment_id: str,
    text: str,
    title: str,
    timeline_cursor: float,
    story_index: int | None = None,
    visuals: list[dict[str, Any]] | None = None,
    exact_beats: list[str] | None = None,
    show_actions_at_end: bool = False,
    subreddit: str | None = None,
    source_author: str | None = None,
    source_score: int | None = None,
    source_comment_count: int | None = None,
    presentation: str = "story",
    voice_role: str = "narrator",
    segment_timing: dict[str, Any] | None = None,
) -> float:
    page_states = reddit_page_text_states(text, exact_beats=exact_beats)
    if not page_states:
        return timeline_cursor
    chunks = [
        (int(item["beat_index"]), str(item["narration_text"]))
        for item in page_states
    ]
    if not isinstance(segment_timing, dict):
        raise CompilationStoryboardError(f"timing is required for narration segment {segment_id}")
    timing_windows = _timing_windows(chunks, segment_timing)
    segment_start = timeline_cursor
    segment_slide_start = len(slides)
    visuals = visuals or []
    visual_scene_count = _visual_scene_count(chunks, exact_beats=exact_beats, visuals=visuals)
    beat_count = max((beat_index for beat_index, _ in chunks), default=0)
    schedule_source = "editorial_story_beats" if exact_beats else "deterministic_word_schedule"
    for chunk_index, state in enumerate(page_states):
        beat_index = int(state["beat_index"])
        chunk = str(state["narration_text"])
        page_index = int(state["page_index"])
        page_step = int(state["page_step"])
        local_start, local_end = timing_windows[chunk_index]
        duration = local_end - local_start
        slide: dict[str, Any] = {
            "slide_id": f"{segment_id}-page-{page_index:03d}-step-{page_step:02d}",
            "scene_id": f"{segment_id}-beat-{beat_index:03d}",
            "segment_id": segment_id,
            "kind": "reddit_page",
            "story_index": story_index,
            "beat_index": beat_index,
            "page_index": page_index,
            "page_step": page_step,
            "show_title": page_index == 1,
            "show_actions": False,
            "presentation": presentation,
            "voice_role": voice_role,
            "title": title,
            "display_text": str(state["display_text"]),
            "narration_text": chunk,
            "text_sha256": hashlib.sha256(_normalized_text(chunk).encode("utf-8")).hexdigest(),
            "duration_sec": round(duration, 3),
            "start_sec": round(segment_start + local_start, 3),
            "end_sec": round(segment_start + local_end, 3),
            "timing_source": str(segment_timing.get("timing_source") or ""),
        }
        if subreddit:
            clean_subreddit = str(subreddit).strip()
            slide["subreddit"] = clean_subreddit if clean_subreddit.startswith("r/") else f"r/{clean_subreddit}"
        if source_author:
            clean_author = str(source_author).strip()
            slide["source_author"] = clean_author if clean_author.startswith("u/") else f"u/{clean_author}"
        if isinstance(source_score, int) and not isinstance(source_score, bool):
            slide["source_score"] = source_score
        if isinstance(source_comment_count, int) and not isinstance(source_comment_count, bool):
            slide["source_comment_count"] = source_comment_count
        if visuals:
            visual_scene_index = _visual_scene_for_chunk(
                chunk_index=chunk_index,
                beat_index=beat_index,
                chunk_count=len(chunks),
                beat_count=beat_count,
                scene_count=visual_scene_count,
                exact_beats=exact_beats,
            )
            visual_index = (visual_scene_index - 1) % len(visuals)
            slide.update({
                "visual": visuals[visual_index],
                "visual_index": visual_index + 1,
                "visual_scene_index": visual_scene_index,
                "visual_scene_id": f"{segment_id}-visual-scene-{visual_scene_index:03d}",
                "visual_schedule_source": schedule_source,
            })
        slides.append(slide)
    if show_actions_at_end and len(slides) > segment_slide_start:
        slides[-1]["show_actions"] = True
    return segment_start + float(segment_timing["duration_sec"])


def _legacy_storyboard(compilation: dict[str, Any], artifact_root: Path) -> dict[str, Any]:
    slides: list[dict[str, Any]] = [{
        "slide_id": "intro",
        "kind": "title",
        "title": str(compilation.get("title_ru") or "Страшные истории с Reddit"),
    }]
    for index, story in enumerate(compilation.get("stories") or [], start=1):
        snapshot = story.get("source_snapshot") or {}
        slides.append({
            "slide_id": f"story-{index:02d}-title",
            "kind": "story_title",
            "story_index": index,
            "title": str(story.get("title_ru") or snapshot.get("title") or ""),
            "source_url": str(snapshot.get("source_url") or ""),
        })
        for image_index, visual in enumerate(_verified_local_images(story, artifact_root), start=1):
            slides.append({
                "slide_id": f"story-{index:02d}-image-{image_index:02d}",
                "kind": "source_image",
                "story_index": index,
                "visual": visual,
            })
    slides.append({"slide_id": "outro", "kind": "outro", "text": str(compilation.get("outro_ru") or "")})
    return {
        "version": 1,
        "format": "compilation_16x9",
        "resolution": [1920, 1080],
        "slides": slides,
        "creative_manifest": {
            "version": 1,
            "mode": "legacy_static",
            "text_timing_coverage": 0.0,
            "thumbnail_required": True,
        },
    }


def build_storyboard(
    compilation: dict[str, Any],
    artifact_root: Path,
    *,
    background_video: str | Path | None = None,
    tts_state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build scene-level pages when a complete narration contract is available."""
    artifact_root = Path(artifact_root)
    if not _complete_narration(compilation):
        result = _legacy_storyboard(compilation, artifact_root)
        if background_video:
            result["background_video"] = _verified_background_video(background_video, artifact_root)
        return result

    timing_contract = _bound_tts_state(compilation, tts_state)
    bindings = timing_contract["bindings"]
    segment_timings = timing_contract["segment_timings"]
    try:
        narration_segments = build_compilation_segments(compilation)
    except NarrationPreflightError as exc:
        raise CompilationStoryboardError(str(exc)) from exc
    segment_by_id = {item["segment_id"]: item for item in narration_segments}
    slides: list[dict[str, Any]] = []
    cursor = 0.0
    title = str(compilation.get("title_ru") or "Истории с Reddit")
    intro_segment = segment_by_id.get("intro")
    if not intro_segment:
        raise CompilationStoryboardError("narration plan is missing intro")
    cursor = _append_reddit_pages(
        slides,
        segment_id="intro",
        text=intro_segment["text"],
        title=title,
        timeline_cursor=cursor,
        presentation="intro",
        voice_role=intro_segment["voice_role"],
        segment_timing=segment_timings.get("intro"),
    )
    stories = compilation.get("stories") or []
    for index, story in enumerate(stories, start=1):
        snapshot = story.get("source_snapshot") or {}
        source_id = str(snapshot.get("source_id") or snapshot.get("post_id") or index)
        story_segment_id = f"story_{source_id}"
        story_segment = segment_by_id.get(story_segment_id)
        if not story_segment:
            raise CompilationStoryboardError(
                f"narration plan is missing story segment {story_segment_id}"
            )
        visuals = _verified_local_images(story, artifact_root)
        spoken_story = story_segment["text"]
        cursor = _append_reddit_pages(
            slides,
            segment_id=story_segment_id,
            text=spoken_story,
            title=str(story.get("title_ru") or snapshot.get("title") or f"История {index}"),
            timeline_cursor=cursor,
            story_index=index,
            visuals=visuals,
            exact_beats=_exact_story_beats(story, spoken_story),
            show_actions_at_end=True,
            subreddit=str(snapshot.get("subreddit") or "").strip() or None,
            source_author=str(snapshot.get("author") or "").strip() or None,
            source_score=snapshot.get("score"),
            source_comment_count=snapshot.get("num_comments"),
            presentation="story",
            voice_role=story_segment["voice_role"],
            segment_timing=segment_timings.get(story_segment_id),
        )
        if index < len(stories):
            transition_id = f"transition_{index:02d}"
            transition_segment = segment_by_id.get(transition_id)
            if not transition_segment:
                continue
            cursor = _append_reddit_pages(
                slides,
                segment_id=transition_id,
                text=transition_segment["text"],
                title="Следующая история",
                timeline_cursor=cursor,
                story_index=index,
                presentation="transition",
                voice_role=transition_segment["voice_role"],
                segment_timing=segment_timings.get(transition_id),
            )
    outro_segment = segment_by_id.get("outro")
    if not outro_segment:
        raise CompilationStoryboardError("narration plan is missing outro")
    cursor = _append_reddit_pages(
        slides,
        segment_id="outro",
        text=outro_segment["text"],
        title="Обсудим в комментариях",
        timeline_cursor=cursor,
        presentation="outro",
        voice_role=outro_segment["voice_role"],
        segment_timing=segment_timings.get("outro"),
    )
    expected_text = narration_text(compilation)
    covered_text = _normalized_text(" ".join(str(slide.get("narration_text") or "") for slide in slides))
    coverage = 1.0 if expected_text and covered_text == expected_text else 0.0
    final_audio_duration = float(bindings["final_audio_duration_sec"])
    if abs(cursor - final_audio_duration) > 0.001:
        raise CompilationStoryboardError("storyboard timeline does not cover final narration audio")
    timing_sources = sorted({str(slide.get("timing_source") or "") for slide in slides})
    storyboard: dict[str, Any] = {
        "version": 2,
        "format": "compilation_16x9",
        "resolution": [1920, 1080],
        **bindings,
        "publication_authorized": False,
        "timeline_duration_sec": round(final_audio_duration, 3),
        "slides": slides,
        "creative_manifest": {
            "version": 1,
            "mode": "reddit_pages",
            **bindings,
            "publication_authorized": False,
            "narration_sha256": narration_sha256(compilation),
            "narration_characters": len(expected_text),
            "text_timing_coverage": coverage,
            "audio_timing_coverage": 1.0,
            "timing_sources": timing_sources,
            "page_slide_count": len(slides),
            "max_planned_seconds_per_slide": max((slide["duration_sec"] for slide in slides), default=0),
            "background_video_required": bool(background_video),
            "thumbnail_required": True,
            "visual_contract": {
                "version": VISUAL_CONTRACT_VERSION,
                "text_left_x": TEXT_LEFT_X,
                "text_right_x": TEXT_RIGHT_X,
                "mascot_safe_x": MASCOT_SAFE_X,
                "story_visual_feather_start_x": STORY_VISUAL_FEATHER_START_X,
                "story_visual_feather_end_x": STORY_VISUAL_FEATHER_END_X,
                "story_visual_brightness": STORY_VISUAL_BRIGHTNESS,
                "readability_shade_alpha": READABILITY_SHADE_ALPHA,
                "min_visual_scenes": MIN_VISUAL_SCENES,
                "max_visual_scenes": MAX_VISUAL_SCENES,
            },
            "story_visual_schedules": _story_visual_schedules(slides),
        },
    }
    if background_video:
        storyboard["background_video"] = _verified_background_video(background_video, artifact_root)
    return storyboard


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compilation", required=True)
    parser.add_argument("--artifact-root", required=True)
    parser.add_argument("--background-video", help="Optional existing local video under artifact_root.")
    parser.add_argument("--tts-state", help="Required COMPLETE TTS state for a production storyboard.")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    compilation = json.loads(Path(args.compilation).read_text(encoding="utf-8"))
    storyboard = build_storyboard(
        compilation,
        Path(args.artifact_root),
        background_video=args.background_video,
        tts_state=(
            json.loads(Path(args.tts_state).read_text(encoding="utf-8"))
            if args.tts_state else None
        ),
    )
    Path(args.output).write_text(json.dumps(storyboard, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
