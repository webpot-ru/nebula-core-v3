"""Fail-closed QA for an artifact-only acc1 horror compilation."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from PIL import Image, UnidentifiedImageError

from acc1_episode_manifest import SHA256_RE, validate_episode_manifest
from acc1_episode_contract import validate_episode_script
from acc1_episode_packaging import validate_packaging as validate_episode_packaging
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
)
from compilation_metadata import validate_metadata
from compilation_narration import (
    NarrationPreflightError,
    build_compilation_segments,
    episode_truth_disclosure,
)
from compilation_renderer import preflight_storyboard
from compilation_storyboard import narration_sha256, narration_text
from episode_contract import validate_compilation
from pre_publish_qa import ffprobe_json, media_duration, stream_count, video_resolution


MAX_SECONDS_PER_SLIDE = 12.0
MIN_TIMING_COVERAGE = 0.99
THUMBNAIL_SIZE = (1280, 720)
ARTIFACT_HASH_FIELDS = (
    "script_sha256",
    "audio_sha256",
    "metadata_sha256",
    "storyboard_sha256",
    "video_sha256",
    "thumbnail_sha256",
)


def load_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def validate_tts_state(
    state: dict[str, Any],
    *,
    expected_voice_id: str | None = None,
    expected_comment_voice_id: str | None = None,
) -> list[str]:
    failures: list[str] = []
    if state.get("status") != "COMPLETE":
        failures.append("TTS state must be COMPLETE")
    if state.get("required_model_id") != "eleven_v3":
        failures.append("TTS required_model_id must be eleven_v3")
    chunks = state.get("chunks") or []
    if not isinstance(chunks, list) or not chunks:
        failures.append("TTS chunks are missing")
    for index, chunk in enumerate(chunks if isinstance(chunks, list) else []):
        if not isinstance(chunk, dict) or chunk.get("status") != "COMPLETE":
            failures.append(f"TTS chunk {index} is not COMPLETE")
            continue
        if chunk.get("model_id") != "eleven_v3":
            failures.append(f"TTS chunk {index} did not request eleven_v3")
        voice_role = chunk.get("voice_role")
        if voice_role not in {"narrator", "comment"}:
            failures.append(f"TTS chunk {index} has invalid voice_role")
        elif voice_role == "narrator":
            if expected_voice_id and chunk.get("voice_id") != expected_voice_id:
                failures.append(f"TTS chunk {index} narrator voice_id does not match expected voice")
        else:
            if not expected_comment_voice_id:
                failures.append("comment voice id is required for comment-role TTS chunks")
            elif chunk.get("voice_id") != expected_comment_voice_id:
                failures.append(f"TTS chunk {index} comment voice_id does not match expected voice")
            if expected_voice_id and chunk.get("voice_id") == expected_voice_id:
                failures.append(f"TTS chunk {index} comment role fell back to narrator voice")
        if not chunk.get("audio_sha256"):
            failures.append(f"TTS chunk {index} has no audio checksum")
    if not state.get("final_audio_sha256"):
        failures.append("TTS final audio checksum is missing")
    if not SHA256_RE.fullmatch(str(state.get("narration_plan_sha256") or "")):
        failures.append("TTS narration_plan_sha256 is missing")
    if state.get("publication_authorized") is not False:
        failures.append("TTS state publication_authorized must remain false")
    return failures


def _canonical_hash(value: dict[str, Any]) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _validate_thumbnail(path: Path | None, artifact_root: Path) -> tuple[list[str], str | None]:
    if path is None:
        return ["actual thumbnail is required"], None
    root = artifact_root.resolve()
    resolved = path.resolve()
    if resolved == root or root not in resolved.parents or not resolved.is_file():
        return ["actual thumbnail must be a file under artifact_root"], None
    try:
        with Image.open(resolved) as image:
            if image.size != THUMBNAIL_SIZE:
                return ["actual thumbnail must be 1280x720"], None
            image.verify()
    except (OSError, UnidentifiedImageError) as exc:
        return [f"actual thumbnail decode failed: {exc}"], None
    return [], hashlib.sha256(resolved.read_bytes()).hexdigest()


def _validate_audio(path: Path | None, artifact_root: Path) -> tuple[list[str], str | None]:
    if path is None:
        return ["actual final narration audio is required"], None
    root = artifact_root.resolve()
    resolved = path.resolve()
    if resolved == root or root not in resolved.parents or not resolved.is_file():
        return ["actual final narration audio must be a file under artifact_root"], None
    if resolved.stat().st_size <= 0:
        return ["actual final narration audio must not be empty"], None
    return [], _sha256_file(resolved)


def _source_identity_from_compilation(compilation: dict[str, Any]) -> list[dict[str, str]]:
    identities: list[dict[str, str]] = []
    for story in compilation.get("stories") or []:
        snapshot = story.get("source_snapshot") if isinstance(story, dict) else None
        if not isinstance(snapshot, dict):
            continue
        body = snapshot.get("body")
        body_sha256 = str(
            snapshot.get("body_sha256")
            or snapshot.get("source_body_sha256")
            or (_sha256_bytes(body.encode("utf-8")) if isinstance(body, str) else "")
        ).strip().lower()
        identities.append({
            "post_id": str(snapshot.get("post_id") or snapshot.get("source_id") or "").strip(),
            "body_sha256": body_sha256,
            "truth_mode": str(snapshot.get("truth_mode") or "").strip(),
        })
    return identities


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _validate_episode_chain(
    *,
    compilation: dict[str, Any],
    metadata: dict[str, Any],
    tts_state: dict[str, Any],
    storyboard: dict[str, Any],
    render_report: dict[str, Any],
    creative_manifest: dict[str, Any] | None,
    episode_plan: dict[str, Any] | None,
    artifact_hashes: dict[str, str] | None,
) -> tuple[list[str], str | None, str | None, dict[str, str], bool, bool]:
    failures: list[str] = []
    normalized_hashes: dict[str, str] = {}
    if not isinstance(episode_plan, dict):
        failures.append("immutable episode plan is required")
        plan_hash = None
    else:
        plan_report = validate_episode_manifest(episode_plan)
        if plan_report["status"] != "PASS":
            failures.extend(
                f"episode plan: {failure}" for failure in plan_report["failures"]
            )
        plan_hash = str(episode_plan.get("episode_plan_sha256") or "").lower() or None
    daily_plan_sha256 = (
        str(episode_plan.get("daily_plan_sha256") or "").lower() or None
        if isinstance(episode_plan, dict) else None
    )

    downstream = {
        "script": compilation,
        "metadata": metadata,
        "TTS state": tts_state,
        "storyboard": storyboard,
        "render report": render_report,
        "creative manifest": creative_manifest,
    }
    if plan_hash:
        for label, payload in downstream.items():
            if not isinstance(payload, dict) or payload.get("episode_plan_sha256") != plan_hash:
                failures.append(f"{label} episode_plan_sha256 does not match immutable plan")
            if not isinstance(payload, dict) or payload.get("daily_plan_sha256") != daily_plan_sha256:
                failures.append(f"{label} daily_plan_sha256 does not match immutable plan")

        planned_sources = [
            {
                "post_id": str(item.get("post_id") or ""),
                "body_sha256": str(item.get("body_sha256") or "").lower(),
                "truth_mode": str(item.get("truth_mode") or ""),
            }
            for item in episode_plan.get("sources") or []
            if isinstance(item, dict)
        ]
        if _source_identity_from_compilation(compilation) != planned_sources:
            failures.append("script source identities do not match immutable episode plan")

    if not isinstance(artifact_hashes, dict):
        failures.append("exact script/audio/metadata/storyboard/video/thumbnail checksums are required")
    else:
        for field in ARTIFACT_HASH_FIELDS:
            digest = str(artifact_hashes.get(field) or "").strip().lower()
            if not SHA256_RE.fullmatch(digest):
                failures.append(f"artifact_sha256.{field} must be a SHA-256 digest")
            else:
                normalized_hashes[field] = digest

    audible_disclosure = True
    metadata_disclosure = True
    chunks = tts_state.get("chunks") if isinstance(tts_state, dict) else None
    chunk_groups: dict[str, list[dict[str, Any]]] = {}
    actual_segment_order: list[str] = []
    if isinstance(chunks, list):
        for chunk in chunks:
            if not isinstance(chunk, dict):
                continue
            logical_id = str(chunk.get("logical_segment_id") or "")
            if logical_id not in chunk_groups:
                actual_segment_order.append(logical_id)
            chunk_groups.setdefault(logical_id, []).append(chunk)
            if plan_hash and chunk.get("episode_plan_sha256") != plan_hash:
                failures.append(f"TTS chunk {logical_id or 'unknown'} episode plan binding mismatch")
            if daily_plan_sha256 and chunk.get("daily_plan_sha256") != daily_plan_sha256:
                failures.append(f"TTS chunk {logical_id or 'unknown'} daily plan binding mismatch")
    try:
        expected_segments = build_compilation_segments(compilation)
    except NarrationPreflightError as exc:
        failures.append(f"accepted script cannot build the deterministic TTS plan: {exc}")
        expected_segments = []
    expected_segment_ids = {item["segment_id"] for item in expected_segments}
    if actual_segment_order != [item["segment_id"] for item in expected_segments]:
        failures.append("TTS logical segment order does not match accepted script")
    for segment in expected_segments:
        actual_text = " ".join(
            " ".join(
                str(chunk.get("text") or "")
                for chunk in chunk_groups.get(segment["segment_id"], [])
            ).split()
        )
        expected_text = " ".join(str(segment["text"]).split())
        if actual_text != expected_text:
            failures.append(
                f"TTS state text does not match accepted script segment {segment['segment_id']}"
            )
        actual_roles = {
            str(chunk.get("voice_role") or "")
            for chunk in chunk_groups.get(segment["segment_id"], [])
        }
        if actual_roles != {segment["voice_role"]}:
            failures.append(
                f"TTS state voice role does not match segment {segment['segment_id']}"
            )
    unexpected_segments = sorted(
        segment_id for segment_id in chunk_groups if segment_id not in expected_segment_ids
    )
    if unexpected_segments:
        failures.append(
            "TTS state contains unexpected logical segments: " + ", ".join(unexpected_segments)
        )
    try:
        disclosure = episode_truth_disclosure(compilation)["text"]
    except NarrationPreflightError as exc:
        failures.append(str(exc))
        disclosure = ""
        audible_disclosure = False
        metadata_disclosure = False
    if disclosure:
        spoken_all = " ".join(
            str(chunk.get("text") or "")
            for chunk in chunks if isinstance(chunk, dict)
        ) if isinstance(chunks, list) else ""
        spoken_all = " ".join(spoken_all.split())
        intro_spoken = " ".join(
            " ".join(
                str(chunk.get("text") or "") for chunk in chunk_groups.get("intro", [])
            ).split()
        )
        if spoken_all.count(disclosure) != 1 or intro_spoken.count(disclosure) != 1:
            failures.append("TTS state must contain one exact audible truth disclosure in intro")
            audible_disclosure = False
        description = " ".join(str(metadata.get("youtube_description") or "").split())
        if description.count(disclosure) != 1:
            failures.append("metadata must contain one exact visible truth disclosure")
            metadata_disclosure = False

    narration_plan_sha256 = str(tts_state.get("narration_plan_sha256") or "")
    audio_sha256 = str(tts_state.get("final_audio_sha256") or "")
    for label, payload in {
        "storyboard": storyboard,
        "render report": render_report,
        "creative manifest": creative_manifest,
    }.items():
        if not isinstance(payload, dict):
            continue
        if payload.get("narration_plan_sha256") != narration_plan_sha256:
            failures.append(f"{label} narration_plan_sha256 does not match TTS state")
        if payload.get("audio_sha256") != audio_sha256:
            failures.append(f"{label} audio_sha256 does not match TTS state")
    expected_roles = {item["segment_id"]: item["voice_role"] for item in expected_segments}
    for slide in storyboard.get("slides") or []:
        if not isinstance(slide, dict):
            continue
        segment_id = str(slide.get("segment_id") or "")
        if segment_id in expected_roles and slide.get("voice_role") != expected_roles[segment_id]:
            failures.append(f"storyboard voice_role does not match segment {segment_id}")
    return (
        failures,
        plan_hash,
        daily_plan_sha256,
        normalized_hashes,
        audible_disclosure,
        metadata_disclosure,
    )


def _validate_creative_contract(
    compilation: dict[str, Any],
    storyboard: dict[str, Any],
    render_report: dict[str, Any],
    creative_manifest: dict[str, Any] | None,
    slides: list[dict[str, Any]],
) -> list[str]:
    failures: list[str] = []
    if not isinstance(creative_manifest, dict) or not creative_manifest:
        return ["creative manifest is required"]
    if creative_manifest.get("mode") != "reddit_pages":
        failures.append("creative manifest mode must be reddit_pages")
    expected_visual_contract = {
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
    }
    if creative_manifest.get("visual_contract") != expected_visual_contract:
        failures.append("creative manifest visual contract does not match the acc1 mascot-safe geometry")
    try:
        expected_narration_sha = narration_sha256(compilation)
    except Exception as exc:
        failures.append(f"accepted narration cannot be hashed for creative manifest: {exc}")
        expected_narration_sha = None
    if expected_narration_sha is None or creative_manifest.get("narration_sha256") != expected_narration_sha:
        failures.append("creative manifest narration checksum does not match accepted script")
    try:
        manifest_coverage = float(creative_manifest.get("text_timing_coverage"))
    except (TypeError, ValueError):
        manifest_coverage = 0.0
    if manifest_coverage < MIN_TIMING_COVERAGE:
        failures.append("creative manifest text timing coverage is incomplete")
    if not slides or any(slide.get("kind") != "reddit_page" for slide in slides):
        failures.append("production storyboard must contain only timed reddit_page slides")
    segment_groups: dict[str, list[dict[str, Any]]] = {}
    for slide in slides:
        segment_id = str(slide.get("segment_id") or "")
        segment_groups.setdefault(segment_id, []).append(slide)
    for segment_id, segment_slides in segment_groups.items():
        action_indexes = [index for index, item in enumerate(segment_slides) if item.get("show_actions")]
        if _is_story_segment(segment_id):
            if action_indexes != [len(segment_slides) - 1]:
                failures.append(
                    f"reddit actions must appear once, only after the final chunk of {segment_id}"
                )
        elif action_indexes:
            failures.append(f"reddit actions are forbidden outside story segments: {segment_id}")
    schedule_entries = creative_manifest.get("story_visual_schedules")
    schedule_by_segment = {
        str(entry.get("segment_id") or ""): entry
        for entry in schedule_entries if isinstance(entry, dict)
    } if isinstance(schedule_entries, list) else {}
    for segment_id, segment_slides in segment_groups.items():
        if not _is_story_segment(segment_id):
            continue
        visual_slides = [slide for slide in segment_slides if isinstance(slide.get("visual"), dict)]
        schedule = schedule_by_segment.get(segment_id)
        if not visual_slides:
            if schedule:
                failures.append(f"visual schedule exists without verified visuals: {segment_id}")
            continue
        if not schedule:
            failures.append(f"verified story visuals require a manifest schedule: {segment_id}")
            continue
        ordered_scenes: list[tuple[str, str]] = []
        seen_scene_ids: set[str] = set()
        sha_by_scene: dict[str, str] = {}
        for slide in visual_slides:
            scene_id = str(slide.get("visual_scene_id") or "")
            visual_sha = str((slide.get("visual") or {}).get("sha256") or "")
            if not scene_id or not visual_sha:
                failures.append(f"visual slide is missing scene/checksum evidence: {segment_id}")
                continue
            if scene_id in sha_by_scene and sha_by_scene[scene_id] != visual_sha:
                failures.append(f"visual changes inside one scene: {scene_id}")
            sha_by_scene[scene_id] = visual_sha
            if scene_id not in seen_scene_ids:
                seen_scene_ids.add(scene_id)
                ordered_scenes.append((scene_id, visual_sha))
        scene_count = len(ordered_scenes)
        visual_count = len({visual_sha for _, visual_sha in ordered_scenes})
        if not MIN_VISUAL_SCENES <= scene_count <= MAX_VISUAL_SCENES:
            failures.append(
                f"{segment_id} must schedule {MIN_VISUAL_SCENES}-{MAX_VISUAL_SCENES} visual scenes"
            )
        if visual_count < min(MIN_VISUAL_SCENES, scene_count):
            failures.append(f"{segment_id} needs at least three distinct scene visuals")
        manifest_scenes = schedule.get("scenes") if isinstance(schedule.get("scenes"), list) else []
        manifest_pairs = [
            (str(scene.get("scene_id") or ""), str(scene.get("visual_sha256") or ""))
            for scene in manifest_scenes if isinstance(scene, dict)
        ]
        if int(schedule.get("scene_count") or 0) != scene_count or manifest_pairs != ordered_scenes:
            failures.append(f"visual schedule manifest does not match storyboard slides: {segment_id}")
        if int(schedule.get("visual_count") or 0) != visual_count:
            failures.append(f"visual schedule distinct-image count is wrong: {segment_id}")
    covered_text = " ".join(
        " ".join(str(slide.get("narration_text") or "").split()) for slide in slides
    ).strip()
    try:
        expected_text = narration_text(compilation)
    except Exception as exc:
        failures.append(f"accepted narration cannot be normalized for coverage: {exc}")
        expected_text = ""
    if not expected_text or covered_text != expected_text:
        failures.append("storyboard timed text does not cover the accepted narration exactly")
    if int(creative_manifest.get("page_slide_count") or 0) != len(slides):
        failures.append("creative manifest page count does not match storyboard")
    if render_report.get("creative_manifest_sha256") != _canonical_hash(creative_manifest):
        failures.append("render report is not bound to the creative manifest")
    try:
        max_slide = float(render_report.get("max_slide_duration_sec"))
    except (TypeError, ValueError):
        max_slide = 0.0
    if max_slide <= 0:
        failures.append("render report is missing max slide duration")
    elif max_slide > MAX_SECONDS_PER_SLIDE:
        failures.append(f"render has a slide longer than {MAX_SECONDS_PER_SLIDE:g} seconds")
    try:
        audio_duration = float(render_report.get("audio_duration_sec") or 0)
        planned_duration = sum(float(slide.get("duration_sec") or 0) for slide in slides)
        expected_max_slide = max(float(slide.get("duration_sec") or 0) for slide in slides) * audio_duration / planned_duration
    except (TypeError, ValueError, ZeroDivisionError):
        expected_max_slide = 0.0
    if expected_max_slide <= 0 or abs(max_slide - expected_max_slide) > 0.05:
        failures.append("render max slide duration is not bound to storyboard/audio timing")
    for key in ("slide_timing_coverage", "text_timing_coverage"):
        try:
            coverage = float(render_report.get(key))
        except (TypeError, ValueError):
            coverage = 0.0
        if coverage < MIN_TIMING_COVERAGE:
            failures.append(f"render report {key} is incomplete")
    if int(render_report.get("reddit_page_count") or 0) != len(slides):
        failures.append("render report reddit page count does not match storyboard")
    background = storyboard.get("background_video")
    background_required = creative_manifest.get("background_video_required") is True
    if isinstance(background, dict):
        if not background_required:
            failures.append("storyboard background video is not declared in the creative manifest")
        if render_report.get("background_video_used") is not True:
            failures.append("render report did not use the storyboard background video")
        if render_report.get("background_video_sha256") != background.get("sha256"):
            failures.append("render report background checksum does not match storyboard")
        if render_report.get("background_audio_discarded") is not True:
            failures.append("render report did not confirm background audio discard")
    else:
        if background_required:
            failures.append("creative manifest requires a background video but storyboard has none")
        if render_report.get("background_video_used"):
            failures.append("render report used an undeclared background video")
    if render_report.get("mascot_safe_x") != MASCOT_SAFE_X:
        failures.append("render report does not confirm the mascot-safe boundary")
    return failures


def _is_story_segment(segment_id: str) -> bool:
    return segment_id.startswith("story-") or segment_id.startswith("story_")


def _runtime_target(
    target_duration_minutes: list[float] | tuple[float, float] | None,
) -> tuple[float, float] | None:
    if target_duration_minutes is None:
        return None
    if not isinstance(target_duration_minutes, (list, tuple)) or len(target_duration_minutes) != 2:
        raise ValueError("target_duration_minutes must contain exactly [minimum, maximum]")
    minimum, maximum = (float(value) for value in target_duration_minutes)
    if minimum <= 0 or maximum <= minimum:
        raise ValueError("target_duration_minutes must be positive and strictly increasing")
    return minimum, maximum


def run_qa(
    compilation: dict[str, Any],
    metadata: dict[str, Any],
    tts_state: dict[str, Any],
    storyboard: dict[str, Any],
    render_report: dict[str, Any],
    *,
    artifact_root: Path,
    video_path: Path | None = None,
    thumbnail_path: Path | None = None,
    creative_manifest: dict[str, Any] | None = None,
    expected_voice_id: str | None = None,
    expected_comment_voice_id: str | None = None,
    episode_plan: dict[str, Any] | None = None,
    artifact_hashes: dict[str, str] | None = None,
    audio_path: Path | None = None,
    topic_playoff: dict[str, Any] | None = None,
    target_duration_minutes: list[float] | tuple[float, float] | None = None,
) -> dict[str, Any]:
    failures: list[str] = []
    warnings: list[str] = []
    generic_episode = bool(str(compilation.get("episode_format") or "").strip())
    if generic_episode:
        if not isinstance(episode_plan, dict):
            script_contract = {
                "status": "BLOCKED", "failures": ["immutable episode plan is required"],
                "story_count": len(compilation.get("stories") or []),
            }
        elif not isinstance(topic_playoff, dict):
            script_contract = {
                "status": "BLOCKED", "failures": ["exact topic playoff is required"],
                "story_count": len(compilation.get("stories") or []),
            }
        else:
            script_contract = validate_episode_script(
                compilation, plan=episode_plan, playoff=topic_playoff,
            )
        failures.extend(script_contract.get("failures") or [])
        failures.extend(validate_episode_packaging(metadata, compilation))
        contract = {
            "story_count": script_contract.get("story_count", len(compilation.get("stories") or [])),
            "estimated_minutes": None,
            "warnings": [],
        }
    else:
        contract = validate_compilation(compilation)
        failures.extend(contract["failures"])
        warnings.extend(contract["warnings"])
        failures.extend(validate_metadata(metadata, compilation))
    failures.extend(validate_tts_state(
        tts_state,
        expected_voice_id=expected_voice_id,
        expected_comment_voice_id=expected_comment_voice_id,
    ))
    try:
        slides = preflight_storyboard(storyboard, artifact_root)
    except Exception as exc:
        failures.append(f"storyboard preflight failed: {exc}")
        slides = []
    embedded_manifest = storyboard.get("creative_manifest")
    if creative_manifest is None and isinstance(embedded_manifest, dict):
        creative_manifest = embedded_manifest
    elif creative_manifest is not None and embedded_manifest != creative_manifest:
        failures.append("external creative manifest does not match storyboard manifest")
    (
        episode_failures,
        episode_plan_sha256,
        daily_plan_sha256,
        normalized_artifact_hashes,
        audible_disclosure,
        metadata_disclosure,
    ) = _validate_episode_chain(
        compilation=compilation,
        metadata=metadata,
        tts_state=tts_state,
        storyboard=storyboard,
        render_report=render_report,
        creative_manifest=creative_manifest,
        episode_plan=episode_plan,
        artifact_hashes=artifact_hashes,
    )
    failures.extend(episode_failures)
    failures.extend(_validate_creative_contract(
        compilation, storyboard, render_report, creative_manifest, slides,
    ))
    audio_failures, audio_sha256 = _validate_audio(audio_path, artifact_root)
    failures.extend(audio_failures)
    if audio_sha256:
        if tts_state.get("final_audio_sha256") != audio_sha256:
            failures.append("TTS final audio checksum does not match actual narration audio")
        if render_report.get("audio_sha256") != audio_sha256:
            failures.append("render report audio checksum does not match actual narration audio")
        if normalized_artifact_hashes.get("audio_sha256") != audio_sha256:
            failures.append("artifact audio checksum does not match actual narration audio")
    thumbnail_failures, thumbnail_sha256 = _validate_thumbnail(thumbnail_path, artifact_root)
    failures.extend(thumbnail_failures)
    if thumbnail_sha256 and normalized_artifact_hashes.get("thumbnail_sha256") != thumbnail_sha256:
        failures.append("artifact thumbnail checksum does not match actual thumbnail")
    if render_report.get("status") != "ok":
        failures.append("render report status must be ok")
    if render_report.get("resolution") != [1920, 1080]:
        failures.append("render report resolution must be 1920x1080")
    if not render_report.get("audio_merged"):
        failures.append("render report must confirm merged audio")
    try:
        render_duration = float(render_report.get("duration_sec") or 0)
        audio_duration = float(render_report.get("audio_duration_sec") or 0)
    except (TypeError, ValueError):
        render_duration = audio_duration = 0
    if render_duration <= 0 or audio_duration <= 0 or abs(render_duration - audio_duration) > 1.0:
        failures.append("render/audio duration mismatch exceeds 1 second")
    try:
        runtime_target = _runtime_target(target_duration_minutes)
    except (TypeError, ValueError) as exc:
        runtime_target = None
        failures.append(f"invalid runtime target: {exc}")
    if runtime_target is not None:
        minimum_minutes, maximum_minutes = runtime_target
        actual_minutes = audio_duration / 60.0
        if not minimum_minutes <= actual_minutes <= maximum_minutes:
            failures.append(
                "actual narration duration "
                f"{actual_minutes:.2f} minutes is outside the locked "
                f"{minimum_minutes:g}-{maximum_minutes:g} minute target"
            )
    video_sha256: str | None = None
    if video_path is not None:
        if not video_path.is_file():
            failures.append("final MP4 is missing")
        else:
            video_sha256 = _sha256_file(video_path)
            if render_report.get("video_sha256") != video_sha256:
                failures.append("render report video checksum does not match final MP4")
            if normalized_artifact_hashes.get("video_sha256") != video_sha256:
                failures.append("artifact video checksum does not match final MP4")
            probe = ffprobe_json(video_path)
            if stream_count(probe, "video") != 1 or stream_count(probe, "audio") != 1:
                failures.append("final MP4 must have one video and one audio stream")
            if video_resolution(probe) != "1920x1080":
                failures.append("final MP4 resolution must be 1920x1080")
            duration = media_duration(probe)
            if not duration or abs(duration - audio_duration) > 1.0:
                failures.append("final MP4 duration does not match narration")
    return {
        "status": "PASS" if not failures else "BLOCKED",
        "publication_authorized": False,
        "failures": failures,
        "warnings": warnings,
        "story_count": contract["story_count"],
        "estimated_minutes": contract["estimated_minutes"],
        "slide_count": len(slides),
        "episode_plan_sha256": episode_plan_sha256,
        "daily_plan_sha256": daily_plan_sha256,
        "artifact_sha256": {
            field: normalized_artifact_hashes.get(field) for field in ARTIFACT_HASH_FIELDS
        },
        "truth_disclosure_audible": audible_disclosure,
        "truth_disclosure_visible_in_metadata": metadata_disclosure,
        "video_sha256": video_sha256,
        "thumbnail_sha256": thumbnail_sha256,
        "expected_voice_id_checked": bool(expected_voice_id),
        "expected_comment_voice_id_checked": (
            bool(expected_comment_voice_id)
            if any(
                isinstance(chunk, dict) and chunk.get("voice_role") == "comment"
                for chunk in tts_state.get("chunks") or []
            ) else True
        ),
        "runtime_target_minutes": (
            list(runtime_target) if runtime_target is not None else None
        ),
        "actual_runtime_minutes": round(audio_duration / 60.0, 3) if audio_duration > 0 else None,
        "topic_playoff_sha256": (
            str(topic_playoff.get("playoff_sha256") or "")
            if isinstance(topic_playoff, dict) else None
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compilation", required=True)
    parser.add_argument("--metadata", required=True)
    parser.add_argument("--tts-state", required=True)
    parser.add_argument("--storyboard", required=True)
    parser.add_argument("--render-report", required=True)
    parser.add_argument("--episode-plan", required=True)
    parser.add_argument("--topic-playoff", help="Required exact playoff for generic SAGA/BUNDLE/THREAD scripts.")
    parser.add_argument("--artifact-root", required=True)
    parser.add_argument("--audio", required=True)
    parser.add_argument("--video", required=True)
    parser.add_argument("--thumbnail", required=True, help="Required 1280x720 thumbnail under artifact-root.")
    parser.add_argument("--creative-manifest", help="Optional JSON sidecar; embedded storyboard manifest is accepted.")
    parser.add_argument("--expected-voice-id", help="Fail if any TTS chunk used a different voice.")
    parser.add_argument("--expected-comment-voice-id", help="Required when comment-role TTS is present.")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    compilation_path = Path(args.compilation)
    metadata_path = Path(args.metadata)
    storyboard_path = Path(args.storyboard)
    audio_path = Path(args.audio)
    video_path = Path(args.video)
    thumbnail_path = Path(args.thumbnail)
    result = run_qa(
        load_object(compilation_path), load_object(metadata_path),
        load_object(Path(args.tts_state)), load_object(storyboard_path),
        load_object(Path(args.render_report)), artifact_root=Path(args.artifact_root),
        video_path=video_path,
        thumbnail_path=thumbnail_path,
        creative_manifest=load_object(Path(args.creative_manifest)) if args.creative_manifest else None,
        expected_voice_id=args.expected_voice_id,
        expected_comment_voice_id=args.expected_comment_voice_id,
        episode_plan=load_object(Path(args.episode_plan)),
        artifact_hashes={
            "script_sha256": _sha256_file(compilation_path),
            "audio_sha256": _sha256_file(audio_path),
            "metadata_sha256": _sha256_file(metadata_path),
            "storyboard_sha256": _sha256_file(storyboard_path),
            "video_sha256": _sha256_file(video_path),
            "thumbnail_sha256": _sha256_file(thumbnail_path),
        },
        audio_path=audio_path,
        topic_playoff=(
            load_object(Path(args.topic_playoff)) if args.topic_playoff else None
        ),
    )
    Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
