#!/usr/bin/env python3
"""Thin repository-root bootstrap for :mod:`acc1_episode_factory`."""

from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from acc1_episode_factory import EpisodeFactoryError, main  # noqa: E402


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except EpisodeFactoryError as exc:
        print(f"acc1 episode factory blocked: {exc}", file=sys.stderr)
        raise SystemExit(1)
