import argparse
import json
import sys
from pathlib import Path
from typing import Any

from vectorengine_client import (
    DEFAULT_GEMINI_MODEL,
    VectorEngineError,
    call_gemini_json,
    gemini_source_label,
    load_dotenv_file,
    resolve_gemini_provider,
)


DEFAULT_OUTPUT = "youtube_metadata.json"


def clip_text(value: str, limit: int) -> str:
    value = " ".join(str(value or "").split()).strip()
    if len(value) <= limit:
        return value
    clipped = value[: max(0, limit - 1)].rstrip()
    if " " in clipped:
        clipped = clipped.rsplit(" ", 1)[0].rstrip()
    return f"{clipped}..."


def sanitize_reason(reason: str | None, limit: int = 360) -> str:
    return clip_text(str(reason or "").replace("\n", " "), limit)


def load_json(path: str | Path) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as f:
        return json.load(f)


def load_channel(channel_id: str | None) -> dict[str, Any]:
    data = load_json(Path(__file__).with_name("channels.json"))
    channels = data.get("channels", [])
    if not channels:
        raise VectorEngineError("channels.json has no channels.")

    if channel_id:
        for channel in channels:
            if channel.get("id") == channel_id or channel.get("handle") == channel_id:
                return channel
        raise VectorEngineError(f"Channel not found in channels.json: {channel_id}")

    return channels[0]


def story_excerpt(story: dict[str, Any], limit: int = 2400) -> str:
    parts = [
        f"Subreddit: {story.get('subreddit', '')}",
        f"Title: {story.get('title', '')}",
        f"Author: {story.get('author', '')}",
        f"Upvotes: {story.get('upvotes', '')}",
        f"Comments: {story.get('comments_count', '')}",
        "",
        str(story.get("body", "")),
    ]
    comments = story.get("comments") or []
    if comments:
        parts.append("\nTop comments:")
        for comment in comments[:3]:
            parts.append(f"- {comment.get('username', 'user')}: {comment.get('body', '')}")
    text = "\n".join(parts).strip()
    return text[:limit]


def producer_packaging_context(story: dict[str, Any]) -> str:
    adaptation = story.get("editorial_adaptation")
    if isinstance(adaptation, dict):
        adaptation = {
            key: value
            for key, value in adaptation.items()
            if key not in {"source_snapshot"}
        }
    fields = {
        "format_intent": story.get("format_intent"),
        "content_bet": story.get("content_bet"),
        "producer_score": story.get("producer_score"),
        "producer_angle": story.get("producer_angle"),
        "first_screen_promise": story.get("first_screen_promise"),
        "first_screen_text": story.get("first_screen_text"),
        "packaging_thesis": story.get("packaging_thesis"),
        "shorts_cut": story.get("shorts_cut"),
        "longform_angle": story.get("longform_angle"),
        "hook_evidence": story.get("hook_evidence"),
        "editorial_adaptation": adaptation,
    }
    compact = {key: value for key, value in fields.items() if value not in (None, "", [], {})}
    return json.dumps(compact, ensure_ascii=False, indent=2) if compact else "{}"


