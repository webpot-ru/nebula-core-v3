import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from vectorengine_client import (
    DEFAULT_GEMINI_MODEL,
    VectorEngineError,
    call_gemini_json,
    gemini_source_label,
    load_dotenv_file,
)


DEFAULT_STORY = "story_data.json"
DEFAULT_OUTPUT = "story_data.json"
URL_RE = re.compile(r"(?i)\b(?:https?://|www\.)[^\s<>)\]]+")


class StoryAdapterError(RuntimeError):
    pass


def load_json(path: str | Path) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise StoryAdapterError(f"{path} must contain a JSON object.")
    return data


def save_json(path: str | Path, payload: dict[str, Any]) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_channel(channel_id: str | None) -> dict[str, Any]:
    data = load_json(Path(__file__).with_name("channels.json"))
    channels = data.get("channels", [])
    if not channels:
        raise StoryAdapterError("channels.json has no channels.")
    if channel_id:
        for channel in channels:
            if channel.get("id") == channel_id or channel.get("handle") == channel_id:
                return channel
        raise StoryAdapterError(f"Channel not found in channels.json: {channel_id}")
    return channels[0]


def clean_text(value: Any) -> str:
    return re.sub(r"[ \t]+", " ", str(value or "").replace("\r\n", "\n")).strip()


def normalize_for_match(value: str) -> str:
    normalized = re.sub(r"\s+", " ", str(value or "").casefold()).strip()
    return normalized


def story_source_text(story: dict[str, Any]) -> str:
    parts = [
        str(story.get("title") or ""),
        str(story.get("body") or ""),
    ]
    for comment in story.get("comments") or []:
        if isinstance(comment, dict):
            parts.append(str(comment.get("body") or ""))
    return "\n".join(parts)


def source_urls(story: dict[str, Any]) -> set[str]:
    return {match.group(0).rstrip(".,;:!?)") for match in URL_RE.finditer(story_source_text(story))}


def adapted_urls(payload: dict[str, Any]) -> set[str]:
    parts = [
        str(payload.get("adapted_title") or ""),
        str(payload.get("adapted_body") or ""),
        str(payload.get("hook") or ""),
        str(payload.get("first_screen_text") or ""),
    ]
    for comment in payload.get("comments") or []:
        if isinstance(comment, dict):
            parts.append(str(comment.get("body") or ""))
    return {match.group(0).rstrip(".,;:!?)") for text in parts for match in URL_RE.finditer(text)}


