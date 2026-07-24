#!/usr/bin/env python3
"""Validate the first fixed-release image through one bounded VectorEngine call."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path
from typing import Callable

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from acc1_episode_factory import CallBudget
from acc1_episode_images import (
    PROVIDER_LANDSCAPE_SIZE,
    SIZE,
    image_plan,
    normalize_editorial_provider_image,
)
from acc1_visual_contract import EDITORIAL_MOTION_MODE, FORMAT_VISUAL_SYSTEM_V3_STYLE_PROFILE
from scripts.run_acc1_fixed_first_release import SCENE_IMAGE_COUNT, build_script
from vectorengine_client import DEFAULT_IMAGE_MODEL, call_image_generation


Generator = Callable[..., Path]


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def build_preflight(output_dir: Path) -> tuple[dict, dict]:
    script = build_script()
    plan = image_plan(
        script,
        visual_mode=EDITORIAL_MOTION_MODE,
        style_profile=FORMAT_VISUAL_SYSTEM_V3_STYLE_PROFILE,
    )
    if len(plan) != SCENE_IMAGE_COUNT:
        raise RuntimeError(
            f"size canary requires the exact {SCENE_IMAGE_COUNT}-image production plan",
        )
    first = plan[0]
    report = {
        "status": "IMAGE_SIZE_CANARY_PREFLIGHT_PASS",
        "selected_plan_index": 1,
        "selected_source_id": first["source_id"],
        "selected_layer_role": first.get("layer_role"),
        "selected_panel_grammar": first.get("panel_grammar"),
        "prompt_sha256": hashlib.sha256(first["prompt"].encode("utf-8")).hexdigest(),
        "model": DEFAULT_IMAGE_MODEL,
        "provider_requested_size": PROVIDER_LANDSCAPE_SIZE,
        "required_output_size": SIZE,
        "approved_image_call_cap": 1,
        "automatic_retries": 0,
        "new_image_calls": 0,
        "new_ai33_calls": 0,
        "youtube_called": False,
        "publication_authorized": False,
    }
    _write_json(output_dir / "image-size-canary-preflight.json", report)
    return report, first


def run_canary(
    output_dir: Path,
    *,
    generator: Generator = call_image_generation,
) -> dict:
    preflight, first = build_preflight(output_dir)
    attempts = CallBudget(
        generator,
        cap=1,
        label="image",
        journal_path=output_dir / "provider-attempts" / "image.json",
    )
    image_path = output_dir / "scene-images" / "first-production-page.png"
    image_path.parent.mkdir(parents=True, exist_ok=True)
    attempts(
        prompt=first["prompt"],
        output_path=image_path,
        model=DEFAULT_IMAGE_MODEL,
        size=PROVIDER_LANDSCAPE_SIZE,
    )
    with Image.open(image_path) as image:
        provider_dimensions = list(image.size)
        provider_format = image.format
        image.load()
    provider_sha256 = _sha256_file(image_path)
    try:
        normalization = normalize_editorial_provider_image(
            image_path,
            requested_size=PROVIDER_LANDSCAPE_SIZE,
            output_size=SIZE,
        )
    except Exception as exc:
        blocked = {
            **preflight,
            "status": "BLOCKED_PROVIDER_DIMENSIONS",
            "new_image_calls": len(attempts.calls),
            "provider_original_dimensions": provider_dimensions,
            "provider_original_format": provider_format,
            "provider_original_sha256": provider_sha256,
            "error_type": type(exc).__name__,
            "error": str(exc),
        }
        _write_json(output_dir / "image-size-canary-result.json", blocked)
        raise
    with Image.open(image_path) as image:
        final_dimensions = list(image.size)
        final_format = image.format
        image.load()
    result = {
        **preflight,
        "status": "IMAGE_SIZE_CANARY_PASS",
        "new_image_calls": len(attempts.calls),
        "provider_original_dimensions": provider_dimensions,
        "provider_original_format": provider_format,
        "provider_original_sha256": provider_sha256,
        "normalization": normalization,
        "final_dimensions": final_dimensions,
        "final_format": final_format,
        "final_sha256": _sha256_file(image_path),
        "image": image_path.relative_to(output_dir).as_posix(),
    }
    if (
        result["new_image_calls"] != 1
        or result["final_dimensions"] != [1536, 864]
        or result["new_ai33_calls"] != 0
        or result["youtube_called"] is not False
    ):
        raise RuntimeError("one-image size canary returned an unsafe result")
    _write_json(output_dir / "image-size-canary-result.json", result)
    return result


def recover_canary(output_dir: Path, *, source_run_id: str) -> dict:
    preflight_path = output_dir / "image-size-canary-preflight.json"
    prior_result_path = output_dir / "image-size-canary-result.json"
    journal_path = output_dir / "provider-attempts" / "image.json"
    image_path = output_dir / "scene-images" / "first-production-page.png"
    preflight = json.loads(preflight_path.read_text(encoding="utf-8"))
    prior = json.loads(prior_result_path.read_text(encoding="utf-8"))
    journal = json.loads(journal_path.read_text(encoding="utf-8"))
    attempts = journal.get("attempts")
    if (
        preflight.get("status") != "IMAGE_SIZE_CANARY_PREFLIGHT_PASS"
        or prior.get("status") != "BLOCKED_PROVIDER_DIMENSIONS"
        or prior.get("new_image_calls") != 1
        or prior.get("new_ai33_calls") != 0
        or prior.get("youtube_called") is not False
        or journal.get("provider") != "image"
        or journal.get("cap") != 1
        or not isinstance(attempts, list)
        or len(attempts) != 1
        or attempts[0].get("status") != "COMPLETE"
        or not image_path.is_file()
        or attempts[0].get("output_sha256") != _sha256_file(image_path)
        or prior.get("provider_original_sha256") != _sha256_file(image_path)
    ):
        raise RuntimeError("existing size-canary artifact is incomplete or unsafe")
    archived_result = output_dir / f"image-size-canary-source-result-{source_run_id}.json"
    if archived_result.exists():
        raise RuntimeError("source size-canary result was already archived")
    shutil.copy2(prior_result_path, archived_result)
    normalization = normalize_editorial_provider_image(
        image_path,
        requested_size=PROVIDER_LANDSCAPE_SIZE,
        output_size=SIZE,
    )
    with Image.open(image_path) as image:
        final_dimensions = list(image.size)
        final_format = image.format
        image.load()
    result = {
        **preflight,
        "status": "IMAGE_SIZE_CANARY_RECOVERED",
        "source_run_id": source_run_id,
        "source_image_calls": 1,
        "new_image_calls": 0,
        "new_ai33_calls": 0,
        "youtube_called": False,
        "provider_original_dimensions": prior["provider_original_dimensions"],
        "provider_original_format": prior["provider_original_format"],
        "provider_original_sha256": prior["provider_original_sha256"],
        "normalization": normalization,
        "final_dimensions": final_dimensions,
        "final_format": final_format,
        "final_sha256": _sha256_file(image_path),
        "image": image_path.relative_to(output_dir).as_posix(),
        "source_result": archived_result.name,
    }
    if (
        result["final_dimensions"] != [1536, 864]
        or result["new_image_calls"] != 0
        or result["new_ai33_calls"] != 0
        or result["youtube_called"] is not False
    ):
        raise RuntimeError("no-spend size-canary recovery returned an unsafe result")
    _write_json(prior_result_path, result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--preflight-only", action="store_true")
    parser.add_argument("--confirm-exactly-one-image-call", action="store_true")
    parser.add_argument("--recover-existing", action="store_true")
    parser.add_argument("--source-run-id")
    args = parser.parse_args()
    modes = sum((
        bool(args.preflight_only),
        bool(args.confirm_exactly_one_image_call),
        bool(args.recover_existing),
    ))
    if modes != 1:
        raise SystemExit(
            "choose preflight-only, exactly one image call or recover-existing",
        )
    if args.recover_existing != bool(args.source_run_id):
        raise SystemExit("recover-existing requires one source-run-id")
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    if args.preflight_only:
        result, _ = build_preflight(output_dir)
    elif args.recover_existing:
        result = recover_canary(output_dir, source_run_id=str(args.source_run_id))
    else:
        result = run_canary(output_dir)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
