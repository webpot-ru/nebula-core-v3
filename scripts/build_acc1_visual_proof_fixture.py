#!/usr/bin/env python3
"""Build a deterministic no-provider long-text visual proof fixture for acc1."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from acc1_visual_contract import BACKGROUND_ASSET_PATH, BACKGROUND_ASSET_SHA256


SCENE_COLORS = (
    (32, 66, 84),
    (61, 90, 74),
    (103, 72, 84),
    (86, 69, 42),
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _placeholder(path: Path, *, story_index: int, scene_index: int) -> None:
    base = SCENE_COLORS[(scene_index - 1) % len(SCENE_COLORS)]
    image = Image.new("RGB", (1536, 864), base)
    draw = ImageDraw.Draw(image)
    accent = tuple(min(255, channel + 48) for channel in base)
    for offset in range(-864, 1536, 160):
        draw.polygon(
            [(offset, 864), (offset + 360, 864), (offset + 900, 0), (offset + 540, 0)],
            fill=accent,
        )
    draw.ellipse((180 + story_index * 40, 180, 650 + story_index * 40, 650), outline="#f0d9b5", width=18)
    image.save(path, format="PNG")


def build_fixture(output_dir: Path, background_source: Path) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=False)
    if _sha256(background_source) != BACKGROUND_ASSET_SHA256:
        raise RuntimeError("approved acc1 background checksum mismatch")
    background = output_dir / "chonker-reading-loop-v1.mp4"
    shutil.copy2(background_source, background)

    stories = []
    source_urls = []
    sentence = (
        "Вечером герой заметил странную деталь затем проверил дверь позвонил соседу "
        "и наконец понял настоящую причину происходящего."
    )
    for story_index in range(1, 4):
        generated_media = []
        for scene_index in range(1, 5):
            image_path = output_dir / f"story-{story_index:02d}-scene-{scene_index:02d}.png"
            _placeholder(image_path, story_index=story_index, scene_index=scene_index)
            generated_media.append({
                "media_id": f"fixture-story-{story_index}-scene-{scene_index}",
                "kind": "generated_image",
                "download_status": "verified",
                "local_path": str(image_path),
                "sha256": _sha256(image_path),
                "caption": "",
                "scene_index": scene_index,
                "scene_count": 4,
            })
        source_body = f"Synthetic Reddit fixture body for story {story_index}. Complete ending."
        source_url = f"https://reddit.example/proof-{story_index}"
        source_urls.append(source_url)
        stories.append({
            "title_ru": f"Тестовая история {story_index}",
            "hook_ru": "Странная деталь меняет смысл всей истории.",
            "narration_ru": " ".join(sentence for _ in range(120)),
            "disclosure": "This story is fiction from Reddit.",
            "ending_preserved_evidence": "Complete ending.",
            "change_ledger": [],
            "invented_factual_claims": [],
            "editorial_review": {"verdict": "PASS", "issues": []},
            "generated_media": generated_media,
            "source_snapshot": {
                "post_id": f"proof-{story_index}",
                "source_url": source_url,
                "subreddit": "r/nosleep",
                "title": f"Proof story {story_index}",
                "body": source_body,
                "body_sha256": hashlib.sha256(source_body.encode("utf-8")).hexdigest(),
                "truth_mode": "fiction",
                "source_media": [],
            },
        })

    compilation = {
        "title_ru": "Три тестовые истории Reddit",
        "intro_ru": "Проверяем длинный текст, смену сцен и безопасную область персонажа.",
        "outro_ru": "Это локальная техническая проверка без публикации и внешних провайдеров.",
        "rights_mode": "test_only_not_cleared",
        "publication_authorized": False,
        "revision_count": 0,
        "stories": stories,
        "editorial_review": {"verdict": "PASS", "issues": []},
    }
    metadata = {
        "packaging_options": [
            {"youtube_title": f"Локальный proof {index}", "thumbnail_text": f"ПРОВЕРКА {index}", "angle": f"proof-{index}"}
            for index in range(1, 4)
        ],
        "youtube_description": "\n".join(source_urls),
        "language": "ru",
    }
    tts_state = {
        "status": "COMPLETE",
        "required_model_id": "eleven_v3",
        "chunks": [{
            "status": "COMPLETE", "model_id": "eleven_v3",
            "voice_id": "local-no-provider-proof", "audio_sha256": "a" * 64,
        }],
        "final_audio_sha256": "b" * 64,
    }
    thumbnail = output_dir / "thumbnail.png"
    Image.new("RGB", (1280, 720), "#203142").save(thumbnail, format="PNG")
    audio = output_dir / "silent-layout-proof.wav"
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("ffmpeg is required")
    subprocess.run([
        ffmpeg, "-y", "-v", "error", "-f", "lavfi", "-i",
        "anullsrc=channel_layout=stereo:sample_rate=44100", "-t", "36", str(audio),
    ], check=True)
    _write_json(output_dir / "compilation.json", compilation)
    _write_json(output_dir / "metadata.json", metadata)
    _write_json(output_dir / "tts-state.json", tts_state)
    result = {
        "output_dir": str(output_dir),
        "background": str(background),
        "background_sha256": _sha256(background),
        "compilation": str(output_dir / "compilation.json"),
        "metadata": str(output_dir / "metadata.json"),
        "tts_state": str(output_dir / "tts-state.json"),
        "thumbnail": str(thumbnail),
        "audio": str(audio),
        "audio_role": "silence_only_layout_stress_test",
    }
    _write_json(output_dir / "fixture-manifest.json", result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--background", default=BACKGROUND_ASSET_PATH)
    args = parser.parse_args()
    result = build_fixture(Path(args.output_dir), Path(args.background))
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