def build_prompt(story: dict[str, Any], channel: dict[str, Any]) -> str:
    language = channel.get("lang", "en")
    channel_name = channel.get("name") or channel.get("handle") or channel.get("id")
    niche = channel.get("niche_label") or channel.get("niche")
    translate_prompt = channel.get("translate_prompt") or "Keep natural native phrasing."
    return f"""
Create YouTube packaging metadata for a Reddit story video.

Channel:
- id: {channel.get('id')}
- handle: {channel.get('handle')}
- name: {channel_name}
- output language: {language}
- region: {channel.get('region')}
- audience: {channel.get('audience')}
- niche: {niche}
- localization instruction: {translate_prompt}

Story:
{story_excerpt(story)}

Requirements:
- Return strict JSON only.
- Localize title, description, hashtags, and thumbnail text to the channel language.
- Do not invent facts outside the story.
- Treat Reddit metrics as support, not the packaging idea.
- Generate 3 honest packaging options. Each option must be backed by the story/adaptation context and must not imply a twist that is not in source text.
- Choose one option as selected_option_index.
- Keep youtube_title under 95 characters.
- Keep thumbnail_text punchy: 2 short lines max, no more than 32 characters total if possible.
- Description must include the original Reddit URL if present.
- Use SEO keywords naturally, not as spam. Tags are secondary; title, thumbnail text, and first-screen promise matter more.
- Tags must be plain strings without # and suitable for YouTube tags.
- Hashtags must include # and be suitable for the description.
- Thumbnail prompt must be a visual prompt for a dramatic YouTube thumbnail, with no copyrighted characters.
- Flag risks such as too graphic, privacy, self-harm, hate, medical, legal, or sexual content.

Producer packaging context:
{producer_packaging_context(story)}

JSON shape:
{{
  "youtube_title": "string",
  "youtube_description": "string",
  "tags": ["string"],
  "hashtags": ["#string"],
  "thumbnail_text": "string",
  "thumbnail_prompt": "string",
  "seo_keywords": ["string"],
  "packaging_options": [
    {{
      "youtube_title": "string",
      "thumbnail_text": "string",
      "first_screen_promise": "string",
      "why_click": "string",
      "source_backing": "string"
    }}
  ],
  "selected_option_index": 0,
  "risk_flags": ["string"],
  "language": "{language}",
  "source_notes": "string"
}}
""".strip()


def normalized_packaging_options(metadata: dict[str, Any]) -> list[dict[str, str]]:
    options = []
    for item in metadata.get("packaging_options") or []:
        if not isinstance(item, dict):
            continue
        option = {
            "youtube_title": str(item.get("youtube_title") or "").strip()[:100],
            "thumbnail_text": str(item.get("thumbnail_text") or "").strip()[:80],
            "first_screen_promise": str(item.get("first_screen_promise") or "").strip()[:240],
            "why_click": str(item.get("why_click") or "").strip()[:240],
            "source_backing": str(item.get("source_backing") or "").strip()[:240],
        }
        if option["youtube_title"] or option["thumbnail_text"]:
            options.append(option)
    return options[:3]


def selected_packaging_option(metadata: dict[str, Any], options: list[dict[str, str]]) -> dict[str, str] | None:
    if not options:
        return None
    try:
        index = int(metadata.get("selected_option_index", 0))
    except (TypeError, ValueError):
        index = 0
    if index < 0 or index >= len(options):
        index = 0
    return options[index]


def selected_packaging_index(metadata: dict[str, Any], options: list[dict[str, str]]) -> int | None:
    if not options:
        return None
    try:
        index = int(metadata.get("selected_option_index", 0))
    except (TypeError, ValueError):
        index = 0
    if index < 0 or index >= len(options):
        index = 0
    return index


def normalize_metadata(
    metadata: dict[str, Any],
    *,
    story: dict[str, Any],
    channel: dict[str, Any],
    model: str,
    source: str,
    key_name: str | None,
) -> dict[str, Any]:
    packaging_options = normalized_packaging_options(metadata)
    selected_option = selected_packaging_option(metadata, packaging_options)
    selected_index = selected_packaging_index(metadata, packaging_options)
    title = str(
        metadata.get("youtube_title")
        or (selected_option or {}).get("youtube_title")
        or story.get("title")
        or "Reddit Story"
    ).strip()
    description = str(metadata.get("youtube_description") or "").strip()
    if story.get("url") and story["url"] not in description:
        description = f"{description}\n\nOriginal thread: {story['url']}".strip()

    tags = [str(tag).strip().lstrip("#") for tag in metadata.get("tags", []) if str(tag).strip()]
    hashtags = [str(tag).strip() for tag in metadata.get("hashtags", []) if str(tag).strip()]
    hashtags = [tag if tag.startswith("#") else f"#{tag}" for tag in hashtags]

    return {
        "source": source,
        "model": model,
        "keyName": key_name,
        "channelId": channel.get("id"),
        "channelHandle": channel.get("handle"),
        "language": metadata.get("language") or channel.get("lang"),
        "youtube_title": title[:100],
        "youtube_description": description[:5000],
        "tags": tags[:25],
        "hashtags": hashtags[:6],
        "thumbnail_text": str(
            metadata.get("thumbnail_text")
            or (selected_option or {}).get("thumbnail_text")
            or ""
        ).strip()[:80],
        "thumbnail_prompt": str(metadata.get("thumbnail_prompt") or "").strip(),
        "packaging_options": packaging_options,
        "selected_option_index": selected_index,
        "first_screen_promise": str(
            metadata.get("first_screen_promise")
            or (selected_option or {}).get("first_screen_promise")
            or story.get("first_screen_promise")
            or ""
        ).strip()[:240],
        "seo_keywords": [
            str(keyword).strip()
            for keyword in metadata.get("seo_keywords", [])
            if str(keyword).strip()
        ][:20],
        "risk_flags": [
            str(flag).strip()
            for flag in metadata.get("risk_flags", [])
            if str(flag).strip()
        ][:12],
        "source_notes": str(metadata.get("source_notes") or "").strip(),
    }


