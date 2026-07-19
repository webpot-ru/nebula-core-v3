#!/usr/bin/env python3
"""Fail closed when a channel is explicitly disabled for legacy publishing."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Sequence


def check_channel_automation(config: dict[str, Any], channel_id: str) -> dict[str, Any]:
    channels = config.get("channels")
    if not isinstance(channels, list):
        raise ValueError("channels.json must contain a channels array")
    matches = [item for item in channels if item.get("id") == channel_id]
    if len(matches) != 1:
        raise ValueError(f"channel {channel_id!r} must match exactly one config row")
    channel = matches[0]
    if channel.get("automation_enabled") is False:
        raise ValueError(f"channel {channel_id} automation_enabled=false")
    videos_per_day = channel.get("videos_per_day")
    if isinstance(videos_per_day, bool) or not isinstance(videos_per_day, int):
        raise ValueError(f"channel {channel_id} videos_per_day must be an integer")
    if videos_per_day <= 0:
        raise ValueError(f"channel {channel_id} videos_per_day must be greater than zero")
    return {
        "channel_id": channel_id,
        "automation_allowed": True,
        "videos_per_day": videos_per_day,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--channels", default="channels.json")
    parser.add_argument("--channel", required=True)
    args = parser.parse_args(argv)
    config = json.loads(Path(args.channels).read_text(encoding="utf-8"))
    try:
        result = check_channel_automation(config, args.channel)
    except ValueError as exc:
        parser.error(str(exc))
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