def evidence_items(payload: dict[str, Any]) -> list[dict[str, str]]:
    raw = payload.get("hook_evidence")
    if isinstance(raw, dict):
        raw = [raw]
    if not isinstance(raw, list):
        return []
    items: list[dict[str, str]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        quote = clean_text(item.get("quote"))
        if not quote:
            continue
        items.append({
            "field": clean_text(item.get("field") or "unknown"),
            "quote": quote[:280],
            "why_it_matters": clean_text(item.get("why_it_matters"))[:280],
        })
    return items


def evidence_is_source_backed(story: dict[str, Any], payload: dict[str, Any]) -> bool:
    source = normalize_for_match(story_source_text(story))
    if not source:
        return False
    for item in evidence_items(payload):
        quote = normalize_for_match(item.get("quote") or "")
        if quote and quote in source:
            return True
    return False


def story_hash(story: dict[str, Any]) -> str:
    digest = hashlib.sha1(story_source_text(story).encode("utf-8")).hexdigest()
    return digest[:16]


def story_payload_for_prompt(story: dict[str, Any]) -> dict[str, Any]:
    comments = []
    for index, comment in enumerate(story.get("comments") or []):
        if not isinstance(comment, dict):
            continue
        comments.append({
            "index": index,
            "username": comment.get("username") or f"u/commenter_{index + 1}",
            "body": comment.get("body") or "",
        })
    return {
        "subreddit": story.get("subreddit"),
        "title": story.get("title") or "",
        "body": story.get("body") or "",
        "comments": comments,
        "source_url": story.get("url"),
        "topic_family": story.get("topic_family"),
        "format_intent": story.get("format_intent"),
        "content_bet": story.get("content_bet"),
        "first_screen_promise": story.get("first_screen_promise"),
        "first_screen_text": story.get("first_screen_text"),
        "packaging_thesis": story.get("packaging_thesis"),
        "shorts_cut": story.get("shorts_cut"),
        "longform_angle": story.get("longform_angle"),
        "hook_evidence": story.get("hook_evidence"),
    }


def build_prompt(story: dict[str, Any], channel: dict[str, Any], max_body_chars: int | None) -> str:
    language = channel.get("lang") or "en"
    max_body_rule = (
        f"- Keep adapted_body under {max_body_chars} characters if possible.\n"
        if max_body_chars and max_body_chars > 0
        else ""
    )
    return f"""
You are an editor for a multilingual YouTube Reddit-story pipeline.
Your task is NOT to invent a new story. Your task is to make the selected Reddit source cleaner, tighter, and stronger for narration.

Channel:
- id: {channel.get('id')}
- handle: {channel.get('handle')}
- language: {language}
- region: {channel.get('region')}
- audience: {channel.get('audience')}
- promise: {channel.get('niche_label') or channel.get('niche')}

Rules:
- Preserve every factual claim, timeline, point of view, and speaker role.
- Do not invent new betrayals, deaths, crimes, secrets, relationships, numbers, places, quotes, updates, or motives.
- Do not remove the ending or any necessary story beat. For Shorts, the source was already selected to be short enough; keep the complete source arc instead of summarizing a long story.
- You may remove repetition, filler, Reddit housekeeping, and low-value edits.
- You may move one source-backed hook into the title/opening if it is supported by an exact quote from title/body/comment.
- Keep URLs exactly as source text if they are relevant; do not add new URLs.
- Keep Reddit usernames only inside comments; do not add spoken comment labels.
- If the source is too weak to adapt honestly, set safe_to_publish=false.
{max_body_rule}- Return strict JSON only.

Return JSON:
{{
  "safe_to_publish": <true|false>,
  "adapted_title": "<source-backed title/hook, no invented facts>",
  "adapted_body": "<cleaned story body, same facts and point of view>",
  "comments": [
    {{"index": 0, "body": "<cleaned comment body, or original if already good>"}}
  ],
  "hook": "<the exact hook idea being used, or null>",
  "first_screen_text": "<what should be visible first, max 180 chars>",
  "hook_evidence": [
    {{"field": "title|body|comment[0]", "quote": "<exact quote from source text>", "why_it_matters": "<why this supports the hook>"}}
  ],
  "removed_or_compressed": ["<short note>"],
  "facts_not_in_source": [],
  "adaptation_notes": "<one sentence>",
  "risk_flags": []
}}

Selected source JSON:
{json.dumps(story_payload_for_prompt(story), ensure_ascii=False, indent=2)}
""".strip()


def validate_adaptation(
    story: dict[str, Any],
    payload: dict[str, Any],
    *,
    strict_evidence: bool,
    max_expansion_ratio: float,
) -> list[str]:
    failures: list[str] = []
    if not payload.get("safe_to_publish", True):
        failures.append("Gemini marked adapted story as not safe_to_publish.")
    if not clean_text(payload.get("adapted_title")):
        failures.append("adapted_title is empty.")
    if not clean_text(payload.get("adapted_body")) and clean_text(story.get("body")):
        failures.append("adapted_body is empty.")
    if payload.get("facts_not_in_source"):
        failures.append("facts_not_in_source is not empty.")
    if strict_evidence and not evidence_is_source_backed(story, payload):
        failures.append("hook_evidence has no exact quote found in source title/body/comments.")

    original_len = len(clean_text(story.get("title"))) + len(clean_text(story.get("body")))
    adapted_len = len(clean_text(payload.get("adapted_title"))) + len(clean_text(payload.get("adapted_body")))
    if original_len > 0 and adapted_len > (original_len * max_expansion_ratio + 160):
        failures.append(
            f"Adapted text expanded too much: {adapted_len} chars vs {original_len} source chars."
        )

    new_urls = adapted_urls(payload) - source_urls(story)
    if new_urls:
        failures.append(f"Adaptation introduced new URL(s): {', '.join(sorted(new_urls))[:240]}")
    return failures


def apply_adaptation(story: dict[str, Any], payload: dict[str, Any], channel: dict[str, Any]) -> dict[str, Any]:
    adapted = dict(story)
    source_snapshot = {
        "title": story.get("title") or "",
        "body": story.get("body") or "",
        "comments": [
            {
                "index": index,
                "username": comment.get("username"),
                "body": comment.get("body"),
            }
            for index, comment in enumerate(story.get("comments") or [])
            if isinstance(comment, dict)
        ],
    }

    adapted["title"] = clean_text(payload.get("adapted_title")) or clean_text(story.get("title"))
    adapted["body"] = clean_text(payload.get("adapted_body")) or clean_text(story.get("body"))
    adapted["first_screen_text"] = clean_text(payload.get("first_screen_text")) or adapted.get("first_screen_text")
    adapted["hook_override"] = clean_text(payload.get("hook")) or adapted.get("hook_override")
    adapted["hook_evidence"] = evidence_items(payload) or adapted.get("hook_evidence") or []

    cleaned_comments_by_index: dict[int, str] = {}
    for fallback_index, item in enumerate(payload.get("comments") or []):
        if not isinstance(item, dict):
            continue
        try:
            index = int(item.get("index", fallback_index))
        except (TypeError, ValueError):
            index = fallback_index
        body = clean_text(item.get("body"))
        if body:
            cleaned_comments_by_index[index] = body

    comments = []
    for index, comment in enumerate(story.get("comments") or []):
        if not isinstance(comment, dict):
            continue
        copied = dict(comment)
        if index in cleaned_comments_by_index:
            copied["body"] = cleaned_comments_by_index[index]
        comments.append(copied)
    adapted["comments"] = comments

    adapted["editorial_adaptation"] = {
        "version": 1,
        "source": gemini_source_label(),
        "mode": "source_backed_no_invent",
        "channelId": channel.get("id"),
        "channelHandle": channel.get("handle"),
        "source_hash": story_hash(story),
        "source_snapshot": source_snapshot,
        "hook": clean_text(payload.get("hook")),
        "first_screen_text": adapted.get("first_screen_text"),
        "hook_evidence": evidence_items(payload),
        "removed_or_compressed": [
            clean_text(item)[:220]
            for item in payload.get("removed_or_compressed") or []
            if clean_text(item)
        ][:12],
        "adaptation_notes": clean_text(payload.get("adaptation_notes")),
        "risk_flags": [
            clean_text(item)
            for item in payload.get("risk_flags") or []
            if clean_text(item)
        ][:12],
        "adapted_at": datetime.now(timezone.utc).isoformat(),
        "facts_not_in_source": payload.get("facts_not_in_source") or [],
    }
    return adapted


def adapt_story(args: argparse.Namespace) -> dict[str, Any]:
    for env_file in args.env_file:
        load_dotenv_file(env_file)
    story = load_json(args.story)
    channel = load_channel(args.channel)

    if story.get("editorial_adaptation") and args.skip_if_adapted:
        return story

    if args.dry_run:
        print(json.dumps({
            "status": "dry_run",
            "story": args.story,
            "channel": channel.get("id"),
            "strictEvidence": args.strict_evidence,
            "sourceHash": story_hash(story),
            "wouldCallGemini": False,
            "wouldCallVectorEngine": False,
        }, ensure_ascii=False, indent=2))
        return story

    if not args.confirm_spend:
        raise StoryAdapterError(
            "Refusing to call Gemini because story adaptation can spend API credits or quota. "
            "Re-run with --confirm-spend or use --dry-run."
        )

    max_body_chars = args.max_body_chars if args.allow_body_trim else None
    if args.max_body_chars and not args.allow_body_trim:
        print(
            "Ignoring --max-body-chars because adapter body trimming is disabled. "
            "Use source-length filtering in scraper.py, or pass --allow-body-trim for an explicit manual trim."
        )

    try:
        raw = call_gemini_json(
            prompt=build_prompt(story, channel, max_body_chars),
            model=args.model,
            temperature=args.temperature,
            max_output_tokens=args.max_output_tokens,
        )
    except VectorEngineError as exc:
        raise StoryAdapterError(f"Gemini adaptation failed: {exc}") from exc

    failures = validate_adaptation(
        story,
        raw,
        strict_evidence=args.strict_evidence,
        max_expansion_ratio=args.max_expansion_ratio,
    )
    if failures:
        raise StoryAdapterError("Unsafe story adaptation: " + "; ".join(failures))
    return apply_adaptation(story, raw, channel)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Source-backed Reddit story adaptation before translation/TTS.")
    parser.add_argument("--story", default=DEFAULT_STORY, help="Input story_data.json path.")
    parser.add_argument("--output", "-o", default=DEFAULT_OUTPUT, help="Output adapted story path.")
    parser.add_argument("--channel", "-c", required=True, help="Channel id/handle from channels.json.")
    parser.add_argument("--model", default=DEFAULT_GEMINI_MODEL, help="Gemini model.")
    parser.add_argument("--temperature", type=float, default=0.2)
    parser.add_argument("--max-output-tokens", type=int, default=4096)
    parser.add_argument("--env-file", action="append", default=[], help="Optional env file to load before Gemini calls.")
    parser.add_argument("--confirm-spend", action="store_true", help="Required for live Gemini calls.")
    parser.add_argument("--dry-run", action="store_true", help="Validate inputs without calling Gemini.")
    parser.add_argument("--strict-evidence", action="store_true", help="Fail unless hook_evidence quotes are found exactly in source text.")
    parser.add_argument("--skip-if-adapted", action="store_true", help="Do nothing if story already has editorial_adaptation.")
    parser.add_argument("--max-body-chars", type=int, default=None, help="Deprecated safety valve: ask Gemini to shorten adapted body. Ignored unless --allow-body-trim is set.")
    parser.add_argument("--allow-body-trim", action="store_true", help="Allow adapter-level body shortening. Production workflows should not use this.")
    parser.add_argument("--max-expansion-ratio", type=float, default=1.15, help="Fail if adapted title/body expands too much.")
    return parser


def main(argv: list[str]) -> int:
    args = build_parser().parse_args(argv)
    adapted = adapt_story(args)
    if not args.dry_run:
        save_json(args.output, adapted)
        print(json.dumps({
            "status": "ok",
            "story": args.story,
            "output": args.output,
            "channel": args.channel,
            "adapted": bool(adapted.get("editorial_adaptation")),
            "strictEvidence": args.strict_evidence,
            "sourceHash": adapted.get("editorial_adaptation", {}).get("source_hash"),
        }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv[1:]))
    except (OSError, json.JSONDecodeError, StoryAdapterError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
