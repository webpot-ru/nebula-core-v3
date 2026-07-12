"""Fail-closed QA for an artifact-only acc1 horror compilation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from compilation_metadata import validate_metadata
from compilation_renderer import preflight_storyboard
from episode_contract import validate_compilation
from pre_publish_qa import ffprobe_json, media_duration, stream_count, video_resolution


def load_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def validate_tts_state(state: dict[str, Any]) -> list[str]:
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
        if not chunk.get("audio_sha256"):
            failures.append(f"TTS chunk {index} has no audio checksum")
    if not state.get("final_audio_sha256"):
        failures.append("TTS final audio checksum is missing")
    return failures


def run_qa(
    compilation: dict[str, Any],
    metadata: dict[str, Any],
    tts_state: dict[str, Any],
    storyboard: dict[str, Any],
    render_report: dict[str, Any],
    *,
    artifact_root: Path,
    video_path: Path | None = None,
) -> dict[str, Any]:
    failures: list[str] = []
    warnings: list[str] = []
    contract = validate_compilation(compilation)
    failures.extend(contract["failures"])
    warnings.extend(contract["warnings"])
    failures.extend(validate_metadata(metadata, compilation))
    failures.extend(validate_tts_state(tts_state))
    try:
        slides = preflight_storyboard(storyboard, artifact_root)
    except Exception as exc:
        failures.append(f"storyboard preflight failed: {exc}")
        slides = []
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
    if video_path is not None:
        if not video_path.is_file():
            failures.append("final MP4 is missing")
        else:
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
        "failures": failures,
        "warnings": warnings,
        "story_count": contract["story_count"],
        "estimated_minutes": contract["estimated_minutes"],
        "slide_count": len(slides),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compilation", required=True)
    parser.add_argument("--metadata", required=True)
    parser.add_argument("--tts-state", required=True)
    parser.add_argument("--storyboard", required=True)
    parser.add_argument("--render-report", required=True)
    parser.add_argument("--artifact-root", required=True)
    parser.add_argument("--video")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    result = run_qa(
        load_object(Path(args.compilation)), load_object(Path(args.metadata)),
        load_object(Path(args.tts_state)), load_object(Path(args.storyboard)),
        load_object(Path(args.render_report)), artifact_root=Path(args.artifact_root),
        video_path=Path(args.video) if args.video else None,
    )
    Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
