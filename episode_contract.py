"""Deterministic contract for an acc1 artifact-only Reddit horror compilation."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any


TRUTH_MODES = {"fiction", "unverified_personal_account"}
REVIEW_VERDICTS = {"PASS", "REVISE", "BLOCK"}
MIN_STORIES = 3
MAX_STORIES = 6
TARGET_MINUTES = 45.0
TARGET_MAX_MINUTES = 60.0
HARD_MIN_MINUTES = 40.0
HARD_MAX_MINUTES = 70.0
DEFAULT_WORDS_PER_MINUTE = 130.0


def normalized_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").casefold()).strip()


def content_hash(payload: Any) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def estimate_minutes(word_count: int, words_per_minute: float = DEFAULT_WORDS_PER_MINUTE) -> float:
    if words_per_minute <= 0:
        raise ValueError("words_per_minute must be positive")
    return round(word_count / words_per_minute, 2)


def _words(value: Any) -> list[str]:
    return re.findall(r"[\wЁёА-Яа-я-]+", str(value or ""), flags=re.UNICODE)


def validate_source_snapshot(snapshot: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    for key in ("post_id", "source_url", "subreddit", "title", "body", "truth_mode"):
        if not str(snapshot.get(key) or "").strip():
            failures.append(f"source_snapshot.{key} is required")
    if snapshot.get("truth_mode") not in TRUTH_MODES:
        failures.append("source_snapshot.truth_mode must be fiction or unverified_personal_account")
    expected = hashlib.sha256(str(snapshot.get("body") or "").encode("utf-8")).hexdigest()
    if snapshot.get("body_sha256") != expected:
        failures.append("source_snapshot.body_sha256 does not match body")
    return failures


def validate_compilation(script: dict[str, Any]) -> dict[str, Any]:
    failures: list[str] = []
    warnings: list[str] = []
    if script.get("publication_authorized") is not False:
        failures.append("publication_authorized must be false for internal pilots")
    if script.get("rights_mode") != "test_only_not_cleared":
        failures.append("rights_mode must be test_only_not_cleared")

    stories = script.get("stories")
    if not isinstance(stories, list):
        failures.append("stories must be a list")
        stories = []
    if not MIN_STORIES <= len(stories) <= MAX_STORIES:
        failures.append(f"story count must be between {MIN_STORIES} and {MAX_STORIES}")

    seen: set[str] = set()
    total_words = 0
    truth_modes: set[str] = set()
    for index, story in enumerate(stories):
        prefix = f"stories[{index}]"
        if not isinstance(story, dict):
            failures.append(f"{prefix} must be an object")
            continue
        snapshot = story.get("source_snapshot")
        if not isinstance(snapshot, dict):
            failures.append(f"{prefix}.source_snapshot must be an object")
            snapshot = {}
        else:
            failures.extend(f"{prefix}: {item}" for item in validate_source_snapshot(snapshot))
        post_id = str(snapshot.get("post_id") or "").strip()
        if post_id in seen:
            failures.append(f"duplicate post_id: {post_id}")
        seen.add(post_id)
        truth_modes.add(str(snapshot.get("truth_mode") or ""))

        narration = str(story.get("narration_ru") or "").strip()
        if not narration:
            failures.append(f"{prefix}.narration_ru is required")
        total_words += len(_words(narration))
        if re.search(r"(?i)https?://|www\.", narration):
            failures.append(f"{prefix}.narration_ru contains a raw URL")
        if story.get("invented_factual_claims"):
            failures.append(f"{prefix}.invented_factual_claims must be empty")
        if not isinstance(story.get("change_ledger"), list):
            failures.append(f"{prefix}.change_ledger must be a list")
        if not isinstance(story.get("editorial_review"), dict) or story["editorial_review"].get("verdict") != "PASS":
            failures.append(f"{prefix}.editorial_review must PASS")
        if not str(story.get("ending_preserved_evidence") or "").strip():
            failures.append(f"{prefix}.ending_preserved_evidence is required")
        media = snapshot.get("source_media") or []
        if not isinstance(media, list):
            failures.append(f"{prefix}.source_snapshot.source_media must be a list")

        disclosure = normalized_text(story.get("disclosure"))
        required_term = "fiction" if snapshot.get("truth_mode") == "fiction" else "unverified"
        if required_term not in disclosure:
            failures.append(f"{prefix}.disclosure must explicitly label the story as {required_term}")

    minutes = estimate_minutes(total_words)
    if not HARD_MIN_MINUTES <= minutes <= HARD_MAX_MINUTES:
        failures.append(f"estimated runtime must be {HARD_MIN_MINUTES:.0f}-{HARD_MAX_MINUTES:.0f} minutes, got {minutes:.2f}")
    elif not TARGET_MINUTES <= minutes <= TARGET_MAX_MINUTES:
        warnings.append(f"estimated runtime is outside the 45-60 minute target: {minutes:.2f}")
    if len(truth_modes) > 1:
        failures.append("a compilation must not mix fiction and unverified encounter lanes")

    try:
        revision_count = int(script.get("revision_count", 0))
    except (TypeError, ValueError):
        revision_count = 99
    if revision_count < 0 or revision_count > 2:
        failures.append("revision_count must be between 0 and 2")

    review = script.get("editorial_review")
    if review is not None:
        if not isinstance(review, dict) or review.get("verdict") not in REVIEW_VERDICTS:
            failures.append("editorial_review.verdict must be PASS, REVISE, or BLOCK")
        elif review.get("verdict") == "PASS" and review.get("issues"):
            failures.append("PASS editorial review cannot contain unresolved issues")

    return {
        "status": "PASS" if not failures else "BLOCKED",
        "failures": failures,
        "warnings": warnings,
        "story_count": len(stories),
        "word_count": total_words,
        "estimated_minutes": minutes,
        "script_hash": content_hash(script),
    }
