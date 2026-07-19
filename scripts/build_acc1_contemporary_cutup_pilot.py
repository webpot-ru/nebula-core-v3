#!/usr/bin/env python3
"""Render the contemporary-cutup v1 motion profile from one approved styleframe.

The source frame is converted into a full composition plate plus a portal/detail
plate.  The script makes no provider calls and never authorizes publication.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from acc1_editorial_motion import build_editorial_motion_contract
from acc1_visual_contract import EDITORIAL_MOTION_MODE, EDITORIAL_MOTION_STYLE_PROFILE
from compilation_editorial_motion_renderer import render_editorial_motion_compilation


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _text_sha256(text: str) -> str:
    return hashlib.sha256(" ".join(text.split()).encode("utf-8")).hexdigest()


def _timing(text: str, duration: float) -> dict:
    words = text.split()
    return {
        "duration_sec": duration,
        "timing_source": "local_cutup_pilot",
        "words": [
            {
                "word": word,
                "start": round(index * duration / len(words), 3),
                "end": round((index + 1) * duration / len(words), 3),
                "timing_source": "local_cutup_pilot",
            }
            for index, word in enumerate(words)
        ],
    }


def _prepare_plates(source: Path, asset_dir: Path) -> tuple[Path, Path]:
    asset_dir.mkdir(parents=True, exist_ok=True)
    with Image.open(source) as image:
        frame = ImageOps.fit(
            image.convert("RGB"), (1536, 864), method=Image.Resampling.LANCZOS,
        )
    hero = asset_dir / "cutup-hero-plate.png"
    frame.save(hero, format="PNG", optimize=True)

    # Focus the second plate on the phone -> office -> chair route while
    # retaining enough context for a portal-scale push.
    detail_crop = frame.crop((520, 70, 1480, 850))
    detail = ImageOps.fit(
        detail_crop, (1536, 864), method=Image.Resampling.LANCZOS,
    )
    detail_path = asset_dir / "cutup-portal-plate.png"
    detail.save(detail_path, format="PNG", optimize=True)
    return hero, detail_path


def _asset(path: Path, root: Path, role: str, excerpt: str) -> dict:
    return {
        "kind": "generated_image",
        "provider": "openai-native-imagegen",
        "model": "imagegen",
        "local_path": path.relative_to(root).as_posix(),
        "sha256": _sha256(path),
        "asset_family_id": "contemporary-cutup-pilot-001",
        "layer_role": role,
        "motion_module": "digital_memory_stack",
        "source_excerpt_sha256": _text_sha256(excerpt),
        "factual_text_allowed": False,
    }


def _contact_sheet(video: Path, output_dir: Path) -> Path:
    frame_dir = output_dir / "review-frames"
    frame_dir.mkdir(parents=True, exist_ok=True)
    times = (1.0, 5.0, 9.0, 13.0, 18.0)
    paths: list[Path] = []
    for index, second in enumerate(times, start=1):
        path = frame_dir / f"frame-{index:02d}.png"
        subprocess.run(
            [
                "ffmpeg", "-y", "-ss", str(second), "-i", str(video),
                "-frames:v", "1", "-vf", "scale=768:432", str(path),
            ],
            check=True,
            capture_output=True,
        )
        paths.append(path)
    sheet = Image.new("RGB", (1536, 1296), "#111820")
    for index, path in enumerate(paths):
        with Image.open(path) as frame:
            x = (index % 2) * 768
            y = (index // 2) * 432
            sheet.paste(frame.convert("RGB"), (x, y))
    contact_sheet = output_dir / "contact-sheet.png"
    sheet.save(contact_sheet, format="PNG", optimize=True)
    return contact_sheet


def build(source: Path, output_dir: Path) -> dict:
    if not source.is_file():
        raise RuntimeError(f"missing approved styleframe: {source}")
    output_dir.mkdir(parents=True, exist_ok=True)
    hero, detail = _prepare_plates(source, output_dir / "assets")
    narration = (
        "Одно сообщение заставило её иначе увидеть обычный рабочий конфликт. "
        "Камера проходит через экран телефона в пустой офис, где знакомое кресло "
        "внезапно становится главным смысловым акцентом истории"
    )
    assets = [
        _asset(hero, output_dir, "hero_plate", narration),
        _asset(detail, output_dir, "detail_plate", narration),
    ]
    contract = build_editorial_motion_contract(
        narration_segments=[{
            "segment_id": "story_message",
            "kind": "story",
            "voice_role": "narrator",
            "text": narration,
        }],
        segment_timings={"story_message": _timing(narration, 20.0)},
        story_assets={"story_message": assets},
        story_metadata={
            "story_message": {
                "story_index": 1,
                "title": "ОДНО СООБЩЕНИЕ",
                "source_label": "ВИЗУАЛЬНЫЙ ПИЛОТ",
                "truth_mode": "editorial_demo",
            },
        },
        final_audio_duration_sec=20.0,
    )
    storyboard = {
        "version": 4,
        "format": "compilation_16x9",
        "resolution": [1920, 1080],
        "fps": 30,
        "visual_mode": EDITORIAL_MOTION_MODE,
        "style_profile": EDITORIAL_MOTION_STYLE_PROFILE,
        "publication_authorized": False,
        "timeline_duration_sec": 20.0,
        "slides": contract["scenes"],
        "motion_plan": contract["motion_plan"],
        "motion_plan_sha256": contract["motion_plan"]["motion_plan_sha256"],
        "caption_track": contract["caption_track"],
        "caption_track_sha256": contract["caption_track"]["caption_track_sha256"],
    }
    (output_dir / "storyboard.json").write_text(
        json.dumps(storyboard, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )
    copied_styleframe = output_dir / "approved-styleframe.png"
    shutil.copy2(source, copied_styleframe)
    (output_dir / "asset-provenance.json").write_text(
        json.dumps(
            {
                "provider_calls_this_render": 0,
                "style_profile": EDITORIAL_MOTION_STYLE_PROFILE,
                "approved_styleframe_sha256": _sha256(copied_styleframe),
                "assets": assets,
            },
            ensure_ascii=False,
            indent=2,
        ) + "\n",
        encoding="utf-8",
    )
    audio = output_dir / "pilot-audio.wav"
    subprocess.run(
        [
            "ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo",
            "-t", "20", "-c:a", "pcm_s16le", str(audio),
        ],
        check=True,
        capture_output=True,
    )
    output = output_dir / "contemporary-cutup-pilot.mp4"
    report = render_editorial_motion_compilation(
        storyboard, output_dir, output, audio=audio,
    )
    report.update({
        "output": output.name,
        "provider_calls_this_render": 0,
        "contact_sheet": _contact_sheet(output, output_dir).name,
    })
    (output_dir / "render-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()
    print(json.dumps(build(Path(args.source), Path(args.output_dir)), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
