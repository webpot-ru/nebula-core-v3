"""Deterministic, no-network shot and caption contracts for acc1 cinematic video."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any

from acc1_visual_contract import (
    CANVAS_FPS,
    CANVAS_HEIGHT,
    CANVAS_WIDTH,
    CINEMATIC_CAPTION_TRACK_VERSION,
    CINEMATIC_CAPTION_WORDS_PER_CUE,
    CINEMATIC_PAN_CENTER_MAX,
    CINEMATIC_PAN_CENTER_MIN,
    CINEMATIC_SHOT_PLAN_VERSION,
    CINEMATIC_SERVICE_SHOT_MAX_SECONDS,
    CINEMATIC_STORY_MODE,
    CINEMATIC_STORY_SHOT_MAX_SECONDS,
    CINEMATIC_STORY_SHOT_MIN_SECONDS,
    CINEMATIC_ZOOM_END_MAX,
    CINEMATIC_ZOOM_END_MIN,
)


class CinematicShotError(RuntimeError):
    """Raised when a cinematic plan cannot remain deterministic and source-bound."""


def canonical_hash(value: Any) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _bound_payload(value: dict[str, Any], hash_field: str) -> dict[str, Any]:
    payload = dict(value)
    payload[hash_field] = canonical_hash(value)
    return payload


def verify_bound_payload(value: Any, hash_field: str) -> bool:
    if not isinstance(value, dict):
        return False
    recorded = str(value.get(hash_field) or "")
    payload = {key: item for key, item in value.items() if key != hash_field}
    return len(recorded) == 64 and recorded == canonical_hash(payload)


def _story_shot_count(duration: float, visual_count: int) -> int:
    if duration + 1e-6 < CINEMATIC_STORY_SHOT_MIN_SECONDS:
        raise CinematicShotError(
            "cinematic story narration must be at least "
            f"{CINEMATIC_STORY_SHOT_MIN_SECONDS:g} seconds"
        )
    minimum = max(1, math.ceil(duration / CINEMATIC_STORY_SHOT_MAX_SECONDS))
    maximum = max(1, math.floor(duration / CINEMATIC_STORY_SHOT_MIN_SECONDS))
    if minimum > maximum:
        raise CinematicShotError("story duration cannot satisfy cinematic shot bounds")
    return min(maximum, max(minimum, min(max(1, visual_count), maximum)))


def _word_partitions(text: str, count: int) -> list[str]:
    words = str(text or "").split()
    if not words or count < 1:
        raise CinematicShotError("cinematic shot narration text is required")
    if count > len(words):
        raise CinematicShotError(
            "cinematic narration has fewer words than required story shots",
        )
    boundaries = [round(index * len(words) / count) for index in range(count + 1)]
    parts = [
        " ".join(words[boundaries[index]:boundaries[index + 1]])
        for index in range(count)
    ]
    if any(not part for part in parts) or " ".join(parts) != " ".join(words):
        raise CinematicShotError("cinematic text partition changed narration")
    return parts


def _motion(shot_id: str, visual_sha256: str) -> dict[str, Any]:
    seed = hashlib.sha256(f"{shot_id}:{visual_sha256}".encode("utf-8")).digest()
    zoom_steps = round((CINEMATIC_ZOOM_END_MAX - CINEMATIC_ZOOM_END_MIN) * 100)
    end_scale = CINEMATIC_ZOOM_END_MIN + (seed[0] % (zoom_steps + 1)) / 100
    centers = (
        CINEMATIC_PAN_CENTER_MIN,
        0.50,
        CINEMATIC_PAN_CENTER_MAX,
    )
    start_x = centers[seed[1] % len(centers)]
    start_y = centers[seed[2] % len(centers)]
    end_x = centers[seed[3] % len(centers)]
    end_y = centers[seed[4] % len(centers)]
    if start_x == end_x and start_y == end_y:
        end_x = centers[(seed[3] + 1) % len(centers)]
    return {
        "type": "slow_push_pan",
        "start_scale": 1.0,
        "end_scale": round(end_scale, 2),
        "start_center": [start_x, start_y],
        "end_center": [end_x, end_y],
        "easing": "linear",
    }


def _caption_track(
    narration_segments: list[dict[str, Any]],
    segment_timings: dict[str, dict[str, Any]],
    final_audio_duration_sec: float,
) -> dict[str, Any]:
    cues: list[dict[str, Any]] = []
    cursor = 0.0
    all_text: list[str] = []
    for segment in narration_segments:
        segment_id = str(segment.get("segment_id") or "")
        text = " ".join(str(segment.get("text") or "").split())
        timing = segment_timings.get(segment_id)
        if not isinstance(timing, dict):
            raise CinematicShotError(f"missing timing for caption segment {segment_id}")
        words = timing.get("words")
        expected_words = text.split()
        if (
            not isinstance(words, list)
            or [str(item.get("word") or "") for item in words] != expected_words
        ):
            raise CinematicShotError(f"caption timing does not match segment {segment_id}")
        all_text.append(text)
        for index in range(0, len(words), CINEMATIC_CAPTION_WORDS_PER_CUE):
            group = words[index:index + CINEMATIC_CAPTION_WORDS_PER_CUE]
            start = cursor + float(group[0]["start"])
            end = cursor + float(group[-1]["end"])
            if end <= start:
                end = start + 0.001
            cue_text = " ".join(str(item["word"]) for item in group)
            cues.append({
                "cue_id": f"cue-{len(cues) + 1:04d}",
                "segment_id": segment_id,
                "start_sec": round(start, 3),
                "end_sec": round(min(end, final_audio_duration_sec), 3),
                "text": cue_text,
                "text_sha256": hashlib.sha256(cue_text.encode("utf-8")).hexdigest(),
            })
        cursor += float(timing.get("duration_sec") or 0)
    for previous, current in zip(cues, cues[1:]):
        if float(current["start_sec"]) + 0.001 >= float(previous["end_sec"]):
            continue
        lower = float(previous["start_sec"]) + 0.001
        upper = float(current["end_sec"]) - 0.001
        if lower >= upper:
            raise CinematicShotError("caption timing cannot be made non-overlapping")
        boundary = min(
            upper,
            max(
                lower,
                (
                    float(previous["end_sec"])
                    + float(current["start_sec"])
                ) / 2,
            ),
        )
        previous["end_sec"] = round(boundary, 3)
        current["start_sec"] = round(boundary, 3)
    normalized_text = " ".join(all_text)
    if abs(cursor - final_audio_duration_sec) > 0.001:
        raise CinematicShotError("caption timeline does not cover final audio")
    payload = {
        "version": CINEMATIC_CAPTION_TRACK_VERSION,
        "language": "ru",
        "timeline_duration_sec": round(final_audio_duration_sec, 3),
        "cue_count": len(cues),
        "text_sha256": hashlib.sha256(normalized_text.encode("utf-8")).hexdigest(),
        "cues": cues,
    }
    return _bound_payload(payload, "caption_track_sha256")


def build_cinematic_contract(
    *,
    narration_segments: list[dict[str, Any]],
    segment_timings: dict[str, dict[str, Any]],
    story_visuals: dict[str, list[dict[str, Any]]],
    story_metadata: dict[str, dict[str, Any]],
    final_audio_duration_sec: float,
) -> dict[str, Any]:
    """Build exact continuous shots from already verified local scene images."""

    if not narration_segments or final_audio_duration_sec <= 0:
        raise CinematicShotError("cinematic narration and final duration are required")
    story_ids = [
        str(segment["segment_id"])
        for segment in narration_segments
        if segment.get("kind") == "story"
    ]
    if not story_ids:
        raise CinematicShotError("cinematic storyboard requires a story segment")
    for segment_id in story_ids:
        visuals = story_visuals.get(segment_id)
        if not isinstance(visuals, list) or not visuals:
            raise CinematicShotError(
                f"cinematic story {segment_id} requires a verified local image"
            )

    first_visual = story_visuals[story_ids[0]][0]
    last_visual = story_visuals[story_ids[-1]][-1]
    shots: list[dict[str, Any]] = []
    cursor = 0.0
    completed_story_count = 0
    for segment in narration_segments:
        segment_id = str(segment.get("segment_id") or "")
        segment_kind = str(segment.get("kind") or "")
        timing = segment_timings.get(segment_id)
        if not isinstance(timing, dict):
            raise CinematicShotError(f"missing cinematic timing for {segment_id}")
        duration = float(timing.get("duration_sec") or 0)
        if duration < 0.5:
            raise CinematicShotError(f"cinematic segment {segment_id} is shorter than 0.5 seconds")
        if segment_kind == "story":
            visuals = story_visuals[segment_id]
            shot_count = _story_shot_count(duration, len(visuals))
            completed_story_count += 1
        else:
            if duration > CINEMATIC_SERVICE_SHOT_MAX_SECONDS + 0.001:
                raise CinematicShotError(
                    f"cinematic {segment_kind} segment must remain a short "
                    f"{CINEMATIC_SERVICE_SHOT_MAX_SECONDS:g}-second bumper",
                )
            shot_count = 1
            if segment_kind == "intro":
                visuals = [first_visual]
            elif segment_kind == "outro":
                visuals = [last_visual]
            elif segment_kind == "transition":
                next_story_position = min(completed_story_count, len(story_ids) - 1)
                visuals = [story_visuals[story_ids[next_story_position]][0]]
            elif segment_kind == "mid_story_cta":
                anchor_story_position = max(0, completed_story_count - 1)
                visuals = [story_visuals[story_ids[anchor_story_position]][-1]]
            else:
                raise CinematicShotError(f"unsupported narration segment kind {segment_kind}")

        text_parts = _word_partitions(str(segment.get("text") or ""), shot_count)
        for shot_index in range(shot_count):
            local_start = duration * shot_index / shot_count
            local_end = duration * (shot_index + 1) / shot_count
            shot_duration = local_end - local_start
            if segment_kind == "story" and not (
                CINEMATIC_STORY_SHOT_MIN_SECONDS - 0.001
                <= shot_duration
                <= CINEMATIC_STORY_SHOT_MAX_SECONDS + 0.001
            ):
                raise CinematicShotError("cinematic story shot duration is out of bounds")
            visual = visuals[shot_index % len(visuals)]
            visual_sha = str(visual.get("sha256") or "")
            if len(visual_sha) != 64:
                raise CinematicShotError("cinematic visual requires SHA-256 evidence")
            shot_id = f"{segment_id}-shot-{shot_index + 1:03d}"
            narration_part = text_parts[shot_index]
            metadata = story_metadata.get(segment_id, {})
            shot = {
                "slide_id": shot_id,
                "shot_id": shot_id,
                "scene_id": shot_id,
                "segment_id": segment_id,
                "kind": "cinematic_shot",
                "presentation": segment_kind,
                "story_index": metadata.get("story_index"),
                "voice_role": str(segment.get("voice_role") or ""),
                "visual": visual,
                "visual_sha256": visual_sha,
                "start_sec": round(cursor + local_start, 3),
                "end_sec": round(cursor + local_end, 3),
                "duration_sec": round(shot_duration, 3),
                "narration_text": narration_part,
                "text_sha256": hashlib.sha256(narration_part.encode("utf-8")).hexdigest(),
                "timing_source": str(timing.get("timing_source") or ""),
                "motion": _motion(shot_id, visual_sha),
            }
            if metadata.get("title"):
                shot["story_title"] = str(metadata["title"])
            if metadata.get("source_label"):
                shot["source_label"] = str(metadata["source_label"])
            if metadata.get("truth_mode"):
                shot["truth_mode"] = str(metadata["truth_mode"])
            shots.append(shot)
        cursor += duration

    if abs(cursor - final_audio_duration_sec) > 0.001:
        raise CinematicShotError("cinematic shots do not cover final audio")
    for previous, current in zip(shots, shots[1:]):
        if abs(float(previous["end_sec"]) - float(current["start_sec"])) > 0.001:
            raise CinematicShotError("cinematic shot timeline has a gap or overlap")

    shot_payload = {
        "version": CINEMATIC_SHOT_PLAN_VERSION,
        "visual_mode": CINEMATIC_STORY_MODE,
        "resolution": [CANVAS_WIDTH, CANVAS_HEIGHT],
        "fps": CANVAS_FPS,
        "timeline_duration_sec": round(final_audio_duration_sec, 3),
        "shot_count": len(shots),
        "story_shot_count": sum(shot["presentation"] == "story" for shot in shots),
        "shots": shots,
    }
    shot_plan = _bound_payload(shot_payload, "shot_plan_sha256")
    captions = _caption_track(
        narration_segments, segment_timings, final_audio_duration_sec,
    )
    return {
        "shots": shots,
        "shot_plan": shot_plan,
        "caption_track": captions,
    }


def _srt_time(seconds: float) -> str:
    milliseconds = max(0, round(float(seconds) * 1000))
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, millis = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def write_caption_srt(caption_track: dict[str, Any], output: Path) -> Path:
    """Write a hash-verified caption sidecar without changing its cue timings."""

    if not verify_bound_payload(caption_track, "caption_track_sha256"):
        raise CinematicShotError("caption track checksum mismatch")
    cues = caption_track.get("cues")
    if not isinstance(cues, list) or not cues:
        raise CinematicShotError("caption track contains no cues")
    lines: list[str] = []
    previous_end = 0.0
    for index, cue in enumerate(cues, start=1):
        start = float(cue.get("start_sec") or 0)
        end = float(cue.get("end_sec") or 0)
        text = str(cue.get("text") or "").strip()
        if start + 0.001 < previous_end or end <= start or not text:
            raise CinematicShotError("caption cues are invalid or overlap")
        if hashlib.sha256(text.encode("utf-8")).hexdigest() != cue.get("text_sha256"):
            raise CinematicShotError("caption cue text checksum mismatch")
        lines.extend([
            str(index),
            f"{_srt_time(start)} --> {_srt_time(end)}",
            text,
            "",
        ])
        previous_end = end
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines), encoding="utf-8")
    return output
