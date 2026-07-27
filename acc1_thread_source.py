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
    MAX_EPISODE_RESPONSE_WORDS,
    MIN_EPISODE_RESPONSE_WORDS,
    PRODUCTION_MAX_RESPONSES,
    PRODUCTION_MIN_RESPONSES,
    TRUTH_MODES,
    ThreadCollectorError,
    collect_thread,
)


DEFAULT_SUBREDDIT = "AskReddit"
DEFAULT_TIME_FILTER = "month"
DEFAULT_CANDIDATE_LIMIT = 10
DEFAULT_RESPONSE_SCAN_LIMIT = 50
DEFAULT_SEARCH_SORT = "comments"
OAUTH_REQUEST_BUDGET = 1
MAX_CANDIDATE_LIMIT = 43
MAX_RESPONSE_SCAN_LIMIT = 100
MAX_FINALIST_LIMIT = 5
MAX_SEARCH_QUERIES = 4
MAX_SEARCH_QUERY_CHARACTERS = 512
TIME_FILTERS = ("day", "week", "month", "year", "all")
REMOVED_MARKERS = {"[deleted]", "[removed]", "[removed by reddit]"}
LINK_RE = re.compile(r"(?:https?://|www\.|\[[^\]]+\]\([^\)]+\))", re.IGNORECASE)
STORY_PROMPT_SIGNALS = (
    "story",
    "stories",
    "experience",
    "experiences",
    "happened",
    "aftermath",
    "moment",
    "moments",
    "situation",
    "situations",
    "event",
    "events",
    "incident",
    "incidents",
)
NARRATIVE_CONSEQUENCE_PATTERNS = tuple(
    (signal, re.compile(pattern, re.IGNORECASE))
    for signal, pattern in (
        (
            "discovery_or_reveal",
            r"\b(?:discover(?:ed|y)?|reveal(?:ed)?|expos(?:e|ed)|"
            r"found\s+out|learned\s+the\s+truth)\b",
        ),
        (
            "aftermath_or_consequence",
            r"\b(?:aftermath|fallout|consequences?|what\s+happened\s+"
            r"(?:after|next)|changed\s+(?:you|your|how|the\s+way)|ruined|ended)\b",
        ),
        (
            "secret_or_confession",
            r"\b(?:family\s+secret|dark\s+secret|secret|confession)\b",
        ),
        (
            "reality_glitch",
            r"\b(?:glitches?\s+(?:in\s+)?(?:the\s+matrix|reality)|"
            r"time\s+slip|lost\s+time|time\s+loop)\b",
        ),
        (
            "impossible_or_unexplained",
            r"\b(?:impossible\s+coincidence|unexplained\s+"
            r"(?:event|incident|experience)|question(?:ed|ing)?\s+reality|"
            r"reality\s+(?:felt|seemed)\s+wrong)\b",
        ),
        (
            "explicit_follow_through",
            r"\b(?:what\s+did\s+you\s+do\s+(?:after|next)|"
            r"how\s+did\s+it\s+end|how\s+did\s+it\s+change)\b",
        ),
    )
)
SHALLOW_PROMPT_PATTERNS = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\bone\s+word\b",
        r"\bwithout\s+saying\b",
        r"\bname\s+(?:a|one)\b",
        r"\bwhat(?:'s|\s+is)\s+a\s+word\b",
        r"\bfinish\s+the\s+sentence\b",
        r"\bwrong\s+answers?\s+only\b",
        r"\bwhat(?:'s|\s+is|\s+was)\s+(?:your|the)\s+most\s+"
        r"(?:embarrassing|awkward)\b",
        r"\bmost\s+(?:embarrassing|awkward)\s+(?:moment|thing)\b",
        r"\bsecret\s+you(?:'ve|\s+have)\s+never\s+told\b",
    )
)


