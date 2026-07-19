#!/usr/bin/env python3
"""Build a human-paced, no-provider acc1 format-review MP4.

This is deliberately not source-selection evidence. It uses a short synthetic
story, macOS system speech, approved local background, and deterministic scene
art so the viewer can judge pacing, Reddit chrome, intro/outro, and page changes
without spending provider credits.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from acc1_visual_contract import BACKGROUND_ASSET_PATH, BACKGROUND_ASSET_SHA256
from compilation_renderer import render_compilation
from compilation_storyboard import build_storyboard, narration_text


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _scene(path: Path, color: str, accent: str, offset: int) -> None:
    image = Image.new("RGB", (1536, 864), color)
    glow = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(glow)
    draw.ellipse((40 + offset, 20, 980 + offset, 960), fill=accent + "b8")
    glow = glow.filter(ImageFilter.GaussianBlur(150))
    image = Image.alpha_composite(image.convert("RGBA"), glow).convert("RGB")
    image.save(path, format="PNG")


def build(
    output_dir: Path,
    background_source: Path,
    *,
    system_voice: str,
    audio_source: Path | None = None,
) -> dict[str, object]:
    output_dir.mkdir(parents=True, exist_ok=False)
    if _sha256(background_source) != BACKGROUND_ASSET_SHA256:
        raise RuntimeError("approved acc1 background checksum mismatch")
    say = shutil.which("say")
    if not say:
        raise RuntimeError("macOS say is required for the no-provider spoken preview")
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("ffmpeg is required for the no-provider spoken preview")

    background = output_dir / "chonker-reading-loop-v1.mp4"
    shutil.copy2(background_source, background)
    media = []
    for index, (color, accent) in enumerate(
        (("#1c3342", "#7f9aaa"), ("#3b2d37", "#9a6c7d"), ("#2c3c2f", "#76927c")),
        start=1,
    ):
        image_path = output_dir / f"scene-{index:02d}.png"
        _scene(image_path, color, accent, index * 45)
        media.append({
            "media_id": f"format-review-scene-{index}",
            "kind": "generated_image",
            "download_status": "verified",
            "local_path": str(image_path),
            "sha256": _sha256(image_path),
            "scene_index": index,
            "scene_count": 3,
        })

    story_beats = [
        (
            "Я заметил, что каждое утро сосед оставляет у моей двери пустую синюю кружку. "
            "Сначала я решил, что он просто путает этажи, поэтому отнёс кружку обратно и ничего не сказал. "
            "На следующий день она снова стояла на коврике, а под ней лежала записка с просьбой не открывать дверь после полуночи."
        ),
        (
            "Я постучал к соседу, но квартира оказалась пустой, и управляющий сказал, что там уже несколько месяцев никто не живёт. "
            "Вечером я поставил телефон снимать коридор и лёг спать, стараясь не думать о записке. "
            "Ровно в полночь раздался короткий звонок, затем второй, а потом кто-то очень медленно провёл кружкой по двери. "
            "Я не открыл и дождался утра. На записи не было человека: кружка появилась в кадре сама, будто её осторожно поставили из слепой зоны."
        ),
        (
            "Тогда консьерж вспомнил прежнего жильца, который каждый день приносил больной соседке чай в такой же синей кружке. "
            "Женщина жила в моей квартире и однажды не ответила на ночной звонок. После этого кружка стала появляться у каждой новой двери. "
            "Я оставил её у пустой квартиры и написал на записке, что помощь больше не нужна. На следующее утро коридор был пуст, и кружка больше не возвращалась."
        ),
    ]
    story_text = " ".join(story_beats)
    compilation = {
        "title_ru": "Истории Reddit на русском",
        "intro_ru": "Добрый вечер. Сегодня проверяем новый формат Chonker Talks: одна короткая история, спокойный темп и настоящий интерфейс Reddit.",
        "outro_ru": "Как вы думаете, у этой истории есть обычное объяснение? Напишите свою версию в комментариях. До следующей истории.",
        "rights_mode": "synthetic_format_review_only",
        "publication_authorized": False,
        "revision_count": 0,
        "stories": [{
            "title_ru": "Каждое утро у моей двери появлялась синяя кружка",
            "narration_ru": story_text,
            "story_beats": story_beats,
            "generated_media": media,
            "source_snapshot": {
                "post_id": "synthetic-format-review",
                "source_url": "https://www.reddit.com/",
                "subreddit": "AskReddit",
                "author": "format_review_fixture",
                "score": 12400,
                "num_comments": 428,
                "title": "Synthetic format review",
                "truth_mode": "fiction",
                "source_media": [],
            },
        }],
        "editorial_review": {"verdict": "TEST_ONLY", "issues": ["synthetic source"]},
    }
    compilation_path = output_dir / "compilation.json"
    _write_json(compilation_path, compilation)
    storyboard = build_storyboard(compilation, output_dir, background_video=background)
    storyboard_path = output_dir / "storyboard.json"
    _write_json(storyboard_path, storyboard)

    spoken = narration_text(compilation)
    spoken_path = output_dir / "spoken-preview.txt"
    spoken_path.write_text(spoken + "\n", encoding="utf-8")
    audio = output_dir / "system-voice-preview.wav"
    if audio_source is not None:
        source = audio_source.expanduser().resolve()
        if not source.is_file():
            raise RuntimeError("audio_source must be an existing local file")
        subprocess.run(
            [ffmpeg, "-y", "-v", "error", "-i", str(source), "-ar", "44100", "-ac", "2", str(audio)],
            check=True,
        )
    else:
        aiff = output_dir / "system-voice-preview.aiff"
        subprocess.run(
            [say, "-v", system_voice, "-r", "185", "-o", str(aiff), "-f", str(spoken_path)],
            check=True,
        )
        subprocess.run(
            [ffmpeg, "-y", "-v", "error", "-i", str(aiff), "-ar", "44100", "-ac", "2", str(audio)],
            check=True,
        )
    if not audio.is_file() or audio.stat().st_size <= 78:
        raise RuntimeError(
            "macOS system speech produced no audio; run the helper from an interactive local shell"
        )
    video = output_dir / "format-review.mp4"
    report = render_compilation(storyboard, output_dir, video, audio=audio)
    report.update({
        "proof_kind": "human_paced_synthetic_format_review",
        "source_selection_proven": False,
        "provider_called": False,
        "voice_kind": "macos_system_preview_not_production_voice",
        "system_voice": system_voice,
    })
    report_path = output_dir / "render-report.json"
    _write_json(report_path, report)
    return {
        "video": str(video),
        "report": str(report_path),
        "storyboard": str(storyboard_path),
        "audio": str(audio),
        "duration_sec": report["duration_sec"],
        "provider_called": False,
        "source_selection_proven": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--background", default=BACKGROUND_ASSET_PATH)
    parser.add_argument("--system-voice", default="Milena")
    parser.add_argument("--audio-source")
    args = parser.parse_args()
    print(json.dumps(build(
        Path(args.output_dir), Path(args.background), system_voice=args.system_voice,
        audio_source=Path(args.audio_source) if args.audio_source else None,
    ), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
