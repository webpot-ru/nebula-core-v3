#!/usr/bin/env python3
"""Build a hash-bound, fail-closed acc1 SAGA greenlight draft.

The command is deliberately no-spend and does not turn a reviewed Reddit
source into an approved episode.  It copies only deterministic source evidence
from an exact queue/review pair; all creative fields remain empty and blocked.
Without an explicit ``--post-id`` it preserves the queue-selected story identity
instead of silently replacing ``story.json`` with the reviewer's top-ranked row.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any


ELIGIBLE_STATUS = "SAGA_SOURCE_ELIGIBLE_FOR_GREENLIGHT"
SAGA_REVIEW_MODE = "deterministic_full_body_saga"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
# Match ``scraper.source_word_count`` and the deterministic topic reviewer so
# dates, ages, and amounts cannot break the hash-bound handoff.
WORD_RE = re.compile(r"[A-Za-z0-9']+")
SCORE_FIELDS = (
    "title_thumbnail",
    "cold_open",
    "arc_payoff",
    "viewer_promise",
    "source_truth",
    "originality_visual",
)


class GreenlightTemplateError(RuntimeError):
    """Raised when the exact source/review evidence cannot be trusted."""


def _text(value: Any) -> str:
    return str(value or "").strip()


def canonical_content_hash(payload: Any) -> str:
    """Match ``review_reddit_topics.content_hash`` byte-for-byte."""
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _read_object(path: Path, label: str) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise GreenlightTemplateError(f"{label} must be a JSON object")
    return payload


def _verify_bindings(queue: dict[str, Any], review: dict[str, Any]) -> tuple[str, str]:
    source_sha256 = canonical_content_hash(queue)
    if _text(review.get("source_sha256")) != source_sha256:
        raise GreenlightTemplateError("topic-review source_sha256 does not match the exact queue")

    review_without_hash = dict(review)
    recorded_review_sha256 = _text(review_without_hash.pop("review_sha256", None))
    review_sha256 = canonical_content_hash(review_without_hash)
    if recorded_review_sha256 != review_sha256:
        raise GreenlightTemplateError("topic-review review_sha256 does not match its canonical content")
    return source_sha256, review_sha256


def _select_candidate(
    queue: dict[str, Any],
    review: dict[str, Any],
    post_id: str | None,
) -> tuple[dict[str, Any], str]:
    raw_topics = review.get("top_topics")
    if not isinstance(raw_topics, list):
        raise GreenlightTemplateError("topic-review top_topics must be a list")
    topics = [item for item in raw_topics if isinstance(item, dict)]
    if not topics:
        raise GreenlightTemplateError("topic-review has no candidate available for source selection")

    requested_post_id = _text(post_id)
    selection_mode = "explicit_post_id" if requested_post_id else "queue_selected_post_id"
    if not requested_post_id:
        requested_post_id = _text(queue.get("selected_post_id"))
        if not requested_post_id:
            raise GreenlightTemplateError("queue selected_post_id is required for default source selection")

    selected = [
        item for item in topics
        if _text(item.get("post_id")) == requested_post_id
    ]
    if post_id:
        if len(selected) != 1:
            raise GreenlightTemplateError("--post-id must match exactly one topic-review top_topics candidate")
    else:
        if len(selected) != 1:
            raise GreenlightTemplateError(
                "queue selected_post_id must match exactly one eligible topic-review top_topics candidate"
            )
    candidate = selected[0]

    if candidate.get("review_status") != ELIGIBLE_STATUS:
        raise GreenlightTemplateError("selected candidate is not SAGA_SOURCE_ELIGIBLE_FOR_GREENLIGHT")
    if candidate.get("blocking_reasons"):
        raise GreenlightTemplateError("selected candidate contains blocking reasons")
    return candidate, selection_mode


def _verify_exact_queue_candidate(
    queue: dict[str, Any],
    review: dict[str, Any],
    candidate: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    if queue.get("channel_id") != "acc1" or review.get("channel_id") != "acc1":
        raise GreenlightTemplateError("queue and topic-review channel_id must both be acc1")
    if review.get("review_mode") != SAGA_REVIEW_MODE:
        raise GreenlightTemplateError("topic-review must use deterministic_full_body_saga")
    if review.get("status") != "review_ready":
        raise GreenlightTemplateError("topic-review status must be review_ready")
    if review.get("production_authorized") is not False:
        raise GreenlightTemplateError("topic-review production_authorized must remain false")

    queue_plan = queue.get("source_plan")
    review_plan = review.get("source_plan")
    if not isinstance(queue_plan, dict) or queue_plan != review_plan:
        raise GreenlightTemplateError("queue and topic-review must contain the same exact source_plan")
    if queue_plan.get("format") != "SAGA" or queue.get("format_intent") != "saga":
        raise GreenlightTemplateError("source evidence must be an acc1 SAGA queue")
    pilot_id = _text(queue_plan.get("pilot_id"))
    pillar_id = _text(queue_plan.get("pillar"))
    if not pilot_id or not pillar_id:
        raise GreenlightTemplateError("source_plan pilot_id and pillar are required")

    selected_post_id = _text(candidate.get("post_id"))
    if not selected_post_id:
        raise GreenlightTemplateError("selected candidate post_id is required")
    entries = [
        item for item in queue.get("entries") or []
        if isinstance(item, dict) and _text(item.get("post_id")) == selected_post_id
    ]
    if len(entries) != 1:
        raise GreenlightTemplateError("selected candidate must match exactly one exact queue entry")
    entry = entries[0]

    source_body = str(entry.get("source_body") or "")
    if not source_body.strip():
        raise GreenlightTemplateError("selected queue entry must contain its full source_body")
    body_sha256 = hashlib.sha256(source_body.encode("utf-8")).hexdigest()
    word_count = len(WORD_RE.findall(source_body))
    if candidate.get("source_body_sha256") != body_sha256:
        raise GreenlightTemplateError("selected candidate source_body_sha256 does not match the queue body")
    if candidate.get("source_word_count") != word_count:
        raise GreenlightTemplateError("selected candidate source_word_count does not match the queue body")
    recorded_body_sha256 = _text(entry.get("source_body_sha256"))
    if recorded_body_sha256 and recorded_body_sha256 != body_sha256:
        raise GreenlightTemplateError("queue entry source_body_sha256 does not match its body")
    recorded_word_count = entry.get("source_word_count")
    if recorded_word_count is not None and recorded_word_count != word_count:
        raise GreenlightTemplateError("queue entry source_word_count does not match its body")

    expected_url = _text(entry.get("url") or entry.get("source_url"))
    if not expected_url or _text(candidate.get("source_url")) != expected_url:
        raise GreenlightTemplateError("selected candidate source URL does not match the queue entry")
    if _text(candidate.get("title")) != _text(entry.get("title")):
        raise GreenlightTemplateError("selected candidate title does not match the queue entry")
    if _text(candidate.get("subreddit")) != _text(entry.get("subreddit")):
        raise GreenlightTemplateError("selected candidate subreddit does not match the queue entry")
    if _text(candidate.get("source_family")) != _text(queue_plan.get("topic_family")):
        raise GreenlightTemplateError("selected candidate source family does not match source_plan")
    if _text(candidate.get("pillar_id")) != pillar_id:
        raise GreenlightTemplateError("selected candidate pillar does not match source_plan")

    if candidate.get("runtime_fit") is not True:
        raise GreenlightTemplateError("selected candidate has not proven SAGA runtime fit")
    if candidate.get("payoff_complete") is not True:
        raise GreenlightTemplateError("selected candidate has not proven a complete payoff")
    if candidate.get("depends_on_screenshot_or_link") is not False:
        raise GreenlightTemplateError("selected candidate depends on a screenshot or outbound link")
    if candidate.get("truth_mode") not in {"fiction", "unverified_personal_account"}:
        raise GreenlightTemplateError("selected candidate has no publishable truth mode")
    if not SHA256_RE.fullmatch(body_sha256):
        raise GreenlightTemplateError("selected candidate body hash is invalid")
    return queue_plan, entry


def build_template(
    queue: dict[str, Any],
    review: dict[str, Any],
    *,
    post_id: str | None = None,
) -> dict[str, Any]:
    """Build one deterministic draft without asserting any creative PASS."""
    source_sha256, review_sha256 = _verify_bindings(queue, review)
    candidate, selection_mode = _select_candidate(queue, review, _text(post_id) or None)
    source_plan, _entry = _verify_exact_queue_candidate(queue, review, candidate)
    source_url = _text(candidate.get("source_url"))
    queue_selected_post_id = _text(queue.get("selected_post_id"))
    top_topics = [item for item in review.get("top_topics") or [] if isinstance(item, dict)]
    review_top_post_id = _text(top_topics[0].get("post_id")) if top_topics else ""
    selected_post_id = _text(candidate.get("post_id"))

    return {
        "version": 1,
        "status": "DRAFT_BLOCKED",
        "channel_id": "acc1",
        "pilot_id": _text(source_plan.get("pilot_id")),
        "format": "SAGA",
        "pillar": _text(source_plan.get("pillar")),
        "artifact_bindings": {
            "source_sha256": source_sha256,
            "review_sha256": review_sha256,
        },
        "selection_contract": {
            "authority": "greenlight_source_post_id",
            "mode": selection_mode,
            "queue_selected_post_id": queue_selected_post_id,
            "review_top_post_id": review_top_post_id,
            "selected_post_id": selected_post_id,
            "preliminary_story_superseded": selected_post_id != queue_selected_post_id,
        },
        "source": {
            "post_id": _text(candidate.get("post_id")),
            "title": _text(candidate.get("title")),
            "subreddit": _text(candidate.get("subreddit")),
            "source_url": source_url,
            "source_urls": [source_url],
            "source_body_sha256": candidate.get("source_body_sha256"),
            "source_word_count": candidate.get("source_word_count"),
            "estimated_minutes_at_130_wpm": candidate.get("estimated_minutes_at_130_wpm"),
            "runtime_target_minutes": candidate.get("runtime_target_minutes"),
            "runtime_fit": candidate.get("runtime_fit"),
            "complete": True,
            "primary_story_count": 1,
            "truth_mode": candidate.get("truth_mode"),
            "fictional_as_real": False,
            "depends_on_screenshot_or_link": candidate.get("depends_on_screenshot_or_link"),
            "payoff_complete": candidate.get("payoff_complete"),
            "payoff_evidence": candidate.get("payoff_evidence"),
            "pillar_id": candidate.get("pillar_id"),
            "pillar_fit_score": candidate.get("pillar_fit_score"),
            "pillar_fit_evidence": candidate.get("pillar_fit_evidence"),
            "source_family": candidate.get("source_family"),
            "review_status": candidate.get("review_status"),
            "blocking_reasons": [],
        },
        "packaging_options": [],
        "cold_open": {},
        "story_beats": [],
        "originality_plan": {},
        "veto_flags": [],
        "scores": {field: 0 for field in SCORE_FIELDS},
        "draft_blockers": [
            "packaging_options_required",
            "cold_open_required",
            "story_beats_required",
            "originality_plan_required",
            "manual_scoring_required",
        ],
        "production_authorized": False,
        "publication_authorized": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--queue", required=True, help="Exact candidate queue JSON")
    parser.add_argument("--review", required=True, help="Exact topic-review JSON")
    parser.add_argument("--output", required=True, help="Draft greenlight JSON to create")
    parser.add_argument(
        "--post-id",
        help="Explicit eligible top_topics post ID; defaults to the exact queue selected_post_id",
    )
    args = parser.parse_args()

    queue = _read_object(Path(args.queue), "queue")
    review = _read_object(Path(args.review), "topic-review")
    payload = build_template(queue, review, post_id=args.post_id)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": payload["status"],
        "pilot_id": payload["pilot_id"],
        "post_id": payload["source"]["post_id"],
        "publication_authorized": False,
        "output": str(output),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
