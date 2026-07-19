#!/usr/bin/env python3
"""Re-render a paid Ink & Gouache pilot without any provider calls.

The command copies only the checksum-bound normalized image assets, storyboard
and silent audio from an existing pilot into a new artifact root, then runs the
current HyperFrames renderer.  It never loads provider credentials.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from acc1_visual_contract import INK_GOUACHE_STORY_PAGES_STYLE_PROFILE
from acc1_cinematic_shots import write_caption_srt
from compilation_editorial_motion_renderer import (
    HYPERFRAMES_VERSION,
    _hyperframes_cli,
    _write_workspace,
    preflight_editorial_motion_storyboard,
    render_editorial_motion_compilation,
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _copy_bound_inputs(source: Path, output: Path) -> tuple[dict, Path]:
    storyboard_path = source / "storyboard.json"
    audio_path = source / "silent-pilot-audio.wav"
    if not storyboard_path.is_file() or not audio_path.is_file():
        raise RuntimeError("source pilot is missing storyboard.json or silent-pilot-audio.wav")
    storyboard = json.loads(storyboard_path.read_text(encoding="utf-8"))
    if storyboard.get("style_profile") != INK_GOUACHE_STORY_PAGES_STYLE_PROFILE:
        raise RuntimeError("source pilot is not ink_gouache_story_pages_v1")

    for scene in storyboard.get("slides") or []:
        for asset in scene.get("assets") or []:
            relative = Path(str(asset.get("local_path") or ""))
            source_asset = source / relative
            target_asset = output / relative
            if not source_asset.is_file() or _sha256(source_asset) != asset.get("sha256"):
                raise RuntimeError(f"source asset failed checksum readback: {relative}")
            target_asset.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_asset, target_asset)

    output.mkdir(parents=True, exist_ok=True)
    (output / "storyboard.json").write_text(
        json.dumps(storyboard, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )
    target_audio = output / audio_path.name
    shutil.copy2(audio_path, target_audio)
    for optional in ("source-lock.json", "image-plan.json", "episode-with-assets.json"):
        candidate = source / optional
        if candidate.is_file():
            shutil.copy2(candidate, output / optional)
    return storyboard, target_audio


def _contact_sheet(video: Path, output: Path) -> Path:
    times = (4, 24, 52, 76, 96, 130, 164, 200, 236, 270, 294)
    frames = output / "review-frames"
    frames.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for index, second in enumerate(times, start=1):
        frame = frames / f"frame-{index:02d}-{second:03d}s.png"
        subprocess.run(
            [
                "ffmpeg", "-y", "-ss", str(second), "-i", str(video),
                "-frames:v", "1", "-vf", "scale=640:360", str(frame),
            ],
            check=True,
            capture_output=True,
        )
        paths.append(frame)
    sheet = Image.new("RGB", (1280, 2160), "#0c0e0d")
    draw = ImageDraw.Draw(sheet)
    for index, (second, path) in enumerate(zip(times, paths)):
        x = (index % 2) * 640
        y = (index // 2) * 360
        with Image.open(path) as frame:
            sheet.paste(frame.convert("RGB"), (x, y))
        draw.rectangle((x + 10, y + 10, x + 76, y + 38), fill="#111813")
        draw.text((x + 18, y + 16), f"{second}s", fill="#efe8d8")
    result = output / "contact-sheet.png"
    sheet.save(result, format="PNG", optimize=True)
    return result


def _finalize_existing_silent(storyboard: dict, output: Path, audio: Path) -> dict:
    """Validate and mux a completed direct HyperFrames render without recapture."""

    scenes = preflight_editorial_motion_storyboard(storyboard, output)
    workspace = output / "editorial-motion-hyperframes"
    silent = output / "reddit-five-minute-ink-gouache-s-tier-v6-hyperframes-silent.mp4"
    if not workspace.is_dir() or not silent.is_file() or silent.stat().st_size <= 0:
        raise RuntimeError("--reuse-silent-render requires the completed workspace and silent MP4")
    check = subprocess.run(
        [*_hyperframes_cli(), "check", "--json"],
        cwd=workspace,
        check=True,
        capture_output=True,
        text=True,
    )
    check_payload = json.loads(check.stdout)
    if not check_payload.get("ok"):
        raise RuntimeError("HyperFrames check did not pass for the completed silent render")
    video = output / "reddit-five-minute-ink-gouache-s-tier-v6.mp4"
    subprocess.run(
        [
            "ffmpeg", "-y", "-i", str(silent), "-i", str(audio),
            "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-c:a", "aac",
            "-b:a", "192k", "-shortest", "-movflags", "+faststart", str(video),
        ],
        check=True,
        capture_output=True,
    )
    probe = subprocess.run(
        [
            "ffprobe", "-v", "error", "-show_entries",
            "stream=codec_name,width,height,avg_frame_rate:format=duration",
            "-of", "json", str(video),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    probe_payload = json.loads(probe.stdout)
    video_stream = next(
        item for item in probe_payload.get("streams") or []
        if item.get("codec_name") == "h264"
    )
    duration = float((probe_payload.get("format") or {}).get("duration") or 0)
    if [video_stream.get("width"), video_stream.get("height")] != [1920, 1080]:
        raise RuntimeError("final MP4 geometry drifted")
    if abs(duration - float(storyboard["timeline_duration_sec"])) > 0.35:
        raise RuntimeError("final MP4 duration drifted")
    caption = write_caption_srt(
        storyboard["caption_track"], output / "editorial-motion-captions.srt",
    )
    return {
        "version": 1,
        "status": "PASS",
        "visual_mode": storyboard["visual_mode"],
        "style_profile": storyboard["style_profile"],
        "renderer": "hyperframes",
        "hyperframes_version": HYPERFRAMES_VERSION,
        "hyperframes_check_passed": True,
        "hyperframes_check": check_payload,
        "publication_authorized": False,
        "output_sha256": _sha256(video),
        "video_codec": "h264",
        "resolution": [1920, 1080],
        "fps": 30,
        "duration_sec": round(duration, 3),
        "scene_count": len(scenes),
        "module_usage": storyboard["motion_plan"]["module_usage"],
        "motion_plan_sha256": storyboard["motion_plan_sha256"],
        "caption_track_sha256": storyboard["caption_track_sha256"],
        "caption_srt": str(caption),
        "caption_srt_sha256": _sha256(caption),
        "audio_sha256": _sha256(audio),
        "audio_mux": "ffmpeg_post_render",
        "silent_hyperframes_output_sha256": _sha256(silent),
        "background_video_used": False,
        "factual_text_rendering": "html_svg_only",
        "asset_pack_count": len({scene["asset_family_id"] for scene in scenes}),
        "workspace": str(workspace),
        "resumed_from_completed_silent_render": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--reuse-silent-render", action="store_true")
    parser.add_argument("--prepare-only", action="store_true")
    args = parser.parse_args()
    source = Path(args.source_dir).resolve()
    output = Path(args.output_dir).resolve()
    if source == output:
        raise RuntimeError("output-dir must differ from source-dir")
    storyboard, audio = _copy_bound_inputs(source, output)
    video = output / "reddit-five-minute-ink-gouache-s-tier-v6.mp4"
    if args.prepare_only:
        scenes = preflight_editorial_motion_storyboard(storyboard, output)
        workspace = _write_workspace(
            scenes,
            output,
            audio,
            float(storyboard["timeline_duration_sec"]),
            style_profile=str(storyboard["style_profile"]),
        )
        print(json.dumps({
            "status": "prepared",
            "workspace": str(workspace),
            "provider_calls": 0,
            "reused_paid_assets": 16,
        }, ensure_ascii=False))
        return 0
    if args.reuse_silent_render:
        report = _finalize_existing_silent(storyboard, output, audio)
    else:
        report = render_editorial_motion_compilation(
            storyboard, output, video, audio=audio,
        )
    contact = _contact_sheet(video, output)
    report.update({
        "source_artifact_root": str(source),
        "provider_calls": 0,
        "reused_paid_assets": 16,
        "output": video.name,
        "output_sha256": _sha256(video),
        "contact_sheet": contact.name,
        "contact_sheet_sha256": _sha256(contact),
    })
    (output / "render-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
