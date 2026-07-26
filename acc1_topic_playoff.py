"""Fail-closed topic playoff for one acc1 episode.

The module is deliberately provider-neutral.  A producer and an independent
critic may be powered by Gemini in the GitHub workflow, but this gate only
accepts their structured JSON after deterministic source checks have passed.
Reddit popularity is not treated as proof of truth or YouTube demand.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

from acc1_language_gate import is_russian_text
from acc1_thread_contract import (
    THREAD_AGGREGATE_RESPONSE_WORD_COUNT,
    THREAD_RESPONSE_COUNT,
    in_closed_range,
)
from compilation_narration import narration_preflight


SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
WORD_RE = re.compile(r"[^\W_]+", re.UNICODE)
TRUTH_MODES = {"fiction", "unverified_personal_account"}
FORMATS = {"SAGA", "BUNDLE", "THREAD"}
MIN_FINALISTS = 3
MIN_PASSING_FINALISTS = 3
EXCEPTIONAL_WINNER_MIN_CANDIDATES = 5
EXCEPTIONAL_WINNER_MIN_SCORE = 95
PASS_SCORE = 90
MIN_EVIDENCE_CHARACTERS = 24
MIN_EVIDENCE_WORDS = 4
MIN_EVIDENCE_UNIQUE_WORDS = 3
MAX_COLD_OPEN_NARRATION_CHARACTERS = 500
MAX_NARRATION_TOKEN_CHARACTERS = 80
MIN_COLD_OPEN_WORDS = 8
MAX_COLD_OPEN_WORDS = 30

SCORE_MAXIMA = {
    "hook_specificity": 15,
    "stakes_clarity": 10,
    "escalation": 10,
    "payoff": 15,
    "novelty": 10,
    "russian_fit": 10,
    "discussion_potential": 10,
    "renderability": 5,
    "packaging_honesty": 10,
    "source_truth": 5,
}
SCORE_MINIMA = {
    "hook_specificity": 12,
    "stakes_clarity": 8,
    "escalation": 8,
    "payoff": 12,
    "novelty": 7,
    "russian_fit": 8,
    "discussion_potential": 7,
    "renderability": 4,
    "packaging_honesty": 9,
    "source_truth": 5,
}
HARD_VETOES = {
    "incomplete_source",
    "missing_payoff",
    "screenshot_or_link_dependent",
    "fictional_as_real",
    "wrong_pillar",
    "duplicate_source",
    "mixed_truth_modes",
    "open_ending_misrepresented",
    "raw_url_in_narration",
    "viewer_promise_mismatch",
    "unverified_claim_presented_as_fact",
    "unsafe_or_advertiser_hostile",
}


class TopicPlayoffError(ValueError):
    """Raised when a playoff artifact cannot be trusted."""


def canonical_hash(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _text(value: Any) -> str:
    return str(value or "").strip()


def _word_count(value: str) -> int:
    return len(WORD_RE.findall(value))


def _fail(failures: list[str], message: str) -> None:
    if message not in failures:
        failures.append(message)


def _require_russian(
    value: Any,
    *,
    prefix: str,
    failures: list[str],
    minimum_words: int = 1,
    minimum_ratio: float = 0.55,
) -> None:
    if not is_russian_text(
        value,
        minimum_cyrillic_words=minimum_words,
        minimum_cyrillic_letter_ratio=minimum_ratio,
    ):
        _fail(failures, f"{prefix} must be demonstrably Russian")


def _validate_veto_flags(value: Any, *, prefix: str, failures: list[str]) -> None:
    """Require an explicit empty list for every passing decision.

    Known hard-veto names are prompt guidance, not an allowlist that can make
    an unknown risk disappear. Any declared veto blocks the candidate.
    """
    if not isinstance(value, list):
        _fail(failures, f"{prefix} must be a list")
        return
    normalized: list[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            _fail(failures, f"{prefix}[{index}] must be a non-empty string")
            continue
        normalized.append(item.strip())
    if normalized:
        _fail(failures, f"{prefix} contains veto flags: {', '.join(sorted(set(normalized)))}")


def _validate_source(source: Any, *, pillar: str, prefix: str) -> tuple[dict[str, Any] | None, list[str]]:
    failures: list[str] = []
    if not isinstance(source, dict):
        return None, [f"{prefix} must be an object"]
    source_id = _text(source.get("source_id") or source.get("post_id") or source.get("id"))
    body = str(source.get("body") or source.get("source_body") or "")
    body_sha = _text(source.get("body_sha256") or source.get("source_body_sha256"))
    source_url = _text(source.get("source_url") or source.get("url"))
    author = _text(source.get("author"))
    signature = _text(source.get("story_signature") or source.get("source_signature"))
    truth_mode = _text(source.get("truth_mode"))
    role = _text(source.get("role") or "story").lower()

    if not source_id:
        _fail(failures, f"{prefix}.source_id is required")
    if not body.strip():
        _fail(failures, f"{prefix}.body is required")
    actual_body_sha = hashlib.sha256(body.encode("utf-8")).hexdigest()
    if body_sha != actual_body_sha:
        _fail(failures, f"{prefix}.body_sha256 does not match body")
    if not source_url.startswith("https://www.reddit.com/"):
        _fail(failures, f"{prefix}.source_url must be an official canonical Reddit URL")
    if not author:
        _fail(failures, f"{prefix}.author is required")
    if not signature:
        _fail(failures, f"{prefix}.story_signature is required")
    if truth_mode not in TRUTH_MODES:
        _fail(failures, f"{prefix}.truth_mode is invalid")
    if _text(source.get("pillar")) != pillar:
        _fail(failures, f"{prefix}.pillar does not match episode pillar")
    if source.get("complete") is not True:
        _fail(failures, f"{prefix}.complete must be true")
    if source.get("depends_on_screenshot_or_link") is not False:
        _fail(failures, f"{prefix} depends on a screenshot or outbound link")
    if source.get("fictional_as_real") is not False:
        _fail(failures, f"{prefix}.fictional_as_real must be false")
    if role not in {"story", "prompt", "response"}:
        _fail(failures, f"{prefix}.role must be story, prompt, or response")
    if role == "story" and source.get("payoff_complete") is not True:
        _fail(failures, f"{prefix}.payoff_complete must be true")

    normalized = dict(source)
    normalized.update(
        {
            "source_id": source_id,
            "body": body,
            "body_sha256": actual_body_sha,
            "source_url": source_url,
            "author": author,
            "story_signature": signature,
            "truth_mode": truth_mode,
            "role": role,
            "word_count": _word_count(body),
        }
    )
    return normalized, failures


def _validate_format_sources(
    *,
    format_id: str,
    pilot_id: str,
    sources: list[dict[str, Any]],
    failures: list[str],
) -> None:
    story_sources = [source for source in sources if source["role"] == "story"]
    prompts = [source for source in sources if source["role"] == "prompt"]
    responses = [source for source in sources if source["role"] == "response"]
    total_words = sum(source["word_count"] for source in sources)

    if format_id == "SAGA":
        if len(story_sources) != 1 or prompts or responses:
            _fail(failures, "SAGA requires exactly one story source")
        if not 2340 <= total_words <= 3900:
            _fail(failures, "SAGA source words must be between 2340 and 3900")
    elif format_id == "BUNDLE":
        expected = (2, 3) if pilot_id == "pilot_01" else (3, 5) if pilot_id == "pilot_02" else None
        if expected is None:
            _fail(failures, "BUNDLE is only valid for pilot_01 or pilot_02")
        elif not expected[0] <= len(story_sources) <= expected[1] or prompts or responses:
            _fail(failures, f"{pilot_id} BUNDLE requires {expected[0]}-{expected[1]} story sources")
        if not 2340 <= total_words <= 3900:
            _fail(failures, "BUNDLE aggregate source words must be between 2340 and 3900")
    elif format_id == "THREAD":
        if (
            story_sources
            or len(prompts) != 1
            or not in_closed_range(len(responses), THREAD_RESPONSE_COUNT)
        ):
            _fail(
                failures,
                "THREAD requires one prompt and "
                f"{THREAD_RESPONSE_COUNT[0]}-{THREAD_RESPONSE_COUNT[1]} responses",
            )
        response_words = sum(source["word_count"] for source in responses)
        if not in_closed_range(
            response_words,
            THREAD_AGGREGATE_RESPONSE_WORD_COUNT,
        ):
            _fail(
                failures,
                "THREAD response words must be between "
                f"{THREAD_AGGREGATE_RESPONSE_WORD_COUNT[0]} and "
                f"{THREAD_AGGREGATE_RESPONSE_WORD_COUNT[1]}",
            )

    if format_id in {"SAGA", "BUNDLE"}:
        truth_modes = {source["truth_mode"] for source in story_sources}
        if len(truth_modes) != 1:
            _fail(failures, "story episode must not mix truth modes")

    uniqueness_fields = {
        "source_id": [source["source_id"].casefold() for source in sources],
        "source_url": [source["source_url"].casefold() for source in sources],
        "body_sha256": [source["body_sha256"] for source in sources],
        "story_signature": [source["story_signature"] for source in sources],
        "author": [source["author"].casefold().removeprefix("u/") for source in sources],
    }
    for field, values in uniqueness_fields.items():
        if len(values) != len(set(values)):
            _fail(failures, f"sources contain duplicate {field}")


def _validate_named_evidence(
    value: Any,
    *,
    sources: list[dict[str, Any]],
    prefix: str,
    failures: list[str],
    ending_window: bool = False,
) -> bool:
    if not isinstance(value, dict):
        _fail(failures, f"{prefix} must be an object with source_id and source_quote")
        return False
    source_id = _text(value.get("source_id"))
    quote = _text(value.get("source_quote") or value.get("source_backing"))
    source = next((item for item in sources if item["source_id"] == source_id), None)
    if source is None:
        _fail(failures, f"{prefix}.source_id must name an exact candidate source")
    words = [match.group(0).casefold() for match in WORD_RE.finditer(quote)]
    if (
        len(quote) < MIN_EVIDENCE_CHARACTERS
        or len(words) < MIN_EVIDENCE_WORDS
        or len(set(words)) < MIN_EVIDENCE_UNIQUE_WORDS
    ):
        _fail(failures, f"{prefix}.source_quote is too generic to prove the claim")
    if source is None or not quote or quote not in source["body"]:
        _fail(failures, f"{prefix}.source_quote must be an exact quote from source_id")
        return False
    if ending_window:
        body = source["body"]
        tail = body[-max(800, len(body) // 4):]
        if quote not in tail:
            _fail(failures, f"{prefix}.source_quote must come from the source ending window")
            return False
    return not any(failure.startswith(prefix) for failure in failures)


def _validate_source_bound_direction(
    value: Any,
    *,
    sources_by_id: dict[str, dict[str, Any]],
    prefix: str,
    failures: list[str],
    direction_field: str = "direction",
) -> dict[str, str] | None:
    """Validate one creative instruction against one exact named source."""
    if not isinstance(value, dict):
        _fail(failures, f"{prefix} must be an object")
        return None

    direction = _text(value.get(direction_field))
    source_id = _text(value.get("source_id"))
    source_quote = _text(value.get("source_quote"))
    if not direction:
        _fail(failures, f"{prefix}.{direction_field} is required")
    else:
        _require_russian(
            direction,
            prefix=f"{prefix}.{direction_field}",
            failures=failures,
            minimum_words=2,
        )
    if not source_id:
        _fail(failures, f"{prefix}.source_id is required")
    source = sources_by_id.get(source_id)
    if source is None:
        _fail(failures, f"{prefix}.source_id must name an exact candidate source")
    if not source_quote:
        _fail(failures, f"{prefix}.source_quote is required")
    quote_words = [
        match.group(0).casefold() for match in WORD_RE.finditer(source_quote)
    ]
    if (
        source_quote
        and (
            len(source_quote) < MIN_EVIDENCE_CHARACTERS
            or len(quote_words) < MIN_EVIDENCE_WORDS
            or len(set(quote_words)) < MIN_EVIDENCE_UNIQUE_WORDS
        )
    ):
        _fail(
            failures,
            f"{prefix}.source_quote is too generic to prove the creative direction",
        )
    if source_quote and (source is None or source_quote not in source["body"]):
        _fail(
            failures,
            f"{prefix}.source_quote must be an exact quote from the named source_id",
        )
    if (
        not direction
        or source is None
        or not source_quote
        or source_quote not in source["body"]
        or len(source_quote) < MIN_EVIDENCE_CHARACTERS
        or len(quote_words) < MIN_EVIDENCE_WORDS
        or len(set(quote_words)) < MIN_EVIDENCE_UNIQUE_WORDS
    ):
        return None
    return {
        direction_field: direction,
        "source_id": source_id,
        "source_quote": source_quote,
    }


def _validate_creative_plan(
    candidate: dict[str, Any],
    sources: list[dict[str, Any]],
    failures: list[str],
) -> tuple[str | None, int]:
    """Require source-bound beats and original editorial/visual/sound direction."""
    initial_failure_count = len(failures)
    sources_by_id = {source["source_id"]: source for source in sources}
    normalized_beats: list[dict[str, str]] = []
    beats = candidate.get("story_beats")
    if not isinstance(beats, list) or not 3 <= len(beats) <= 12:
        _fail(failures, "story_beats must contain 3-12 source-bound beats")
    if isinstance(beats, list):
        for index, beat in enumerate(beats):
            normalized = _validate_source_bound_direction(
                beat,
                sources_by_id=sources_by_id,
                prefix=f"story_beats[{index}]",
                failures=failures,
                direction_field="beat",
            )
            if normalized is not None:
                normalized_beats.append(normalized)

        beat_directions = {
            " ".join(item["beat"].split()).casefold() for item in normalized_beats
        }
        beat_evidence = {
            (item["source_id"], item["source_quote"]) for item in normalized_beats
        }
        if (
            len(beat_directions) != len(normalized_beats)
            or len(beat_evidence) != len(normalized_beats)
        ):
            _fail(failures, "story_beats must be distinct in both beat and source evidence")

    normalized_originality: dict[str, dict[str, str]] = {}
    originality = candidate.get("originality_plan")
    if not isinstance(originality, dict):
        _fail(failures, "originality_plan must be an object")
    else:
        for field in ("editorial_frame", "visual_direction", "sound_direction"):
            normalized = _validate_source_bound_direction(
                originality.get(field),
                sources_by_id=sources_by_id,
                prefix=f"originality_plan.{field}",
                failures=failures,
            )
            if normalized is not None:
                normalized_originality[field] = normalized

    if len(failures) != initial_failure_count:
        return None, len(normalized_beats)
    normalized_plan = {
        "story_beats": normalized_beats,
        "originality_plan": normalized_originality,
    }
    return canonical_hash(normalized_plan), len(normalized_beats)


def _validate_packaging(candidate: dict[str, Any], sources: list[dict[str, Any]], failures: list[str]) -> None:
    options = candidate.get("packaging_options")
    if not isinstance(options, list) or len(options) != 3:
        _fail(failures, "packaging_options must contain exactly three options")
        return
    signatures: set[tuple[str, str, str]] = set()
    angles: set[str] = set()
    for index, option in enumerate(options):
        prefix = f"packaging_options[{index}]"
        if not isinstance(option, dict):
            _fail(failures, f"{prefix} must be an object")
            continue
        title = _text(option.get("youtube_title") or option.get("title"))
        thumbnail = _text(option.get("thumbnail_text") or option.get("thumbnail_concept"))
        first_screen = _text(option.get("first_screen_promise"))
        angle = _text(option.get("angle")).casefold()
        backing = option.get("source_backing")
        if not title or len(title) > 95:
            _fail(failures, f"{prefix}.youtube_title is empty or too long")
        elif title:
            _require_russian(title, prefix=f"{prefix}.youtube_title", failures=failures)
        if not thumbnail or len(thumbnail) > 32:
            _fail(failures, f"{prefix}.thumbnail_text is empty or too long")
        elif thumbnail:
            _require_russian(
                thumbnail,
                prefix=f"{prefix}.thumbnail_text",
                failures=failures,
                minimum_ratio=0.50,
            )
        if not first_screen:
            _fail(failures, f"{prefix}.first_screen_promise is required")
        else:
            _require_russian(
                first_screen,
                prefix=f"{prefix}.first_screen_promise",
                failures=failures,
            )
        if not angle:
            _fail(failures, f"{prefix}.angle is required")
        _validate_named_evidence(
            {"source_id": option.get("source_id"), "source_backing": backing},
            sources=sources,
            prefix=f"{prefix}.evidence",
            failures=failures,
        )
        signatures.add((title.casefold(), thumbnail.casefold(), first_screen.casefold()))
        angles.add(angle)
    if len(signatures) != 3 or len(angles) != 3:
        _fail(failures, "packaging options must be materially distinct")


def _validate_reviews(candidate: dict[str, Any], failures: list[str]) -> float:
    reviews = candidate.get("reviews")
    if not isinstance(reviews, list) or len(reviews) != 2:
        _fail(failures, "exactly two independent structured reviews are required")
        return 0.0
    roles = {_text(review.get("role")).lower() for review in reviews if isinstance(review, dict)}
    if roles != {"producer", "critic"}:
        _fail(failures, "reviews must contain producer and critic roles")

    totals: list[float] = []
    for index, review in enumerate(reviews):
        prefix = f"reviews[{index}]"
        if not isinstance(review, dict):
            _fail(failures, f"{prefix} must be an object")
            continue
        if _text(review.get("verdict")).upper() != "PASS":
            _fail(failures, f"{prefix}.verdict must be PASS")
        _validate_veto_flags(
            review.get("veto_flags"),
            prefix=f"{prefix}.veto_flags",
            failures=failures,
        )
        scorecard = review.get("scorecard")
        if not isinstance(scorecard, dict):
            _fail(failures, f"{prefix}.scorecard must be an object")
            continue
        total = 0.0
        for field, maximum in SCORE_MAXIMA.items():
            value = scorecard.get(field)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                _fail(failures, f"{prefix}.scorecard.{field} must be numeric")
                continue
            if not 0 <= value <= maximum:
                _fail(failures, f"{prefix}.scorecard.{field} must be between 0 and {maximum}")
                continue
            if value < SCORE_MINIMA[field]:
                _fail(failures, f"{prefix}.scorecard.{field} is below the S-tier target minimum")
            total += float(value)
        if total < PASS_SCORE:
            _fail(failures, f"{prefix} total score {total:g} is below {PASS_SCORE}")
        if not _text(review.get("decision_reason")):
            _fail(failures, f"{prefix}.decision_reason is required")
        totals.append(total)
    return round(sum(totals) / len(totals), 3) if len(totals) == 2 else 0.0


def validate_base_candidate(
    candidate: Any,
    *,
    plan: dict[str, Any],
    index: int,
) -> dict[str, Any]:
    """Validate every provider-independent candidate/source contract."""
    failures: list[str] = []
    prefix = f"candidates[{index}]"
    if not isinstance(candidate, dict):
        return {
            "candidate_id": None,
            "status": "BLOCKED",
            "format": None,
            "pillar": None,
            "pilot_id": None,
            "sources": [],
            "failures": [f"{prefix} must be an object"],
        }
    candidate_id = _text(candidate.get("candidate_id"))
    if not candidate_id:
        _fail(failures, f"{prefix}.candidate_id is required")
    format_id = _text(candidate.get("format")).upper()
    pillar = _text(candidate.get("pillar"))
    pilot_id = _text(candidate.get("pilot_id"))
    if format_id != _text(plan.get("format")).upper() or format_id not in FORMATS:
        _fail(failures, f"{prefix}.format does not match plan")
    if pillar != _text(plan.get("pillar")):
        _fail(failures, f"{prefix}.pillar does not match plan")
    if pilot_id != _text(plan.get("pilot_id")):
        _fail(failures, f"{prefix}.pilot_id does not match plan")
    raw_sources = candidate.get("sources")
    if not isinstance(raw_sources, list) or not raw_sources:
        _fail(failures, f"{prefix}.sources must be a non-empty list")
        raw_sources = []
    sources: list[dict[str, Any]] = []
    for source_index, raw_source in enumerate(raw_sources):
        source, source_failures = _validate_source(
            raw_source,
            pillar=pillar,
            prefix=f"{prefix}.sources[{source_index}]",
        )
        failures.extend(source_failures)
        if source is not None:
            sources.append(source)
    if len(sources) == len(raw_sources):
        _validate_format_sources(
            format_id=format_id,
            pilot_id=pilot_id,
            sources=sources,
            failures=failures,
        )

    return {
        "candidate_id": candidate_id or None,
        "status": "PASS" if not failures else "BLOCKED",
        "format": format_id or None,
        "pillar": pillar or None,
        "pilot_id": pilot_id or None,
        "sources": sources,
        "failures": failures,
    }


def validate_candidate(
    candidate: Any,
    *,
    plan: dict[str, Any],
    index: int,
) -> dict[str, Any]:
    base = validate_base_candidate(candidate, plan=plan, index=index)
    failures = list(base["failures"])
    prefix = f"candidates[{index}]"
    if not isinstance(candidate, dict):
        return {
            "candidate_id": None,
            "status": "BLOCKED",
            "score": 0,
            "candidate_contract_sha256": None,
            "packaging_options_sha256": None,
            "failures": failures,
        }
    candidate_id = _text(candidate.get("candidate_id"))
    format_id = _text(candidate.get("format")).upper()
    sources = list(base["sources"])
    if candidate.get("viewer_promise_fit") is not True:
        _fail(failures, f"{prefix}.viewer_promise_fit must be true")

    _validate_named_evidence(
        candidate.get("pillar_evidence"),
        sources=sources,
        prefix=f"{prefix}.pillar_evidence",
        failures=failures,
    )

    cold_open = candidate.get("cold_open")
    if not isinstance(cold_open, dict):
        _fail(failures, f"{prefix}.cold_open must be an object")
    else:
        cold_open_text = _text(cold_open.get("text"))
        cold_open_words = _word_count(cold_open_text)
        if not MIN_COLD_OPEN_WORDS <= cold_open_words <= MAX_COLD_OPEN_WORDS:
            _fail(
                failures,
                f"{prefix}.cold_open.text must contain "
                f"{MIN_COLD_OPEN_WORDS}-{MAX_COLD_OPEN_WORDS} words",
            )
        _require_russian(
            cold_open_text,
            prefix=f"{prefix}.cold_open.text",
            failures=failures,
            minimum_words=3,
        )
        narration = narration_preflight(cold_open_text)
        narration_text = _text(narration.get("narration_text"))
        if narration.get("status") != "PASS":
            _fail(failures, f"{prefix}.cold_open.text is not narration-safe")
        if len(narration_text) > MAX_COLD_OPEN_NARRATION_CHARACTERS:
            _fail(
                failures,
                f"{prefix}.cold_open.text exceeds the 500-character spoken limit",
            )
        if any(
            len(token) > MAX_NARRATION_TOKEN_CHARACTERS
            for token in narration_text.split()
        ):
            _fail(failures, f"{prefix}.cold_open.text contains an overlong spoken token")
        _validate_named_evidence(
            cold_open,
            sources=sources,
            prefix=f"{prefix}.cold_open",
            failures=failures,
        )
    if format_id in {"SAGA", "BUNDLE"}:
        _validate_named_evidence(
            candidate.get("payoff_evidence"),
            sources=sources,
            prefix=f"{prefix}.payoff_evidence",
            failures=failures,
            ending_window=True,
        )

    _validate_veto_flags(
        candidate.get("veto_flags"),
        prefix=f"{prefix}.veto_flags",
        failures=failures,
    )
    creative_plan_sha256, story_beat_count = _validate_creative_plan(
        candidate,
        sources,
        failures,
    )
    _validate_packaging(candidate, sources, failures)
    score = _validate_reviews(candidate, failures)

    source_digest = canonical_hash(
        [
            {
                "source_id": source["source_id"],
                "body_sha256": source["body_sha256"],
                "source_url": source["source_url"],
                "truth_mode": source["truth_mode"],
                "role": source["role"],
            }
            for source in sources
        ]
    ) if sources else None
    return {
        "candidate_id": candidate_id or None,
        "status": "PASS" if not failures else "BLOCKED",
        "score": score,
        "candidate_contract_sha256": canonical_hash(candidate),
        "packaging_options_sha256": canonical_hash(candidate.get("packaging_options")),
        "cold_open_sha256": canonical_hash({
            "text": _text((candidate.get("cold_open") or {}).get("text")),
            "source_id": _text((candidate.get("cold_open") or {}).get("source_id")),
            "source_quote": _text((candidate.get("cold_open") or {}).get("source_quote")),
        }),
        "source_set_sha256": source_digest,
        "creative_plan_sha256": creative_plan_sha256,
        "story_beat_count": story_beat_count,
        "source_count": len(sources),
        "failures": failures,
    }


def run_playoff(payload: dict[str, Any]) -> dict[str, Any]:
    """Validate all finalists and select the strongest fully passing topic."""
    failures: list[str] = []
    plan = payload.get("daily_plan")
    if not isinstance(plan, dict):
        raise TopicPlayoffError("daily_plan must be an object")
    plan_sha = _text(payload.get("daily_plan_sha256"))
    actual_plan_sha = canonical_hash(plan)
    if plan_sha != actual_plan_sha or not SHA256_RE.fullmatch(plan_sha):
        failures.append("daily_plan_sha256 does not match daily_plan")
    if plan.get("channel_id") != "acc1":
        failures.append("daily_plan.channel_id must be acc1")
    if plan.get("publication_authorized") is not False:
        failures.append("daily_plan.publication_authorized must be false")

    candidates = payload.get("candidates")
    if not isinstance(candidates, list):
        candidates = []
        failures.append("candidates must be a list")
    if len(candidates) < MIN_FINALISTS:
        failures.append(f"at least {MIN_FINALISTS} finalists are required")
    reviews = [validate_candidate(item, plan=plan, index=index) for index, item in enumerate(candidates)]
    candidate_ids = [item["candidate_id"] for item in reviews if item["candidate_id"]]
    if len(candidate_ids) != len(set(candidate_ids)):
        failures.append("candidate_id values must be unique")
    passing = [item for item in reviews if item["status"] == "PASS"]
    passing.sort(key=lambda item: (-item["score"], str(item["candidate_id"])))
    winner = passing[0] if passing else None
    exceptional_winner = bool(
        len(candidates) >= EXCEPTIONAL_WINNER_MIN_CANDIDATES
        and winner
        and winner["score"] >= EXCEPTIONAL_WINNER_MIN_SCORE
        and not winner["failures"]
    )
    if len(passing) < MIN_PASSING_FINALISTS and not exceptional_winner:
        failures.append(
            f"at least {MIN_PASSING_FINALISTS} finalists must independently PASS, or one "
            f"clean winner must score at least {EXCEPTIONAL_WINNER_MIN_SCORE} after "
            f"{EXCEPTIONAL_WINNER_MIN_CANDIDATES} candidates are reviewed"
        )

    result: dict[str, Any] = {
        "version": 1,
        "status": "READY_FOR_SCRIPTING" if not failures and winner else "BLOCKED",
        "publication_authorized": False,
        "s_tier_target": True,
        "millions_of_views_guaranteed": False,
        "daily_plan_sha256": actual_plan_sha,
        "playoff_input_sha256": canonical_hash(payload),
        "minimum_finalists": MIN_FINALISTS,
        "minimum_passing_finalists": MIN_PASSING_FINALISTS,
        "exceptional_winner_policy": {
            "minimum_reviewed_candidates": EXCEPTIONAL_WINNER_MIN_CANDIDATES,
            "minimum_score": EXCEPTIONAL_WINNER_MIN_SCORE,
            "requires_zero_winner_failures": True,
            "used": exceptional_winner and len(passing) < MIN_PASSING_FINALISTS,
        },
        "minimum_review_score": PASS_SCORE,
        "candidate_reviews": reviews,
        "winner": winner,
        "failures": failures,
        "selection_rule": (
            "three_independent_passes_or_exceptional_clean_winner_after_five_reviews_"
            "then_review_average_desc_then_candidate_id_asc"
        ),
    }
    unhashed = dict(result)
    result["playoff_sha256"] = canonical_hash(unhashed)
    return result


def _read_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TopicPlayoffError(f"{path} must contain a JSON object")
    return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    result = run_playoff(_read_object(Path(args.input)))
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": result["status"], "winner": (result["winner"] or {}).get("candidate_id")}, ensure_ascii=False))
    return 0 if result["status"] == "READY_FOR_SCRIPTING" else 1


if __name__ == "__main__":
    raise SystemExit(main())
