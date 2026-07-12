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
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont, UnidentifiedImageError


WIDTH, HEIGHT, FPS = 1920, 1080, 30
DEFAULT_DURATIONS = {"title": 4.0, "story_title": 5.0, "source_image": 8.0, "outro": 5.0}
ALLOWED_IMAGE_FORMATS = {"JPEG", "PNG", "WEBP"}
MAX_PIXELS = 40_000_000


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
    path = Path(raw).resolve()
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


def preflight_storyboard(storyboard: dict[str, Any], artifact_root: Path) -> list[dict[str, Any]]:
    if storyboard.get("format") != "compilation_16x9" or storyboard.get("resolution") != [WIDTH, HEIGHT]:
        raise CompilationRenderError("storyboard must be compilation_16x9 at 1920x1080")
    slides = storyboard.get("slides")
    if not isinstance(slides, list) or not slides:
        raise CompilationRenderError("storyboard has no slides")
    checked: list[dict[str, Any]] = []
    seen: set[str] = set()
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
        checked.append(slide)
    return checked


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


def render_slide_frame(slide: dict[str, Any], output: Path) -> None:
    canvas = Image.new("RGB", (WIDTH, HEIGHT), "#080b12")
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


def render_compilation(storyboard: dict[str, Any], artifact_root: Path, output: Path, *, audio: Path | None = None) -> dict[str, Any]:
    slides = preflight_storyboard(storyboard, artifact_root)
    ffmpeg, ffprobe = shutil.which("ffmpeg"), shutil.which("ffprobe")
    if not ffmpeg or not ffprobe:
        raise CompilationRenderError("ffmpeg and ffprobe are required")
    audio_duration = None
    if audio is not None:
        audio = audio.resolve()
        if not audio.is_file():
            raise CompilationRenderError("audio file does not exist")
        audio_duration = _probe_duration(ffprobe, audio)
        scale = audio_duration / sum(slide["duration_sec"] for slide in slides)
        for slide in slides:
            slide["duration_sec"] *= scale
    with tempfile.TemporaryDirectory(prefix="compilation-render-") as temp:
        work = Path(temp)
        frames: list[Path] = []
        for index, slide in enumerate(slides):
            frame = work / f"slide-{index:04d}.png"
            render_slide_frame(slide, frame)
            frames.append(frame)
        concat = work / "slides.ffconcat"
        lines = ["ffconcat version 1.0"]
        for frame, slide in zip(frames, slides):
            lines.extend([f"file '{frame.name}'", f"duration {slide['duration_sec']:.6f}"])
        lines.append(f"file '{frames[-1].name}'")
        concat.write_text("\n".join(lines) + "\n", encoding="utf-8")
        output.parent.mkdir(parents=True, exist_ok=True)
        command = [ffmpeg, "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(concat)]
        if audio:
            command += ["-i", str(audio), "-map", "0:v:0", "-map", "1:a:0", "-shortest"]
        command += ["-r", str(FPS), "-c:v", "libx264", "-pix_fmt", "yuv420p"]
        if audio:
            command += ["-c:a", "aac", "-b:a", "192k"]
        command += ["-movflags", "+faststart", str(output)]
        subprocess.run(command, check=True)
    duration = _probe_duration(ffprobe, output)
    return {"status": "ok", "output": str(output), "resolution": [WIDTH, HEIGHT], "fps": FPS, "slide_count": len(slides), "duration_sec": duration, "audio_merged": audio is not None, "audio_duration_sec": audio_duration}


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
        report = {"status": "preflight_ok", "slide_count": len(slides)} if args.preflight_only else render_compilation(storyboard, Path(args.artifact_root), Path(args.output), audio=Path(args.audio) if args.audio else None)
        if args.report:
            Path(args.report).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False))
        return 0
    except (OSError, ValueError, json.JSONDecodeError, subprocess.CalledProcessError, CompilationRenderError) as exc:
        print(f"compilation render failed: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
