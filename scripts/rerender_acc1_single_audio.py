#!/usr/bin/env python3
"""Reuse fixed-release art and render one new AI33 master MP3 plus SRT."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from acc1_episode_factory import CallBudget, NARRATOR_VOICE_ID
from acc1_narration_profiles import resolve_narration_profile
from acc1_pronunciation_dictionary import (
    load_acc1_pronunciation_dictionary,
    resolve_acc1_pronunciation_dictionary_id,
)
from acc1_visual_contract import EDITORIAL_MOTION_MODE
from chrome_guided_webtoon_renderer import (
    assemble_chrome_guided_segments,
    build_chrome_guided_segment_plan,
    render_chrome_guided_segment,
)
from compilation_storyboard import build_storyboard
from compilation_tts_runner import build_tts_chunks
from scripts.run_acc1_fixed_first_release import (
    BRAND_CTA_ASSET, BRAND_OUTRO_ASSET, BRAND_STING_ASSET, PROFILE_ID,
    sha256_file, write_json,
)
from single_audio_tts_runner import run_single_audio_tts
from translator_tts import post_tts_task


def validate_completed_artifact(root: Path) -> dict:
    image = json.loads((root / "provider-attempts/image.json").read_text(encoding="utf-8"))
    ai33 = json.loads((root / "provider-attempts/ai33.json").read_text(encoding="utf-8"))
    state = json.loads((root / "tts/compilation_tts_state.json").read_text(encoding="utf-8"))
    if image.get("cap") != 69 or len(image.get("attempts") or []) != 69:
        raise RuntimeError("source artifact does not contain the exact 69 image attempts")
    if any(item.get("status") != "COMPLETE" for item in image["attempts"]):
        raise RuntimeError("source image attempts are incomplete")
    if ai33.get("cap") != 61 or len(ai33.get("attempts") or []) != 61:
        raise RuntimeError("source artifact does not contain the exact historical AI33 journal")
    chunks = state.get("chunks") or []
    if len(chunks) != 61 or any(item.get("status") != "COMPLETE" for item in chunks):
        raise RuntimeError("source artifact must contain 61 checksum-bound completed audio chunks")
    for item in chunks:
        audio = root / "tts/segments" / f"{item['chunk_id']}.mp3"
        if not audio.is_file() or sha256_file(audio) != item.get("audio_sha256"):
            raise RuntimeError("source audio checksum mismatch")
    return {
        "source_image_attempts": 69,
        "source_audio_chunks_verified": 61,
        "publication_authorized": False,
    }


def preflight(root: Path) -> dict:
    evidence = validate_completed_artifact(root)
    script = json.loads((root / "episode-script.json").read_text(encoding="utf-8"))
    profile = resolve_narration_profile(PROFILE_ID, pillar_id="relationships_family")
    dictionary = load_acc1_pronunciation_dictionary()
    planned = build_tts_chunks(
        script, voice_id=NARRATOR_VOICE_ID, narration_profile_id=PROFILE_ID,
        speed=profile["speed"], voice_settings_json=profile["voice_settings_json"],
        pronunciation_dictionary_id=72,
        pronunciation_dictionary_sha256=dictionary["sha256"],
    )
    text = " ".join(item["text"] for item in planned)
    if len(text) > 1_000_000:
        raise RuntimeError("master narration exceeds AI33 v3 character limit")
    return {
        **evidence,
        "status": "SINGLE_AUDIO_PREFLIGHT_PASS",
        "provider_task_cap": 1,
        "automatic_tts_retries": 0,
        "master_character_count": len(text),
        "master_word_count": len(text.split()),
        "with_transcript": True,
        "outputs": ["narration-master.mp3", "narration.srt"],
        "image_calls_authorized": 0,
        "youtube_called": False,
    }


def prepare_segmented(root: Path, *, resume_only: bool = False) -> dict:
    report = preflight(root)
    script = json.loads((root / "episode-script.json").read_text(encoding="utf-8"))
    profile = resolve_narration_profile(PROFILE_ID, pillar_id="relationships_family")
    dictionary = load_acc1_pronunciation_dictionary()
    dictionary_id = resolve_acc1_pronunciation_dictionary_id(required=True)
    provider_dir = root / "provider-attempts"
    if resume_only:
        def ai33(**_kwargs):
            raise RuntimeError("resume-only recovery forbids new AI33 submissions")
    else:
        ai33 = CallBudget(
            post_tts_task, cap=1, label="ai33_single_audio",
            journal_path=provider_dir / "ai33-single-audio.json",
        )
    state = run_single_audio_tts(
        script, output_dir=root / "tts-single", artifact_root=root,
        api_key=str(os.environ.get("AI33_API_KEY") or ""),
        voice_id=NARRATOR_VOICE_ID, narration_profile_id=PROFILE_ID,
        pronunciation_dictionary_id=dictionary_id,
        pronunciation_dictionary_sha256=dictionary["sha256"],
        speed=profile["speed"], voice_settings_json=profile["voice_settings_json"],
        post_task=ai33, resume_only=resume_only,
    )
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
            "sha256": sha256_file(destination), "duration_sec": duration,
            "placement": placement, "audio_policy": "discard",
        }
    write_json(root / "episode-script.json", script)
    storyboard = build_storyboard(
        script, root, tts_state=state, visual_mode=EDITORIAL_MOTION_MODE,
    )
    write_json(root / "storyboard-single-audio.json", storyboard)
    segment_plan = build_chrome_guided_segment_plan(storyboard, root)
    write_json(root / "segmented-render-plan.json", segment_plan)
    result = {
        **report, "status": "SEGMENTED_RENDER_PREPARED",
        "ai33_task_submissions": 0 if resume_only else len(ai33.calls),
        "existing_ai33_task_polled": bool(resume_only),
        "master_audio": state["final_audio_path"],
        "master_audio_sha256": state["final_audio_sha256"],
        "srt": state["master_srt_path"], "srt_sha256": state["master_srt_sha256"],
        "segment_count": segment_plan["segment_count"],
        "segment_indices": [item["index"] for item in segment_plan["segments"]],
        "image_calls": 0, "youtube_called": False, "publication_authorized": False,
    }
    write_json(root / "single-audio-preparation-result.json", result)
    return result


def render_segment(root: Path, segment_index: int) -> dict:
    preparation = json.loads(
        (root / "single-audio-preparation-result.json").read_text(encoding="utf-8"),
    )
    if (
        preparation.get("status") != "SEGMENTED_RENDER_PREPARED"
        or preparation.get("ai33_task_submissions") != 0
        or preparation.get("image_calls") != 0
        or preparation.get("youtube_called") is not False
    ):
        raise RuntimeError("segment render requires a zero-new-call preparation result")
    storyboard = json.loads((root / "storyboard-single-audio.json").read_text(encoding="utf-8"))
    output = root / "render-segments" / f"segment-{segment_index:03d}.mp4"
    segment_report = render_chrome_guided_segment(
        storyboard, root, segment_index, output,
    )
    write_json(
        root / "render-segments" / f"segment-{segment_index:03d}.json",
        segment_report,
    )
    return segment_report


def assemble_segmented(root: Path) -> dict:
    preparation = json.loads(
        (root / "single-audio-preparation-result.json").read_text(encoding="utf-8"),
    )
    if (
        preparation.get("status") != "SEGMENTED_RENDER_PREPARED"
        or preparation.get("ai33_task_submissions") != 0
        or preparation.get("image_calls") != 0
        or preparation.get("youtube_called") is not False
    ):
        raise RuntimeError("assembly requires a zero-new-call preparation result")
    storyboard = json.loads((root / "storyboard-single-audio.json").read_text(encoding="utf-8"))
    plan = json.loads((root / "segmented-render-plan.json").read_text(encoding="utf-8"))
    segment_paths = [
        root / "render-segments" / f"segment-{int(item['index']):03d}.mp4"
        for item in plan["segments"]
    ]
    video = root / "final-output-single-audio.mp4"
    audio = root / str(preparation["master_audio"])
    render_report = assemble_chrome_guided_segments(
        storyboard, root, segment_paths, video, audio=audio,
    )
    write_json(root / "render-report-single-audio.json", render_report)
    result = {
        **preparation, "status": "READY_FOR_HUMAN_REVIEW",
        "video": video.name, "video_sha256": sha256_file(video),
        "render_segment_count": render_report["segment_count"],
        "temporary_frame_workspaces_removed": True,
    }
    write_json(root / "single-audio-rerender-result.json", result)
    return result


def produce(root: Path, *, resume_only: bool = False) -> dict:
    preparation = prepare_segmented(root, resume_only=resume_only)
    for segment_index in preparation["segment_indices"]:
        render_segment(root, int(segment_index))
    return assemble_segmented(root)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-root", required=True)
    parser.add_argument("--produce", action="store_true")
    parser.add_argument("--prepare-segmented", action="store_true")
    parser.add_argument("--render-segment", type=int)
    parser.add_argument("--assemble-segmented", action="store_true")
    parser.add_argument("--confirm-one-ai33-task", action="store_true")
    parser.add_argument("--resume-existing-task-only", action="store_true")
    args = parser.parse_args()
    root = Path(args.artifact_root).resolve()
    actions = sum((
        bool(args.produce), bool(args.prepare_segmented),
        args.render_segment is not None, bool(args.assemble_segmented),
    ))
    if actions > 1:
        raise RuntimeError("choose exactly one production action")
    if (args.produce or args.prepare_segmented) and not (
        args.confirm_one_ai33_task or args.resume_existing_task_only
    ):
        raise RuntimeError("provider preparation requires an explicit confirmation")
    if args.confirm_one_ai33_task and args.resume_existing_task_only:
        raise RuntimeError("new-task and resume-only confirmations are mutually exclusive")
    if args.produce:
        result = produce(root, resume_only=args.resume_existing_task_only)
    elif args.prepare_segmented:
        result = prepare_segmented(root, resume_only=args.resume_existing_task_only)
    elif args.render_segment is not None:
        result = render_segment(root, args.render_segment)
    elif args.assemble_segmented:
        result = assemble_segmented(root)
    else:
        result = preflight(root)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