def fallback_labels(channel: dict[str, Any]) -> dict[str, Any]:
    lang = str(channel.get("lang") or "en").lower()
    if lang.startswith("ru"):
        return {
            "fallback_title": "История с Reddit",
            "thumbnail_text": "РЕШИЛИ ЖЕСТКО",
            "original_thread": "Оригинальная ветка",
            "hashtags": ["#реддит", "#история", "#shorts"],
            "tags": ["реддит", "истории реддит", "жизненная история", "моральная дилемма", "shorts"],
            "seo": ["история reddit", "реддит истории", "моральная дилемма"],
            "why_click": "Резервная упаковка без Gemini после блокировки metadata prompt.",
            "source_notes": "Резервные metadata созданы без Gemini после ошибки упаковки.",
        }
    if lang.startswith("es"):
        return {
            "fallback_title": "Historia de Reddit",
            "thumbnail_text": "SE PASARON",
            "original_thread": "Hilo original",
            "hashtags": ["#reddit", "#historias", "#shorts"],
            "tags": ["reddit", "historias de reddit", "historia viral", "dilema moral", "shorts"],
            "seo": ["historia reddit", "historias de reddit", "dilema moral"],
            "why_click": "Empaque de reserva sin Gemini tras un bloqueo del prompt de metadata.",
            "source_notes": "Metadata de reserva creada sin Gemini tras un error de empaque.",
        }
    if lang.startswith("pt"):
        return {
            "fallback_title": "Historia do Reddit",
            "thumbnail_text": "PASSOU DO LIMITE",
            "original_thread": "Thread original",
            "hashtags": ["#reddit", "#historias", "#shorts"],
            "tags": ["reddit", "historias do reddit", "historia viral", "dilema moral", "shorts"],
            "seo": ["historia reddit", "historias do reddit", "dilema moral"],
            "why_click": "Pacote reserva sem Gemini apos bloqueio do prompt de metadata.",
            "source_notes": "Metadata reserva criada sem Gemini apos erro de pacote.",
        }
    return {
        "fallback_title": "Reddit Story",
        "thumbnail_text": "TOO FAR?",
        "original_thread": "Original thread",
        "hashtags": ["#reddit", "#stories", "#shorts"],
        "tags": ["reddit", "reddit stories", "viral story", "moral dilemma", "shorts"],
        "seo": ["reddit story", "viral reddit", "moral dilemma"],
        "why_click": "Fallback packaging without Gemini after a metadata prompt error.",
        "source_notes": "Fallback metadata generated without Gemini after a packaging error.",
    }


