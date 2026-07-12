"""Deterministic contracts for the acc1 artifact-only long-form pilot."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any


TRUTH_MODES = {"fiction", "unverified_personal_account"}
REVIEW_VERDICTS = {"PASS", "REVISE", "BLOCK"}
MIN_SCENES = 6
MAX_SCENES = 10
MIN_MINUTES = 30.0
MAX_MINUTES = 50.0
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


def validate_episode_script(script: dict[str, Any]) -> dict[str, Any]:
    failures: list[str] = []
    warnings: list[str] = []
    snapshot = script.get("source_snapshot")
    if not isinstance(snapshot, dict):
        failures.append("source_snapshot must be an object")
        snapshot = {}
    else:
        failures.extend(validate_source_snapshot(snapshot))

    scenes = script.get("scenes")
    if not isinstance(scenes, list):
        failures.append("scenes must be a list")
        scenes = []
    if not MIN_SCENES <= len(scenes) <= MAX_SCENES:
        failures.append(f"scene count must be between {MIN_SCENES} and {MAX_SCENES}")

    source = normalized_text(f"{snapshot.get('title', '')}\n{snapshot.get('body', '')}")
    seen: set[str] = set()
    total_words = 0
    for index, scene in enumerate(scenes):
        prefix = f"scenes[{index}]"
        if not isinstance(scene, dict):
            failures.append(f"{prefix} must be an object")
            continue
        scene_id = str(scene.get("scene_id") or "").strip()
        if not scene_id:
            failures.append(f"{prefix}.scene_id is required")
        elif scene_id in seen:
            failures.append(f"duplicate scene_id: {scene_id}")
        seen.add(scene_id)
        narration = str(scene.get("narration_ru") or "").strip()
        if not narration:
            failures.append(f"{prefix}.narration_ru is required")
        total_words += len(_words(narration))
        anchors = scene.get("source_anchors")
        if not isinstance(anchors, list) or not anchors:
            failures.append(f"{prefix}.source_anchors must not be empty")
        else:
            for anchor in anchors:
                if normalized_text(anchor) not in source:
                    failures.append(f"{prefix} has an anchor not found in source")
        if scene.get("invented_factual_claims"):
            failures.append(f"{prefix}.invented_factual_claims must be empty")
        if not isinstance(scene.get("change_ledger"), list):
            failures.append(f"{prefix}.change_ledger must be a list")
        if not isinstance(scene.get("visual_beats"), list) or not scene.get("visual_beats"):
            failures.append(f"{prefix}.visual_beats must not be empty")

    minutes = estimate_minutes(total_words)
    if not MIN_MINUTES <= minutes <= MAX_MINUTES:
        failures.append(f"estimated runtime must be {MIN_MINUTES:.0f}-{MAX_MINUTES:.0f} minutes, got {minutes:.2f}")

    disclosure = normalized_text(script.get("disclosure"))
    truth_mode = snapshot.get("truth_mode")
    required_term = "fiction" if truth_mode == "fiction" else "unverified"
    if required_term not in disclosure:
        failures.append(f"disclosure must explicitly label the story as {required_term}")

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
        "scene_count": len(scenes),
        "word_count": total_words,
        "estimated_minutes": minutes,
        "script_hash": content_hash(script),
    }
