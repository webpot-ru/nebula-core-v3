#!/usr/bin/env python3
"""Fail-closed validation for the approved acc1 webtoon production style."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "specs/acc1-video-style-v2.json"


class StyleContractError(RuntimeError):
    pass


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_contract(*, require_production_ready: bool = False) -> dict:
    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    if contract.get("style_id") != "chonker_cinematic_webtoon_v2":
        raise StyleContractError("unexpected acc1 style_id")
    subtitles = contract.get("subtitles", {})
    if subtitles.get("mode") != "burned_in_fixed_bottom_band":
        raise StyleContractError("fixed bottom subtitle band is required")
    if subtitles.get("line_count") != 1:
        raise StyleContractError("acc1 subtitles must use exactly one line")
    if subtitles.get("horizontal_alignment") != "center" or subtitles.get("vertical_alignment") != "center":
        raise StyleContractError("subtitle text must be centered in both axes")
    if subtitles.get("band", {}).get("height") != 130:
        raise StyleContractError("subtitle band height drift")
    expected_brand_caption_visibility = {
        "intro": "visible",
        "subscribe_cta": "visible",
        "outro": "visible",
    }
    if subtitles.get("visibility_during_brand_inserts") != expected_brand_caption_visibility:
        raise StyleContractError(
            "all brand inserts must preserve captions while narration continues",
        )

    checked_assets = {}
    for name, item in contract.get("brand_inserts", {}).items():
        path = ROOT / item["path"]
        if not path.is_file():
            raise StyleContractError(f"missing required brand insert: {name}: {path}")
        actual = sha256_file(path)
        if actual != item["sha256"]:
            raise StyleContractError(f"brand insert checksum drift: {name}")
        checked_assets[name] = actual

    renderer = contract.get("renderer", {})
    entrypoint = ROOT / renderer["production_entrypoint"]
    source = entrypoint.read_text(encoding="utf-8")
    forbidden_hits = [token for token in renderer.get("forbidden_imports", []) if token in source]
    required_actions = renderer.get("required_segmented_actions", [])
    missing_actions = [token for token in required_actions if token not in source]
    if (
        renderer.get("production_render_strategy") != "hyperframes_segmented_matrix"
        or renderer.get("segment_count_min") != 2
        or renderer.get("segment_count_max") != 16
        or renderer.get("segment_max_duration_sec") != 120
        or renderer.get("matrix_max_parallel") != 8
    ):
        raise StyleContractError("segmented production limits drifted")

    workflow_path = ROOT / renderer["production_workflow"]
    workflow = workflow_path.read_text(encoding="utf-8")
    required_workflow_tokens = [
        "\n  prepare:\n",
        "\n  render:\n",
        "\n  assemble:\n",
        "--prepare-segmented",
        "--render-segment",
        "--assemble-segmented",
        "matrix: ${{ fromJSON(needs.prepare.outputs.matrix) }}",
        "max-parallel: 8",
        "ceiling <= 120.0",
        "merge-multiple: true",
    ]
    missing_workflow_tokens = [
        token for token in required_workflow_tokens if token not in workflow
    ]
    render_job = ""
    assemble_job = ""
    if "\n  render:\n" in workflow and "\n  assemble:\n" in workflow:
        render_job = workflow.split("\n  render:\n", 1)[1].split("\n  assemble:\n", 1)[0]
        assemble_job = workflow.split("\n  assemble:\n", 1)[1]
    no_spend_secret_leaks = [
        token
        for token in ("VECTORENGINE_API_KEY", "AI33_API_KEY", "YOUTUBE_")
        if token in render_job or token in assemble_job
    ]
    approved_preview = contract.get("approval_gate", {}).get("approved_preview_sha256")
    blockers = []
    if forbidden_hits:
        blockers.append("legacy_renderer_still_wired")
    if missing_actions:
        blockers.append("segmented_renderer_actions_missing")
    if missing_workflow_tokens:
        blockers.append("segmented_workflow_topology_missing")
    if no_spend_secret_leaks:
        blockers.append("provider_secret_exposed_after_preparation")
    if "--produce" in workflow:
        blockers.append("monolithic_production_flag_present")
    if not approved_preview:
        blockers.append("approved_preview_sha256_missing")

    report = {
        "status": "PRODUCTION_READY" if not blockers else "BLOCKED",
        "style_id": contract["style_id"],
        "renderer_required": renderer["required_id"],
        "render_strategy": renderer["production_render_strategy"],
        "segment_max_duration_sec": renderer["segment_max_duration_sec"],
        "matrix_max_parallel": renderer["matrix_max_parallel"],
        "subtitle_mode": subtitles["mode"],
        "brand_assets": checked_assets,
        "approved_preview_sha256": approved_preview,
        "blockers": blockers,
        "provider_calls_authorized": False,
        "publication_authorized": False,
    }
    if require_production_ready and blockers:
        raise StyleContractError("production blocked: " + ", ".join(blockers))
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--require-production-ready", action="store_true")
    parser.add_argument("--output")
    args = parser.parse_args()
    report = validate_contract(require_production_ready=args.require_production_ready)
    encoded = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        Path(args.output).write_text(encoded, encoding="utf-8")
    print(encoded, end="")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except StyleContractError as exc:
        raise SystemExit(str(exc)) from exc
