#!/usr/bin/env python3
"""Bounded PRAW adapter for the deterministic acc1 THREAD collector.

This is the only network-facing layer for THREAD sources.  The CLI refuses to
construct a Reddit client unless ``--confirm-reddit-read`` is explicitly set.
It writes the network snapshot consumed by :mod:`acc1_thread_collector` and the
resulting immutable manifest as separate artifacts.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Iterable

from acc1_thread_collector import (
    MAX_RESPONSES,
    MIN_RESPONSES,
    TRUTH_MODES,
    ThreadCollectorError,
    collect_thread,
)


DEFAULT_SUBREDDIT = "AskReddit"
DEFAULT_TIME_FILTER = "month"
DEFAULT_CANDIDATE_LIMIT = 10
DEFAULT_RESPONSE_SCAN_LIMIT = 50
MAX_CANDIDATE_LIMIT = 25
MAX_RESPONSE_SCAN_LIMIT = 100
MAX_FINALIST_LIMIT = 5
TIME_FILTERS = ("day", "week", "month", "year", "all")
REMOVED_MARKERS = {"[deleted]", "[removed]", "[removed by reddit]"}
LINK_RE = re.compile(r"(?:https?://|www\.|\[[^\]]+\]\([^\)]+\))", re.IGNORECASE)


class ThreadSourceError(RuntimeError):
    """Raised when a bounded Reddit read cannot produce a valid THREAD."""


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).replace("\r\n", "\n").replace("\r", "\n").strip()
    return text or None


def _integer(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _author(value: Any) -> str | None:
    return _text(value) if value is not None else None


def _subreddit_name(submission: Any) -> str | None:
    subreddit = getattr(submission, "subreddit", None)
    display_name = getattr(subreddit, "display_name", None)
    return _text(display_name if display_name is not None else subreddit)


def _permalink(value: Any) -> str | None:
    return _text(getattr(value, "permalink", None))


def _bool_attr(value: Any, *names: str) -> bool:
    return any(getattr(value, name, False) is True for name in names)


def _has_attr_payload(value: Any, *names: str) -> bool:
    for name in names:
        payload = getattr(value, name, None)
        if payload not in (None, False, "", [], {}):
            return True
    return False


def _comment_snapshot(comment: Any, prompt_id: str) -> dict[str, Any]:
    """Copy one PRAW comment without shortening its body."""
    body_value = getattr(comment, "body", None)
    body = str(body_value).replace("\r\n", "\n").replace("\r", "\n") if body_value is not None else None
    author = _author(getattr(comment, "author", None))
    normalized_body = (body or "").strip().casefold()
    removed_by_category = _text(getattr(comment, "removed_by_category", None))

    is_deleted = (
        author is None
        or normalized_body == "[deleted]"
        or _bool_attr(comment, "deleted", "is_deleted")
    )
    is_removed = (
        normalized_body in {"[removed]", "[removed by reddit]"}
        or removed_by_category is not None
        or _bool_attr(comment, "removed", "is_removed", "banned_by_reddit")
    )
    is_truncated = _bool_attr(
        comment,
        "truncated",
        "is_truncated",
        "body_truncated",
        "body_is_truncated",
        "is_body_truncated",
    )
    depends_on_link = _bool_attr(comment, "depends_on_link", "is_link_dependent") or bool(
        body and LINK_RE.search(body)
    )
    depends_on_screenshot = _bool_attr(
        comment,
        "depends_on_screenshot",
        "is_screenshot_dependent",
    )
    has_external_payload = _has_attr_payload(
        comment,
        "attachments",
        "media",
        "media_metadata",
        "gallery_data",
        "outbound_links",
    )
    depends_on_external_context = (
        depends_on_link
        or depends_on_screenshot
        or has_external_payload
        or _bool_attr(
            comment,
            "depends_on_external_context",
            "depends_on_screenshot_or_link",
            "has_external_dependency",
        )
    )

    response_id = _text(getattr(comment, "id", None))
    parent_id = _text(getattr(comment, "parent_id", None))
    depth = _integer(getattr(comment, "depth", None))
    return {
        "id": response_id,
        "author": author,
        "score": _integer(getattr(comment, "score", None)),
        "body": body,
        "source_url": _permalink(comment),
        "parent_id": parent_id,
        "depth": depth,
        "is_top_level": bool(parent_id and parent_id.casefold() == f"t3_{prompt_id.casefold()}" and depth in (None, 0)),
        "is_deleted": is_deleted,
        "is_removed": is_removed,
        "removed_by_category": removed_by_category,
        "is_truncated": is_truncated,
        "complete": bool(body and not is_deleted and not is_removed and not is_truncated),
        "depends_on_link": depends_on_link,
        "depends_on_screenshot": depends_on_screenshot,
        "depends_on_screenshot_or_link": depends_on_link or depends_on_screenshot,
        "depends_on_external_context": depends_on_external_context,
        "has_external_dependency": has_external_payload,
    }


def _response_order(item: dict[str, Any]) -> tuple[Any, ...]:
    score = item.get("score")
    score_key = -score if isinstance(score, int) and not isinstance(score, bool) else float("inf")
    response_id = str(item.get("id") or "")
    stable = json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return score_key, response_id, stable


def snapshot_submission(
    submission: Any,
    *,
    truth_mode: str,
    response_scan_limit: int,
    query: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create the exact network-free snapshot schema consumed by the collector."""
    if truth_mode not in TRUTH_MODES:
        raise ThreadSourceError(f"unsupported truth_mode: {truth_mode}")
    if not MIN_RESPONSES <= response_scan_limit <= MAX_RESPONSE_SCAN_LIMIT:
        raise ThreadSourceError(
            f"response_scan_limit must be between {MIN_RESPONSES} and {MAX_RESPONSE_SCAN_LIMIT}"
        )

    prompt_id = _text(getattr(submission, "id", None))
    if not prompt_id:
        raise ThreadSourceError("submission has no prompt id")

    # PRAW applies these values to the first comment-forest request.  We do not
    # call replace_more(), which would turn a bounded read into an unbounded one.
    submission.comment_sort = "top"
    submission.comment_limit = response_scan_limit
    forest = getattr(submission, "comments", None)
    if forest is None:
        raise ThreadSourceError(f"submission {prompt_id} has no comment forest")

    responses: list[dict[str, Any]] = []
    for visited, comment in enumerate(forest):
        if visited >= response_scan_limit:
            break
        # MoreComments placeholders have no concrete comment body/id and are
        # intentionally left unresolved to preserve the network bound.
        if not hasattr(comment, "body") and not hasattr(comment, "id"):
            continue
        responses.append(_comment_snapshot(comment, prompt_id))
    responses.sort(key=_response_order)

    selftext = getattr(submission, "selftext", "")
    prompt_body = str(selftext).replace("\r\n", "\n").replace("\r", "\n") if selftext is not None else ""
    snapshot: dict[str, Any] = {
        "snapshot_version": 1,
        "source_adapter": "acc1_thread_source.praw_bounded_v1",
        "truth_mode": truth_mode,
        "prompt": {
            "id": prompt_id,
            "subreddit": _subreddit_name(submission),
            "author": _author(getattr(submission, "author", None)),
            "score": _integer(getattr(submission, "score", None)),
            "title": _text(getattr(submission, "title", None)),
            "body": prompt_body,
            "source_url": _permalink(submission),
        },
        "responses": responses,
    }
    if query:
        snapshot["query"] = dict(query)
    return snapshot


