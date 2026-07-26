"""Deterministic, artifact-only 16:9 renderer for compilation storyboards.

The renderer deliberately accepts local files only.  It does not download media,
call providers, or reuse the browser-based Reddit-card renderer.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import tempfile
import textwrap
import re
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageEnhance, ImageFont, UnidentifiedImageError

from acc1_visual_contract import (
    CANVAS_FPS as FPS,
    CANVAS_HEIGHT as HEIGHT,
    CANVAS_WIDTH as WIDTH,
    CINEMATIC_STORY_MODE,
    DEFAULT_VISUAL_MODE,
    EDITORIAL_MOTION_MODE,
    MASCOT_SAFE_X,
    READABILITY_SHADE_ALPHA,
    STORY_VISUAL_BRIGHTNESS,
    STORY_VISUAL_FEATHER_END_X,
    STORY_VISUAL_FEATHER_START_X,
    TEXT_LEFT_X,
    TEXT_RIGHT_X,
    VISUAL_MODES,
    resolve_visual_mode,
)
from acc1_caption_burn import CaptionBurnError, burn_captions
from compilation_storyboard import (
    CompilationStoryboardError,
    compilation_text_layout_states,
)

DEFAULT_DURATIONS = {
    "title": 4.0,
    "story_title": 5.0,
    "source_image": 8.0,
    "outro": 5.0,
    "reddit_page": 5.0,
}
ALLOWED_IMAGE_FORMATS = {"JPEG", "PNG", "WEBP"}
ALLOWED_VIDEO_SUFFIXES = {".mp4", ".mov", ".m4v", ".webm"}
MAX_PIXELS = 40_000_000
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class CompilationRenderError(RuntimeError):
    pass


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _local_image(slide: dict[str, Any], artifact_root: Path) -> Path:
    visual = slide.get("visual")
    if not isinstance(visual, dict):
        raise CompilationRenderError("source_image slide has no visual object")
    raw = str(visual.get("local_path") or "")
    if not raw:
        raise CompilationRenderError("source_image slide has no local_path")
    root = artifact_root.resolve()
    candidate = Path(raw).expanduser()
    path = candidate.resolve() if candidate.is_absolute() else (root / candidate).resolve()
    if path == root or root not in path.parents or not path.is_file():
        raise CompilationRenderError("source image must be a file under artifact_root")
    expected = str(visual.get("sha256") or "").casefold()
    if len(expected) != 64 or any(char not in "0123456789abcdef" for char in expected):
        raise CompilationRenderError("source image requires a valid sha256")
    if _sha256(path) != expected:
        raise CompilationRenderError("source image checksum mismatch")
    try:
        with Image.open(path) as image:
            if image.format not in ALLOWED_IMAGE_FORMATS:
                raise CompilationRenderError(f"unsupported source image format: {image.format}")
            if image.width * image.height > MAX_PIXELS:
                raise CompilationRenderError("source image exceeds pixel limit")
            image.verify()
    except (UnidentifiedImageError, OSError) as exc:
        raise CompilationRenderError(f"source image decode failed: {exc}") from exc
    return path


def _local_background_video(storyboard: dict[str, Any], artifact_root: Path) -> Path | None:
    asset = storyboard.get("background_video")
    if asset in (None, ""):
        return None
    if not isinstance(asset, dict):
        raise CompilationRenderError("background_video must be an object")
    raw = str(asset.get("local_path") or "")
    root = artifact_root.resolve()
    candidate = Path(raw).expanduser()
    path = candidate.resolve() if candidate.is_absolute() else (root / candidate).resolve()
    if path == root or root not in path.parents or not path.is_file():
        raise CompilationRenderError("background video must be a file under artifact_root")
    if path.suffix.casefold() not in ALLOWED_VIDEO_SUFFIXES:
        raise CompilationRenderError("unsupported background video format")
    expected = str(asset.get("sha256") or "").casefold()
    if len(expected) != 64 or any(char not in "0123456789abcdef" for char in expected):
        raise CompilationRenderError("background video requires a valid sha256")
    if _sha256(path) != expected:
        raise CompilationRenderError("background video checksum mismatch")
    if asset.get("loop") is not True or asset.get("audio_policy") != "discard":
        raise CompilationRenderError("background video must explicitly loop with audio_policy=discard")
    return path


def _storyboard_bindings(storyboard: dict[str, Any]) -> dict[str, str]:
    if int(storyboard.get("version") or 1) < 2:
        return {}
    creative = storyboard.get("creative_manifest")
    if not isinstance(creative, dict):
        raise CompilationRenderError("version 2 storyboard requires creative_manifest")
    bindings: dict[str, str] = {}
    for field in (
        "episode_plan_sha256",
        "daily_plan_sha256",
        "audio_sha256",
        "narration_plan_sha256",
    ):
        digest = str(storyboard.get(field) or "").strip().lower()
        if not SHA256_RE.fullmatch(digest):
            raise CompilationRenderError(f"storyboard {field} must be a SHA-256 digest")
        if creative.get(field) != digest:
            raise CompilationRenderError(f"creative manifest {field} does not match storyboard")
        bindings[field] = digest
    if storyboard.get("publication_authorized") is not False:
        raise CompilationRenderError("storyboard cannot authorize publication")
    if creative.get("publication_authorized") is not False:
        raise CompilationRenderError("creative manifest cannot authorize publication")
    return bindings


def _storyboard_visual_mode(storyboard: dict[str, Any]) -> str:
    creative = storyboard.get("creative_manifest")
    creative_mode = (
        str(creative.get("mode") or "")
        if isinstance(creative, dict)
        else ""
    )
    raw_mode = storyboard.get("visual_mode")
    if raw_mode in (None, ""):
        if creative_mode in VISUAL_MODES:
            raw_mode = creative_mode
        elif creative_mode and int(storyboard.get("version") or 1) >= 2:
            raise CompilationRenderError(
                f"unsupported creative manifest mode: {creative_mode}",
            )
        else:
            raw_mode = DEFAULT_VISUAL_MODE
    try:
        mode = resolve_visual_mode(raw_mode)
    except ValueError as exc:
        raise CompilationRenderError(str(exc)) from exc
    if (
        creative_mode
        and int(storyboard.get("version") or 1) >= 2
        and creative_mode != mode
    ):
        raise CompilationRenderError(
            "storyboard visual_mode does not match creative manifest mode",
        )
    return mode


def _preflight_reddit_storyboard(
    storyboard: dict[str, Any], artifact_root: Path,
) -> list[dict[str, Any]]:
    if storyboard.get("format") != "compilation_16x9" or storyboard.get("resolution") != [WIDTH, HEIGHT]:
        raise CompilationRenderError("storyboard must be compilation_16x9 at 1920x1080")
    slides = storyboard.get("slides")
    if not isinstance(slides, list) or not slides:
        raise CompilationRenderError("storyboard has no slides")
    checked: list[dict[str, Any]] = []
    seen: set[str] = set()
    previous_end: float | None = None
    version = int(storyboard.get("version") or 1)
    _storyboard_bindings(storyboard)
    for index, source in enumerate(slides):
        if not isinstance(source, dict):
            raise CompilationRenderError(f"slide {index} is not an object")
        slide = dict(source)
        slide_id = str(slide.get("slide_id") or "")
        kind = str(slide.get("kind") or "")
        if not slide_id or slide_id in seen:
            raise CompilationRenderError("slide_id must be present and unique")
        if kind not in DEFAULT_DURATIONS:
            raise CompilationRenderError(f"unsupported slide kind: {kind or 'missing'}")
        seen.add(slide_id)
        try:
            duration = float(slide.get("duration_sec", DEFAULT_DURATIONS[kind]))
        except (TypeError, ValueError) as exc:
            raise CompilationRenderError(f"invalid duration for {slide_id}") from exc
        if not 0.5 <= duration <= 300:
            raise CompilationRenderError(f"duration for {slide_id} must be between 0.5 and 300 seconds")
        slide["duration_sec"] = duration
        if kind == "source_image":
            slide["verified_image_path"] = str(_local_image(slide, artifact_root))
        elif kind == "reddit_page":
            if slide.get("voice_role") not in {"narrator", "comment"}:
                raise CompilationRenderError(f"{slide_id} requires narrator/comment voice_role")
            narration = " ".join(str(slide.get("narration_text") or "").split())
            display = " ".join(str(slide.get("display_text") or "").split())
            if not narration or not display or narration not in display:
                raise CompilationRenderError(f"{slide_id} requires covered narration/display text")
            expected_hash = str(slide.get("text_sha256") or "")
            if hashlib.sha256(narration.encode("utf-8")).hexdigest() != expected_hash:
                raise CompilationRenderError(f"{slide_id} narration text checksum mismatch")
            visual = slide.get("visual")
            if visual is not None:
                slide["verified_image_path"] = str(_local_image(slide, artifact_root))
            if version >= 2:
                try:
                    start = float(slide["start_sec"])
                    end = float(slide["end_sec"])
                except (KeyError, TypeError, ValueError) as exc:
                    raise CompilationRenderError(f"{slide_id} requires numeric start_sec/end_sec") from exc
                if start < 0 or end <= start or abs((end - start) - duration) > 0.02:
                    raise CompilationRenderError(f"{slide_id} has inconsistent timing")
                if previous_end is None and abs(start) > 0.02:
                    raise CompilationRenderError(f"{slide_id} timeline must start at zero")
                if previous_end is not None and abs(start - previous_end) > 0.02:
                    raise CompilationRenderError(f"{slide_id} creates a timing gap or overlap")
                previous_end = end
        checked.append(slide)
    _local_background_video(storyboard, artifact_root)
    return checked


def preflight_storyboard(
    storyboard: dict[str, Any], artifact_root: Path,
) -> list[dict[str, Any]]:
    mode = _storyboard_visual_mode(storyboard)
    if mode == CINEMATIC_STORY_MODE:
        from compilation_cinematic_renderer import (
            CinematicRenderError,
            preflight_cinematic_storyboard,
        )

        try:
            return preflight_cinematic_storyboard(storyboard, artifact_root)
        except CinematicRenderError as exc:
            raise CompilationRenderError(str(exc)) from exc
    if mode == EDITORIAL_MOTION_MODE:
        from compilation_editorial_motion_renderer import (
            EditorialMotionRenderError,
            preflight_editorial_motion_storyboard,
        )

        try:
            return preflight_editorial_motion_storyboard(storyboard, artifact_root)
        except EditorialMotionRenderError as exc:
            raise CompilationRenderError(str(exc)) from exc
    return _preflight_reddit_storyboard(storyboard, artifact_root)


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        Path("/System/Library/Fonts/Supplemental/Arial Bold.ttf" if bold else "/System/Library/Fonts/Supplemental/Arial.ttf"),
        Path("/System/Library/Fonts/Supplemental/PTSerifCaption.ttc"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    ]
    for path in candidates:
        if path.is_file():
            return ImageFont.truetype(str(path), size=size)
    return ImageFont.load_default()


def _centered_text(draw: ImageDraw.ImageDraw, text: str, y: int, font: Any, fill: str, max_chars: int) -> None:
    lines = textwrap.wrap(" ".join(text.split()), width=max_chars)[:5] or [""]
    spacing = 18
    boxes = [draw.textbbox((0, 0), line, font=font) for line in lines]
    total = sum(box[3] - box[1] for box in boxes) + spacing * (len(lines) - 1)
    cursor = y - total // 2
    for line, box in zip(lines, boxes):
        width = box[2] - box[0]
        draw.text(((WIDTH - width) // 2, cursor), line, font=font, fill=fill)
        cursor += box[3] - box[1] + spacing


def _cover_image(source: Image.Image, size: tuple[int, int]) -> Image.Image:
    source = source.convert("RGB")
    scale = max(size[0] / source.width, size[1] / source.height)
    resized = source.resize(
        (max(1, round(source.width * scale)), max(1, round(source.height * scale))),
        Image.Resampling.LANCZOS,
    )
    left = max(0, (resized.width - size[0]) // 2)
    top = max(0, (resized.height - size[1]) // 2)
    return resized.crop((left, top, left + size[0], top + size[1]))


def _wrap_pixels(draw: ImageDraw.ImageDraw, text: str, font: Any, max_width: int) -> list[str]:
    words = " ".join(str(text or "").split()).split()
    lines: list[str] = []
    current = ""
    for word in words:
        if draw.textbbox((0, 0), word, font=font, stroke_width=2)[2] > max_width:
            raise CompilationRenderError("reddit page contains a word wider than the text column")
        candidate = f"{current} {word}".strip()
        if draw.textbbox((0, 0), candidate, font=font, stroke_width=2)[2] <= max_width:
            current = candidate
            continue
        if not current:
            raise CompilationRenderError("reddit page contains a word wider than the text column")
        lines.append(current)
        current = word
    if current:
        lines.append(current)
    return lines


def _fit_reddit_title(
    draw: ImageDraw.ImageDraw,
    title: str,
    font: Any,
    max_width: int,
    *,
    max_lines: int = 3,
) -> tuple[str, list[str], bool]:
    """Fit a visual title while preserving the full title in episode data."""
    normalized = " ".join(str(title or "История с Reddit").split()) or "История с Reddit"
    lines = _wrap_pixels(draw, normalized, font, max_width) or ["История с Reddit"]
    if len(lines) <= max_lines:
        return normalized, lines, False
    words = normalized.split()
    for kept in range(len(words) - 1, 1, -1):
        head_count = max(1, round(kept * 0.58))
        tail_count = max(1, kept - head_count)
        candidate = " ".join(words[:head_count] + ["…"] + words[-tail_count:])
        candidate_lines = _wrap_pixels(draw, candidate, font, max_width)
        if candidate_lines and len(candidate_lines) <= max_lines:
            return candidate, candidate_lines, True
    raise CompilationRenderError("reddit page title cannot fit even as an extractive display title")


def _reddit_page_text_layout(
    draw: ImageDraw.ImageDraw, slide: dict[str, Any],
) -> dict[str, Any]:
    """Measure the exact production text geometry without drawing a frame."""
    left, right = TEXT_LEFT_X, TEXT_RIGHT_X
    top = 84
    presentation = str(slide.get("presentation") or "story")
    if presentation != "story":
        cursor = top + 74
    else:
        subreddit = str(slide.get("subreddit") or "r/Reddit").strip()
        source_author = str(slide.get("source_author") or "").strip()
        source_line = subreddit + (f"  •  {source_author}" if source_author else "")
        source_font = _font(30, True)
        source_width = draw.textbbox(
            (0, 0), source_line, font=source_font, stroke_width=1,
        )[2]
        if source_width > right - left - 70:
            raise CompilationRenderError("reddit source line is wider than the text column")
        cursor = top + 90

    is_story_title_screen = slide.get("screen_mode") == "story_title"
    title_font = _font(46 if is_story_title_screen else 52, True)
    title_line_height = 58 if is_story_title_screen else 66
    max_title_lines = 5 if is_story_title_screen else 3
    title_lines: list[str] = []
    display_title = ""
    title_truncated = False
    title_start = cursor
    if slide.get("show_title"):
        title = " ".join(str(slide.get("title") or "История с Reddit").split())
        display_title, title_lines, title_truncated = _fit_reddit_title(
            draw, title, title_font, right - left,
        )
        cursor += 66 * len(title_lines) + 18
    else:
        cursor += 20

    body_font = _font(48)
    body_start = cursor
    body_lines = _wrap_pixels(
        draw, str(slide.get("display_text") or ""), body_font, right - left,
    )
    line_height = 65
    bottom_reserve = 145 if slide.get("show_actions") else 48
    available_lines = max(1, int((HEIGHT - bottom_reserve - cursor) / line_height))
    if len(body_lines) > available_lines:
        raise CompilationRenderError(
            f"reddit page text needs {len(body_lines)} lines but only {available_lines} fit"
        )
    body_end = body_start + line_height * len(body_lines)
    return {
        "title_font": title_font,
        "title_lines": title_lines,
        "display_title": display_title,
        "title_truncated": title_truncated,
        "title_start": title_start,
        "title_line_height": title_line_height,
        "body_font": body_font,
        "body_lines": body_lines,
        "body_start": body_start,
        "body_end": body_end,
        "line_height": line_height,
        "available_lines": available_lines,
        "actions_y": min(HEIGHT - 86, body_end + 20),
    }


def validate_compilation_text_layout(compilation: dict[str, Any]) -> dict[str, Any]:
    """Fail before packaging/images/TTS if any final Reddit page cannot fit."""
    try:
        states = compilation_text_layout_states(compilation)
    except CompilationStoryboardError as exc:
        raise CompilationRenderError(str(exc)) from exc
    if not states:
        raise CompilationRenderError("compilation text layout has no Reddit page states")
    probe = Image.new("L", (1, 1), 0)
    draw = ImageDraw.Draw(probe)
    page_keys: set[tuple[str, int]] = set()
    max_body_lines = 0
    title_truncated_state_count = 0
    measured_states: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for state in states:
        layout = _reddit_page_text_layout(draw, state)
        max_body_lines = max(max_body_lines, len(layout["body_lines"]))
        title_truncated_state_count += int(layout["title_truncated"])
        page_keys.add((str(state.get("segment_id") or ""), int(state.get("page_index") or 0)))
        measured_states.append((state, layout))
    state_payload = [{
        "slide_id": state["slide_id"],
        "segment_id": state["segment_id"],
        "page_index": state["page_index"],
        "page_step": state["page_step"],
        "show_title": state["show_title"],
        "show_actions": state["show_actions"],
        "title": state["title"],
        "display_title": layout["display_title"],
        "title_truncated": layout["title_truncated"],
        "display_text": state["display_text"],
        "narration_text": state["narration_text"],
    } for state, layout in measured_states]
    encoded = json.dumps(
        state_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")
    return {
        "version": 1,
        "status": "PASS",
        "layout": "reddit_pages_1920x1080",
        "text_column": [TEXT_LEFT_X, TEXT_RIGHT_X],
        "title_font_px": 52,
        "body_font_px": 48,
        "body_line_height_px": 65,
        "state_count": len(states),
        "page_count": len(page_keys),
        "maximum_body_lines_observed": max_body_lines,
        "title_truncated_state_count": title_truncated_state_count,
        "page_states_sha256": hashlib.sha256(encoded).hexdigest(),
        "publication_authorized": False,
    }


def _compact_metric(value: Any, fallback: str) -> str:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        return fallback
    if value >= 1_000_000:
        return f"{value / 1_000_000:.1f}".rstrip("0").rstrip(".") + "M"
    if value >= 1_000:
        return f"{value / 1_000:.1f}".rstrip("0").rstrip(".") + "K"
    return str(value)


def _draw_vote_arrow(draw: ImageDraw.ImageDraw, cx: int, cy: int, *, down: bool = False) -> None:
    """Draw the compact hollow vote arrow used by current Reddit cards."""
    color = "#f4f6f7"
    points = [
        (cx, cy - 15), (cx - 13, cy - 1), (cx - 6, cy - 1),
        (cx - 6, cy + 12), (cx + 6, cy + 12), (cx + 6, cy - 1),
        (cx + 13, cy - 1),
    ]
    if down:
        points = [(px, 2 * cy - py) for px, py in points]
    draw.line(points + [points[0]], fill=color, width=3, joint="curve")


def _draw_comment_icon(draw: ImageDraw.ImageDraw, cx: int, cy: int) -> None:
    color = "#f4f6f7"
    draw.ellipse((cx - 14, cy - 13, cx + 14, cy + 12), outline=color, width=3)
    draw.line((cx - 8, cy + 9, cx - 12, cy + 17, cx - 1, cy + 12), fill=color, width=3, joint="curve")


def _draw_share_icon(draw: ImageDraw.ImageDraw, cx: int, cy: int) -> None:
    color = "#f4f6f7"
    # Compact forward-arrow silhouette used by Reddit's share pill.
    draw.polygon(
        [
            (cx - 16, cy + 14), (cx - 13, cy + 4), (cx - 8, cy - 2),
            (cx - 2, cy - 6), (cx + 5, cy - 7), (cx + 5, cy - 14),
            (cx + 16, cy - 4), (cx + 5, cy + 6), (cx + 5, cy),
            (cx, cy), (cx - 6, cy + 4), (cx - 11, cy + 9),
        ],
        fill=color,
    )


def _draw_reddit_actions(draw: ImageDraw.ImageDraw, x: int, y: int, slide: dict[str, Any]) -> None:
    """Draw current-Reddit-style separate action pills with source-backed metrics."""
    outline = "#f4f6f7"
    color = "#f4f6f7"
    font = _font(28, True)
    height = 64
    radius = height // 2

    vote_w = 194
    draw.rounded_rectangle((x, y, x + vote_w, y + height), radius=radius, outline=outline, width=3)
    _draw_vote_arrow(draw, x + 28, y + 32)
    vote_text = _compact_metric(slide.get("source_score"), "Vote")
    vote_box = draw.textbbox((0, 0), vote_text, font=font)
    vote_text_w = vote_box[2] - vote_box[0]
    draw.text((x + (vote_w - vote_text_w) // 2, y + 13), vote_text, font=font, fill=color)
    _draw_vote_arrow(draw, x + vote_w - 28, y + 32, down=True)

    gap = 12
    comment_x = x + vote_w + gap
    comment_w = 190
    draw.rounded_rectangle((comment_x, y, comment_x + comment_w, y + height), radius=radius, outline=outline, width=3)
    _draw_comment_icon(draw, comment_x + 31, y + 30)
    comment_text = _compact_metric(slide.get("source_comment_count"), "Comments")
    draw.text((comment_x + 57, y + 13), comment_text, font=font, fill=color)

    # Reddit only shows a reaction/award pill when the source post has a real
    # reaction. The current snapshot contract has no award field, so do not
    # fabricate a badge or count merely to fill the row.
    share_x = comment_x + comment_w + gap
    share_w = 164
    draw.rounded_rectangle((share_x, y, share_x + share_w, y + height), radius=radius, outline=outline, width=3)
    _draw_share_icon(draw, share_x + 31, y + 29)
    draw.text((share_x + 57, y + 13), "Share", font=font, fill=color)


def _reddit_page_frame(slide: dict[str, Any], *, transparent: bool) -> Image.Image:
    # The compact audio intro is source-bound but is not printed as faux Reddit
    # text.  The first screen is instead the real post title and source header.
    if slide.get("screen_mode") == "story_title":
        slide = {
            **slide,
            "presentation": "story",
            "title": str(slide.get("screen_title") or slide.get("title") or "История с Reddit"),
            "display_text": "",
            "show_title": True,
            "show_actions": False,
        }
    canvas = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0) if transparent else (8, 11, 18, 255))
    visual_path = slide.get("verified_image_path")
    if visual_path:
        with Image.open(visual_path) as source:
            visual = _cover_image(source, (MASCOT_SAFE_X, HEIGHT)).convert("RGBA")
        visual = ImageEnhance.Brightness(visual).enhance(STORY_VISUAL_BRIGHTNESS)
        feather = Image.new("L", (MASCOT_SAFE_X, HEIGHT), 255)
        feather_draw = ImageDraw.Draw(feather)
        feather_span = STORY_VISUAL_FEATHER_END_X - STORY_VISUAL_FEATHER_START_X
        for x in range(STORY_VISUAL_FEATHER_START_X, STORY_VISUAL_FEATHER_END_X):
            alpha = round(255 * (1 - (x - STORY_VISUAL_FEATHER_START_X) / feather_span))
            feather_draw.line((x, 0, x, HEIGHT), fill=max(0, alpha))
        canvas.alpha_composite(Image.composite(visual, Image.new("RGBA", visual.size), feather), (0, 0))

    # A fixed left-side readability gradient keeps the animated character on the
    # right visible while avoiding a floating rectangular card.
    shade = Image.new("RGBA", (MASCOT_SAFE_X, HEIGHT), (0, 0, 0, 0))
    shade_draw = ImageDraw.Draw(shade)
    for x in range(shade.width):
        if x <= STORY_VISUAL_FEATHER_START_X:
            alpha = READABILITY_SHADE_ALPHA
        else:
            alpha = max(0, round(
                READABILITY_SHADE_ALPHA * (1 - (x - STORY_VISUAL_FEATHER_START_X) /
                                           (MASCOT_SAFE_X - STORY_VISUAL_FEATHER_START_X))
            ))
        shade_draw.line((x, 0, x, HEIGHT), fill=(4, 7, 12, alpha))
    canvas.alpha_composite(shade, (0, 0))

    draw = ImageDraw.Draw(canvas)
    left, right = TEXT_LEFT_X, TEXT_RIGHT_X
    top = 84
    presentation = str(slide.get("presentation") or "story")
    if presentation != "story":
        eyebrow = {
            "intro": "CHONKER TALKS  •  REDDIT STORIES",
            "transition": "NEXT STORY",
            "outro": "CHONKER TALKS",
        }.get(presentation, "CHONKER TALKS")
        draw.text((left, top), eyebrow, font=_font(28, True), fill="#ff4500")
        cursor = top + 74
    else:
        avatar_color = "#ff4500"
        draw.ellipse((left, top, left + 52, top + 52), fill=avatar_color)
        subreddit = str(slide.get("subreddit") or "r/Reddit").strip()
        source_author = str(slide.get("source_author") or "").strip()
        source_line = subreddit + (f"  •  {source_author}" if source_author else "")
        draw.text((left + 70, top + 7), source_line, font=_font(30, True), fill="#d7dadc", stroke_width=1, stroke_fill="#101216")
        cursor = top + 90
    layout = _reddit_page_text_layout(draw, slide)
    cursor = int(layout["title_start"])
    for line in layout["title_lines"]:
        draw.text((left, cursor), line, font=layout["title_font"], fill="#ffffff", stroke_width=1, stroke_fill="#080b12")
        cursor += int(layout["title_line_height"])
    cursor = int(layout["body_start"])
    for line in layout["body_lines"]:
        draw.text((left, cursor), line, font=layout["body_font"], fill="#e6e9eb", stroke_width=1, stroke_fill="#080b12")
        cursor += int(layout["line_height"])

    if slide.get("show_actions"):
        _draw_reddit_actions(draw, left, int(layout["actions_y"]), slide)
    return canvas


def render_slide_frame(slide: dict[str, Any], output: Path, *, transparent: bool = False) -> None:
    if slide["kind"] == "cinematic_shot":
        if transparent:
            raise CompilationRenderError(
                "cinematic full-screen frames cannot be transparent",
            )
        from compilation_cinematic_renderer import (
            CinematicRenderError,
            render_cinematic_frame,
        )

        try:
            render_cinematic_frame(slide, output)
        except CinematicRenderError as exc:
            raise CompilationRenderError(str(exc)) from exc
        return
    if slide["kind"] == "reddit_page":
        canvas = _reddit_page_frame(slide, transparent=transparent)
        output.parent.mkdir(parents=True, exist_ok=True)
        canvas.save(output, format="PNG", optimize=False)
        return

    canvas = Image.new("RGBA" if transparent else "RGB", (WIDTH, HEIGHT), (0, 0, 0, 0) if transparent else "#080b12")
    draw = ImageDraw.Draw(canvas)
    kind = slide["kind"]
    if kind == "source_image":
        with Image.open(slide["verified_image_path"]) as source:
            source = source.convert("RGB")
            source.thumbnail((WIDTH - 180, HEIGHT - 180), Image.Resampling.LANCZOS)
            x, y = (WIDTH - source.width) // 2, (HEIGHT - source.height) // 2
            canvas.paste(source, (x, y))
        caption = str((slide.get("visual") or {}).get("caption") or "").strip()
        if caption:
            draw.rounded_rectangle((100, HEIGHT - 150, WIDTH - 100, HEIGHT - 55), 18, fill=(0, 0, 0, 190))
            _centered_text(draw, caption, HEIGHT - 103, _font(30), "#f0f2f5", 90)
    else:
        draw.rectangle((0, 0, 18, HEIGHT), fill="#c6253d")
        label = "СТРАШНЫЕ ИСТОРИИ С REDDIT" if kind == "title" else f"ИСТОРИЯ {slide.get('story_index', '')}".strip()
        if kind == "outro":
            label = "СПАСИБО ЗА ПРОСЛУШИВАНИЕ"
        _centered_text(draw, label, 250, _font(32, True), "#c6253d", 70)
        text = str(slide.get("title") or slide.get("text") or "Страшные истории с Reddit")
        _centered_text(draw, text, 555, _font(66, True), "#f5f5f5", 40)
    output.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output, format="PNG", optimize=False)


def _probe_duration(ffprobe: str, path: Path) -> float:
    result = subprocess.run(
        [ffprobe, "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(path)],
        check=True, capture_output=True, text=True,
    )
    value = float(result.stdout.strip())
    if value <= 0:
        raise CompilationRenderError("audio duration must be positive")
    return value


def _render_reddit_compilation(
    storyboard: dict[str, Any],
    artifact_root: Path,
    output: Path,
    *,
    audio: Path | None = None,
) -> dict[str, Any]:
    slides = _preflight_reddit_storyboard(storyboard, artifact_root)
    bindings = _storyboard_bindings(storyboard)
    ffmpeg, ffprobe = shutil.which("ffmpeg"), shutil.which("ffprobe")
    if not ffmpeg or not ffprobe:
        raise CompilationRenderError("ffmpeg and ffprobe are required")
    background_video = _local_background_video(storyboard, artifact_root)
    if background_video is not None:
        probe = subprocess.run(
            [ffprobe, "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=codec_type", "-of", "default=nw=1:nk=1", str(background_video)],
            check=True, capture_output=True, text=True,
        )
        if probe.stdout.strip() != "video":
            raise CompilationRenderError("background video has no decodable video stream")
    audio_duration = None
    audio_sha256 = None
    if bindings and audio is None:
        raise CompilationRenderError("version 2 storyboard requires bound narration audio")
    if audio is not None:
        audio = audio.resolve()
        root = Path(artifact_root).resolve()
        if audio == root or root not in audio.parents or not audio.is_file():
            raise CompilationRenderError("audio must be a file under artifact_root")
        audio_sha256 = _sha256(audio)
        if bindings and audio_sha256 != bindings["audio_sha256"]:
            raise CompilationRenderError("audio checksum does not match storyboard")
        audio_duration = _probe_duration(ffprobe, audio)
        scale = audio_duration / sum(slide["duration_sec"] for slide in slides)
        for slide in slides:
            slide["duration_sec"] *= scale
    cursor = 0.0
    for slide in slides:
        slide["render_start_sec"] = cursor
        cursor += slide["duration_sec"]
        slide["render_end_sec"] = cursor
    target_duration = audio_duration or cursor
    with tempfile.TemporaryDirectory(prefix="compilation-render-") as temp:
        work = Path(temp)
        frames: list[Path] = []
        for index, slide in enumerate(slides):
            frame = work / f"slide-{index:04d}.png"
            render_slide_frame(slide, frame, transparent=background_video is not None)
            frames.append(frame)
        concat = work / "slides.ffconcat"
        lines = ["ffconcat version 1.0"]
        for frame, slide in zip(frames, slides):
            lines.extend([f"file '{frame.name}'", f"duration {slide['duration_sec']:.6f}"])
        lines.append(f"file '{frames[-1].name}'")
        concat.write_text("\n".join(lines) + "\n", encoding="utf-8")
        output.parent.mkdir(parents=True, exist_ok=True)
        if background_video is not None:
            command = [
                ffmpeg, "-y", "-v", "error", "-stream_loop", "-1", "-i", str(background_video),
                "-f", "concat", "-safe", "0", "-i", str(concat),
            ]
            audio_index = 2
            if audio:
                command += ["-i", str(audio)]
            command += [
                "-filter_complex",
                f"[0:v]scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=increase,crop={WIDTH}:{HEIGHT},fps={FPS}[bg];"
                "[1:v]format=rgba[pages];[bg][pages]overlay=0:0:shortest=1,format=yuv420p[v]",
                "-map", "[v]",
            ]
            if audio:
                command += ["-map", f"{audio_index}:a:0"]
        else:
            command = [ffmpeg, "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(concat)]
            if audio:
                command += ["-i", str(audio), "-map", "0:v:0", "-map", "1:a:0"]
        command += ["-t", f"{target_duration:.6f}", "-r", str(FPS), "-c:v", "libx264", "-pix_fmt", "yuv420p"]
        if audio:
            command += ["-c:a", "aac", "-b:a", "192k"]
        command += ["-movflags", "+faststart", str(output)]
        subprocess.run(command, check=True)
    duration = _probe_duration(ffprobe, output)
    creative_manifest = storyboard.get("creative_manifest") if isinstance(storyboard.get("creative_manifest"), dict) else {}
    creative_hash = hashlib.sha256(
        json.dumps(creative_manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest() if creative_manifest else None
    return {
        "status": "ok",
        "output": str(output),
        "visual_mode": DEFAULT_VISUAL_MODE,
        "resolution": [WIDTH, HEIGHT],
        "fps": FPS,
        "slide_count": len(slides),
        "reddit_page_count": sum(slide["kind"] == "reddit_page" for slide in slides),
        "duration_sec": duration,
        "video_sha256": _sha256(output),
        "episode_plan_sha256": bindings.get("episode_plan_sha256"),
        "daily_plan_sha256": bindings.get("daily_plan_sha256"),
        "narration_plan_sha256": bindings.get("narration_plan_sha256"),
        "timing_contract_sha256": storyboard.get("timing_contract_sha256"),
        "audio_sha256": audio_sha256,
        "pause_map_sha256": storyboard.get("pause_map_sha256"),
        "audio_mix_report_sha256": storyboard.get("audio_mix_report_sha256"),
        "narration_profile_id": storyboard.get("narration_profile_id"),
        "narration_profile_sha256": storyboard.get(
            "narration_profile_sha256",
        ),
        "publication_authorized": False,
        "audio_merged": audio is not None,
        "audio_duration_sec": audio_duration,
        "background_video_used": background_video is not None,
        "background_video_sha256": _sha256(background_video) if background_video else None,
        "background_audio_discarded": background_video is not None,
        "mascot_safe_x": MASCOT_SAFE_X,
        "max_slide_duration_sec": max((slide["duration_sec"] for slide in slides), default=0),
        "slide_timing_coverage": round(sum(slide["duration_sec"] for slide in slides if slide.get("narration_text")) / cursor, 6) if cursor else 0.0,
        "text_timing_coverage": creative_manifest.get("text_timing_coverage", 0.0),
        "creative_manifest_sha256": creative_hash,
    }


def render_compilation(
    storyboard: dict[str, Any],
    artifact_root: Path,
    output: Path,
    *,
    audio: Path | None = None,
) -> dict[str, Any]:
    brand_overlay_fields = ("brand_sting", "brand_cta", "brand_outro")
    brand_overlays = [
        (field, storyboard[field])
        for field in brand_overlay_fields
        if isinstance(storyboard.get(field), dict)
    ]
    render_output = output
    temp_dir: tempfile.TemporaryDirectory[str] | None = None
    if brand_overlays:
        artifact_temp_root = Path(artifact_root).resolve()
        artifact_temp_root.mkdir(parents=True, exist_ok=True)
        temp_dir = tempfile.TemporaryDirectory(
            prefix="compilation-brand-overlay-",
            dir=artifact_temp_root,
        )
        render_output = Path(temp_dir.name) / "base.mp4"
    mode = _storyboard_visual_mode(storyboard)
    if mode == CINEMATIC_STORY_MODE:
        from compilation_cinematic_renderer import (
            CinematicRenderError,
            render_cinematic_compilation,
        )

        try:
            report = render_cinematic_compilation(
                storyboard,
                artifact_root,
                render_output,
                audio=audio,
            )
        except CinematicRenderError as exc:
            raise CompilationRenderError(str(exc)) from exc
    elif mode == EDITORIAL_MOTION_MODE:
        from compilation_editorial_motion_renderer import (
            EditorialMotionRenderError,
            render_editorial_motion_compilation,
        )

        try:
            report = render_editorial_motion_compilation(
                storyboard,
                artifact_root,
                render_output,
                audio=audio,
            )
        except EditorialMotionRenderError as exc:
            raise CompilationRenderError(str(exc)) from exc
    else:
        report = _render_reddit_compilation(
            storyboard,
            artifact_root,
            render_output,
            audio=audio,
        )
    if not brand_overlays:
        return report
    try:
        root = Path(artifact_root).resolve()
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            raise CompilationRenderError(
                "ffmpeg is required for brand overlay compositing",
            )
        output = Path(output).resolve()
        if output == root or root not in output.parents:
            raise CompilationRenderError(
                "brand-composited output must remain under artifact_root",
            )
        output.parent.mkdir(parents=True, exist_ok=True)
        command = [ffmpeg, "-y", "-v", "error", "-i", str(render_output)]
        resolved: list[tuple[str, Path, str, float, float]] = []
        for field, contract in brand_overlays:
            raw_path = str(contract.get("local_path") or "")
            asset_path = (root / raw_path).resolve()
            if (
                asset_path == root
                or root not in asset_path.parents
                or not asset_path.is_file()
            ):
                raise CompilationRenderError(
                    f"{field} must be a local artifact file",
                )
            expected = str(contract.get("sha256") or "").strip().lower()
            if (
                not SHA256_RE.fullmatch(expected)
                or _sha256(asset_path) != expected
            ):
                raise CompilationRenderError(f"{field} checksum mismatch")
            start = float(contract.get("start_sec") or 0)
            duration = float(contract.get("duration_sec") or 0)
            if start < 0 or not 0.5 <= duration <= 15.0:
                raise CompilationRenderError(f"{field} timing is invalid")
            if contract.get("audio_policy") != "discard":
                raise CompilationRenderError(
                    f"{field} must discard asset audio",
                )
            if field == "brand_cta":
                if asset_path.suffix.casefold() != ".webm":
                    raise CompilationRenderError(
                        "brand_cta must be a transparent WebM",
                    )
                command += ["-c:v", "libvpx-vp9"]
            command += ["-i", str(asset_path)]
            resolved.append((field, asset_path, expected, start, duration))

        filters: list[str] = []
        previous = "0:v"
        for index, (
            _field,
            _path,
            _expected,
            start,
            duration,
        ) in enumerate(resolved, start=1):
            asset_label = f"brand{index}"
            output_label = "v" if index == len(resolved) else f"base{index}"
            end = start + duration
            filters.append(
                f"[{index}:v]scale={WIDTH}:{HEIGHT}:"
                "force_original_aspect_ratio=increase,"
                f"crop={WIDTH}:{HEIGHT},fps={FPS},format=rgba,"
                f"trim=duration={duration:.6f},"
                f"setpts=PTS-STARTPTS+{start:.6f}/TB[{asset_label}]",
            )
            filters.append(
                f"[{previous}][{asset_label}]overlay=0:0:"
                f"enable='between(t,{start:.6f},{end:.6f})':"
                f"eof_action=pass[{output_label}]",
            )
            previous = output_label

        composite_output = Path(temp_dir.name) / "branded.mp4"
        command += [
            "-filter_complex",
            ";".join(filters),
            "-map",
            "[v]",
            "-map",
            "0:a?",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-r",
            str(FPS),
            "-c:a",
            "copy",
            "-movflags",
            "+faststart",
            str(composite_output),
        ]
        subprocess.run(command, check=True)

        caption_ass_raw = str(report.get("caption_ass") or "").strip()
        captions_reburned = False
        if caption_ass_raw:
            caption_ass = Path(caption_ass_raw)
            caption_ass = (
                caption_ass.resolve()
                if caption_ass.is_absolute()
                else (root / caption_ass).resolve()
            )
            if (
                caption_ass == root
                or root not in caption_ass.parents
                or not caption_ass.is_file()
            ):
                raise CompilationRenderError(
                    "brand overlay caption ASS is missing or outside artifact root",
                )
            try:
                burn_captions(composite_output, caption_ass, output)
            except CaptionBurnError as exc:
                raise CompilationRenderError(str(exc)) from exc
            captions_reburned = True
        else:
            shutil.move(str(composite_output), str(output))

        caption_source_raw = str(report.get("caption_srt") or "").strip()
        if caption_source_raw:
            caption_source = Path(caption_source_raw)
            if caption_source.is_file():
                caption_output = output.with_suffix(".srt")
                if caption_source.resolve() != caption_output.resolve():
                    shutil.copy2(caption_source, caption_output)
                report["caption_srt"] = str(caption_output)
                report["caption_srt_sha256"] = _sha256(caption_output)
        report.update({
            "output": str(output),
            "video_sha256": _sha256(output),
            "duration_sec": _probe_duration(
                shutil.which("ffprobe") or "ffprobe",
                output,
            ),
            "captions_reburned_after_brand_overlays": captions_reburned,
        })
        for field, _path, expected, start, duration in resolved:
            report.update({
                f"{field}_used": True,
                f"{field}_sha256": expected,
                f"{field}_start_sec": round(start, 3),
                f"{field}_duration_sec": round(duration, 3),
                f"{field}_audio_discarded": True,
            })
            if field == "brand_cta":
                report["brand_cta_alpha_decoder"] = "libvpx-vp9"
        return report
    finally:
        if temp_dir is not None:
            temp_dir.cleanup()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Render an artifact-only acc1 compilation MP4")
    parser.add_argument("--storyboard", required=True)
    parser.add_argument("--artifact-root", required=True)
    parser.add_argument("--output", default="compilation.mp4")
    parser.add_argument("--audio")
    parser.add_argument("--report")
    parser.add_argument("--preflight-only", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        storyboard = json.loads(Path(args.storyboard).read_text(encoding="utf-8"))
        slides = preflight_storyboard(storyboard, Path(args.artifact_root))
        bindings = _storyboard_bindings(storyboard)
        visual_mode = _storyboard_visual_mode(storyboard)
        report = ({
            "status": "preflight_ok",
            "visual_mode": visual_mode,
            "slide_count": len(slides),
            **bindings,
            "publication_authorized": False,
        } if args.preflight_only else render_compilation(
            storyboard,
            Path(args.artifact_root),
            Path(args.output),
            audio=Path(args.audio) if args.audio else None,
        ))
        if args.report:
            Path(args.report).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False))
        return 0
    except (OSError, ValueError, json.JSONDecodeError, subprocess.CalledProcessError, CompilationRenderError) as exc:
        print(f"compilation render failed: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
