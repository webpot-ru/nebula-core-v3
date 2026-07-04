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
STORY_SLIDE_MAX_CHARS = 520
COMMENT_SLIDE_MAX_CHARS = 460
COMMENTS_PER_SLIDE = 2

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


def narration_field_text(container: dict[str, Any], field: str) -> str:
    if not isinstance(container, dict):
        return ""
    value = container.get(f"narration_{field}")
    if value is None or not str(value).strip():
        value = container.get(field)
    return clean_text(value)


def split_text_chunks_with_narration(
    display_text: str,
    narration_text: str,
    max_chars: int,
) -> list[dict[str, str]]:
    display_sentences = split_sentences(display_text)
    if not display_sentences and display_text:
        display_sentences = [clean_text(display_text)]
    if not display_sentences:
        return []

    narration_sentences = split_sentences(narration_text)
    use_parallel_narration = bool(narration_text) and len(narration_sentences) == len(display_sentences)
    if not use_parallel_narration:
        narration_sentences = display_sentences

    chunks: list[dict[str, str]] = []
    current_display = ""
    current_narration = ""

    for display_sentence, narration_sentence in zip(display_sentences, narration_sentences):
        display_candidate = f"{current_display} {display_sentence}".strip()
        narration_candidate = f"{current_narration} {narration_sentence}".strip()
        if current_display and len(display_candidate) > max_chars:
            chunks.append({
                "body": current_display,
                "narration_body": current_narration,
            })
            current_display = display_sentence
            current_narration = narration_sentence
        else:
            current_display = display_candidate
            current_narration = narration_candidate

    if current_display:
        chunks.append({
            "body": current_display,
            "narration_body": current_narration,
        })
    if len(chunks) >= 2 and len(chunks[-1]["body"]) < max(140, int(max_chars * 0.35)):
        merged_body = f"{chunks[-2]['body']} {chunks[-1]['body']}".strip()
        merged_narration = f"{chunks[-2]['narration_body']} {chunks[-1]['narration_body']}".strip()
        if len(merged_body) <= int(max_chars * 1.25):
            chunks[-2] = {
                "body": merged_body,
                "narration_body": merged_narration,
            }
            chunks.pop()
    return chunks


def count_words(text: str) -> int:
    return len(re.findall(r"\S+", clean_text(text)))


def slide_narration_text(slide: dict[str, Any]) -> str:
    parts: list[str] = []
    title = narration_field_text(slide, "title")
    body = narration_field_text(slide, "body")
    if title:
        parts.append(title)
    if body:
        parts.append(body)
    for comment in slide.get("comments") or []:
        if isinstance(comment, dict):
            comment_body = narration_field_text(comment, "body")
            if comment_body:
                parts.append(comment_body)
    return "\n\n".join(parts)


def estimated_slide_duration(word_count: int) -> float:
    return round(max(2.4, min(12.0, word_count / 2.65 + 0.8)), 3)


def assign_slide_word_ranges(slides: list[dict[str, Any]]) -> None:
    cursor = 0
    for index, slide in enumerate(slides):
        text = slide_narration_text(slide)
        words = count_words(text)
        slide["index"] = index
        slide["word_start"] = cursor
        slide["word_end"] = cursor + words
        slide["word_count"] = words
        slide["estimated_duration_sec"] = estimated_slide_duration(words)
        cursor += words


