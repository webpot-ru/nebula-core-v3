#!/usr/bin/env python3
"""Build the source-locked five-minute silent Ink & Gouache Reportage pilot.

This wrapper keeps the previous contemporary-cutup canary intact. It produces
the same source-faithful eight-beat story with sixteen bounded gpt-image-2
attempts, no automatic retries, and a separate output directory.
"""

from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from build_acc1_reddit_five_minute_cutup_pilot import main
from acc1_visual_contract import INK_GOUACHE_STORY_PAGES_STYLE_PROFILE


if __name__ == "__main__":
    sys.argv.extend([
        "--style-profile", INK_GOUACHE_STORY_PAGES_STYLE_PROFILE,
        "--output-filename", "reddit-five-minute-ink-gouache-pilot.mp4",
    ])
    raise SystemExit(main())
