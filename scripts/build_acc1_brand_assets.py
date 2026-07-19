#!/usr/bin/env python3
"""Build deterministic local acc1 banner/avatar assets from approved Chonker art."""

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps


BANNER_SIZE = (2560, 1440)
SAFE_AREA = (507, 509, 2053, 932)
AVATAR_SIZE = (800, 800)
TITLE = "ИСТОРИИ REDDIT"
SUBTITLE = "НА РУССКОМ"
EYEBROW = "CHONKER TALKS"


def _font(paths: list[str], size: int) -> ImageFont.FreeTypeFont:
    for value in paths:
        path = Path(value)
        if path.exists():
            return ImageFont.truetype(str(path), size=size)
    raise RuntimeError("No supported local font found")


def _fonts() -> tuple[ImageFont.FreeTypeFont, ImageFont.FreeTypeFont, ImageFont.FreeTypeFont]:
    bold = [
        "/System/Library/Fonts/Supplemental/Arial Black.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/Library/Fonts/Arial Unicode.ttf",
    ]
    regular = [
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/Library/Fonts/Arial Unicode.ttf",
    ]
    return _font(bold, 104), _font(bold, 44), _font(regular, 32)


def _left_gradient(size: tuple[int, int]) -> Image.Image:
    width, height = size
    overlay = Image.new("RGBA", size, (0, 0, 0, 0))
    pixels = overlay.load()
    for x in range(width):
        if x <= 1160:
            alpha = 72
        elif x >= 1720:
            alpha = 0
        else:
            alpha = round(72 * (1720 - x) / 560)
        for y in range(height):
            pixels[x, y] = (2, 10, 19, alpha)
    return overlay


def build_banner(source: Image.Image) -> Image.Image:
    banner = ImageOps.fit(source.convert("RGB"), BANNER_SIZE, method=Image.Resampling.LANCZOS)
    banner = ImageEnhance.Contrast(banner).enhance(1.04).convert("RGBA")
    banner = Image.alpha_composite(banner, _left_gradient(BANNER_SIZE))
    draw = ImageDraw.Draw(banner)
    title_font, subtitle_font, eyebrow_font = _fonts()

    x = SAFE_AREA[0] + 58
    y = SAFE_AREA[1] + 48
    accent = (244, 95, 65, 255)
    white = (245, 247, 250, 255)
    muted = (189, 204, 218, 255)

    eyebrow_box = draw.textbbox((x + 20, y + 7), EYEBROW, font=eyebrow_font)
    eyebrow_width = eyebrow_box[2] - eyebrow_box[0]
    draw.rounded_rectangle(
        (x, y, x + eyebrow_width + 40, y + 44),
        radius=22,
        fill=(18, 43, 65, 232),
    )
    draw.text((x + 20, y + 7), EYEBROW, font=eyebrow_font, fill=muted)
    y += 74
    draw.text((x, y), TITLE, font=title_font, fill=white, stroke_width=2, stroke_fill=(0, 0, 0, 150))
    title_box = draw.textbbox((x, y), TITLE, font=title_font, stroke_width=2)
    y = title_box[3] + 12
    draw.rounded_rectangle((x, y + 9, x + 68, y + 17), radius=4, fill=accent)
    draw.text((x + 92, y - 7), SUBTITLE, font=subtitle_font, fill=accent)
    return banner.convert("RGB")


def build_text_ready_banner(source: Image.Image) -> Image.Image:
    """Reframe a finished imagegen banner so its typography fits YouTube safe area."""
    background = ImageOps.fit(source.convert("RGB"), BANNER_SIZE, method=Image.Resampling.LANCZOS)
    background = ImageEnhance.Brightness(background.filter(ImageFilter.GaussianBlur(18))).enhance(0.42)

    overlay_width = 1894
    overlay_height = round(overlay_width * source.height / source.width)
    overlay = source.convert("RGB").resize((overlay_width, overlay_height), Image.Resampling.LANCZOS)
    x = 384
    y = (BANNER_SIZE[1] - overlay_height) // 2
    mask = Image.new("L", overlay.size, 0)
    inset = 34
    ImageDraw.Draw(mask).rectangle(
        (inset, inset, overlay_width - inset, overlay_height - inset),
        fill=255,
    )
    mask = mask.filter(ImageFilter.GaussianBlur(42))
    background.paste(overlay, (x, y), mask)
    return background


