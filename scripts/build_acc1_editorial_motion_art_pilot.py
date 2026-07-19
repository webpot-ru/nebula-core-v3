#!/usr/bin/env python3
"""Render an artistic editorial-motion pilot from verified gpt-image-2 plates.

This script performs no provider calls.  It converts the previously generated
S-tier motel plates into two source-bound asset packs and sends them through
the same production renderer used by ``editorial_motion_v1``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from acc1_editorial_motion import build_editorial_motion_contract
from acc1_visual_contract import EDITORIAL_MOTION_MODE, EDITORIAL_MOTION_STYLE_PROFILE
from compilation_editorial_motion_renderer import render_editorial_motion_compilation


SOURCE_ROOT = ROOT / "build/s-tier-stack-pilot/assets"
SOURCE_JOURNAL = ROOT / "build/s-tier-stack-pilot/gpt-image-2-assets.json"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _text_sha256(text: str) -> str:
    return hashlib.sha256(" ".join(text.split()).encode("utf-8")).hexdigest()


def _timing(text: str, duration: float) -> dict:
    words = text.split()
    return {
        "duration_sec": duration,
        "timing_source": "art_pilot_fixture",
        "words": [
            {
                "word": word,
                "start": round(index * duration / len(words), 3),
                "end": round((index + 1) * duration / len(words), 3),
                "timing_source": "art_pilot_fixture",
            }
            for index, word in enumerate(words)
        ],
    }


def _asset(
    path: Path,
    *,
    root: Path,
    family: str,
    role: str,
    module: str,
    excerpt: str,
) -> dict:
    return {
        "kind": "generated_image",
        "provider": "vectorengine",
        "model": "gpt-image-2",
        "local_path": path.relative_to(root).as_posix(),
        "sha256": _sha256(path),
        "asset_family_id": family,
        "layer_role": role,
        "motion_module": module,
        "source_excerpt_sha256": _text_sha256(excerpt),
        "factual_text_allowed": False,
    }


def build(output_dir: Path) -> dict:
    if not SOURCE_JOURNAL.is_file():
        raise RuntimeError("missing gpt-image-2 provenance journal")
    provenance = json.loads(SOURCE_JOURNAL.read_text(encoding="utf-8"))
    if not isinstance(provenance, dict):
        raise RuntimeError("invalid gpt-image-2 provenance journal")

    output_dir.mkdir(parents=True, exist_ok=True)
    asset_dir = output_dir / "assets"
    asset_dir.mkdir(parents=True, exist_ok=True)
    names = (
        "motel-exterior.png",
        "lobby-monitor.png",
        "corridor-door.png",
        "keycard-evidence.png",
    )
    copied: dict[str, Path] = {}
    for name in names:
        source = SOURCE_ROOT / name
        if not source.is_file():
            raise RuntimeError(f"missing paid pilot plate: {name}")
        target = asset_dir / name
        shutil.copy2(source, target)
        copied[name] = target

    intro = "В три семнадцать ночи пустой мотель зафиксировал гостя которого не существовало"
    story = (
        "Сначала администратор увидел только слабое движение на парковке и решил что камера поймала отражение. "
        "Но монитор в холле показал ту же фигуру уже внутри здания хотя входная дверь ни разу не открылась. "
        "Он сверил журнал смены и обнаружил активированную ключ карту от номера который оставался закрытым весь месяц. "
        "На записи коридора дверь этого номера медленно приоткрылась за несколько секунд до того как карта появилась в системе. "
        "Последняя отметка изменила смысл всей последовательности камера не предсказала приход гостя она наблюдала как кто то выходил наружу"
    )
    outro = "После этой детали прежняя версия событий рассыпалась окончательно"
    story_words = story.split()
    split = round(len(story_words) / 2)
    excerpts = (" ".join(story_words[:split]), " ".join(story_words[split:]))

    assets = [
        _asset(
            copied["motel-exterior.png"], root=output_dir,
            family="motel-night-pack-001", role="hero_plate",
            module="digital_memory_stack", excerpt=excerpts[0],
        ),
        _asset(
            copied["lobby-monitor.png"], root=output_dir,
            family="motel-night-pack-001", role="detail_plate",
            module="digital_memory_stack", excerpt=excerpts[0],
        ),
        _asset(
            copied["corridor-door.png"], root=output_dir,
            family="motel-night-pack-002", role="hero_plate",
            module="evidence_transform", excerpt=excerpts[1],
        ),
        _asset(
            copied["keycard-evidence.png"], root=output_dir,
            family="motel-night-pack-002", role="detail_plate",
            module="evidence_transform", excerpt=excerpts[1],
        ),
    ]
    segments = [
        {"segment_id": "intro", "kind": "intro", "voice_role": "narrator", "text": intro},
        {"segment_id": "story_motel", "kind": "story", "voice_role": "narrator", "text": story},
        {"segment_id": "outro", "kind": "outro", "voice_role": "narrator", "text": outro},
    ]
    timings = {
        "intro": _timing(intro, 6.0),
        "story_motel": _timing(story, 80.0),
        "outro": _timing(outro, 6.0),
    }
    contract = build_editorial_motion_contract(
        narration_segments=segments,
        segment_timings=timings,
        story_assets={"story_motel": assets},
        story_metadata={
            "story_motel": {
                "story_index": 1,
                "title": "НОЧНАЯ СМЕНА",
                "source_label": "РЕДАКЦИОННАЯ ИЛЛЮСТРАЦИЯ",
                "truth_mode": "fiction",
            },
        },
        final_audio_duration_sec=92.0,
    )
    storyboard = {
        "version": 4,
        "format": "compilation_16x9",
        "resolution": [1920, 1080],
        "fps": 30,
        "visual_mode": EDITORIAL_MOTION_MODE,
        "style_profile": EDITORIAL_MOTION_STYLE_PROFILE,
        "publication_authorized": False,
        "timeline_duration_sec": 92.0,
        "slides": contract["scenes"],
        "motion_plan": contract["motion_plan"],
        "motion_plan_sha256": contract["motion_plan"]["motion_plan_sha256"],
        "caption_track": contract["caption_track"],
        "caption_track_sha256": contract["caption_track"]["caption_track_sha256"],
    }
    (output_dir / "storyboard.json").write_text(
        json.dumps(storyboard, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )
    (output_dir / "asset-provenance.json").write_text(
        json.dumps(
            {
                "provider_calls_this_run": 0,
                "source_journal": SOURCE_JOURNAL.relative_to(ROOT).as_posix(),
                "source_journal_sha256": _sha256(SOURCE_JOURNAL),
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
            "-t", "92", "-c:a", "pcm_s16le", str(audio),
        ],
        check=True,
        capture_output=True,
    )
    output = output_dir / "editorial-motion-art-pilot.mp4"
    report = render_editorial_motion_compilation(
        storyboard, output_dir, output, audio=audio,
    )
    report["output"] = output.name
    report["provider_calls_this_run"] = 0
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