def deterministic_fallback(
    story: dict[str, Any],
    channel: dict[str, Any],
    model: str,
    *,
    reason: str | None = None,
) -> dict[str, Any]:
    url = story.get("url", "")
    labels = fallback_labels(channel)
    localized_title_source = (
        story.get("first_screen_text")
        or story.get("first_screen_promise")
        or story.get("packaging_thesis")
    )
    lang = str(channel.get("lang") or "en").lower()
    if localized_title_source:
        title_source = localized_title_source
    elif lang.startswith("en"):
        title_source = story.get("title") or labels["fallback_title"]
    else:
        title_source = labels["fallback_title"]
    title = clip_text(str(title_source), 95) or labels["fallback_title"]
    subreddit = str(story.get("subreddit") or "Reddit").strip()
    hashtag_line = " ".join(labels["hashtags"])
    description = f"{title}\n\n{labels['original_thread']}: {url}\n\n{hashtag_line}".strip()
    fallback_reason = sanitize_reason(reason)
    source_notes = labels["source_notes"]
    if fallback_reason:
        source_notes = f"{source_notes} Reason: {fallback_reason}"
    return {
        "source": "gemini-error-fallback" if fallback_reason else "deterministic-fallback",
        "model": model,
        "keyName": None,
        "channelId": channel.get("id"),
        "channelHandle": channel.get("handle"),
        "language": channel.get("lang"),
        "youtube_title": title[:100],
        "youtube_description": description[:5000],
        "tags": (labels["tags"] + [subreddit.replace("r/", "")])[:25],
        "hashtags": labels["hashtags"][:6],
        "thumbnail_text": labels["thumbnail_text"],
        "packaging_options": [
            {
                "youtube_title": title[:100],
                "thumbnail_text": labels["thumbnail_text"],
                "first_screen_promise": str(story.get("first_screen_promise") or story.get("first_screen_text") or "")[:240],
                "why_click": labels["why_click"],
                "source_backing": str(story.get("title") or "")[:240],
            }
        ],
        "selected_option_index": 0,
        "first_screen_promise": str(story.get("first_screen_promise") or story.get("first_screen_text") or "")[:240],
        "thumbnail_prompt": (
            "Dramatic YouTube thumbnail for a Reddit story, cinematic lighting, "
            "high contrast, expressive human silhouette, no text in the image."
        ),
        "seo_keywords": (labels["seo"] + [subreddit])[:20],
        "risk_flags": [],
        "source_notes": source_notes,
        "metadata_fallback_reason": fallback_reason,
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate YouTube SEO metadata through Gemini.")
    parser.add_argument("--story", default="story_data.json", help="Input story JSON path.")
    parser.add_argument("--channel", "-c", default=None, help="Channel id/handle from channels.json.")
    parser.add_argument("--output", "-o", default=DEFAULT_OUTPUT, help="Output metadata JSON path.")
    parser.add_argument("--model", default=DEFAULT_GEMINI_MODEL, help="Gemini model.")
    parser.add_argument("--env-file", action="append", default=[], help="Optional env file to load.")
    parser.add_argument("--confirm-spend", action="store_true", help="Required for live Gemini calls.")
    parser.add_argument("--dry-run", action="store_true", help="Build fallback metadata without API spend.")
    parser.add_argument(
        "--fallback-on-error",
        action="store_true",
        help="Write conservative fallback metadata if Gemini packaging fails. Intended for render dry-runs, not production upload.",
    )
    parser.add_argument("--temperature", type=float, default=0.35)
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    story = load_json(args.story)
    channel = load_channel(args.channel)

    loaded_env_files = [path for path in args.env_file if load_dotenv_file(path)]
    key_name: str | None = None

    if args.dry_run:
        metadata = deterministic_fallback(story, channel, args.model)
    else:
        if not args.confirm_spend:
            raise VectorEngineError(
                "Refusing to call Gemini because this can spend API credits or quota. "
                "Re-run with --confirm-spend or use --dry-run."
            )
        try:
            _, key_name, _ = resolve_gemini_provider()
            raw_metadata = call_gemini_json(
                prompt=build_prompt(story, channel),
                model=args.model,
                temperature=args.temperature,
            )
            metadata = normalize_metadata(
                raw_metadata,
                story=story,
                channel=channel,
                model=args.model,
                source=gemini_source_label(),
                key_name=key_name,
            )
        except VectorEngineError as exc:
            if not args.fallback_on_error:
                raise
            metadata = deterministic_fallback(story, channel, args.model, reason=str(exc))
            metadata["keyName"] = key_name

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": "ok",
        "source": metadata.get("source"),
        "model": metadata.get("model"),
        "channelId": metadata.get("channelId"),
        "language": metadata.get("language"),
        "output": str(output_path),
        "keyName": key_name,
        "loadedEnvFileCount": len(loaded_env_files),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv[1:]))
    except (OSError, json.JSONDecodeError, VectorEngineError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
