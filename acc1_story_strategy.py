"""Fail-closed local strategy and greenlight contract for acc1 Reddit stories.

This module is intentionally additive.  It does not replace the proven
``reddit_horror_compilation`` artifact lane; horror remains one series inside
the broader Russian Reddit-story channel.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

from acc1_thread_contract import (
    THREAD_AGGREGATE_RESPONSE_WORD_COUNT,
    THREAD_COMIC_PAGE_COUNT,
    THREAD_RESPONSE_COUNT,
    THREAD_TARGET_DURATION_MINUTES,
    in_closed_range,
)


PILLAR_IDS = (
    "relationships_family",
    "work_money_justice",
    "confessions_awkward_taboo",
    "professions_human_experience",
    "strange_dark_unexplained",
)

FORMAT_CONTRACTS = {
    "SAGA": {
        "target_duration_minutes": [18, 30],
        "source_status": "manual_source_review_available",
    },
    "BUNDLE": {
        "target_duration_minutes": [18, 30],
        "story_count": [2, 5],
        "aggregate_source_word_count": [2340, 3900],
        "source_status": "local_selector_implemented_live_unverified",
    },
    "THREAD": {
        "target_duration_minutes": list(THREAD_TARGET_DURATION_MINUTES),
        "response_count": list(THREAD_RESPONSE_COUNT),
        "aggregate_response_word_count": list(
            THREAD_AGGREGATE_RESPONSE_WORD_COUNT
        ),
        "comic_page_count": list(THREAD_COMIC_PAGE_COUNT),
        "source_status": "local_contract_ready_github_canary_required",
    },
}

SOURCE_MODES = {"narrative_story", "question_prompt"}

SAGA_WORDS_PER_MINUTE = 130
FORMAT_PILLAR_SOURCE_FAMILY = {
    "SAGA": {
        "strange_dark_unexplained": "dark_curiosity",
    },
    "BUNDLE": {
        "relationships_family": "human_drama",
        "work_money_justice": "human_drama",
    },
    "THREAD": {
        "confessions_awkward_taboo": "human_experience_thread",
        "professions_human_experience": "human_experience_thread",
        "strange_dark_unexplained": "human_experience_thread",
    },
}
FORMAT_PILLAR_SUBREDDITS = {
    "SAGA": {
        "strange_dark_unexplained": (
            "nosleep", "LetsNotMeet", "creepyencounters", "Glitch_in_the_Matrix",
        ),
    },
    "BUNDLE": {
        "relationships_family": (
            "relationship_advice", "AmItheAsshole", "AITAH", "offmychest",
        ),
        "work_money_justice": (
            "MaliciousCompliance", "prorevenge", "talesfromyourserver", "tifu",
        ),
    },
    "THREAD": {
        "confessions_awkward_taboo": ("AskReddit",),
        "professions_human_experience": ("AskReddit",),
        "strange_dark_unexplained": ("AskReddit",),
    },
}
BUNDLE_PILOT_STORY_COUNTS = {
    "pilot_01": [2, 3],
    "pilot_02": [3, 5],
}
PILOT_FRANCHISE_CONTRACTS = {
    "pilot_01": {
        "franchise_id": "aita_family_conflict",
        "portfolio_role": "core",
        "packaging_rule": (
            "one concrete family or relationship conflict, visible opposing sides, "
            "and a source-backed reversal or payoff"
        ),
    },
    "pilot_02": {
        "franchise_id": "work_money_justice",
        "portfolio_role": "core",
        "packaging_rule": (
            "one concrete workplace or money injustice, clear escalation, and a "
            "source-backed consequence"
        ),
    },
    "pilot_03": {
        "franchise_id": "strange_dark_saga",
        "portfolio_role": "core",
        "packaging_rule": (
            "one impossible or frightening incident with escalating source-backed "
            "resolution and an explicit fiction or unverified-account label"
        ),
    },
    "pilot_04": {
        "franchise_id": "secrets_reveal_fallout_thread",
        "portfolio_role": "secondary",
        "packaging_rule": (
            "secrets and confessions only when the prompt asks for discovery, reveal, "
            "consequences, or aftermath; generic awkward lists are excluded"
        ),
    },
    "pilot_05": {
        "franchise_id": "professions_human_experience_thread",
        "portfolio_role": "experimental",
        "packaging_rule": (
            "unusual insider experiences with concrete narrative consequences; keep "
            "outside the core mix until comparable audience data exists"
        ),
    },
    "pilot_06": {
        "franchise_id": "matrix_unexplained_thread",
        "portfolio_role": "core",
        "packaging_rule": (
            "glitches in reality, time slips, impossible coincidences, or unexplained "
            "incidents with narrative detail and aftermath"
        ),
    },
}
THREAD_PILOT_SEARCH_QUERIES = {
    "pilot_04": (
        '"family secret" AND (discovered OR revealed OR exposed OR "found out")',
        '"dark secret" AND (discovered OR revealed OR exposed OR "found out")',
        "confession AND (aftermath OR fallout OR consequences OR changed)",
        "(secret OR confession) AND (discovered OR revealed OR exposed) "
        "AND (story OR experience OR happened)",
    ),
    "pilot_05": (
        "job AND (incident OR experience OR happened) AND (after OR changed OR learned)",
        "workplace AND (incident OR story OR experience) AND "
        "(consequence OR aftermath OR changed)",
        "profession AND (unusual OR strangest OR worst) AND (experience OR happened)",
        "career AND (incident OR experience OR happened) AND (learned OR changed)",
    ),
    "pilot_06": (
        "(unexplained OR unexplainable) "
        "AND (story OR experience OR happened OR witnessed)",
        "(paranormal OR supernatural) "
        "AND (story OR experience OR happened OR witnessed)",
        '("no proof" OR "no explanation") '
        "AND (story OR experience OR happened OR witnessed)",
        '("glitch in the matrix" OR "glitch in reality" OR "time slip" '
        'OR "lost time" OR "impossible coincidence") '
        "AND (story OR experience OR happened OR witnessed)",
    ),
}
THREAD_SEARCH_SORT = "comments"
THREAD_PILOT_TIME_FILTERS = {
    "pilot_04": "year",
    "pilot_05": "year",
    "pilot_06": "all",
}
THREAD_PILOT_PROMPT_POLICIES = {
    "pilot_06": "unexplained_first_v1",
}
ROUTABLE_SOURCE_STATUSES = {
    "SAGA": {"manual_forced_family_review", "ready"},
    "BUNDLE": {"local_selector_implemented_live_unverified", "ready"},
    "THREAD": {
        "local_contract_ready_github_canary_required",
        "manual_source_review_available",
        "ready",
    },
}
ARTIFACT_READY_THREAD_SOURCE_STATUSES = {
    "local_contract_ready_github_canary_required",
    "manual_source_review_available",
    "ready",
}
READY_THREAD_SOURCE_STATUSES = ARTIFACT_READY_THREAD_SOURCE_STATUSES
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
# Keep source-body counts identical across scraper, deterministic review,
# greenlight draft, and final greenlight validation.  Ages, dates, and money
# amounts are narration tokens too, so digits must not disappear at handoff.
WORD_RE = re.compile(r"[A-Za-z0-9']+")

EXPECTED_PILOT_MATRIX = (
    ("pilot_01", "BUNDLE", "relationships_family"),
    ("pilot_02", "BUNDLE", "work_money_justice"),
    ("pilot_03", "SAGA", "strange_dark_unexplained"),
    ("pilot_04", "THREAD", "confessions_awkward_taboo"),
    ("pilot_05", "THREAD", "professions_human_experience"),
    ("pilot_06", "THREAD", "strange_dark_unexplained"),
)
EXPECTED_PILOT_CYCLE_ORDER = (
    "pilot_01", "pilot_04", "pilot_02", "pilot_05", "pilot_03", "pilot_06",
)

GREENLIGHT_SCORE_MAX = {
    "title_thumbnail": 25,
    "cold_open": 20,
    "arc_payoff": 20,
    "viewer_promise": 15,
    "source_truth": 10,
    "originality_visual": 10,
}
GREENLIGHT_PASS_SCORE = 75
BLOCKING_VETO_FLAGS = {
    "incomplete_source",
    "screenshot_or_link_dependent",
    "fictional_as_real",
    "weak_or_missing_payoff",
    "no_visible_originality",
}
TRUTH_MODES = {"fiction", "unverified_personal_account"}


class StrategyContractError(RuntimeError):
    """Raised when an acc1 pilot cannot resolve to a safe source plan."""


def resolve_comment_plan(format_id: str, source_mode: str) -> dict[str, Any]:
    """Resolve whether an episode should include Reddit responses.

    Narrative SAGA episodes follow the source post and its authored updates;
    they do not append unrelated top comments. A SAGA based on an explicit
    question/advice prompt may add a small selected-answer coda. THREAD is the
    response-led format and therefore requires a larger response set.
    """
    normalized_format = _text(format_id).upper()
    normalized_source = _text(source_mode).lower()
    if normalized_format not in FORMAT_CONTRACTS:
        raise StrategyContractError("format must be SAGA, BUNDLE, or THREAD")
    if normalized_source not in SOURCE_MODES:
        raise StrategyContractError("source_mode must be narrative_story or question_prompt")
    if normalized_format == "THREAD":
        if normalized_source != "question_prompt":
            raise StrategyContractError("THREAD requires source_mode=question_prompt")
        return {
            "mode": "required_responses",
            "required": True,
            "count": list(THREAD_RESPONSE_COUNT),
            "use_comment_voice": True,
        }
    if normalized_format == "BUNDLE" and normalized_source != "narrative_story":
        raise StrategyContractError("BUNDLE requires source_mode=narrative_story")
    if normalized_source == "question_prompt":
        return {
            "mode": "selected_answers",
            "required": True,
            "count": [2, 4],
            "use_comment_voice": True,
        }
    return {
        "mode": "none",
        "required": False,
        "count": [0, 0],
        "use_comment_voice": False,
    }


def _text(value: Any) -> str:
    return str(value or "").strip()


def _require_text(mapping: Any, key: str, failures: list[str], prefix: str = "") -> str:
    value = mapping.get(key) if isinstance(mapping, dict) else None
    text = _text(value)
    if not text:
        failures.append(f"{prefix}{key} is required")
    return text


def _saga_word_range(target_minutes: list[int] | tuple[int, int]) -> list[int]:
    if len(target_minutes) != 2:
        raise StrategyContractError("SAGA target_duration_minutes must contain two values")
    minimum, maximum = target_minutes
    if not isinstance(minimum, int) or not isinstance(maximum, int) or minimum <= 0 or maximum < minimum:
        raise StrategyContractError("SAGA target_duration_minutes is invalid")
    return [minimum * SAGA_WORDS_PER_MINUTE, maximum * SAGA_WORDS_PER_MINUTE]


def _content_hash(payload: Any) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _verify_artifact_bindings(
    bindings: dict[str, Any],
    source_queue: dict[str, Any] | None,
    topic_review: dict[str, Any] | None,
    failures: list[str],
) -> bool | None:
    """Verify greenlight bindings against the actual canonical queue/review content.

    The evidence pair is mandatory.  Hash-shaped strings without the exact
    queue and review artifacts do not prove what was reviewed.
    """
    if source_queue is None and topic_review is None:
        failures.append("source_queue and topic_review are required for binding verification")
        return False
    if source_queue is None or topic_review is None:
        failures.append("source_queue and topic_review must be supplied together for binding verification")
        return False

    expected_source_hash = _content_hash(source_queue)
    review_without_hash = dict(topic_review)
    recorded_review_hash = _text(review_without_hash.pop("review_sha256", None))
    expected_review_hash = _content_hash(review_without_hash)
    recorded_source_hash = _text(topic_review.get("source_sha256"))

    if recorded_source_hash != expected_source_hash:
        failures.append("topic_review.source_sha256 does not match the source queue")
    if recorded_review_hash != expected_review_hash:
        failures.append("topic_review.review_sha256 does not match the review content")
    if _text(bindings.get("source_sha256")) != expected_source_hash:
        failures.append("artifact_bindings.source_sha256 does not match the source queue")
    if _text(bindings.get("review_sha256")) != expected_review_hash:
        failures.append("artifact_bindings.review_sha256 does not match the topic review")
    return not any("sha256 does not match" in item for item in failures)


def _verify_selected_saga_source(
    *,
    payload: dict[str, Any],
    source: dict[str, Any],
    pillar_id: str,
    source_queue: dict[str, Any] | None,
    topic_review: dict[str, Any] | None,
    failures: list[str],
) -> bool:
    """Bind the greenlight claims to one eligible reviewed SAGA candidate."""
    if source_queue is None or topic_review is None:
        return False
    source_plan = topic_review.get("source_plan")
    if not isinstance(source_plan, dict):
        failures.append("topic_review.source_plan is required")
        return False
    if source_queue.get("channel_id") != "acc1" or topic_review.get("channel_id") != "acc1":
        failures.append("source queue and topic review channel_id must both be acc1")
    if source_queue.get("format_intent") != "saga":
        failures.append("source queue format_intent must be saga")
    if source_queue.get("source_plan") != source_plan:
        failures.append("source queue and topic review must contain the same source_plan")
    if topic_review.get("review_mode") != "deterministic_full_body_saga":
        failures.append("topic review must use deterministic_full_body_saga")
    if topic_review.get("status") != "review_ready":
        failures.append("topic review status must be review_ready")
    if topic_review.get("production_authorized") is not False:
        failures.append("topic review production_authorized must be false")
    pilot_id = _text(payload.get("pilot_id"))
    if not pilot_id:
        failures.append("pilot_id is required for SAGA greenlight")
    elif pilot_id != _text(source_plan.get("pilot_id")):
        failures.append("pilot_id does not match topic_review.source_plan")
    if pillar_id != _text(source_plan.get("pillar")):
        failures.append("pillar does not match topic_review.source_plan")

    post_id = _text(source.get("post_id"))
    if not post_id:
        failures.append("source.post_id is required")
        return False
    matches = [
        item for item in topic_review.get("top_topics") or []
        if isinstance(item, dict) and _text(item.get("post_id")) == post_id
    ]
    if len(matches) != 1:
        failures.append("source.post_id must match exactly one eligible topic_review.top_topics candidate")
        return False
    candidate = matches[0]
    if candidate.get("review_status") != "SAGA_SOURCE_ELIGIBLE_FOR_GREENLIGHT":
        failures.append("selected topic-review candidate is not SAGA greenlight eligible")
    if candidate.get("blocking_reasons"):
        failures.append("selected topic-review candidate contains blocking reasons")
    if _text(candidate.get("pillar_id")) != pillar_id:
        failures.append("selected candidate pillar does not match greenlight pillar")

    source_urls = {_text(item) for item in source.get("source_urls") or [] if _text(item)}
    candidate_url = _text(candidate.get("source_url"))
    if not candidate_url or candidate_url not in source_urls:
        failures.append("source.source_urls do not include the reviewed candidate URL")
    comparisons = (
        ("source_body_sha256", "source_body_sha256"),
        ("truth_mode", "truth_mode"),
        ("source_word_count", "source_word_count"),
    )
    for source_key, candidate_key in comparisons:
        if source.get(source_key) != candidate.get(candidate_key):
            failures.append(f"source.{source_key} does not match the reviewed candidate")
    if source.get("payoff_complete") is not candidate.get("payoff_complete"):
        failures.append("source.payoff_complete does not match the reviewed candidate")
    if source.get("depends_on_screenshot_or_link") is not candidate.get("depends_on_screenshot_or_link"):
        failures.append("source dependency claim does not match the reviewed candidate")

    queue_matches = [
        item for item in source_queue.get("entries") or []
        if isinstance(item, dict) and _text(item.get("post_id")) == post_id
    ]
    if len(queue_matches) != 1:
        failures.append("source.post_id must match exactly one source_queue entry")
        source_body = ""
    else:
        queue_entry = queue_matches[0]
        source_body = str(queue_entry.get("source_body") or "")
        if not source_body.strip():
            failures.append("selected source_queue entry has no full source_body")
        elif hashlib.sha256(source_body.encode("utf-8")).hexdigest() != _text(candidate.get("source_body_sha256")):
            failures.append("selected source_queue body does not match the reviewed candidate hash")
        actual_word_count = len(WORD_RE.findall(source_body))
        if actual_word_count != candidate.get("source_word_count"):
            failures.append("selected source_queue word count does not match the reviewed candidate")
        queue_url = _text(queue_entry.get("url") or queue_entry.get("source_url"))
        if queue_url and queue_url != candidate_url:
            failures.append("selected source_queue URL does not match the reviewed candidate")

    payoff_evidence = _text(source.get("payoff_evidence"))
    if not payoff_evidence or payoff_evidence != _text(candidate.get("payoff_evidence")):
        failures.append("source.payoff_evidence must match the reviewed candidate")
    if source_body and payoff_evidence not in source_body:
        failures.append("source.payoff_evidence is not present in the full source body")

    cold_open = payload.get("cold_open") if isinstance(payload.get("cold_open"), dict) else {}
    cold_open_evidence = _text(cold_open.get("source_evidence"))
    if source_body and cold_open_evidence not in source_body:
        failures.append("cold_open.source_evidence is not present in the full source body")
    return not any(
        marker in item
        for item in failures
        for marker in (
            "topic_review.source_plan", "pilot_id", "pillar does not match",
            "source.post_id", "selected topic-review", "selected candidate",
            "reviewed candidate", "source dependency claim",
            "source_queue", "payoff_evidence", "cold_open.source_evidence",
            "source queue", "topic review",
        )
    )


def resolve_pilot_source_plan(channel: dict[str, Any], pilot_id: str) -> dict[str, Any]:
    """Resolve one configured acc1 pilot without consulting ``topic_mix``.

    Resolution proves only that the exact format/pillar/source contract is
    configured. ``artifact_ready`` may be true for a locally verified
    fail-closed contract, while ``production_ready`` remains false until the
    exact live source path has passed its GitHub canary. Routing therefore
    cannot be mistaken for live source proof.
    """
    if channel.get("id") != "acc1":
        raise StrategyContractError("pilot source plans are only defined for acc1")
    pilot_matches = [
        item for item in channel.get("pilot_matrix") or []
        if isinstance(item, dict) and item.get("id") == pilot_id
    ]
    if len(pilot_matches) != 1:
        raise StrategyContractError(f"pilot_id must match exactly one configured pilot: {pilot_id}")
    pilot = pilot_matches[0]
    format_id = _text(pilot.get("format")).upper()
    pillar_id = _text(pilot.get("pillar"))
    if pillar_id not in PILLAR_IDS:
        raise StrategyContractError(f"pilot {pilot_id} has an unknown pillar: {pillar_id}")
    expected_franchise = PILOT_FRANCHISE_CONTRACTS.get(pilot_id)
    if expected_franchise is None:
        raise StrategyContractError(f"pilot {pilot_id} has no canonical franchise contract")
    for key, expected_value in expected_franchise.items():
        if pilot.get(key) != expected_value:
            raise StrategyContractError(
                f"pilot {pilot_id} {key} must equal the canonical franchise contract"
            )

    formats = channel.get("episode_formats") if isinstance(channel.get("episode_formats"), dict) else {}
    format_contract = formats.get(format_id) if isinstance(formats.get(format_id), dict) else {}
    expected_contract = FORMAT_CONTRACTS.get(format_id)
    if expected_contract is None:
        raise StrategyContractError(f"pilot {pilot_id} has unsupported format: {format_id}")
    for key, expected_value in expected_contract.items():
        if format_contract.get(key) != expected_value:
            raise StrategyContractError(
                f"pilot {pilot_id} configured {format_id} {key} does not match the canonical contract"
            )

    topic_family = FORMAT_PILLAR_SOURCE_FAMILY[format_id].get(pillar_id)
    if not topic_family:
        raise StrategyContractError(
            f"pilot {pilot_id} pillar has no {format_id} source family: {pillar_id}"
        )
    family_rows = [
        item for item in channel.get("source_family_plan") or []
        if isinstance(item, dict)
        and _text(item.get("format")).upper() == format_id
        and _text(item.get("scraper_family")) == topic_family
    ]
    if len(family_rows) != 1:
        raise StrategyContractError(
            f"pilot {pilot_id} requires exactly one {format_id} source_family_plan row for {topic_family}"
        )
    source_family_status = _text(family_rows[0].get("status"))
    if source_family_status not in ROUTABLE_SOURCE_STATUSES[format_id]:
        raise StrategyContractError(
            f"pilot {pilot_id} source family {topic_family} has an unsupported status "
            f"({source_family_status or 'missing'})"
        )

    target_minutes = format_contract.get("target_duration_minutes")
    configured_subreddits = {
        _text(item).casefold(): _text(item)
        for item in channel.get("subreddits") or []
        if _text(item)
    }
    planned_subreddits: list[str] = []
    for required_subreddit in FORMAT_PILLAR_SUBREDDITS[format_id][pillar_id]:
        configured = configured_subreddits.get(required_subreddit.casefold())
        if not configured:
            raise StrategyContractError(
                f"pilot {pilot_id} requires configured subreddit {required_subreddit}"
            )
        planned_subreddits.append(configured)
    source_status = _text(format_contract.get("source_status"))
    thread_artifact_ready = (
        format_id == "THREAD"
        and source_status in ARTIFACT_READY_THREAD_SOURCE_STATUSES
        and source_family_status in ROUTABLE_SOURCE_STATUSES["THREAD"]
    )
    plan: dict[str, Any] = {
        "pilot_id": pilot_id,
        "format": format_id,
        "pillar": pillar_id,
        "topic_family": topic_family,
        "source_status": source_status,
        "source_family_status": source_family_status,
        "artifact_ready": thread_artifact_ready or format_id != "THREAD",
        "live_source_verified": source_status == "ready" and source_family_status == "ready",
        "production_ready": source_status == "ready" and source_family_status == "ready",
        "subreddits": planned_subreddits,
        "format_intent": format_id.casefold(),
        "target_duration_minutes": list(target_minutes),
        "franchise_id": expected_franchise["franchise_id"],
        "portfolio_role": expected_franchise["portfolio_role"],
        "packaging_rule": expected_franchise["packaging_rule"],
    }
    if format_id == "SAGA":
        plan.update({
            "source_mode": "narrative_story",
            "primary_story_count": 1,
            "source_word_count": _saga_word_range(target_minutes),
            "words_per_minute": SAGA_WORDS_PER_MINUTE,
        })
    elif format_id == "BUNDLE":
        configured_story_count = pilot.get("story_count")
        expected_story_count = BUNDLE_PILOT_STORY_COUNTS.get(pilot_id)
        if configured_story_count != expected_story_count:
            raise StrategyContractError(
                f"pilot {pilot_id} story_count must equal {expected_story_count}"
            )
        plan.update({
            "source_mode": "narrative_story",
            "story_count": list(configured_story_count),
            "aggregate_source_word_count": list(format_contract["aggregate_source_word_count"]),
            "words_per_minute": SAGA_WORDS_PER_MINUTE,
            # Long BUNDLE components are evergreen. Live evidence showed the
            # day window supplied no eligible component while the month pool
            # supplied nearly all usable sources; keep the same three-window
            # request envelope but replace day with year.
            "time_windows": ["week", "month", "year"],
        })
    else:
        configured_queries = pilot.get("search_queries")
        search_queries = (
            tuple(_text(value) for value in configured_queries)
            if isinstance(configured_queries, list)
            else ()
        )
        expected_queries = THREAD_PILOT_SEARCH_QUERIES.get(pilot_id)
        if not expected_queries or search_queries != expected_queries:
            raise StrategyContractError(
                f"pilot {pilot_id} search_queries must equal the canonical pillar portfolio"
            )
        search_sort = _text(pilot.get("search_sort"))
        if search_sort != THREAD_SEARCH_SORT:
            raise StrategyContractError(
                f"pilot {pilot_id} search_sort must equal {THREAD_SEARCH_SORT}"
            )
        search_time_filter = _text(pilot.get("search_time_filter"))
        expected_time_filter = THREAD_PILOT_TIME_FILTERS.get(pilot_id)
        if not expected_time_filter or search_time_filter != expected_time_filter:
            raise StrategyContractError(
                f"pilot {pilot_id} search_time_filter must equal "
                f"{expected_time_filter or 'a canonical THREAD window'}"
            )
        prompt_policy = _text(pilot.get("prompt_policy")) or None
        expected_prompt_policy = THREAD_PILOT_PROMPT_POLICIES.get(pilot_id)
        if prompt_policy != expected_prompt_policy:
            raise StrategyContractError(
                f"pilot {pilot_id} prompt_policy must equal "
                f"{expected_prompt_policy or 'the canonical default'}"
            )
        plan.update({
            "source_mode": "question_prompt",
            "response_count": list(format_contract["response_count"]),
            "aggregate_response_word_count": list(
                format_contract["aggregate_response_word_count"]
            ),
            "comic_page_count": list(format_contract["comic_page_count"]),
            "collector_contract": "bounded_top_level_full_body_v1",
            "search_queries": list(search_queries),
            "search_sort": search_sort,
            "search_time_filter": search_time_filter,
        })
        if prompt_policy is not None:
            plan["prompt_policy"] = prompt_policy
    return plan


def validate_channel_strategy(channel: dict[str, Any]) -> dict[str, Any]:
    """Validate the local-only broad acc1 strategy without provider access."""
    failures: list[str] = []
    if channel.get("id") != "acc1":
        failures.append("channel.id must be acc1")
    if channel.get("automation_enabled") is not False:
        failures.append("automation_enabled must remain false")
    if channel.get("videos_per_day") != 0:
        failures.append("videos_per_day must remain 0")
    if channel.get("strategy_status") != "broad_reddit_story_pilot_local_only":
        failures.append("strategy_status must be broad_reddit_story_pilot_local_only")
    if channel.get("topic_mix_status") != "superseded_pending_rebuild":
        failures.append("topic_mix_status must be superseded_pending_rebuild")

    cadence = channel.get("cadence_plan")
    if not isinstance(cadence, dict):
        failures.append("cadence_plan must be an object")
        cadence = {}
    if cadence.get("mode") != "fixed_six_slot_saga_bundle_thread_pilot_local_only":
        failures.append("cadence_plan.mode must use the fixed six-slot SAGA/BUNDLE/THREAD pilot")
    cycle_order = tuple(cadence.get("pilot_cycle_order") or [])
    if cycle_order != EXPECTED_PILOT_CYCLE_ORDER:
        failures.append("cadence_plan.pilot_cycle_order must match the canonical interleaved pilot cycle")
    if cadence.get("selection_policy") != "exact_cycle_slot_then_topic_playoff_no_cross_pillar_fallback":
        failures.append("cadence_plan.selection_policy must forbid cross-pillar fallback")

    pillars = channel.get("content_pillars")
    pillar_ids = tuple(item.get("id") for item in pillars or [] if isinstance(item, dict))
    if pillar_ids != PILLAR_IDS:
        failures.append("content_pillars must contain the five canonical pillar ids in order")

    formats = channel.get("episode_formats")
    if not isinstance(formats, dict):
        failures.append("episode_formats must be an object")
        formats = {}
    for format_id, expected in FORMAT_CONTRACTS.items():
        actual = formats.get(format_id)
        if not isinstance(actual, dict):
            failures.append(f"episode_formats.{format_id} is required")
            continue
        for key, expected_value in expected.items():
            if actual.get(key) != expected_value:
                failures.append(f"episode_formats.{format_id}.{key} must equal {expected_value!r}")

    matrix = channel.get("pilot_matrix")
    actual_matrix = tuple(
        (item.get("id"), item.get("format"), item.get("pillar"))
        for item in matrix or []
        if isinstance(item, dict)
    )
    if actual_matrix != EXPECTED_PILOT_MATRIX:
        failures.append("pilot_matrix must match the canonical six-pilot experiment")

    for pilot_id, format_id, _pillar_id in EXPECTED_PILOT_MATRIX:
        try:
            plan = resolve_pilot_source_plan(channel, pilot_id)
        except StrategyContractError as exc:
            failures.append(str(exc))
            continue
        if plan.get("format") != format_id:
            failures.append(f"pilot {pilot_id} resolved the wrong format")

    branding = channel.get("channel_branding")
    if not isinstance(branding, dict):
        failures.append("channel_branding must be an object")
    else:
        if branding.get("status") != "local_proposal_not_applied_to_youtube":
            failures.append("channel_branding.status must remain local_proposal_not_applied_to_youtube")
        _require_text(branding, "proposed_name", failures, "channel_branding.")
        _require_text(branding, "proposed_description", failures, "channel_branding.")

    return {
        "status": "PASS" if not failures else "BLOCKED",
        "failures": failures,
        "pillar_count": len(pillar_ids),
        "pilot_count": len(actual_matrix),
        "pilot_cycle_order": list(cycle_order),
        "bundle_source_ready": formats.get("BUNDLE", {}).get("source_status") == "ready",
        "thread_source_ready": formats.get("THREAD", {}).get("source_status")
        in ARTIFACT_READY_THREAD_SOURCE_STATUSES,
    }


def validate_greenlight(
    payload: dict[str, Any],
    channel: dict[str, Any] | None = None,
    *,
    source_queue: dict[str, Any] | None = None,
    topic_review: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Validate one no-spend pre-production episode greenlight artifact."""
    failures: list[str] = []
    warnings: list[str] = []

    if payload.get("channel_id") != "acc1":
        failures.append("channel_id must be acc1")
    if payload.get("publication_authorized") is not False:
        failures.append("publication_authorized must be false before external approval")

    bindings = payload.get("artifact_bindings")
    bindings_valid = isinstance(bindings, dict)
    if not bindings_valid:
        failures.append("artifact_bindings must be an object")
        bindings = {}
    else:
        for key in ("source_sha256", "review_sha256"):
            digest = _text(bindings.get(key))
            if not SHA256_RE.fullmatch(digest):
                failures.append(f"artifact_bindings.{key} must be a lowercase 64-character SHA-256")
                bindings_valid = False
    bindings_verified = _verify_artifact_bindings(
        bindings, source_queue, topic_review, failures,
    )

    format_id = _text(payload.get("format")).upper()
    pillar_id = _text(payload.get("pillar"))
    if format_id not in FORMAT_CONTRACTS:
        failures.append("format must be SAGA, BUNDLE, or THREAD")
    if pillar_id not in PILLAR_IDS:
        failures.append("pillar is not part of the acc1 viewer promise")

    source = payload.get("source")
    if not isinstance(source, dict):
        failures.append("source must be an object")
        source = {}
    if source.get("complete") is not True:
        failures.append("source.complete must be true")
    truth_mode = _text(source.get("truth_mode"))
    if truth_mode not in TRUTH_MODES:
        failures.append("source.truth_mode must be fiction or unverified_personal_account")
    if source.get("depends_on_screenshot_or_link") is not False:
        failures.append("source must not depend on a screenshot or outbound link")
    if source.get("fictional_as_real") is not False:
        failures.append("fictional_as_real must be false")
    if source.get("payoff_complete") is not True:
        failures.append("source.payoff_complete must be true")
    source_urls = source.get("source_urls")
    if not isinstance(source_urls, list) or not source_urls or not all(_text(item) for item in source_urls):
        failures.append("source.source_urls must contain at least one source URL")

    if format_id == "SAGA" and source.get("primary_story_count") != 1:
        failures.append("SAGA requires exactly one primary story")
    selected_source_verified = False
    if format_id == "SAGA":
        selected_source_verified = _verify_selected_saga_source(
            payload=payload,
            source=source,
            pillar_id=pillar_id,
            source_queue=source_queue,
            topic_review=topic_review,
            failures=failures,
        )
    if format_id == "BUNDLE":
        primary_story_count = source.get("primary_story_count")
        if (
            isinstance(primary_story_count, bool)
            or not isinstance(primary_story_count, int)
            or not 2 <= primary_story_count <= 5
        ):
            failures.append("BUNDLE requires 2-5 complete primary stories")
        failures.append(
            "BUNDLE greenlight requires a checksum-bound bundle manifest; binding is not implemented"
        )
    if format_id == "THREAD":
        response_count = source.get("response_count")
        if (
            not isinstance(response_count, int)
            or isinstance(response_count, bool)
            or not in_closed_range(response_count, THREAD_RESPONSE_COUNT)
        ):
            failures.append(
                "THREAD requires "
                f"{THREAD_RESPONSE_COUNT[0]}-{THREAD_RESPONSE_COUNT[1]} "
                "complete responses"
            )
        if source.get("responses_are_diverse") is not True:
            failures.append("THREAD responses_are_diverse must be true")
        thread_status = ""
        if isinstance(channel, dict):
            formats = channel.get("episode_formats")
            if isinstance(formats, dict) and isinstance(formats.get("THREAD"), dict):
                thread_status = _text(formats["THREAD"].get("source_status"))
        if thread_status not in READY_THREAD_SOURCE_STATUSES:
            failures.append(
                "THREAD collector is not ready in the channel strategy "
                f"(status={thread_status or 'unavailable'})"
            )

    packaging = payload.get("packaging_options")
    if not isinstance(packaging, list) or len(packaging) != 3:
        failures.append("packaging_options must contain exactly three distinct options")
    else:
        signatures: set[tuple[str, str]] = set()
        for index, option in enumerate(packaging):
            if not isinstance(option, dict):
                failures.append(f"packaging_options[{index}] must be an object")
                continue
            title = _require_text(option, "title", failures, f"packaging_options[{index}].")
            thumbnail = _require_text(
                option, "thumbnail_concept", failures, f"packaging_options[{index}]."
            )
            _require_text(
                option, "first_screen_promise", failures, f"packaging_options[{index}]."
            )
            signatures.add((title.casefold(), thumbnail.casefold()))
        if len(signatures) != 3:
            failures.append("packaging_options must be conceptually distinct")

    cold_open = payload.get("cold_open")
    if not isinstance(cold_open, dict):
        failures.append("cold_open must be an object")
    else:
        _require_text(cold_open, "text", failures, "cold_open.")
        _require_text(cold_open, "source_evidence", failures, "cold_open.")

    beats = payload.get("story_beats")
    if not isinstance(beats, list) or len([item for item in beats if _text(item)]) < 3:
        failures.append("story_beats must contain at least three concrete beats")

    originality = payload.get("originality_plan")
    if not isinstance(originality, dict):
        failures.append("originality_plan must be an object")
    else:
        for key in ("editorial_framing", "visual_beats", "sound_design"):
            _require_text(originality, key, failures, "originality_plan.")

    veto_flags = {_text(item) for item in payload.get("veto_flags") or [] if _text(item)}
    blocking_vetoes = sorted(veto_flags & BLOCKING_VETO_FLAGS)
    if blocking_vetoes:
        failures.append("blocking veto flags: " + ", ".join(blocking_vetoes))

    scores = payload.get("scores")
    total = 0
    if not isinstance(scores, dict):
        failures.append("scores must be an object")
    else:
        for key, maximum in GREENLIGHT_SCORE_MAX.items():
            value = scores.get(key)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                failures.append(f"scores.{key} must be numeric")
                continue
            if value < 0 or value > maximum:
                failures.append(f"scores.{key} must be between 0 and {maximum}")
                continue
            total += value
    total = round(total, 2)
    if total < GREENLIGHT_PASS_SCORE:
        failures.append(f"greenlight score must be at least {GREENLIGHT_PASS_SCORE}, got {total:g}")

    return {
        "status": "PASS" if not failures else "BLOCKED",
        "failures": failures,
        "warnings": warnings,
        "score": total,
        "minimum_score": GREENLIGHT_PASS_SCORE,
        "channel_id": payload.get("channel_id"),
        "pilot_id": payload.get("pilot_id"),
        "format": format_id or None,
        "pillar": pillar_id or None,
        "publication_authorized": False,
        "artifact_bindings": dict(bindings),
        "artifact_bindings_valid": bindings_valid,
        "artifact_bindings_verified": bindings_verified,
        "selected_source_verified": selected_source_verified,
    }


def _read_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--channels", default="channels.json")
    parser.add_argument("--greenlight")
    parser.add_argument("--source-queue")
    parser.add_argument("--topic-review")
    parser.add_argument("--pilot-id")
    args = parser.parse_args()

    config = _read_object(Path(args.channels))
    channel = next(
        (item for item in config.get("channels") or [] if item.get("id") == "acc1"),
        {},
    )
    report: dict[str, Any] = {"channel_strategy": validate_channel_strategy(channel)}
    if args.pilot_id:
        try:
            report["source_plan"] = {"status": "PASS", **resolve_pilot_source_plan(channel, args.pilot_id)}
        except StrategyContractError as exc:
            report["source_plan"] = {"status": "BLOCKED", "failures": [str(exc)]}
    if args.greenlight:
        source_queue = _read_object(Path(args.source_queue)) if args.source_queue else None
        topic_review = _read_object(Path(args.topic_review)) if args.topic_review else None
        report["episode_greenlight"] = validate_greenlight(
            _read_object(Path(args.greenlight)),
            channel=channel,
            source_queue=source_queue,
            topic_review=topic_review,
        )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if all(item.get("status") == "PASS" for item in report.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
