#!/usr/bin/env python3
"""Resume the fixed acc1 release from saved provider identities without POSTs."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from acc1_episode_factory import BRAND_CTA_ASSET, BRAND_OUTRO_ASSET, BRAND_STING_ASSET, NARRATOR_VOICE_ID
from acc1_narration_profiles import resolve_narration_profile
from acc1_pronunciation_dictionary import load_acc1_pronunciation_dictionary
from acc1_visual_contract import EDITORIAL_MOTION_MODE
from chrome_guided_webtoon_renderer import build_chrome_guided_segment_plan
from compilation_storyboard import build_storyboard
from compilation_tts_runner import run_compilation_tts
from scripts.run_acc1_fixed_first_release import (
    IMAGE_CAP,
    PROFILE_ID,
    TTS_CAP,
    _fixed_intro_contract,
    _validate_segment_plan,
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


def _dictionary_binding(state: dict[str, Any]) -> tuple[int, str]:
    bindings = {
        (
            item.get("pronunciation_dictionary_id"),
            str(item.get("pronunciation_dictionary_sha256") or "").lower(),
        )
        for item in state.get("chunks") or []
    }
    if len(bindings) != 1:
        raise RecoveryError("saved TTS chunks do not share one pronunciation dictionary")
    dictionary_id, dictionary_sha256 = bindings.pop()
    if isinstance(dictionary_id, bool) or not isinstance(dictionary_id, int) or dictionary_id <= 0:
        raise RecoveryError("saved pronunciation dictionary id is invalid")
    local_dictionary = load_acc1_pronunciation_dictionary()
    if dictionary_sha256 != local_dictionary["sha256"]:
        raise RecoveryError("saved pronunciation dictionary does not match the committed rules")
    return dictionary_id, dictionary_sha256


def validate_recovery_artifact(root: Path) -> dict[str, Any]:
    root = root.resolve()
    image_journal = _read(root / "provider-attempts/image.json")
    ai33_journal = _read(root / "provider-attempts/ai33.json")
    state = _read(root / "tts/compilation_tts_state.json")
    if image_journal.get("cap") != IMAGE_CAP or len(image_journal.get("attempts") or []) != IMAGE_CAP:
        raise RecoveryError("recovery requires the exact 69-call image journal")
    if any(item.get("status") != "COMPLETE" for item in image_journal["attempts"]):
        raise RecoveryError("all image attempts must already be COMPLETE")
    if ai33_journal.get("cap") != TTS_CAP or len(ai33_journal.get("attempts") or []) != TTS_CAP:
        raise RecoveryError("recovery requires the exact 61-task AI33 journal")
    if any(item.get("status") != "COMPLETE" for item in ai33_journal["attempts"]):
        raise RecoveryError("all AI33 submissions must already be COMPLETE")
    chunks = state.get("chunks") or []
    if len(chunks) != TTS_CAP:
        raise RecoveryError("recovery requires the exact 61-chunk TTS state")
    if any(item.get("status") not in {"COMPLETE", "SUBMITTED"} for item in chunks):
        raise RecoveryError("recovery permits only COMPLETE or durable SUBMITTED TTS chunks")
    submitted = [item for item in chunks if item.get("status") == "SUBMITTED"]
    complete = [item for item in chunks if item.get("status") == "COMPLETE"]
    if not submitted or len(complete) + len(submitted) != TTS_CAP:
        raise RecoveryError("recovery requires at least one durable SUBMITTED TTS chunk")
    task_ids = [str(item.get("task_id") or "").strip() for item in submitted]
    if any(not task_id or len(task_id) > 512 for task_id in task_ids):
        raise RecoveryError("submitted recovery chunk has no durable AI33 task id")
    if len(set(task_ids)) != len(task_ids):
        raise RecoveryError("submitted recovery chunks contain duplicate AI33 task ids")
    for item in complete:
        chunk_id = str(item.get("chunk_id") or "").strip()
        audio = root / "tts" / "segments" / f"{chunk_id}.mp3"
        if (
            not chunk_id
            or not audio.is_file()
            or not item.get("audio_sha256")
            or sha256_file(audio) != item["audio_sha256"]
        ):
            raise RecoveryError("completed TTS chunk audio is missing or changed")
    dictionary_id, dictionary_sha256 = _dictionary_binding(state)
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
        "completed_audio_reused": len(complete),
        "existing_tasks_to_poll": len(submitted),
        "existing_task_ids_sha256": hashlib.sha256(
            "\n".join(sorted(task_ids)).encode("utf-8"),
        ).hexdigest(),
        "pronunciation_dictionary_id": dictionary_id,
        "pronunciation_dictionary_sha256": dictionary_sha256,
        "new_image_calls_authorized": 0,
        "new_ai33_submissions_authorized": 0,
        "publication_authorized": False,
        "youtube_called": False,
    }


def _refuse_post(**_: Any) -> dict[str, Any]:
    raise RecoveryError("recovery is forbidden from creating a new AI33 task")


def _restore_intro_contract(script: dict[str, Any]) -> bool:
    stories = script.get("stories") or []
    if not stories or not isinstance(stories[0], dict):
        raise RecoveryError("fixed release recovery requires its first source-bound story")
    try:
        expected = _fixed_intro_contract(
            intro_ru=str(script.get("intro_ru") or ""),
            truth_disclosure_ru=str(script.get("truth_disclosure_ru") or ""),
            first_story=stories[0],
        )
    except RuntimeError as exc:
        raise RecoveryError(str(exc)) from exc
    existing = script.get("intro_contract")
    if existing is not None and existing != expected:
        raise RecoveryError("saved intro contract differs from the fixed-input source binding")
    script["intro_contract"] = expected
    return existing is None


def prepare_segmented_recovery(root: Path, *, source_run_id: str) -> dict[str, Any]:
    root = root.resolve()
    preflight = validate_recovery_artifact(root)
    script = _read(root / "episode-script.json")
    intro_contract_restored = _restore_intro_contract(script)
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
        pronunciation_dictionary_id=preflight["pronunciation_dictionary_id"],
        pronunciation_dictionary_sha256=preflight["pronunciation_dictionary_sha256"],
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
    segment_plan = build_chrome_guided_segment_plan(storyboard, root)
    segment_indices = _validate_segment_plan(segment_plan)
    write_json(root / "segmented-render-plan.json", segment_plan)
    result = {
        **preflight,
        "status": "SEGMENTED_RENDER_PREPARED",
        "recovery_source_run_id": source_run_id,
        "storyboard": "storyboard.json",
        "storyboard_sha256": sha256_file(root / "storyboard.json"),
        "segment_plan_sha256": sha256_file(root / "segmented-render-plan.json"),
        "master_audio": audio.relative_to(root).as_posix(),
        "master_audio_sha256": sha256_file(audio),
        "thumbnail": "youtube-thumbnail.png",
        "thumbnail_sha256": sha256_file(root / "youtube-thumbnail.png"),
        "image_calls": IMAGE_CAP,
        "ai33_task_submissions": TTS_CAP,
        "segment_count": len(segment_indices),
        "segment_indices": segment_indices,
        "segment_max_duration_sec": segment_plan["max_duration_sec"],
        "new_image_calls": 0,
        "new_ai33_task_submissions": 0,
        "intro_contract_restored": intro_contract_restored,
        "youtube_called": False,
        "publication_authorized": False,
    }
    write_json(root / "segmented-preparation-result.json", result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-root", required=True)
    parser.add_argument("--preflight-only", action="store_true")
    parser.add_argument("--prepare-segmented", action="store_true")
    parser.add_argument("--source-run-id")
    args = parser.parse_args()
    root = Path(args.artifact_root)
    if args.preflight_only == args.prepare_segmented:
        raise SystemExit("choose exactly one recovery action")
    if args.prepare_segmented and not args.source_run_id:
        raise SystemExit("segmented recovery requires --source-run-id")
    result = (
        validate_recovery_artifact(root)
        if args.preflight_only
        else prepare_segmented_recovery(root, source_run_id=str(args.source_run_id))
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RecoveryError as exc:
        raise SystemExit(str(exc)) from exc
