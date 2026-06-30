import argparse
import base64
import binascii
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
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
    "pt": "Comentário de",
    "pt-BR": "Comentário de",
    "fr": "Commentaire de",
    "it": "Commento di",
}

LINK_PLACEHOLDERS = {
    "ru": "ссылка на экране",
    "en": "the link is on screen",
    "de": "den Link siehst du auf dem Bildschirm",
    "es": "el enlace está en pantalla",
    "es-419": "el enlace está en pantalla",
    "pt": "o link está na tela",
    "pt-BR": "o link está na tela",
    "fr": "le lien est affiché à l'écran",
    "it": "il link è sullo schermo",
}

URL_RE = re.compile(r"(?i)\b(?:https?://|www\.)[^\s<>)\]]+")
MARKDOWN_LINK_RE = re.compile(r"\[([^\]\n]{0,120})\]\(((?:https?://|www\.)[^\s)]+)\)")
GENERIC_LINK_LABELS = {
    "link", "here", "this", "source", "url", "proof", "screenshot",
    "enlace", "aquí", "esto", "fuente", "captura",
    "ссылка", "тут", "здесь", "источник", "скрин",
    "link", "hier", "quelle", "beweis",
    "lien", "ici", "source", "preuve",
    "link", "qui", "fonte", "prova",
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


def normalize_lang_code(value: str | None) -> str:
    return str(value or "").replace("_", "-").lower()


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


def load_optional_env_files(paths: list[str]) -> int:
    if not paths:
        return 0
    try:
        from vectorengine_client import load_dotenv_file
    except ImportError as exc:
        raise Ai33Error("vectorengine_client.py is required for --env-file support.") from exc
    return sum(1 for path in paths if load_dotenv_file(path))


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


def should_translate_story(story: dict[str, Any], lang_code: str, args: argparse.Namespace) -> bool:
    if args.skip_translation:
        return False

    normalized_target = normalize_lang_code(lang_code)
    if normalized_target.startswith("en"):
        return False

    localization = story.get("localization") if isinstance(story.get("localization"), dict) else {}
    existing_lang = (
        story.get("language")
        or story.get("localized_language")
        or localization.get("language")
        or localization.get("target_language")
    )
    if normalize_lang_code(existing_lang) == normalized_target and not args.force_translation:
        return False

    return True


def build_translation_prompt(story: dict[str, Any], channel: dict[str, Any], lang_code: str) -> str:
    comments = [
        {
            "index": index,
            "username": str(comment.get("username") or f"u/commenter_{index + 1}"),
            "body": str(comment.get("body") or ""),
        }
        for index, comment in enumerate(story.get("comments") or [])
        if isinstance(comment, dict)
    ]
    payload = {
        "title": story.get("title") or "",
        "body": story.get("body") or "",
        "comments": comments,
    }
    translate_prompt = channel.get("translate_prompt") or "Translate naturally for native speakers."
    channel_name = channel.get("name") or channel.get("handle") or channel.get("id") or "channel"
    return f"""
Translate the Reddit story text for a narrated YouTube video.

Target:
- channel: {channel_name}
- language code: {lang_code}
- region: {channel.get('region', '')}
- audience: {channel.get('audience', '')}
- localization instruction: {translate_prompt}

Rules:
- Translate only the story title, story body, and each comment body.
- Preserve Reddit usernames, subreddit names, URLs, numbers, and factual details.
- Keep the same point of view, sequence of events, emotional intensity, and informal Reddit style.
- Do not summarize, censor, add explanations, or invent facts.
- Keep line breaks only where they help natural narration.
- Return strict JSON only, with exactly this shape:
{{
  "title": "translated title",
  "body": "translated body",
  "comments": [
    {{"index": 0, "body": "translated comment body"}}
  ],
  "language": "{lang_code}"
}}

Source story JSON:
{json.dumps(payload, ensure_ascii=False, indent=2)}
""".strip()


def apply_translated_fields(
    story: dict[str, Any],
    translated_fields: dict[str, Any],
    *,
    channel: dict[str, Any],
    lang_code: str,
    model: str,
) -> dict[str, Any]:
    localized = dict(story)

    translated_title = str(translated_fields.get("title") or story.get("title") or "").strip()
    translated_body = str(translated_fields.get("body") or story.get("body") or "").strip()
    if translated_title:
        localized["title"] = translated_title
    if translated_body:
        localized["body"] = translated_body

    translated_by_index: dict[int, str] = {}
    for fallback_index, item in enumerate(translated_fields.get("comments") or []):
        if not isinstance(item, dict):
            continue
        try:
            index = int(item.get("index", fallback_index))
        except (TypeError, ValueError):
            index = fallback_index
        body = str(item.get("body") or "").strip()
        if body:
            translated_by_index[index] = body

    localized_comments = []
    for index, comment in enumerate(story.get("comments") or []):
        if not isinstance(comment, dict):
            continue
        copied = dict(comment)
        if index in translated_by_index:
            copied["body"] = translated_by_index[index]
        localized_comments.append(copied)
    localized["comments"] = localized_comments

    source_language = (
        story.get("source_language")
        or story.get("original_language")
        or ("en" if normalize_lang_code(story.get("language")) != normalize_lang_code(lang_code) else story.get("language"))
        or "en"
    )
    localized["source_language"] = source_language
    localized["language"] = lang_code
    localized["localized_language"] = lang_code
    localized["localization"] = {
        "source": "vectorengine-gemini",
        "model": model,
        "language": lang_code,
        "channelId": channel.get("id"),
        "channelHandle": channel.get("handle"),
        "translated_at": datetime.now(timezone.utc).isoformat(),
    }
    return localized


def translate_story_text(
    story: dict[str, Any],
    *,
    channel: dict[str, Any],
    lang_code: str,
    model: str,
    temperature: float,
) -> dict[str, Any]:
    try:
        from vectorengine_client import VectorEngineError, call_gemini_json
    except ImportError as exc:
        raise Ai33Error("vectorengine_client.py is required for story translation.") from exc

    try:
        translated_fields = call_gemini_json(
            prompt=build_translation_prompt(story, channel, lang_code),
            model=model,
            temperature=temperature,
            max_output_tokens=4096,
        )
    except VectorEngineError as exc:
        raise Ai33Error(f"VectorEngine Gemini translation failed: {exc}") from exc

    return apply_translated_fields(
        story,
        translated_fields,
        channel=channel,
        lang_code=lang_code,
        model=model,
    )


def save_story(story: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(story, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def localized_link_placeholder(lang_code: str) -> str:
    return LINK_PLACEHOLDERS.get(lang_code) or LINK_PLACEHOLDERS.get(lang_code[:2]) or LINK_PLACEHOLDERS["en"]


def normalize_link_label(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip()).casefold()


def clean_text_for_narration_and_karaoke(text: Any, lang_code: str) -> tuple[str, int]:
    original = str(text or "")
    if not original:
        return "", 0

    placeholder = localized_link_placeholder(lang_code)
    changes = 0

    def replace_markdown(match: re.Match[str]) -> str:
        nonlocal changes
        changes += 1
        label = re.sub(r"\s+", " ", match.group(1).strip())
        if not label or normalize_link_label(label) in GENERIC_LINK_LABELS:
            return placeholder
        return f"{label} ({placeholder})"

    cleaned = MARKDOWN_LINK_RE.sub(replace_markdown, original)

    def replace_url(_: re.Match[str]) -> str:
        nonlocal changes
        changes += 1
        return placeholder

    cleaned = URL_RE.sub(replace_url, cleaned)
    escaped_placeholder = re.escape(placeholder)
    service_prefixes = (
        r"original\s+(?:thread|post|source)|reddit\s+thread|source|link|url|"
        r"enlace|fuente|ссылка|источник|quelle|lien|fonte"
    )
    cleaned = re.sub(
        rf"(?im)^\s*(?:{service_prefixes})\s*:?\s*{escaped_placeholder}\s*$",
        placeholder,
        cleaned,
    )
    cleaned = re.sub(
        rf"(?:{escaped_placeholder})(?:[\s,.;:!?-]+{escaped_placeholder})+",
        placeholder,
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
    return cleaned, changes


def sanitize_story_for_narration_and_karaoke(
    story: dict[str, Any],
    lang_code: str,
) -> tuple[dict[str, Any], int]:
    sanitized = dict(story)
    total_changes = 0

    for field in ("title", "body"):
        cleaned, changes = clean_text_for_narration_and_karaoke(sanitized.get(field), lang_code)
        if changes:
            sanitized[field] = cleaned
            total_changes += changes

    comments = []
    for comment in story.get("comments") or []:
        if not isinstance(comment, dict):
            continue
        copied = dict(comment)
        cleaned, changes = clean_text_for_narration_and_karaoke(copied.get("body"), lang_code)
        if changes:
            copied["body"] = cleaned
            total_changes += changes
        comments.append(copied)
    if comments:
        sanitized["comments"] = comments

    if total_changes:
        sanitized["narration_sanitization"] = {
            "version": 1,
            "source": "translator_tts",
            "language": lang_code,
            "link_placeholder": localized_link_placeholder(lang_code),
            "changes": total_changes,
            "sanitized_at": datetime.now(timezone.utc).isoformat(),
        }
    return sanitized, total_changes


def resolve_lang_and_voice(args: argparse.Namespace) -> tuple[str, str]:
    channel = load_channel_config(args.channel or args.target)
    if channel:
        lang = channel.get("lang") or args.target
        voice_id = args.voice_id or channel.get("tts_voice") or VOICE_IDS.get(lang)
        return lang, normalize_voice_id(voice_id)

    lang = args.target
    voice_id = args.voice_id or VOICE_IDS.get(lang)
    return lang, normalize_voice_id(voice_id)


def build_narration_text(story: dict[str, Any], lang_code: str, include_comment_labels: bool = False) -> str:
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
            if include_comment_labels:
                parts.append(f"{comment_label} {username}: {comment_body}")
            else:
                parts.append(comment_body)

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
    loaded_env_files = load_optional_env_files(args.env_file)
    lang_code, voice_id = resolve_lang_and_voice(args)
    channel = load_channel_config(args.channel or args.target) or {"lang": lang_code}
    story_path = Path(args.story).resolve()
    output_path = Path(args.output or f"narration_{lang_code}.mp3").resolve()

    story = load_story(story_path)
    translation_needed = should_translate_story(story, lang_code, args)
    translated_story_path = Path(args.translated_story_output).resolve() if args.translated_story_output else story_path

    if translation_needed and not args.dry_run:
        story = translate_story_text(
            story,
            channel=channel,
            lang_code=lang_code,
            model=args.translation_model,
            temperature=args.translation_temperature,
        )

    sanitization_changes = 0
    if not args.preserve_raw_links:
        story, sanitization_changes = sanitize_story_for_narration_and_karaoke(story, lang_code)

    if not args.dry_run and (translation_needed or sanitization_changes):
        save_story(story, translated_story_path)
        action = "localized" if translation_needed else "narration-safe"
        print(f"Saved {action} story text to {translated_story_path}")
        if sanitization_changes:
            print(f"Sanitized {sanitization_changes} link/service token(s) for narration/karaoke.")

    narration_text = build_narration_text(story, lang_code, args.include_comment_labels)

    if args.dry_run:
        print("AI33 TTS dry run")
        print(f"  story: {story_path}")
        print(f"  language: {lang_code}")
        print(f"  voice_id: {voice_id}")
        print(f"  translation: {'needed' if translation_needed else 'skipped'}")
        print(f"  translation_model: {args.translation_model}")
        print(f"  narration_sanitization_changes: {sanitization_changes}")
        print(f"  model_id: {args.model_id or '(omitted)'}")
        print(f"  output: {output_path}")
        print(f"  characters: {len(narration_text)}")
        print(f"  speed: {args.speed:g}")
        print(f"  poll: {not args.no_poll}")
        print(f"  loadedEnvFileCount: {loaded_env_files}")
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
    parser.add_argument(
        "--translated-story-output",
        help="Where to save localized story JSON. Default: overwrite --story when translation runs.",
    )
    parser.add_argument(
        "--skip-translation",
        action="store_true",
        help="Do not translate story text before TTS/storyboard handoff.",
    )
    parser.add_argument(
        "--force-translation",
        action="store_true",
        help="Translate even if story metadata already says it is localized for the target language.",
    )
    parser.add_argument("--translation-model", default="gemini-3.5-flash", help="VectorEngine Gemini model for story localization.")
    parser.add_argument("--translation-temperature", type=float, default=0.2, help="Gemini temperature for story localization.")
    parser.add_argument("--env-file", action="append", default=[], help="Optional env file to load before VectorEngine/AI33 calls.")
    parser.add_argument("--voice-id", help="AI33 prefixed voice_id from Voice Library.")
    parser.add_argument(
        "--include-comment-labels",
        action="store_true",
        help="Include localized 'Comment by user' labels in narration. Default keeps audio aligned to visible card/comment text for karaoke.",
    )
    parser.add_argument(
        "--preserve-raw-links",
        action="store_true",
        help="Keep raw URLs in story text and narration. Default replaces URLs with localized on-screen-link phrases.",
    )
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
