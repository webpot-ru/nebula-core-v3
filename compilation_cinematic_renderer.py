"""Artifact-only renderer for checksum-bound ``cinematic_story_v1`` boards."""

from __future__ import annotations

import hashlib
import json
import math
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont, UnidentifiedImageError

from acc1_cinematic_shots import (
    CinematicShotError,
    canonical_hash,
    verify_bound_payload,
    write_caption_srt,
)
from acc1_visual_contract import (
    CANVAS_FPS as FPS,
    CANVAS_HEIGHT as HEIGHT,
    CANVAS_WIDTH as WIDTH,
    CINEMATIC_PAN_CENTER_MAX,
    CINEMATIC_PAN_CENTER_MIN,
    CINEMATIC_SERVICE_SHOT_MAX_SECONDS,
    CINEMATIC_STORY_MODE,
    CINEMATIC_STORY_SHOT_MAX_SECONDS,
    CINEMATIC_STORY_SHOT_MIN_SECONDS,
    CINEMATIC_ZOOM_END_MAX,
    CINEMATIC_ZOOM_END_MIN,
)


ALLOWED_IMAGE_FORMATS = {"JPEG", "PNG", "WEBP"}
MAX_PIXELS = 40_000_000
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class CinematicRenderError(RuntimeError):
    """Raised when a cinematic artifact is not exact, local, or renderable."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _local_image(slide: dict[str, Any], artifact_root: Path) -> Path:
    visual = slide.get("visual")
    if not isinstance(visual, dict):
        raise CinematicRenderError("cinematic shot has no visual object")
    raw = str(visual.get("local_path") or "")
    root = Path(artifact_root).resolve()
    candidate = Path(raw).expanduser()
    path = candidate.resolve() if candidate.is_absolute() else (root / candidate).resolve()
    if path == root or root not in path.parents or not path.is_file():
        raise CinematicRenderError("cinematic image must be a file under artifact_root")
    expected = str(visual.get("sha256") or "").strip().lower()
    if not SHA256_RE.fullmatch(expected):
        raise CinematicRenderError("cinematic image requires a valid sha256")
    if str(slide.get("visual_sha256") or "").strip().lower() != expected:
        raise CinematicRenderError("cinematic shot visual checksum binding mismatch")
    if _sha256(path) != expected:
        raise CinematicRenderError("cinematic image checksum mismatch")
    try:
        with Image.open(path) as image:
            if image.format not in ALLOWED_IMAGE_FORMATS:
                raise CinematicRenderError(
                    f"unsupported cinematic image format: {image.format}",
                )
            if image.width * image.height > MAX_PIXELS:
                raise CinematicRenderError("cinematic image exceeds pixel limit")
            image.verify()
    except (UnidentifiedImageError, OSError) as exc:
        raise CinematicRenderError(f"cinematic image decode failed: {exc}") from exc
    return path


def _storyboard_bindings(storyboard: dict[str, Any]) -> dict[str, Any]:
    creative = storyboard.get("creative_manifest")
    if not isinstance(creative, dict):
        raise CinematicRenderError("cinematic storyboard requires creative_manifest")
    if creative.get("mode") != CINEMATIC_STORY_MODE:
        raise CinematicRenderError("creative manifest cinematic mode mismatch")
    bindings: dict[str, Any] = {}
    for field in (
        "episode_plan_sha256",
        "daily_plan_sha256",
        "audio_sha256",
        "narration_plan_sha256",
    ):
        digest = str(storyboard.get(field) or "").strip().lower()
        if not SHA256_RE.fullmatch(digest):
            raise CinematicRenderError(f"storyboard {field} must be a SHA-256 digest")
        if creative.get(field) != digest:
            raise CinematicRenderError(f"creative manifest {field} does not match storyboard")
        bindings[field] = digest
    timing_digest = str(
        storyboard.get("timing_contract_sha256") or "",
    ).strip().lower()
    if (
        not SHA256_RE.fullmatch(timing_digest)
        or creative.get("timing_contract_sha256") != timing_digest
    ):
        raise CinematicRenderError(
            "cinematic timing_contract_sha256 binding mismatch",
        )
    try:
        final_duration = float(storyboard.get("final_audio_duration_sec") or 0)
        creative_duration = float(
            creative.get("final_audio_duration_sec") or 0,
        )
    except (TypeError, ValueError) as exc:
        raise CinematicRenderError(
            "cinematic final audio duration binding is invalid",
        ) from exc
    if final_duration <= 0 or abs(final_duration - creative_duration) > 1e-6:
        raise CinematicRenderError(
            "cinematic final audio duration binding mismatch",
        )
    bindings["timing_contract_sha256"] = timing_digest
    bindings["final_audio_duration_sec"] = final_duration
    if (
        storyboard.get("publication_authorized") is not False
        or creative.get("publication_authorized") is not False
    ):
        raise CinematicRenderError("cinematic storyboard cannot authorize publication")
    return bindings


def _motion(slide: dict[str, Any]) -> dict[str, Any]:
    motion = slide.get("motion")
    if not isinstance(motion, dict) or motion.get("type") != "slow_push_pan":
        raise CinematicRenderError("cinematic shot requires slow_push_pan motion")
    try:
        start_scale = float(motion["start_scale"])
        end_scale = float(motion["end_scale"])
        start_center = [float(item) for item in motion["start_center"]]
        end_center = [float(item) for item in motion["end_center"]]
    except (KeyError, TypeError, ValueError) as exc:
        raise CinematicRenderError("cinematic motion contract is invalid") from exc
    if (
        abs(start_scale - 1.0) > 1e-6
        or not CINEMATIC_ZOOM_END_MIN <= end_scale <= CINEMATIC_ZOOM_END_MAX
        or len(start_center) != 2
        or len(end_center) != 2
        or any(
            not CINEMATIC_PAN_CENTER_MIN <= coordinate <= CINEMATIC_PAN_CENTER_MAX
            for coordinate in start_center + end_center
        )
        or motion.get("easing") != "linear"
    ):
        raise CinematicRenderError("cinematic motion exceeds the approved push/pan bounds")
    return {
        "type": "slow_push_pan",
        "start_scale": start_scale,
        "end_scale": end_scale,
        "start_center": start_center,
        "end_center": end_center,
        "easing": "linear",
    }


def preflight_cinematic_storyboard(
    storyboard: dict[str, Any], artifact_root: Path,
) -> list[dict[str, Any]]:
    """Verify hashes, local images, timing and motion without rendering."""

    if (
        storyboard.get("visual_mode") != CINEMATIC_STORY_MODE
        or storyboard.get("format") != "compilation_16x9"
        or storyboard.get("resolution") != [WIDTH, HEIGHT]
    ):
        raise CinematicRenderError(
            "cinematic storyboard must be cinematic_story_v1 at 1920x1080",
        )
    if storyboard.get("background_video") not in (None, ""):
        raise CinematicRenderError("cinematic_story_v1 does not accept background_video")
    bindings = _storyboard_bindings(storyboard)
    shot_plan = storyboard.get("shot_plan")
    captions = storyboard.get("caption_track")
    if not verify_bound_payload(shot_plan, "shot_plan_sha256"):
        raise CinematicRenderError("cinematic shot plan checksum mismatch")
    if not verify_bound_payload(captions, "caption_track_sha256"):
        raise CinematicRenderError("cinematic caption track checksum mismatch")
    shot_hash = str(shot_plan["shot_plan_sha256"])
    caption_hash = str(captions["caption_track_sha256"])
    creative = storyboard["creative_manifest"]
    if (
        storyboard.get("shot_plan_sha256") != shot_hash
        or creative.get("shot_plan_sha256") != shot_hash
        or storyboard.get("caption_track_sha256") != caption_hash
        or creative.get("caption_track_sha256") != caption_hash
    ):
        raise CinematicRenderError("cinematic plan hash binding mismatch")
    slides = storyboard.get("slides")
    if not isinstance(slides, list) or not slides or shot_plan.get("shots") != slides:
        raise CinematicRenderError("cinematic slides must exactly match the bound shot plan")
    if (
        shot_plan.get("visual_mode") != CINEMATIC_STORY_MODE
        or shot_plan.get("resolution") != [WIDTH, HEIGHT]
        or shot_plan.get("fps") != FPS
        or shot_plan.get("shot_count") != len(slides)
    ):
        raise CinematicRenderError("cinematic shot plan geometry/count mismatch")

    checked: list[dict[str, Any]] = []
    seen: set[str] = set()
    previous_end = 0.0
    for index, source in enumerate(slides):
        if not isinstance(source, dict):
            raise CinematicRenderError(f"cinematic shot {index} is not an object")
        slide = dict(source)
        shot_id = str(slide.get("shot_id") or "")
        if (
            slide.get("kind") != "cinematic_shot"
            or not shot_id
            or slide.get("slide_id") != shot_id
            or shot_id in seen
        ):
            raise CinematicRenderError("cinematic shot ids must be present, equal, and unique")
        seen.add(shot_id)
        try:
            start = float(slide["start_sec"])
            end = float(slide["end_sec"])
            duration = float(slide["duration_sec"])
        except (KeyError, TypeError, ValueError) as exc:
            raise CinematicRenderError(f"{shot_id} requires numeric timing") from exc
        if (
            start < 0
            or end <= start
            or abs((end - start) - duration) > 0.002
            or abs(start - previous_end) > 0.002
        ):
            raise CinematicRenderError(f"{shot_id} has a timing gap, overlap, or mismatch")
        presentation = str(slide.get("presentation") or "")
        if presentation == "story":
            if not (
                CINEMATIC_STORY_SHOT_MIN_SECONDS - 0.002
                <= duration
                <= CINEMATIC_STORY_SHOT_MAX_SECONDS + 0.002
            ):
                raise CinematicRenderError(f"{shot_id} violates story-shot duration bounds")
        elif (
            presentation not in {"intro", "transition", "mid_story_cta", "outro"}
            or not 0.5 <= duration <= CINEMATIC_SERVICE_SHOT_MAX_SECONDS + 0.002
        ):
            raise CinematicRenderError(f"{shot_id} has unsupported presentation/duration")
        narration = " ".join(str(slide.get("narration_text") or "").split())
        if (
            not narration
            or hashlib.sha256(narration.encode("utf-8")).hexdigest()
            != slide.get("text_sha256")
        ):
            raise CinematicRenderError(f"{shot_id} narration checksum mismatch")
        slide["verified_image_path"] = str(_local_image(slide, artifact_root))
        slide["motion"] = _motion(slide)
        checked.append(slide)
        previous_end = end

    caption_cues = captions.get("cues")
    if not isinstance(caption_cues, list) or not caption_cues:
        raise CinematicRenderError("cinematic caption track contains no cues")
    shot_text = " ".join(
        " ".join(str(slide.get("narration_text") or "").split())
        for slide in checked
    )
    caption_text = " ".join(
        " ".join(str(cue.get("text") or "").split())
        for cue in caption_cues
    )
    caption_text_sha = hashlib.sha256(shot_text.encode("utf-8")).hexdigest()
    if (
        caption_text != shot_text
        or captions.get("text_sha256") != caption_text_sha
        or creative.get("narration_sha256") != caption_text_sha
    ):
        raise CinematicRenderError(
            "cinematic captions do not bind to exact shot narration",
        )
    shot_segment_order = list(dict.fromkeys(
        str(slide.get("segment_id") or "") for slide in checked
    ))
    caption_segment_order = list(dict.fromkeys(
        str(cue.get("segment_id") or "") for cue in caption_cues
    ))
    if caption_segment_order != shot_segment_order:
        raise CinematicRenderError(
            "cinematic caption segment order does not match shots",
        )
    segment_windows: dict[str, tuple[float, float]] = {}
    for slide in checked:
        segment_id = str(slide.get("segment_id") or "")
        start, end = segment_windows.get(
            segment_id,
            (float(slide["start_sec"]), float(slide["end_sec"])),
        )
        segment_windows[segment_id] = (
            min(start, float(slide["start_sec"])),
            max(end, float(slide["end_sec"])),
        )
    for cue in caption_cues:
        segment_id = str(cue.get("segment_id") or "")
        window = segment_windows.get(segment_id)
        try:
            cue_start = float(cue["start_sec"])
            cue_end = float(cue["end_sec"])
        except (KeyError, TypeError, ValueError) as exc:
            raise CinematicRenderError("cinematic caption cue timing is invalid") from exc
        if (
            window is None
            or cue_start + 0.002 < window[0]
            or cue_end > window[1] + 0.002
        ):
            raise CinematicRenderError(
                "cinematic caption cue escapes its narration segment",
            )

    try:
        timeline_duration = float(storyboard.get("timeline_duration_sec") or 0)
        bound_audio_duration = float(storyboard.get("final_audio_duration_sec") or 0)
    except (TypeError, ValueError) as exc:
        raise CinematicRenderError("cinematic timeline duration is invalid") from exc
    if (
        abs(previous_end - timeline_duration) > 0.002
        or abs(previous_end - bound_audio_duration) > 0.002
        or abs(float(shot_plan.get("timeline_duration_sec") or 0) - previous_end) > 0.002
        or abs(float(captions.get("timeline_duration_sec") or 0) - previous_end) > 0.002
    ):
        raise CinematicRenderError("cinematic timeline does not cover bound narration audio")
    if bindings["audio_sha256"] != storyboard.get("audio_sha256"):
        raise CinematicRenderError("cinematic audio binding mismatch")
    try:
        with tempfile.TemporaryDirectory(prefix="cinematic-caption-preflight-") as temp:
            write_caption_srt(captions, Path(temp) / "captions.srt")
    except (CinematicShotError, OSError) as exc:
        raise CinematicRenderError(str(exc)) from exc
    return checked


def _cover_crop(
    source: Image.Image,
    *,
    scale: float,
    center: list[float],
) -> Image.Image:
    source = source.convert("RGB")
    base_scale = max(WIDTH / source.width, HEIGHT / source.height)
    resized = source.resize(
        (
            max(WIDTH, math.ceil(source.width * base_scale * scale)),
            max(HEIGHT, math.ceil(source.height * base_scale * scale)),
        ),
        Image.Resampling.LANCZOS,
    )
    extra_x = resized.width - WIDTH
    extra_y = resized.height - HEIGHT
    left = round(extra_x * center[0])
    top = round(extra_y * center[1])
    return resized.crop((left, top, left + WIDTH, top + HEIGHT))


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for path in (
        Path("/System/Library/Fonts/Supplemental/Arial Bold.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
    ):
        if path.is_file():
            return ImageFont.truetype(str(path), size=size)
    return ImageFont.load_default()


def _clean_overlay_text(value: Any, *, limit: int = 120) -> str:
    """Return one bounded display line for a burned-in service overlay."""

    return " ".join(str(value or "").split())[:limit]


def _wrapped_overlay_lines(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    *,
    max_width: int,
    max_lines: int,
) -> list[str]:
    """Wrap display text by measured pixels and ellipsize only the final line."""

    words = str(text or "").split()
    if not words or max_width <= 0 or max_lines < 1:
        return []

    def width(value: str) -> int:
        box = draw.textbbox((0, 0), value, font=font)
        return box[2] - box[0]

    def ellipsize(value: str) -> str:
        suffix = "…"
        candidate = value.strip()
        while candidate and width(candidate + suffix) > max_width:
            candidate = candidate[:-1].rstrip()
        return candidate + suffix if candidate else suffix

    lines: list[str] = []
    cursor = 0
    while cursor < len(words) and len(lines) < max_lines:
        line = words[cursor]
        cursor += 1
        if width(line) > max_width:
            line = ellipsize(line)
        while cursor < len(words):
            candidate = f"{line} {words[cursor]}"
            if width(candidate) > max_width:
                break
            line = candidate
            cursor += 1
        if len(lines) == max_lines - 1 and cursor < len(words):
            line = ellipsize(" ".join([line, *words[cursor:]]))
            cursor = len(words)
        lines.append(line)
    return lines


def _truth_label(value: Any) -> str:
    truth_mode = _clean_overlay_text(value, limit=64)
    return {
        "fiction": "ХУДОЖЕСТВЕННАЯ ИСТОРИЯ",
        "unverified_personal_account": (
            "ЛИЧНЫЙ РАССКАЗ • НЕ ПОДТВЕРЖДЁН НЕЗАВИСИМО"
        ),
    }.get(truth_mode, truth_mode.upper())


def _service_overlay_slide(
    slides: list[dict[str, Any]], index: int,
) -> dict[str, Any]:
    """Bind intro/transition disclosure to the story that immediately follows."""

    slide = dict(slides[index])
    if slide.get("presentation") not in {"intro", "transition"}:
        return slide
    following_story = next(
        (
            candidate
            for candidate in slides[index + 1:]
            if candidate.get("presentation") == "story"
        ),
        None,
    )
    if not isinstance(following_story, dict):
        return slide
    for field in ("story_title", "source_label", "truth_mode"):
        value = following_story.get(field)
        if value not in (None, ""):
            slide[field] = value
    return slide


def _draw_service_overlay(
    canvas: Image.Image, slide: dict[str, Any],
) -> None:
    presentation = str(slide.get("presentation") or "")
    if presentation not in {"intro", "transition", "mid_story_cta", "outro"}:
        return
    draw = ImageDraw.Draw(canvas, "RGBA")
    draw.rectangle((0, 0, WIDTH, HEIGHT), fill=(0, 0, 0, 48))
    label = {
        "intro": "CHONKER TALKS",
        "transition": "СЛЕДУЮЩАЯ ИСТОРИЯ",
        "mid_story_cta": "ВАШЕ МНЕНИЕ",
        "outro": "ОБСУДИМ В КОММЕНТАРИЯХ",
    }[presentation]
    draw.text((72, 72), label, font=_font(34), fill=(255, 255, 255, 225))
    title = _clean_overlay_text(slide.get("story_title"), limit=160)
    source = _clean_overlay_text(slide.get("source_label"), limit=100)
    truth = _truth_label(slide.get("truth_mode"))
    if title:
        title_font = _font(54)
        title_lines = _wrapped_overlay_lines(
            draw,
            title,
            title_font,
            max_width=WIDTH - 144,
            max_lines=2,
        )
        title_text = "\n".join(title_lines)
        title_box = draw.multiline_textbbox(
            (0, 0), title_text, font=title_font, spacing=10,
        )
        title_y = 880 - title_box[3]
        draw.multiline_text(
            (72, title_y), title_text, font=title_font, spacing=10,
            fill=(255, 255, 255, 242),
        )
    if source:
        draw.text(
            (72, 900), source, font=_font(32),
            fill=(255, 255, 255, 224),
        )
    if truth:
        truth_box = draw.textbbox((0, 0), truth, font=_font(26))
        truth_width = truth_box[2] - truth_box[0]
        draw.rounded_rectangle(
            (72, 964, 104 + truth_width, 1020),
            radius=12,
            fill=(10, 10, 10, 190),
            outline=(255, 255, 255, 96),
            width=1,
        )
        draw.text(
            (88, 977), truth, font=_font(26),
            fill=(255, 255, 255, 228),
        )


def _render_service_overlay(slide: dict[str, Any], output: Path) -> None:
    """Write only the transparent service graphics used by FFmpeg."""

    canvas = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    _draw_service_overlay(canvas, slide)
    output.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output, format="PNG", optimize=False)


def render_cinematic_frame(
    slide: dict[str, Any],
    output: Path,
    *,
    progress: float = 0.0,
) -> None:
    """Render one representative full-screen frame for visual inspection/tests."""

    progress = min(1.0, max(0.0, float(progress)))
    motion = _motion(slide)
    scale = motion["start_scale"] + (
        motion["end_scale"] - motion["start_scale"]
    ) * progress
    center = [
        motion["start_center"][axis]
        + (motion["end_center"][axis] - motion["start_center"][axis]) * progress
        for axis in range(2)
    ]
    path = Path(str(slide.get("verified_image_path") or ""))
    if not path.is_file():
        raise CinematicRenderError("verified cinematic image is missing")
    with Image.open(path) as source:
        canvas = _cover_crop(source, scale=scale, center=center)
    _draw_service_overlay(canvas, slide)
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output, format="PNG", optimize=False)


def _probe_duration(ffprobe: str, path: Path) -> float:
    result = subprocess.run(
        [
            ffprobe, "-v", "error", "-show_entries", "format=duration",
            "-of", "default=nw=1:nk=1", str(path),
        ],
        check=True, capture_output=True, text=True,
    )
    duration = float(result.stdout.strip())
    if duration <= 0:
        raise CinematicRenderError("media duration must be positive")
    return duration


def _zoompan_filter(slide: dict[str, Any], frames: int) -> str:
    motion = slide["motion"]
    denominator = max(1, frames - 1)
    scale_delta = motion["end_scale"] - motion["start_scale"]
    x_delta = motion["end_center"][0] - motion["start_center"][0]
    y_delta = motion["end_center"][1] - motion["start_center"][1]
    return (
        f"scale={WIDTH * 11 // 10}:{HEIGHT * 11 // 10}:"
        "force_original_aspect_ratio=increase,"
        f"crop={WIDTH * 11 // 10}:{HEIGHT * 11 // 10},"
        f"zoompan=z='1+{scale_delta:.6f}*on/{denominator}':"
        f"x='(iw-iw/zoom)*({motion['start_center'][0]:.6f}+"
        f"{x_delta:.6f}*on/{denominator})':"
        f"y='(ih-ih/zoom)*({motion['start_center'][1]:.6f}+"
        f"{y_delta:.6f}*on/{denominator})':"
        f"d={frames}:s={WIDTH}x{HEIGHT}:fps={FPS},format=yuv420p"
    )


def render_cinematic_compilation(
    storyboard: dict[str, Any],
    artifact_root: Path,
    output: Path,
    *,
    audio: Path | None,
) -> dict[str, Any]:
    """Render the exact shot timeline without rescaling it to narration."""

    slides = preflight_cinematic_storyboard(storyboard, artifact_root)
    bindings = _storyboard_bindings(storyboard)
    ffmpeg, ffprobe = shutil.which("ffmpeg"), shutil.which("ffprobe")
    if not ffmpeg or not ffprobe:
        raise CinematicRenderError("ffmpeg and ffprobe are required")
    if audio is None:
        raise CinematicRenderError("cinematic storyboard requires bound narration audio")
    root = Path(artifact_root).resolve()
    audio = Path(audio).resolve()
    if audio == root or root not in audio.parents or not audio.is_file():
        raise CinematicRenderError("audio must be a file under artifact_root")
    audio_sha256 = _sha256(audio)
    if audio_sha256 != bindings["audio_sha256"]:
        raise CinematicRenderError("audio checksum does not match cinematic storyboard")
    audio_duration = _probe_duration(ffprobe, audio)
    expected_duration = float(storyboard["timeline_duration_sec"])
    if abs(audio_duration - expected_duration) > 0.05:
        raise CinematicRenderError(
            "audio duration does not match the exact cinematic timeline",
        )

    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="cinematic-render-") as temp:
        work = Path(temp)
        segment_paths: list[Path] = []
        service_overlay_evidence: list[dict[str, Any]] = []
        final_frame = math.ceil(expected_duration * FPS)
        for index, slide in enumerate(slides):
            start_frame = round(float(slide["start_sec"]) * FPS)
            end_frame = (
                final_frame
                if index == len(slides) - 1
                else round(float(slide["end_sec"]) * FPS)
            )
            frames = max(1, end_frame - start_frame)
            segment = work / f"shot-{index:04d}.mp4"
            render_input = Path(slide["verified_image_path"])
            presentation = str(slide.get("presentation") or "")
            overlay_input: Path | None = None
            if presentation in {"intro", "transition", "mid_story_cta", "outro"}:
                overlay_slide = _service_overlay_slide(slides, index)
                overlay_input = work / f"service-overlay-{index:04d}.png"
                _render_service_overlay(overlay_slide, overlay_input)
                service_overlay_evidence.append({
                    "shot_id": str(slide["shot_id"]),
                    "presentation": presentation,
                    "story_title": _clean_overlay_text(
                        overlay_slide.get("story_title"), limit=84,
                    ),
                    "source_label": _clean_overlay_text(
                        overlay_slide.get("source_label"), limit=100,
                    ),
                    "truth_mode": _clean_overlay_text(
                        overlay_slide.get("truth_mode"), limit=64,
                    ),
                    "truth_label": _truth_label(
                        overlay_slide.get("truth_mode"),
                    ),
                    "burned_in_overlay_sha256": _sha256(overlay_input),
                })
            command = [
                ffmpeg, "-y", "-v", "error", "-loop", "1", "-framerate", str(FPS),
                "-i", str(render_input),
            ]
            if overlay_input is None:
                command.extend(["-vf", _zoompan_filter(slide, frames)])
            else:
                command.extend([
                    "-loop", "1", "-framerate", str(FPS), "-i", str(overlay_input),
                    "-filter_complex",
                    (
                        f"[0:v]{_zoompan_filter(slide, frames)}[base];"
                        "[1:v]format=rgba[service];"
                        "[base][service]overlay=0:0:shortest=1,format=yuv420p[outv]"
                    ),
                    "-map", "[outv]",
                ])
            command.extend([
                "-frames:v", str(frames), "-an", "-c:v", "libx264",
                "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p",
                "-movflags", "+faststart", str(segment),
            ])
            subprocess.run(command, check=True)
            segment_paths.append(segment)
        concat = work / "shots.ffconcat"
        concat.write_text(
            "ffconcat version 1.0\n"
            + "\n".join(f"file '{path.name}'" for path in segment_paths)
            + "\n",
            encoding="utf-8",
        )
        silent_video = work / "silent.mp4"
        subprocess.run(
            [
                ffmpeg, "-y", "-v", "error", "-f", "concat", "-safe", "0",
                "-i", str(concat), "-c", "copy", str(silent_video),
            ],
            check=True,
        )
        subprocess.run(
            [
                ffmpeg, "-y", "-v", "error", "-i", str(silent_video), "-i", str(audio),
                "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy",
                "-c:a", "aac", "-b:a", "192k", "-t", f"{audio_duration:.6f}",
                "-movflags", "+faststart", str(output),
            ],
            check=True,
        )

    try:
        caption_path = write_caption_srt(
            storyboard["caption_track"], output.with_suffix(".srt"),
        )
    except CinematicShotError as exc:
        raise CinematicRenderError(str(exc)) from exc
    motion_evidence = [
        {
            "shot_id": slide["shot_id"],
            "visual_sha256": slide["visual_sha256"],
            "motion": slide["motion"],
        }
        for slide in slides
    ]
    creative = storyboard["creative_manifest"]
    return {
        "status": "ok",
        "output": str(output),
        "visual_mode": CINEMATIC_STORY_MODE,
        "resolution": [WIDTH, HEIGHT],
        "fps": FPS,
        "slide_count": len(slides),
        "shot_count": len(slides),
        "reddit_page_count": 0,
        "duration_sec": _probe_duration(ffprobe, output),
        "video_sha256": _sha256(output),
        "episode_plan_sha256": bindings["episode_plan_sha256"],
        "daily_plan_sha256": bindings["daily_plan_sha256"],
        "narration_plan_sha256": bindings["narration_plan_sha256"],
        "timing_contract_sha256": bindings["timing_contract_sha256"],
        "audio_sha256": audio_sha256,
        "pause_map_sha256": storyboard.get("pause_map_sha256"),
        "audio_mix_report_sha256": storyboard.get("audio_mix_report_sha256"),
        "narration_profile_id": storyboard.get("narration_profile_id"),
        "narration_profile_sha256": storyboard.get(
            "narration_profile_sha256",
        ),
        "audio_merged": True,
        "audio_duration_sec": audio_duration,
        "publication_authorized": False,
        "background_video_used": False,
        "fullscreen_images_verified": True,
        "story_shots_overlay_free": True,
        "service_overlay_count": len(service_overlay_evidence),
        "service_overlay_evidence_sha256": canonical_hash(
            service_overlay_evidence,
        ),
        "service_overlay_evidence": service_overlay_evidence,
        "shot_plan_sha256": storyboard["shot_plan_sha256"],
        "caption_track_sha256": storyboard["caption_track_sha256"],
        "caption_srt": str(caption_path),
        "caption_srt_sha256": _sha256(caption_path),
        "motion_evidence_sha256": canonical_hash(motion_evidence),
        "motion_evidence": motion_evidence,
        "story_shot_duration_min_sec": min(
            (
                slide["duration_sec"]
                for slide in slides
                if slide["presentation"] == "story"
            ),
            default=None,
        ),
        "story_shot_duration_max_sec": max(
            (
                slide["duration_sec"]
                for slide in slides
                if slide["presentation"] == "story"
            ),
            default=None,
        ),
        "text_timing_coverage": creative.get("text_timing_coverage", 0.0),
        "creative_manifest_sha256": canonical_hash(creative),
    }
