"""Deterministic burned-caption helpers for acc1 review videos."""

from __future__ import annotations

import hashlib
import math
import shutil
import subprocess
from pathlib import Path
from typing import Any


PLAY_RES_X = 1920
PLAY_RES_Y = 1080
CAPTION_FONT_SIZE = 42
CAPTION_MARGIN_V = 38
CAPTION_MAX_CHARS = 90


class CaptionBurnError(RuntimeError):
    """Raised when the fixed one-line caption contract cannot be rendered."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _stamp(seconds: float) -> str:
    centiseconds = max(0, round(seconds * 100))
    hours, centiseconds = divmod(centiseconds, 360_000)
    minutes, centiseconds = divmod(centiseconds, 6_000)
    secs, centiseconds = divmod(centiseconds, 100)
    return f"{hours}:{minutes:02d}:{secs:02d}.{centiseconds:02d}"


def _escape_ass(text: str) -> str:
    return (
        text.replace("\\", r"\\")
        .replace("{", r"\{")
        .replace("}", r"\}")
        .replace("\n", " ")
    )


def write_caption_ass(caption_track: dict[str, Any], output: Path) -> Path:
    """Write the approved single-line caption track for the fixed 1080p band."""

    events: list[str] = []
    previous_end = 0.0
    for cue in caption_track.get("cues") or []:
        text = " ".join(str(cue.get("text") or "").split())
        start = float(cue.get("start_sec") or 0)
        end = float(cue.get("end_sec") or 0)
        if (
            not text
            or len(text) > CAPTION_MAX_CHARS
            or start < previous_end - 0.002
            or end <= start
        ):
            raise CaptionBurnError("caption cue violates the fixed one-line contract")
        events.append(
            f"Dialogue: 0,{_stamp(start)},{_stamp(end)},Caption,,0,0,0,,"
            rf"{{\q2}}{_escape_ass(text)}",
        )
        previous_end = end
    if not events:
        raise CaptionBurnError("caption track is empty")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        "\n".join([
            "[Script Info]",
            "ScriptType: v4.00+",
            f"PlayResX: {PLAY_RES_X}",
            f"PlayResY: {PLAY_RES_Y}",
            "WrapStyle: 2",
            "ScaledBorderAndShadow: yes",
            "",
            "[V4+ Styles]",
            "Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,"
            "BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,"
            "BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding",
            f"Style: Caption,Arial,{CAPTION_FONT_SIZE},&H00F7F7F7,&H000000FF,"
            "&H00101010,&H00000000,-1,0,0,0,100,100,0,0,1,1.6,0,2,70,70,"
            f"{CAPTION_MARGIN_V},1",
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
    name = captions.name.replace("\\", r"\\").replace("'", r"\'")
    return f"ass=filename='{name}'"


def burn_captions(
    source: Path,
    captions: Path,
    output: Path,
    *,
    target_duration_sec: float | None = None,
    fps: int | None = None,
) -> None:
    """Burn ASS captions while preserving the already-approved audio track.

    A segmented render may accumulate sub-frame timestamp rounding when its
    H.264 parts are concatenated.  When a target duration is supplied, make
    the video stream exactly frame-aligned before burning captions so that the
    final container cannot inherit that cumulative drift.
    """

    if (target_duration_sec is None) != (fps is None):
        raise CaptionBurnError(
            "target duration and fps must be supplied together",
        )
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise CaptionBurnError("ffmpeg is required for burned captions")
    video_filter = subtitle_filter(captions)
    target_args: list[str] = []
    if target_duration_sec is not None and fps is not None:
        if (
            isinstance(fps, bool)
            or not isinstance(fps, int)
            or fps <= 0
            or isinstance(target_duration_sec, bool)
            or not isinstance(target_duration_sec, (int, float))
            or not math.isfinite(target_duration_sec)
            or target_duration_sec <= 0
        ):
            raise CaptionBurnError("caption duration normalization is invalid")
        target_frames = max(
            1,
            math.ceil(target_duration_sec * fps - 1e-9),
        )
        frame_aligned_duration = target_frames / fps
        video_filter = ",".join([
            f"fps={fps}",
            (
                "tpad=stop_mode=clone:"
                f"stop_duration={frame_aligned_duration:.6f}"
            ),
            f"trim=end_frame={target_frames}",
            f"setpts=N/({fps}*TB)",
            video_filter,
        ])
        target_args = [
            "-frames:v",
            str(target_frames),
            "-t",
            f"{frame_aligned_duration:.6f}",
        ]
    output.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            ffmpeg,
            "-y",
            "-v",
            "error",
            "-i",
            str(source),
            "-vf",
            video_filter,
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "18",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "copy",
            *target_args,
            "-movflags",
            "+faststart",
            str(output),
        ],
        cwd=captions.parent,
        check=True,
    )
    if not output.is_file() or output.stat().st_size <= 0:
        raise CaptionBurnError("caption burn produced no MP4")