class ThreadSourceError(RuntimeError):
    """Raised when a bounded Reddit read cannot produce a valid THREAD."""

    def __init__(
        self,
        message: str,
        *,
        diagnostics: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.diagnostics = diagnostics or {}


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


def _submission_rejection(
    submission: Any,
    expected_subreddit: str,
    *,
    minimum_comments: int = MIN_RESPONSES,
) -> list[str]:
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
    elif comments < minimum_comments:
        reasons.append("insufficient_comment_count")
    return sorted(set(reasons))


def _story_prompt_ranking_evidence(submission: Any) -> dict[str, Any]:
    title = _text(getattr(submission, "title", None)) or ""
    selftext = _text(getattr(submission, "selftext", "")) or ""
    prompt_text = f"{title} {selftext}".casefold()
    prompt_tokens = set(re.findall(r"[a-z]+", prompt_text))
    matched_story_signals = sorted(
        signal for signal in STORY_PROMPT_SIGNALS if signal in prompt_tokens
    )
    shallow_patterns = sorted(
        pattern.pattern for pattern in SHALLOW_PROMPT_PATTERNS if pattern.search(prompt_text)
    )
    matched_narrative_consequence_signals = sorted(
        signal
        for signal, pattern in NARRATIVE_CONSEQUENCE_PATTERNS
        if pattern.search(prompt_text)
    )
    return {
        "matched_story_signals": matched_story_signals,
        "story_signal_count": len(matched_story_signals),
        "matched_narrative_consequence_signals": (
            matched_narrative_consequence_signals
        ),
        "narrative_consequence_signal_count": len(
            matched_narrative_consequence_signals
        ),
        "shallow_prompt_patterns": shallow_patterns,
        "shallow_prompt": bool(shallow_patterns),
    }


def _candidate_order(submission: Any) -> tuple[Any, ...]:
    score = _integer(getattr(submission, "score", None))
    comments = _integer(getattr(submission, "num_comments", None))
    ranking = _story_prompt_ranking_evidence(submission)
    return (
        1 if ranking["shallow_prompt"] else 0,
        -ranking["narrative_consequence_signal_count"],
        -ranking["story_signal_count"],
        -(comments if comments is not None else -1),
        -(score if score is not None else -1),
        _text(getattr(submission, "id", None)) or "",
    )


def _normalize_search_queries(
    *,
    search_query: str | None,
    search_queries: Iterable[str] | None,
) -> tuple[str, ...]:
    legacy_query = (search_query or "").strip() or None
    if isinstance(search_queries, str):
        raise ThreadSourceError("search_queries must be an iterable of complete query strings")
    configured = list(search_queries or ())
    if legacy_query and configured:
        raise ThreadSourceError("search_query and search_queries are mutually exclusive")

    raw_queries: list[Any] = configured if configured else ([legacy_query] if legacy_query else [])
    normalized: list[str] = []
    for value in raw_queries:
        if not isinstance(value, str):
            raise ThreadSourceError("every search query must be a string")
        query = value.strip()
        if not query:
            raise ThreadSourceError("search queries cannot be empty")
        if len(query) > MAX_SEARCH_QUERY_CHARACTERS:
            raise ThreadSourceError(
                f"search queries cannot exceed {MAX_SEARCH_QUERY_CHARACTERS} characters"
            )
        if query not in normalized:
            normalized.append(query)
    if len(normalized) > MAX_SEARCH_QUERIES:
        raise ThreadSourceError(
            f"search query portfolio cannot exceed {MAX_SEARCH_QUERIES} queries"
        )
    return tuple(normalized)


def _candidate_submissions(
    reddit: Any,
    *,
    subreddit_name: str,
    time_filter: str,
    candidate_limit: int,
    prompt_id: str | None,
    search_queries: tuple[str, ...] = (),
    search_sort: str = DEFAULT_SEARCH_SORT,
) -> list[dict[str, Any]]:
    if prompt_id:
        submission = reddit.submission(id=prompt_id)
        return [{
            "submission": submission,
            "matched_search_queries": [],
            "ranking_evidence": _story_prompt_ranking_evidence(submission),
        }]
    subreddit = reddit.subreddit(subreddit_name)
    discovered: dict[str, dict[str, Any]] = {}
    if search_queries:
        for query_index, query in enumerate(search_queries):
            submissions = subreddit.search(
                query,
                sort=search_sort,
                syntax="lucene",
                time_filter=time_filter,
                limit=candidate_limit,
            )
            for result_index, submission in enumerate(submissions):
                candidate_id = _text(getattr(submission, "id", None))
                identity = (
                    f"id:{candidate_id.casefold()}"
                    if candidate_id
                    else f"missing:{query_index}:{result_index}"
                )
                existing = discovered.get(identity)
                if existing is None:
                    discovered[identity] = {
                        "submission": submission,
                        "matched_search_queries": [query],
                        "ranking_evidence": _story_prompt_ranking_evidence(submission),
                    }
                elif query not in existing["matched_search_queries"]:
                    existing["matched_search_queries"].append(query)
    else:
        for result_index, submission in enumerate(
            subreddit.top(time_filter=time_filter, limit=candidate_limit)
        ):
            candidate_id = _text(getattr(submission, "id", None))
            identity = (
                f"id:{candidate_id.casefold()}"
                if candidate_id
                else f"missing:top:{result_index}"
            )
            discovered[identity] = {
                "submission": submission,
                "matched_search_queries": [],
                "ranking_evidence": _story_prompt_ranking_evidence(submission),
            }
    candidates = list(discovered.values())
    return sorted(candidates, key=lambda item: _candidate_order(item["submission"]))


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
    search_queries: Iterable[str] | None = None,
    search_sort: str = DEFAULT_SEARCH_SORT,
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
        search_queries=search_queries,
        search_sort=search_sort,
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
    search_queries: Iterable[str] | None = None,
    search_sort: str = DEFAULT_SEARCH_SORT,
    finalist_limit: int = 3,
    minimum_finalists: int = 1,
    require_episode_runtime: bool = True,
    excluded_prompt_ids: set[str] | None = None,
) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    """Evaluate the bounded pool and return up to five production-fit prompts."""
    subreddit_name = (subreddit_name or "").strip()
    prompt_id = (prompt_id or "").strip() or None
    normalized_search_queries = _normalize_search_queries(
        search_query=search_query,
        search_queries=search_queries,
    )
    search_sort = (search_sort or "").strip()
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
    if not 1 <= minimum_finalists <= finalist_limit:
        raise ThreadSourceError(
            "minimum_finalists must be between 1 and finalist_limit"
        )
    if not MIN_RESPONSES <= response_scan_limit <= MAX_RESPONSE_SCAN_LIMIT:
        raise ThreadSourceError(
            f"response_scan_limit must be between {MIN_RESPONSES} and {MAX_RESPONSE_SCAN_LIMIT}"
        )
    if not MIN_RESPONSES <= max_responses <= MAX_RESPONSES:
        raise ThreadSourceError(
            f"max_responses must be between {MIN_RESPONSES} and {MAX_RESPONSES}"
        )
    if require_episode_runtime and not (
        PRODUCTION_MIN_RESPONSES <= max_responses <= PRODUCTION_MAX_RESPONSES
    ):
        raise ThreadSourceError(
            "production max_responses must be between "
            f"{PRODUCTION_MIN_RESPONSES} and {PRODUCTION_MAX_RESPONSES}"
        )
    if max_responses > response_scan_limit:
        raise ThreadSourceError("max_responses cannot exceed response_scan_limit")
    if truth_mode not in TRUTH_MODES:
        raise ThreadSourceError(f"truth_mode must be one of: {', '.join(sorted(TRUTH_MODES))}")
    if prompt_id and normalized_search_queries:
        raise ThreadSourceError("exact prompt_id cannot be combined with search queries")
    if normalized_search_queries and search_sort != DEFAULT_SEARCH_SORT:
        raise ThreadSourceError(
            f"THREAD discovery search_sort must equal {DEFAULT_SEARCH_SORT}"
        )
    if prompt_id and prompt_id.casefold() in excluded:
        raise ThreadSourceError("exact prompt_id is excluded by publication history")

    candidate_records = _candidate_submissions(
        reddit,
        subreddit_name=subreddit_name,
        time_filter=time_filter,
        candidate_limit=candidate_limit,
        prompt_id=prompt_id,
        search_queries=normalized_search_queries,
        search_sort=search_sort,
    )
    listing_request_budget = (
        1 if prompt_id or not normalized_search_queries else len(normalized_search_queries)
    )
    diagnostics: dict[str, Any] = {
        "version": 2,
        "status": "EVALUATING_THREAD_SOURCE",
        "subreddit": subreddit_name,
        "time_filter": time_filter,
        "search_sort": search_sort if normalized_search_queries else None,
        "search_syntax": "lucene" if normalized_search_queries else None,
        "search_queries": list(normalized_search_queries),
        "oauth_request_budget": OAUTH_REQUEST_BUDGET,
        "listing_request_budget": listing_request_budget,
        "comment_tree_request_budget": candidate_limit,
        "total_request_upper_bound": (
            OAUTH_REQUEST_BUDGET + listing_request_budget + candidate_limit
        ),
        "candidate_limit": candidate_limit,
        "response_scan_limit": response_scan_limit,
        "max_responses": max_responses,
        "finalist_limit": finalist_limit,
        "minimum_finalists": minimum_finalists,
        "require_episode_runtime": require_episode_runtime,
        "excluded_prompt_id_count": len(excluded),
        "unique_candidates_discovered": len(candidate_records),
        "candidate_outcomes": [],
    }
    if not candidate_records:
        diagnostics["status"] = "BLOCKED_NO_PROMPT_CANDIDATES"
        raise ThreadSourceError(
            "bounded Reddit read returned no prompt candidates",
            diagnostics=diagnostics,
        )

    failures: list[str] = []
    results: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for candidate_record in candidate_records[:candidate_limit]:
        submission = candidate_record["submission"]
        matched_search_queries = list(candidate_record["matched_search_queries"])
        candidate_id = _text(getattr(submission, "id", None)) or "unknown"
        outcome: dict[str, Any] = {
            "prompt_id": candidate_id,
            "title": _text(getattr(submission, "title", None)),
            "source_url": _permalink(submission),
            "score": _integer(getattr(submission, "score", None)),
            "num_comments": _integer(getattr(submission, "num_comments", None)),
            "matched_search_queries": matched_search_queries,
            "ranking_evidence": dict(candidate_record["ranking_evidence"]),
        }
        if candidate_id.casefold() in excluded:
            failures.append(f"{candidate_id}: excluded_by_publication_history")
            outcome.update({
                "status": "PRE_SNAPSHOT_REJECTED",
                "reason_codes": ["excluded_by_publication_history"],
            })
            diagnostics["candidate_outcomes"].append(outcome)
            continue
        rejection = _submission_rejection(
            submission,
            subreddit_name,
            minimum_comments=(
                PRODUCTION_MIN_RESPONSES
                if require_episode_runtime
                else MIN_RESPONSES
            ),
        )
        if rejection:
            failures.append(f"{candidate_id}: {','.join(rejection)}")
            outcome.update({
                "status": "PRE_SNAPSHOT_REJECTED",
                "reason_codes": rejection,
            })
            diagnostics["candidate_outcomes"].append(outcome)
            continue
        query = {
            "mode": (
                "prompt_id"
                if prompt_id
                else "subreddit_search_portfolio"
                if len(normalized_search_queries) > 1
                else "subreddit_search"
                if normalized_search_queries
                else "subreddit_top"
            ),
            "subreddit": subreddit_name,
            "time_filter": time_filter,
            "candidate_limit": candidate_limit,
            "response_scan_limit": response_scan_limit,
            "selected_prompt_id": candidate_id,
            "excluded_prompt_id_count": len(excluded),
            "oauth_request_budget": OAUTH_REQUEST_BUDGET,
            "listing_request_budget": listing_request_budget,
            "total_request_upper_bound": (
                OAUTH_REQUEST_BUDGET + listing_request_budget + candidate_limit
            ),
            "ranking_evidence": dict(candidate_record["ranking_evidence"]),
        }
        if normalized_search_queries:
            query.update({
                "search_queries": list(normalized_search_queries),
                "matched_search_queries": matched_search_queries,
                "search_sort": search_sort,
                "search_syntax": "lucene",
            })
            if len(normalized_search_queries) == 1:
                query["search_query"] = normalized_search_queries[0]
        snapshot: dict[str, Any] | None = None
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
            eligible_match = re.search(r"\bfound\s+(\d+)\b", str(exc))
            outcome.update({
                "status": "COLLECTOR_REJECTED",
                "failure": str(exc),
                "snapshot": snapshot,
            })
            if eligible_match:
                outcome["eligible_response_count"] = int(eligible_match.group(1))
            diagnostics["candidate_outcomes"].append(outcome)
            continue
        results.append((snapshot, manifest))
        outcome.update({
            "status": "VALID_FINALIST",
            "response_count": manifest.get("response_count"),
            "aggregate_response_word_count": manifest.get(
                "aggregate_response_word_count"
            ),
            "manifest_sha256": manifest.get("manifest_sha256"),
            "snapshot": snapshot,
        })
        diagnostics["candidate_outcomes"].append(outcome)
        if len(results) >= finalist_limit:
            break

    diagnostics["evaluated_candidate_count"] = len(diagnostics["candidate_outcomes"])
    diagnostics["valid_finalist_count"] = len(results)
    diagnostics["valid_finalist_ids"] = [
        str(manifest["prompt"]["id"])
        for _snapshot, manifest in results
    ]
    if len(results) >= minimum_finalists:
        return results

    detail = "; ".join(failures) if failures else "all candidates were ineligible"
    if results:
        diagnostics["status"] = "BLOCKED_INSUFFICIENT_VALID_THREADS"
        raise ThreadSourceError(
            "bounded Reddit read produced "
            f"{len(results)} valid THREAD finalists; requires at least "
            f"{minimum_finalists}: {detail}",
            diagnostics=diagnostics,
        )

    diagnostics["status"] = "BLOCKED_NO_VALID_THREAD"
    raise ThreadSourceError(
        f"no bounded prompt produced a valid THREAD: {detail}",
        diagnostics=diagnostics,
    )


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
        help=(
            "Require "
            f"{PRODUCTION_MIN_RESPONSES}-{PRODUCTION_MAX_RESPONSES} responses "
            f"and {MIN_EPISODE_RESPONSE_WORDS}-{MAX_EPISODE_RESPONSE_WORDS} "
            "aggregate response words for a production THREAD"
        ),
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
