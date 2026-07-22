#!/usr/bin/env python3
"""Render four existing acc1 comic scenes with existing master audio only."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from acc1_editorial_motion import bind_payload
from acc1_visual_contract import EDITORIAL_MOTION_MODULES
from chrome_guided_webtoon_renderer import render_chrome_guided_webtoon


def _read(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"{path.name} must contain an object")
    return value


def resolve_storyboard(download_root: Path) -> Path:
    matches = []
    for path in download_root.rglob("*storyboard*.json"):
        try:
            payload = _read(path)
        except (OSError, json.JSONDecodeError, RuntimeError):
            continue
        if (
            isinstance(payload.get("slides"), list)
            and isinstance(payload.get("motion_plan"), dict)
            and payload.get("style_profile") == "cinematic_ink_webtoon_v1"
        ):
            matches.append(path)
    if len(matches) != 1:
        raise RuntimeError(f"expected exactly one production webtoon storyboard, found {len(matches)}")
    return matches[0]


def resolve_master_audio(download_root: Path) -> Path:
    matches = list(download_root.rglob("narration-master.mp3"))
    if len(matches) != 1:
        raise RuntimeError(f"expected exactly one narration-master.mp3, found {len(matches)}")
    return matches[0]


def build_canary_storyboard(source: dict, *, scene_count: int = 4) -> tuple[dict, float, float]:
    slides = list(source.get("slides") or [])
    start_index = next((index for index, scene in enumerate(slides)
                        if scene.get("presentation") == "story"), None)
    if start_index is None:
        raise RuntimeError("source storyboard has no story scenes")
    selected = slides[start_index:start_index + scene_count]
    if len(selected) != scene_count or any(scene.get("presentation") != "story" for scene in selected):
        raise RuntimeError("source storyboard has no four consecutive story scenes")
    if len({(scene.get("motion") or {}).get("module") for scene in selected}) < 2:
        raise RuntimeError("canary needs at least two semantic camera modules")

    source_start = float(selected[0]["start_sec"])
    source_end = float(selected[-1]["end_sec"])
    rebased = []
    cursor = 0.0
    for scene in selected:
        duration = float(scene["duration_sec"])
        rebased.append({**scene, "start_sec": round(cursor, 3),
                        "end_sec": round(cursor + duration, 3)})
        cursor += duration
    duration = round(cursor, 3)

    original_plan = dict(source["motion_plan"])
    original_plan.pop("motion_plan_sha256", None)
    original_plan.update({
        "timeline_duration_sec": duration,
        "scene_count": len(rebased),
        "module_usage": {
            module: sum((scene.get("motion") or {}).get("module") == module for scene in rebased)
            for module in EDITORIAL_MOTION_MODULES
        },
        "scenes": rebased,
    })
    motion_plan = bind_payload(original_plan, "motion_plan_sha256")

    source_cues = (source.get("caption_track") or {}).get("cues") or []
    cues = []
    for cue in source_cues:
        cue_start, cue_end = float(cue["start_sec"]), float(cue["end_sec"])
        if cue_end <= source_start or cue_start >= source_end:
            continue
        cues.append({**cue, "cue_id": f"cue-{len(cues) + 1:04d}",
                     "start_sec": round(max(cue_start, source_start) - source_start, 3),
                     "end_sec": round(min(cue_end, source_end) - source_start, 3)})
    if not cues:
        raise RuntimeError("source storyboard has no captions for selected scenes")
    caption_source = dict(source["caption_track"])
    caption_source.pop("caption_track_sha256", None)
    caption_source.update({"timeline_duration_sec": duration, "cue_count": len(cues), "cues": cues})
    caption_track = bind_payload(caption_source, "caption_track_sha256")

    storyboard = {
        **source,
        "slides": rebased,
        "timeline_duration_sec": duration,
        "motion_plan": motion_plan,
        "motion_plan_sha256": motion_plan["motion_plan_sha256"],
        "caption_track": caption_track,
        "caption_track_sha256": caption_track["caption_track_sha256"],
        "publication_authorized": False,
    }
    return storyboard, source_start, source_end


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-root", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--scene-count", type=int, default=4, choices=range(3, 6))
    args = parser.parse_args()
    download_root = Path(args.artifact_root).resolve()
    storyboard_path = resolve_storyboard(download_root)
    root = storyboard_path.parent
    output = Path(args.output_dir).resolve()
    output.mkdir(parents=True, exist_ok=True)
    source = _read(storyboard_path)
    storyboard, start, end = build_canary_storyboard(source, scene_count=args.scene_count)
    (output / "storyboard-canary.json").write_text(
        json.dumps(storyboard, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    master = resolve_master_audio(download_root)
    audio = output / "narration-canary.mp3"
    subprocess.run(["ffmpeg", "-y", "-ss", f"{start:.3f}", "-t", f"{end-start:.3f}",
                    "-i", str(master), "-vn", "-c:a", "libmp3lame", "-q:a", "2", str(audio)],
                   check=True)
    video = output / "webtoon-canary.mp4"
    report = render_chrome_guided_webtoon(storyboard, root, video, audio=audio)
    report.update({"source_run_id": "29888971818", "scene_count": args.scene_count,
                   "new_ai33_calls": 0, "new_image_calls": 0, "youtube_called": False})
    (output / "render-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    frame_dir = output / "frames"
    frame_dir.mkdir(exist_ok=True)
    subprocess.run([
        "ffmpeg", "-y", "-i", str(video),
        "-vf", f"fps=4/{storyboard['timeline_duration_sec']}",
        "-frames:v", "4", str(frame_dir / "frame-%02d.png"),
    ], check=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
