#!/usr/bin/env python3
"""Build the locked acc1 first release using only Image and AI33 providers."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from acc1_episode_contract import truth_disclosure_ru
from acc1_episode_factory import (
    BRAND_CTA_ASSET,
    BRAND_OUTRO_ASSET,
    BRAND_STING_ASSET,
    CallBudget,
    NARRATOR_VOICE_ID,
)
from acc1_episode_images import (
    PROVIDER_LANDSCAPE_SIZE,
    SIZE,
    generate_episode_images,
    image_plan,
    normalize_editorial_provider_image,
)
from acc1_narration_profiles import resolve_narration_profile
from acc1_pronunciation_dictionary import (
    load_acc1_pronunciation_dictionary,
    resolve_acc1_pronunciation_dictionary_id,
)
from acc1_visual_contract import (
    EDITORIAL_MOTION_MODE,
    FORMAT_VISUAL_SYSTEM_V3_STYLE_PROFILE,
    select_format_visual_system_v3_panel_grammar,
)
from chrome_guided_webtoon_renderer import (
    assemble_chrome_guided_segments,
    build_chrome_guided_segment_plan,
    render_chrome_guided_segment,
)
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
MIN_RENDER_SEGMENTS = 2
MAX_RENDER_SEGMENTS = 16
FIXED_COLD_OPEN_RU = (
    "Моя сестра забеременела от моего мужа, но семья требует, чтобы я её простила."
)

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
    "bundle_story_opener", "bundle_guided_page", "bundle_guided_page",
    "bundle_story_opener", "bundle_guided_page", "bundle_guided_page",
    "bundle_story_opener", "bundle_guided_page", "bundle_guided_page",
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


def _fixed_intro_contract(
    *,
    intro_ru: str,
    truth_disclosure_ru: str,
    first_story: dict,
) -> dict:
    snapshot = first_story.get("source_snapshot") or {}
    source_id = str(snapshot.get("source_id") or snapshot.get("post_id") or "").strip()
    source_quote = str(snapshot.get("title") or first_story.get("title_ru") or "").strip()
    expected_intro = f"{FIXED_COLD_OPEN_RU} {truth_disclosure_ru}".strip()
    if intro_ru != expected_intro:
        raise RuntimeError("fixed release intro no longer matches its frozen cold open")
    if source_id != STORY_CONFIG[0]["post_id"] or source_quote != STORY_CONFIG[0]["title"]:
        raise RuntimeError("fixed release cold-open source binding drifted")
    return {
        "version": 1,
        "cold_open": {
            "text": FIXED_COLD_OPEN_RU,
            "source_id": source_id,
            "source_quote": source_quote,
        },
        "parts": [
            {"kind": "cold_open", "text": FIXED_COLD_OPEN_RU},
            {"kind": "truth_disclosure", "text": truth_disclosure_ru},
        ],
        "intro_ru": intro_ru,
        "legacy_fixed_input_recovery": True,
        "verified_supporter_manifest": None,
    }


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
        panel_grammars = [
            select_format_visual_system_v3_panel_grammar("BUNDLE", scene_index, pack_count)["id"]
            for scene_index in range(1, pack_count + 1)
        ]
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
            "editorial_panel_grammars": panel_grammars,
            "source_snapshot": {
                "source_id": config["post_id"], "post_id": config["post_id"],
                "subreddit": config["subreddit"], "author": config["author"],
                "url": config["url"], "title": config["title"],
                "truth_mode": "unverified_personal_account",
                "body_sha256": target["source_body_sha256"],
            },
        })
    disclosure = truth_disclosure_ru({"unverified_personal_account"}, source_count=4)
    intro_ru = f"{FIXED_COLD_OPEN_RU} {disclosure}"
    script = {
        "version": 1,
        "episode_format": "BUNDLE",
        "title_ru": "Четыре семьи, которые требуют слишком многого",
        "intro_ru": intro_ru,
        "intro_contract": _fixed_intro_contract(
            intro_ru=intro_ru,
            truth_disclosure_ru=disclosure,
            first_story=stories[0],
        ),
        "truth_disclosure_ru": disclosure,
        "mid_story_cta_ru": "Если вам близок такой формат, подпишитесь на Chonker Talks.",
        "outro_ru": "Где проходит граница между семейной поддержкой и правом отказаться? Обсудим в комментариях.",
        "stories": stories,
        "visual_mode": EDITORIAL_MOTION_MODE,
        "style_profile": FORMAT_VISUAL_SYSTEM_V3_STYLE_PROFILE,
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


def dry_run(output_dir: Path) -> dict:
    script = build_script()
    dictionary = load_acc1_pronunciation_dictionary()
    plan = image_plan(script, visual_mode=EDITORIAL_MOTION_MODE, style_profile=FORMAT_VISUAL_SYSTEM_V3_STYLE_PROFILE)
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


def _validate_segment_plan(plan: dict) -> list[int]:
    segments = plan.get("segments")
    if not isinstance(segments, list):
        raise RuntimeError("segmented render plan has no segments")
    if plan.get("renderer") != "hyperframes_segmented":
        raise RuntimeError("segmented render plan uses an unexpected renderer")
    indices = [int(item["index"]) for item in segments]
    if not MIN_RENDER_SEGMENTS <= len(indices) <= MAX_RENDER_SEGMENTS:
        raise RuntimeError(
            f"fixed release requires {MIN_RENDER_SEGMENTS}-{MAX_RENDER_SEGMENTS} "
            f"bounded render segments, got {len(indices)}",
        )
    if indices != list(range(1, len(indices) + 1)):
        raise RuntimeError("segmented render indices must be contiguous")
    if int(plan.get("segment_count") or 0) != len(indices):
        raise RuntimeError("segmented render count does not match its segment list")
    ceiling = float(plan.get("max_duration_sec") or 0)
    if ceiling <= 0 or ceiling > 120.0:
        raise RuntimeError("segmented render ceiling must be at most 120 seconds")
    durations = [float(item.get("duration_sec") or 0) for item in segments]
    if any(duration <= 0 for duration in durations):
        raise RuntimeError("segmented render plan contains an empty segment")
    if any(duration > ceiling + 0.001 for duration in durations):
        raise RuntimeError("segmented render plan contains an oversized segment")
    return indices


def _prepared_file(output_dir: Path, raw: object, *, label: str) -> Path:
    root = output_dir.resolve()
    candidate = (root / str(raw or "")).resolve()
    if candidate == root or root not in candidate.parents or not candidate.is_file():
        raise RuntimeError(f"{label} must be a file under the prepared artifact")
    return candidate


def _load_preparation(output_dir: Path) -> tuple[dict, dict, dict]:
    storyboard_path = output_dir / "storyboard.json"
    plan_path = output_dir / "segmented-render-plan.json"
    result = json.loads(
        (output_dir / "segmented-preparation-result.json").read_text(encoding="utf-8"),
    )
    plan = json.loads(
        plan_path.read_text(encoding="utf-8"),
    )
    storyboard = json.loads(
        storyboard_path.read_text(encoding="utf-8"),
    )
    indices = _validate_segment_plan(plan)
    if (
        result.get("status") != "SEGMENTED_RENDER_PREPARED"
        or result.get("image_calls") != IMAGE_CAP
        or result.get("ai33_task_submissions") != TTS_CAP
        or result.get("publication_authorized") is not False
        or result.get("youtube_called") is not False
        or result.get("segment_indices") != indices
        or int(result.get("segment_count") or 0) != len(indices)
        or result.get("storyboard_sha256") != sha256_file(storyboard_path)
        or result.get("segment_plan_sha256") != sha256_file(plan_path)
    ):
        raise RuntimeError("segmented preparation result is incomplete or unsafe")
    audio = _prepared_file(
        output_dir,
        result.get("master_audio"),
        label="master audio",
    )
    thumbnail = _prepared_file(
        output_dir,
        result.get("thumbnail"),
        label="thumbnail",
    )
    if (
        not audio.is_file()
        or sha256_file(audio) != result.get("master_audio_sha256")
        or not thumbnail.is_file()
        or sha256_file(thumbnail) != result.get("thumbnail_sha256")
    ):
        raise RuntimeError("segmented preparation media checksum mismatch")
    return result, plan, storyboard


def prepare_segmented(output_dir: Path) -> dict:
    preflight = dry_run(output_dir)
    script = json.loads((output_dir / "episode-script.json").read_text(encoding="utf-8"))
    provider_dir = output_dir / "provider-attempts"
    images = CallBudget(
        call_image_generation, cap=IMAGE_CAP, label="image",
        journal_path=provider_dir / "image.json",
    )
    script, assets = generate_episode_images(
        script, output_dir / "scene-images", max_images=SCENE_IMAGE_COUNT,
        generator=images, model=DEFAULT_IMAGE_MODEL, artifact_root=output_dir,
        visual_mode=EDITORIAL_MOTION_MODE,
        style_profile=FORMAT_VISUAL_SYSTEM_V3_STYLE_PROFILE,
        size=PROVIDER_LANDSCAPE_SIZE,
        output_size=SIZE,
    )
    thumbnail = output_dir / "youtube-thumbnail.png"
    images(
        prompt=(
            "premium adult hand-drawn graphic-novel illustration, tense contemporary Russian family "
            "divided inside one unequal-panel comic page, one woman isolated in the foreground, ivory, "
            "muted olive, dusty rose, burgundy and deep navy, expressive variable ink contours, restrained "
            "cel shading and tactile matte gouache, never photographic and never orange-dominated, "
            "YouTube 16:9 thumbnail with a strong central safe area. "
            "Bake exactly this large, legible Russian headline into the artwork: «СЕМЬЯ ТРЕБУЕТ ПРОСТИТЬ». "
            "Correct Cyrillic spelling is mandatory; no other words, letters, subtitles, watermark or logo."
        ),
        output_path=thumbnail,
        model=DEFAULT_IMAGE_MODEL,
        size=PROVIDER_LANDSCAPE_SIZE,
    )
    thumbnail_normalization = normalize_editorial_provider_image(
        thumbnail,
        requested_size=PROVIDER_LANDSCAPE_SIZE,
        output_size=SIZE,
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
    for field, source, duration, placement in (
        ("brand_sting", BRAND_STING_ASSET, 1.5, "after_cold_open"),
        ("brand_cta", BRAND_CTA_ASSET, 3.0, "first_story_midpoint"),
        ("brand_outro", BRAND_OUTRO_ASSET, 6.0, "timeline_end"),
    ):
        destination = output_dir / "branding" / source.name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        script[field] = {
            "local_path": destination.relative_to(output_dir).as_posix(),
            "sha256": sha256_file(destination), "duration_sec": duration,
            "placement": placement, "audio_policy": "discard",
        }
    write_json(output_dir / "episode-script.json", script)
    storyboard = build_storyboard(
        script, output_dir, tts_state=tts_state, visual_mode=EDITORIAL_MOTION_MODE,
    )
    write_json(output_dir / "storyboard.json", storyboard)
    segment_plan = build_chrome_guided_segment_plan(storyboard, output_dir)
    segment_indices = _validate_segment_plan(segment_plan)
    write_json(output_dir / "segmented-render-plan.json", segment_plan)
    result = {
        **preflight,
        "status": "SEGMENTED_RENDER_PREPARED",
        "storyboard": "storyboard.json",
        "storyboard_sha256": sha256_file(output_dir / "storyboard.json"),
        "segment_plan_sha256": sha256_file(output_dir / "segmented-render-plan.json"),
        "master_audio": audio.relative_to(output_dir).as_posix(),
        "master_audio_sha256": sha256_file(audio),
        "thumbnail": thumbnail.name, "thumbnail_sha256": sha256_file(thumbnail),
        "thumbnail_normalization": thumbnail_normalization,
        "image_calls": len(images.calls), "ai33_task_submissions": len(ai33.calls),
        "segment_count": len(segment_indices),
        "segment_indices": segment_indices,
        "segment_max_duration_sec": segment_plan["max_duration_sec"],
        "publication_authorized": False, "youtube_called": False,
    }
    write_json(output_dir / "segmented-preparation-result.json", result)
    return result


def render_segment(output_dir: Path, segment_index: int) -> dict:
    preparation, plan, storyboard = _load_preparation(output_dir)
    indices = _validate_segment_plan(plan)
    if segment_index not in indices:
        raise RuntimeError("requested segment is outside the prepared matrix")
    output = output_dir / "render-segments" / f"segment-{segment_index:03d}.mp4"
    report = render_chrome_guided_segment(
        storyboard,
        output_dir,
        segment_index,
        output,
    )
    if (
        report.get("status") != "PASS"
        or report.get("provider_calls") != 0
        or report.get("youtube_called") is not False
        or report.get("temporary_workspace_removed") is not True
        or int(report.get("segment_count") or 0) != preparation["segment_count"]
    ):
        raise RuntimeError("bounded segment render returned an unsafe report")
    write_json(
        output_dir / "render-segments" / f"segment-{segment_index:03d}.json",
        report,
    )
    return report


def assemble_segmented(output_dir: Path) -> dict:
    preparation, plan, storyboard = _load_preparation(output_dir)
    indices = _validate_segment_plan(plan)
    segment_paths = [
        output_dir / "render-segments" / f"segment-{index:03d}.mp4"
        for index in indices
    ]
    video = output_dir / "final-output.mp4"
    audio = output_dir / str(preparation["master_audio"])
    render_report = assemble_chrome_guided_segments(
        storyboard,
        output_dir,
        segment_paths,
        video,
        audio=audio,
    )
    if (
        render_report.get("status") != "PASS"
        or render_report.get("provider_calls") != 0
        or render_report.get("youtube_called") is not False
        or render_report.get("temporary_frame_workspaces_removed") is not True
        or int(render_report.get("segment_count") or 0) != len(indices)
    ):
        raise RuntimeError("segmented assembly returned an unsafe report")
    write_json(output_dir / "render-report.json", render_report)
    result = {
        **preparation,
        "status": "READY_FOR_HUMAN_REVIEW",
        "video": video.name,
        "video_sha256": sha256_file(video),
        "render_segment_count": len(indices),
        "render_strategy": render_report["render_strategy"],
        "temporary_frame_workspaces_removed": True,
    }
    write_json(output_dir / "fixed-release-result.json", result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--prepare-segmented", action="store_true")
    parser.add_argument("--render-segment", type=int)
    parser.add_argument("--assemble-segmented", action="store_true")
    parser.add_argument("--confirm-image-ai33-spend", action="store_true")
    args = parser.parse_args()
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    actions = sum((
        bool(args.prepare_segmented),
        args.render_segment is not None,
        bool(args.assemble_segmented),
    ))
    if actions > 1:
        raise SystemExit("choose exactly one segmented production action")
    if args.prepare_segmented:
        if not args.confirm_image_ai33_spend:
            raise SystemExit("refusing provider calls without --confirm-image-ai33-spend")
        result = prepare_segmented(output_dir)
    elif args.render_segment is not None:
        if args.confirm_image_ai33_spend:
            raise SystemExit("segment rendering cannot accept provider-spend confirmation")
        result = render_segment(output_dir, args.render_segment)
    elif args.assemble_segmented:
        if args.confirm_image_ai33_spend:
            raise SystemExit("segment assembly cannot accept provider-spend confirmation")
        result = assemble_segmented(output_dir)
    else:
        if args.confirm_image_ai33_spend:
            raise SystemExit("dry-run preflight cannot accept provider-spend confirmation")
        result = dry_run(output_dir)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
