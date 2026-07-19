#!/usr/bin/env python3
"""Create a checksum-bound, fail-closed creative-review template for acc1."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from acc1_visual_contract import (
    CINEMATIC_STORY_MODE,
    DEFAULT_VISUAL_MODE,
    EDITORIAL_MOTION_MODE,
    VISUAL_MODES,
    resolve_visual_mode,
)


CHECKS = (
    "editorial_acceptance",
    "voice_role_confirmed",
    "first_30_seconds_accepted",
    "text_readability_accepted",
    "visual_rhythm_accepted",
    "reddit_ui_sequence_accepted",
    "background_character_accepted",
    "source_visual_blend_accepted",
    "thumbnail_truthful",
    "fiction_disclosure_accepted",
)

CINEMATIC_CHECKS = (
    "editorial_acceptance",
    "voice_role_confirmed",
    "first_30_seconds_accepted",
    "source_truth_card_accepted",
    "fullscreen_scene_semantics_accepted",
    "motion_rhythm_accepted",
    "caption_track_accepted",
    "voice_mix_accepted",
    "brand_anchor_accepted",
    "thumbnail_truthful",
    "fiction_disclosure_accepted",
)

EDITORIAL_MOTION_CHECKS = (
    "editorial_acceptance",
    "voice_role_confirmed",
    "first_30_seconds_accepted",
    "continuous_visual_system_accepted",
    "semantic_transformations_accepted",
    "source_bound_evidence_accepted",
    "motion_rhythm_accepted",
    "caption_track_accepted",
    "voice_mix_accepted",
    "asset_consistency_accepted",
    "thumbnail_truthful",
    "fiction_disclosure_accepted",
)


def checks_for_mode(visual_mode: str) -> tuple[str, ...]:
    mode = resolve_visual_mode(visual_mode)
    if mode == CINEMATIC_STORY_MODE:
        return CINEMATIC_CHECKS
    if mode == EDITORIAL_MOTION_MODE:
        return EDITORIAL_MOTION_CHECKS
    return CHECKS


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_template(
    video: Path,
    thumbnail: Path,
    *,
    visual_mode: str = DEFAULT_VISUAL_MODE,
) -> dict:
    if not video.is_file() or not thumbnail.is_file():
        raise FileNotFoundError("video and thumbnail must exist")
    mode = resolve_visual_mode(visual_mode)
    checks = checks_for_mode(mode)
    return {
        "version": 3,
        "status": "BLOCKED",
        "visual_mode": mode,
        "publication_authorized": False,
        "decision_scope": "private_review_only",
        "human_attested": False,
        "video_sha256": sha256_file(video),
        "thumbnail_sha256": sha256_file(thumbnail),
        "reviewer": None,
        "reviewed_at": None,
        "notes": "",
        "observations": [],
        "checks": {field: False for field in checks},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--video", required=True)
    parser.add_argument("--thumbnail", required=True)
    parser.add_argument(
        "--visual-mode",
        choices=tuple(sorted(VISUAL_MODES)),
        default=DEFAULT_VISUAL_MODE,
    )
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    payload = build_template(
        Path(args.video),
        Path(args.thumbnail),
        visual_mode=args.visual_mode,
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "BLOCKED", "output": str(output), "publication_authorized": False}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
