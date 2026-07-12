#!/usr/bin/env python3
"""Build one acc1 internal horror compilation from a full-body topic review."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


class PilotSelectionError(RuntimeError):
    pass


def read_object(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise PilotSelectionError(f"{path} must contain a JSON object")
    return data


def select_compilation(
    queue: dict[str, Any],
    review: dict[str, Any],
    story_count: int,
    time_filter: str,
    source_mode: str,
) -> dict[str, Any]:
    if not 3 <= story_count <= 6:
        raise PilotSelectionError("story count must be between 3 and 6")
    if time_filter not in {"month", "year"}:
        raise PilotSelectionError("acc1 long-form pilots require month or year")
    if review.get("channel_id") not in (None, "acc1") or queue.get("channel_id") not in (None, "acc1"):
        raise PilotSelectionError("pilot selector only accepts acc1 evidence")
    entries = {str(item.get("post_id")): item for item in queue.get("entries") or [] if isinstance(item, dict) and item.get("post_id")}
    expected_truth = {
        "nosleep": "fiction",
        "letsnotmeet": "unverified_personal_account",
    }.get(source_mode)
    if not expected_truth:
        raise PilotSelectionError("source_mode must be nosleep or letsnotmeet")

    selected: list[dict[str, Any]] = []
    used: set[str] = set()
    for topic in review.get("top_topics") or []:
        if not isinstance(topic, dict):
            continue
        post_id = str(topic.get("post_id") or "")
        entry = entries.get(post_id)
        if not post_id or post_id in used or not entry:
            continue
        body = str(entry.get("source_body") or "").strip()
        risks = set(topic.get("risks") or [])
        truth_mode = str(topic.get("truth_mode") or "")
        if not body or risks & {"possible_series_dependency", "possible_open_ending"}:
            continue
        if truth_mode != expected_truth:
            continue
        subreddit = str(entry.get("subreddit") or "").casefold().removeprefix("r/")
        if subreddit != source_mode:
            continue
        media = entry.get("source_media") if isinstance(entry.get("source_media"), list) else []
        if "external_dependency" in risks and not media:
            continue
        snapshot = {
            "post_id": post_id,
            "source_url": entry.get("url") or entry.get("source_url"),
            "subreddit": entry.get("subreddit"),
            "title": entry.get("title"),
            "body": body,
            "body_sha256": hashlib.sha256(body.encode("utf-8")).hexdigest(),
            "truth_mode": truth_mode,
            "source_media": media,
            "source_word_count": len(body.split()),
        }
        selected.append({
            "story_index": len(selected) + 1,
            "theme_id": topic.get("theme_id"),
            "selection_score": topic.get("shortlist_score"),
            "source_snapshot": snapshot,
        })
        used.add(post_id)
        if len(selected) == story_count:
            break
    if len(selected) != story_count:
        raise PilotSelectionError(f"only {len(selected)} eligible distinct stories found; requested {story_count}")
    total_source_words = sum(item["source_snapshot"]["source_word_count"] for item in selected)
    estimated_minutes = round(total_source_words / 130, 2)
    if not 40 <= estimated_minutes <= 70:
        raise PilotSelectionError(
            f"selected source runtime estimate is outside 40-70 minutes: {estimated_minutes}"
        )
    return {
        "version": 2,
        "status": "READY",
        "channel_id": "acc1",
        "product": "reddit_horror_compilation",
        "source_mode": source_mode,
        "time_filter": time_filter,
        "story_count": len(selected),
        "target_runtime_minutes": [45, 60],
        "source_word_count": total_source_words,
        "estimated_source_minutes": estimated_minutes,
        "rights_mode": "test_only_not_cleared",
        "distribution_scope": "internal_artifact_only",
        "publication_authorized": False,
        "stories": selected,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--queue", required=True)
    parser.add_argument("--review", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--story-count", type=int, choices=range(3, 7), default=3)
    parser.add_argument("--source-mode", choices=("nosleep", "letsnotmeet"), required=True)
    parser.add_argument("--time-filter", choices=("month", "year"), required=True)
    args = parser.parse_args()
    compilation = select_compilation(
        read_object(Path(args.queue)),
        read_object(Path(args.review)),
        args.story_count,
        args.time_filter,
        args.source_mode,
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(compilation, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "READY", "story_count": compilation["story_count"], "output": str(output)}))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, json.JSONDecodeError, PilotSelectionError) as exc:
        print(f"ERROR: {exc}")
        raise SystemExit(1)