def build_avatar(source: Image.Image) -> Image.Image:
    width, height = source.size
    crop_size = min(width * 0.44, height * 0.78)
    center_x = width * 0.735
    center_y = height * 0.45
    box = (
        round(center_x - crop_size / 2),
        round(center_y - crop_size / 2),
        round(center_x + crop_size / 2),
        round(center_y + crop_size / 2),
    )
    avatar = source.convert("RGB").crop(box).resize(AVATAR_SIZE, Image.Resampling.LANCZOS)
    avatar = ImageEnhance.Contrast(avatar).enhance(1.05)
    overlay = Image.new("RGBA", AVATAR_SIZE, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    draw.ellipse((14, 14, 786, 786), outline=(244, 95, 65, 255), width=18)
    return Image.alpha_composite(avatar.convert("RGBA"), overlay).convert("RGB")


def build_safe_area_preview(banner: Image.Image) -> Image.Image:
    preview = banner.convert("RGBA")
    overlay = Image.new("RGBA", preview.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    draw.rectangle(SAFE_AREA, outline=(64, 255, 153, 255), width=5)
    draw.rectangle((0, 0, BANNER_SIZE[0], SAFE_AREA[1]), fill=(0, 0, 0, 65))
    draw.rectangle((0, SAFE_AREA[3], BANNER_SIZE[0], BANNER_SIZE[1]), fill=(0, 0, 0, 65))
    draw.rectangle((0, SAFE_AREA[1], SAFE_AREA[0], SAFE_AREA[3]), fill=(0, 0, 0, 65))
    draw.rectangle((SAFE_AREA[2], SAFE_AREA[1], BANNER_SIZE[0], SAFE_AREA[3]), fill=(0, 0, 0, 65))
    return Image.alpha_composite(preview, overlay).convert("RGB")


def build_safe_area_guide() -> Image.Image:
    """Transparent overlay for composing a 2560x1440 YouTube banner."""
    guide = Image.new("RGBA", BANNER_SIZE, (0, 0, 0, 0))
    draw = ImageDraw.Draw(guide)
    shade = (0, 0, 0, 92)
    draw.rectangle((0, 0, BANNER_SIZE[0], SAFE_AREA[1]), fill=shade)
    draw.rectangle((0, SAFE_AREA[3], BANNER_SIZE[0], BANNER_SIZE[1]), fill=shade)
    draw.rectangle((0, SAFE_AREA[1], SAFE_AREA[0], SAFE_AREA[3]), fill=shade)
    draw.rectangle((SAFE_AREA[2], SAFE_AREA[1], BANNER_SIZE[0], SAFE_AREA[3]), fill=shade)
    draw.rectangle(SAFE_AREA, outline=(64, 255, 153, 255), width=6)
    return guide


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--version", default="v1")
    parser.add_argument(
        "--source-has-banner-text",
        action="store_true",
        help="Preserve imagegen typography and reframe the finished artwork into the YouTube safe area.",
    )
    args = parser.parse_args()

    source = Image.open(args.source)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    banner = build_text_ready_banner(source) if args.source_has_banner_text else build_banner(source)
    avatar = build_avatar(source)
    preview = build_safe_area_preview(banner)
    banner_path = output_dir / f"acc1-channel-banner-{args.version}.png"
    avatar_path = output_dir / f"acc1-channel-avatar-{args.version}.png"
    preview_path = output_dir / f"acc1-channel-banner-safe-area-preview-{args.version}.png"
    guide_path = output_dir / "youtube-banner-safe-area-guide-2560x1440.png"
    banner.save(banner_path, optimize=True)
    avatar.save(avatar_path, optimize=True)
    preview.save(preview_path, optimize=True)
    build_safe_area_guide().save(guide_path, optimize=True)
    print(f"banner={banner_path}")
    print(f"avatar={avatar_path}")
    print(f"preview={preview_path}")
    print(f"guide={guide_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
