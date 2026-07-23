#!/usr/bin/env python3
"""Build a production-shaped acc1 HyperFrames review from a failed canary artifact.

The workflow reuses four completed VectorEngine pages and the existing AI33
narration cut. It performs no provider or YouTube calls.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from acc1_visual_contract import FORMAT_VISUAL_SYSTEM_V3_STYLE_PROFILE


SOURCE_RUN_ID = "29975009888"
SOURCE_ARTIFACT = f"acc1-format-v3-canary-{SOURCE_RUN_ID}"
STYLE_CONTRACT = ROOT / "specs/acc1-video-style-v2.json"
CAPTION_MAX_CHARS = 44
CAPTION_FONT_SIZE = 42
CAPTION_BAND_HEIGHT = 130


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"{path.name} must contain an object")
    return payload


def resolve_generated_storyboard(download_root: Path) -> tuple[Path, dict[str, Any]]:
    matches: list[tuple[Path, dict[str, Any]]] = []
    for path in download_root.rglob("storyboard-generated.json"):
        try:
            payload = _read_object(path)
        except (OSError, json.JSONDecodeError, RuntimeError):
            continue
        if (
            payload.get("style_profile") == FORMAT_VISUAL_SYSTEM_V3_STYLE_PROFILE
            and isinstance(payload.get("slides"), list)
            and len(payload["slides"]) == 4
        ):
            matches.append((path, payload))
    if len(matches) != 1:
        raise RuntimeError(f"expected one four-page v3 storyboard, found {len(matches)}")
    path, payload = matches[0]
    if payload.get("publication_authorized") is not False:
        raise RuntimeError("review storyboard cannot authorize publication")
    if any(
        scene.get("style_profile") != FORMAT_VISUAL_SYSTEM_V3_STYLE_PROFILE
        for scene in payload["slides"]
    ):
        raise RuntimeError("scene style profile drifted from approved v3")
    return path, payload


def verify_paid_generation_receipt(storyboard_path: Path) -> dict[str, Any]:
    journal = _read_object(storyboard_path.parent / "paid-image-attempts.json")
    attempts = journal.get("attempts")
    if (
        journal.get("approved_call_cap") != 4
        or journal.get("automatic_retries") != 0
        or not isinstance(attempts, list)
        or len(attempts) != 4
        or any(item.get("status") != "complete" for item in attempts)
    ):
        raise RuntimeError("source image receipt is not exactly four completed calls without retries")
    return journal


def resolve_existing_audio(download_root: Path) -> Path:
    matches = list(download_root.rglob("narration-canary.mp3"))
    if len(matches) != 1:
        raise RuntimeError(f"expected one existing canary narration file, found {len(matches)}")
    return matches[0]


def _probe_duration(path: Path) -> float:
    completed = subprocess.run(
        [
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    duration = float(completed.stdout.strip())
    if duration <= 0:
        raise RuntimeError(f"{path.name} has no positive duration")
    return duration


def attach_production_branding(
    storyboard: dict[str, Any], artifact_root: Path,
) -> tuple[dict[str, Any], list[tuple[float, float]]]:
    contract = _read_object(STYLE_CONTRACT)
    inserts = contract["brand_inserts"]
    brand_dir = artifact_root / "brand-inserts"
    brand_dir.mkdir(parents=True, exist_ok=True)
    duration = float(storyboard["timeline_duration_sec"])
    timing = {
        "intro": 4.5,
        "subscribe_cta": round(duration * 0.40, 3),
    }
    field_names = {
        "intro": "brand_sting",
        "subscribe_cta": "brand_cta",
        "outro": "brand_outro",
    }
    hidden_intervals: list[tuple[float, float]] = []
    result = dict(storyboard)
    for key in ("intro", "subscribe_cta", "outro"):
        item = inserts[key]
        source = (ROOT / item["path"]).resolve()
        expected = str(item["sha256"])
        if not source.is_file() or _sha256(source) != expected:
            raise RuntimeError(f"approved {key} asset checksum drift")
        copied = brand_dir / source.name
        shutil.copy2(source, copied)
        insert_duration = min(_probe_duration(copied), 6.0)
        start = (
            max(0.0, duration - insert_duration)
            if key == "outro"
            else min(timing[key], max(0.0, duration - insert_duration))
        )
        result[field_names[key]] = {
            "local_path": copied.relative_to(artifact_root).as_posix(),
            "sha256": expected,
            "start_sec": round(start, 3),
            "duration_sec": round(insert_duration, 3),
            "audio_policy": "discard",
        }
        hidden_intervals.append((start, start + insert_duration))
    return result, hidden_intervals


def brand_safe_caption_track(
    caption_track: dict[str, Any], hidden_intervals: list[tuple[float, float]],
) -> dict[str, Any]:
    cues = []
    for source in caption_track.get("cues") or []:
        cue = dict(source)
        start = float(cue["start_sec"])
        end = float(cue["end_sec"])
        if any(
            start < hidden_end and end > hidden_start
            for hidden_start, hidden_end in hidden_intervals
        ):
            continue
        cues.append(cue)
    return {**caption_track, "cues": cues, "cue_count": len(cues)}


def split_caption_cue(
    cue: dict[str, Any], max_chars: int = CAPTION_MAX_CHARS,
) -> list[dict[str, Any]]:
    text = " ".join(str(cue.get("text") or "").split())
    if not text:
        raise RuntimeError("caption cue is empty")
    if max_chars <= 0:
        raise RuntimeError("caption max_chars must be positive")

    chunks: list[str] = []
    current: list[str] = []
    for word in text.split():
        if len(word) > max_chars:
            raise RuntimeError("caption contains a word longer than the one-line contract")
        candidate = " ".join([*current, word])
        if current and len(candidate) > max_chars:
            chunks.append(" ".join(current))
            current = [word]
        else:
            current.append(word)
    if current:
        chunks.append(" ".join(current))

    start = float(cue["start_sec"])
    end = float(cue["end_sec"])
    duration = end - start
    if duration <= 0:
        raise RuntimeError("caption cue duration must be positive")

    weights = [len(chunk) for chunk in chunks]
    total_weight = sum(weights)
    boundaries = [start]
    cumulative = 0
    for weight in weights[:-1]:
        cumulative += weight
        boundaries.append(start + duration * cumulative / total_weight)
    boundaries.append(end)
    return [
        {
            **cue,
            "start_sec": boundaries[index],
            "end_sec": boundaries[index + 1],
            "text": chunk,
        }
        for index, chunk in enumerate(chunks)
    ]


def normalize_caption_track(
    caption_track: dict[str, Any], max_chars: int = CAPTION_MAX_CHARS,
) -> dict[str, Any]:
    cues = [
        part
        for cue in caption_track.get("cues") or []
        for part in split_caption_cue(cue, max_chars=max_chars)
    ]
    return {**caption_track, "cues": cues, "cue_count": len(cues)}


def write_srt(
    caption_track: dict[str, Any], output: Path, max_chars: int = CAPTION_MAX_CHARS,
) -> Path:
    def stamp(seconds: float) -> str:
        milliseconds = max(0, round(seconds * 1000))
        hours, milliseconds = divmod(milliseconds, 3_600_000)
        minutes, milliseconds = divmod(milliseconds, 60_000)
        secs, milliseconds = divmod(milliseconds, 1000)
        return f"{hours:02d}:{minutes:02d}:{secs:02d},{milliseconds:03d}"

    blocks = []
    for index, cue in enumerate(caption_track.get("cues") or [], start=1):
        text = " ".join(str(cue.get("text") or "").split())
        if not text or len(text) > max_chars or "\n" in text:
            raise RuntimeError("caption cue violates the approved one-line contract")
        blocks.append(
            f"{index}\n{stamp(float(cue['start_sec']))} --> "
            f"{stamp(float(cue['end_sec']))}\n{text}",
        )
    if not blocks:
        raise RuntimeError("brand-safe caption track is empty")
    output.write_text("\n\n".join(blocks) + "\n", encoding="utf-8")
    return output


def write_ass(caption_track: dict[str, Any], output: Path) -> Path:
    def stamp(seconds: float) -> str:
        centiseconds = max(0, round(seconds * 100))
        hours, centiseconds = divmod(centiseconds, 360_000)
        minutes, centiseconds = divmod(centiseconds, 6_000)
        secs, centiseconds = divmod(centiseconds, 100)
        return f"{hours}:{minutes:02d}:{secs:02d}.{centiseconds:02d}"

    def escape(text: str) -> str:
        return text.replace("\\", r"\\").replace("{", r"\{").replace("}", r"\}")

    events = []
    for cue in caption_track.get("cues") or []:
        text = " ".join(str(cue.get("text") or "").split())
        if not text or len(text) > CAPTION_MAX_CHARS or "\n" in text:
            raise RuntimeError("caption cue violates the approved one-line contract")
        events.append(
            f"Dialogue: 0,{stamp(float(cue['start_sec']))},{stamp(float(cue['end_sec']))},"
            f"Caption,,0,0,0,,{escape(text)}",
        )
    if not events:
        raise RuntimeError("brand-safe caption track is empty")
    output.write_text(
        "\n".join([
            "[Script Info]",
            "ScriptType: v4.00+",
            "PlayResX: 1920",
            "PlayResY: 1080",
            "ScaledBorderAndShadow: yes",
            "",
            "[V4+ Styles]",
            "Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,"
            "BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,"
            "BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding",
            f"Style: Caption,Arial,{CAPTION_FONT_SIZE},&H00EAF2F5,&H000000FF,&H00101010,"
            "&H00000000,-1,0,0,0,100,100,0,0,1,1,0,2,0,0,38,1",
            "",
            "[Events]",
            "Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text",
            *events,
            "",
        ]),
        encoding="utf-8",
    )
    return output


def subtitle_filter(captions: Path) -> str:
    subtitle_name = captions.name.replace("'", r"\'")
    return f"ass=filename='{subtitle_name}'"


def burn_captions(source: Path, captions: Path, output: Path) -> None:
    subprocess.run(
        [
            "ffmpeg", "-y", "-v", "error", "-i", str(source),
            "-vf", subtitle_filter(captions), "-c:v", "libx264", "-preset", "medium",
            "-crf", "18", "-pix_fmt", "yuv420p", "-c:a", "copy",
            "-movflags", "+faststart", str(output),
        ],
        cwd=captions.parent,
        check=True,
    )
    if not output.is_file() or output.stat().st_size <= 0:
        raise RuntimeError("caption burn produced no MP4")


def extract_review_frames(video: Path, storyboard: dict[str, Any], output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    for index, scene in enumerate(storyboard["slides"], start=1):
        timestamp = float(scene["start_sec"]) + float(scene["duration_sec"]) * 0.34
        subprocess.run(
            [
                "ffmpeg", "-y", "-v", "error", "-ss", f"{timestamp:.3f}",
                "-i", str(video), "-frames:v", "1",
                str(output / f"frame-{index:02d}.png"),
            ],
            check=True,
        )


def main() -> int:
    from compilation_renderer import render_compilation

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-root", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()

    download_root = Path(args.artifact_root).resolve()
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    storyboard_path, storyboard = resolve_generated_storyboard(download_root)
    journal = verify_paid_generation_receipt(storyboard_path)
    artifact_root = storyboard_path.parent
    audio_source = resolve_existing_audio(download_root)
    audio = artifact_root / "narration-hyperframes-test.mp3"
    shutil.copy2(audio_source, audio)
    branded_storyboard, hidden_intervals = attach_production_branding(storyboard, artifact_root)

    base_video = artifact_root / "hyperframes-realistic-base.mp4"
    render_report = render_compilation(
        branded_storyboard,
        artifact_root,
        base_video,
        audio=audio,
    )
    intermediate_video = output_dir / "hyperframes-intermediate.mp4"
    shutil.copy2(base_video, intermediate_video)
    partial_report = {
        **render_report,
        "status": "HYPERFRAMES_RENDERED_AWAITING_POSTPROCESS",
        "source_run_id": SOURCE_RUN_ID,
        "source_artifact": SOURCE_ARTIFACT,
        "style_profile": FORMAT_VISUAL_SYSTEM_V3_STYLE_PROFILE,
        "renderer": "hyperframes",
        "source_image_calls": len(journal["attempts"]),
        "source_image_retries": journal["automatic_retries"],
        "new_image_calls": 0,
        "new_ai33_calls": 0,
        "youtube_called": False,
        "intermediate_video": intermediate_video.name,
        "intermediate_video_sha256": _sha256(intermediate_video),
    }
    (output_dir / "render-report.json").write_text(
        json.dumps(partial_report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    safe_track = normalize_caption_track(
        brand_safe_caption_track(storyboard["caption_track"], hidden_intervals),
    )
    captions = write_srt(safe_track, artifact_root / "captions-brand-safe.srt")
    captions_ass = write_ass(safe_track, artifact_root / "captions-brand-safe.ass")
    final_video = output_dir / "acc1-hyperframes-realistic-test.mp4"
    burn_captions(base_video, captions_ass, final_video)
    extract_review_frames(final_video, storyboard, output_dir / "frames")
    shutil.copy2(captions, output_dir / captions.name)
    shutil.copy2(captions_ass, output_dir / captions_ass.name)
    shutil.copy2(storyboard_path, output_dir / "storyboard-generated.json")

    report = {
        **render_report,
        "status": "PASS",
        "source_run_id": SOURCE_RUN_ID,
        "source_artifact": SOURCE_ARTIFACT,
        "style_profile": FORMAT_VISUAL_SYSTEM_V3_STYLE_PROFILE,
        "renderer": "hyperframes",
        "source_image_calls": len(journal["attempts"]),
        "source_image_retries": journal["automatic_retries"],
        "new_image_calls": 0,
        "new_ai33_calls": 0,
        "youtube_called": False,
        "captions_burned": True,
        "caption_band_height_px": CAPTION_BAND_HEIGHT,
        "caption_max_chars": CAPTION_MAX_CHARS,
        "caption_font_size_px": CAPTION_FONT_SIZE,
        "caption_layout": "ass_1920x1080",
        "brand_safe_caption_cues": len(safe_track["cues"]),
        "final_video": final_video.name,
        "final_video_sha256": _sha256(final_video),
    }
    (output_dir / "render-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
