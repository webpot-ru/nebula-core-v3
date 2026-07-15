#!/usr/bin/env python3
"""Build a deterministic, provenance-preserving acc1 THREAD source manifest.

The collector is deliberately network-free.  It accepts one JSON snapshot with
one Reddit prompt and its top-level responses, validates the snapshot, selects
8-15 complete and distinct responses, and emits a tamper-evident manifest.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import hmac
import json
import re
import sys
from collections import Counter
from pathlib import Path
from statistics import median
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from source_text_quality import (
    source_text_quality_blockers,
    source_text_quality_evidence,
)
from source_safety import source_safety_evidence


MIN_RESPONSES = 8
MAX_RESPONSES = 15
MIN_EPISODE_RESPONSE_WORDS = 1950
MAX_EPISODE_RESPONSE_WORDS = 3250
MIN_NATURAL_RESPONSE_WORDS = 80
MAX_NATURAL_RESPONSE_WORDS = 650
MAX_SOURCE_CHARACTERS_PER_WORD = 12
MAX_SOURCE_TOKEN_CHARACTERS = 80
MAX_PROMPT_CHARACTERS = 2_000
MIN_EDITORIAL_FUNCTIONS = 3
NEAR_DUPLICATE_JACCARD = 0.90
TRUTH_MODES = {"fiction", "unverified_personal_account"}
REDDIT_HOSTS = {"reddit.com", "www.reddit.com", "old.reddit.com", "new.reddit.com"}
DELETED_MARKERS = {"[deleted]", "[removed]", "[removed by reddit]"}
TRUNCATION_MARKERS = {"[truncated]", "... [truncated]", "… [truncated]"}
OUTBOUND_LINK_RE = re.compile(r"(?:https?://|www\.|\[[^\]]+\]\([^\)]+\))", re.IGNORECASE)
TOKEN_RE = re.compile(r"[^\W_]+", re.UNICODE)
EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
PHONE_RE = re.compile(r"(?<!\w)(?:\+?\d[\s().-]*){10,15}(?!\w)")
SAFETY_BLOCK_PATTERNS = (
    re.compile(r"\b(?:how\s+to|step[- ]by[- ]step)\b.{0,48}\b(?:make|build)\b.{0,24}\b(?:bomb|explosive)\b", re.IGNORECASE),
    re.compile(r"\byou\s+should\s+(?:kill|hurt)\s+(?:yourself|him|her|them)\b", re.IGNORECASE),
    re.compile(r"\b(?:child|minor|underage)\b.{0,48}\b(?:sex|sexual|nude|porn)\w*\b", re.IGNORECASE),
    re.compile(r"\b(?:home\s+address|phone\s+number|full\s+legal\s+name)\s*(?:is|:)\s*\S+", re.IGNORECASE),
)
SAFETY_FLAG_KEYS = (
    "unsafe",
    "is_unsafe",
    "safety_blocked",
    "contains_personal_data",
    "contains_doxxing",
    "doxxing",
    "sexual_content_involving_minors",
    "instructions_for_wrongdoing",
)
PROMPT_STOPWORDS = {
    "about", "after", "again", "also", "been", "being", "complete", "could",
    "does", "from", "happened", "have", "including", "into", "other", "people",
    "please", "reddit", "share", "should", "story", "tell", "that", "their", "them",
    "then", "there", "these", "thing", "this", "those", "what", "when", "where",
    "which", "while", "with", "would", "your",
}
PROMPT_REQUEST_MARKERS = {
    "?", "what", "when", "where", "which", "who", "why", "how", "tell", "share",
    "experience", "story", "happened", "ever",
}
FIRST_PERSON_RE = re.compile(r"\b(?:i|i'm|i've|i'd|my|mine|me|we|our|us)\b", re.IGNORECASE)
NARRATIVE_RE = re.compile(
    r"\b(?:when|after|before|then|later|eventually|once|years?|months?|days?|night|morning)\b",
    re.IGNORECASE,
)
EDITORIAL_ROLE_PATTERNS: tuple[tuple[str, tuple[re.Pattern[str], ...]], ...] = (
    (
        "practical_context",
        tuple(
            re.compile(pattern, re.IGNORECASE)
            for pattern in (
                r"\bin\s+my\s+(?:job|profession|industry|field)\b",
                r"\bat\s+work\b",
                r"\bstandard\s+procedure\b",
                r"\bin\s+practice\b",
                r"\bthe\s+(?:policy|procedure|protocol)\b",
            )
        ),
    ),
    (
        "counterpoint",
        tuple(
            re.compile(pattern, re.IGNORECASE)
            for pattern in (
                r"\bhowever\b", r"\bon\s+the\s+other\s+hand\b", r"\bunlike\b",
                r"\binstead\b", r"\balthough\b", r"\bcontrary\b",
            )
        ),
    ),
    (
        "reflection_empathy",
        tuple(
            re.compile(pattern, re.IGNORECASE)
            for pattern in (
                r"\bi\s+realized\b", r"\bi\s+learned\b", r"\bchanged\s+my\s+(?:view|mind)\b",
                r"\bi\s+understand\b", r"\bmade\s+me\s+feel\b", r"\bsince\s+then\b",
            )
        ),
    ),
    (
        "concise_humor",
        tuple(
            re.compile(pattern, re.IGNORECASE)
            for pattern in (
                r"\blol\b", r"\bfunny\b", r"\blaugh(?:ed|ing)?\b", r"\bjoke\b",
                r"\bridiculous\b",
            )
        ),
    ),
)

EDITORIAL_FUNCTION_PATTERNS: tuple[tuple[str, tuple[re.Pattern[str], ...]], ...] = (
    (
        "escalation",
        tuple(
            re.compile(pattern, re.IGNORECASE)
            for pattern in (
                r"\bbut\s+then\b", r"\bthen\b", r"\bsuddenly\b", r"\beventually\b",
                r"\bthings?\s+got\s+worse\b", r"\bthe\s+next\s+(?:thing|day|night)\b",
                r"\buntil\b", r"\bafter\s+that\b",
            )
        ),
    ),
    (
        "twist_or_payoff",
        tuple(
            re.compile(pattern, re.IGNORECASE)
            for pattern in (
                r"\bit\s+turned\s+out\b", r"\bturns\s+out\b", r"\bi\s+(?:realized|discovered)\b",
                r"\bi\s+found\s+out\b", r"\bin\s+the\s+end\b", r"\beventually\b",
                r"\bthe\s+(?:truth|reason|outcome|result)\b", r"\bnever\s+again\b",
            )
        ),
    ),
    (
        "stakes_or_conflict",
        tuple(
            re.compile(pattern, re.IGNORECASE)
            for pattern in (
                r"\b(?:fired|divorc(?:e|ed)|broke\s+up|breakup|debt|threatened|caught|exposed)\b",
                r"\b(?:police|hospital|court|lawsuit|ambulance|emergency|danger|terrified)\b",
                r"\b(?:argument|fight|conflict|lied|cheated|stole|missing|lost)\b",
            )
        ),
    ),
    (
        "reflection",
        tuple(pattern for role, patterns in EDITORIAL_ROLE_PATTERNS if role == "reflection_empathy" for pattern in patterns),
    ),
    (
        "counterpoint",
        tuple(pattern for role, patterns in EDITORIAL_ROLE_PATTERNS if role == "counterpoint" for pattern in patterns),
    ),
    (
        "practical_context",
        tuple(pattern for role, patterns in EDITORIAL_ROLE_PATTERNS if role == "practical_context" for pattern in patterns),
    ),
    (
        "humor_or_relief",
        tuple(pattern for role, patterns in EDITORIAL_ROLE_PATTERNS if role == "concise_humor" for pattern in patterns),
    ),
)

INTEREST_EMOTION_RE = re.compile(
    r"\b(?:afraid|angry|ashamed|embarrassed|heartbroken|relieved|shocked|terrified|"
    r"couldn['’]t\s+believe|felt|cried|crying|laughed|laughing)\b",
    re.IGNORECASE,
)
INTEREST_SPECIFICITY_RE = re.compile(
    r"(?:\b\d{1,4}\b|[\"“”][^\"“”]{3,100}[\"“”]|\b(?:manager|teacher|doctor|nurse|"
    r"coworker|neighbor|customer|client|boss|husband|wife|boyfriend|girlfriend|parent|child)\b)",
    re.IGNORECASE,
)
SELECTION_TARGET_WORDS = (MIN_EPISODE_RESPONSE_WORDS + MAX_EPISODE_RESPONSE_WORDS) // 2


class ThreadCollectorError(ValueError):
    """Raised when a THREAD snapshot cannot produce a safe manifest."""


def _canonical_json(value: Any) -> str:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise ThreadCollectorError(f"snapshot is not canonical JSON: {exc}") from exc


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_text(value: str) -> str:
    return _sha256_bytes(value.encode("utf-8"))


def _content_hash(value: Any) -> str:
    return _sha256_text(_canonical_json(value))


def _normalize_text(value: Any, field: str, *, required: bool = True) -> str:
    if value is None and not required:
        return ""
    if not isinstance(value, str):
        raise ThreadCollectorError(f"{field} must be a string")
    text = value.replace("\r\n", "\n").replace("\r", "\n").strip()
    if required and not text:
        raise ThreadCollectorError(f"{field} is required")
    return text


def _normalize_id(value: Any, field: str) -> str:
    text = _normalize_text(value, field).casefold()
    if not re.fullmatch(r"[a-z0-9_]+", text):
        raise ThreadCollectorError(f"{field} must be a Reddit base36-style id")
    return text


def _source_value(mapping: dict[str, Any]) -> Any:
    for key in ("source_url", "permalink", "url"):
        value = mapping.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return None


def _canonical_reddit_url(value: Any, field: str) -> str:
    raw = _normalize_text(value, field)
    if raw.startswith("/"):
        raw = "https://www.reddit.com" + raw
    parsed = urlsplit(raw)
    host = (parsed.hostname or "").casefold()
    if host not in REDDIT_HOSTS:
        raise ThreadCollectorError(f"{field} must be an official Reddit URL")
    if not parsed.path.startswith("/"):
        raise ThreadCollectorError(f"{field} has no Reddit path")
    path = re.sub(r"/{2,}", "/", parsed.path)
    if not path.endswith("/"):
        path += "/"
    return urlunsplit(("https", "www.reddit.com", path, "", ""))


def _url_has_prompt(url: str, prompt_id: str) -> bool:
    return f"/comments/{prompt_id}/" in urlsplit(url).path.casefold()


def _url_has_response(url: str, response_id: str) -> bool:
    parts = [part.casefold() for part in urlsplit(url).path.split("/") if part]
    return response_id.casefold() in parts


def _author_key(author: str) -> str:
    value = author.strip().casefold()
    return value[2:] if value.startswith("u/") else value


def _tokens(body: str) -> set[str]:
    return {match.group(0).casefold() for match in TOKEN_RE.finditer(body)}


def _jaccard(left: set[str], right: set[str]) -> float:
    if not left and not right:
        return 1.0
    union = left | right
    return len(left & right) / len(union) if union else 0.0


def _prompt_relevance(body: str, prompt: dict[str, Any]) -> dict[str, Any]:
    prompt_text = f"{prompt['title']}\n{prompt['body']}"
    prompt_tokens = {
        token
        for token in _tokens(prompt_text)
        if len(token) >= 4 and token not in PROMPT_STOPWORDS
    }
    body_tokens = _tokens(body)
    matched_tokens = sorted(prompt_tokens & body_tokens)
    prompt_words = _tokens(prompt_text)
    request_prompt = (
        "?" in prompt_text
        or bool(prompt_words & (PROMPT_REQUEST_MARKERS - {"?"}))
    )
    first_person_count = len(FIRST_PERSON_RE.findall(body))
    narrative_marker_count = len(NARRATIVE_RE.findall(body))
    narrative_answer = (
        request_prompt
        and first_person_count >= 2
        and narrative_marker_count >= 1
    )
    return {
        "passed": bool(matched_tokens or narrative_answer),
        "matched_prompt_tokens": matched_tokens,
        "narrative_answer_fallback": narrative_answer,
        "first_person_marker_count": first_person_count,
        "narrative_marker_count": narrative_marker_count,
    }


def _safety_evidence(response: dict[str, Any], body: str) -> dict[str, Any]:
    return source_safety_evidence(response, body)


def _primary_content_type(body: str, word_count: int) -> tuple[str, list[str]]:
    """Classify what the response is, independently from its episode functions."""
    first_person_count = len(FIRST_PERSON_RE.findall(body))
    narrative_marker_count = len(NARRATIVE_RE.findall(body))
    if first_person_count >= 2 and narrative_marker_count >= 1:
        return "personal_account", ["first_person_narrative"]

    for role, patterns in EDITORIAL_ROLE_PATTERNS:
        matches = sorted({pattern.pattern for pattern in patterns if pattern.search(body)})
        if matches and (role != "concise_humor" or word_count <= 260):
            return role, matches

    question_match = re.search(
        r"(?:^|[.!?]\s+)(?:what|when|where|which|who|why|how|did|do|was|were|could|would)\b[^?]{0,180}\?",
        body,
        re.IGNORECASE,
    )
    if question_match:
        return "clarifying_question", ["direct_question"]
    return "substantive_response", ["relevant_self_contained_response"]


def _editorial_functions(body: str, content_type: str) -> tuple[list[str], dict[str, list[str]]]:
    functions: list[str] = []
    evidence: dict[str, list[str]] = {}
    if content_type == "personal_account":
        functions.append("personal_story")
        evidence["personal_story"] = ["first_person_narrative"]

    for function, patterns in EDITORIAL_FUNCTION_PATTERNS:
        matches = sorted({pattern.pattern for pattern in patterns if pattern.search(body)})
        if matches:
            functions.append(function)
            evidence[function] = matches

    if content_type == "clarifying_question" and "counterpoint" not in functions:
        functions.append("counterpoint")
        evidence["counterpoint"] = ["direct_question"]
    if not functions:
        functions.append("context")
        evidence["context"] = ["substantive_relevant_response"]
    return functions, evidence


def _viewer_interest_evidence(
    body: str,
    word_count: int,
    functions: list[str],
) -> dict[str, Any]:
    """Return a deterministic discovery score; it is not a truth or quality claim."""
    first_words = " ".join(body.split()[:70])
    specificity_matches = INTEREST_SPECIFICITY_RE.findall(body)
    emotion_matches = INTEREST_EMOTION_RE.findall(body)
    function_set = set(functions)
    sentence_count = len(re.findall(r"[.!?](?:\s|$)", body))
    paragraph_count = len([part for part in re.split(r"\n\s*\n", body) if part.strip()])

    components = {
        "opening_hook": min(
            15,
            5
            + (5 if INTEREST_EMOTION_RE.search(first_words) else 0)
            + (5 if any(name in function_set for name in ("stakes_or_conflict", "twist_or_payoff")) else 0),
        ),
        "specificity": min(20, len(specificity_matches) * 4),
        "stakes_or_conflict": 15 if "stakes_or_conflict" in function_set else 0,
        "escalation": 15 if "escalation" in function_set else 0,
        "twist_or_payoff": 20 if "twist_or_payoff" in function_set else 0,
        "emotion_or_discussion": min(10, len(emotion_matches) * 2),
        "narration_fit": 5 if 120 <= word_count <= 520 and sentence_count >= 3 else 3,
    }
    score = min(100, sum(components.values()))
    return {
        "score": score,
        "scale": [0, 100],
        "components": components,
        "specificity_signal_count": len(specificity_matches),
        "emotion_signal_count": len(emotion_matches),
        "paragraph_count": paragraph_count,
        "method": "deterministic_source_text_signals_v1",
        "reddit_score_is_truth_evidence": False,
    }


def _editorial_evidence(
    response: dict[str, Any],
    body: str,
    prompt: dict[str, Any],
    word_count: int,
) -> dict[str, Any]:
    natural_length = {
        "passed": MIN_NATURAL_RESPONSE_WORDS <= word_count <= MAX_NATURAL_RESPONSE_WORDS,
        "word_count": word_count,
        "minimum_words": MIN_NATURAL_RESPONSE_WORDS,
        "maximum_words": MAX_NATURAL_RESPONSE_WORDS,
    }
    lexical_quality = source_text_quality_evidence(body)
    lexical_blockers = source_text_quality_blockers(body)
    narration_envelope = {
        "passed": not lexical_blockers,
        **lexical_quality,
        "blocking_reasons": lexical_blockers,
        "maximum_characters_per_word": MAX_SOURCE_CHARACTERS_PER_WORD,
        "maximum_token_characters": MAX_SOURCE_TOKEN_CHARACTERS,
    }
    relevance = _prompt_relevance(body, prompt)
    safety = _safety_evidence(response, body)
    content_type, content_type_matches = _primary_content_type(body, word_count)
    functions, function_matches = _editorial_functions(body, content_type)
    viewer_interest = _viewer_interest_evidence(body, word_count, functions)
    return {
        "natural_length": natural_length,
        "narration_envelope": narration_envelope,
        "prompt_relevance": relevance,
        "safety": safety,
        "content_type": {
            "passed": bool(content_type),
            "type": content_type,
            "matched_signals": content_type_matches,
        },
        "editorial_functions": {
            "passed": bool(functions),
            "functions": functions,
            "matched_signals": function_matches,
        },
        "viewer_interest": viewer_interest,
    }


def _truth_mode(snapshot: dict[str, Any]) -> str:
    value = snapshot.get("truth_mode")
    if value is None and isinstance(snapshot.get("prompt"), dict):
        value = snapshot["prompt"].get("truth_mode")
    truth_mode = _normalize_text(value, "truth_mode")
    if truth_mode not in TRUTH_MODES:
        allowed = ", ".join(sorted(TRUTH_MODES))
        raise ThreadCollectorError(f"truth_mode must be one of: {allowed}")
    return truth_mode


def _normalize_prompt(snapshot: dict[str, Any]) -> dict[str, Any]:
    prompt = snapshot.get("prompt")
    if not isinstance(prompt, dict):
        raise ThreadCollectorError("prompt must be a JSON object")
    prompt_id = _normalize_id(prompt.get("id"), "prompt.id")
    title = _normalize_text(prompt.get("title"), "prompt.title")
    body = _normalize_text(prompt.get("body", ""), "prompt.body", required=False)
    prompt_text = re.sub(r"\s+", " ", f"{title} {body}").strip()
    prompt_tokens = TOKEN_RE.findall(prompt_text)
    if len(prompt_text) > MAX_PROMPT_CHARACTERS:
        raise ThreadCollectorError("prompt exceeds the 2000-character narration limit")
    if any(len(token) > MAX_SOURCE_TOKEN_CHARACTERS for token in prompt_tokens):
        raise ThreadCollectorError("prompt contains an overlong narration token")
    prompt_quality_blockers = source_text_quality_blockers(prompt_text)
    if prompt_quality_blockers:
        raise ThreadCollectorError(
            "prompt failed lexical narration quality: "
            + ", ".join(prompt_quality_blockers)
        )
    source_url = _canonical_reddit_url(_source_value(prompt), "prompt.source_url")
    if not _url_has_prompt(source_url, prompt_id):
        raise ThreadCollectorError("prompt.source_url does not contain prompt.id")

    subreddit = _normalize_text(prompt.get("subreddit"), "prompt.subreddit")
    author_value = prompt.get("author")
    author = None
    if author_value is not None:
        author = _normalize_text(author_value, "prompt.author")
    score = prompt.get("score")
    if score is not None and (isinstance(score, bool) or not isinstance(score, int)):
        raise ThreadCollectorError("prompt.score must be an integer when present")

    content = {
        "id": prompt_id,
        "subreddit": subreddit,
        "author": author,
        "score": score,
        "title": title,
        "body": body,
        "source_url": source_url,
        "body_sha256": _sha256_text(body),
    }
    content["prompt_sha256"] = _content_hash(
        {
            "id": prompt_id,
            "title": title,
            "body": body,
            "source_url": source_url,
        }
    )
    return content


def _truthy_flag(mapping: dict[str, Any], keys: tuple[str, ...]) -> bool:
    return any(mapping.get(key) is True for key in keys)


def _nonempty_field(mapping: dict[str, Any], keys: tuple[str, ...]) -> bool:
    for key in keys:
        value = mapping.get(key)
        if value not in (None, False, "", [], {}):
            return True
    return False


def _response_rejection(
    response: Any,
    prompt: dict[str, Any],
    *,
    enforce_editorial_gates: bool,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    prompt_id = prompt["id"]
    if not isinstance(response, dict):
        return None, {
            "response_ref": _content_hash(response)[:16],
            "response_id": None,
            "author": None,
            "source_url": None,
            "reason_codes": ["response_not_object"],
        }

    reasons: set[str] = set()
    response_id: str | None = None
    author: str | None = None
    body = ""
    score: int | None = None
    source_url: str | None = None
    parent_id: str | None = None

    try:
        response_id = _normalize_id(response.get("id"), "response.id")
    except ThreadCollectorError:
        reasons.add("missing_or_invalid_response_id")

    try:
        author = _normalize_text(response.get("author"), "response.author")
    except ThreadCollectorError:
        reasons.add("missing_author_provenance")
    if author and _author_key(author) in {"[deleted]", "[removed]", "deleted", "removed"}:
        reasons.add("deleted_or_removed_author")

    score_value = response.get("score")
    if isinstance(score_value, bool) or not isinstance(score_value, int):
        reasons.add("missing_or_invalid_score_provenance")
    else:
        score = score_value

    try:
        body = _normalize_text(response.get("body"), "response.body")
    except ThreadCollectorError:
        reasons.add("missing_body")
    normalized_body = body.casefold()
    if normalized_body in DELETED_MARKERS:
        reasons.add("deleted_or_removed_body")
    if normalized_body in TRUNCATION_MARKERS:
        reasons.add("truncated_body")

    if _truthy_flag(
        response,
        ("deleted", "is_deleted", "removed", "is_removed", "banned_by_reddit"),
    ):
        reasons.add("deleted_or_removed_body")
    if _nonempty_field(response, ("removed_by", "removed_by_category")):
        reasons.add("deleted_or_removed_body")
    if _truthy_flag(
        response,
        ("truncated", "is_truncated", "body_truncated", "body_is_truncated", "is_body_truncated"),
    ):
        reasons.add("truncated_body")
    if response.get("complete") is False or response.get("is_complete") is False:
        reasons.add("incomplete_body")

    try:
        source_url = _canonical_reddit_url(_source_value(response), "response.source_url")
    except ThreadCollectorError:
        reasons.add("missing_or_invalid_source_provenance")
    if source_url and response_id:
        if not _url_has_prompt(source_url, prompt_id) or not _url_has_response(source_url, response_id):
            reasons.add("source_provenance_mismatch")

    raw_parent_id = response.get("parent_id")
    if isinstance(raw_parent_id, str) and raw_parent_id.strip():
        parent_id = raw_parent_id.strip().casefold()
        if parent_id not in {prompt_id, f"t3_{prompt_id}"}:
            reasons.add("not_top_level_response")
    else:
        reasons.add("missing_parent_provenance")
    if response.get("depth") not in (None, 0):
        reasons.add("not_top_level_response")
    if response.get("is_top_level") is False:
        reasons.add("not_top_level_response")

    if _truthy_flag(
        response,
        (
            "depends_on_external_context",
            "depends_on_link",
            "depends_on_screenshot",
            "depends_on_screenshot_or_link",
            "has_external_dependency",
            "is_link_dependent",
            "is_screenshot_dependent",
            "link_dependent",
            "screenshot_dependent",
        ),
    ):
        reasons.add("external_context_dependency")
    if _nonempty_field(
        response,
        ("attachments", "media", "media_metadata", "gallery_data", "outbound_links"),
    ):
        reasons.add("external_context_dependency")
    if body and OUTBOUND_LINK_RE.search(body):
        reasons.add("outbound_link_dependency")

    word_count = len(TOKEN_RE.findall(body))
    editorial_evidence: dict[str, Any] | None = None
    if enforce_editorial_gates and body:
        editorial_evidence = _editorial_evidence(response, body, prompt, word_count)
        if not editorial_evidence["natural_length"]["passed"]:
            reasons.add("unnatural_response_length")
        if not editorial_evidence["narration_envelope"]["passed"]:
            reasons.add("unnatural_response_character_density")
        if not editorial_evidence["prompt_relevance"]["passed"]:
            reasons.add("prompt_irrelevant_response")
        if not editorial_evidence["safety"]["passed"]:
            reasons.add("unsafe_response")
        if not editorial_evidence["content_type"]["passed"]:
            reasons.add("missing_content_type")
        if not editorial_evidence["editorial_functions"]["passed"]:
            reasons.add("missing_editorial_function")

    response_ref = response_id or _content_hash(response)[:16]
    if reasons:
        rejection = {
            "response_ref": response_ref,
            "response_id": response_id,
            "author": author,
            "source_url": source_url,
            "reason_codes": sorted(reasons),
        }
        if editorial_evidence is not None:
            rejection["editorial_evidence"] = editorial_evidence
        return None, rejection

    assert response_id is not None
    assert author is not None
    assert score is not None
    assert source_url is not None
    assert parent_id is not None
    body_sha256 = _sha256_text(body)
    candidate = {
        "id": response_id,
        "author": author,
        "score": score,
        "body": body,
        "body_sha256": body_sha256,
        "source_url": source_url,
        "parent_id": f"t3_{prompt_id}",
        "word_count": word_count,
        "character_count": len(body),
        "_author_key": _author_key(author),
        "_tokens": _tokens(body),
    }
    if editorial_evidence is not None:
        candidate["_editorial_evidence"] = editorial_evidence
        candidate["_content_type"] = editorial_evidence["content_type"]["type"]
        candidate["_editorial_functions"] = editorial_evidence["editorial_functions"]["functions"]
        candidate["_viewer_interest_score"] = editorial_evidence["viewer_interest"]["score"]
    return candidate, None


def _raw_source_hash(snapshot: dict[str, Any], truth_mode: str) -> str:
    responses = snapshot.get("responses")
    if not isinstance(responses, list):
        raise ThreadCollectorError("responses must be a JSON array")
    stable_responses = sorted(responses, key=_canonical_json)
    return _content_hash(
        {
            "truth_mode": truth_mode,
            "prompt": snapshot.get("prompt"),
            "responses": stable_responses,
        }
    )


def _deduplicate_candidates(
    candidates: list[dict[str, Any]],
    rejections: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    ordered = sorted(
        candidates,
        key=lambda item: (-item["score"], item["id"], item["body_sha256"], item["source_url"]),
    )
    accepted: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    seen_authors: set[str] = set()
    seen_bodies: set[str] = set()

    for candidate in ordered:
        reason: str | None = None
        if candidate["id"] in seen_ids:
            reason = "duplicate_response_id"
        elif candidate["body_sha256"] in seen_bodies:
            reason = "duplicate_response_body"
        elif candidate["_author_key"] in seen_authors:
            reason = "duplicate_response_author"
        elif any(
            _jaccard(candidate["_tokens"], previous["_tokens"]) >= NEAR_DUPLICATE_JACCARD
            for previous in accepted
        ):
            reason = "near_duplicate_response"

        if reason:
            rejections.append(
                {
                    "response_ref": candidate["id"],
                    "response_id": candidate["id"],
                    "author": candidate["author"],
                    "source_url": candidate["source_url"],
                    "reason_codes": [reason],
                }
            )
            continue

        accepted.append(candidate)
        seen_ids.add(candidate["id"])
        seen_authors.add(candidate["_author_key"])
        seen_bodies.add(candidate["body_sha256"])
    return accepted


def _max_pairwise_jaccard(responses: list[dict[str, Any]]) -> float:
    maximum = 0.0
    for index, left in enumerate(responses):
        for right in responses[index + 1 :]:
            maximum = max(maximum, _jaccard(left["_tokens"], right["_tokens"]))
    return round(maximum, 6)


def _public_response(response: dict[str, Any], rank: int) -> dict[str, Any]:
    public = {
        "rank": rank,
        "id": response["id"],
        "author": response["author"],
        "score": response["score"],
        "body": response["body"],
        "body_sha256": response["body_sha256"],
        "source_url": response["source_url"],
        "parent_id": response["parent_id"],
        "word_count": response["word_count"],
        "character_count": response["character_count"],
    }
    if "_editorial_evidence" in response:
        public["content_type"] = response["_content_type"]
        public["editorial_functions"] = response["_editorial_functions"]
        # Compatibility field for older readers; it now describes content, not episode function.
        public["editorial_role"] = response["_content_type"]
        public["viewer_interest_score"] = response["_viewer_interest_score"]
        public["editorial_evidence"] = response["_editorial_evidence"]
    return public


def _sorted_rejections(rejections: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        rejections,
        key=lambda item: (
            str(item.get("response_id") or item.get("response_ref") or ""),
            str(item.get("author") or ""),
            tuple(item.get("reason_codes") or []),
        ),
    )


def _select_production_responses(
    eligible: list[dict[str, Any]],
    max_responses: int,
) -> tuple[list[dict[str, Any]], list[str], list[str], None]:
    """Optimize the whole source set for interest, runtime, and episode functions.

    Reddit score is used only as a deterministic tiebreaker after source-text
    interest.  Exact dynamic programming avoids the former greedy false-negative
    where short high-score responses prevented a feasible long-form set.
    """
    function_names = sorted(
        {
            str(function)
            for response in eligible
            for function in response.get("_editorial_functions") or []
        }
    )
    function_bits = {name: 1 << index for index, name in enumerate(function_names)}

    # states[count][(word_sum, function_mask)] =
    # (interest_sum, reddit_tiebreak_sum, selected_candidate_indices)
    states: list[dict[tuple[int, int], tuple[int, int, tuple[int, ...]]]] = [
        {} for _ in range(min(max_responses, len(eligible)) + 1)
    ]
    states[0][(0, 0)] = (0, 0, ())

    for index, response in enumerate(eligible):
        response_words = int(response["word_count"])
        interest_score = int(response.get("_viewer_interest_score") or 0)
        reddit_tiebreak = len(eligible) - index
        response_mask = 0
        for function in response.get("_editorial_functions") or []:
            response_mask |= function_bits[str(function)]

        upper_count = min(index + 1, len(states) - 1)
        for count in range(upper_count, 0, -1):
            for (words, mask), previous in list(states[count - 1].items()):
                next_words = words + response_words
                if next_words > MAX_EPISODE_RESPONSE_WORDS:
                    continue
                next_mask = mask | response_mask
                candidate_state = (
                    previous[0] + interest_score,
                    previous[1] + reddit_tiebreak,
                    previous[2] + (index,),
                )
                key = (next_words, next_mask)
                current = states[count].get(key)
                if current is None or (
                    candidate_state[0],
                    candidate_state[1],
                    tuple(-value for value in candidate_state[2]),
                ) > (
                    current[0],
                    current[1],
                    tuple(-value for value in current[2]),
                ):
                    states[count][key] = candidate_state

    finalists: list[tuple[tuple[float, int, int, int, int, tuple[int, ...]], tuple[int, ...]]] = []
    for count in range(MIN_RESPONSES, len(states)):
        for (words, mask), state in states[count].items():
            distinct_functions = mask.bit_count()
            if words < MIN_EPISODE_RESPONSE_WORDS:
                continue
            if distinct_functions < MIN_EDITORIAL_FUNCTIONS:
                continue
            average_interest = state[0] / count
            objective = (
                average_interest,
                distinct_functions,
                -abs(words - SELECTION_TARGET_WORDS),
                state[0],
                state[1],
                tuple(-value for value in state[2]),
            )
            finalists.append((objective, state[2]))

    if finalists:
        _, selected_indices = max(finalists, key=lambda item: item[0])
        selected = [eligible[index] for index in selected_indices]
        selected = _order_episode_arc(selected)
        selected_ids = {str(response["id"]) for response in selected}
        unselected_ids = [
            str(response["id"]) for response in eligible if str(response["id"]) not in selected_ids
        ]
        return selected, unselected_ids, [], None

    function_supply = Counter(
        str(function)
        for response in eligible
        for function in response.get("_editorial_functions") or ["missing"]
    )
    raise ThreadCollectorError(
        "THREAD production editorial/runtime selection cannot satisfy all hard gates: "
        f"responses={MIN_RESPONSES}-{max_responses}, "
        f"words={MIN_EPISODE_RESPONSE_WORDS}-{MAX_EPISODE_RESPONSE_WORDS}, "
        f"editorial_functions>={MIN_EDITORIAL_FUNCTIONS}, "
        f"function_supply={dict(sorted(function_supply.items()))}"
    )


def _order_episode_arc(selected: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Order a selected set as hook -> rising intensity -> reflective/payoff ending."""
    if len(selected) < 2:
        return selected

    def components(response: dict[str, Any]) -> dict[str, int]:
        evidence = response.get("_editorial_evidence") or {}
        interest = evidence.get("viewer_interest") or {}
        values = interest.get("components") or {}
        return {str(key): int(value) for key, value in values.items()}

    opener = min(
        selected,
        key=lambda response: (
            -components(response).get("opening_hook", 0),
            -int(response.get("_viewer_interest_score") or 0),
            int(response["word_count"]),
            str(response["id"]),
        ),
    )
    remaining = [response for response in selected if response is not opener]
    finale = min(
        remaining,
        key=lambda response: (
            -(
                components(response).get("twist_or_payoff", 0)
                + components(response).get("emotion_or_discussion", 0)
                + (10 if "reflection" in (response.get("_editorial_functions") or []) else 0)
            ),
            -int(response.get("_viewer_interest_score") or 0),
            str(response["id"]),
        ),
    )
    middle = [response for response in remaining if response is not finale]
    middle.sort(
        key=lambda response: (
            components(response).get("stakes_or_conflict", 0)
            + components(response).get("escalation", 0),
            int(response.get("_viewer_interest_score") or 0),
            int(response["score"]),
            str(response["id"]),
        )
    )
    return [opener, *middle, finale]


