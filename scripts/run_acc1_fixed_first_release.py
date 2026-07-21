#!/usr/bin/env python3
"""Build the locked acc1 first release using only Image and AI33 providers."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from acc1_episode_contract import truth_disclosure_ru
from PIL import Image, ImageOps

from acc1_episode_factory import CallBudget, NARRATOR_VOICE_ID
from acc1_narration_profiles import resolve_narration_profile
from acc1_pronunciation_dictionary import (
    load_acc1_pronunciation_dictionary,
    resolve_acc1_pronunciation_dictionary_id,
)
from acc1_visual_contract import (
    CINEMATIC_INK_WEBTOON_STYLE_PROFILE,
    EDITORIAL_MOTION_MODE,
)
from compilation_narration import build_compilation_segments
from chrome_guided_webtoon_renderer import render_chrome_guided_webtoon
from compilation_storyboard import build_storyboard
from compilation_tts_runner import build_tts_chunks, run_compilation_tts
from translator_tts import post_tts_task
from vectorengine_client import DEFAULT_IMAGE_MODEL, call_image_generation


NARRATION_PATH = ROOT / "specs/acc1-first-release-v1/narration-draft-ru.md"
PLAN_PATH = ROOT / "specs/acc1-first-release-v1/production-plan.json"
PROFILE_ID = "acc1_relationships_family_v1"
IMAGE_CAP = 69
SCENE_IMAGE_COUNT = 68
TTS_CAP = 61
BRAND_STING_ASSET = ROOT / "videos/chonker-talks-intro/renders/chonker-talks-editorial-intro-preview-v2.mp4"
BRAND_CTA_ASSET = ROOT / "videos/chonker-talks-cta/renders/chonker-talks-midroll-cta-v2.webm"
BRAND_OUTRO_ASSET = ROOT / "videos/chonker-talks-outro/renders/chonker-talks-youtube-outro-v1.mp4"

STORY_CONFIG = (
    {
        "post_id": "1uw7804", "subreddit": "relationship_advice",
        "author": "ThrowRAMPerspective",
        "url": "https://reddit.com/r/relationship_advice/comments/1uw7804/",
        "title": "Сестра беременна от моего мужа",
        "identity": "Recurring narrator: 27-year-old woman with dark wavy shoulder-length hair and practical contemporary clothes. Recurring sister: 29-year-old woman with lighter straight hair, visibly pregnant only when chronology requires it. Recurring husband: 28-year-old man with short dark hair and restrained neutral wardrobe. Keep every face, age, body shape and wardrobe stable inside this story only.",
        "palette": "relationships", "target": 18,
    },
    {
        "post_id": "1v0l1ei", "subreddit": "offmychest",
        "author": "isnt_THIS_crazy",
        "url": "https://reddit.com/r/offmychest/comments/1v0l1ei/",
        "title": "Парень моей подруги считает, что я заслуживаю смерти",
        "identity": "Recurring narrator: calm 39-year-old gay man with close-cropped dark hair and understated clothes. Recurring friend: expressive 38-year-old woman with an auburn bob. Recurring boyfriend: neat 29-year-old man with a conservative appearance, never a villain caricature. Keep every face, age, body shape and wardrobe stable inside this story only.",
        "palette": "relationships", "target": 18,
    },
    {
        "post_id": "1uy2j23", "subreddit": "relationship_advice",
        "author": "ThrowRATempturesangs",
        "url": "https://reddit.com/r/relationship_advice/comments/1uy2j23/",
        "title": "Родители требуют, чтобы я снова растил их детей",
        "identity": "Recurring narrator: lean 20-year-old man with tired eyes and simple workwear. Recurring parents: both 38, in conservative modest clothing. Younger siblings appear in varied small groups with distinct faces rather than clones. Keep every recurring face, age, body shape and wardrobe stable inside this story only.",
        "palette": "relationships", "target": 16,
    },
    {
        "post_id": "1uviexk", "subreddit": "AmItheAsshole",
        "author": "Opposite-Meringue610",
        "url": "https://reddit.com/r/AmItheAsshole/comments/1uviexk/",
        "title": "После семнадцати лет молчания — двенадцать звонков в день",
        "identity": "Recurring narrator: composed middle-aged woman with a silver-brown bob. Recurring husband: older man with a grey beard. Recurring adult daughter: dark-blonde hair and controlled formal wardrobe. Keep every face, age, body shape and wardrobe stable inside this story only.",
        "palette": "relationships", "target": 16,
    },
)

LAYOUTS = (
    "hero_left_details_right", "phone_portal_insets", "message_cascade",
    "vertical_routine_triptych", "evidence_slits", "rumor_table_wide",
    "corridor_false_claim", "empty_desk_release", "hero_left_details_right",
)


def canonical_hash(value: object) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def _section(text: str, heading: str, next_heading: str | None) -> str:
    start = text.index(heading) + len(heading)
    end = text.index(next_heading, start) if next_heading else len(text)
    return text[start:end].strip()


def build_script() -> dict:
    markdown = NARRATION_PATH.read_text(encoding="utf-8")
    plan = json.loads(PLAN_PATH.read_text(encoding="utf-8"))
    expected = {item["post_id"]: item for item in plan["stories"]}
    headings = [f"## Story {index} —" for index in range(1, 5)]
    stories = []
    for index, config in enumerate(STORY_CONFIG):
        heading_start = markdown.index(headings[index])
        body_start = markdown.index("\n", heading_start) + 1
        next_marker = headings[index + 1] if index < 3 else "## Editorial completion status"
        body_end = markdown.index(next_marker, body_start)
        narration = markdown[body_start:body_end].strip()
        target = expected[config["post_id"]]
        if target["image_target"] != config["target"]:
            raise RuntimeError(f"image target drift for {config['post_id']}")
        pack_count = config["target"] // 2
        stories.append({
            "title_ru": config["title"],
            "narration_ru": narration,
            "narration_role": "narrator",
            "transition_after_ru": (
                "Следующая история — о семье, которая тоже требует близости, не признавая причинённого вреда."
                if index < 3 else ""
            ),
            "image_target": config["target"],
            "visual_identity_contract": config["identity"],
            "editorial_motion_families": [config["palette"]] * pack_count,
            "editorial_page_layouts": list(LAYOUTS[:pack_count]),
            "source_snapshot": {
                "source_id": config["post_id"], "post_id": config["post_id"],
                "subreddit": config["subreddit"], "author": config["author"],
                "url": config["url"], "title": config["title"],
                "truth_mode": "unverified_personal_account",
                "body_sha256": target["source_body_sha256"],
            },
        })
    disclosure = truth_disclosure_ru({"unverified_personal_account"}, source_count=4)
    script = {
        "version": 1,
        "episode_format": "BUNDLE",
        "title_ru": "Четыре семьи, которые требуют слишком многого",
        "intro_ru": (
            "Моя сестра забеременела от моего мужа, но семья требует, чтобы я её простила. "
            + disclosure
        ),
        "truth_disclosure_ru": disclosure,
        # The approved three-second transparent CTA is visual-only; keeping it
        # out of narration preserves the exact 61-task AI33 authorization.
        "mid_story_cta_ru": "",
        "outro_ru": "Где проходит граница между семейной поддержкой и правом отказаться? Обсудим в комментариях.",
        "stories": stories,
        "visual_mode": EDITORIAL_MOTION_MODE,
        "style_profile": CINEMATIC_INK_WEBTOON_STYLE_PROFILE,
        "pillar": "relationships_family",
        "narration_profile_id": PROFILE_ID,
        "publication_authorized": False,
    }
    plan_binding = {
        "source_manifest_sha256": plan["source_manifest_sha256"],
        "narration_sha256": sha256_file(NARRATION_PATH),
        "production_plan_sha256": sha256_file(PLAN_PATH),
    }
    script["daily_plan_sha256"] = canonical_hash(plan_binding)
    script["episode_plan_sha256"] = canonical_hash({**plan_binding, "script": script})
    return script


def fixed_image_plan(script: dict) -> list[dict]:
    style = (
        "premium adult cinematic ink webtoon, believable contemporary adults, expressive restrained acting, "
        "confident ink contours, matte gouache color, dry-brush shadows and tactile uncoated paper, sophisticated "
        "editorial graphic-novel staging, never childish and never superhero pop-art, one to three unequal panels "
        "inside a continuous full-screen 16:9 page, no speech balloons, no generated text, no letters, no numbers, "
        "no UI, no logo, no watermark, no gore"
    )
    modules = (
        "living_photo_depth", "digital_memory_stack", "evidence_transform",
        "graphic_timeline", "nested_collage_zoom", "dark_semantic_reveal",
    )
    plan: list[dict] = []
    for story_index, story in enumerate(script["stories"]):
        sentences = [
            item.strip() for item in re.split(r"(?<=[.!?…])\s+|\n+", story["narration_ru"])
            if item.strip()
        ]
        pack_count = story["image_target"] // 2
        for pack_index in range(pack_count):
            anchor = min(len(sentences) - 1, round((pack_index + 0.5) * len(sentences) / pack_count - 0.5))
            excerpt = sentences[anchor]
            if len(excerpt) < 100 and anchor + 1 < len(sentences):
                excerpt = f"{excerpt} {sentences[anchor + 1]}"
            family_id = f"story-{story_index + 1:02d}-pack-{pack_index + 1:03d}"
            module = modules[pack_index % len(modules)]
            layout = story["editorial_page_layouts"][pack_index]
            for role in ("hero_plate", "detail_plate"):
                role_direction = (
                    "wide establishing page with the primary emotional event and clear spatial depth"
                    if role == "hero_plate"
                    else "closer materially different detail page of the same supported moment"
                )
                prompt = (
                    f"{style}. {role_direction}. Page layout: {layout}. "
                    f"Recurring identity contract: {story['visual_identity_contract']} "
                    f"Depict only this source-supported moment: {excerpt[:700]}. "
                    "Do not invent a person, clue, document, outcome, danger or emotion."
                )
                plan.append({
                    "story_index": story_index,
                    "source_id": story["source_snapshot"]["post_id"],
                    "scene_index": pack_index + 1,
                    "scene_count": pack_count,
                    "asset_family_id": family_id,
                    "layer_role": role,
                    "motion_module": module,
                    "story_family": "relationships",
                    "page_layout": layout,
                    "source_excerpt": excerpt[:700],
                    "source_excerpt_sha256": hashlib.sha256(excerpt[:700].encode()).hexdigest(),
                    "prompt": prompt,
                })
    return plan


def generate_fixed_images(script: dict, output_dir: Path, images: CallBudget) -> tuple[dict, list[dict]]:
    plan = fixed_image_plan(script)
    output_dir.mkdir(parents=True, exist_ok=True)
    assets: list[dict] = []
    for index, item in enumerate(plan, start=1):
        output = output_dir / f"scene-{index:03d}-{item['layer_role']}.png"
        result = Path(images(
            prompt=item["prompt"], output_path=output,
            model=DEFAULT_IMAGE_MODEL, size="1536x864",
        ))
        with Image.open(result) as source:
            source.load()
            if source.size != (1536, 864):
                ratio = source.width / source.height
                if source.width < 1536 or source.height < 864 or abs(ratio - 16 / 9) > 0.03:
                    raise RuntimeError(f"unsafe provider image geometry: {source.size}")
                normalized = ImageOps.fit(source.convert("RGB"), (1536, 864), Image.Resampling.LANCZOS)
                normalized.save(output, format="PNG")
        asset = {
            "media_id": f"fixed-scene-{index:03d}", "kind": "generated_image",
            "local_path": output.relative_to(output_dir.parent).as_posix(),
            "sha256": sha256_file(output), "download_status": "verified",
            "model": DEFAULT_IMAGE_MODEL, "size": "1536x864",
            "prompt": item["prompt"], "caption": "",
            **{key: item[key] for key in (
                "scene_index", "scene_count", "asset_family_id", "layer_role",
                "motion_module", "story_family", "page_layout", "source_excerpt_sha256",
            )},
        }
        script["stories"][item["story_index"]].setdefault("generated_media", []).append(asset)
        assets.append(asset)
    return script, assets


def apply_brand_overlays(base_video: Path, output: Path, storyboard: dict) -> None:
    intro_end = max(float(scene["end_sec"]) for scene in storyboard["slides"] if scene["presentation"] == "intro")
    story_one = [scene for scene in storyboard["slides"] if scene.get("story_index") == 1]
    cta_start = (float(story_one[0]["start_sec"]) + float(story_one[-1]["end_sec"])) / 2 - 1.5
    duration = float(storyboard["timeline_duration_sec"])
    outro_start = max(0.0, duration - 6.0)
    filter_graph = (
        f"[1:v]setpts=PTS-STARTPTS+{intro_end:.3f}/TB[sting];"
        f"[2:v]format=rgba,setpts=PTS-STARTPTS+{cta_start:.3f}/TB[cta];"
        f"[3:v]setpts=PTS-STARTPTS+{outro_start:.3f}/TB[outro];"
        "[0:v][sting]overlay=eof_action=pass:shortest=0[v1];"
        "[v1][cta]overlay=eof_action=pass:shortest=0[v2];"
        "[v2][outro]overlay=eof_action=pass:shortest=0[vout]"
    )
    subprocess.run([
        "ffmpeg", "-y", "-i", str(base_video), "-i", str(BRAND_STING_ASSET),
        "-c:v", "libvpx-vp9", "-i", str(BRAND_CTA_ASSET), "-i", str(BRAND_OUTRO_ASSET),
        "-filter_complex", filter_graph, "-map", "[vout]", "-map", "0:a:0",
        "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
        "-c:a", "copy", "-movflags", "+faststart", str(output),
    ], check=True)


def dry_run(output_dir: Path) -> dict:
    script = build_script()
    dictionary = load_acc1_pronunciation_dictionary()
    plan = fixed_image_plan(script)
    chunks = build_tts_chunks(
        script, voice_id=NARRATOR_VOICE_ID, narration_profile_id=PROFILE_ID,
    )
    if len(plan) != SCENE_IMAGE_COUNT:
        raise RuntimeError(f"fixed release must plan {SCENE_IMAGE_COUNT} scene images, got {len(plan)}")
    if len(chunks) > TTS_CAP:
        raise RuntimeError(f"fixed release needs {len(chunks)} AI33 submissions, cap is {TTS_CAP}")
    result = {
        "status": "FIXED_INPUT_PREFLIGHT_PASS",
        "publication_authorized": False,
        "provider_allowlist": ["image", "ai33"],
        "forbidden_providers": ["reddit", "gemini", "openai", "youtube"],
        "scene_image_calls": len(plan), "thumbnail_calls": 1,
        "image_call_cap": IMAGE_CAP, "automatic_image_retries": 0,
        "ai33_task_submissions": len(chunks), "ai33_task_cap": TTS_CAP,
        "pronunciation_dictionary_sha256": dictionary["sha256"],
        "script_sha256": canonical_hash(script),
    }
    write_json(output_dir / "episode-script.json", script)
    write_json(output_dir / "fixed-input-preflight.json", result)
    write_json(output_dir / "image-plan.json", {"assets": plan})
    return result


def produce(output_dir: Path) -> dict:
    preflight = dry_run(output_dir)
    script = json.loads((output_dir / "episode-script.json").read_text(encoding="utf-8"))
    provider_dir = output_dir / "provider-attempts"
    images = CallBudget(
        call_image_generation, cap=IMAGE_CAP, label="image",
        journal_path=provider_dir / "image.json",
    )
    script, assets = generate_fixed_images(script, output_dir / "scene-images", images)
    thumbnail = output_dir / "youtube-thumbnail.png"
    images(
        prompt=(
            "premium adult cinematic ink webtoon, tense modern family group divided by torn paper, "
            "one woman isolated in the foreground, burgundy, indigo, amber and ivory, expressive ink and "
            "matte gouache, YouTube 16:9 thumbnail, strong central safe area. "
            "Bake exactly this large, legible Russian headline into the artwork: «СЕМЬЯ ТРЕБУЕТ ПРОСТИТЬ». "
            "Correct Cyrillic spelling is mandatory; no other words, letters, subtitles, watermark or logo."
        ),
        output_path=thumbnail, model=DEFAULT_IMAGE_MODEL, size="1536x864",
    )
    write_json(output_dir / "episode-script.json", script)
    write_json(output_dir / "scene-images-manifest.json", {
        "status": "PASS", "assets": assets, "image_calls": len(images.calls),
        "publication_authorized": False,
    })

    profile = resolve_narration_profile(PROFILE_ID, pillar_id="relationships_family")
    dictionary = load_acc1_pronunciation_dictionary()
    dictionary_id = resolve_acc1_pronunciation_dictionary_id(required=True)
    ai33 = CallBudget(
        post_tts_task, cap=TTS_CAP, label="ai33",
        journal_path=provider_dir / "ai33.json",
    )
    tts_state = run_compilation_tts(
        script, output_dir=output_dir / "tts", artifact_root=output_dir,
        api_key=str(os.environ.get("AI33_API_KEY") or os.environ.get("A133_API_KEY") or ""),
        voice_id=NARRATOR_VOICE_ID, narration_profile_id=PROFILE_ID,
        speed=profile["speed"], voice_settings_json=profile["voice_settings_json"],
        pronunciation_dictionary_id=dictionary_id,
        pronunciation_dictionary_sha256=dictionary["sha256"],
        post_task=ai33, overall_timeout_seconds=14_400,
    )
    audio = output_dir / str(tts_state["final_audio_path"])
    storyboard = build_storyboard(
        script, output_dir, tts_state=tts_state, visual_mode=EDITORIAL_MOTION_MODE,
    )
    write_json(output_dir / "storyboard.json", storyboard)
    base_video = output_dir / "final-output-base.mp4"
    render_report = render_chrome_guided_webtoon(
        storyboard, output_dir, base_video, audio=audio,
    )
    video = output_dir / "final-output.mp4"
    apply_brand_overlays(base_video, video, storyboard)
    render_report["base_output_sha256"] = sha256_file(base_video)
    render_report["output_sha256"] = sha256_file(video)
    render_report["brand_overlays"] = ["intro", "mid_story_cta", "outro"]
    write_json(output_dir / "render-report.json", render_report)
    result = {
        **preflight,
        "status": "READY_FOR_HUMAN_REVIEW",
        "video": video.name, "video_sha256": sha256_file(video),
        "thumbnail": thumbnail.name, "thumbnail_sha256": sha256_file(thumbnail),
        "image_calls": len(images.calls), "ai33_task_submissions": len(ai33.calls),
        "publication_authorized": False, "youtube_called": False,
    }
    write_json(output_dir / "fixed-release-result.json", result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--produce", action="store_true")
    parser.add_argument("--confirm-image-ai33-spend", action="store_true")
    args = parser.parse_args()
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    if args.produce:
        if not args.confirm_image_ai33_spend:
            raise SystemExit("refusing provider calls without --confirm-image-ai33-spend")
        result = produce(output_dir)
    else:
        result = dry_run(output_dir)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
