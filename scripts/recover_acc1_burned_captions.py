#!/usr/bin/env python3
"""Burn existing acc1 captions without provider calls or a visual rerender."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from acc1_caption_burn import burn_captions, sha256_file, write_caption_ass
from acc1_editorial_motion import verify_bound_payload


def read_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"{path.name} must contain an object")
    return payload


def probe(path: Path) -> dict[str, Any]:
    completed = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "stream=codec_type,codec_name,width,height:format=duration",
            "-of",
            "json",
            str(path),
        ],
        check=True,
        text=True,
        capture_output=True,
    )
    payload = json.loads(completed.stdout)
    streams = payload.get("streams") or []
    video = next(item for item in streams if item.get("codec_type") == "video")
    audio = next(item for item in streams if item.get("codec_type") == "audio")
    return {
        "duration_sec": float((payload.get("format") or {}).get("duration") or 0),
        "video_codec": video.get("codec_name"),
        "audio_codec": audio.get("codec_name"),
        "resolution": [video.get("width"), video.get("height")],
    }


def extract_review_frames(
    video: Path,
    caption_track: dict[str, Any],
    output_dir: Path,
) -> list[str]:
    cues = caption_track.get("cues") or []
    selected = [cues[0], cues[len(cues) // 2], cues[-1]]
    output_dir.mkdir(parents=True, exist_ok=True)
    names: list[str] = []
    for index, cue in enumerate(selected, start=1):
        timestamp = (
            float(cue["start_sec"]) + float(cue["end_sec"])
        ) / 2
        name = f"caption-review-{index:02d}.png"
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-v",
                "error",
                "-ss",
                f"{timestamp:.3f}",
                "-i",
                str(video),
                "-frames:v",
                "1",
                str(output_dir / name),
            ],
            check=True,
        )
        names.append(name)
    return names


def recover(source_root: Path, output_root: Path, *, source_run_id: str) -> dict[str, Any]:
    source_root = source_root.resolve()
    output_root = output_root.resolve()
    source_video = source_root / "final-output.mp4"
    source_srt = source_root / "editorial-motion-captions.srt"
    storyboard = read_object(source_root / "storyboard.json")
    render_report = read_object(source_root / "render-report.json")
    release_result = read_object(source_root / "fixed-release-result.json")
    if (
        not source_video.is_file()
        or not source_srt.is_file()
        or render_report.get("status") != "PASS"
        or render_report.get("provider_calls") != 0
        or render_report.get("youtube_called") is not False
        or release_result.get("status") != "READY_FOR_HUMAN_REVIEW"
        or release_result.get("youtube_called") is not False
        or sha256_file(source_video) != release_result.get("video_sha256")
        or sha256_file(source_srt) != render_report.get("caption_srt_sha256")
    ):
        raise RuntimeError("source artifact is not the exact safe review package")
    caption_track = storyboard.get("caption_track")
    if (
        not verify_bound_payload(caption_track, "caption_track_sha256")
        or storyboard.get("caption_track_sha256")
        != caption_track.get("caption_track_sha256")
        or render_report.get("caption_track_sha256")
        != caption_track.get("caption_track_sha256")
    ):
        raise RuntimeError("caption track binding does not match the source artifact")

    output_root.mkdir(parents=True, exist_ok=True)
    captions_ass = write_caption_ass(
        caption_track,
        output_root / "editorial-motion-captions.ass",
    )
    final_video = output_root / "final-output-captioned.mp4"
    burn_captions(source_video, captions_ass, final_video)
    source_probe = probe(source_video)
    final_probe = probe(final_video)
    if (
        final_probe["video_codec"] != "h264"
        or final_probe["audio_codec"] != source_probe["audio_codec"]
        or final_probe["resolution"] != [1920, 1080]
        or abs(final_probe["duration_sec"] - source_probe["duration_sec"]) > 0.12
        or sha256_file(final_video) == sha256_file(source_video)
    ):
        raise RuntimeError("captioned MP4 failed codec, duration, or identity checks")
    shutil.copy2(source_srt, output_root / source_srt.name)
    review_frames = extract_review_frames(
        final_video,
        caption_track,
        output_root / "review-frames",
    )
    report = {
        "version": 1,
        "status": "READY_FOR_HUMAN_REVIEW",
        "source_run_id": source_run_id,
        "source_video_sha256": sha256_file(source_video),
        "captioned_video": final_video.name,
        "captioned_video_sha256": sha256_file(final_video),
        "caption_srt_sha256": sha256_file(source_srt),
        "caption_ass_sha256": sha256_file(captions_ass),
        "caption_track_sha256": caption_track["caption_track_sha256"],
        "caption_cue_count": len(caption_track["cues"]),
        "captions_burned": True,
        "fixed_subtitle_band": {"y": 950, "height": 130, "line_count": 1},
        "source_probe": source_probe,
        "captioned_probe": final_probe,
        "review_frames": review_frames,
        "provider_calls": 0,
        "new_image_calls": 0,
        "new_ai33_task_submissions": 0,
        "publication_authorized": False,
        "youtube_called": False,
    }
    (output_root / "caption-recovery-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", required=True)
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--source-run-id", required=True)
    args = parser.parse_args()
    result = recover(
        Path(args.source_root),
        Path(args.output_root),
        source_run_id=str(args.source_run_id),
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
