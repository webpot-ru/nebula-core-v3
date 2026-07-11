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
    normalize_voice_settings_json,
)


VOICE_SETTINGS_PROFILES: dict[str, dict[str, float] | None] = {
    "default": None,
    "natural": {"stability": 0.50, "similarity_boost": 0.75, "style": 0},
    "creative": {"stability": 0.35, "similarity_boost": 0.75, "style": 0},
    "robust": {"stability": 0.70, "similarity_boost": 0.75, "style": 0},
}


SAMPLE_TEXTS: dict[str, dict[str, dict[str, str]]] = {
    "neutral": {
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
    },
    "emotional": {
        "ru": {
            "narrator": "[curious] Сегодня у нас история с Reddit. Сначала это звучит как обычная ссора. Но потом появляется одна деталь... [whispers] и после нее вся история становится намного страннее.",
            "comment": "[sighs] Я бы на твоем месте остановился прямо здесь. Слишком много деталей не сходится.",
        },
        "en": {
            "narrator": "[curious] Today we have a Reddit story. At first, it sounds like a normal argument. But then one detail appears... [whispers] and after that, the whole story feels much darker.",
            "comment": "[sighs] I would stop right there. Way too many details in this story do not add up.",
        },
        "de": {
            "narrator": "[curious] Heute geht es um eine Reddit-Geschichte. Zuerst klingt alles wie ein normaler Streit. Aber dann taucht ein Detail auf... [whispers] und danach wirkt die ganze Geschichte viel unheimlicher.",
            "comment": "[sighs] Ich würde an deiner Stelle genau hier stoppen. In dieser Geschichte passt zu viel nicht zusammen.",
        },
        "es-419": {
            "narrator": "[curious] Hoy tenemos una historia de Reddit. Al principio parece una pelea normal. Pero luego aparece un detalle... [whispers] y desde ese momento todo se vuelve mucho más raro.",
            "comment": "[sighs] Yo me detendría justo ahí. Hay demasiadas cosas en esta historia que no cuadran.",
        },
        "pt-BR": {
            "narrator": "[curious] Hoje temos uma história do Reddit. No começo parece uma briga comum. Mas então aparece um detalhe... [whispers] e depois disso a história fica muito mais estranha.",
            "comment": "[sighs] Eu pararia exatamente aí. Tem detalhe demais nessa história que não fecha.",
        },
        "fr": {
            "narrator": "[curious] Aujourd'hui, on a une histoire de Reddit. Au début, ça ressemble à une dispute normale. Mais ensuite, un détail apparaît... [whispers] et après ça, toute l'histoire devient beaucoup plus étrange.",
            "comment": "[sighs] À ta place, je m'arrêterais là. Il y a beaucoup trop de détails qui ne collent pas.",
        },
        "it": {
            "narrator": "[curious] Oggi abbiamo una storia da Reddit. All'inizio sembra una lite normale. Poi però salta fuori un dettaglio... [whispers] e da lì tutta la storia diventa molto più strana.",
            "comment": "[sighs] Io mi fermerei proprio qui. In questa storia ci sono troppe cose che non tornano.",
        },
    },
}


def resolve_profile_voice_settings(args: argparse.Namespace) -> str | None:
    if args.voice_settings_json:
        return normalize_voice_settings_json(args.voice_settings_json)
    profile = VOICE_SETTINGS_PROFILES[args.voice_settings_profile]
    if profile is None:
        return None
    return normalize_voice_settings_json(json.dumps(profile, ensure_ascii=False))


def voice_settings_suffix(args: argparse.Namespace) -> str:
    return "custom" if args.voice_settings_json else args.voice_settings_profile


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


def sample_text_for(channel: dict[str, Any], role: str, text_style: str) -> str:
    lang = str(channel.get("lang") or "en")
    samples_for_style = SAMPLE_TEXTS.get(text_style) or SAMPLE_TEXTS["emotional"]
    texts = (
        samples_for_style.get(lang)
        or samples_for_style.get(lang.split("-", 1)[0])
        or samples_for_style["en"]
    )
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
        voice_settings_json=resolve_profile_voice_settings(args),
        tts_retries=args.tts_retries,
        tts_retry_delay=args.tts_retry_delay,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate short AI33 samples for narrator/comment voices.")
    parser.add_argument("--channels-json", default="channels.json")
    parser.add_argument("--channels", default="all", help="Comma-separated channel IDs, or all.")
    parser.add_argument("--output-dir", default="build/voice_samples")
    parser.add_argument("--model-id", default=AI33_TTS_MODEL_ID)
    parser.add_argument("--require-model-id", default="eleven_v3")
    parser.add_argument(
        "--text-style",
        choices=sorted(SAMPLE_TEXTS.keys()),
        default="emotional",
        help="Sample script style. emotional uses sparse Eleven v3 audio tags for expression checks.",
    )
    parser.add_argument(
        "--voice-settings-profile",
        choices=sorted(VOICE_SETTINGS_PROFILES.keys()),
        default="creative",
        help="Voice settings profile for the sample run. Use natural if creative is too unstable.",
    )
    parser.add_argument(
        "--voice-settings-json",
        help="Optional JSON object overriding --voice-settings-profile.",
    )
    parser.add_argument("--speed", type=float, default=1.0)
    parser.add_argument("--timeout", type=int, default=900)
    parser.add_argument("--poll-interval", type=int, default=5)
    parser.add_argument("--tts-retries", type=int, default=1)
    parser.add_argument("--tts-retry-delay", type=int, default=10)
    parser.add_argument("--with-transcript", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if args.require_model_id and args.model_id != args.require_model_id:
        raise Ai33Error(
            f"AI33 model preflight failed: required {args.require_model_id!r}, got {args.model_id!r}."
        )

    if args.tts_retries < 0:
        raise Ai33Error("--tts-retries must be 0 or greater.")
    if args.tts_retry_delay < 0:
        raise Ai33Error("--tts-retry-delay must be 0 or greater.")

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
        "required_model_id": args.require_model_id,
        "speed": args.speed,
        "text_style": args.text_style,
        "voice_settings_profile": voice_settings_suffix(args),
        "voice_settings_json": resolve_profile_voice_settings(args),
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
            text = sample_text_for(channel, role, args.text_style)
            file_name = (
                f"{channel_id}_{lang}_{role}_{voice_settings_suffix(args)}_"
                f"{args.text_style}_{voice_id}.mp3"
            ).replace("/", "-")
            output_path = output_dir / file_name
            sample_record = {
                "role": role,
                "voice_id": voice_id,
                "text": text,
                "text_style": args.text_style,
                "voice_settings_profile": voice_settings_suffix(args),
                "voice_settings_json": resolve_profile_voice_settings(args),
                "file": str(output_path),
            }
            channel_manifest["samples"].append(sample_record)
            if args.dry_run:
                settings_label = sample_record["voice_settings_profile"]
                print(f"DRY RUN {channel_id} {role} {voice_id} [{args.text_style}/{settings_label}]: {text}")
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
    try:
        raise SystemExit(main())
    except Ai33Error as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
