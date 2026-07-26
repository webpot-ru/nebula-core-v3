"""Fail-closed QA for an artifact-only acc1 horror compilation."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from PIL import Image, UnidentifiedImageError

from acc1_cinematic_shots import verify_bound_payload
from acc1_episode_manifest import SHA256_RE, validate_episode_manifest
from acc1_episode_contract import validate_episode_script
from acc1_episode_packaging import validate_packaging as validate_episode_packaging
from acc1_visual_contract import (
    CINEMATIC_CAPTION_TRACK_VERSION,
    CINEMATIC_PAN_CENTER_MAX,
    CINEMATIC_PAN_CENTER_MIN,
    CINEMATIC_SERVICE_SHOT_MAX_SECONDS,
    CINEMATIC_SHOT_PLAN_VERSION,
    CINEMATIC_STORY_MODE,
    CINEMATIC_STORY_SHOT_MAX_SECONDS,
    CINEMATIC_STORY_SHOT_MIN_SECONDS,
    CINEMATIC_ZOOM_END_MAX,
    CINEMATIC_ZOOM_END_MIN,
    CONTRACT_VERSION as VISUAL_CONTRACT_VERSION,
    DEFAULT_VISUAL_MODE,
    MAX_VISUAL_SCENES,
    MIN_VISUAL_SCENES,
    MASCOT_SAFE_X,
    READABILITY_SHADE_ALPHA,
    STORY_VISUAL_BRIGHTNESS,
    STORY_VISUAL_FEATHER_END_X,
    STORY_VISUAL_FEATHER_START_X,
    TEXT_LEFT_X,
    TEXT_RIGHT_X,
    resolve_visual_mode,
)
from compilation_audio_mix import (
    AUDIO_MIX_REPORT_VERSION,
    PAUSE_MAP_VERSION,
    verify_self_hash as verify_audio_sidecar_hash,
)
from acc1_narration_profiles import (
    NarrationProfileError,
    canonical_hash,
    resolve_narration_profile,
    verify_narration_boundary_contract,
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


# Word-aligned AI33 narration can cross a natural punctuation boundary a few
# hundred milliseconds after the 12-second planning target.  Preserve that
# natural phrase rather than splitting a Reddit page mid-clause; anything past
# this narrow tolerance remains a hard QA block.
MAX_SECONDS_PER_SLIDE = 12.25
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
    expected_narration_profile_id: str | None = None,
    expected_narration_profile_sha256: str | None = None,
    expected_narration_boundary_contract: dict[str, Any] | None = None,
) -> list[str]:
    failures: list[str] = []
    if state.get("status") != "COMPLETE":
        failures.append("TTS state must be COMPLETE")
    if state.get("required_model_id") != "eleven_v3":
        failures.append("TTS required_model_id must be eleven_v3")
    chunks = state.get("chunks") or []
    if not isinstance(chunks, list) or not chunks:
        failures.append("TTS chunks are missing")
    if expected_narration_profile_id:
        if state.get("narration_profile_id") != expected_narration_profile_id:
            failures.append("TTS narration_profile_id does not match episode plan")
        if (
            state.get("narration_profile_sha256")
            != expected_narration_profile_sha256
        ):
            failures.append("TTS narration profile checksum does not match episode plan")
    if expected_narration_boundary_contract is not None:
        contract = expected_narration_boundary_contract
        if not verify_narration_boundary_contract(contract):
            failures.append("episode-plan narration boundary contract checksum is invalid")
        if state.get("narration_boundary_contract") != contract:
            failures.append("TTS narration boundary contract does not match episode plan")
        for field, expected in (
            (
                "narration_boundary_contract_sha256",
                contract.get("narration_boundary_contract_sha256"),
            ),
            ("narration_boundary_policy_id", contract.get("policy_id")),
            ("episode_format", contract.get("episode_format")),
            ("boundary_source_count", contract.get("source_count")),
        ):
            if state.get(field) != expected:
                failures.append(f"TTS {field} does not match episode plan")
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
        if expected_narration_profile_id:
            if chunk.get("narration_profile_id") != expected_narration_profile_id:
                failures.append(
                    f"TTS chunk {index} narration_profile_id does not match episode plan",
                )
            if (
                chunk.get("narration_profile_sha256")
                != expected_narration_profile_sha256
            ):
                failures.append(
                    f"TTS chunk {index} narration profile checksum changed",
                )
        if expected_narration_boundary_contract is not None:
            contract = expected_narration_boundary_contract
            if (
                chunk.get("narration_boundary_contract_sha256")
                != contract.get("narration_boundary_contract_sha256")
                or chunk.get("narration_boundary_policy_id")
                != contract.get("policy_id")
                or chunk.get("episode_format") != contract.get("episode_format")
                or chunk.get("boundary_source_count") != contract.get("source_count")
            ):
                failures.append(
                    f"TTS chunk {index} narration boundary contract changed",
                )
            expected_speed = _number(contract.get("base_speed"), default=-1)
            if (
                contract.get("episode_format") == "BUNDLE"
                and chunk.get("logical_segment_kind") == "transition"
            ):
                expected_speed = _number(
                    contract.get("effective_transition_speed"),
                    default=-1,
                )
            if abs(_number(chunk.get("effective_speed"), default=-1) - expected_speed) > 1e-9:
                failures.append(
                    f"TTS chunk {index} effective speed violates the boundary contract",
                )
    if expected_narration_boundary_contract is not None and isinstance(chunks, list):
        transition_ids = {
            str(chunk.get("logical_segment_id") or "")
            for chunk in chunks
            if isinstance(chunk, dict)
            and chunk.get("logical_segment_kind") == "transition"
        }
        if len(transition_ids) != _integer(
            expected_narration_boundary_contract.get("spoken_transition_count"),
            default=-1,
        ):
            failures.append("TTS spoken transition count violates the boundary contract")
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


def _srt_cues(path: Path) -> list[tuple[float, float, str]] | None:
    """Parse the intentionally simple deterministic SRT emitted by this project."""
    try:
        blocks = path.read_text(encoding="utf-8").replace("\r\n", "\n").strip().split("\n\n")
    except OSError:
        return None
    cues: list[tuple[float, float, str]] = []
    for expected_index, block in enumerate(blocks, start=1):
        lines = block.splitlines()
        if len(lines) < 3 or lines[0].strip() != str(expected_index) or " --> " not in lines[1]:
            return None
        try:
            start_raw, end_raw = lines[1].split(" --> ", 1)
            def seconds(raw: str) -> float:
                hours, minutes, rest = raw.strip().split(":")
                secs, millis = rest.split(",")
                return int(hours) * 3600 + int(minutes) * 60 + int(secs) + int(millis) / 1000
            start, end = seconds(start_raw), seconds(end_raw)
        except (ValueError, TypeError):
            return None
        cues.append((start, end, "\n".join(lines[2:]).strip()))
    return cues


def _number(value: object, *, default: float = 0.0) -> float:
    """Return a finite numeric value without letting malformed sidecars escape QA."""
    try:
        result = float(value)
    except (TypeError, ValueError):
        return default
    return result if result == result and result not in (float("inf"), float("-inf")) else default


def _integer(value: object, *, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return default


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


def _validate_audio_mix_chain(
    *,
    tts_state: dict[str, Any],
    pause_map: dict[str, Any] | None,
    audio_mix_report: dict[str, Any] | None,
    episode_plan: dict[str, Any] | None,
    storyboard: dict[str, Any],
    render_report: dict[str, Any],
    creative_manifest: dict[str, Any] | None,
    actual_audio_sha256: str | None,
) -> tuple[list[str], str]:
    """Validate profile -> chunks -> pauses -> measured mix -> render bindings."""

    failures: list[str] = []
    raw_audio_sha256 = str(tts_state.get("final_audio_sha256") or "").lower()
    plan_version = _integer((episode_plan or {}).get("version") or 1, default=0)
    mix_contract = (episode_plan or {}).get("audio_mix_contract")
    required = (
        plan_version >= 2
        and isinstance(mix_contract, dict)
        and mix_contract.get("required") is True
    )
    if pause_map is None and audio_mix_report is None and not required:
        return failures, raw_audio_sha256
    if not isinstance(pause_map, dict) or not isinstance(audio_mix_report, dict):
        return ["pause map and audio mix report are required by episode plan"], raw_audio_sha256
    if not verify_audio_sidecar_hash(pause_map, "pause_map_sha256"):
        failures.append("pause map self-hash is invalid")
    if not verify_audio_sidecar_hash(
        audio_mix_report, "audio_mix_report_sha256",
    ):
        failures.append("audio mix report self-hash is invalid")
    if pause_map.get("status") != "PASS":
        failures.append("pause map status must be PASS")
    if audio_mix_report.get("status") != "PASS":
        failures.append("audio mix report status must be PASS")
    if (
        pause_map.get("publication_authorized") is not False
        or audio_mix_report.get("publication_authorized") is not False
    ):
        failures.append("audio sidecars must not authorize publication")

    if required:
        if pause_map.get("version") != PAUSE_MAP_VERSION:
            failures.append("pause map version does not match the v2 contract")
        if audio_mix_report.get("version") != AUDIO_MIX_REPORT_VERSION:
            failures.append("audio mix report version does not match the v2 contract")
        if pause_map.get("network_used") is not False or audio_mix_report.get("network_used") is not False:
            failures.append("audio sidecars must confirm network_used=false")
        if audio_mix_report.get("mode") != "voice_only":
            failures.append("audio mix report must be voice_only")
        if audio_mix_report.get("failures") != []:
            failures.append("audio mix report must contain no failures")

    binding_fields = [
        "episode_plan_sha256",
        "daily_plan_sha256",
        "narration_plan_sha256",
        "timing_contract_sha256",
        "narration_profile_id",
        "narration_profile_sha256",
    ]
    if tts_state.get("narration_boundary_contract") is not None:
        binding_fields.extend([
            "narration_boundary_contract",
            "narration_boundary_contract_sha256",
            "narration_boundary_policy_id",
            "episode_format",
            "boundary_source_count",
        ])
    for field in binding_fields:
        expected = tts_state.get(field)
        if pause_map.get(field) != expected:
            failures.append(f"pause map {field} does not match TTS state")
        if audio_mix_report.get(field) != expected:
            failures.append(f"audio mix report {field} does not match TTS state")
    if (
        audio_mix_report.get("pause_map_sha256")
        != pause_map.get("pause_map_sha256")
    ):
        failures.append("audio mix report does not bind the exact pause map")

    chunks = tts_state.get("chunks") if isinstance(tts_state.get("chunks"), list) else []
    entries = pause_map.get("entries") if isinstance(pause_map.get("entries"), list) else []
    if len(entries) != len(chunks) or not entries:
        failures.append("pause map must contain exactly one entry per TTS chunk")
    cursor = 0.0
    voice_total = 0.0
    pause_total = 0.0
    input_chunks: list[dict[str, Any]] = []
    for index, (chunk, entry) in enumerate(zip(chunks, entries)):
        if not isinstance(chunk, dict) or not isinstance(entry, dict):
            failures.append(f"pause map entry {index} is invalid")
            continue
        values = [
            _number(chunk.get("audio_duration_sec")), _number(entry.get("timeline_audio_start_sec")),
            _number(entry.get("timeline_audio_end_sec")), _number(entry.get("timeline_pause_start_sec")),
            _number(entry.get("timeline_pause_end_sec")), _number(entry.get("pause_after_sec")),
        ]
        duration, audio_start, audio_end, pause_start, pause_end, pause_after = values
        if duration <= 0 or audio_start < 0 or pause_after < 0:
            failures.append(f"pause map entry {index} duration is invalid")
            continue
        if (
            entry.get("chunk_id") != chunk.get("chunk_id")
            or entry.get("logical_segment_id") != chunk.get("logical_segment_id")
            or entry.get("audio_sha256") != chunk.get("audio_sha256")
            or entry.get("word_timings_sha256")
            != chunk.get("word_timings_sha256")
            or abs(_number(entry.get("audio_duration_sec")) - duration) > 0.001
            or abs(audio_start - cursor) > 0.001
            or abs(audio_end - (audio_start + duration)) > 0.001
            or abs(pause_start - audio_end) > 0.001
            or abs(pause_end - (pause_start + pause_after)) > 0.001
        ):
            failures.append(f"pause map entry {index} changed chunk/timeline identity")
        if required:
            try:
                canonical_pause = None
                profile = resolve_narration_profile(
                    str(tts_state.get("narration_profile_id") or ""),
                    pillar_id=str(tts_state.get("narration_pillar_id") or ""),
                )
                pause_contract = profile["pause_after"]
                if index == len(chunks) - 1:
                    expected_kind, canonical_pause = "none", 0.0
                elif chunk.get("is_last_in_segment") is True:
                    expected_kind = "segment"
                    canonical_pause = _number(
                        (pause_contract.get("segment_seconds") or {}).get(
                            chunk.get("logical_segment_kind"),
                        ), default=-1,
                    )
                elif chunk.get("is_last_in_beat") is True:
                    expected_kind, canonical_pause = "beat", _number(pause_contract.get("beat_seconds"), default=-1)
                else:
                    expected_kind, canonical_pause = "intra_beat", _number(pause_contract.get("intra_beat_seconds"), default=-1)
                if entry.get("pause_kind") != expected_kind or abs(pause_after - canonical_pause) > 0.001:
                    failures.append(f"pause map entry {index} violates the canonical pause contract")
            except (NarrationProfileError, TypeError, KeyError):
                failures.append(f"pause map entry {index} cannot resolve the canonical pause contract")
        cursor = pause_end
        voice_total += duration
        pause_total += pause_after
        input_chunks.append({
            "chunk_id": chunk.get("chunk_id"), "audio_path": chunk.get("audio_path"),
            "audio_sha256": chunk.get("audio_sha256"), "audio_duration_sec": chunk.get("audio_duration_sec"),
            "timing_source": chunk.get("timing_source"), "word_timings_sha256": chunk.get("word_timings_sha256"),
        })
    pause_duration = _number(pause_map.get("timeline_duration_sec"))
    expected_duration = _number(audio_mix_report.get("expected_timeline_duration_sec"))
    measured_duration = _number(audio_mix_report.get("output_duration_sec"))
    tolerance = _number(audio_mix_report.get("duration_tolerance_sec"))
    if (
        pause_duration <= 0
        or abs(cursor - pause_duration) > 0.001
        or abs(expected_duration - pause_duration) > 0.001
        or measured_duration <= 0
        or abs(measured_duration - pause_duration) > max(0.05, tolerance) + 0.001
    ):
        failures.append("audio mix duration does not match the pause-map timeline")

    if required and (
        abs(_number(pause_map.get("voice_duration_sec")) - voice_total) > 0.001
        or abs(_number(pause_map.get("pause_duration_sec")) - pause_total) > 0.001
        or pause_map.get("input_chunks_sha256") != canonical_hash(input_chunks)
        or audio_mix_report.get("input_chunks") != input_chunks
        or audio_mix_report.get("input_chunks_sha256") != canonical_hash(input_chunks)
    ):
        failures.append("audio sidecar voice/pause totals or input chunk contract changed")

    output_sha256 = str(audio_mix_report.get("output_sha256") or "").lower()
    if not SHA256_RE.fullmatch(output_sha256):
        failures.append("audio mix report output_sha256 is invalid")
    if actual_audio_sha256 and output_sha256 != actual_audio_sha256:
        failures.append("audio mix output checksum does not match actual final audio")

    if required:
        if not isinstance(mix_contract, dict):
            failures.append("episode plan audio_mix_contract is missing")
        else:
            if mix_contract.get("narration_profile_id") != tts_state.get(
                "narration_profile_id",
            ):
                failures.append("audio mix contract narration profile id changed")
            if mix_contract.get("narration_profile_sha256") != tts_state.get(
                "narration_profile_sha256",
            ):
                failures.append("audio mix contract narration profile checksum changed")
            target = mix_contract.get("voice_only_loudness") or {}
            loudness = audio_mix_report.get("loudness") or {}
            if (
                _number(loudness.get("target_integrated_lufs")) != _number(target.get("integrated_lufs"))
                or _number(loudness.get("tolerance_lu")) != _number(target.get("tolerance_lu"))
                or _number(loudness.get("max_true_peak_dbtp")) != _number(target.get("max_true_peak_dbtp"))
            ):
                failures.append("measured loudness target does not match episode plan")
            measured_lufs = _number(loudness.get("measured_integrated_lufs"), default=float("inf"))
            measured_peak = _number(loudness.get("measured_true_peak_dbtp"), default=float("inf"))
            if (
                abs(measured_lufs - _number(target.get("integrated_lufs"))) > _number(target.get("tolerance_lu"))
                or measured_peak > _number(target.get("max_true_peak_dbtp")) + 0.05
            ):
                failures.append("audio mix measured loudness/true-peak values do not pass plan target")
            if (
                loudness.get("integrated_loudness_pass") is not True
                or loudness.get("true_peak_pass") is not True
            ):
                failures.append("audio mix loudness/true-peak gate did not pass")

            planned_tts = (episode_plan.get("provider_settings") or {}).get(
                "tts",
            )
            planned_boundary = (
                planned_tts.get("narration_boundary_contract")
                if isinstance(planned_tts, dict)
                else None
            )
            if planned_boundary is not None:
                if not isinstance(planned_boundary, dict) or not (
                    verify_narration_boundary_contract(planned_boundary)
                ):
                    failures.append(
                        "episode plan narration boundary contract checksum is invalid"
                    )
                elif tts_state.get("narration_boundary_contract") != planned_boundary:
                    failures.append(
                        "TTS narration boundary contract does not match episode plan"
                    )

        try:
            profile = resolve_narration_profile(
                str(tts_state.get("narration_profile_id") or ""),
                pillar_id=str(tts_state.get("narration_pillar_id") or ""),
            )
        except NarrationProfileError:
            failures.append("TTS narration profile cannot be resolved canonically")
        else:
            if (
                pause_map.get("pause_contract") != profile["pause_after"]
                or pause_map.get("pause_contract_sha256") != canonical_hash(profile["pause_after"])
            ):
                failures.append("pause map does not use the canonical narration-profile pause contract")

    for label, payload in (
        ("storyboard", storyboard),
        ("creative manifest", creative_manifest),
        ("render report", render_report),
    ):
        if not isinstance(payload, dict):
            continue
        if payload.get("pause_map_sha256") != pause_map.get("pause_map_sha256"):
            failures.append(f"{label} pause_map_sha256 does not match final mix")
        if payload.get("audio_mix_report_sha256") != audio_mix_report.get(
            "audio_mix_report_sha256",
        ):
            failures.append(f"{label} audio_mix_report_sha256 does not match final mix")
        if payload.get("audio_sha256") != output_sha256:
            failures.append(f"{label} audio checksum does not match final mix")
        if required and (
            abs(_number(payload.get("timeline_duration_sec"), default=measured_duration) - measured_duration) > max(0.05, tolerance) + 0.001
            if label == "storyboard" else False
        ):
            failures.append("storyboard timeline duration does not match final mix")
    if required and abs(_number(render_report.get("audio_duration_sec")) - measured_duration) > max(0.05, tolerance) + 0.001:
        failures.append("render audio duration does not match final mix")
    return failures, output_sha256 or raw_audio_sha256


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
    expected_final_audio_sha256: str | None = None,
) -> tuple[list[str], str | None, str | None, dict[str, str], bool, bool]:
    failures: list[str] = []
    normalized_hashes: dict[str, str] = {}
    if not isinstance(episode_plan, dict):
        failures.append("immutable episode plan is required")
        plan_hash = None
    else:
        try:
            plan_report = validate_episode_manifest(episode_plan)
        except (TypeError, ValueError, KeyError, OverflowError) as exc:
            plan_report = {"status": "BLOCKED", "failures": [f"malformed manifest: {exc}"]}
        if plan_report["status"] != "PASS":
            failures.extend(
                f"episode plan: {failure}" for failure in plan_report["failures"]
            )
        plan_hash = str(episode_plan.get("episode_plan_sha256") or "").lower() or None
    daily_plan_sha256 = (
        str(episode_plan.get("daily_plan_sha256") or "").lower() or None
        if isinstance(episode_plan, dict) else None
    )
    if isinstance(episode_plan, dict) and _integer(episode_plan.get("version") or 1, default=0) >= 2:
        planned_mode = str(episode_plan.get("visual_mode") or "")
        planned_profile_id = str(episode_plan.get("narration_profile_id") or "")
        planned_profile_sha256 = str(
            episode_plan.get("narration_profile_sha256") or "",
        )
        for label, payload in (
            ("script", compilation),
            ("storyboard", storyboard),
            ("creative manifest", creative_manifest),
            ("render report", render_report),
        ):
            if not isinstance(payload, dict):
                continue
            payload_mode = payload.get("visual_mode", payload.get("mode"))
            if payload_mode != planned_mode:
                failures.append(f"{label} visual_mode does not match episode plan")
        if tts_state.get("narration_profile_id") != planned_profile_id:
            failures.append("TTS narration_profile_id does not match episode plan")
        if tts_state.get("narration_profile_sha256") != planned_profile_sha256:
            failures.append("TTS narration profile checksum does not match episode plan")
        planned_tts = (episode_plan.get("provider_settings") or {}).get("tts")
        planned_boundary = (
            planned_tts.get("narration_boundary_contract")
            if isinstance(planned_tts, dict)
            else None
        )
        if planned_boundary is not None:
            if compilation.get("narration_boundary_contract") != planned_boundary:
                failures.append(
                    "script narration boundary contract does not match episode plan"
                )
            if tts_state.get("narration_boundary_contract") != planned_boundary:
                failures.append(
                    "TTS narration boundary contract does not match episode plan"
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
    audio_sha256 = str(
        expected_final_audio_sha256
        or tts_state.get("final_audio_sha256")
        or "",
    )
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


def _validate_reddit_creative_contract(
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


def _validate_cinematic_creative_contract(
    compilation: dict[str, Any],
    storyboard: dict[str, Any],
    render_report: dict[str, Any],
    creative_manifest: dict[str, Any] | None,
    slides: list[dict[str, Any]],
    artifact_root: Path,
) -> list[str]:
    failures: list[str] = []
    if not isinstance(creative_manifest, dict) or not creative_manifest:
        return ["creative manifest is required"]
    if (
        storyboard.get("visual_mode") != CINEMATIC_STORY_MODE
        or creative_manifest.get("mode") != CINEMATIC_STORY_MODE
        or render_report.get("visual_mode") != CINEMATIC_STORY_MODE
    ):
        failures.append("cinematic visual_mode must match across storyboard/render")
    if int(storyboard.get("version") or 0) != 3:
        failures.append("cinematic storyboard version must be 3")
    expected_visual_contract = {
        "version": VISUAL_CONTRACT_VERSION,
        "shot_plan_version": CINEMATIC_SHOT_PLAN_VERSION,
        "caption_track_version": CINEMATIC_CAPTION_TRACK_VERSION,
        "story_shot_min_seconds": CINEMATIC_STORY_SHOT_MIN_SECONDS,
        "story_shot_max_seconds": CINEMATIC_STORY_SHOT_MAX_SECONDS,
        "service_shot_max_seconds": CINEMATIC_SERVICE_SHOT_MAX_SECONDS,
        "zoom_end_min": CINEMATIC_ZOOM_END_MIN,
        "zoom_end_max": CINEMATIC_ZOOM_END_MAX,
        "full_screen_images": True,
    }
    if creative_manifest.get("visual_contract") != expected_visual_contract:
        failures.append("cinematic visual contract does not match canonical bounds")
    try:
        expected_narration_sha = narration_sha256(compilation)
        expected_text = narration_text(compilation)
    except Exception as exc:
        failures.append(f"accepted narration cannot be hashed for cinematic QA: {exc}")
        expected_narration_sha = None
        expected_text = ""
    if creative_manifest.get("narration_sha256") != expected_narration_sha:
        failures.append("cinematic narration checksum does not match accepted script")
    try:
        coverage = float(creative_manifest.get("text_timing_coverage") or 0)
    except (TypeError, ValueError):
        coverage = 0.0
    if coverage < MIN_TIMING_COVERAGE:
        failures.append("cinematic text timing coverage is incomplete")
    if not slides or any(slide.get("kind") != "cinematic_shot" for slide in slides):
        failures.append("cinematic storyboard must contain only cinematic_shot slides")

    covered_text = " ".join(
        " ".join(str(slide.get("narration_text") or "").split())
        for slide in slides
    ).strip()
    if not expected_text or covered_text != expected_text:
        failures.append("cinematic shots do not cover accepted narration exactly")
    if storyboard.get("background_video") not in (None, ""):
        failures.append("cinematic storyboard must not use the mascot background loop")
    if creative_manifest.get("background_video_required") is not False:
        failures.append("cinematic creative manifest must reject background video")
    if render_report.get("background_video_used") is not False:
        failures.append("cinematic render unexpectedly used a background video")
    if render_report.get("fullscreen_images_verified") is not True:
        failures.append("cinematic render did not confirm full-screen images")
    if int(render_report.get("reddit_page_count") or 0) != 0:
        failures.append("cinematic render must contain no Reddit-page slides")

    shot_plan = storyboard.get("shot_plan")
    caption_track = storyboard.get("caption_track")
    if not verify_bound_payload(shot_plan, "shot_plan_sha256"):
        failures.append("cinematic shot plan self-hash is invalid")
        shot_plan = {}
    if not verify_bound_payload(caption_track, "caption_track_sha256"):
        failures.append("cinematic caption track self-hash is invalid")
        caption_track = {}
    shot_hash = str((shot_plan or {}).get("shot_plan_sha256") or "")
    caption_hash = str((caption_track or {}).get("caption_track_sha256") or "")
    if (shot_plan or {}).get("shots") != storyboard.get("slides"):
        failures.append("shot plan does not exactly match storyboard slides")
    for label, payload in (
        ("storyboard", storyboard),
        ("creative manifest", creative_manifest),
        ("render report", render_report),
    ):
        if not isinstance(payload, dict):
            continue
        if payload.get("shot_plan_sha256") != shot_hash:
            failures.append(f"{label} shot_plan_sha256 changed")
        if payload.get("caption_track_sha256") != caption_hash:
            failures.append(f"{label} caption_track_sha256 changed")
    if int((shot_plan or {}).get("version") or 0) != CINEMATIC_SHOT_PLAN_VERSION:
        failures.append("cinematic shot plan version is invalid")
    if int((caption_track or {}).get("version") or 0) != CINEMATIC_CAPTION_TRACK_VERSION:
        failures.append("cinematic caption track version is invalid")
    if int((shot_plan or {}).get("shot_count") or 0) != len(slides):
        failures.append("cinematic shot plan count does not match storyboard")
    if int(creative_manifest.get("shot_count") or 0) != len(slides):
        failures.append("cinematic creative manifest shot count is wrong")
    if int(render_report.get("shot_count") or 0) != len(slides):
        failures.append("cinematic render shot count is wrong")

    cursor = 0.0
    expected_motion: list[dict[str, Any]] = []
    story_durations: list[float] = []
    for index, slide in enumerate(slides):
        try:
            start = float(slide.get("start_sec") or 0)
            end = float(slide.get("end_sec") or 0)
            duration = float(slide.get("duration_sec") or 0)
        except (TypeError, ValueError):
            failures.append(f"cinematic shot {index} timing is invalid")
            continue
        if (
            abs(start - cursor) > 0.001
            or end <= start
            or abs((end - start) - duration) > 0.002
        ):
            failures.append(f"cinematic shot {index} has a gap/overlap")
        cursor = end
        presentation = str(slide.get("presentation") or "")
        if presentation == "story":
            story_durations.append(duration)
            if not (
                CINEMATIC_STORY_SHOT_MIN_SECONDS - 0.001
                <= duration
                <= CINEMATIC_STORY_SHOT_MAX_SECONDS + 0.001
            ):
                failures.append(f"cinematic story shot {index} is outside 20-45 seconds")
        elif duration > CINEMATIC_SERVICE_SHOT_MAX_SECONDS + 0.001:
            failures.append(f"cinematic service shot {index} is too long")
        visual = slide.get("visual")
        if (
            not isinstance(visual, dict)
            or visual.get("fit") != "cover"
            or visual.get("sha256") != slide.get("visual_sha256")
        ):
            failures.append(f"cinematic shot {index} lacks full-screen visual evidence")
        motion = slide.get("motion")
        try:
            start_scale = float((motion or {}).get("start_scale"))
            end_scale = float((motion or {}).get("end_scale"))
            start_center = [float(value) for value in (motion or {}).get("start_center")]
            end_center = [float(value) for value in (motion or {}).get("end_center")]
        except (TypeError, ValueError):
            failures.append(f"cinematic shot {index} motion is invalid")
            continue
        if (
            not isinstance(motion, dict)
            or motion.get("type") != "slow_push_pan"
            or motion.get("easing") != "linear"
            or start_scale != 1.0
            or not CINEMATIC_ZOOM_END_MIN <= end_scale <= CINEMATIC_ZOOM_END_MAX
            or len(start_center) != 2
            or len(end_center) != 2
            or any(
                value < CINEMATIC_PAN_CENTER_MIN
                or value > CINEMATIC_PAN_CENTER_MAX
                for value in start_center + end_center
            )
        ):
            failures.append(f"cinematic shot {index} motion violates safe bounds")
        expected_motion.append({
            "shot_id": slide.get("shot_id"),
            "visual_sha256": slide.get("visual_sha256"),
            "motion": motion,
        })
    try:
        timeline_duration = float(storyboard.get("timeline_duration_sec") or 0)
    except (TypeError, ValueError):
        timeline_duration = 0.0
    if timeline_duration <= 0 or abs(cursor - timeline_duration) > 0.002:
        failures.append("cinematic shots do not cover the full audio timeline")
    if render_report.get("motion_evidence") != expected_motion:
        failures.append("render motion evidence does not match exact shots")
    if render_report.get("motion_evidence_sha256") != _canonical_hash(expected_motion):
        failures.append("render motion evidence checksum is invalid")
    if story_durations:
        if abs(float(render_report.get("story_shot_duration_min_sec") or 0) - min(story_durations)) > 0.002:
            failures.append("render minimum story-shot duration is wrong")
        if abs(float(render_report.get("story_shot_duration_max_sec") or 0) - max(story_durations)) > 0.002:
            failures.append("render maximum story-shot duration is wrong")

    cues = (caption_track or {}).get("cues")
    if not isinstance(cues, list) or not cues:
        failures.append("cinematic caption track has no cues")
    else:
        previous_end = 0.0
        caption_text: list[str] = []
        for index, cue in enumerate(cues):
            try:
                start = float(cue.get("start_sec") or 0)
                end = float(cue.get("end_sec") or 0)
            except (TypeError, ValueError):
                failures.append(f"caption cue {index} timing is invalid")
                continue
            text = str(cue.get("text") or "").strip()
            if (
                start + 0.001 < previous_end
                or end <= start
                or end > timeline_duration + 0.001
                or not text
                or hashlib.sha256(text.encode("utf-8")).hexdigest()
                != cue.get("text_sha256")
            ):
                failures.append(f"caption cue {index} is invalid or overlaps")
            previous_end = end
            caption_text.append(text)
        if " ".join(caption_text) != expected_text:
            failures.append("caption cues do not preserve accepted narration")
    if render_report.get("creative_manifest_sha256") != _canonical_hash(
        creative_manifest,
    ):
        failures.append("cinematic render is not bound to creative manifest")
    caption_srt = str(render_report.get("caption_srt") or "").strip()
    caption_path = Path(caption_srt) if caption_srt else None
    root = Path(artifact_root).resolve()
    if caption_path is not None:
        caption_path = (
            caption_path.resolve()
            if caption_path.is_absolute()
            else (root / caption_path).resolve()
        )
    if (
        caption_path is None
        or caption_path == root
        or root not in caption_path.parents
        or not caption_path.is_file()
    ):
        failures.append("cinematic caption SRT is missing or outside artifact root")
    elif render_report.get("caption_srt_sha256") != _sha256_file(caption_path):
        failures.append("cinematic caption SRT checksum is invalid")
    else:
        srt_cues = _srt_cues(caption_path)
        expected_srt = [
            (_number(cue.get("start_sec")), _number(cue.get("end_sec")), str(cue.get("text") or "").strip())
            for cue in cues
        ] if isinstance(cues, list) else []
        if srt_cues is None or len(srt_cues) != len(expected_srt):
            failures.append("cinematic caption SRT contents do not match caption cues")
        else:
            for actual, expected in zip(srt_cues, expected_srt):
                if (
                    abs(actual[0] - expected[0]) > 0.001
                    or abs(actual[1] - expected[1]) > 0.001
                    or actual[2] != expected[2]
                ):
                    failures.append("cinematic caption SRT contents do not match caption cues")
                    break
    return failures


def _validate_editorial_motion_creative_contract(
    compilation: dict[str, Any],
    storyboard: dict[str, Any],
    render_report: dict[str, Any],
    creative_manifest: dict[str, Any] | None,
    scenes: list[dict[str, Any]],
    artifact_root: Path,
) -> list[str]:
    failures: list[str] = []
    if not isinstance(creative_manifest, dict):
        return ["editorial motion requires creative_manifest"]
    style_profile = str(storyboard.get("style_profile") or "").strip()
    if style_profile not in EDITORIAL_MOTION_STYLE_PROFILES:
        failures.append("editorial motion style profile is unsupported")
    if (
        storyboard.get("visual_mode") != EDITORIAL_MOTION_MODE
        or creative_manifest.get("mode") != EDITORIAL_MOTION_MODE
        or render_report.get("visual_mode") != EDITORIAL_MOTION_MODE
    ):
        failures.append("editorial motion visual_mode must match across artifacts")
    if storyboard.get("background_video") not in (None, ""):
        failures.append("editorial motion must not use a background video")
    if creative_manifest.get("background_video_required") is not False:
        failures.append("editorial motion creative manifest must reject background video")
    if render_report.get("background_video_used") is not False:
        failures.append("editorial motion render unexpectedly used background video")
    renderer = str(render_report.get("renderer") or "")
    if (
        renderer not in {"hyperframes", "hyperframes_segmented"}
        or render_report.get("hyperframes_check_passed") is not True
    ):
        failures.append("editorial motion requires a passing HyperFrames check")
    if renderer == "hyperframes_segmented":
        segment_count = _integer(render_report.get("segment_count"))
        segment_ceiling = _number(
            render_report.get("segment_max_duration_sec"),
        )
        segment_reports = render_report.get("segments")
        if (
            segment_count < 1
            or not 0 < segment_ceiling <= 120
            or not isinstance(segment_reports, list)
            or len(segment_reports) != segment_count
        ):
            failures.append(
                "editorial segmented render requires a complete <=120s segment inventory",
            )
        else:
            for index, segment in enumerate(segment_reports, start=1):
                if (
                    not isinstance(segment, dict)
                    or _number(segment.get("duration_sec")) <= 0
                    or _number(segment.get("duration_sec")) > segment_ceiling + 0.12
                ):
                    failures.append(
                        f"editorial render segment {index} violates the bounded duration",
                    )
        if render_report.get("captions_burned") is not True:
            failures.append("editorial segmented render must burn the approved captions")
    if render_report.get("factual_text_rendering") != "html_svg_only":
        failures.append("editorial factual text must be rendered by HTML/SVG")

    expected_contract = {
        "version": VISUAL_CONTRACT_VERSION,
        "motion_plan_version": EDITORIAL_MOTION_PLAN_VERSION,
        "caption_track_version": EDITORIAL_MOTION_CAPTION_TRACK_VERSION,
        "assets_per_pack": EDITORIAL_MOTION_ASSETS_PER_PACK,
        "story_scene_min_seconds": EDITORIAL_MOTION_MIN_SCENE_SECONDS,
        "story_scene_max_seconds": EDITORIAL_MOTION_MAX_SCENE_SECONDS,
        "service_scene_max_seconds": EDITORIAL_MOTION_SERVICE_SCENE_MAX_SECONDS,
        "modules": list(EDITORIAL_MOTION_MODULES),
        "style_profile": style_profile,
        "factual_text_rendering": "html_svg_only",
        "full_screen_images": True,
        "seek_safe": True,
    }
    if creative_manifest.get("visual_contract") != expected_contract:
        failures.append("editorial motion visual contract drifted")

    motion_plan = storyboard.get("motion_plan")
    captions = storyboard.get("caption_track")
    if not verify_editorial_payload(motion_plan, "motion_plan_sha256"):
        failures.append("editorial motion plan self-hash is invalid")
        motion_plan = {}
    if not verify_editorial_payload(captions, "caption_track_sha256"):
        failures.append("editorial caption track self-hash is invalid")
        captions = {}
    motion_hash = str((motion_plan or {}).get("motion_plan_sha256") or "")
    caption_hash = str((captions or {}).get("caption_track_sha256") or "")
    if (motion_plan or {}).get("scenes") != scenes:
        failures.append("editorial motion plan does not exactly match storyboard scenes")
    for label, payload in (
        ("storyboard", storyboard),
        ("creative manifest", creative_manifest),
        ("render report", render_report),
    ):
        if payload.get("motion_plan_sha256") != motion_hash:
            failures.append(f"{label} motion_plan_sha256 changed")
        if payload.get("caption_track_sha256") != caption_hash:
            failures.append(f"{label} caption_track_sha256 changed")
    if int((motion_plan or {}).get("version") or 0) != EDITORIAL_MOTION_PLAN_VERSION:
        failures.append("editorial motion plan version is invalid")
    if (
        (motion_plan or {}).get("style_profile") != style_profile
        or creative_manifest.get("style_profile") != style_profile
        or render_report.get("style_profile") != style_profile
    ):
        failures.append("editorial motion style profile drifted")
    if int((captions or {}).get("version") or 0) != EDITORIAL_MOTION_CAPTION_TRACK_VERSION:
        failures.append("editorial caption track version is invalid")
    if int((motion_plan or {}).get("scene_count") or 0) != len(scenes):
        failures.append("editorial motion plan scene count is wrong")
    if int(render_report.get("scene_count") or 0) != len(scenes):
        failures.append("editorial render scene count is wrong")

    try:
        expected_text = narration_text(compilation)
    except Exception as exc:
        failures.append(f"accepted narration cannot be read for editorial QA: {exc}")
        expected_text = ""
    covered_text = " ".join(
        " ".join(str(scene.get("narration_text") or "").split())
        for scene in scenes
    ).strip()
    if not expected_text or covered_text != expected_text:
        failures.append("editorial scenes do not cover accepted narration exactly")

    root = Path(artifact_root).resolve()
    cursor = 0.0
    family_ids: set[str] = set()
    module_usage = {module: 0 for module in EDITORIAL_MOTION_MODULES}
    for index, scene in enumerate(scenes):
        if scene.get("kind") != "editorial_motion_scene":
            failures.append(f"editorial scene {index} has invalid kind")
            continue
        try:
            start = float(scene.get("start_sec") or 0)
            end = float(scene.get("end_sec") or 0)
            duration = float(scene.get("duration_sec") or 0)
        except (TypeError, ValueError):
            failures.append(f"editorial scene {index} timing is invalid")
            continue
        if abs(start - cursor) > 0.001 or end <= start or abs(end - start - duration) > 0.002:
            failures.append(f"editorial scene {index} has a timing gap or overlap")
        cursor = end
        presentation = str(scene.get("presentation") or "")
        if presentation == "story" and not (
            EDITORIAL_MOTION_MIN_SCENE_SECONDS - 0.002
            <= duration
            <= EDITORIAL_MOTION_MAX_SCENE_SECONDS + 0.002
        ):
            failures.append(f"editorial story scene {index} violates duration bounds")
        if presentation != "story" and duration > EDITORIAL_MOTION_SERVICE_SCENE_MAX_SECONDS + 0.002:
            failures.append(f"editorial service scene {index} is too long")
        module = str((scene.get("motion") or {}).get("module") or "")
        if module not in module_usage or (scene.get("motion") or {}).get("seek_safe") is not True:
            failures.append(f"editorial scene {index} has invalid or unsafe motion")
        else:
            module_usage[module] += 1
        if scene.get("factual_text_rendering") != "html_svg_only":
            failures.append(f"editorial scene {index} permits AI-rendered factual text")
        if scene.get("style_profile") != style_profile:
            failures.append(f"editorial scene {index} style profile drifted")
        if style_profile == INK_GOUACHE_STORY_PAGES_STYLE_PROFILE and (
            scene.get("story_family") not in INK_GOUACHE_STORY_FAMILIES
            or scene.get("page_layout") not in INK_GOUACHE_PAGE_LAYOUTS
        ):
            failures.append(
                f"editorial scene {index} has invalid Ink & Gouache art direction",
            )
        assets = scene.get("assets")
        if not isinstance(assets, list) or len(assets) != EDITORIAL_MOTION_ASSETS_PER_PACK:
            failures.append(f"editorial scene {index} asset pack is incomplete")
            continue
        roles = [str(asset.get("layer_role") or "") for asset in assets]
        if roles != ["hero_plate", "detail_plate"]:
            failures.append(f"editorial scene {index} asset roles are invalid")
        family_id = str(scene.get("asset_family_id") or "")
        if not family_id:
            failures.append(f"editorial scene {index} has no asset family")
        family_ids.add(family_id)
        for asset in assets:
            raw = str(asset.get("local_path") or "")
            candidate = Path(raw).expanduser()
            path = candidate.resolve() if candidate.is_absolute() else (root / candidate).resolve()
            expected = str(asset.get("sha256") or "").lower()
            if (
                path == root
                or root not in path.parents
                or not path.is_file()
                or not SHA256_RE.fullmatch(expected)
                or _sha256_file(path) != expected
            ):
                failures.append(f"editorial scene {index} asset checksum/path is invalid")
    if module_usage != (motion_plan or {}).get("module_usage"):
        failures.append("editorial module usage does not match bound plan")
    if int(render_report.get("asset_pack_count") or 0) != len(family_ids):
        failures.append("editorial render asset pack count is wrong")
    try:
        planned_duration = float(storyboard.get("timeline_duration_sec") or 0)
        rendered_duration = float(render_report.get("duration_sec") or 0)
    except (TypeError, ValueError):
        planned_duration = rendered_duration = 0
    if abs(cursor - planned_duration) > 0.002 or abs(rendered_duration - planned_duration) > 0.35:
        failures.append("editorial render duration does not match its bound timeline")

    caption_path_raw = str(render_report.get("caption_srt") or "")
    caption_path = (
        Path(caption_path_raw).resolve()
        if Path(caption_path_raw).is_absolute()
        else (root / caption_path_raw).resolve()
    )
    if (
        not caption_path_raw
        or caption_path == root
        or root not in caption_path.parents
        or not caption_path.is_file()
        or render_report.get("caption_srt_sha256") != _sha256_file(caption_path)
    ):
        failures.append("editorial caption SRT is missing or invalid")
    return failures


def _validate_creative_contract(
    compilation: dict[str, Any],
    storyboard: dict[str, Any],
    render_report: dict[str, Any],
    creative_manifest: dict[str, Any] | None,
    slides: list[dict[str, Any]],
    artifact_root: Path,
) -> list[str]:
    raw_mode = storyboard.get("visual_mode")
    if raw_mode in (None, "") and isinstance(creative_manifest, dict):
        raw_mode = creative_manifest.get("mode")
    try:
        mode = resolve_visual_mode(raw_mode)
    except ValueError as exc:
        return [str(exc)]
    declared_script_mode = compilation.get("visual_mode")
    failures: list[str] = []
    if declared_script_mode not in (None, "", mode):
        failures.append("script visual_mode does not match storyboard")
    if mode == CINEMATIC_STORY_MODE:
        failures.extend(_validate_cinematic_creative_contract(
            compilation,
            storyboard,
            render_report,
            creative_manifest,
            slides,
            artifact_root,
        ))
    else:
        failures.extend(_validate_reddit_creative_contract(
            compilation,
            storyboard,
            render_report,
            creative_manifest,
            slides,
        ))
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
    pause_map: dict[str, Any] | None = None,
    audio_mix_report: dict[str, Any] | None = None,
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
    expected_profile_id: str | None = None
    expected_profile_sha256: str | None = None
    expected_boundary_contract: dict[str, Any] | None = None
    if isinstance(episode_plan, dict) and _integer(episode_plan.get("version") or 1, default=0) >= 2:
        expected_profile_id = str(
            episode_plan.get("narration_profile_id") or "",
        )
        expected_profile_sha256 = str(
            episode_plan.get("narration_profile_sha256") or "",
        )
        planned_tts = (episode_plan.get("provider_settings") or {}).get("tts")
        if isinstance(planned_tts, dict) and isinstance(
            planned_tts.get("narration_boundary_contract"),
            dict,
        ):
            expected_boundary_contract = planned_tts[
                "narration_boundary_contract"
            ]
    failures.extend(validate_tts_state(
        tts_state,
        expected_voice_id=expected_voice_id,
        expected_comment_voice_id=expected_comment_voice_id,
        expected_narration_profile_id=expected_profile_id,
        expected_narration_profile_sha256=expected_profile_sha256,
        expected_narration_boundary_contract=expected_boundary_contract,
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
    audio_failures, audio_sha256 = _validate_audio(audio_path, artifact_root)
    failures.extend(audio_failures)
    mix_failures, expected_final_audio_sha256 = _validate_audio_mix_chain(
        tts_state=tts_state,
        pause_map=pause_map,
        audio_mix_report=audio_mix_report,
        episode_plan=episode_plan,
        storyboard=storyboard,
        render_report=render_report,
        creative_manifest=creative_manifest,
        actual_audio_sha256=audio_sha256,
    )
    failures.extend(mix_failures)
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
        expected_final_audio_sha256=expected_final_audio_sha256,
    )
    failures.extend(episode_failures)
    try:
        failures.extend(_validate_creative_contract(
            compilation,
            storyboard,
            render_report,
            creative_manifest,
            slides,
            artifact_root,
        ))
    except (TypeError, ValueError, KeyError, OverflowError) as exc:
        failures.append(f"creative contract is malformed: {exc}")
    if audio_sha256:
        if expected_final_audio_sha256 != audio_sha256:
            failures.append("final audio checksum does not match expected narration/mix")
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
            video_stream = next((item for item in probe.get("streams", []) if item.get("codec_type") == "video"), {})
            audio_stream = next((item for item in probe.get("streams", []) if item.get("codec_type") == "audio"), {})
            frame_rate = str(video_stream.get("avg_frame_rate") or video_stream.get("r_frame_rate") or "")
            try:
                numerator, denominator = frame_rate.split("/", 1)
                fps = float(numerator) / float(denominator)
            except (ValueError, ZeroDivisionError):
                fps = 0.0
            if video_stream.get("codec_name") != "h264" or abs(fps - 30.0) > 0.01:
                failures.append("final MP4 video must be H.264 at 30 fps")
            if audio_stream.get("codec_name") != "aac":
                failures.append("final MP4 audio must be AAC")
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
        "visual_mode": (
            storyboard.get("visual_mode")
            if isinstance(storyboard, dict) else None
        ),
        "narration_profile_id": tts_state.get("narration_profile_id"),
        "narration_profile_sha256": tts_state.get("narration_profile_sha256"),
        "timing_contract_sha256": tts_state.get("timing_contract_sha256"),
        "pause_map_sha256": pause_map.get("pause_map_sha256") if isinstance(pause_map, dict) else None,
        "audio_mix_report_sha256": (
            audio_mix_report.get("audio_mix_report_sha256")
            if isinstance(audio_mix_report, dict) else None
        ),
        "shot_plan_sha256": storyboard.get("shot_plan_sha256") if isinstance(storyboard, dict) else None,
        "caption_track_sha256": storyboard.get("caption_track_sha256") if isinstance(storyboard, dict) else None,
        "caption_srt_sha256": render_report.get("caption_srt_sha256"),
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
    parser.add_argument(
        "--pause-map",
        help="Required self-hashed pause-map sidecar for manifest v2 episodes.",
    )
    parser.add_argument(
        "--audio-mix-report",
        help="Required measured voice-mix report for manifest v2 episodes.",
    )
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
        pause_map=(
            load_object(Path(args.pause_map)) if args.pause_map else None
        ),
        audio_mix_report=(
            load_object(Path(args.audio_mix_report))
            if args.audio_mix_report else None
        ),
        topic_playoff=(
            load_object(Path(args.topic_playoff)) if args.topic_playoff else None
        ),
    )
    Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
