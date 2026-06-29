import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_OUTPUT = "storyboard.json"
DEFAULT_FORMAT = "shorts"
SHORTS_RESOLUTION = {"width": 1080, "height": 1920, "aspect_ratio": "9:16"}

SCENE_DEFAULTS = {
    "hook": {"duration_sec": 3.0, "visual_template": "reddit_hook"},
    "setup": {"duration_sec": 4.0, "visual_template": "story_card"},
    "escalation": {"duration_sec": 4.0, "visual_template": "story_card"},
    "comments_context": {"duration_sec": 4.0, "visual_template": "comment_stack"},
    "payoff": {"duration_sec": 4.0, "visual_template": "payoff_card"},
    "cta": {"duration_sec": 3.0, "visual_template": "poll_card"},
}


class StoryboardError(RuntimeError):
    pass


def load_json(path: str | Path) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise StoryboardError(f"{path} must contain a JSON object.")
    return data


def clean_text(value: Any) -> str:
    text = str(value or "").replace("\r", "\n")
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


def split_sentences(text: str) -> list[str]:
    normalized = clean_text(text).replace("\n", " ")
    if not normalized:
        return []
    parts = re.split(r"(?<=[.!?])\s+", normalized)
    return [part.strip() for part in parts if part.strip()]


def pack_chunks(sentences: list[str], max_chars: int) -> list[str]:
    chunks: list[str] = []
    current = ""
    for sentence in sentences:
        candidate = f"{current} {sentence}".strip()
        if current and len(candidate) > max_chars:
            chunks.append(current)
            current = sentence
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks


def excerpt(text: str, limit: int) -> str:
    cleaned = clean_text(text)
    if len(cleaned) <= limit:
        return cleaned
    trimmed = cleaned[: limit - 1].rstrip()
    last_space = trimmed.rfind(" ")
    if last_space > max(0, limit - 45):
        trimmed = trimmed[:last_space]
    return f"{trimmed}..."


def comment_lines(story: dict[str, Any], limit: int = 2) -> list[str]:
    comments = story.get("comments") or []
    lines: list[str] = []
    for comment in comments[:limit]:
        if not isinstance(comment, dict):
            continue
        username = clean_text(comment.get("username") or "u/redditor")
        body = excerpt(comment.get("body") or "", 130)
        if body:
            lines.append(f"{username}: {body}")
    return lines


def build_scene(scene_type: str, title: str, text: str, index: int) -> dict[str, Any]:
    defaults = SCENE_DEFAULTS[scene_type]
    return {
        "index": index,
        "scene_type": scene_type,
        "title": title,
        "text": clean_text(text),
        "duration_sec": defaults["duration_sec"],
        "visual_template": defaults["visual_template"],
    }


def build_storyboard(story: dict[str, Any], output_format: str) -> dict[str, Any]:
    if output_format != "shorts":
        raise StoryboardError("Only --format shorts is supported in the dry-run renderer.")

    title = clean_text(story.get("title")) or "A Reddit story took a strange turn"
    body = clean_text(story.get("body"))
    subreddit = clean_text(story.get("subreddit")) or "Reddit"
    author = clean_text(story.get("author")) or "u/anonymous"
    upvotes = clean_text(story.get("upvotes")) or clean_text(story.get("score")) or "0"
    comments_count = clean_text(story.get("comments_count")) or clean_text(story.get("num_comments")) or "0"

    sentences = split_sentences(body)
    chunks = pack_chunks(sentences, max_chars=230)
    if not chunks and body:
        chunks = [excerpt(body, 230)]
    if not chunks:
        chunks = ["The details were short, but the comments turned it into a debate."]

    setup_text = chunks[0]
    escalation_text = chunks[1] if len(chunks) > 1 else excerpt(body or title, 230)
    payoff_text = chunks[-1] if len(chunks) > 2 else "The ending left people arguing about what should have happened next."
    comments_text = "\n".join(comment_lines(story)) or "The comments split fast: some people defended the poster, while others thought the story had a missing piece."

    scenes = [
        build_scene("hook", "Hook", title, 1),
        build_scene("setup", f"{subreddit} / {author}", setup_text, 2),
        build_scene("escalation", "Then it got worse", escalation_text, 3),
        build_scene("comments_context", f"{upvotes} upvotes / {comments_count} comments", comments_text, 4),
        build_scene("payoff", "The part everyone argued about", payoff_text, 5),
        build_scene("cta", "Your verdict?", "Who was right here?\nComment your take.", 6),
    ]

    return {
        "version": 1,
        "format": output_format,
        "resolution": SHORTS_RESOLUTION,
        "render_story": {
            "subreddit": subreddit,
            "title": title,
            "author": author,
            "body": body,
            "upvotes": upvotes,
            "comments_count": comments_count,
            "url": clean_text(story.get("url")),
            "comments": [
                {
                    "id": index + 1,
                    "username": clean_text(comment.get("username") or f"u/commenter_{index + 1}"),
                    "time": clean_text(comment.get("time") or "1h ago"),
                    "body": clean_text(comment.get("body")),
                    "upvotes": clean_text(comment.get("upvotes") or "1"),
                }
                for index, comment in enumerate(story.get("comments") or [])
                if isinstance(comment, dict) and clean_text(comment.get("body"))
            ][:3],
        },
        "source": {
            "subreddit": subreddit,
            "author": author,
            "url": clean_text(story.get("url")),
        },
        "created_at": datetime.now(timezone.utc).isoformat(),
        "scene_count": len(scenes),
        "scenes": scenes,
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate a deterministic dry-run storyboard from story_data.json.")
    parser.add_argument("--input", "-i", default="story_data.json", help="Input story JSON path.")
    parser.add_argument("--output", "-o", default=DEFAULT_OUTPUT, help="Output storyboard JSON path.")
    parser.add_argument("--format", default=DEFAULT_FORMAT, choices=["shorts"], help="Storyboard format.")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    story = load_json(args.input)
    storyboard = build_storyboard(story, args.format)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(storyboard, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": "ok",
        "input": args.input,
        "output": str(output_path),
        "format": storyboard["format"],
        "sceneCount": storyboard["scene_count"],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv[1:]))
    except (OSError, json.JSONDecodeError, StoryboardError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
