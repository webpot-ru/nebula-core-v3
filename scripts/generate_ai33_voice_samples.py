#!/usr/bin/env python3
"""Generate short AI33 TTS samples for configured channel voices."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from translator_tts import (
    AI33_TTS_MODEL_ID,
    Ai33Error,
    generate_tts_audio,
    get_api_key,
)


SAMPLE_TEXTS = {
    "ru": {
        "narrator": "Сегодня у нас история с Reddit: сначала все кажется обычной ссорой, но последняя деталь полностью меняет смысл.",
        "comment": "Я бы на твоем месте сразу остановился. В этой истории слишком много странных деталей.",
    },
    "en": {
        "narrator": "Today we have a Reddit story: at first it sounds like a normal argument, but the last detail changes everything.",
        "comment": "I would stop right there. This story has way too many strange details.",
    },
    "de": {
        "narrator": "Heute geht es um eine Reddit-Geschichte: zuerst klingt alles wie ein normaler Streit, aber das letzte Detail ändert alles.",
        "comment": "Ich würde an deiner Stelle sofort aufpassen. An dieser Geschichte sind zu viele Dinge seltsam.",
    },
    "es-419": {
        "narrator": "Hoy tenemos una historia de Reddit: al principio parece una pelea normal, pero el último detalle lo cambia todo.",
        "comment": "Yo me detendría justo ahí. En esta historia hay demasiados detalles raros.",
    },
    "pt-BR": {
        "narrator": "Hoje temos uma história do Reddit: no começo parece uma briga comum, mas o último detalhe muda tudo.",
        "comment": "Eu pararia exatamente aí. Essa história tem detalhes estranhos demais.",
    },
    "fr": {
        "narrator": "Aujourd'hui, on a une histoire de Reddit: au début, ça ressemble à une dispute normale, mais le dernier détail change tout.",
        "comment": "À ta place, je m'arrêterais tout de suite. Il y a beaucoup trop de détails étranges dans cette histoire.",
    },
    "it": {
        "narrator": "Oggi abbiamo una storia da Reddit: all'inizio sembra una lite normale, ma l'ultimo dettaglio cambia tutto.",
        "comment": "Io mi fermerei proprio lì. In questa storia ci sono troppi dettagli strani.",
    },
}


def load_channels(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    channels = data.get("channels")
    if not isinstance(channels, list):
        raise Ai33Error(f"{path} must contain a channels list.")
    return [channel for channel in channels if isinstance(channel, dict)]


def parse_channel_filter(value: str) -> set[str] | None:
    cleaned = [item.strip() for item in value.split(",") if item.strip()]
    if not cleaned or cleaned == ["all"]:
        return None
    return set(cleaned)


def sample_text_for(channel: dict[str, Any], role: str) -> str:
    lang = str(channel.get("lang") or "en")
    texts = SAMPLE_TEXTS.get(lang) or SAMPLE_TEXTS.get(lang.split("-", 1)[0]) or SAMPLE_TEXTS["en"]
    return texts[role]


def build_tts_args(args: argparse.Namespace) -> SimpleNamespace:
    return SimpleNamespace(
        model_id=args.model_id,
        speed=args.speed,
        with_transcript=args.with_transcript,
        context_chaining=False,
        receive_url=None,
        pronunciation_dictionary_id=None,
        no_poll=False,
        timeout=args.timeout,
        poll_interval=args.poll_interval,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate short AI33 samples for narrator/comment voices.")
    parser.add_argument("--channels-json", default="channels.json")
    parser.add_argument("--channels", default="all", help="Comma-separated channel IDs, or all.")
    parser.add_argument("--output-dir", default="build/voice_samples")
    parser.add_argument("--model-id", default=AI33_TTS_MODEL_ID)
    parser.add_argument("--speed", type=float, default=1.0)
    parser.add_argument("--timeout", type=int, default=900)
    parser.add_argument("--poll-interval", type=int, default=5)
    parser.add_argument("--with-transcript", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    selected = parse_channel_filter(args.channels)
    channels = load_channels(Path(args.channels_json))
    channels = [channel for channel in channels if selected is None or channel.get("id") in selected]
    if not channels:
        raise Ai33Error(f"No channels matched filter: {args.channels}")

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output_dir = Path(args.output_dir) / timestamp
    tts_args = build_tts_args(args)
    manifest: dict[str, Any] = {
        "generated_at": timestamp,
        "model_id": args.model_id,
        "speed": args.speed,
        "channels": [],
    }

    api_key = None if args.dry_run else get_api_key()
    for channel in channels:
        channel_id = str(channel.get("id") or "")
        lang = str(channel.get("lang") or "")
        voices = [
            ("narrator", channel.get("tts_voice")),
            ("comment", channel.get("comment_tts_voice")),
        ]
        channel_manifest = {
            "id": channel_id,
            "handle": channel.get("handle"),
            "name": channel.get("name"),
            "lang": lang,
            "samples": [],
        }
        for role, voice_id in voices:
            if not voice_id:
                raise Ai33Error(f"{channel_id} has no {role} voice configured.")
            text = sample_text_for(channel, role)
            file_name = f"{channel_id}_{lang}_{role}_{voice_id}.mp3".replace("/", "-")
            output_path = output_dir / file_name
            sample_record = {
                "role": role,
                "voice_id": voice_id,
                "text": text,
                "file": str(output_path),
            }
            channel_manifest["samples"].append(sample_record)
            if args.dry_run:
                print(f"DRY RUN {channel_id} {role} {voice_id}: {text}")
                continue
            output_path.parent.mkdir(parents=True, exist_ok=True)
            print(f"Generating {channel_id} {role}: voice_id={voice_id}, chars={len(text)}")
            generate_tts_audio(
                api_key=str(api_key),
                text=text,
                voice_id=str(voice_id),
                output_path=output_path,
                args=tts_args,
            )
        manifest["channels"].append(channel_manifest)

    if not args.dry_run:
        output_dir.mkdir(parents=True, exist_ok=True)
        manifest_path = output_dir / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"Saved voice sample manifest to {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
