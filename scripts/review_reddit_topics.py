#!/usr/bin/env python3
"""Deterministic full-body topic review for bounded Reddit candidate queues."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

from source_text_quality import source_text_quality_blockers
from source_safety import source_safety_evidence


# Keep source-runtime accounting byte-for-byte compatible with
# ``scraper.source_word_count``. Reddit stories often contain dates, ages, or
# amounts; dropping those tokens here could make the deterministic review and
# the later greenlight binding disagree about the same source body.
WORD_RE = re.compile(r"[A-Za-z0-9']+")
SERIES_RE = re.compile(r"\b(?:part|chapter|episode|season)\s*(?:one|two|three|[0-9]+)\b|\bseries\b", re.I)
OPEN_ENDING_RE = re.compile(
    r"\b(?:to be continued|i(?:'m| am) still waiting|i don'?t know what happens next|"
    r"i(?:'m| am) writing this in case|if anything happens to me|in case .{0,60} happens to me)\b",
    re.I,
)
CLOSURE_RE = re.compile(
    r"\b(?:finally|in the end|eventually|after that|since then|turned out|found out|"
    r"apolog(?:ized|ised)|broke up|divorced|quit|resigned|fired|reported|blocked|paid|refunded|"
    r"won|lost|settled|never saw|never heard|that was the last|edit|update)\b",
    re.I,
)
SAGA_WORDS_PER_MINUTE = 130
SAGA_MIN_WORDS = 18 * SAGA_WORDS_PER_MINUTE
SAGA_MAX_WORDS = 30 * SAGA_WORDS_PER_MINUTE
MAX_SOURCE_CHARACTERS_PER_WORD = 12
MAX_SOURCE_TOKEN_CHARACTERS = 80
SAGA_PILLAR_SOURCE_FAMILY = {
    "relationships_family": "human_drama",
    "work_money_justice": "human_drama",
    "strange_dark_unexplained": "dark_curiosity",
}
SAGA_PILOT_PILLAR = {
    "pilot_01": "relationships_family",
    "pilot_02": "work_money_justice",
    "pilot_03": "strange_dark_unexplained",
}
BUNDLE_PILOT_PILLAR = {
    "pilot_01": "relationships_family",
    "pilot_02": "work_money_justice",
}
SAGA_PILLARS: dict[str, tuple[str, ...]] = {
    "relationships_family": (
        "relationship", "husband", "wife", "boyfriend", "girlfriend", "partner", "marriage",
        "mother", "father", "mom", "dad", "parent", "brother", "sister", "family", "child",
        "wedding", "divorce", "in-law", "cheated", "breakup",
    ),
    "work_money_justice": (
        "work", "job", "boss", "manager", "coworker", "employee", "company", "office", "shift",
        "money", "paid", "paycheck", "salary", "rent", "debt", "refund", "stole", "fired", "quit",
        "revenge", "compliance", "reported", "court", "justice", "customer", "client",
    ),
    "strange_dark_unexplained": (
        "strange", "creepy", "scary", "unexplained", "impossible", "rule", "never", "night",
        "shadow", "door", "window", "basement", "train", "road", "station", "recording", "camera",
        "message", "missing", "stranger", "encounter", "glitch",
    ),
}
UNVERIFIED_PERSONAL_SUBREDDITS = {
    "amitheasshole", "aitah", "relationship_advice", "offmychest", "confession", "tifu",
    "prorevenge", "maliciouscompliance", "entitledparents", "bestofredditorupdates",
    "talesfromyourserver", "letsnotmeet", "creepyencounters", "glitch_in_the_matrix",
    "truescarystories",
}


THEMES: tuple[dict[str, Any], ...] = (
    {
        "id": "forbidden_rule_system",
        "label_ru": "Одно запретное правило в обычной системе",
        "terms": ("rule", "rules", "forbidden", "never", "do not", "don't", "must not", "exactly"),
    },
    {
        "id": "family_home_anomaly",
        "label_ru": "Семейная или домашняя аномалия",
        "terms": (
            "mother", "father", "mom", "dad", "parent", "parents", "brother", "sister",
            "family", "house", "home", "apartment", "neighbour", "neighbor", "childhood",
        ),
    },
    {
        "id": "night_work_role",
        "label_ru": "Ночная работа с невозможной обязанностью",
        "terms": (
            "night shift", "graveyard shift", "boss", "job", "work", "dispatcher", "driver",
            "sitter", "security", "janitor", "maintenance", "delivery", "mop", "call center",
        ),
    },
    {
        "id": "public_space_travel_trap",
        "label_ru": "Ловушка в дороге или общественном месте",
        "terms": (
            "subway", "train", "bus", "road", "highway", "station", "diner", "restaurant",
            "aquarium", "hotel", "elevator", "airport", "parking", "tunnel",
        ),
    },
    {
        "id": "haunted_media_record",
        "label_ru": "Запись или сообщение, которого не должно существовать",
        "terms": (
            "video", "camera", "recording", "tape", "card", "letter", "message", "text",
            "phone", "announcement", "photo", "photograph", "screen", "mail",
        ),
    },
    {
        "id": "boundary_anomaly",
        "label_ru": "Граница, которую нельзя пересекать или проверять",
        "terms": (
            "line", "boundary", "cross", "fence", "door", "peephole", "threshold", "gate",
            "bridge", "border", "entrance", "window",
        ),
    },
)


def content_hash(payload: Any) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _text(value: Any) -> str:
    return str(value or "").strip()


def bind_artifact_hashes(review: dict[str, Any], queue: dict[str, Any]) -> dict[str, Any]:
    bound = dict(review)
    bound["source_sha256"] = content_hash(queue)
    without_review_hash = dict(bound)
    without_review_hash.pop("review_sha256", None)
    bound["review_sha256"] = content_hash(without_review_hash)
    return bound


def load_queue(path: Path, allow_missing: bool) -> dict[str, Any]:
    if not path.exists():
        if allow_missing:
            return {}
        raise FileNotFoundError(path)
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("queue must be a JSON object")
    return data


def normalized_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").casefold()).strip()


def source_narration_blockers(body: str) -> list[str]:
    """Reject source text whose spoken-cost envelope is not naturally bounded."""
    return source_text_quality_blockers(body)


def term_hits(text: str, terms: tuple[str, ...]) -> int:
    return sum(1 for term in terms if re.search(rf"\b{re.escape(term)}\b", text))


def truth_mode(subreddit: str) -> str:
    normalized = subreddit.casefold().removeprefix("r/")
    if normalized == "nosleep":
        return "fiction"
    if normalized in UNVERIFIED_PERSONAL_SUBREDDITS:
        return "unverified_personal_account"
    if normalized == "unresolvedmysteries":
        return "evidence_required"
    return "unknown"


def candidate_risks(entry: dict[str, Any], body: str) -> list[str]:
    risks: list[str] = []
    if entry.get("source_has_url") or entry.get("source_has_markdown_link") or entry.get("source_has_markdown_image"):
        risks.append("external_dependency")
    title = str(entry.get("title") or "")
    if SERIES_RE.search(title):
        risks.append("possible_series_dependency")
    ending = body[-1600:]
    if OPEN_ENDING_RE.search(ending):
        risks.append("possible_open_ending")
    word_count = len(WORD_RE.findall(body))
    if word_count < 2500:
        risks.append("short_source_for_target_runtime")
    mode = truth_mode(str(entry.get("subreddit") or ""))
    if mode == "unverified_personal_account":
        risks.append("unverified_claim")
    elif mode == "evidence_required":
        risks.append("factual_evidence_required")
    elif mode == "unknown":
        risks.append("truth_mode_unknown")
    return risks


def analyze_entry(entry: dict[str, Any]) -> dict[str, Any]:
    body = str(entry.get("source_body") or "")
    if not body.strip():
        raise ValueError(f"candidate {entry.get('post_id') or '(unknown)'} has no source_body")
    title = str(entry.get("title") or "")
    title_text = normalized_text(title)
    full_text = normalized_text(f"{title}\n{body}")
    theme_scores: dict[str, int] = {}
    for theme in THEMES:
        title_hits = term_hits(title_text, theme["terms"])
        full_hits = term_hits(full_text, theme["terms"])
        # The topic promise must be visible in the title. The full body is still
        # read for structure/risk evidence, but incidental words cannot assign a theme.
        score = (title_hits * 5) + min(full_hits, 3) if title_hits else 0
        if score:
            theme_scores[theme["id"]] = score

    word_count = len(WORD_RE.findall(body))
    risks = candidate_risks(entry, body)
    local_score = int(entry.get("local_score") or 0)
    length_bonus = 12 if 2500 <= word_count <= 6500 else 6 if 1400 <= word_count < 2500 else 0
    risk_penalty = 8 * len(risks)
    strongest_theme = max(theme_scores.values(), default=0)
    shortlist_score = local_score + length_bonus + (strongest_theme * 4) - risk_penalty
    return {
        "post_id": entry.get("post_id"),
        "title": title,
        "subreddit": entry.get("subreddit"),
        "source_body_chars": len(body),
        "source_word_count": word_count,
        "truth_mode": truth_mode(str(entry.get("subreddit") or "")),
        "theme_scores": theme_scores,
        "risks": risks,
        "shortlist_score": shortlist_score,
        "review_status": "SHORTLIST_FOR_RIGHTS_REVIEW",
    }


def _pillar_fit(title: str, body: str, pillar_id: str, topic_family: str) -> dict[str, Any]:
    terms = SAGA_PILLARS[pillar_id]
    title_text = normalized_text(title)
    full_text = normalized_text(f"{title}\n{body}")
    title_matches = [term for term in terms if re.search(rf"\b{re.escape(term)}\b", title_text)]
    full_matches = [term for term in terms if re.search(rf"\b{re.escape(term)}\b", full_text)]
    expected_family = SAGA_PILLAR_SOURCE_FAMILY[pillar_id]
    family_match = topic_family == expected_family
    score = (len(title_matches) * 5) + min(len(full_matches), 8) + (3 if family_match else 0)
    return {
        "matches": sorted(set(title_matches + full_matches)),
        "score": score,
        "family_match": family_match,
        "passes": family_match and (bool(title_matches) or len(set(full_matches)) >= 2),
    }


def _payoff_evidence(title: str, body: str) -> dict[str, Any]:
    if SERIES_RE.search(title):
        return {"complete": False, "reason": "possible_series_dependency", "evidence": ""}
    ending = body[-1800:].strip()
    if OPEN_ENDING_RE.search(ending):
        return {"complete": False, "reason": "possible_open_ending", "evidence": ""}
    closure = CLOSURE_RE.search(ending)
    terminal = bool(re.search(r"[.!?][\"')\]]*$", ending))
    if not terminal:
        return {
            "complete": False,
            "reason": "payoff_not_structurally_proven",
            "evidence": closure.group(0) if closure else "",
        }
    if not closure:
        # Horror fiction commonly closes on a final image, action, or reveal
        # without connective words such as "finally" or "in the end". The
        # deterministic gate can prove that the supplied source has a terminal
        # ending and no explicit series/open-ending marker; semantic payoff is
        # still scored independently by the paid producer and critic.
        return {
            "complete": True,
            "reason": "terminal_ending_without_open_marker",
            "evidence": ending[-600:].strip(),
        }
    evidence_start = max(0, closure.start() - 180)
    evidence_end = min(len(ending), closure.end() + 420)
    return {
        "complete": True,
        "reason": "closure_marker_and_terminal_ending",
        "evidence": ending[evidence_start:evidence_end].strip(),
    }


def analyze_saga_entry(
    entry: dict[str, Any],
    *,
    pillar_id: str,
    expected_family: str,
    allowed_subreddits: set[str],
) -> dict[str, Any]:
    body = str(entry.get("source_body") or "")
    if not body.strip():
        raise ValueError(f"candidate {entry.get('post_id') or '(unknown)'} has no source_body")
    title = str(entry.get("title") or "").strip()
    word_count = len(WORD_RE.findall(body))
    estimated_minutes = round(word_count / SAGA_WORDS_PER_MINUTE, 2)
    mode = truth_mode(str(entry.get("subreddit") or ""))
    topic_family = str(entry.get("topic_family") or "").strip()
    normalized_subreddit = str(entry.get("subreddit") or "").strip().casefold().removeprefix("r/")
    pillar_fit = _pillar_fit(title, body, pillar_id, topic_family)
    payoff = _payoff_evidence(title, body)
    source_media = entry.get("source_media")
    has_native_media = bool(
        isinstance(source_media, list)
        and any(isinstance(item, dict) for item in source_media)
    )
    depends_on_external = bool(
        entry.get("source_has_url")
        or entry.get("source_has_markdown_link")
        or entry.get("source_has_markdown_image")
        or has_native_media
    )
    blocking_reasons: list[str] = []
    if topic_family != expected_family:
        blocking_reasons.append("wrong_source_family")
    if normalized_subreddit not in allowed_subreddits:
        blocking_reasons.append("subreddit_not_in_source_plan")
    if not SAGA_MIN_WORDS <= word_count <= SAGA_MAX_WORDS:
        blocking_reasons.append("outside_saga_runtime")
    blocking_reasons.extend(source_narration_blockers(body))
    if not source_safety_evidence(entry, body)["passed"]:
        blocking_reasons.append("unsafe_or_pii_source")
    if depends_on_external:
        blocking_reasons.append("screenshot_or_link_dependent")
    if mode not in {"fiction", "unverified_personal_account"}:
        blocking_reasons.append("truth_mode_not_publishable")
    if not pillar_fit["passes"]:
        blocking_reasons.append("pillar_fit_not_proven")
    if not payoff["complete"]:
        blocking_reasons.append(payoff["reason"])

    body_sha256 = hashlib.sha256(body.encode("utf-8")).hexdigest()
    recorded_hash = str(entry.get("source_body_sha256") or "").strip()
    if recorded_hash and recorded_hash != body_sha256:
        blocking_reasons.append("source_body_hash_mismatch")
    local_score = int(entry.get("local_score") or 0)
    shortlist_score = local_score + (pillar_fit["score"] * 4) - (12 * len(blocking_reasons))
    return {
        "post_id": entry.get("post_id"),
        "title": title,
        "subreddit": entry.get("subreddit"),
        "source_url": entry.get("url") or entry.get("source_url"),
        "source_body_chars": len(body),
        "source_body_sha256": body_sha256,
        "source_word_count": word_count,
        "estimated_minutes_at_130_wpm": estimated_minutes,
        "runtime_target_minutes": [18, 30],
        "runtime_fit": SAGA_MIN_WORDS <= word_count <= SAGA_MAX_WORDS,
        "truth_mode": mode,
        "depends_on_screenshot_or_link": depends_on_external,
        "payoff_complete": payoff["complete"],
        "payoff_evidence": payoff["evidence"],
        "pillar_id": pillar_id,
        "pillar_fit_score": pillar_fit["score"],
        "pillar_fit_evidence": pillar_fit["matches"],
        "source_family": topic_family,
        "blocking_reasons": blocking_reasons,
        "shortlist_score": shortlist_score,
        "review_status": (
            "SAGA_SOURCE_ELIGIBLE_FOR_GREENLIGHT"
            if not blocking_reasons
            else "BLOCKED"
        ),
    }


def analyze_bundle_entry(
    entry: dict[str, Any],
    *,
    pillar_id: str,
    expected_family: str,
    allowed_subreddits: set[str],
) -> dict[str, Any]:
    """Review one complete component without applying the aggregate episode runtime."""
    body = str(entry.get("source_body") or "")
    if not body.strip():
        raise ValueError(f"candidate {entry.get('post_id') or '(unknown)'} has no source_body")
    title = str(entry.get("title") or "").strip()
    author = str(entry.get("author") or "").strip()
    word_count = len(WORD_RE.findall(body))
    mode = truth_mode(str(entry.get("subreddit") or ""))
    topic_family = str(entry.get("topic_family") or "").strip()
    normalized_subreddit = str(entry.get("subreddit") or "").strip().casefold().removeprefix("r/")
    pillar_fit = _pillar_fit(title, body, pillar_id, topic_family)
    payoff = _payoff_evidence(title, body)
    source_media = entry.get("source_media")
    has_native_media = bool(
        isinstance(source_media, list)
        and any(isinstance(item, dict) for item in source_media)
    )
    depends_on_external = bool(
        entry.get("source_has_url")
        or entry.get("source_has_markdown_link")
        or entry.get("source_has_markdown_image")
        or has_native_media
    )
    blocking_reasons: list[str] = []
    if topic_family != expected_family:
        blocking_reasons.append("wrong_source_family")
    if normalized_subreddit not in allowed_subreddits:
        blocking_reasons.append("subreddit_not_in_source_plan")
    if not 300 <= word_count <= 1800:
        blocking_reasons.append("outside_bundle_component_runtime")
    blocking_reasons.extend(source_narration_blockers(body))
    if not source_safety_evidence(entry, body)["passed"]:
        blocking_reasons.append("unsafe_or_pii_source")
    if not author:
        blocking_reasons.append("missing_author_provenance")
    if depends_on_external:
        blocking_reasons.append("screenshot_or_link_dependent")
    if mode not in {"fiction", "unverified_personal_account"}:
        blocking_reasons.append("truth_mode_not_publishable")
    if not pillar_fit["passes"]:
        blocking_reasons.append("pillar_fit_not_proven")
    if not payoff["complete"]:
        blocking_reasons.append(payoff["reason"])

    body_sha256 = hashlib.sha256(body.encode("utf-8")).hexdigest()
    recorded_hash = str(entry.get("source_body_sha256") or "").strip()
    if recorded_hash and recorded_hash != body_sha256:
        blocking_reasons.append("source_body_hash_mismatch")
    local_score = int(entry.get("local_score") or 0)
    shortlist_score = local_score + (pillar_fit["score"] * 4) - (12 * len(blocking_reasons))
    eligible = not blocking_reasons
    return {
        "post_id": entry.get("post_id"),
        "title": title,
        "subreddit": entry.get("subreddit"),
        "author": author,
        "source_url": entry.get("url") or entry.get("source_url"),
        "story_signature": entry.get("story_signature"),
        "source_body": body,
        "source_body_chars": len(body),
        "source_body_sha256": body_sha256,
        "source_word_count": word_count,
        "estimated_minutes_at_130_wpm": round(word_count / SAGA_WORDS_PER_MINUTE, 2),
        "truth_mode": mode,
        "complete": eligible,
        "self_contained": eligible,
        "depends_on_screenshot_or_link": depends_on_external,
        "payoff_complete": payoff["complete"],
        "payoff_evidence": payoff["evidence"],
        "pillar_id": pillar_id,
        "pillar_fit_score": pillar_fit["score"],
        "pillar_fit_evidence": pillar_fit["matches"],
        "source_family": topic_family,
        "blocking_reasons": blocking_reasons,
        "shortlist_score": shortlist_score,
        "review_status": "BUNDLE_COMPONENT_ELIGIBLE" if eligible else "BLOCKED",
    }


def build_bundle_review(queue: dict[str, Any], top_n: int) -> dict[str, Any]:
    source_plan = queue.get("source_plan")
    failures: list[str] = []
    if not isinstance(source_plan, dict):
        failures.append("source_plan must be an object for BUNDLE review")
        source_plan = {}
    pillar_id = _text(source_plan.get("pillar"))
    pilot_id = _text(source_plan.get("pilot_id"))
    expected_pillar = BUNDLE_PILOT_PILLAR.get(pilot_id)
    expected_family = "human_drama" if expected_pillar else None
    if source_plan.get("format") != "BUNDLE":
        failures.append("source_plan.format must be BUNDLE")
    if expected_pillar != pillar_id:
        failures.append(
            f"source_plan pilot/pillar pair is not canonical: {pilot_id or '(missing)'}/{pillar_id or '(missing)'}"
        )
    if source_plan.get("format_intent") != "bundle":
        failures.append("source_plan.format_intent must be bundle")
    if source_plan.get("aggregate_source_word_count") != [2340, 3900]:
        failures.append("source_plan.aggregate_source_word_count must be [2340, 3900]")
    if expected_family and source_plan.get("topic_family") != expected_family:
        failures.append("BUNDLE source_plan.topic_family must be human_drama")
    raw_subreddits = source_plan.get("subreddits")
    if not isinstance(raw_subreddits, list) or not raw_subreddits:
        failures.append("source_plan.subreddits must contain configured subreddits")
        raw_subreddits = []
    allowed_subreddits = {
        str(item).strip().casefold().removeprefix("r/") for item in raw_subreddits
    }
    raw_entries = queue.get("entries") or []
    base = {
        "version": 1,
        "review_mode": "deterministic_full_body_bundle_components",
        "channel_id": queue.get("channel_id"),
        "format_intent": queue.get("format_intent"),
        "source_plan": source_plan,
        "candidate_count": len(raw_entries),
        "production_authorized": False,
    }
    if failures:
        return bind_artifact_hashes({
            **base,
            "status": "blocked_invalid_source_plan",
            "eligible_candidate_count": 0,
            "failures": failures,
            "candidate_reviews": [],
            "top_topics": [],
        }, queue)
    candidates = [
        analyze_bundle_entry(
            entry,
            pillar_id=pillar_id,
            expected_family=str(expected_family),
            allowed_subreddits=allowed_subreddits,
        )
        for entry in raw_entries
        if isinstance(entry, dict)
    ]
    eligible = [item for item in candidates if not item["blocking_reasons"]]
    eligible.sort(key=lambda item: (-item["shortlist_score"], str(item.get("post_id") or "")))
    chosen = eligible[:top_n]
    return bind_artifact_hashes({
        **base,
        "status": "review_ready" if chosen else "no_eligible_bundle_components",
        "eligible_candidate_count": len(eligible),
        "failures": [],
        "candidate_reviews": candidates,
        "top_topics": chosen,
    }, queue)


def build_saga_review(queue: dict[str, Any], top_n: int) -> dict[str, Any]:
    source_plan = queue.get("source_plan")
    failures: list[str] = []
    if not isinstance(source_plan, dict):
        failures.append("source_plan must be an object for SAGA review")
        source_plan = {}
    pillar_id = str(source_plan.get("pillar") or "").strip()
    pilot_id = str(source_plan.get("pilot_id") or "").strip()
    expected_family = SAGA_PILLAR_SOURCE_FAMILY.get(pillar_id)
    expected_pillar = SAGA_PILOT_PILLAR.get(pilot_id)
    if source_plan.get("format") != "SAGA":
        failures.append("source_plan.format must be SAGA")
    if expected_pillar != pillar_id:
        failures.append(
            f"source_plan pilot/pillar pair is not canonical: {pilot_id or '(missing)'}/{pillar_id or '(missing)'}"
        )
    if not expected_family:
        failures.append(f"unknown SAGA pillar: {pillar_id or '(missing)'}")
    if expected_family and source_plan.get("topic_family") != expected_family:
        failures.append(
            f"source_plan.topic_family must be {expected_family} for pillar {pillar_id}"
        )
    if source_plan.get("format_intent") != "saga":
        failures.append("source_plan.format_intent must be saga")
    if source_plan.get("target_duration_minutes") != [18, 30]:
        failures.append("source_plan.target_duration_minutes must be [18, 30]")
    if source_plan.get("source_word_count") != [SAGA_MIN_WORDS, SAGA_MAX_WORDS]:
        failures.append(
            f"source_plan.source_word_count must be [{SAGA_MIN_WORDS}, {SAGA_MAX_WORDS}]"
        )
    if source_plan.get("words_per_minute") != SAGA_WORDS_PER_MINUTE:
        failures.append(f"source_plan.words_per_minute must be {SAGA_WORDS_PER_MINUTE}")
    raw_subreddits = source_plan.get("subreddits")
    if not isinstance(raw_subreddits, list) or not raw_subreddits or not all(
        str(item or "").strip() for item in raw_subreddits
    ):
        failures.append("source_plan.subreddits must contain at least one configured subreddit")
        raw_subreddits = []
    allowed_subreddits = {
        str(item).strip().casefold().removeprefix("r/") for item in raw_subreddits
    }
    raw_entries = queue.get("entries") or []
    if failures:
        return bind_artifact_hashes({
            "version": 2,
            "status": "blocked_invalid_source_plan",
            "review_mode": "deterministic_full_body_saga",
            "channel_id": queue.get("channel_id"),
            "format_intent": queue.get("format_intent"),
            "source_plan": source_plan,
            "candidate_count": len(raw_entries),
            "eligible_candidate_count": 0,
            "failures": failures,
            "candidate_reviews": [],
            "top_topics": [],
            "production_authorized": False,
        }, queue)
    if not raw_entries:
        return bind_artifact_hashes({
            "version": 2,
            "status": "no_candidates",
            "review_mode": "deterministic_full_body_saga",
            "channel_id": queue.get("channel_id"),
            "format_intent": queue.get("format_intent"),
            "source_plan": source_plan,
            "candidate_count": 0,
            "eligible_candidate_count": 0,
            "failures": [],
            "candidate_reviews": [],
            "top_topics": [],
            "production_authorized": False,
        }, queue)

    candidates = [
        analyze_saga_entry(
            entry,
            pillar_id=pillar_id,
            expected_family=expected_family,
            allowed_subreddits=allowed_subreddits,
        )
        for entry in raw_entries
        if isinstance(entry, dict)
    ]
    eligible = [item for item in candidates if not item["blocking_reasons"]]
    eligible.sort(key=lambda item: item["shortlist_score"], reverse=True)
    chosen = eligible[:top_n]
    queue_selected_post_id = _text(queue.get("selected_post_id"))
    review_top_post_id = _text(chosen[0].get("post_id")) if chosen else ""
    eligible_ids = {_text(item.get("post_id")) for item in eligible}
    if not queue_selected_post_id:
        selection_alignment = "queue_selection_missing"
    elif queue_selected_post_id == review_top_post_id:
        selection_alignment = "aligned"
    elif queue_selected_post_id in eligible_ids:
        selection_alignment = "queue_selection_eligible_not_review_top"
    else:
        selection_alignment = "queue_selection_not_eligible"
    return bind_artifact_hashes({
        "version": 2,
        "status": "review_ready" if chosen else "no_eligible_saga_candidate",
        "review_mode": "deterministic_full_body_saga",
        "channel_id": queue.get("channel_id"),
        "format_intent": queue.get("format_intent"),
        "source_plan": source_plan,
        "candidate_count": len(candidates),
        "eligible_candidate_count": len(eligible),
        "failures": [],
        "candidate_reviews": candidates,
        "top_topics": chosen,
        "queue_selected_post_id": queue_selected_post_id or None,
        "review_top_post_id": review_top_post_id or None,
        "selection_alignment": selection_alignment,
        "production_authorized": False,
    }, queue)


def build_review(queue: dict[str, Any], top_n: int) -> dict[str, Any]:
    source_plan = queue.get("source_plan")
    format_intent = str(queue.get("format_intent") or "").strip().casefold()
    source_format = str((source_plan or {}).get("format") or "").strip().upper() if isinstance(source_plan, dict) else ""
    if queue.get("channel_id") == "acc1" and (format_intent == "bundle" or source_format == "BUNDLE"):
        return build_bundle_review(queue, top_n)
    if queue.get("channel_id") == "acc1" and (
        format_intent == "saga" or source_format == "SAGA"
    ):
        return build_saga_review(queue, top_n)

    raw_entries = queue.get("entries") or []
    if not raw_entries:
        return bind_artifact_hashes({
            "version": 1,
            "status": "no_candidates",
            "review_mode": "deterministic_full_body",
            "channel_id": queue.get("channel_id"),
            "format_intent": queue.get("format_intent"),
            "candidate_count": 0,
            "themes": [],
            "top_topics": [],
        }, queue)

    candidates = [analyze_entry(entry) for entry in raw_entries if isinstance(entry, dict)]
    theme_rows: list[dict[str, Any]] = []
    by_id = {theme["id"]: theme for theme in THEMES}
    for theme_id, theme in by_id.items():
        matches = [candidate for candidate in candidates if candidate["theme_scores"].get(theme_id)]
        if not matches:
            continue
        matches.sort(
            key=lambda candidate: (
                candidate["theme_scores"][theme_id],
                candidate["shortlist_score"],
            ),
            reverse=True,
        )
        theme_rows.append({
            "id": theme_id,
            "label_ru": theme["label_ru"],
            "candidate_count": len(matches),
            "signal_score": sum(candidate["theme_scores"][theme_id] for candidate in matches),
            "best_candidate_score": max(candidate["shortlist_score"] for candidate in matches),
            "candidate_post_ids": [candidate["post_id"] for candidate in matches],
        })
    theme_rows.sort(
        key=lambda row: (row["best_candidate_score"], row["signal_score"], row["candidate_count"]),
        reverse=True,
    )

    chosen: list[dict[str, Any]] = []
    used_posts: set[str] = set()
    remaining_themes = list(theme_rows)
    while remaining_themes and len(chosen) < top_n:
        available: list[tuple[dict[str, Any], dict[str, Any]]] = []
        for theme in remaining_themes:
            options = [
                candidate for candidate in candidates
                if candidate["theme_scores"].get(theme["id"])
                and candidate["post_id"] not in used_posts
            ]
            if not options:
                continue
            options.sort(
                key=lambda candidate: (
                    candidate["shortlist_score"],
                    candidate["theme_scores"][theme["id"]],
                ),
                reverse=True,
            )
            available.append((theme, options[0]))
        if not available:
            break
        theme, best = max(
            available,
            key=lambda item: (
                item[1]["shortlist_score"],
                item[1]["theme_scores"][item[0]["id"]],
                item[0]["signal_score"],
            ),
        )
        candidate = dict(best)
        candidate["theme_id"] = theme["id"]
        candidate["theme_label_ru"] = theme["label_ru"]
        candidate["why_shortlisted"] = (
            "full source body matches a repeatable acc1 archetype; requires manual story and rights review"
        )
        chosen.append(candidate)
        used_posts.add(str(candidate["post_id"]))
        remaining_themes = [item for item in remaining_themes if item["id"] != theme["id"]]

    return bind_artifact_hashes({
        "version": 1,
        "status": "review_ready" if chosen else "no_theme_match",
        "review_mode": "deterministic_full_body",
        "channel_id": queue.get("channel_id"),
        "format_intent": queue.get("format_intent"),
        "candidate_count": len(candidates),
        "themes": theme_rows,
        "top_topics": chosen,
        "production_authorized": False,
    }, queue)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--queue", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--top-n", type=int, default=3)
    parser.add_argument("--allow-missing", action="store_true")
    args = parser.parse_args()

    queue = load_queue(Path(args.queue), args.allow_missing)
    review = build_review(queue, max(1, args.top_n))
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(review, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": review["status"],
        "candidate_count": review["candidate_count"],
        "top_topic_count": len(review["top_topics"]),
        "output": str(output),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
