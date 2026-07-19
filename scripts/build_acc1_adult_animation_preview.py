#!/usr/bin/env python3
"""Render one no-provider adult-animation profile preview through HyperFrames.

The preview deliberately uses crops of the locked style board only.  It is a
local renderer/choreography proof, not a story asset generator or a release
candidate.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from acc1_editorial_motion import build_editorial_motion_contract
from acc1_visual_contract import (
    ADULT_ANIMATION_SERIES,
    EDITORIAL_MOTION_MODE,
    is_adult_animation_style_profile,
    select_adult_animation_layouts,
)
from compilation_editorial_motion_renderer import render_editorial_motion_compilation


REFERENCE = ROOT / "docs/assets/acc1-adult-animation-six-series-v1.png"
PANEL_BOXES = {
    "adult_animation_family_v1": (0, 0, 557, 470),
    "adult_animation_work_v1": (557, 0, 1115, 470),
    "adult_animation_saga_absurd_v1": (1115, 0, 1672, 470),
    "adult_animation_confessions_v1": (0, 470, 557, 941),
    "adult_animation_professions_v1": (557, 470, 1115, 941),
    "adult_animation_daily_weird_v1": (1115, 470, 1672, 941),
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _timing(text: str, duration: float) -> dict:
    words = text.split()
    return {
        "duration_sec": duration,
        "timing_source": "adult_animation_preview",
        "words": [
            {
                "word": word,
                "start": round(index * duration / len(words), 3),
                "end": round((index + 1) * duration / len(words), 3),
                "timing_source": "adult_animation_preview",
            }
            for index, word in enumerate(words)
        ],
    }


def _write_plate(reference: Image.Image, box: tuple[int, int, int, int], output: Path, *, detail: bool) -> None:
    panel = reference.crop(box)
    if detail:
        width, height = panel.size
        panel = panel.crop((width // 5, height // 8, width, height * 7 // 8))
    ImageOps.fit(panel.convert("RGB"), (1536, 864), method=Image.Resampling.LANCZOS).save(output)


def _asset(path: Path, *, root: Path, family: str, role: str, module: str, story_family: str, page_layout: str) -> dict:
    return {
        "kind": "local_style_reference_crop",
        "local_path": path.relative_to(root).as_posix(),
        "sha256": _sha256(path),
        "asset_family_id": family,
        "layer_role": role,
        "motion_module": module,
        "source_excerpt_sha256": "0" * 64,
        "factual_text_allowed": False,
        "story_family": story_family,
        "page_layout": page_layout,
    }


def build(output_dir: Path, profile: str) -> dict:
    if not is_adult_animation_style_profile(profile):
        raise ValueError("profile must be one approved adult-animation profile")
    if not REFERENCE.is_file():
        raise RuntimeError("locked adult-animation reference asset is missing")
    output_dir.mkdir(parents=True, exist_ok=True)
    series = ADULT_ANIMATION_SERIES[profile]
    layouts = select_adult_animation_layouts(profile, "local-preview-source-20260718", 2)
    source = Image.open(REFERENCE)
    assets = []
    for index, (layout, module) in enumerate(zip(layouts, ("living_photo_depth", "evidence_transform")), start=1):
        hero = output_dir / f"preview-{index}-hero.png"
        detail = output_dir / f"preview-{index}-detail.png"
        _write_plate(source, PANEL_BOXES[profile], hero, detail=False)
        _write_plate(source, PANEL_BOXES[profile], detail, detail=True)
        family = f"preview-pack-{index:03d}"
        assets.extend((
            _asset(hero, root=output_dir, family=family, role="hero_plate", module=module, story_family=str(series["story_family"]), page_layout=layout),
            _asset(detail, root=output_dir, family=family, role="detail_plate", module=module, story_family=str(series["story_family"]), page_layout=layout),
        ))
    source.close()
    intro = "ПРОФИЛЬ АНИМАЦИОННОГО СЕРИАЛА"
    story_one = "Первая история раскрывается через одну композицию с собственным ритмом и реакцией"
    story_two = "Следующая история выбирает другую композицию и не копирует предыдущий лист комикса"
    outro = "СЛЕДУЮЩАЯ ИСТОРИЯ ВЫБЕРЕТ ДРУГИЕ РИТМЫ"
    segments = [
        {"segment_id": "intro", "kind": "intro", "voice_role": "narrator", "text": intro},
        {"segment_id": "story_preview_one", "kind": "story", "voice_role": "narrator", "text": story_one},
        {"segment_id": "story_preview_two", "kind": "story", "voice_role": "narrator", "text": story_two},
        {"segment_id": "outro", "kind": "outro", "voice_role": "narrator", "text": outro},
    ]
    timings = {
        "intro": _timing(intro, 4.0),
        "story_preview_one": _timing(story_one, 20.0),
        "story_preview_two": _timing(story_two, 20.0),
        "outro": _timing(outro, 4.0),
    }
    contract = build_editorial_motion_contract(
        narration_segments=segments,
        segment_timings=timings,
        story_assets={
            "story_preview_one": assets[:2],
            "story_preview_two": assets[2:],
        },
        story_metadata={
            "story_preview_one": {"story_index": 1, "title": str(series["label"]).upper(), "source_label": "ЛОКАЛЬНЫЙ ПРЕДПРОСМОТР"},
            "story_preview_two": {"story_index": 2, "title": "ДРУГАЯ КОМПОЗИЦИЯ", "source_label": "ЛОКАЛЬНЫЙ ПРЕДПРОСМОТР"},
        },
        final_audio_duration_sec=48.0,
        style_profile=profile,
    )
    storyboard = {
        "version": 4,
        "format": "compilation_16x9",
        "resolution": [1920, 1080],
        "fps": 30,
        "visual_mode": EDITORIAL_MOTION_MODE,
        "style_profile": profile,
        "publication_authorized": False,
        "timeline_duration_sec": 48.0,
        "slides": contract["scenes"],
        "motion_plan": contract["motion_plan"],
        "motion_plan_sha256": contract["motion_plan"]["motion_plan_sha256"],
        "caption_track": contract["caption_track"],
        "caption_track_sha256": contract["caption_track"]["caption_track_sha256"],
    }
    (output_dir / "storyboard.json").write_text(json.dumps(storyboard, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    audio = output_dir / "preview-silence.wav"
    subprocess.run([
        "ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo", "-t", "48", "-c:a", "pcm_s16le", str(audio),
    ], check=True, capture_output=True)
    output = output_dir / "adult-animation-preview.mp4"
    report = render_editorial_motion_compilation(storyboard, output_dir, output, audio=audio)
    report.update({"output": output.name, "provider_calls_this_run": 0, "reference_asset": REFERENCE.relative_to(ROOT).as_posix(), "selected_layouts": layouts})
    (output_dir / "render-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--profile", required=True, choices=sorted(ADULT_ANIMATION_SERIES))
    args = parser.parse_args()
    print(json.dumps(build(Path(args.output_dir), args.profile), ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