def build_render_slides(
    *,
    title: str,
    narration_title: str,
    body: str,
    narration_body: str,
    comments: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    story_chunks = split_text_chunks_with_narration(body, narration_body, STORY_SLIDE_MAX_CHARS)
    if not story_chunks:
        story_chunks = [{"body": "", "narration_body": ""}]

    slides: list[dict[str, Any]] = []
    story_slide_count = len(story_chunks)
    for index, chunk in enumerate(story_chunks):
        part = "single"
        if story_slide_count > 1:
            if index == 0:
                part = "first"
            elif index == story_slide_count - 1:
                part = "last"
            else:
                part = "middle"
        slides.append({
            "id": f"story_{index + 1}",
            "type": "story",
            "title": title if index == 0 else "",
            "narration_title": narration_title if index == 0 else "",
            "body": chunk["body"],
            "narration_body": chunk["narration_body"],
            "comments": [],
            "part": part,
            "show_post_header": index == 0,
            "show_post_title": index == 0,
            "show_post_footer": index == story_slide_count - 1,
            "continuation_only": index > 0,
        })

    current_comments: list[dict[str, Any]] = []
    current_chars = 0

    def flush_comments() -> None:
        nonlocal current_comments, current_chars
        if not current_comments:
            return
        slides.append({
            "id": f"comments_{len(slides) + 1}",
            "type": "comments",
            "title": "",
            "body": "",
            "comments": current_comments,
            "show_post_header": False,
            "show_post_title": False,
            "show_post_footer": False,
        })
        current_comments = []
        current_chars = 0

    for comment in comments:
        comment_body = clean_text(comment.get("body"))
        if not comment_body:
            continue
        comment_chunks = split_text_chunks_with_narration(
            comment_body,
            clean_text(comment.get("narration_body")) or comment_body,
            COMMENT_SLIDE_MAX_CHARS,
        ) or [{"body": comment_body, "narration_body": clean_text(comment.get("narration_body")) or comment_body}]

        if len(comment_chunks) > 1:
            flush_comments()
            for chunk_index, chunk in enumerate(comment_chunks):
                copied = dict(comment)
                copied["body"] = chunk["body"]
                copied["narration_body"] = chunk["narration_body"]
                copied["part"] = "first" if chunk_index == 0 else ("last" if chunk_index == len(comment_chunks) - 1 else "middle")
                copied["show_header"] = chunk_index == 0
                copied["show_footer"] = chunk_index == len(comment_chunks) - 1
                copied["continuation_only"] = chunk_index > 0
                slides.append({
                    "id": f"comment_{comment.get('id')}_{chunk_index + 1}",
                    "type": "comments",
                    "title": "",
                    "body": "",
                    "comments": [copied],
                    "show_post_header": False,
                    "show_post_title": False,
                    "show_post_footer": False,
                })
            continue

        copied = dict(comment)
        copied["body"] = comment_chunks[0]["body"]
        copied["narration_body"] = comment_chunks[0]["narration_body"]
        copied["part"] = "single"
        copied["show_header"] = True
        copied["show_footer"] = True
        candidate_chars = current_chars + len(copied["body"])
        if current_comments and (
            len(current_comments) >= COMMENTS_PER_SLIDE
            or candidate_chars > COMMENT_SLIDE_MAX_CHARS
        ):
            flush_comments()
        current_comments.append(copied)
        current_chars += len(copied["body"])

    flush_comments()

    assign_slide_word_ranges(slides)
    return slides


def build_scenes_from_slides(slides: list[dict[str, Any]]) -> list[dict[str, Any]]:
    scenes: list[dict[str, Any]] = []
    for index, slide in enumerate(slides, start=1):
        text = slide_narration_text(slide)
        title = clean_text(slide.get("title")) or ("Comments" if slide.get("type") == "comments" else "Story")
        scenes.append({
            "index": index,
            "scene_type": slide.get("type") or "story",
            "title": title,
            "text": text,
            "duration_sec": float(slide.get("estimated_duration_sec") or 3.0),
            "visual_template": "reddit_slide",
            "slide_id": slide.get("id"),
            "word_start": slide.get("word_start"),
            "word_end": slide.get("word_end"),
        })
    return scenes


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

    comments = [
        {
            "id": index + 1,
            "username": clean_text(comment.get("username") or f"u/commenter_{index + 1}"),
            "time": clean_text(comment.get("time") or "1h ago"),
            "body": clean_text(comment.get("body")),
            "narration_body": narration_field_text(comment, "body"),
            "upvotes": clean_text(comment.get("upvotes") or "1"),
        }
        for index, comment in enumerate(story.get("comments") or [])
        if isinstance(comment, dict) and clean_text(comment.get("body"))
    ]
    narration_title = narration_field_text(story, "title") or title
    narration_body = narration_field_text(story, "body") or body
    render_slides = build_render_slides(
        title=title,
        narration_title=narration_title,
        body=body,
        narration_body=narration_body,
        comments=comments,
    )
    scenes = build_scenes_from_slides(render_slides)

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
            "comments": comments,
            "slides": render_slides,
        },
        "render_slides": render_slides,
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
