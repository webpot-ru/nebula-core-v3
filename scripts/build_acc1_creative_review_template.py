#!/usr/bin/env python3
"""Create a checksum-bound, fail-closed creative-review template for acc1."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


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


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_template(video: Path, thumbnail: Path) -> dict:
    if not video.is_file() or not thumbnail.is_file():
        raise FileNotFoundError("video and thumbnail must exist")
    return {
        "version": 1,
        "status": "BLOCKED",
        "publication_authorized": False,
        "video_sha256": sha256_file(video),
        "thumbnail_sha256": sha256_file(thumbnail),
        "reviewer": None,
        "reviewed_at": None,
        "notes": "",
        "checks": {field: False for field in CHECKS},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--video", required=True)
    parser.add_argument("--thumbnail", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    payload = build_template(Path(args.video), Path(args.thumbnail))
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "BLOCKED", "output": str(output), "publication_authorized": False}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
