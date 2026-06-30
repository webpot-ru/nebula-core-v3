import argparse
import base64
import binascii
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import requests


AI33_API_BASE = os.environ.get("AI33_API_BASE", "https://api.ai33.pro").rstrip("/")
AI33_TTS_URL = os.environ.get(
    "AI33_TTS_URL",
    f"{AI33_API_BASE}/v3/text-to-speech",
)
AI33_TTS_MODEL_ID = os.environ.get("AI33_TTS_MODEL_ID", "eleven_v3")
AI33_TASK_URL_TEMPLATE = os.environ.get(
    "AI33_TASK_URL_TEMPLATE",
    f"{AI33_API_BASE}/v3/task/{{task_id}}",
)
AI33_TASK_AUTH_HEADER = os.environ.get("AI33_TASK_AUTH_HEADER", "Authorization")

VOICE_PREFIXES = ("elevenlabs_", "minimax_", "clone_", "edge_", "kokoro_")

VOICE_IDS = {
    "ru": "edge_ru-RU-DmitryNeural",
    "en": "edge_en-US-ChristopherNeural",
    "de": "edge_de-DE-ConradNeural",
    "es": "edge_es-MX-JorgeNeural",
    "es-419": "edge_es-MX-JorgeNeural",
    "pt": "edge_pt-BR-AntonioNeural",
    "pt-BR": "edge_pt-BR-AntonioNeural",
    "fr": "edge_fr-FR-HenriNeural",
    "it": "edge_it-IT-DiegoNeural",
}

COMMENT_LABELS = {
    "ru": "Комментарий от",
    "en": "Comment by",
    "de": "Kommentar von",
    "es": "Comentario de",
    "es-419": "Comentario de",
    "pt": "Comentario de",
    "pt-BR": "Comentario de",
    "fr": "Commentaire de",
    "it": "Commento di",
}

AUDIO_URL_KEYS = {
    "audio_url",
    "file_url",
    "download_url",
    "output_url",
    "result_url",
    "media_url",
    "mp3_url",
    "wav_url",
}

AUDIO_BASE64_KEYS = {
    "audio_base64",
    "base64_audio",
    "audio",
    "file_base64",
}


class Ai33Error(RuntimeError):
    pass


def get_api_key() -> str:
    """Read the AI33 key from env without printing or persisting it."""
    key = os.environ.get("AI33_API_KEY") or os.environ.get("A133_API_KEY")
    if not key:
        raise Ai33Error(
            "Missing AI33_API_KEY. Add it to the local environment or GitHub "
            "Secrets. A133_API_KEY is accepted only as a compatibility fallback."
        )
    return key


def load_channel_config(channel_id: str | None) -> dict[str, Any] | None:
    if not channel_id:
        return None

    config_path = Path(__file__).with_name("channels.json")
    if not config_path.exists():
        return None

    with config_path.open("r", encoding="utf-8") as f:
        channels = json.load(f).get("channels", [])

    for channel in channels:
        if channel.get("id") == channel_id or channel.get("handle") == channel_id:
            return channel
    return None


def load_story(story_path: Path) -> dict[str, Any]:
    if not story_path.exists():
        raise Ai33Error(f"Story data file not found: {story_path}. Run scraper.py first.")

    with story_path.open("r", encoding="utf-8") as f:
        return json.load(f)


def normalize_voice_id(voice_id: str) -> str:
    if not voice_id:
        raise Ai33Error("No AI33 voice_id configured.")
    if not voice_id.startswith(VOICE_PREFIXES):
        prefixes = ", ".join(VOICE_PREFIXES)
        raise Ai33Error(
            f"AI33 voice_id must start with one of: {prefixes}. Got: {voice_id}"
        )
    return voice_id


def resolve_lang_and_voice(args: argparse.Namespace) -> tuple[str, str]:
    channel = load_channel_config(args.channel or args.target)
    if channel:
        lang = channel.get("lang") or args.target
        voice_id = args.voice_id or channel.get("tts_voice") or VOICE_IDS.get(lang)
        return lang, normalize_voice_id(voice_id)

    lang = args.target
    voice_id = args.voice_id or VOICE_IDS.get(lang)
    return lang, normalize_voice_id(voice_id)


def build_narration_text(story: dict[str, Any], lang_code: str) -> str:
    parts: list[str] = []
    title = (story.get("title") or "").strip()
    body = (story.get("body") or "").strip()

    if title:
        parts.append(title)
    if body:
        parts.append(body)

    comment_label = COMMENT_LABELS.get(lang_code, COMMENT_LABELS.get(lang_code[:2], "Comment by"))
    for comment in story.get("comments", []):
        username = (comment.get("username") or "user").strip()
        comment_body = (comment.get("body") or "").strip()
        if comment_body:
            parts.append(f"{comment_label} {username}: {comment_body}")

    narration_text = "\n\n".join(parts).strip()
    if not narration_text:
        raise Ai33Error("story_data.json does not contain title, body, or comments text.")
    return narration_text


