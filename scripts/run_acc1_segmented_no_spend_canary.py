#!/usr/bin/env python3
"""Exercise the production segmented renderer with frozen acc1 media only.

The GitHub workflow downloads an existing four-page v3 artifact and its
existing narration.  Preparation copies that immutable source into a canonical
artifact root, chooses a short canary-only render ceiling that guarantees more
than one matrix job, and records checksums.  Rendering and assembly never call
VectorEngine, AI33, Reddit, OpenAI, Gemini or YouTube.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import shutil
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from chrome_guided_webtoon_renderer import (
    assemble_chrome_guided_segments,
    build_chrome_guided_segment_plan,
    render_chrome_guided_segment,
)
from compilation_editorial_motion_renderer import (
    DEFAULT_SEGMENT_MAX_DURATION_SEC,
    preflight_editorial_motion_storyboard,
)
from scripts.render_acc1_hyperframes_realistic_test import (
    repair_scene_bindings,
    resolve_existing_audio,
    resolve_generated_storyboard,
    verify_paid_generation_receipt,
)


SOURCE_RUN_ID = "30063115374"
SOURCE_ARTIFACT = f"acc1-panel-grammar-canary-{SOURCE_RUN_ID}"
AUDIO_RUN_ID = "29975009888"
AUDIO_ARTIFACT = f"acc1-format-v3-canary-{AUDIO_RUN_ID}"
EXPECTED_PAGE_COUNT = 5
MIN_SEGMENTS = 2
MAX_SEGMENTS = EXPECTED_PAGE_COUNT
PREPARATION_FILE = "segmented-canary-preparation.json"
PLAN_FILE = "segmented-canary-plan.json"
STORYBOARD_FILE = "storyboard.json"
AUDIO_FILE = "narration-existing.mp3"
FINAL_VIDEO_FILE = "acc1-segmented-no-spend-canary.mp4"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"{path.name} must contain an object")
    return payload


def _write_object(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return path


def _under_root(root: Path, raw: object, *, label: str) -> Path:
    resolved_root = root.resolve()
    path = (resolved_root / str(raw or "")).resolve()
    if path == resolved_root or resolved_root not in path.parents or not path.is_file():
        raise RuntimeError(f"{label} must be a file under the prepared artifact")
    return path


def choose_canary_segment_ceiling(scene_durations: list[float]) -> float:
    """Choose a safe ceiling that forces a multi-job canary without scene cuts."""

    if len(scene_durations) < MIN_SEGMENTS or any(value <= 0 for value in scene_durations):
        raise RuntimeError("segmented canary requires at least two positive scenes")
    longest = max(scene_durations)
    ceiling = math.ceil((longest + 0.010) * 1000) / 1000
    if ceiling > DEFAULT_SEGMENT_MAX_DURATION_SEC:
        raise RuntimeError("existing canary contains a scene above the production ceiling")
    if sum(scene_durations) <= ceiling:
        raise RuntimeError("existing canary cannot prove a multi-segment render")
    return ceiling


def validate_segment_plan(plan: dict[str, Any]) -> list[int]:
    segments = plan.get("segments")
    if not isinstance(segments, list):
        raise RuntimeError("segmented canary plan has no segment list")
    if plan.get("renderer") != "hyperframes_segmented":
        raise RuntimeError("segmented canary plan uses an unexpected renderer")
    indices = [int(item.get("index") or 0) for item in segments]
    if not MIN_SEGMENTS <= len(indices) <= MAX_SEGMENTS:
        raise RuntimeError(
            f"segmented canary requires {MIN_SEGMENTS}-{MAX_SEGMENTS} render jobs",
        )
    if indices != list(range(1, len(indices) + 1)):
        raise RuntimeError("segmented canary indices must be contiguous")
    if int(plan.get("segment_count") or 0) != len(indices):
        raise RuntimeError("segmented canary count does not match its segment list")
    ceiling = float(plan.get("max_duration_sec") or 0)
    if not 0 < ceiling <= DEFAULT_SEGMENT_MAX_DURATION_SEC:
        raise RuntimeError("segmented canary ceiling is outside production limits")
    durations = [float(item.get("duration_sec") or 0) for item in segments]
    if any(not 0 < duration <= ceiling + 0.001 for duration in durations):
        raise RuntimeError("segmented canary contains an empty or oversized segment")
    return indices


def prepare(
    source_root: Path,
    audio_root: Path,
    workdir: Path,
    *,
    source_run_id: str = SOURCE_RUN_ID,
    source_artifact: str = SOURCE_ARTIFACT,
) -> dict[str, Any]:
    source_root = source_root.resolve()
    audio_root = audio_root.resolve()
    workdir = workdir.resolve()
    if source_run_id != SOURCE_RUN_ID or source_artifact != SOURCE_ARTIFACT:
        raise RuntimeError("segmented canary is locked to the approved frozen artifact")
    source_storyboard_path, storyboard = resolve_generated_storyboard(
        source_root,
        expected_page_count=EXPECTED_PAGE_COUNT,
    )
    journal = verify_paid_generation_receipt(
        source_storyboard_path,
        expected_page_count=EXPECTED_PAGE_COUNT,
    )
    storyboard = repair_scene_bindings(storyboard)
    if workdir == source_storyboard_path.parent or workdir in source_storyboard_path.parents:
        raise RuntimeError("prepared output must be separate from the downloaded source")
    workdir.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source_storyboard_path.parent, workdir, dirs_exist_ok=True)

    storyboard_path = _write_object(workdir / STORYBOARD_FILE, storyboard)
    audio_path = resolve_existing_audio(
        audio_root,
        storyboard=storyboard,
        destination=workdir / AUDIO_FILE,
    )
    checked_scenes = preflight_editorial_motion_storyboard(storyboard, workdir)
    ceiling = choose_canary_segment_ceiling([
        float(scene["duration_sec"]) for scene in checked_scenes
    ])
    plan = build_chrome_guided_segment_plan(
        storyboard,
        workdir,
        max_duration_sec=ceiling,
    )
    indices = validate_segment_plan(plan)
    plan_path = _write_object(workdir / PLAN_FILE, plan)
    result = {
        "version": 1,
        "status": "SEGMENTED_NO_SPEND_PREPARED",
        "source_run_id": source_run_id,
        "source_artifact": source_artifact,
        "audio_run_id": AUDIO_RUN_ID,
        "audio_artifact": AUDIO_ARTIFACT,
        "source_storyboard_sha256": _sha256(source_storyboard_path),
        "storyboard": STORYBOARD_FILE,
        "storyboard_sha256": _sha256(storyboard_path),
        "segment_plan": PLAN_FILE,
        "segment_plan_sha256": _sha256(plan_path),
        "audio": AUDIO_FILE,
        "audio_sha256": _sha256(audio_path),
        "source_image_calls": len(journal["attempts"]),
        "source_image_retries": int(journal["automatic_retries"]),
        "new_image_calls": 0,
        "new_ai33_calls": 0,
        "provider_calls": 0,
        "youtube_called": False,
        "publication_authorized": False,
        "render_strategy": "hyperframes_segmented_matrix",
        "segment_count": len(indices),
        "segment_indices": indices,
        "segment_max_duration_sec": ceiling,
    }
    _write_object(workdir / PREPARATION_FILE, result)
    return result


def _load_preparation(
    workdir: Path,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], Path]:
    workdir = workdir.resolve()
    preparation_path = workdir / PREPARATION_FILE
    plan_path = workdir / PLAN_FILE
    storyboard_path = workdir / STORYBOARD_FILE
    preparation = _read_object(preparation_path)
    plan = _read_object(plan_path)
    storyboard = _read_object(storyboard_path)
    indices = validate_segment_plan(plan)
    audio = _under_root(workdir, preparation.get("audio"), label="existing narration")
    if (
        preparation.get("status") != "SEGMENTED_NO_SPEND_PREPARED"
        or preparation.get("source_run_id") != SOURCE_RUN_ID
        or preparation.get("source_artifact") != SOURCE_ARTIFACT
        or preparation.get("audio_run_id") != AUDIO_RUN_ID
        or preparation.get("audio_artifact") != AUDIO_ARTIFACT
        or preparation.get("storyboard_sha256") != _sha256(storyboard_path)
        or preparation.get("segment_plan_sha256") != _sha256(plan_path)
        or preparation.get("audio_sha256") != _sha256(audio)
        or preparation.get("source_image_calls") != EXPECTED_PAGE_COUNT
        or preparation.get("source_image_retries") != 0
        or preparation.get("new_image_calls") != 0
        or preparation.get("new_ai33_calls") != 0
        or preparation.get("provider_calls") != 0
        or preparation.get("youtube_called") is not False
        or preparation.get("publication_authorized") is not False
        or preparation.get("render_strategy") != "hyperframes_segmented_matrix"
        or preparation.get("segment_indices") != indices
        or int(preparation.get("segment_count") or 0) != len(indices)
    ):
        raise RuntimeError("segmented canary preparation is incomplete or unsafe")
    return preparation, plan, storyboard, audio


def render_segment(workdir: Path, segment_index: int) -> dict[str, Any]:
    preparation, plan, storyboard, _ = _load_preparation(workdir)
    indices = validate_segment_plan(plan)
    if segment_index not in indices:
        raise RuntimeError("requested canary segment is outside the matrix")
    output = workdir / "render-segments" / f"segment-{segment_index:03d}.mp4"
    report = render_chrome_guided_segment(
        storyboard,
        workdir,
        segment_index,
        output,
        max_duration_sec=float(plan["max_duration_sec"]),
    )
    result = {
        **report,
        "source_run_id": SOURCE_RUN_ID,
        "source_artifact": SOURCE_ARTIFACT,
        "source_image_calls": EXPECTED_PAGE_COUNT,
        "new_image_calls": 0,
        "new_ai33_calls": 0,
        "provider_calls": 0,
        "youtube_called": False,
        "publication_authorized": False,
    }
    if (
        result.get("status") != "PASS"
        or result.get("render_strategy") != "hyperframes_segmented_matrix"
        or int(result.get("segment_count") or 0) != preparation["segment_count"]
        or result.get("temporary_workspace_removed") is not True
        or result.get("provider_calls") != 0
        or result.get("youtube_called") is not False
    ):
        raise RuntimeError("segmented canary render returned an unsafe report")
    _write_object(
        workdir / "render-segments" / f"segment-{segment_index:03d}.json",
        result,
    )
    return result


def assemble(workdir: Path) -> dict[str, Any]:
    preparation, plan, storyboard, audio = _load_preparation(workdir)
    indices = validate_segment_plan(plan)
    segment_paths = [
        workdir / "render-segments" / f"segment-{index:03d}.mp4"
        for index in indices
    ]
    output = workdir / FINAL_VIDEO_FILE
    report = assemble_chrome_guided_segments(
        storyboard,
        workdir,
        segment_paths,
        output,
        audio=audio,
        max_duration_sec=float(plan["max_duration_sec"]),
    )
    if (
        report.get("status") != "PASS"
        or report.get("render_strategy") != "hyperframes_segmented_matrix"
        or int(report.get("segment_count") or 0) != len(indices)
        or report.get("temporary_frame_workspaces_removed") is not True
        or report.get("provider_calls") != 0
        or report.get("youtube_called") is not False
    ):
        raise RuntimeError("segmented canary assembly returned an unsafe report")
    final_result = {
        **preparation,
        "status": "PASS",
        "video": FINAL_VIDEO_FILE,
        "video_sha256": _sha256(output),
        "video_bytes": output.stat().st_size,
        "render_segment_count": len(indices),
        "render_strategy": "hyperframes_segmented_matrix",
        "temporary_frame_workspaces_removed": True,
        "new_image_calls": 0,
        "new_ai33_calls": 0,
        "provider_calls": 0,
        "youtube_called": False,
        "publication_authorized": False,
    }
    _write_object(workdir / "render-report.json", report)
    _write_object(workdir / "segmented-canary-result.json", final_result)
    return final_result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workdir", required=True)
    parser.add_argument("--source-root")
    parser.add_argument("--audio-root")
    parser.add_argument("--source-run-id", default=SOURCE_RUN_ID)
    parser.add_argument("--source-artifact", default=SOURCE_ARTIFACT)
    actions = parser.add_mutually_exclusive_group(required=True)
    actions.add_argument("--prepare", action="store_true")
    actions.add_argument("--render-segment", type=int)
    actions.add_argument("--assemble", action="store_true")
    parser.add_argument("--confirm-no-spend-existing-media", action="store_true")
    args = parser.parse_args()

    workdir = Path(args.workdir).resolve()
    if args.prepare:
        if not args.confirm_no_spend_existing_media:
            raise SystemExit("preparation requires --confirm-no-spend-existing-media")
        if not args.source_root or not args.audio_root:
            raise SystemExit("preparation requires --source-root and --audio-root")
        result = prepare(
            Path(args.source_root),
            Path(args.audio_root),
            workdir,
            source_run_id=args.source_run_id,
            source_artifact=args.source_artifact,
        )
    elif args.render_segment is not None:
        if args.source_root or args.audio_root or args.confirm_no_spend_existing_media:
            raise SystemExit("render jobs accept only the frozen prepared artifact")
        result = render_segment(workdir, args.render_segment)
    else:
        if args.source_root or args.audio_root or args.confirm_no_spend_existing_media:
            raise SystemExit("assembly accepts only the frozen prepared artifact")
        result = assemble(workdir)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
