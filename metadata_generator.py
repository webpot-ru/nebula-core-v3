import argparse
import json
import sys
from pathlib import Path
from typing import Any

from vectorengine_client import (
    DEFAULT_GEMINI_MODEL,
    VectorEngineError,
    call_gemini_json,
    get_api_key,
    load_dotenv_file,
)


DEFAULT_OUTPUT = "youtube_metadata.json"


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
- Keep youtube_title under 95 characters.
- Keep thumbnail_text punchy: 2 short lines max, no more than 32 characters total if possible.
- Description must include the original Reddit URL if present.
- Use SEO keywords naturally, not as spam.
- Tags must be plain strings without # and suitable for YouTube tags.
- Hashtags must include # and be suitable for the description.
- Thumbnail prompt must be a visual prompt for a dramatic YouTube thumbnail, with no copyrighted characters.
- Flag risks such as too graphic, privacy, self-harm, hate, medical, legal, or sexual content.

JSON shape:
{{
  "youtube_title": "string",
  "youtube_description": "string",
  "tags": ["string"],
  "hashtags": ["#string"],
  "thumbnail_text": "string",
  "thumbnail_prompt": "string",
  "seo_keywords": ["string"],
  "risk_flags": ["string"],
  "language": "{language}",
  "source_notes": "string"
}}
""".strip()


def normalize_metadata(
    metadata: dict[str, Any],
    *,
    story: dict[str, Any],
    channel: dict[str, Any],
    model: str,
    key_name: str | None,
) -> dict[str, Any]:
    title = str(metadata.get("youtube_title") or story.get("title") or "Reddit Story").strip()
    description = str(metadata.get("youtube_description") or "").strip()
    if story.get("url") and story["url"] not in description:
        description = f"{description}\n\nOriginal thread: {story['url']}".strip()

    tags = [str(tag).strip().lstrip("#") for tag in metadata.get("tags", []) if str(tag).strip()]
    hashtags = [str(tag).strip() for tag in metadata.get("hashtags", []) if str(tag).strip()]
    hashtags = [tag if tag.startswith("#") else f"#{tag}" for tag in hashtags]

    return {
        "source": "vectorengine-gemini",
        "model": model,
        "keyName": key_name,
        "channelId": channel.get("id"),
        "channelHandle": channel.get("handle"),
        "language": metadata.get("language") or channel.get("lang"),
        "youtube_title": title[:100],
        "youtube_description": description[:5000],
        "tags": tags[:25],
        "hashtags": hashtags[:6],
        "thumbnail_text": str(metadata.get("thumbnail_text") or "").strip()[:80],
        "thumbnail_prompt": str(metadata.get("thumbnail_prompt") or "").strip(),
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


def deterministic_fallback(story: dict[str, Any], channel: dict[str, Any], model: str) -> dict[str, Any]:
    url = story.get("url", "")
    title = str(story.get("title") or "Reddit Story").strip()
    subreddit = str(story.get("subreddit") or "Reddit").strip()
    description = f"{title}\n\nOriginal thread: {url}\n\n#reddit #stories #shorts".strip()
    return {
        "source": "deterministic-fallback",
        "model": model,
        "keyName": None,
        "channelId": channel.get("id"),
        "channelHandle": channel.get("handle"),
        "language": channel.get("lang"),
        "youtube_title": title[:100],
        "youtube_description": description[:5000],
        "tags": ["reddit", "reddit stories", subreddit.replace("r/", ""), "viral story", "storytime"],
        "hashtags": ["#reddit", "#stories", "#shorts"],
        "thumbnail_text": "Reddit Story",
        "thumbnail_prompt": (
            "Dramatic YouTube thumbnail for a Reddit story, cinematic lighting, "
            "high contrast, expressive human silhouette, no text in the image."
        ),
        "seo_keywords": ["reddit story", "viral reddit", subreddit],
        "risk_flags": [],
        "source_notes": "Fallback metadata generated without VectorEngine API spend.",
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate YouTube SEO metadata through VectorEngine.")
    parser.add_argument("--story", default="story_data.json", help="Input story JSON path.")
    parser.add_argument("--channel", "-c", default=None, help="Channel id/handle from channels.json.")
    parser.add_argument("--output", "-o", default=DEFAULT_OUTPUT, help="Output metadata JSON path.")
    parser.add_argument("--model", default=DEFAULT_GEMINI_MODEL, help="VectorEngine Gemini model.")
    parser.add_argument("--env-file", action="append", default=[], help="Optional env file to load.")
    parser.add_argument("--confirm-spend", action="store_true", help="Required for live VectorEngine calls.")
    parser.add_argument("--dry-run", action="store_true", help="Build fallback metadata without API spend.")
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
                "Refusing to call VectorEngine because this can spend API credits. "
                "Re-run with --confirm-spend or use --dry-run."
            )
        key_name, _ = get_api_key()
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
            key_name=key_name,
        )

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
