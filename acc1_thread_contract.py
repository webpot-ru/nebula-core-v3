"""Canonical production envelope for long acc1 THREAD episodes."""

from __future__ import annotations


THREAD_TARGET_DURATION_MINUTES = (24, 30)
THREAD_RESPONSE_COUNT = (13, 15)
THREAD_AGGREGATE_RESPONSE_WORD_COUNT = (3120, 3900)
THREAD_COMIC_PAGE_COUNT = (16, 20)
THREAD_WORDS_PER_MINUTE = 130
THREAD_TARGET_NARRATION_WORDS_PER_PAGE = 195


def in_closed_range(value: int | float, bounds: tuple[int, int]) -> bool:
    """Return whether ``value`` is inside one inclusive two-value envelope."""

    return bounds[0] <= value <= bounds[1]