def _submission_rejection(submission: Any, expected_subreddit: str) -> list[str]:
    reasons: list[str] = []
    prompt_id = _text(getattr(submission, "id", None))
    title = _text(getattr(submission, "title", None))
    source_url = _permalink(submission)
    subreddit = _subreddit_name(submission)
    comments = _integer(getattr(submission, "num_comments", None))
    selftext = _text(getattr(submission, "selftext", ""))

    if not prompt_id:
        reasons.append("missing_prompt_id")
    if not title:
        reasons.append("missing_prompt_title")
    if not source_url:
        reasons.append("missing_prompt_permalink")
    if not subreddit or subreddit.casefold() != expected_subreddit.casefold():
        reasons.append("subreddit_mismatch")
    if getattr(submission, "stickied", False) is True:
        reasons.append("stickied_prompt")
    if getattr(submission, "is_self", True) is False:
        reasons.append("link_post_not_prompt")
    if selftext and selftext.casefold() in REMOVED_MARKERS:
        reasons.append("deleted_or_removed_prompt")
    if comments is None:
        reasons.append("missing_comment_count")
    elif comments < MIN_RESPONSES:
        reasons.append("insufficient_comment_count")
    return sorted(set(reasons))


def _candidate_order(submission: Any) -> tuple[Any, ...]:
    score = _integer(getattr(submission, "score", None))
    comments = _integer(getattr(submission, "num_comments", None))
    return (
        -(score if score is not None else -1),
        -(comments if comments is not None else -1),
        _text(getattr(submission, "id", None)) or "",
    )


def _candidate_submissions(
    reddit: Any,
    *,
    subreddit_name: str,
    time_filter: str,
    candidate_limit: int,
    prompt_id: str | None,
    search_query: str | None = None,
) -> list[Any]:
    if prompt_id:
        return [reddit.submission(id=prompt_id)]
    subreddit = reddit.subreddit(subreddit_name)
    if search_query:
        submissions = subreddit.search(
            search_query,
            sort="top",
            time_filter=time_filter,
            limit=candidate_limit,
        )
    else:
        submissions = subreddit.top(time_filter=time_filter, limit=candidate_limit)
    candidates = list(submissions)
    return sorted(candidates, key=_candidate_order)