def bool_form(value: bool) -> str:
    return "true" if value else "false"


def safe_response_text(response: requests.Response, limit: int = 600) -> str:
    text = response.text.strip()
    if len(text) > limit:
        return text[:limit] + "..."
    return text


def request_json(response: requests.Response, context: str) -> dict[str, Any]:
    try:
        return response.json()
    except ValueError as exc:
        raise Ai33Error(f"{context} returned non-JSON response: {safe_response_text(response)}") from exc


def post_tts_task(
    *,
    api_key: str,
    text: str,
    voice_id: str,
    model_id: str | None,
    speed: float,
    file_name: str,
    with_transcript: bool,
    context_chaining: bool,
    receive_url: str | None,
    pronunciation_dictionary_id: int | None,
) -> dict[str, Any]:
    fields: dict[str, str] = {
        "text": text,
        "voice_id": voice_id,
        "speed": f"{speed:g}",
        "with_transcript": bool_form(with_transcript),
        "context_chaining": bool_form(context_chaining),
        "file_name": file_name,
    }
    if model_id:
        fields["model_id"] = model_id
    if receive_url:
        fields["receive_url"] = receive_url
    if pronunciation_dictionary_id is not None:
        fields["pronunciation_dictionary_id"] = str(pronunciation_dictionary_id)

    multipart = {key: (None, value) for key, value in fields.items()}
    response = requests.post(
        AI33_TTS_URL,
        headers={"xi-api-key": api_key},
        files=multipart,
        timeout=60,
    )

    content_type = response.headers.get("content-type", "")
    if response.ok and content_type.startswith("audio/"):
        return {"success": True, "audio_bytes": response.content}

    if not response.ok:
        raise Ai33Error(
            f"AI33 TTS request failed ({response.status_code}): "
            f"{safe_response_text(response)}"
        )

    payload = request_json(response, "AI33 TTS request")
    if not payload.get("success", False):
        raise Ai33Error(f"AI33 TTS request was not successful: {json.dumps(payload)[:600]}")
    return payload


def find_first_key(payload: Any, keys: set[str]) -> Any:
    if isinstance(payload, dict):
        for key, value in payload.items():
            if key in keys and value:
                return value
        for value in payload.values():
            found = find_first_key(value, keys)
            if found:
                return found
    elif isinstance(payload, list):
        for item in payload:
            found = find_first_key(item, keys)
            if found:
                return found
    return None


def find_audio_url(payload: Any) -> str | None:
    value = find_first_key(payload, AUDIO_URL_KEYS)
    if isinstance(value, str) and value.startswith(("http://", "https://")):
        return value

    # Some task APIs use a generic "url" field inside a result object.
    generic_url = find_first_key(payload, {"url"})
    if isinstance(generic_url, str) and generic_url.startswith(("http://", "https://")):
        lowered = generic_url.lower()
        if lowered.endswith((".mp3", ".wav", ".m4a", ".ogg")):
            return generic_url
    return None


def find_audio_base64(payload: Any) -> str | None:
    value = find_first_key(payload, AUDIO_BASE64_KEYS)
    if isinstance(value, str) and len(value) > 100:
        return value
    return None


def write_audio_from_payload(payload: dict[str, Any], output_path: Path, api_key: str) -> bool:
    audio_bytes = payload.get("audio_bytes")
    if isinstance(audio_bytes, bytes):
        output_path.write_bytes(audio_bytes)
        return True

    audio_base64 = find_audio_base64(payload)
    if audio_base64:
        if "," in audio_base64 and audio_base64.split(",", 1)[0].startswith("data:"):
            audio_base64 = audio_base64.split(",", 1)[1]
        try:
            output_path.write_bytes(base64.b64decode(audio_base64, validate=True))
            return True
        except binascii.Error:
            pass

    audio_url = find_audio_url(payload)
    if audio_url:
        response = requests.get(audio_url, headers={"xi-api-key": api_key}, timeout=120)
        if not response.ok:
            raise Ai33Error(
                f"AI33 audio download failed ({response.status_code}): "
                f"{safe_response_text(response)}"
            )
        output_path.write_bytes(response.content)
        return True

    return False


def get_task_payload(api_key: str, task_id: str) -> dict[str, Any]:
    task_url = AI33_TASK_URL_TEMPLATE.format(task_id=task_id)
    response = requests.get(task_url, headers={AI33_TASK_AUTH_HEADER: api_key}, timeout=60)
    if not response.ok:
        raise Ai33Error(
            f"AI33 task polling failed ({response.status_code}) at {task_url}: "
            f"{safe_response_text(response)}"
        )
    return request_json(response, "AI33 task polling")


def task_status(payload: dict[str, Any]) -> str:
    value = find_first_key(payload, {"status", "state"})
    return str(value or "").lower()