def collect_thread(
    snapshot: dict[str, Any],
    *,
    max_responses: int = MAX_RESPONSES,
    require_episode_runtime: bool = False,
) -> dict[str, Any]:
    """Validate one snapshot and return a deterministic THREAD manifest.

    The function never calls Reddit or any other external provider.  It raises
    :class:`ThreadCollectorError` rather than returning a partial manifest.
    """
    if not isinstance(snapshot, dict):
        raise ThreadCollectorError("snapshot must be a JSON object")
    if not MIN_RESPONSES <= max_responses <= MAX_RESPONSES:
        raise ThreadCollectorError(
            f"max_responses must be between {MIN_RESPONSES} and {MAX_RESPONSES}"
        )

    truth_mode = _truth_mode(snapshot)
    prompt = _normalize_prompt(snapshot)
    source_snapshot_sha256 = _raw_source_hash(snapshot, truth_mode)
    raw_responses = snapshot.get("responses")
    assert isinstance(raw_responses, list)

    candidates: list[dict[str, Any]] = []
    rejections: list[dict[str, Any]] = []
    for response in raw_responses:
        candidate, rejection = _response_rejection(
            response,
            prompt,
            enforce_editorial_gates=require_episode_runtime,
        )
        if candidate is not None:
            candidates.append(candidate)
        if rejection is not None:
            rejections.append(rejection)

    eligible = _deduplicate_candidates(candidates, rejections)
    if len(eligible) < MIN_RESPONSES:
        reason_counts = Counter(
            reason for item in rejections for reason in item.get("reason_codes") or []
        )
        summary = ", ".join(
            f"{reason}={count}" for reason, count in sorted(reason_counts.items())
        ) or "no valid responses"
        raise ThreadCollectorError(
            f"THREAD requires at least {MIN_RESPONSES} complete distinct responses; "
            f"found {len(eligible)} ({summary})"
        )

    runtime_skipped_ids: list[str] = []
    editorial_role_skipped_ids: list[str] = []
    editorial_role_cap_count: int | None = None
    if require_episode_runtime:
        (
            selected,
            runtime_skipped_ids,
            editorial_role_skipped_ids,
            editorial_role_cap_count,
        ) = _select_production_responses(eligible, max_responses)
    else:
        selected = eligible[:max_responses]
    public_responses = [
        _public_response(response, rank)
        for rank, response in enumerate(selected, start=1)
    ]
    max_similarity = _max_pairwise_jaccard(selected)
    word_counts = [response["word_count"] for response in selected]
    aggregate_response_word_count = sum(word_counts)
    episode_runtime_fit = (
        MIN_EPISODE_RESPONSE_WORDS
        <= aggregate_response_word_count
        <= MAX_EPISODE_RESPONSE_WORDS
    )
    if require_episode_runtime and not episode_runtime_fit:
        raise ThreadCollectorError("internal runtime selector produced an invalid THREAD envelope")
    scores = [response["score"] for response in selected]
    content_type_counts = Counter(
        str(response.get("_content_type")) for response in selected
        if response.get("_content_type")
    )
    editorial_function_counts = Counter(
        str(function)
        for response in selected
        for function in response.get("_editorial_functions") or []
    )
    rejection_counts = Counter(
        reason for item in rejections for reason in item.get("reason_codes") or []
    )

    manifest: dict[str, Any] = {
        "schema_version": 2,
        "status": "READY",
        "channel_id": "acc1",
        "format": "THREAD",
        "source_type": "reddit_thread_snapshot",
        "network_accessed": False,
        "publication_authorized": False,
        "truth_mode": truth_mode,
        "source_snapshot_sha256": source_snapshot_sha256,
        "prompt": prompt,
        "response_count": len(public_responses),
        "aggregate_response_word_count": aggregate_response_word_count,
        "estimated_response_minutes_at_130_wpm": round(aggregate_response_word_count / 130, 2),
        "episode_runtime_target_words": [MIN_EPISODE_RESPONSE_WORDS, MAX_EPISODE_RESPONSE_WORDS],
        "episode_runtime_fit": episode_runtime_fit,
        "responses": public_responses,
        "selection": {
            "minimum_required": MIN_RESPONSES,
            "maximum_allowed": MAX_RESPONSES,
            "selection_limit": max_responses,
            "eligible_distinct_count": len(eligible),
            "unselected_eligible_count": max(0, len(eligible) - len(selected)),
            "ordering": (
                "optimized_source_interest_set_then_hook_rising_payoff_episode_arc"
                if require_episode_runtime else "score_desc_then_response_id_asc"
            ),
            "runtime_selection": (
                "exact_interest_runtime_function_optimizer_v3"
                if require_episode_runtime else "not_applied"
            ),
            "optimizer_unselected_response_ids": runtime_skipped_ids,
            "runtime_skipped_response_ids": [],
            "editorial_role_skipped_response_ids": editorial_role_skipped_ids,
            "reddit_score_usage": "tiebreak_only_after_source_text_interest",
            "episode_arc": (
                "hook_then_rising_intensity_then_reflective_or_payoff_finale"
                if require_episode_runtime else "not_applied"
            ),
        },
        "editorial_gate_evidence": {
            "applied": require_episode_runtime,
            "score_can_override_blocker": False,
            "natural_response_word_range": [
                MIN_NATURAL_RESPONSE_WORDS,
                MAX_NATURAL_RESPONSE_WORDS,
            ],
            "prompt_relevance_required": require_episode_runtime,
            "safety_required": require_episode_runtime,
            "content_type_is_separate_from_episode_function": True,
            "minimum_distinct_functions": MIN_EDITORIAL_FUNCTIONS,
            "distinct_functions": len(editorial_function_counts),
            "function_counts": dict(sorted(editorial_function_counts.items())),
            "content_type_counts": dict(sorted(content_type_counts.items())),
            "personal_account_share_cap": None,
            "legacy_role_cap_count": editorial_role_cap_count,
            "passed": (
                not require_episode_runtime
                or len(editorial_function_counts) >= MIN_EDITORIAL_FUNCTIONS
            ),
        },
        "viewer_interest_evidence": {
            "method": "deterministic_source_text_signals_v1",
            "selected_scores": [
                int(response.get("_viewer_interest_score") or 0) for response in selected
            ],
            "selected_score_average": round(
                sum(int(response.get("_viewer_interest_score") or 0) for response in selected)
                / len(selected),
                2,
            ),
            "reddit_score_is_discovery_signal_only": True,
            "reddit_content_claimed_as_fact": False,
        },
        "diversity_evidence": {
            "responses_are_diverse": (
                len({response["id"] for response in selected}) == len(selected)
                and len({response["_author_key"] for response in selected}) == len(selected)
                and len({response["body_sha256"] for response in selected}) == len(selected)
                and max_similarity < NEAR_DUPLICATE_JACCARD
            ),
            "distinct_response_ids": len({response["id"] for response in selected}),
            "distinct_authors": len({response["_author_key"] for response in selected}),
            "distinct_body_hashes": len({response["body_sha256"] for response in selected}),
            "near_duplicate_jaccard_threshold": NEAR_DUPLICATE_JACCARD,
            "max_pairwise_token_jaccard": max_similarity,
            "score_min": min(scores),
            "score_max": max(scores),
            "word_count_min": min(word_counts),
            "word_count_max": max(word_counts),
            "word_count_median": median(word_counts),
        },
        "completeness_evidence": {
            "all_selected_top_level": True,
            "all_selected_have_full_bodies": True,
            "raw_body_truncation_applied": False,
            "all_selected_self_contained": True,
        },
        "rejections": _sorted_rejections(rejections),
        "rejection_reason_counts": dict(sorted(rejection_counts.items())),
        "integrity": {
            "algorithm": "sha256",
            "canonicalization": "json-sort-keys-utf8-v1",
            "hash_excludes": "manifest_sha256",
        },
    }
    manifest["manifest_sha256"] = _content_hash(manifest)
    return manifest


