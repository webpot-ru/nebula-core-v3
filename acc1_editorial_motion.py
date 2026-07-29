"""Deterministic source-bound contract for ``editorial_motion_v1``.

The contract treats generated images as coordinated asset packs instead of
finished frames.  Exact text, dates, evidence labels, and captions remain DOM
content owned by the HyperFrames composition.
"""

from __future__ import annotations

import hashlib
import json
import math
from typing import Any

from acc1_visual_contract import (
    ADULT_ANIMATION_SERIES,
    CINEMATIC_INK_WEBTOON_STYLE_PROFILE,
    CANVAS_FPS,
    CANVAS_HEIGHT,
    CANVAS_WIDTH,
    EDITORIAL_MOTION_ASSETS_PER_PACK,
    EDITORIAL_MOTION_CAPTION_TRACK_VERSION,
    EDITORIAL_MOTION_MAX_SCENE_SECONDS,
    EDITORIAL_MOTION_MIN_SCENE_SECONDS,
    EDITORIAL_MOTION_MODULES,
    EDITORIAL_MOTION_PLAN_VERSION,
    EDITORIAL_MOTION_SERVICE_SCENE_MAX_SECONDS,
    EDITORIAL_MOTION_STYLE_PROFILE,
    EDITORIAL_MOTION_STYLE_PROFILES,
    FORMAT_VISUAL_SYSTEM_V3_STYLE_PROFILE,
    EDITORIAL_MOTION_MODE,
    EDITORIAL_MOTION_TARGET_SCENE_SECONDS,
    INK_GOUACHE_PAGE_LAYOUTS,
    INK_GOUACHE_STORY_FAMILIES,
    INK_GOUACHE_STORY_PAGES_STYLE_PROFILE,
    build_format_visual_system_v3_semantic_camera,
    is_adult_animation_style_profile,
)


CAPTION_WORDS_PER_CUE = 8
REQUIRED_LAYER_ROLES = ("hero_plate", "detail_plate")


class EditorialMotionError(RuntimeError):
    """Raised when a motion plan cannot remain exact and deterministic."""


def canonical_hash(value: Any) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def bind_payload(value: dict[str, Any], hash_field: str) -> dict[str, Any]:
    payload = dict(value)
    payload[hash_field] = canonical_hash(value)
    return payload


def verify_bound_payload(value: Any, hash_field: str) -> bool:
    if not isinstance(value, dict):
        return False
    recorded = str(value.get(hash_field) or "")
    payload = {key: item for key, item in value.items() if key != hash_field}
    return len(recorded) == 64 and recorded == canonical_hash(payload)


def _word_partitions(text: str, count: int) -> list[str]:
    words = " ".join(str(text or "").split()).split()
    if not words or count < 1 or count > len(words):
        raise EditorialMotionError("motion scene text cannot be partitioned exactly")
    boundaries = [round(index * len(words) / count) for index in range(count + 1)]
    parts = [
        " ".join(words[boundaries[index]:boundaries[index + 1]])
        for index in range(count)
    ]
    if any(not part for part in parts) or " ".join(parts) != " ".join(words):
        raise EditorialMotionError("motion scene partition changed narration")
    return parts


def _scene_count(duration: float, available_packs: int) -> int:
    if duration + 0.001 < EDITORIAL_MOTION_MIN_SCENE_SECONDS:
        raise EditorialMotionError(
            "editorial story segment is shorter than the minimum motion scene",
        )
    minimum = max(1, math.ceil(duration / EDITORIAL_MOTION_MAX_SCENE_SECONDS))
    maximum = max(1, math.floor(duration / EDITORIAL_MOTION_MIN_SCENE_SECONDS))
    desired = max(1, round(duration / EDITORIAL_MOTION_TARGET_SCENE_SECONDS))
    count = min(maximum, max(minimum, desired))
    if available_packs < count:
        raise EditorialMotionError(
            f"editorial story requires {count} asset packs but has {available_packs}",
        )
    return count


