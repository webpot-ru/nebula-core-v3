"""Deterministic lexical-quality gates for Reddit source narration.

The checks are intentionally conservative: they reject only obvious numeric or
machine-repetition floods that can satisfy length/runtime counters without
providing a narratable story.  They make no factual claims about Reddit text.
"""

from __future__ import annotations

from collections import Counter
import re
from typing import Any


TOKEN_RE = re.compile(r"[^\W_]+", re.UNICODE)
MAX_SOURCE_CHARACTERS_PER_WORD = 12
MAX_SOURCE_TOKEN_CHARACTERS = 80
MIN_COMPOSITION_TOKENS = 40
MIN_REPETITION_TOKENS = 80
MIN_ALPHABETIC_TOKEN_SHARE = 0.75
MAX_NUMERIC_TOKEN_SHARE = 0.20
MAX_DIGIT_CHARACTER_SHARE = 0.20
MIN_WORD_LIKE_TOKEN_SHARE = 0.75
MAX_DOMINANT_TOKEN_SHARE = 0.18
MIN_UNIQUE_TOKEN_RATIO = 0.08
MAX_IDENTICAL_TOKEN_RUN = 10


def source_text_quality_evidence(value: Any) -> dict[str, Any]:
    normalized = re.sub(r"\s+", " ", str(value or "")).strip()
    tokens = TOKEN_RE.findall(normalized)
    normalized_tokens = [token.casefold() for token in tokens]
    token_count = len(tokens)
    alphabetic_count = sum(any(character.isalpha() for character in token) for token in tokens)
    numeric_count = sum(token.isdigit() for token in tokens)
    alphanumeric_character_count = sum(
        character.isalnum() for token in tokens for character in token
    )
    digit_character_count = sum(
        character.isdigit() for token in tokens for character in token
    )
    word_like_count = sum(
        (
            sum(character.isalpha() for character in token)
            >= max(1, sum(character.isalnum() for character in token) / 2)
        )
        for token in tokens
    )
    counts = Counter(normalized_tokens)
    dominant_count = max(counts.values(), default=0)
    longest_run = 0
    current_run = 0
    previous: str | None = None
    for token in normalized_tokens:
        if token == previous:
            current_run += 1
        else:
            previous = token
            current_run = 1
        longest_run = max(longest_run, current_run)
    denominator = max(1, token_count)
    return {
        "normalized_character_count": len(normalized),
        "token_count": token_count,
        "alphabetic_token_share": round(alphabetic_count / denominator, 6),
        "numeric_token_share": round(numeric_count / denominator, 6),
        "digit_character_share": round(
            digit_character_count / max(1, alphanumeric_character_count), 6,
        ),
        "word_like_token_share": round(word_like_count / denominator, 6),
        "dominant_token_share": round(dominant_count / denominator, 6),
        "unique_token_ratio": round(len(counts) / denominator, 6),
        "longest_identical_token_run": longest_run,
        "maximum_token_characters_observed": max((len(token) for token in tokens), default=0),
    }


def source_text_quality_blockers(value: Any) -> list[str]:
    evidence = source_text_quality_evidence(value)
    token_count = int(evidence["token_count"])
    blockers: list[str] = []
    if token_count and evidence["normalized_character_count"] > MAX_SOURCE_CHARACTERS_PER_WORD * token_count:
        blockers.append("unnatural_source_character_density")
    if evidence["maximum_token_characters_observed"] > MAX_SOURCE_TOKEN_CHARACTERS:
        blockers.append("overlong_source_token")
    if evidence["longest_identical_token_run"] > MAX_IDENTICAL_TOKEN_RUN:
        blockers.append("repeated_source_token_run")
    if token_count >= MIN_COMPOSITION_TOKENS:
        if evidence["alphabetic_token_share"] < MIN_ALPHABETIC_TOKEN_SHARE:
            blockers.append("insufficient_alphabetic_token_share")
        if evidence["numeric_token_share"] > MAX_NUMERIC_TOKEN_SHARE:
            blockers.append("excessive_numeric_token_share")
        if evidence["digit_character_share"] > MAX_DIGIT_CHARACTER_SHARE:
            blockers.append("excessive_source_digit_character_share")
        if evidence["word_like_token_share"] < MIN_WORD_LIKE_TOKEN_SHARE:
            blockers.append("insufficient_word_like_token_share")
    if token_count >= MIN_REPETITION_TOKENS:
        if evidence["dominant_token_share"] > MAX_DOMINANT_TOKEN_SHARE:
            blockers.append("dominant_source_token_repetition")
        if evidence["unique_token_ratio"] < MIN_UNIQUE_TOKEN_RATIO:
            blockers.append("low_source_token_variety")
    return blockers
