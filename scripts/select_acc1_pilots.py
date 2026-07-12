#!/usr/bin/env python3
"""Select one or two distinct acc1 internal pilots from a topic review."""

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


def select_pilots(queue: dict[str, Any], review: dict[str, Any], count: int, time_filter: str) -> list[dict[str, Any]]:
    if count not in (1, 2):
        raise PilotSelectionError("pilot count must be 1 or 2")
    if time_filter not in {"month", "year"}:
        raise PilotSelectionError("acc1 long-form pilots require month or year")
    if review.get("channel_id") not in (None, "acc1") or queue.get("channel_id") not in (None, "acc1"):
        raise PilotSelectionError("pilot selector only accepts acc1 evidence")
    entries = {str(item.get("post_id")): item for item in queue.get("entries") or [] if isinstance(item, dict) and item.get("post_id")}
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
        if not body or risks & {"possible_series_dependency", "possible_open_ending", "external_dependency"}:
            continue
        if truth_mode not in {"fiction", "unverified_personal_account"}:
            continue
        snapshot = {
            "post_id": post_id,
            "source_url": entry.get("url") or entry.get("source_url"),
            "subreddit": entry.get("subreddit"),
            "title": entry.get("title"),
            "body": body,
            "body_sha256": hashlib.sha256(body.encode("utf-8")).hexdigest(),
            "truth_mode": truth_mode,
        }
        selected.append({
            "pilot_index": len(selected) + 1,
            "channel_id": "acc1",
            "time_filter": time_filter,
            "theme_id": topic.get("theme_id"),
            "selection_score": topic.get("shortlist_score"),
            "rights_mode": "test_only_not_cleared",
            "distribution_scope": "internal_artifact_only",
            "publication_authorized": False,
            "source_snapshot": snapshot,
        })
        used.add(post_id)
        if len(selected) == count:
            break
    if len(selected) != count:
        raise PilotSelectionError(f"only {len(selected)} eligible distinct pilots found; requested {count}")
    return selected


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--queue", required=True)
    parser.add_argument("--review", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--count", type=int, choices=(1, 2), default=1)
    parser.add_argument("--time-filter", choices=("month", "year"), required=True)
    args = parser.parse_args()
    pilots = select_pilots(read_object(Path(args.queue)), read_object(Path(args.review)), args.count, args.time_filter)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps({"version": 1, "status": "READY", "pilot_count": len(pilots), "pilots": pilots}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "READY", "pilot_count": len(pilots), "output": str(output)}))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, json.JSONDecodeError, PilotSelectionError) as exc:
        print(f"ERROR: {exc}")
        raise SystemExit(1)
