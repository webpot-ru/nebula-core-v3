"""Generate or locally compose a deterministic 1280x720 YouTube thumbnail.

Provider generation remains explicitly spend-gated.  ``--base-image`` is a
fully local path: it never calls VectorEngine and is suitable for CI fixtures or
for applying approved Cyrillic packaging to an existing image.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import textwrap
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont, UnidentifiedImageError

from vectorengine_client import (
    DEFAULT_IMAGE_MODEL,
    VectorEngineError,
    call_image_generation,
    get_api_key,
    load_dotenv_file,
)


THUMBNAIL_SIZE = (1280, 720)
MAX_OVERLAY_CHARACTERS = 48
FONT_CANDIDATES = (
    Path("/System/Library/Fonts/Supplemental/Arial Black.ttf"),
    Path("/System/Library/Fonts/Supplemental/Arial Bold.ttf"),
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
    Path("/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf"),
)


def _load_metadata(metadata_path: Path) -> dict[str, Any]:
    with metadata_path.open("r", encoding="utf-8") as handle:
        metadata = json.load(handle)
    if not isinstance(metadata, dict):
        raise VectorEngineError(f"{metadata_path} must contain a JSON object.")
    return metadata


def _selected_thumbnail_text(metadata: dict[str, Any]) -> str:
    direct = str(metadata.get("thumbnail_text") or "").strip()
    if direct:
        return direct
    options = metadata.get("packaging_options") or []
    try:
        selected = int(metadata.get("selected_option_index", 0))
    except (TypeError, ValueError):
        selected = 0
    if isinstance(options, list) and 0 <= selected < len(options) and isinstance(options[selected], dict):
        return str(options[selected].get("thumbnail_text") or "").strip()
    return ""


def load_prompt(metadata_path: Path) -> str:
    metadata = _load_metadata(metadata_path)
    prompt = str(metadata.get("thumbnail_prompt") or "").strip()
    text = _selected_thumbnail_text(metadata)
    if not prompt:
        raise VectorEngineError(f"{metadata_path} has no thumbnail_prompt.")
    if text:
        prompt = (
            f"{prompt}\n\nLeave strong clean negative space on the left for a deterministic text overlay: {text}. "
            "Do not render any letters, words, logos, watermarks, or pseudo-text."
        )
    return prompt


def _font_path(explicit: str | None = None) -> Path:
    candidates = (Path(explicit).expanduser(),) if explicit else FONT_CANDIDATES
    for path in candidates:
        if path.is_file():
            return path
    raise VectorEngineError("No Cyrillic-capable TrueType font is available for thumbnail overlay.")


def _cover(source: Image.Image, size: tuple[int, int]) -> Image.Image:
    source = source.convert("RGB")
    scale = max(size[0] / source.width, size[1] / source.height)
    resized = source.resize(
        (max(1, round(source.width * scale)), max(1, round(source.height * scale))),
        Image.Resampling.LANCZOS,
    )
    left = max(0, (resized.width - size[0]) // 2)
    top = max(0, (resized.height - size[1]) // 2)
    return resized.crop((left, top, left + size[0], top + size[1]))


def _wrap_text(text: str, *, width: int) -> list[str]:
    explicit = [" ".join(line.split()) for line in text.splitlines() if line.strip()]
    if len(explicit) > 2:
        raise VectorEngineError("thumbnail text must fit at most two lines")
    if len(explicit) == 2:
        return explicit
    value = explicit[0] if explicit else " ".join(text.split())
    words = value.split()
    if not words:
        raise VectorEngineError("thumbnail text is required for deterministic overlay")
    best = [value]
    for split in range(1, len(words)):
        candidate = [" ".join(words[:split]), " ".join(words[split:])]
        if max(len(item) for item in candidate) < max(len(item) for item in best):
            best = candidate
    return best


def _fit_font(draw: ImageDraw.ImageDraw, lines: list[str], path: Path) -> ImageFont.FreeTypeFont:
    max_width = 700
    for size in range(118, 59, -2):
        font = ImageFont.truetype(str(path), size=size)
        if all(draw.textbbox((0, 0), line, font=font, stroke_width=5)[2] <= max_width for line in lines):
            return font
    raise VectorEngineError("thumbnail text is too wide even at the minimum production font size")


def overlay_thumbnail_text(
    base_image: Path,
    output: Path,
    text: str,
    *,
    font_path: str | None = None,
) -> Path:
    """Apply the same deterministic Cyrillic typography to any local base."""
    value = " ".join(str(text or "").split()) if "\n" not in str(text or "") else str(text).strip()
    if not value or len(value.replace("\n", " ")) > MAX_OVERLAY_CHARACTERS:
        raise VectorEngineError(f"thumbnail text must contain 1-{MAX_OVERLAY_CHARACTERS} characters")
    try:
        with Image.open(base_image) as source:
            canvas = _cover(source, THUMBNAIL_SIZE).convert("RGBA")
    except (OSError, UnidentifiedImageError) as exc:
        raise VectorEngineError(f"Unable to decode local thumbnail base: {exc}") from exc

    # Fixed gradient, accent and typography keep the packaging reproducible; the
    # image model is responsible only for the visual premise.
    shade = Image.new("RGBA", THUMBNAIL_SIZE, (0, 0, 0, 0))
    shade_draw = ImageDraw.Draw(shade)
    for x in range(850):
        alpha = 202 if x <= 590 else max(0, round(202 * (1 - (x - 590) / 260)))
        shade_draw.line((x, 0, x, THUMBNAIL_SIZE[1]), fill=(5, 8, 15, alpha))
    canvas.alpha_composite(shade)
    draw = ImageDraw.Draw(canvas)
    font_file = _font_path(font_path)
    lines = _wrap_text(value.upper(), width=20)
    font = _fit_font(draw, lines, font_file)
    small = ImageFont.truetype(str(font_file), size=31)
    label = "ИСТОРИЯ REDDIT"
    label_box = draw.textbbox((0, 0), label, font=small)
    label_right = 72 + (label_box[2] - label_box[0]) + 44
    draw.rounded_rectangle((72, 78, label_right, 126), radius=22, fill="#ff4500")
    draw.text((94, 83), label, font=small, fill="#ffffff")
    line_height = max(draw.textbbox((0, 0), line, font=font, stroke_width=6)[3] for line in lines) + 20
    total_height = line_height * len(lines)
    cursor = max(178, (THUMBNAIL_SIZE[1] - total_height) // 2 + 36)
    for line in lines:
        draw.text(
            (72, cursor), line, font=font, fill="#ffffff",
            stroke_width=8, stroke_fill="#080b12",
        )
        cursor += line_height
    draw.rectangle((72, min(642, cursor + 12), 390, min(654, cursor + 24)), fill="#ff4500")

    output.parent.mkdir(parents=True, exist_ok=True)
    canvas.convert("RGB").save(output, format="PNG", optimize=True)
    return output


def write_thumbnail_report(path: Path, output: Path, *, mode: str, provider_called: bool) -> dict[str, Any]:
    """Atomically bind the release report to a decoded production PNG."""
    try:
        with Image.open(output) as image:
            dimensions = list(image.size)
            image.verify()
    except (OSError, UnidentifiedImageError) as exc:
        raise VectorEngineError(f"Unable to verify composed thumbnail: {exc}") from exc
    if dimensions != list(THUMBNAIL_SIZE):
        raise VectorEngineError("Composed thumbnail must be 1280x720 before report creation")
    report = {
        "status": "PASS",
        "sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
        "dimensions": dimensions,
        "mode": mode,
        "provider_called": bool(provider_called),
        "output": str(output),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)
    return report


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--metadata", default="youtube_metadata.json", help="Metadata JSON path.")
    parser.add_argument("--prompt", help="Direct prompt override.")
    parser.add_argument("--text", help="Deterministic overlay text override.")
    parser.add_argument("--base-image", help="Existing local image; skips provider generation entirely.")
    parser.add_argument("--font", help="Optional explicit Cyrillic-capable TTF/OTF path.")
    parser.add_argument("--output", "-o", default="youtube_thumbnail.png", help="Output PNG path.")
    parser.add_argument("--report", help="Optional atomic JSON report written after a verified PNG.")
    parser.add_argument("--model", default=DEFAULT_IMAGE_MODEL, help="VectorEngine image model.")
    parser.add_argument("--size", default="1536x864", help="Image size for VectorEngine.")
    parser.add_argument("--env-file", action="append", default=[], help="Optional env file to load.")
    parser.add_argument("--confirm-spend", action="store_true", help="Required for live image generation.")
    parser.add_argument("--dry-run", action="store_true", help="Validate without API spend or file output.")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    loaded_env_files = [path for path in args.env_file if load_dotenv_file(path)]
    metadata: dict[str, Any] = {}
    metadata_path = Path(args.metadata)
    if metadata_path.is_file():
        metadata = _load_metadata(metadata_path)
    elif not args.prompt and not args.base_image:
        raise VectorEngineError(f"{metadata_path} does not exist and no --prompt/--base-image was supplied.")

    prompt = str(args.prompt or metadata.get("thumbnail_prompt") or "").strip()
    text = str(args.text or _selected_thumbnail_text(metadata)).strip()
    if not args.base_image and not prompt:
        raise VectorEngineError("thumbnail prompt is required for provider generation")
    if not text:
        raise VectorEngineError("thumbnail text is required for deterministic overlay")
    if not args.prompt and metadata:
        prompt = load_prompt(metadata_path)

    report = {
        "model": args.model,
        "size": args.size,
        "output": args.output,
        "promptCharacters": len(prompt),
        "overlayCharacters": len(text),
        "loadedEnvFileCount": len(loaded_env_files),
        "providerCalled": False,
    }
    if args.dry_run:
        print(json.dumps({"status": "dry-run", **report}, ensure_ascii=False, indent=2))
        return 0

    output = Path(args.output)
    if args.base_image:
        output = overlay_thumbnail_text(Path(args.base_image), output, text, font_path=args.font)
        artifact_report = write_thumbnail_report(
            Path(args.report), output, mode="local-overlay", provider_called=False,
        ) if args.report else None
        print(json.dumps({
            "status": "ok", "mode": "local-overlay", **report,
            "output": str(output), "sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
            "report": str(args.report) if artifact_report else None,
        }, ensure_ascii=False, indent=2))
        return 0

    if not args.confirm_spend:
        raise VectorEngineError(
            "Refusing to call VectorEngine image generation because this spends API credits. "
            "Re-run with --confirm-spend or use --dry-run/--base-image."
        )

    key_name, _ = get_api_key()
    generated = call_image_generation(
        prompt=prompt,
        output_path=output,
        model=args.model,
        size=args.size,
    )
    output = overlay_thumbnail_text(Path(generated), output, text, font_path=args.font)
    artifact_report = write_thumbnail_report(
        Path(args.report), output, mode="provider-base-plus-local-overlay", provider_called=True,
    ) if args.report else None
    print(json.dumps({
        "status": "ok",
        "mode": "provider-base-plus-local-overlay",
        "provider": "vectorengine",
        "providerCalled": True,
        "model": args.model,
        "size": args.size,
        "output": str(output),
        "sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
        "keyName": key_name,
        "loadedEnvFileCount": len(loaded_env_files),
        "report": str(args.report) if artifact_report else None,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv[1:]))
    except (OSError, json.JSONDecodeError, VectorEngineError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
