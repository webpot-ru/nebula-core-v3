#!/usr/bin/env python3
"""Build a no-provider editorial-motion fixture through the production renderer."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from acc1_editorial_motion import build_editorial_motion_contract
from acc1_visual_contract import EDITORIAL_MOTION_MODE, EDITORIAL_MOTION_STYLE_PROFILE
from compilation_editorial_motion_renderer import render_editorial_motion_compilation


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _plate(path: Path, *, detail: bool) -> None:
    image = Image.new("RGB", (1536, 864), "#111c24")
    draw = ImageDraw.Draw(image)
    for y in range(864):
        shade = int(18 + y / 864 * 30)
        draw.line((0, y, 1536, y), fill=(shade // 2, shade, shade + 9))
    draw.rectangle((110, 170, 1426, 720), fill="#182a34", outline="#8ac6c8", width=5)
    if detail:
        draw.rectangle((430, 250, 1120, 650), fill="#d9cfbd", outline="#e34a2f", width=16)
        draw.rectangle((520, 330, 1030, 370), fill="#1a1c1d")
        draw.rectangle((520, 410, 910, 438), fill="#8d7761")
        draw.ellipse((940, 500, 1015, 575), fill="#f0a62b")
    else:
        for index in range(6):
            x = 190 + index * 210
            draw.rectangle((x, 260, x + 150, 610), fill="#273c46", outline="#6f858b", width=4)
        draw.polygon(((100, 720), (1436, 720), (1280, 864), (260, 864)), fill="#0b1116")
        draw.rectangle((1040, 330, 1220, 540), outline="#f0a62b", width=12)
    image.save(path)


def _timing(text: str, duration: float) -> dict:
    words = text.split()
    return {
        "duration_sec": duration,
        "timing_source": "fixture",
        "words": [
            {
                "word": word,
                "start": round(index * duration / len(words), 3),
                "end": round((index + 1) * duration / len(words), 3),
                "timing_source": "fixture",
            }
            for index, word in enumerate(words)
        ],
    }


def build(output_dir: Path) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    hero = output_dir / "fixture-hero.png"
    detail = output_dir / "fixture-detail.png"
    _plate(hero, detail=False)
    _plate(detail, detail=True)
    family = "fixture-night-shift-pack-001"
    assets = [
        {
            "kind": "generated_image",
            "local_path": hero.relative_to(output_dir).as_posix(),
            "sha256": _sha256(hero),
            "asset_family_id": family,
            "layer_role": "hero_plate",
            "motion_module": "living_photo_depth",
            "source_excerpt_sha256": "a" * 64,
            "factual_text_allowed": False,
        },
        {
            "kind": "generated_image",
            "local_path": detail.relative_to(output_dir).as_posix(),
            "sha256": _sha256(detail),
            "asset_family_id": family,
            "layer_role": "detail_plate",
            "motion_module": "living_photo_depth",
            "source_excerpt_sha256": "a" * 64,
            "factual_text_allowed": False,
        },
    ]
    intro = "В ту ночь камера заметила одну невозможную деталь"
    story = (
        "Администратор проверил пустой коридор затем открыл журнал и увидел что ключ "
        "выдали за двадцать минут до появления человека на записи наблюдения"
    )
    outro = "После этого прежняя версия событий больше не работала"
    segments = [
        {"segment_id": "intro", "kind": "intro", "voice_role": "narrator", "text": intro},
        {"segment_id": "story_fixture", "kind": "story", "voice_role": "narrator", "text": story},
        {"segment_id": "outro", "kind": "outro", "voice_role": "narrator", "text": outro},
    ]
    timings = {
        "intro": _timing(intro, 5.0),
        "story_fixture": _timing(story, 40.0),
        "outro": _timing(outro, 5.0),
    }
    contract = build_editorial_motion_contract(
        narration_segments=segments,
        segment_timings=timings,
        story_assets={"story_fixture": assets},
        story_metadata={
            "story_fixture": {
                "story_index": 1,
                "title": "НОЧНАЯ СМЕНА",
                "source_label": "ЛОКАЛЬНЫЙ FIXTURE",
                "truth_mode": "fiction",
            },
        },
        final_audio_duration_sec=50.0,
    )
    storyboard = {
        "version": 4,
        "format": "compilation_16x9",
        "resolution": [1920, 1080],
        "fps": 30,
        "visual_mode": EDITORIAL_MOTION_MODE,
        "style_profile": EDITORIAL_MOTION_STYLE_PROFILE,
        "publication_authorized": False,
        "timeline_duration_sec": 50.0,
        "slides": contract["scenes"],
        "motion_plan": contract["motion_plan"],
        "motion_plan_sha256": contract["motion_plan"]["motion_plan_sha256"],
        "caption_track": contract["caption_track"],
        "caption_track_sha256": contract["caption_track"]["caption_track_sha256"],
    }
    storyboard_path = output_dir / "storyboard.json"
    storyboard_path.write_text(
        json.dumps(storyboard, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )
    audio = output_dir / "fixture-audio.wav"
    subprocess.run([
        "ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo",
        "-t", "50", "-c:a", "pcm_s16le", str(audio),
    ], check=True, capture_output=True)
    output = output_dir / "editorial-motion-fixture.mp4"
    report = render_editorial_motion_compilation(
        storyboard, output_dir, output, audio=audio,
    )
    report["output"] = output.name
    (output_dir / "render-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()
    print(json.dumps(build(Path(args.output_dir)), ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
