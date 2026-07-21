#!/usr/bin/env python3
"""Resume the fixed acc1 release from a saved artifact without provider POSTs."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from acc1_episode_factory import NARRATOR_VOICE_ID
from acc1_narration_profiles import resolve_narration_profile
from acc1_visual_contract import EDITORIAL_MOTION_MODE
from chrome_guided_webtoon_renderer import render_chrome_guided_webtoon
from compilation_storyboard import build_storyboard
from compilation_tts_runner import run_compilation_tts
from scripts.run_acc1_fixed_first_release import (
    BRAND_CTA_ASSET,
    BRAND_OUTRO_ASSET,
    BRAND_STING_ASSET,
    PROFILE_ID,
    sha256_file,
    write_json,
)


class RecoveryError(RuntimeError):
    pass


def _read(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RecoveryError(f"unreadable recovery evidence: {path.name}") from exc
    if not isinstance(value, dict):
        raise RecoveryError(f"recovery evidence must be an object: {path.name}")
    return value


def validate_recovery_artifact(root: Path) -> dict[str, Any]:
    root = root.resolve()
    image_journal = _read(root / "provider-attempts/image.json")
    ai33_journal = _read(root / "provider-attempts/ai33.json")
    state = _read(root / "tts/compilation_tts_state.json")
    if image_journal.get("cap") != 69 or len(image_journal.get("attempts") or []) != 69:
        raise RecoveryError("recovery requires the exact 69-call image journal")
    if any(item.get("status") != "COMPLETE" for item in image_journal["attempts"]):
        raise RecoveryError("all image attempts must already be COMPLETE")
    if ai33_journal.get("cap") != 61 or len(ai33_journal.get("attempts") or []) != 61:
        raise RecoveryError("recovery requires the exact 61-task AI33 journal")
    if any(item.get("status") != "COMPLETE" for item in ai33_journal["attempts"]):
        raise RecoveryError("all AI33 submissions must already be COMPLETE")
    chunks = state.get("chunks") or []
    submitted = [item for item in chunks if item.get("status") == "SUBMITTED"]
    complete = [item for item in chunks if item.get("status") == "COMPLETE"]
    if len(chunks) != 61 or len(complete) != 60 or len(submitted) != 1:
        raise RecoveryError("recovery requires exactly 60 COMPLETE and one SUBMITTED TTS chunk")
    task_id = str(submitted[0].get("task_id") or "")
    if not task_id:
        raise RecoveryError("submitted recovery chunk has no durable AI33 task id")
    required = [root / "episode-script.json", root / "youtube-thumbnail.png"]
    required.extend(root / "scene-images" / f"story-{story:02d}-{post}-scene-{scene:03d}-{role}.png"
                    for story, post, count in ((1, "1uw7804", 9), (2, "1v0l1ei", 9), (3, "1uy2j23", 8), (4, "1uviexk", 8))
                    for scene in range(1, count + 1) for role in ("hero_plate", "detail_plate"))
    missing = [path.relative_to(root).as_posix() for path in required if not path.is_file()]
    if missing:
        raise RecoveryError("recovery artifact is missing files: " + ", ".join(missing[:5]))
    return {
        "status": "RECOVERY_PREFLIGHT_PASS",
        "image_calls_reused": 69,
        "ai33_tasks_reused": 61,
        "completed_audio_reused": 60,
        "existing_task_to_poll": task_id,
        "new_image_calls_authorized": 0,
        "new_ai33_submissions_authorized": 0,
        "publication_authorized": False,
    }


def _refuse_post(**_: Any) -> dict[str, Any]:
    raise RecoveryError("recovery is forbidden from creating a new AI33 task")


def recover(root: Path) -> dict[str, Any]:
    root = root.resolve()
    preflight = validate_recovery_artifact(root)
    script = _read(root / "episode-script.json")
    profile = resolve_narration_profile(PROFILE_ID, pillar_id="relationships_family")
    tts_state = run_compilation_tts(
        script,
        output_dir=root / "tts",
        artifact_root=root,
        api_key=str(os.environ.get("AI33_API_KEY") or os.environ.get("A133_API_KEY") or ""),
        voice_id=NARRATOR_VOICE_ID,
        narration_profile_id=PROFILE_ID,
        speed=profile["speed"],
        voice_settings_json=profile["voice_settings_json"],
        post_task=_refuse_post,
        poll_error_retries=12,
        overall_timeout_seconds=7_200,
    )
    if tts_state.get("status") != "COMPLETE":
        raise RecoveryError("TTS recovery did not reach COMPLETE")
    audio = root / str(tts_state["final_audio_path"])
    for field, source, duration, placement in (
        ("brand_sting", BRAND_STING_ASSET, 1.5, "after_cold_open"),
        ("brand_cta", BRAND_CTA_ASSET, 3.0, "first_story_midpoint"),
        ("brand_outro", BRAND_OUTRO_ASSET, 6.0, "timeline_end"),
    ):
        destination = root / "branding" / source.name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        script[field] = {
            "local_path": destination.relative_to(root).as_posix(),
            "sha256": sha256_file(destination),
            "duration_sec": duration,
            "placement": placement,
            "audio_policy": "discard",
        }
    write_json(root / "episode-script.json", script)
    storyboard = build_storyboard(
        script, root, tts_state=tts_state, visual_mode=EDITORIAL_MOTION_MODE,
    )
    write_json(root / "storyboard.json", storyboard)
    video = root / "final-output.mp4"
    render_report = render_chrome_guided_webtoon(storyboard, root, video, audio=audio)
    write_json(root / "render-report.json", render_report)
    result = {
        **preflight,
        "status": "READY_FOR_HUMAN_REVIEW",
        "video": video.name,
        "video_sha256": sha256_file(video),
        "thumbnail": "youtube-thumbnail.png",
        "thumbnail_sha256": sha256_file(root / "youtube-thumbnail.png"),
        "new_image_calls": 0,
        "new_ai33_task_submissions": 0,
        "youtube_called": False,
        "publication_authorized": False,
    }
    write_json(root / "fixed-release-recovery-result.json", result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-root", required=True)
    parser.add_argument("--preflight-only", action="store_true")
    args = parser.parse_args()
    root = Path(args.artifact_root)
    result = validate_recovery_artifact(root) if args.preflight_only else recover(root)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RecoveryError as exc:
        raise SystemExit(str(exc)) from exc