def verify_manifest(manifest: dict[str, Any]) -> bool:
    """Return whether a manifest still matches its immutable SHA-256 hash."""
    if not isinstance(manifest, dict):
        return False
    expected = manifest.get("manifest_sha256")
    if not isinstance(expected, str) or not re.fullmatch(r"[0-9a-f]{64}", expected):
        return False
    unhashed = copy.deepcopy(manifest)
    unhashed.pop("manifest_sha256", None)
    actual = _content_hash(unhashed)
    return hmac.compare_digest(expected, actual)


def read_snapshot(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ThreadCollectorError(f"cannot read snapshot {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ThreadCollectorError(f"{path} must contain a JSON object")
    return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, help="Network-free Reddit THREAD snapshot JSON")
    parser.add_argument("--output", required=True, help="Destination manifest JSON")
    parser.add_argument(
        "--max-responses",
        type=int,
        choices=range(MIN_RESPONSES, MAX_RESPONSES + 1),
        default=MAX_RESPONSES,
        help="Deterministic response cap (8-15; default: 15)",
    )
    parser.add_argument(
        "--require-episode-runtime",
        action="store_true",
        help="Require 1950-3250 aggregate response words for a production episode",
    )
    args = parser.parse_args(argv)

    try:
        manifest = collect_thread(
            read_snapshot(Path(args.input)),
            max_responses=args.max_responses,
            require_episode_runtime=args.require_episode_runtime,
        )
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    except ThreadCollectorError as exc:
        print(json.dumps({"status": "BLOCKED", "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1

    print(
        json.dumps(
            {
                "status": manifest["status"],
                "response_count": manifest["response_count"],
                "manifest_sha256": manifest["manifest_sha256"],
                "output": str(output),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
