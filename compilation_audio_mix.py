"""Deterministic no-network pause-map and FFmpeg voice-only mix for acc1."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, Callable

from acc1_narration_profiles import (
    NarrationProfileError,
    canonical_hash,
    resolve_narration_profile,
)


PAUSE_MAP_VERSION = 1
AUDIO_MIX_REPORT_VERSION = 1
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class CompilationAudioMixError(RuntimeError):
    """A fail-closed local pause-map, FFmpeg, or loudness-contract error."""


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _without_self_hash(value: dict[str, Any], field: str) -> dict[str, Any]:
    return {key: nested for key, nested in value.items() if key != field}


def verify_self_hash(value: dict[str, Any], field: str) -> bool:
    recorded = str(value.get(field) or "").lower()
    return bool(
        SHA256_RE.fullmatch(recorded)
        and recorded == canonical_hash(_without_self_hash(value, field))
    )


def _atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _profile_from_state(tts_state: dict[str, Any]) -> dict[str, Any]:
    profile_id = str(tts_state.get("narration_profile_id") or "").strip()
    pillar_id = str(tts_state.get("narration_pillar_id") or "").strip()
    try:
        profile = resolve_narration_profile(profile_id, pillar_id=pillar_id)
    except NarrationProfileError as exc:
        raise CompilationAudioMixError(str(exc)) from exc
    if tts_state.get("narration_profile_sha256") != profile["profile_sha256"]:
        raise CompilationAudioMixError(
            "TTS state narration profile checksum does not match the canonical profile"
        )
    return profile


def _validate_state_bindings(tts_state: dict[str, Any]) -> None:
    if tts_state.get("status") != "COMPLETE":
        raise CompilationAudioMixError("pause map requires COMPLETE TTS state")
    if tts_state.get("publication_authorized") is not False:
        raise CompilationAudioMixError(
            "TTS state publication_authorized must remain false"
        )
    for field in (
        "episode_plan_sha256",
        "daily_plan_sha256",
        "narration_plan_sha256",
        "timing_contract_sha256",
    ):
        if not SHA256_RE.fullmatch(str(tts_state.get(field) or "").lower()):
            raise CompilationAudioMixError(f"TTS state {field} must be a SHA-256 digest")


def build_pause_map(
    tts_state: dict[str, Any],
    *,
    output_path: Path | None = None,
) -> dict[str, Any]:
    """Build a deterministic self-hashed timeline from completed exact chunks."""

    _validate_state_bindings(tts_state)
    profile = _profile_from_state(tts_state)
    chunks = tts_state.get("chunks")
    if not isinstance(chunks, list) or not chunks:
        raise CompilationAudioMixError("TTS state chunks must be a non-empty list")

    pause_contract = profile["pause_after"]
    segment_pauses = pause_contract["segment_seconds"]
    entries: list[dict[str, Any]] = []
    cursor = 0.0
    voice_duration = 0.0
    pause_duration = 0.0
    input_chunks: list[dict[str, Any]] = []

    for index, chunk in enumerate(chunks):
        chunk_id = str(chunk.get("chunk_id") or "").strip()
        if chunk.get("status") != "COMPLETE" or not chunk_id:
            raise CompilationAudioMixError(
                "pause map requires every TTS chunk to be COMPLETE"
            )
        if chunk.get("narration_profile_sha256") != profile["profile_sha256"]:
            raise CompilationAudioMixError(
                f"{chunk_id} narration profile checksum changed"
            )
        audio_sha256 = str(chunk.get("audio_sha256") or "").lower()
        if not SHA256_RE.fullmatch(audio_sha256):
            raise CompilationAudioMixError(f"{chunk_id} audio_sha256 is invalid")
        audio_path = str(chunk.get("audio_path") or "").strip()
        if not audio_path:
            raise CompilationAudioMixError(f"{chunk_id} audio_path is required")
        try:
            duration = float(chunk.get("audio_duration_sec"))
        except (TypeError, ValueError) as exc:
            raise CompilationAudioMixError(
                f"{chunk_id} audio_duration_sec is invalid"
            ) from exc
        if not math.isfinite(duration) or duration <= 0:
            raise CompilationAudioMixError(
                f"{chunk_id} audio_duration_sec must be positive"
            )
        timing_source = str(chunk.get("timing_source") or "").strip()
        if timing_source not in {"ai33", "estimated_from_audio_duration"}:
            raise CompilationAudioMixError(f"{chunk_id} timing_source is invalid")
        word_timings = chunk.get("word_timings")
        word_timings_sha256 = str(
            chunk.get("word_timings_sha256") or "",
        ).lower()
        if (
            not isinstance(word_timings, list)
            or not word_timings
            or not SHA256_RE.fullmatch(word_timings_sha256)
            or canonical_hash(word_timings) != word_timings_sha256
        ):
            raise CompilationAudioMixError(
                f"{chunk_id} completed word timing contract is invalid"
            )
        if not isinstance(chunk.get("is_last_in_beat"), bool):
            raise CompilationAudioMixError(f"{chunk_id} beat boundary is missing")
        if not isinstance(chunk.get("is_last_in_segment"), bool):
            raise CompilationAudioMixError(f"{chunk_id} segment boundary is missing")

        is_final = index == len(chunks) - 1
        segment_kind = str(chunk.get("logical_segment_kind") or "").strip()
        if is_final:
            pause_kind = "none"
            pause_after = 0.0
        elif chunk["is_last_in_segment"]:
            if segment_kind not in segment_pauses:
                raise CompilationAudioMixError(
                    f"{chunk_id} has unknown logical segment kind {segment_kind!r}"
                )
            pause_kind = "segment"
            pause_after = float(segment_pauses[segment_kind])
        elif chunk["is_last_in_beat"]:
            pause_kind = "beat"
            pause_after = float(pause_contract["beat_seconds"])
        else:
            pause_kind = "intra_beat"
            pause_after = float(pause_contract["intra_beat_seconds"])
        if not math.isfinite(pause_after) or pause_after < 0:
            raise CompilationAudioMixError(
                f"{chunk_id} has an invalid canonical pause"
            )

        audio_start = cursor
        audio_end = audio_start + duration
        pause_start = audio_end
        pause_end = pause_start + pause_after
        entry = {
            "chunk_id": chunk_id,
            "logical_segment_id": chunk.get("logical_segment_id"),
            "logical_segment_kind": segment_kind,
            "semantic_beat_id": chunk.get("semantic_beat_id"),
            "semantic_beat_index": chunk.get("semantic_beat_index"),
            "audio_path": audio_path,
            "audio_sha256": audio_sha256,
            "audio_duration_sec": round(duration, 6),
            "timing_source": timing_source,
            "word_timings_sha256": word_timings_sha256,
            "timeline_audio_start_sec": round(audio_start, 6),
            "timeline_audio_end_sec": round(audio_end, 6),
            "pause_kind": pause_kind,
            "pause_after_sec": round(pause_after, 6),
            "timeline_pause_start_sec": round(pause_start, 6),
            "timeline_pause_end_sec": round(pause_end, 6),
        }
        entries.append(entry)
        input_chunks.append({
            "chunk_id": chunk_id,
            "audio_path": audio_path,
            "audio_sha256": audio_sha256,
            "audio_duration_sec": round(duration, 6),
            "timing_source": timing_source,
            "word_timings_sha256": word_timings_sha256,
        })
        voice_duration += duration
        pause_duration += pause_after
        cursor = pause_end

    payload: dict[str, Any] = {
        "version": PAUSE_MAP_VERSION,
        "status": "PASS",
        "episode_plan_sha256": tts_state["episode_plan_sha256"],
        "daily_plan_sha256": tts_state["daily_plan_sha256"],
        "narration_plan_sha256": tts_state["narration_plan_sha256"],
        "timing_contract_sha256": tts_state["timing_contract_sha256"],
        "narration_profile_id": profile["profile_id"],
        "narration_profile_sha256": profile["profile_sha256"],
        "narration_pillar_id": profile["pillar_id"],
        "pause_contract": pause_contract,
        "pause_contract_sha256": canonical_hash(pause_contract),
        "input_chunks_sha256": canonical_hash(input_chunks),
        "voice_duration_sec": round(voice_duration, 6),
        "pause_duration_sec": round(pause_duration, 6),
        "timeline_duration_sec": round(cursor, 6),
        "entries": entries,
        "network_used": False,
        "publication_authorized": False,
    }
    payload["pause_map_sha256"] = canonical_hash(payload)
    if output_path is not None:
        _atomic_json(Path(output_path), payload)
    return payload


def _resolve_under_root(root: Path, value: Path | str) -> Path:
    candidate = Path(value)
    resolved = candidate.resolve() if candidate.is_absolute() else (root / candidate).resolve()
    if resolved != root and root not in resolved.parents:
        raise CompilationAudioMixError(
            f"audio mix path must remain under artifact_root: {value}"
        )
    return resolved


def _relative_path(root: Path, path: Path) -> str:
    return path.resolve().relative_to(root).as_posix()


def _run_command(
    command: list[str],
    *,
    runner: Callable[..., subprocess.CompletedProcess[str]],
) -> subprocess.CompletedProcess[str]:
    try:
        result = runner(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=120,
        )
    except subprocess.TimeoutExpired as exc:
        raise CompilationAudioMixError(
            f"local media command timed out: {command[0]}"
        ) from exc
    except OSError as exc:
        raise CompilationAudioMixError(
            f"could not execute local media command: {command[0]}"
        ) from exc
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()[-1600:]
        raise CompilationAudioMixError(
            f"local media command failed ({result.returncode}): {detail}"
        )
    return result


def _available_filters(
    ffmpeg: str,
    *,
    runner: Callable[..., subprocess.CompletedProcess[str]],
) -> set[str]:
    result = _run_command(
        [ffmpeg, "-hide_banner", "-filters"],
        runner=runner,
    )
    filters: set[str] = set()
    for line in (result.stdout or "").splitlines():
        columns = line.split()
        if len(columns) >= 2 and re.fullmatch(r"[A-Za-z0-9_]+", columns[1]):
            filters.add(columns[1])
    return filters


def _concat_inputs_and_filter(
    *,
    entries: list[dict[str, Any]],
    input_paths: list[Path],
) -> tuple[list[str], str]:
    input_args: list[str] = []
    filters: list[str] = []
    labels: list[str] = []
    pause_index = 0
    for input_index, (entry, audio_path) in enumerate(zip(entries, input_paths)):
        input_args.extend(["-i", str(audio_path)])
        label = f"a{input_index}"
        filters.append(
            f"[{input_index}:a]aresample=48000,"
            "aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=mono"
            f"[{label}]"
        )
        labels.append(f"[{label}]")
        pause = float(entry["pause_after_sec"])
        if pause > 0:
            # Keep silence finite inside the filter graph.  Supplying anullsrc
            # as an input can leave FFmpeg waiting on an infinite source even
            # when an input-scoped ``-t`` is present.
            label = f"p{pause_index}"
            filters.append(
                "anullsrc=channel_layout=mono:sample_rate=48000,"
                f"atrim=duration={pause:.6f},asetpts=N/SR/TB,"
                "aformat=sample_fmts=fltp:sample_rates=48000:"
                f"channel_layouts=mono[{label}]"
            )
            labels.append(f"[{label}]")
            pause_index += 1
    if not labels:
        raise CompilationAudioMixError("audio mix has no input labels")
    if len(labels) == 1:
        filters.append(f"{labels[0]}anull[joined]")
    else:
        filters.append(
            "".join(labels) + f"concat=n={len(labels)}:v=0:a=1[joined]"
        )
    return input_args, ";".join(filters)


def _parse_loudnorm_json(text: str) -> dict[str, float]:
    matches = re.findall(
        r'\{\s*"input_i"\s*:.*?\}',
        text or "",
        flags=re.DOTALL,
    )
    for raw in reversed(matches):
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            continue
        required = (
            "input_i",
            "input_tp",
            "input_lra",
            "input_thresh",
            "target_offset",
        )
        values: dict[str, float] = {}
        try:
            for field in required:
                values[field] = float(payload[field])
        except (KeyError, TypeError, ValueError):
            continue
        if all(math.isfinite(value) for value in values.values()):
            return values
    raise CompilationAudioMixError("FFmpeg loudnorm returned no finite JSON measurement")


def _loudnorm_filter(
    *,
    target_lufs: float,
    max_true_peak: float,
    measured: dict[str, float] | None = None,
    print_format: str,
) -> str:
    values = [
        f"I={target_lufs:g}",
        f"TP={max_true_peak:g}",
        "LRA=11",
    ]
    if measured is not None:
        values.extend([
            f"measured_I={measured['input_i']:g}",
            f"measured_TP={measured['input_tp']:g}",
            f"measured_LRA={measured['input_lra']:g}",
            f"measured_thresh={measured['input_thresh']:g}",
            f"offset={measured['target_offset']:g}",
            "linear=true",
        ])
    values.extend(["dual_mono=true", f"print_format={print_format}"])
    return "loudnorm=" + ":".join(values)


def _measure_ebur128(
    ffmpeg: str,
    output_path: Path,
    *,
    runner: Callable[..., subprocess.CompletedProcess[str]],
) -> tuple[float, float]:
    result = _run_command([
        ffmpeg, "-hide_banner", "-nostats", "-i", str(output_path),
        "-filter_complex", "ebur128=peak=true", "-f", "null", "-",
    ], runner=runner)
    integrated = re.findall(
        r"I:\s*(-?\d+(?:\.\d+)?)\s+LUFS",
        result.stderr or "",
    )
    peaks = re.findall(
        r"Peak:\s*(-?\d+(?:\.\d+)?)\s+dBFS",
        result.stderr or "",
    )
    if not integrated or not peaks:
        raise CompilationAudioMixError("FFmpeg ebur128 measurement is incomplete")
    return float(integrated[-1]), float(peaks[-1])


def _probe_audio(
    ffprobe: str,
    output_path: Path,
    *,
    runner: Callable[..., subprocess.CompletedProcess[str]],
) -> dict[str, Any]:
    result = _run_command([
        ffprobe, "-v", "error",
        "-show_entries",
        "format=duration:stream=index,codec_type,codec_name,sample_rate,channels,channel_layout",
        "-of", "json", str(output_path),
    ], runner=runner)
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise CompilationAudioMixError("ffprobe returned invalid JSON") from exc
    streams = payload.get("streams")
    audio_streams = [
        stream for stream in streams or []
        if isinstance(stream, dict) and stream.get("codec_type") == "audio"
    ]
    if len(audio_streams) != 1 or len(streams or []) != 1:
        raise CompilationAudioMixError(
            "voice mix must contain exactly one audio stream and no video"
        )
    try:
        duration = float((payload.get("format") or {}).get("duration"))
    except (TypeError, ValueError) as exc:
        raise CompilationAudioMixError("ffprobe duration is invalid") from exc
    if not math.isfinite(duration) or duration <= 0:
        raise CompilationAudioMixError("voice mix duration must be positive")
    return {
        "duration_sec": round(duration, 6),
        "stream": audio_streams[0],
    }


def _read_pause_map(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CompilationAudioMixError("pause-map sidecar is unreadable") from exc
    if not isinstance(value, dict) or not verify_self_hash(value, "pause_map_sha256"):
        raise CompilationAudioMixError("pause-map sidecar checksum is invalid")
    return value


def mix_compilation_audio(
    tts_state: dict[str, Any],
    *,
    artifact_root: Path,
    pause_map: dict[str, Any] | None = None,
    pause_map_path: Path | None = None,
    output_path: Path | None = None,
    report_path: Path | None = None,
    ffmpeg_path: str | None = None,
    ffprobe_path: str | None = None,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> dict[str, Any]:
    """Insert exact pauses, normalize locally, measure, and self-hash the mix."""

    _validate_state_bindings(tts_state)
    profile = _profile_from_state(tts_state)
    root = Path(artifact_root).resolve()
    if not root.is_dir():
        raise CompilationAudioMixError("artifact_root must be an existing directory")

    declared_pause_path = str(tts_state.get("pause_map_path") or "").strip()
    resolved_pause_path = _resolve_under_root(
        root,
        pause_map_path
        or declared_pause_path
        or Path("narration-pause-map.json"),
    )
    if pause_map is None and resolved_pause_path.is_file():
        pause_map = _read_pause_map(resolved_pause_path)
    elif pause_map is None:
        pause_map = build_pause_map(tts_state)
    if not verify_self_hash(pause_map, "pause_map_sha256"):
        raise CompilationAudioMixError("pause map checksum is invalid")
    for field in (
        "episode_plan_sha256",
        "daily_plan_sha256",
        "narration_plan_sha256",
        "timing_contract_sha256",
        "narration_profile_sha256",
    ):
        if pause_map.get(field) != tts_state.get(field):
            raise CompilationAudioMixError(f"pause map {field} binding changed")
    _atomic_json(resolved_pause_path, pause_map)

    resolved_output = _resolve_under_root(
        root, output_path or Path("compilation_voice_mix.wav"),
    )
    resolved_report = _resolve_under_root(
        root, report_path or Path("audio-mix-report.json"),
    )
    resolved_output.parent.mkdir(parents=True, exist_ok=True)
    resolved_report.parent.mkdir(parents=True, exist_ok=True)

    chunks_by_id = {
        str(item.get("chunk_id") or ""): item
        for item in tts_state.get("chunks") or []
        if isinstance(item, dict)
    }
    entries = pause_map.get("entries")
    if not isinstance(entries, list) or not entries:
        raise CompilationAudioMixError("pause map entries must be a non-empty list")
    input_paths: list[Path] = []
    input_contract: list[dict[str, Any]] = []
    for entry in entries:
        chunk_id = str(entry.get("chunk_id") or "")
        chunk = chunks_by_id.get(chunk_id)
        if chunk is None:
            raise CompilationAudioMixError(
                f"pause map references unknown chunk {chunk_id!r}"
            )
        for field in (
            "audio_path",
            "audio_sha256",
            "audio_duration_sec",
            "timing_source",
            "word_timings_sha256",
        ):
            if entry.get(field) != chunk.get(field):
                raise CompilationAudioMixError(
                    f"pause map {chunk_id} {field} binding changed"
                )
        input_path = _resolve_under_root(root, entry["audio_path"])
        if not input_path.is_file() or input_path.stat().st_size <= 0:
            raise CompilationAudioMixError(f"{chunk_id} input audio is missing")
        if _sha256_file(input_path) != entry["audio_sha256"]:
            raise CompilationAudioMixError(f"{chunk_id} input audio checksum mismatch")
        input_paths.append(input_path)
        input_contract.append({
            "chunk_id": chunk_id,
            "audio_path": _relative_path(root, input_path),
            "audio_sha256": entry["audio_sha256"],
            "audio_duration_sec": entry["audio_duration_sec"],
            "timing_source": entry["timing_source"],
            "word_timings_sha256": entry["word_timings_sha256"],
        })
    if canonical_hash(input_contract) != pause_map.get("input_chunks_sha256"):
        raise CompilationAudioMixError("pause map input chunk contract changed")

    ffmpeg = ffmpeg_path or shutil.which("ffmpeg")
    ffprobe = ffprobe_path or shutil.which("ffprobe")
    if not ffmpeg or not ffprobe:
        raise CompilationAudioMixError("ffmpeg and ffprobe are required")
    filters = _available_filters(ffmpeg, runner=runner)
    loudnorm_available = "loudnorm" in filters
    if not loudnorm_available and "ebur128" not in filters:
        raise CompilationAudioMixError(
            "FFmpeg must provide loudnorm or ebur128 for loudness measurement"
        )

    target = profile["voice_only_loudness"]
    target_lufs = float(target["integrated_lufs"])
    max_true_peak = float(target["max_true_peak_dbtp"])
    input_args, base_filter = _concat_inputs_and_filter(
        entries=entries,
        input_paths=input_paths,
    )
    measured_input: dict[str, float] | None = None
    if loudnorm_available:
        analysis_filter = (
            base_filter
            + ";[joined]"
            + _loudnorm_filter(
                target_lufs=target_lufs,
                max_true_peak=max_true_peak,
                print_format="json",
            )
            + "[analysis]"
        )
        analysis = _run_command([
            ffmpeg, "-hide_banner", "-nostats", "-y",
            *input_args,
            "-filter_complex", analysis_filter,
            "-map", "[analysis]", "-f", "null", "-",
        ], runner=runner)
        measured_input = _parse_loudnorm_json(analysis.stderr or "")
        output_filter = (
            base_filter
            + ";[joined]"
            + _loudnorm_filter(
                target_lufs=target_lufs,
                max_true_peak=max_true_peak,
                measured=measured_input,
                print_format="summary",
            )
            + "[mixed]"
        )
        normalization_mode = "ffmpeg_loudnorm_two_pass"
    else:
        output_filter = base_filter + ";[joined]anull[mixed]"
        normalization_mode = "loudnorm_unavailable_passthrough"

    _run_command([
        ffmpeg, "-hide_banner", "-nostats", "-y",
        *input_args,
        "-filter_complex", output_filter,
        "-map", "[mixed]",
        "-map_metadata", "-1",
        "-ar", "48000", "-ac", "1", "-c:a", "pcm_s16le",
        str(resolved_output),
    ], runner=runner)
    if not resolved_output.is_file() or resolved_output.stat().st_size <= 0:
        raise CompilationAudioMixError("FFmpeg did not create the voice mix")

    probe = _probe_audio(ffprobe, resolved_output, runner=runner)
    if loudnorm_available:
        measurement = _run_command([
            ffmpeg, "-hide_banner", "-nostats", "-i", str(resolved_output),
            "-af", _loudnorm_filter(
                target_lufs=target_lufs,
                max_true_peak=max_true_peak,
                print_format="json",
            ),
            "-f", "null", "-",
        ], runner=runner)
        measured_output = _parse_loudnorm_json(measurement.stderr or "")
        integrated_lufs = measured_output["input_i"]
        true_peak_dbtp = measured_output["input_tp"]
        measurement_mode = "ffmpeg_loudnorm_json"
    else:
        integrated_lufs, true_peak_dbtp = _measure_ebur128(
            ffmpeg, resolved_output, runner=runner,
        )
        measured_output = None
        measurement_mode = "ffmpeg_ebur128_summary"

    duration_tolerance = max(0.25, 0.03 * len(entries))
    expected_duration = float(pause_map["timeline_duration_sec"])
    duration_delta = abs(float(probe["duration_sec"]) - expected_duration)
    loudness_ok = (
        abs(integrated_lufs - target_lufs) <= float(target["tolerance_lu"])
    )
    true_peak_ok = true_peak_dbtp <= max_true_peak + 0.05
    duration_ok = duration_delta <= duration_tolerance
    failures: list[str] = []
    if not duration_ok:
        failures.append("mixed duration does not match the pause-map timeline")
    if not loudness_ok:
        failures.append("measured integrated loudness is outside the target tolerance")
    if not true_peak_ok:
        failures.append("measured true peak exceeds the canonical maximum")

    report: dict[str, Any] = {
        "version": AUDIO_MIX_REPORT_VERSION,
        "status": "PASS" if not failures else "BLOCKED",
        "mode": "voice_only",
        "episode_plan_sha256": tts_state["episode_plan_sha256"],
        "daily_plan_sha256": tts_state["daily_plan_sha256"],
        "narration_plan_sha256": tts_state["narration_plan_sha256"],
        "timing_contract_sha256": tts_state["timing_contract_sha256"],
        "narration_profile_id": profile["profile_id"],
        "narration_profile_sha256": profile["profile_sha256"],
        "input_chunks": input_contract,
        "input_chunks_sha256": canonical_hash(input_contract),
        "pause_map_path": _relative_path(root, resolved_pause_path),
        "pause_map_sha256": pause_map["pause_map_sha256"],
        "output_path": _relative_path(root, resolved_output),
        "output_sha256": _sha256_file(resolved_output),
        "output_duration_sec": probe["duration_sec"],
        "expected_timeline_duration_sec": expected_duration,
        "duration_delta_sec": round(duration_delta, 6),
        "duration_tolerance_sec": round(duration_tolerance, 6),
        "audio_stream": probe["stream"],
        "normalization": {
            "mode": normalization_mode,
            "loudnorm_available": loudnorm_available,
            "first_pass_measurement": measured_input,
        },
        "loudness": {
            "measurement_mode": measurement_mode,
            "target_integrated_lufs": target_lufs,
            "tolerance_lu": float(target["tolerance_lu"]),
            "max_true_peak_dbtp": max_true_peak,
            "measured_integrated_lufs": round(integrated_lufs, 3),
            "measured_true_peak_dbtp": round(true_peak_dbtp, 3),
            "integrated_loudness_pass": loudness_ok,
            "true_peak_pass": true_peak_ok,
            "measurement": measured_output,
        },
        "failures": failures,
        "network_used": False,
        "publication_authorized": False,
    }
    report["audio_mix_report_sha256"] = canonical_hash(report)
    _atomic_json(resolved_report, report)
    if failures:
        raise CompilationAudioMixError("; ".join(failures))
    return report


mix_voice_only_audio = mix_compilation_audio
