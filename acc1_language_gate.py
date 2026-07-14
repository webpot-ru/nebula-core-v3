"""Deterministic Russian-language evidence for acc1 audience-facing text."""

from __future__ import annotations

import re
from typing import Any


CYRILLIC_RE = re.compile(r"[А-Яа-яЁё]")
LATIN_RE = re.compile(r"[A-Za-z]")
CYRILLIC_WORD_RE = re.compile(r"[А-Яа-яЁё]+")


def russian_text_evidence(
    value: Any,
    *,
    minimum_cyrillic_words: int = 1,
    minimum_cyrillic_letter_ratio: float = 0.60,
) -> dict[str, Any]:
    text = str(value or "").strip()
    cyrillic_letters = len(CYRILLIC_RE.findall(text))
    latin_letters = len(LATIN_RE.findall(text))
    alphabetic_letters = cyrillic_letters + latin_letters
    cyrillic_words = len(CYRILLIC_WORD_RE.findall(text))
    ratio = cyrillic_letters / alphabetic_letters if alphabetic_letters else 0.0
    passed = bool(
        text
        and cyrillic_words >= minimum_cyrillic_words
        and ratio >= minimum_cyrillic_letter_ratio
    )
    return {
        "passed": passed,
        "cyrillic_words": cyrillic_words,
        "cyrillic_letters": cyrillic_letters,
        "latin_letters": latin_letters,
        "cyrillic_letter_ratio": round(ratio, 6),
        "minimum_cyrillic_words": minimum_cyrillic_words,
        "minimum_cyrillic_letter_ratio": minimum_cyrillic_letter_ratio,
    }


def is_russian_text(
    value: Any,
    *,
    minimum_cyrillic_words: int = 1,
    minimum_cyrillic_letter_ratio: float = 0.60,
) -> bool:
    return bool(russian_text_evidence(
        value,
        minimum_cyrillic_words=minimum_cyrillic_words,
        minimum_cyrillic_letter_ratio=minimum_cyrillic_letter_ratio,
    )["passed"])
