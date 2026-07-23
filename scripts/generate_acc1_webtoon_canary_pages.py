#!/usr/bin/env python3
"""Generate exactly four light editorial comic pages for the acc1 canary."""

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
    FORMAT_VISUAL_SYSTEM_V3_STYLE_PROFILE,
    select_format_visual_system_v3_panel_grammar,
)
from acc1_editorial_motion import bind_payload, canonical_hash
from scripts.render_acc1_webtoon_canary import build_canary_storyboard, resolve_storyboard
from vectorengine_client import DEFAULT_IMAGE_MODEL, call_image_generation


STYLE = """
Create one complete horizontal 16:9 premium adult hand-drawn graphic-novel page
for a Russian long-form story video. Use believable adult anatomy, mature expressive
faces, elegant variable ink contours, restrained cel shading, subtle matte gouache,
tactile paper grain, cream gutters and unequal panels with one dominant emotional
image. This is fully illustrated art: never photography, photomontage, photorealistic
reconstruction, glossy romance manhwa, superhero pop art or childish clip-art, and
never an orange-dominated universal palette. Use BUNDLE grammar: this story is a
separate mini-comic with its own cast, setting, supporting accent colour and panel
rhythm. No words, letters,
numbers, captions, speech bubbles, UI, logos, signatures or watermarks. Keep the
bottom 14 percent visually quiet because HTML subtitles are added separately.
""".strip()

IDENTITY = """
Recurring identities: narrator is a 27-year-old Russian woman with dark wavy
shoulder-length hair, practical contemporary clothes and a charcoal skirt or
trousers. Sister is a 29-year-old Russian woman with lighter straight hair,
visibly pregnant. Husband is a 28-year-old Russian man with short dark hair and
restrained neutral clothes. Preserve their faces, ages, hair, body shapes and
wardrobe consistently on every page.
""".strip()


def page_prompt(scene: dict, index: int, scene_count: int = 4) -> str:
    moment = " ".join(str(scene.get("narration_text") or "").split())
    if not moment:
        raise RuntimeError(f"scene {index} has no narration_text")
    panel_grammar = select_format_visual_system_v3_panel_grammar(
        "BUNDLE", index, scene_count,
    )
    return (
        f"{STYLE}\n\n{IDENTITY}\n\n"
        f"Page {index} meaning-led panel grammar {panel_grammar['id']}: "
        f"{panel_grammar['direction']} "
        f"Depict only this narrated moment: {moment} "
        "Do not invent another event, person, document, threat or outcome."
    )


def replace_scene_assets(storyboard: dict, pages: list[Path], root: Path) -> dict:
    slides = list(storyboard.get("slides") or [])
    if len(slides) != len(pages):
        raise RuntimeError("page count must match canary scene count")
    for index, (scene, page) in enumerate(zip(slides, pages), start=1):
        panel_grammar = select_format_visual_system_v3_panel_grammar(
            "BUNDLE", index, len(slides),
        )
        digest = hashlib.sha256(page.read_bytes()).hexdigest()
        relative = page.relative_to(root).as_posix()
        base = {
            "media_id": f"canary-light-comic-{index:02d}",
            "kind": "generated_image",
            "provider": "vectorengine",
            "model": DEFAULT_IMAGE_MODEL,
            "local_path": relative,
            "sha256": digest,
            "download_status": "verified",
            "size": "1536x864",
            "caption": "",
            "asset_family_id": f"canary-light-comic-{index:02d}",
            "motion_module": (scene.get("motion") or {}).get("module"),
            "story_family": "relationships",
            "page_layout": "bundle_story_opener" if index == 1 else "bundle_guided_page",
            "panel_grammar": panel_grammar["id"],
            "panel_count": panel_grammar["panel_count"],
            "panel_beat_role": panel_grammar["beat_role"],
            "factual_text_allowed": False,
        }
        scene["assets"] = [
            {**base, "layer_role": "hero_plate"},
            {**base, "layer_role": "detail_plate"},
        ]
        scene["asset_family_id"] = base["asset_family_id"]
        scene["story_family"] = base["story_family"]
        scene["page_layout"] = base["page_layout"]
        scene["panel_grammar"] = base["panel_grammar"]
        scene["panel_count"] = base["panel_count"]
        scene["panel_beat_role"] = base["panel_beat_role"]
        scene["style_profile"] = FORMAT_VISUAL_SYSTEM_V3_STYLE_PROFILE
        pack_payload = {
            "asset_family_id": scene["asset_family_id"],
            "motion_module": base["motion_module"],
            "story_family": base["story_family"],
            "page_layout": base["page_layout"],
            "panel_grammar": base["panel_grammar"],
            "panel_count": base["panel_count"],
            "panel_beat_role": base["panel_beat_role"],
            "assets": scene["assets"],
        }
        scene["asset_pack_sha256"] = canonical_hash(pack_payload)
    storyboard["style_profile"] = FORMAT_VISUAL_SYSTEM_V3_STYLE_PROFILE
    if isinstance(storyboard.get("motion_plan"), dict):
        motion_plan = dict(storyboard["motion_plan"])
        motion_plan.pop("motion_plan_sha256", None)
        motion_plan["style_profile"] = FORMAT_VISUAL_SYSTEM_V3_STYLE_PROFILE
        motion_plan["scenes"] = slides
        storyboard["motion_plan"] = bind_payload(motion_plan, "motion_plan_sha256")
        storyboard["motion_plan_sha256"] = storyboard["motion_plan"]["motion_plan_sha256"]
    return storyboard


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-root", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--confirm-exactly-four-image-calls", action="store_true")
    args = parser.parse_args()
    if not args.confirm_exactly_four_image_calls:
        raise RuntimeError("refusing paid generation without exact four-call confirmation")

    source = json.loads(resolve_storyboard(Path(args.artifact_root)).read_text(encoding="utf-8"))
    storyboard, source_start, source_end = build_canary_storyboard(source, scene_count=4)
    storyboard["canary_source_start_sec"] = source_start
    storyboard["canary_source_end_sec"] = source_end
    output = Path(args.output_dir).resolve()
    pages_dir = output / "scene-images"
    pages_dir.mkdir(parents=True, exist_ok=True)
    journal = {"provider": "vectorengine", "model": DEFAULT_IMAGE_MODEL,
               "approved_call_cap": 4, "automatic_retries": 0, "attempts": []}
    journal_path = output / "paid-image-attempts.json"
    pages: list[Path] = []
    for index, scene in enumerate(storyboard["slides"], start=1):
        prompt = page_prompt(scene, index, len(storyboard["slides"]))
        page = pages_dir / f"light-comic-page-{index:02d}.png"
        record = {"call": index, "output": page.relative_to(output).as_posix(),
                  "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(), "status": "started"}
        journal["attempts"].append(record)
        journal_path.write_text(json.dumps(journal, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        try:
            call_image_generation(prompt=prompt, output_path=page, model=DEFAULT_IMAGE_MODEL,
                                  size="1536x864", retries=0)
        except Exception as exc:
            record.update({"status": "failed", "error_type": type(exc).__name__, "error": str(exc)[:500]})
            journal_path.write_text(json.dumps(journal, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            raise
        record.update({"status": "complete", "sha256": hashlib.sha256(page.read_bytes()).hexdigest()})
        journal_path.write_text(json.dumps(journal, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        pages.append(page)
    replace_scene_assets(storyboard, pages, output)
    (output / "storyboard-generated.json").write_text(
        json.dumps(storyboard, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