def poll_for_audio(
    *,
    api_key: str,
    task_id: str,
    output_path: Path,
    timeout_seconds: int,
    poll_interval: int,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    last_payload: dict[str, Any] = {}

    while time.monotonic() < deadline:
        last_payload = get_task_payload(api_key, task_id)
        if write_audio_from_payload(last_payload, output_path, api_key):
            return last_payload

        status = task_status(last_payload)
        if status in {"failed", "failure", "error", "cancelled", "canceled"}:
            raise Ai33Error(f"AI33 task failed: {json.dumps(last_payload)[:800]}")

        time.sleep(poll_interval)

    raise Ai33Error(
        f"Timed out waiting for AI33 task {task_id}. Last payload: "
        f"{json.dumps(last_payload)[:800]}"
    )


def process_story_audio(args: argparse.Namespace) -> None:
    lang_code, voice_id = resolve_lang_and_voice(args)
    story_path = Path(args.story).resolve()
    output_path = Path(args.output or f"narration_{lang_code}.mp3").resolve()

    story = load_story(story_path)
    narration_text = build_narration_text(story, lang_code)

    if args.dry_run:
        print("AI33 TTS dry run")
        print(f"  story: {story_path}")
        print(f"  language: {lang_code}")
        print(f"  voice_id: {voice_id}")
        print(f"  model_id: {args.model_id or '(omitted)'}")
        print(f"  output: {output_path}")
        print(f"  characters: {len(narration_text)}")
        print(f"  speed: {args.speed:g}")
        print(f"  poll: {not args.no_poll}")
        return

    api_key = get_api_key()
    print(f"Submitting AI33 TTS task: voice_id={voice_id}, chars={len(narration_text)}")
    payload = post_tts_task(
        api_key=api_key,
        text=narration_text,
        voice_id=voice_id,
        model_id=args.model_id,
        speed=args.speed,
        file_name=output_path.name,
        with_transcript=args.with_transcript,
        context_chaining=args.context_chaining,
        receive_url=args.receive_url,
        pronunciation_dictionary_id=args.pronunciation_dictionary_id,
    )

    if write_audio_from_payload(payload, output_path, api_key):
        print(f"Saved audio to {output_path}")
        if args.with_transcript:
            transcript_path = output_path.with_suffix(".json")
            transcript_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"Saved task transcript/metadata to {transcript_path}")
        return

    task_id = payload.get("task_id")
    if not task_id:
        raise Ai33Error(f"AI33 response did not include audio or task_id: {json.dumps(payload)[:800]}")

    print(f"AI33 task_id={task_id}")
    if args.no_poll:
        task_path = output_path.with_suffix(".ai33-task.json")
        task_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Polling disabled. Saved task metadata to {task_path}")
        return

    payload = poll_for_audio(
        api_key=api_key,
        task_id=task_id,
        output_path=output_path,
        timeout_seconds=args.timeout,
        poll_interval=args.poll_interval,
    )
    print(f"Saved audio to {output_path}")

    if args.with_transcript:
        transcript_path = output_path.with_suffix(".json")
        transcript_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Saved task transcript/metadata to {transcript_path}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate narration audio through AI33 TTS v3.")
    parser.add_argument(
        "target",
        nargs="?",
        default="es",
        help="Language code (es, ru, en...) or channels.json channel id (acc1...).",
    )
    parser.add_argument("--channel", "-c", help="Channel id/handle from channels.json.")
    parser.add_argument("--story", default="story_data.json", help="Input story JSON path.")
    parser.add_argument("--output", "-o", help="Output audio file path.")
    parser.add_argument("--voice-id", help="AI33 prefixed voice_id from Voice Library.")
    parser.add_argument(
        "--model-id",
        default=AI33_TTS_MODEL_ID,
        help="AI33/ElevenLabs model_id sent with TTS requests (default: eleven_v3).",
    )
    parser.add_argument("--speed", type=float, default=1.0, help="AI33 speed, 0.5 to 1.5.")
    parser.add_argument("--with-transcript", action="store_true", help="Request transcript metadata.")
    parser.add_argument(
        "--context-chaining",
        action="store_true",
        help="Enable AI33 context chaining (+50 percent credits).",
    )
    parser.add_argument("--receive-url", help="Optional AI33 webhook receive_url.")
    parser.add_argument(
        "--pronunciation-dictionary-id",
        type=int,
        help="Optional AI33 pronunciation_dictionary_id.",
    )
    parser.add_argument("--no-poll", action="store_true", help="Submit only and save task metadata.")
    parser.add_argument("--timeout", type=int, default=900, help="Polling timeout in seconds.")
    parser.add_argument("--poll-interval", type=int, default=5, help="Polling interval in seconds.")
    parser.add_argument("--dry-run", action="store_true", help="Validate inputs without calling AI33.")
    return parser


if __name__ == "__main__":
    try:
        parsed_args = build_parser().parse_args()
        if not 0.5 <= parsed_args.speed <= 1.5:
            raise Ai33Error("--speed must be between 0.5 and 1.5.")
        process_story_audio(parsed_args)
    except Ai33Error as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