def collect_thread_source(
    reddit: Any,
    *,
    subreddit_name: str = DEFAULT_SUBREDDIT,
    time_filter: str = DEFAULT_TIME_FILTER,
    candidate_limit: int = DEFAULT_CANDIDATE_LIMIT,
    response_scan_limit: int = DEFAULT_RESPONSE_SCAN_LIMIT,
    max_responses: int = MAX_RESPONSES,
    truth_mode: str = "unverified_personal_account",
    prompt_id: str | None = None,
    search_query: str | None = None,
    require_episode_runtime: bool = False,
    excluded_prompt_ids: set[str] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Backward-compatible wrapper returning the first valid finalist."""
    return collect_thread_source_candidates(
        reddit,
        subreddit_name=subreddit_name,
        time_filter=time_filter,
        candidate_limit=candidate_limit,
        response_scan_limit=response_scan_limit,
        max_responses=max_responses,
        truth_mode=truth_mode,
        prompt_id=prompt_id,
        search_query=search_query,
        finalist_limit=1,
        require_episode_runtime=require_episode_runtime,
        excluded_prompt_ids=excluded_prompt_ids,
    )[0]


def collect_thread_source_candidates(
    reddit: Any,
    *,
    subreddit_name: str = DEFAULT_SUBREDDIT,
    time_filter: str = DEFAULT_TIME_FILTER,
    candidate_limit: int = DEFAULT_CANDIDATE_LIMIT,
    response_scan_limit: int = DEFAULT_RESPONSE_SCAN_LIMIT,
    max_responses: int = MAX_RESPONSES,
    truth_mode: str = "unverified_personal_account",
    prompt_id: str | None = None,
    search_query: str | None = None,
    finalist_limit: int = 3,
    require_episode_runtime: bool = True,
    excluded_prompt_ids: set[str] | None = None,
) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    """Evaluate the bounded pool and return up to five production-fit prompts."""
    subreddit_name = (subreddit_name or "").strip()
    prompt_id = (prompt_id or "").strip() or None
    search_query = (search_query or "").strip() or None
    excluded = {
        str(value).strip().casefold()
        for value in (excluded_prompt_ids or set())
        if str(value).strip()
    }
    if not subreddit_name:
        raise ThreadSourceError("subreddit_name is required")
    if time_filter not in TIME_FILTERS:
        raise ThreadSourceError(f"time_filter must be one of: {', '.join(TIME_FILTERS)}")
    if not 1 <= candidate_limit <= MAX_CANDIDATE_LIMIT:
        raise ThreadSourceError(f"candidate_limit must be between 1 and {MAX_CANDIDATE_LIMIT}")
    if not 1 <= finalist_limit <= MAX_FINALIST_LIMIT:
        raise ThreadSourceError(
            f"finalist_limit must be between 1 and {MAX_FINALIST_LIMIT}"
        )
    if not MIN_RESPONSES <= response_scan_limit <= MAX_RESPONSE_SCAN_LIMIT:
        raise ThreadSourceError(
            f"response_scan_limit must be between {MIN_RESPONSES} and {MAX_RESPONSE_SCAN_LIMIT}"
        )
    if not MIN_RESPONSES <= max_responses <= MAX_RESPONSES:
        raise ThreadSourceError(
            f"max_responses must be between {MIN_RESPONSES} and {MAX_RESPONSES}"
        )
    if max_responses > response_scan_limit:
        raise ThreadSourceError("max_responses cannot exceed response_scan_limit")
    if truth_mode not in TRUTH_MODES:
        raise ThreadSourceError(f"truth_mode must be one of: {', '.join(sorted(TRUTH_MODES))}")
    if prompt_id and prompt_id.casefold() in excluded:
        raise ThreadSourceError("exact prompt_id is excluded by publication history")

    candidates = _candidate_submissions(
        reddit,
        subreddit_name=subreddit_name,
        time_filter=time_filter,
        candidate_limit=candidate_limit,
        prompt_id=prompt_id,
        search_query=search_query,
    )
    if not candidates:
        raise ThreadSourceError("bounded Reddit read returned no prompt candidates")

    failures: list[str] = []
    results: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for submission in candidates[:candidate_limit]:
        candidate_id = _text(getattr(submission, "id", None)) or "unknown"
        if candidate_id.casefold() in excluded:
            failures.append(f"{candidate_id}: excluded_by_publication_history")
            continue
        rejection = _submission_rejection(submission, subreddit_name)
        if rejection:
            failures.append(f"{candidate_id}: {','.join(rejection)}")
            continue
        query = {
            "mode": "prompt_id" if prompt_id else "subreddit_search" if search_query else "subreddit_top",
            "subreddit": subreddit_name,
            "time_filter": time_filter,
            "candidate_limit": candidate_limit,
            "response_scan_limit": response_scan_limit,
            "selected_prompt_id": candidate_id,
            "excluded_prompt_id_count": len(excluded),
        }
        if search_query:
            query["search_query"] = search_query
        try:
            snapshot = snapshot_submission(
                submission,
                truth_mode=truth_mode,
                response_scan_limit=response_scan_limit,
                query=query,
            )
            manifest = collect_thread(
                snapshot,
                max_responses=max_responses,
                require_episode_runtime=require_episode_runtime,
            )
        except (ThreadCollectorError, ThreadSourceError) as exc:
            failures.append(f"{candidate_id}: {exc}")
            continue
        results.append((snapshot, manifest))
        if len(results) >= finalist_limit:
            break

    if results:
        return results

    detail = "; ".join(failures) if failures else "all candidates were ineligible"
    raise ThreadSourceError(f"no bounded prompt produced a valid THREAD: {detail}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--confirm-reddit-read",
        action="store_true",
        help="Required acknowledgement that this command performs a live read-only Reddit request",
    )
    parser.add_argument("--prompt-id", help="Use one exact Reddit submission instead of discovery")
    parser.add_argument("--search-query", help="Bound discovery to one exact subreddit search query")
    parser.add_argument("--subreddit", default=DEFAULT_SUBREDDIT)
    parser.add_argument("--time-filter", choices=TIME_FILTERS, default=DEFAULT_TIME_FILTER)
    parser.add_argument(
        "--candidate-limit",
        type=int,
        choices=range(1, MAX_CANDIDATE_LIMIT + 1),
        default=DEFAULT_CANDIDATE_LIMIT,
    )
    parser.add_argument(
        "--response-scan-limit",
        type=int,
        choices=range(MIN_RESPONSES, MAX_RESPONSE_SCAN_LIMIT + 1),
        default=DEFAULT_RESPONSE_SCAN_LIMIT,
    )
    parser.add_argument(
        "--max-responses",
        type=int,
        choices=range(MIN_RESPONSES, MAX_RESPONSES + 1),
        default=MAX_RESPONSES,
    )
    parser.add_argument(
        "--truth-mode",
        choices=tuple(sorted(TRUTH_MODES)),
        default="unverified_personal_account",
    )
    parser.add_argument(
        "--require-episode-runtime",
        action="store_true",
        help="Require 1950-3250 aggregate response words for a production THREAD",
    )
    parser.add_argument("--snapshot-output", required=True)
    parser.add_argument("--manifest-output", required=True)
    args = parser.parse_args(argv)

    if not args.confirm_reddit_read:
        print(
            json.dumps(
                {
                    "status": "BLOCKED",
                    "error": "live Reddit read requires explicit --confirm-reddit-read",
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 2

    snapshot_output = Path(args.snapshot_output)
    manifest_output = Path(args.manifest_output)
    if snapshot_output.resolve() == manifest_output.resolve():
        print(
            json.dumps(
                {"status": "BLOCKED", "error": "snapshot and manifest outputs must differ"},
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 2

    try:
        import scraper

        reddit = scraper.get_reddit()
        snapshot, manifest = collect_thread_source(
            reddit,
            subreddit_name=args.subreddit,
            time_filter=args.time_filter,
            candidate_limit=args.candidate_limit,
            response_scan_limit=args.response_scan_limit,
            max_responses=args.max_responses,
            truth_mode=args.truth_mode,
            prompt_id=args.prompt_id,
            search_query=args.search_query,
            require_episode_runtime=args.require_episode_runtime,
        )
        snapshot_text = json.dumps(snapshot, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        manifest_text = json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        snapshot_output.parent.mkdir(parents=True, exist_ok=True)
        manifest_output.parent.mkdir(parents=True, exist_ok=True)
        snapshot_output.write_text(snapshot_text, encoding="utf-8")
        manifest_output.write_text(manifest_text, encoding="utf-8")
    except Exception as exc:
        print(
            json.dumps(
                {"status": "BLOCKED", "error": str(exc)},
                ensure_ascii=False,
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 1

    print(
        json.dumps(
            {
                "status": "READY",
                "prompt_id": manifest["prompt"]["id"],
                "response_count": manifest["response_count"],
                "snapshot_output": str(snapshot_output),
                "manifest_output": str(manifest_output),
                "manifest_sha256": manifest["manifest_sha256"],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
