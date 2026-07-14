"""High-confidence, provider-free safety and PII blockers for Reddit sources."""

from __future__ import annotations

import re
from typing import Any


EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
PHONE_RE = re.compile(r"(?<!\w)(?:\+?\d[\s().-]*){10,15}(?!\w)")
SAFETY_BLOCK_PATTERNS = (
    re.compile(r"\b(?:how\s+to|step[- ]by[- ]step)\b.{0,48}\b(?:make|build)\b.{0,24}\b(?:bomb|explosive)\b", re.IGNORECASE),
    re.compile(r"\byou\s+should\s+(?:kill|hurt)\s+(?:yourself|him|her|them)\b", re.IGNORECASE),
    re.compile(r"\b(?:child|minor|underage)\b.{0,48}\b(?:sex|sexual|nude|porn)\w*\b", re.IGNORECASE),
    re.compile(r"\b(?:home\s+address|phone\s+number|full\s+legal\s+name)\s*(?:is|:)\s*\S+", re.IGNORECASE),
)
SAFETY_FLAG_KEYS = (
    "unsafe", "is_unsafe", "safety_blocked", "contains_personal_data",
    "contains_doxxing", "doxxing", "sexual_content_involving_minors",
    "instructions_for_wrongdoing",
)


def source_safety_evidence(source: dict[str, Any] | None, body: str) -> dict[str, Any]:
    mapping = source if isinstance(source, dict) else {}
    matched_source_flags = sorted(
        key for key in SAFETY_FLAG_KEYS if mapping.get(key) is True
    )
    pattern_ids = [
        f"high_confidence_pattern_{index}"
        for index, pattern in enumerate(SAFETY_BLOCK_PATTERNS, start=1)
        if pattern.search(str(body or ""))
    ]
    pii_pattern_ids: list[str] = []
    if EMAIL_RE.search(str(body or "")):
        pii_pattern_ids.append("email_address")
    if PHONE_RE.search(str(body or "")):
        pii_pattern_ids.append("phone_number")
    blockers = matched_source_flags + pattern_ids + pii_pattern_ids
    return {
        "passed": not blockers,
        "matched_source_flags": matched_source_flags,
        "matched_blocker_ids": pattern_ids + pii_pattern_ids,
    }