def _service_scene_packs(
    packs: list[dict[str, Any]],
    *,
    duration: float,
    segment_kind: str,
    from_end: bool = False,
) -> list[dict[str, Any]]:
    scene_count = max(
        1,
        math.ceil(
            (duration - 0.001) / EDITORIAL_MOTION_SERVICE_SCENE_MAX_SECONDS,
        ),
    )
    if len(packs) < scene_count:
        raise EditorialMotionError(
            f"editorial {segment_kind} requires {scene_count} existing asset "
            f"packs but has {len(packs)}",
        )
    if from_end:
        return packs[-scene_count:]
    return packs[:scene_count]


def _group_asset_packs(assets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    order: list[str] = []
    for asset in assets:
        if not isinstance(asset, dict):
            raise EditorialMotionError("editorial asset must be an object")
        family_id = str(asset.get("asset_family_id") or "").strip()
        role = str(asset.get("layer_role") or "").strip()
        if not family_id or role not in REQUIRED_LAYER_ROLES:
            raise EditorialMotionError(
                "editorial assets require asset_family_id and a supported layer_role",
            )
        if family_id not in grouped:
            grouped[family_id] = []
            order.append(family_id)
        if any(item.get("layer_role") == role for item in grouped[family_id]):
            raise EditorialMotionError(f"duplicate {role} in asset family {family_id}")
        grouped[family_id].append(asset)

    packs: list[dict[str, Any]] = []
    for family_id in order:
        family_assets = sorted(
            grouped[family_id],
            key=lambda item: REQUIRED_LAYER_ROLES.index(str(item["layer_role"])),
        )
        if len(family_assets) != EDITORIAL_MOTION_ASSETS_PER_PACK or tuple(
            str(item.get("layer_role") or "") for item in family_assets
        ) != REQUIRED_LAYER_ROLES:
            raise EditorialMotionError(
                f"asset family {family_id} must contain exactly {REQUIRED_LAYER_ROLES}",
            )
        modules = {str(item.get("motion_module") or "") for item in family_assets}
        if len(modules) != 1 or next(iter(modules)) not in EDITORIAL_MOTION_MODULES:
            raise EditorialMotionError(f"asset family {family_id} has invalid motion module")
        story_families = {str(item.get("story_family") or "") for item in family_assets}
        page_layouts = {str(item.get("page_layout") or "") for item in family_assets}
        panel_grammars = {str(item.get("panel_grammar") or "") for item in family_assets}
        panel_counts = {item.get("panel_count") for item in family_assets}
        panel_beat_roles = {str(item.get("panel_beat_role") or "") for item in family_assets}
        if (
            len(story_families) != 1
            or len(page_layouts) != 1
            or len(panel_grammars) != 1
            or len(panel_counts) != 1
            or len(panel_beat_roles) != 1
        ):
            raise EditorialMotionError(f"asset family {family_id} has inconsistent art direction")
        pack_payload = {
            "asset_family_id": family_id,
            "motion_module": next(iter(modules)),
            "story_family": next(iter(story_families)),
            "page_layout": next(iter(page_layouts)),
            "assets": family_assets,
        }
        panel_grammar = next(iter(panel_grammars))
        if panel_grammar:
            panel_count = next(iter(panel_counts))
            panel_beat_role = next(iter(panel_beat_roles))
            if not isinstance(panel_count, int) or panel_count not in {1, 2, 3, 4, 5} or not panel_beat_role:
                raise EditorialMotionError(f"asset family {family_id} has invalid panel grammar metadata")
            pack_payload.update({
                "panel_grammar": panel_grammar,
                "panel_count": panel_count,
                "panel_beat_role": panel_beat_role,
            })
        packs.append({**pack_payload, "asset_pack_sha256": canonical_hash(pack_payload)})
    return packs


def _caption_track(
    narration_segments: list[dict[str, Any]],
    segment_timings: dict[str, dict[str, Any]],
    final_audio_duration_sec: float,
) -> dict[str, Any]:
    cues: list[dict[str, Any]] = []
    all_text: list[str] = []
    cursor = 0.0
    for segment in narration_segments:
        segment_id = str(segment.get("segment_id") or "")
        text = " ".join(str(segment.get("text") or "").split())
        timing = segment_timings.get(segment_id)
        if not isinstance(timing, dict):
            raise EditorialMotionError(f"missing caption timing for {segment_id}")
        words = timing.get("words")
        if not isinstance(words, list) or [
            str(item.get("word") or "") for item in words
        ] != text.split():
            raise EditorialMotionError(f"caption words do not match {segment_id}")
        all_text.append(text)
        for offset in range(0, len(words), CAPTION_WORDS_PER_CUE):
            group = words[offset:offset + CAPTION_WORDS_PER_CUE]
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
        if float(previous["end_sec"]) <= float(current["start_sec"]) + 0.001:
            continue
        boundary = round(
            (float(previous["end_sec"]) + float(current["start_sec"])) / 2,
            3,
        )
        previous["end_sec"] = boundary
        current["start_sec"] = boundary
    if abs(cursor - final_audio_duration_sec) > 0.001:
        raise EditorialMotionError("caption track does not cover final audio")
    payload = {
        "version": EDITORIAL_MOTION_CAPTION_TRACK_VERSION,
        "language": "ru",
        "timeline_duration_sec": round(final_audio_duration_sec, 3),
        "cue_count": len(cues),
        "text_sha256": hashlib.sha256(" ".join(all_text).encode("utf-8")).hexdigest(),
        "cues": cues,
    }
    return bind_payload(payload, "caption_track_sha256")


def _motion_contract(module: str) -> dict[str, Any]:
    contracts = {
        "living_photo_depth": {"camera": "cutout_parallax", "transition": "torn_edge_match"},
        "evidence_transform": {"camera": "object_to_portal", "transition": "shape_match"},
        "digital_memory_stack": {"camera": "phone_portal", "transition": "screen_threshold"},
        "graphic_timeline": {"camera": "guided_line_track", "transition": "color_plane_wipe"},
        "dark_semantic_reveal": {"camera": "shadow_reframe", "transition": "ink_iris"},
        "nested_collage_zoom": {"camera": "continuous_portal_zoom", "transition": "portal_match"},
    }
    return {
        "module": module,
        **contracts[module],
        "easing": "power2.inOut",
        "seek_safe": True,
    }


def build_editorial_motion_contract(
    *,
    narration_segments: list[dict[str, Any]],
    segment_timings: dict[str, dict[str, Any]],
    story_assets: dict[str, list[dict[str, Any]]],
    story_metadata: dict[str, dict[str, Any]],
    final_audio_duration_sec: float,
    style_profile: str = EDITORIAL_MOTION_STYLE_PROFILE,
) -> dict[str, Any]:
    """Build one continuous mixed-media motion plan from verified asset packs."""

    if not narration_segments or final_audio_duration_sec <= 0:
        raise EditorialMotionError("editorial narration and final duration are required")
    style_profile = str(style_profile or "").strip()
    if style_profile not in EDITORIAL_MOTION_STYLE_PROFILES:
        raise EditorialMotionError("unsupported editorial motion style profile")
    story_ids = [
        str(segment["segment_id"])
        for segment in narration_segments
        if segment.get("kind") == "story"
    ]
    if not story_ids:
        raise EditorialMotionError("editorial motion requires at least one story")
    story_packs = {
        segment_id: _group_asset_packs(story_assets.get(segment_id) or [])
        for segment_id in story_ids
    }
    if any(not packs for packs in story_packs.values()):
        raise EditorialMotionError("every editorial story requires verified asset packs")

    scenes: list[dict[str, Any]] = []
    cursor = 0.0
    completed_story_count = 0
    for segment in narration_segments:
        segment_id = str(segment.get("segment_id") or "")
        segment_kind = str(segment.get("kind") or "")
        timing = segment_timings.get(segment_id)
        if not isinstance(timing, dict):
            raise EditorialMotionError(f"missing editorial timing for {segment_id}")
        duration = float(timing.get("duration_sec") or 0)
        if duration < 0.5:
            raise EditorialMotionError(f"editorial segment {segment_id} is too short")

        if segment_kind == "story":
            packs = story_packs[segment_id]
            metadata_segment_id = segment_id
            scene_count = (
                len(packs)
                if style_profile in {
                    CINEMATIC_INK_WEBTOON_STYLE_PROFILE,
                    FORMAT_VISUAL_SYSTEM_V3_STYLE_PROFILE,
                }
                else _scene_count(duration, len(packs))
            )
            if style_profile in {
                CINEMATIC_INK_WEBTOON_STYLE_PROFILE,
                FORMAT_VISUAL_SYSTEM_V3_STYLE_PROFILE,
            } and not (
                EDITORIAL_MOTION_MIN_SCENE_SECONDS
                <= duration / scene_count
                <= EDITORIAL_MOTION_MAX_SCENE_SECONDS
            ):
                raise EditorialMotionError(
                    "cinematic ink webtoon image targets do not fit the narration duration",
                )
            completed_story_count += 1
        else:
            if segment_kind == "intro":
                metadata_segment_id = story_ids[0]
                packs = _service_scene_packs(
                    story_packs[metadata_segment_id],
                    duration=duration,
                    segment_kind=segment_kind,
                )
            elif segment_kind == "mid_story_cta":
                metadata_segment_id = story_ids[-1]
                packs = _service_scene_packs(
                    story_packs[metadata_segment_id],
                    duration=duration,
                    segment_kind=segment_kind,
                    from_end=True,
                )
            elif segment_kind == "outro":
                metadata_segment_id = story_ids[-1]
                packs = _service_scene_packs(
                    story_packs[metadata_segment_id],
                    duration=duration,
                    segment_kind=segment_kind,
                    from_end=True,
                )
            elif segment_kind == "transition":
                position = min(completed_story_count, len(story_ids) - 1)
                metadata_segment_id = story_ids[position]
                packs = _service_scene_packs(
                    story_packs[metadata_segment_id],
                    duration=duration,
                    segment_kind=segment_kind,
                )
            else:
                raise EditorialMotionError(f"unsupported segment kind {segment_kind}")
            scene_count = len(packs)

        text_parts = _word_partitions(str(segment.get("text") or ""), scene_count)
        for index in range(scene_count):
            start = cursor + duration * index / scene_count
            end = cursor + duration * (index + 1) / scene_count
            pack = packs[index]
            story_family = str(pack.get("story_family") or "")
            page_layout = str(pack.get("page_layout") or "")
            panel_grammar = str(pack.get("panel_grammar") or "")
            panel_count = pack.get("panel_count")
            panel_beat_role = str(pack.get("panel_beat_role") or "")
            if style_profile in {
                INK_GOUACHE_STORY_PAGES_STYLE_PROFILE,
                CINEMATIC_INK_WEBTOON_STYLE_PROFILE,
                FORMAT_VISUAL_SYSTEM_V3_STYLE_PROFILE,
            }:
                if (
                    story_family not in INK_GOUACHE_STORY_FAMILIES
                    or page_layout not in INK_GOUACHE_PAGE_LAYOUTS
                ):
                    raise EditorialMotionError(
                        "ink-and-gouache scenes require a supported story family and page layout",
                    )
            elif is_adult_animation_style_profile(style_profile):
                series = ADULT_ANIMATION_SERIES[style_profile]
                if (
                    story_family != series["story_family"]
                    or page_layout not in series["layouts"]
                ):
                    raise EditorialMotionError(
                        "adult-animation scenes require their profile family and approved layout",
                    )
            module = str(pack["motion_module"])
            if segment_kind == "intro":
                module = "nested_collage_zoom"
            elif segment_kind == "mid_story_cta":
                module = "evidence_transform"
            elif segment_kind == "outro":
                module = "dark_semantic_reveal"
            scene_id = f"{segment_id}-motion-{index + 1:03d}"
            text = text_parts[index]
            metadata = story_metadata.get(metadata_segment_id, {})
            scene_titles = metadata.get("scene_titles")
            if scene_titles is not None and (
                not isinstance(scene_titles, list)
                or len(scene_titles) != scene_count
                or any(not str(item).strip() for item in scene_titles)
            ):
                raise EditorialMotionError(
                    f"editorial scene_titles for {segment_id} must match scene count",
                )
            scene = {
                "slide_id": scene_id,
                "scene_id": scene_id,
                "segment_id": segment_id,
                "kind": "editorial_motion_scene",
                "presentation": segment_kind,
                "story_index": metadata.get("story_index"),
                "format_id": metadata.get("format_id"),
                "scene_number": (
                    metadata.get("format_scene_number") or index + 1
                ),
                "scene_count": (
                    metadata.get("format_scene_count") or scene_count
                ),
                "source_role": metadata.get("source_role"),
                "thread_response_number": metadata.get(
                    "thread_response_number",
                ),
                "editorial_role": metadata.get("editorial_role"),
                "voice_role": str(segment.get("voice_role") or ""),
                "start_sec": round(start, 3),
                "end_sec": round(end, 3),
                "duration_sec": round(end - start, 3),
                "narration_text": text,
                "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                "timing_source": str(timing.get("timing_source") or ""),
                "asset_family_id": pack["asset_family_id"],
                "asset_pack_sha256": pack["asset_pack_sha256"],
                "assets": pack["assets"],
                "story_family": story_family or None,
                "page_layout": page_layout or None,
                "panel_grammar": panel_grammar or None,
                "panel_count": panel_count if panel_grammar else None,
                "panel_beat_role": panel_beat_role or None,
                "motion": _motion_contract(module),
                "style_profile": style_profile,
                "truth_status": "editorial_illustration",
                "factual_text_rendering": "html_svg_only",
            }
            if (
                style_profile == FORMAT_VISUAL_SYSTEM_V3_STYLE_PROFILE
                and panel_grammar
            ):
                scene.update(build_format_visual_system_v3_semantic_camera(
                    panel_beat_role,
                    text,
                ))
            for field in ("title", "source_label", "truth_mode"):
                if metadata.get(field):
                    scene[{"title": "story_title"}.get(field, field)] = str(metadata[field])
            if scene_titles is not None:
                scene["story_title"] = str(scene_titles[index]).strip()
            scenes.append(scene)
        cursor += duration

    if abs(cursor - final_audio_duration_sec) > 0.001:
        raise EditorialMotionError("editorial scenes do not cover final audio")
    for previous, current in zip(scenes, scenes[1:]):
        if abs(float(previous["end_sec"]) - float(current["start_sec"])) > 0.001:
            raise EditorialMotionError("editorial timeline contains a gap or overlap")

    plan_payload = {
        "version": EDITORIAL_MOTION_PLAN_VERSION,
        "visual_mode": EDITORIAL_MOTION_MODE,
        "style_profile": style_profile,
        "resolution": [CANVAS_WIDTH, CANVAS_HEIGHT],
        "fps": CANVAS_FPS,
        "timeline_duration_sec": round(final_audio_duration_sec, 3),
        "scene_count": len(scenes),
        "module_usage": {
            module: sum(scene["motion"]["module"] == module for scene in scenes)
            for module in EDITORIAL_MOTION_MODULES
        },
        "scenes": scenes,
    }
    motion_plan = bind_payload(plan_payload, "motion_plan_sha256")
    captions = _caption_track(
        narration_segments, segment_timings, final_audio_duration_sec,
    )
    return {
        "scenes": scenes,
        "motion_plan": motion_plan,
        "caption_track": captions,
    }
