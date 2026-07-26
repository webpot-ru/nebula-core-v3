"""Artifact-only HyperFrames renderer for ``editorial_motion_v1``."""

from __future__ import annotations

import hashlib
import html
import json
import re
import shutil
import subprocess
import os
import tempfile
from pathlib import Path
from typing import Any

from PIL import Image, UnidentifiedImageError

from acc1_cinematic_shots import write_caption_srt
from acc1_caption_burn import burn_captions, write_caption_ass
from acc1_editorial_motion import canonical_hash, verify_bound_payload
from acc1_visual_contract import (
    ADULT_ANIMATION_SERIES,
    CINEMATIC_INK_WEBTOON_STYLE_PROFILE,
    CANVAS_FPS,
    CANVAS_HEIGHT,
    CANVAS_WIDTH,
    EDITORIAL_MOTION_ASSETS_PER_PACK,
    EDITORIAL_MOTION_MODE,
    EDITORIAL_MOTION_MODULES,
    EDITORIAL_MOTION_STYLE_PROFILE,
    EDITORIAL_MOTION_STYLE_PROFILES,
    FORMAT_VISUAL_SYSTEM_V3_STYLE_PROFILE,
    INK_GOUACHE_PAGE_LAYOUTS,
    INK_GOUACHE_STORY_FAMILIES,
    INK_GOUACHE_STORY_PAGES_STYLE_PROFILE,
    build_format_visual_system_v3_semantic_camera,
    is_adult_animation_style_profile,
    select_format_visual_system_v3_panel_grammar,
)


HYPERFRAMES_VERSION = "0.7.61"
DEFAULT_SEGMENT_MAX_DURATION_SEC = 120.0
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
ALLOWED_IMAGE_FORMATS = {"JPEG", "PNG", "WEBP"}
PROJECT_ROOT = Path(__file__).resolve().parent
GSAP_RUNTIME = PROJECT_ROOT / "assets/acc1/video/editorial-motion/gsap.min.js"


class EditorialMotionRenderError(RuntimeError):
    """Raised when a motion artifact is not exact, local, or renderable."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _under_root(raw: str | Path, root: Path, *, label: str) -> Path:
    root = root.resolve()
    candidate = Path(raw).expanduser()
    if candidate.is_absolute() or candidate.is_file():
        path = candidate.resolve()
    else:
        path = (root / candidate).resolve()
    if path == root or root not in path.parents or not path.is_file():
        raise EditorialMotionRenderError(f"{label} must be a file under artifact_root")
    return path


def _verified_asset(asset: dict[str, Any], root: Path) -> Path:
    path = _under_root(str(asset.get("local_path") or ""), root, label="editorial asset")
    expected = str(asset.get("sha256") or "").strip().lower()
    if not SHA256_RE.fullmatch(expected) or _sha256(path) != expected:
        raise EditorialMotionRenderError("editorial asset checksum mismatch")
    try:
        with Image.open(path) as image:
            image_format = image.format
            width, height = image.size
            image.verify()
    except (OSError, UnidentifiedImageError) as exc:
        raise EditorialMotionRenderError(f"editorial asset decode failed: {exc}") from exc
    if image_format not in ALLOWED_IMAGE_FORMATS or width < 1280 or height < 720:
        raise EditorialMotionRenderError("editorial asset format or dimensions are unsupported")
    return path


def preflight_editorial_motion_storyboard(
    storyboard: dict[str, Any], artifact_root: Path,
) -> list[dict[str, Any]]:
    if (
        storyboard.get("visual_mode") != EDITORIAL_MOTION_MODE
        or storyboard.get("format") != "compilation_16x9"
        or storyboard.get("resolution") != [CANVAS_WIDTH, CANVAS_HEIGHT]
        or int(storyboard.get("fps") or CANVAS_FPS) != CANVAS_FPS
    ):
        raise EditorialMotionRenderError(
            "editorial storyboard must be editorial_motion_v1 at 1920x1080/30",
        )
    if storyboard.get("background_video") not in (None, ""):
        raise EditorialMotionRenderError("editorial motion rejects background_video")
    if storyboard.get("publication_authorized") is not False:
        raise EditorialMotionRenderError("editorial storyboard cannot authorize publication")
    motion_plan = storyboard.get("motion_plan")
    captions = storyboard.get("caption_track")
    if not verify_bound_payload(motion_plan, "motion_plan_sha256"):
        raise EditorialMotionRenderError("editorial motion plan checksum mismatch")
    if not verify_bound_payload(captions, "caption_track_sha256"):
        raise EditorialMotionRenderError("editorial caption track checksum mismatch")
    if (
        storyboard.get("motion_plan_sha256") != motion_plan["motion_plan_sha256"]
        or storyboard.get("caption_track_sha256") != captions["caption_track_sha256"]
    ):
        raise EditorialMotionRenderError("editorial plan bindings changed")
    profile = str(storyboard.get("style_profile") or "")
    if profile not in EDITORIAL_MOTION_STYLE_PROFILES or motion_plan.get("style_profile") != profile:
        raise EditorialMotionRenderError("editorial style profile drifted")
    scenes = storyboard.get("slides")
    if not isinstance(scenes, list) or not scenes or motion_plan.get("scenes") != scenes:
        raise EditorialMotionRenderError("editorial scenes must exactly match motion plan")

    checked: list[dict[str, Any]] = []
    previous_end = 0.0
    seen: set[str] = set()
    for index, source in enumerate(scenes):
        if not isinstance(source, dict):
            raise EditorialMotionRenderError(f"editorial scene {index} is invalid")
        scene = dict(source)
        scene_id = str(scene.get("scene_id") or "")
        if (
            scene.get("kind") != "editorial_motion_scene"
            or not scene_id
            or scene.get("slide_id") != scene_id
            or scene_id in seen
        ):
            raise EditorialMotionRenderError("editorial scene ids must be equal and unique")
        seen.add(scene_id)
        start = float(scene.get("start_sec") or 0)
        end = float(scene.get("end_sec") or 0)
        duration = float(scene.get("duration_sec") or 0)
        if (
            start < 0
            or end <= start
            or abs((end - start) - duration) > 0.002
            or abs(start - previous_end) > 0.002
        ):
            raise EditorialMotionRenderError(f"{scene_id} has a timing gap or mismatch")
        narration = " ".join(str(scene.get("narration_text") or "").split())
        if hashlib.sha256(narration.encode("utf-8")).hexdigest() != scene.get("text_sha256"):
            raise EditorialMotionRenderError(f"{scene_id} narration checksum mismatch")
        module = str((scene.get("motion") or {}).get("module") or "")
        if module not in EDITORIAL_MOTION_MODULES:
            raise EditorialMotionRenderError(f"{scene_id} uses unsupported motion module")
        if scene.get("style_profile") != profile:
            raise EditorialMotionRenderError(f"{scene_id} style profile drifted")
        if scene.get("factual_text_rendering") != "html_svg_only":
            raise EditorialMotionRenderError(f"{scene_id} does not protect factual text")
        assets = scene.get("assets")
        if not isinstance(assets, list) or len(assets) != EDITORIAL_MOTION_ASSETS_PER_PACK:
            raise EditorialMotionRenderError(f"{scene_id} has an incomplete asset pack")
        roles = [str(asset.get("layer_role") or "") for asset in assets]
        if roles != ["hero_plate", "detail_plate"]:
            raise EditorialMotionRenderError(f"{scene_id} asset roles are invalid")
        story_family = str(scene.get("story_family") or "")
        page_layout = str(scene.get("page_layout") or "")
        panel_grammar = str(scene.get("panel_grammar") or "")
        if profile in {
            INK_GOUACHE_STORY_PAGES_STYLE_PROFILE,
            CINEMATIC_INK_WEBTOON_STYLE_PROFILE,
            FORMAT_VISUAL_SYSTEM_V3_STYLE_PROFILE,
        }:
            if (
                story_family not in INK_GOUACHE_STORY_FAMILIES
                or page_layout not in INK_GOUACHE_PAGE_LAYOUTS
            ):
                raise EditorialMotionRenderError(
                    f"{scene_id} has no supported ink-and-gouache family/layout",
                )
            if profile == FORMAT_VISUAL_SYSTEM_V3_STYLE_PROFILE and panel_grammar:
                expected_grammar = select_format_visual_system_v3_panel_grammar(
                    str(scene.get("format_id") or "BUNDLE"),
                    int(scene.get("scene_number") or 1),
                    int(scene.get("scene_count") or 1),
                )
                # Existing frozen artifacts do not contain panel grammar. New
                # artifacts do, but may use segment-local metadata instead of
                # these optional renderer fields, so validate the ID shape here
                # and let the planner enforce its exact sequence.
                if not panel_grammar.startswith(expected_grammar["format_id"].lower() + "_"):
                    raise EditorialMotionRenderError(f"{scene_id} has an invalid v3 panel grammar")
                try:
                    expected_camera = build_format_visual_system_v3_semantic_camera(
                        str(scene.get("panel_beat_role") or panel_grammar),
                        narration,
                    )
                except ValueError as exc:
                    raise EditorialMotionRenderError(
                        f"{scene_id} has no valid semantic camera contract",
                    ) from exc
                for field in (
                    "camera_contract_version",
                    "panel_regions",
                    "semantic_focus",
                    "camera_path",
                ):
                    if scene.get(field) != expected_camera[field]:
                        raise EditorialMotionRenderError(
                            f"{scene_id} semantic camera {field} drifted",
                        )
        elif is_adult_animation_style_profile(profile):
            series = ADULT_ANIMATION_SERIES[profile]
            if (
                story_family != series["story_family"]
                or page_layout not in series["layouts"]
            ):
                raise EditorialMotionRenderError(
                    f"{scene_id} has no supported adult-animation family/layout",
                )
        verified_assets: list[dict[str, Any]] = []
        for asset in assets:
            verified_assets.append({**asset, "verified_path": str(_verified_asset(asset, artifact_root))})
        pack_payload = {
            "asset_family_id": scene.get("asset_family_id"),
            "motion_module": str(assets[0].get("motion_module") or ""),
            "story_family": str(assets[0].get("story_family") or ""),
            "page_layout": str(assets[0].get("page_layout") or ""),
            "assets": assets,
        }
        asset_panel_grammar = str(assets[0].get("panel_grammar") or "")
        if asset_panel_grammar:
            asset_panel_count = assets[0].get("panel_count")
            asset_panel_beat_role = str(assets[0].get("panel_beat_role") or "")
            if (
                any(str(asset.get("panel_grammar") or "") != asset_panel_grammar for asset in assets)
                or any(asset.get("panel_count") != asset_panel_count for asset in assets)
                or any(str(asset.get("panel_beat_role") or "") != asset_panel_beat_role for asset in assets)
            ):
                raise EditorialMotionRenderError(f"{scene_id} asset panel grammar drift")
            pack_payload.update({
                "panel_grammar": asset_panel_grammar,
                "panel_count": asset_panel_count,
                "panel_beat_role": asset_panel_beat_role,
            })
        if canonical_hash(pack_payload) != scene.get("asset_pack_sha256"):
            raise EditorialMotionRenderError(f"{scene_id} asset pack checksum mismatch")
        scene["verified_assets"] = verified_assets
        checked.append(scene)
        previous_end = end
    final_duration = float(storyboard.get("timeline_duration_sec") or 0)
    if abs(previous_end - final_duration) > 0.002:
        raise EditorialMotionRenderError("editorial scenes do not cover timeline duration")
    return checked


def _safe_id(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "-", value).strip("-") or "scene"


def _scene_markup(
    scene: dict[str, Any], copied_assets: list[str], *, style_profile: str,
) -> str:
    scene_id = _safe_id(str(scene["scene_id"]))
    module = html.escape(str(scene["motion"]["module"]), quote=True)
    story_family = _safe_id(str(scene.get("story_family") or "neutral"))
    raw_page_layout = str(scene.get("page_layout") or "continuous-cutup")
    page_layout = _safe_id(raw_page_layout)
    panel_grammar = _safe_id(str(scene.get("panel_grammar") or "legacy"))
    presentation = _safe_id(str(scene.get("presentation") or "story"))
    title = html.escape(str(scene.get("story_title") or "ИСТОРИЯ"))
    source = html.escape(str(scene.get("source_label") or "РЕДАКЦИОННАЯ ИЛЛЮСТРАЦИЯ"))
    hero, detail = (html.escape(path, quote=True) for path in copied_assets)
    semantic_v3 = style_profile == FORMAT_VISUAL_SYSTEM_V3_STYLE_PROFILE
    if semantic_v3:
        hero_plate_markup = f'<div class="hero-plate" id="hero-{scene_id}"></div>'
        portal_markup = f'<div class="portal-shell" id="portal-{scene_id}"></div>'
        object_markup = f'<div class="object-fragment" id="object-{scene_id}"></div>'
    else:
        hero_plate_markup = (
            f'<img class="hero-plate" id="hero-{scene_id}" src="{hero}" alt="" '
            'data-layout-allow-overflow>'
        )
        portal_markup = (
            f'<div class="portal-shell" id="portal-{scene_id}" data-layout-allow-overflow>'
            f'<div class="portal-glow"></div><img src="{detail}" alt="" '
            'data-layout-allow-overflow><i></i></div>'
        )
        object_markup = (
            f'<div class="object-fragment" id="object-{scene_id}" data-layout-allow-overflow>'
            f'<img src="{detail}" alt="" data-layout-allow-overflow></div>'
        )
    adult_style = is_adult_animation_style_profile(style_profile)
    guided_webtoon_style = style_profile in {
        CINEMATIC_INK_WEBTOON_STYLE_PROFILE,
        FORMAT_VISUAL_SYSTEM_V3_STYLE_PROFILE,
    }
    quote_words = str(scene.get("narration_text") or "").split()[:18]
    # Speech bubbles are reserved for short source-backed direct lines.  The
    # normal narration remains in captions, rather than being printed as a
    # fake character quote inside a comic panel.
    quote = "" if adult_style else html.escape(
        " ".join(quote_words) + ("…" if len(quote_words) == 18 else ""),
    )
    module_labels = {
        "living_photo_depth": "ЖИВАЯ СЦЕНА",
        "evidence_transform": "ВАЖНАЯ ДЕТАЛЬ",
        "digital_memory_stack": "ВНУТРИ СООБЩЕНИЯ",
        "graphic_timeline": "ЛИНИЯ ВРЕМЕНИ",
        "dark_semantic_reveal": "СМЫСЛ МЕНЯЕТСЯ",
        "nested_collage_zoom": "ПОГРУЖЕНИЕ",
    }
    module_label = module_labels[str(scene["motion"]["module"])]
    start = float(scene["start_sec"])
    duration = float(scene["duration_sec"])
    ink_layout = raw_page_layout in INK_GOUACHE_PAGE_LAYOUTS
    illustrated_layout = ink_layout or adult_style
    color_planes = "" if illustrated_layout else f"""
          <div class="color-plane plane-blue" id="blue-{scene_id}" data-layout-allow-overflow></div>
          <div class="color-plane plane-coral" id="coral-{scene_id}" data-layout-allow-overflow></div>
          <div class="color-plane plane-yellow" id="yellow-{scene_id}" data-layout-allow-overflow></div>"""
    dark_reveal = ""
    if not illustrated_layout or raw_page_layout == "corridor_false_claim":
        dark_reveal = f'<div class="dark-reveal" id="dark-{scene_id}"></div>'
    foreground_tear = ""
    if not illustrated_layout or presentation == "intro" or raw_page_layout == "empty_desk_release":
        foreground_tear = (
            f'<div class="foreground-tear" id="tear-{scene_id}" '
            'data-layout-allow-overflow></div>'
        )
    timing_attributes = ""
    if not illustrated_layout:
        timing_attributes = (
            f'data-start="{start:.3f}" data-duration="{duration:.3f}" '
            'data-track-index="1"'
        )
    return f"""
      <section class="clip motion-scene module-{module} family-{story_family} layout-{page_layout} grammar-{panel_grammar} presentation-{presentation}" id="clip-{scene_id}"
        {timing_attributes}>
        <div class="scene-inner" id="inner-{scene_id}" data-layout-allow-overflow>
          {hero_plate_markup}
          <div class="scene-grade" id="grade-{scene_id}"></div>
          {color_planes}
          <div class="hero-cutout" id="cutout-{scene_id}" data-layout-allow-overflow>
            <img src="{hero}" alt="" data-layout-allow-overflow>
          </div>
          {portal_markup}
          {object_markup}
          <svg class="story-line" id="line-{scene_id}" viewBox="0 0 1920 1080" aria-hidden="true">
            <path d="M72 640 C330 525 470 610 690 500 S1060 280 1260 410 S1550 720 1870 470"/>
          </svg>
          <div class="story-copy" id="copy-{scene_id}">
            <span>{module_label}</span><h2>{title}</h2><p>{quote}</p><b>{source}</b>
          </div>
          <div class="timeline-rig" id="timeline-{scene_id}">
            <i></i><b>ДО</b><b>ПОВОРОТ</b><b>ПОСЛЕ</b>
          </div>
          {dark_reveal}
          {foreground_tear}
        </div>
      </section>"""


def _ink_gouache_scene_tweens(scene: dict[str, Any]) -> list[str]:
    """Return the connected, page-specific Ink & Gouache choreography.

    The second-pass art direction treats the generated plates as travelling
    depth planes, not as a stack of matching paper cards.  Adjacent scenes
    overlap for a few frames, copy enters from a layout-specific direction,
    and only two beats retain the hand-drawn connective line.
    """

    sid = _safe_id(str(scene["scene_id"]))
    start = float(scene["start_sec"])
    duration = float(scene["duration_sec"])
    tail = max(start + 0.2, start + duration - 0.26)
    layout = str(scene.get("page_layout") or "hero_left_details_right")
    presentation = str(scene.get("presentation") or "story")
    entrance_clips = {
        "phone_portal_insets": "circle(0% at 67% 48%)",
        "message_cascade": "polygon(100% 0,100% 0,100% 100%,100% 100%)",
        "vertical_routine_triptych": "polygon(0 0,100% 0,100% 0,0 0)",
        "evidence_slits": "inset(0 50% 0 50%)",
        "rumor_table_wide": "inset(100% 0 0 0)",
        "corridor_false_claim": "circle(0% at 49% 51%)",
        "empty_desk_release": "inset(0 0 100% 0)",
    }
    start_clip = entrance_clips.get(layout, "polygon(0 0,0 0,0 100%,0 100%)")
    copy_offsets = {
        "phone_portal_insets": (52, -22),
        "message_cascade": (86, -12),
        "vertical_routine_triptych": (-72, 18),
        "evidence_slits": (58, 34),
        "rumor_table_wide": (0, -54),
        "corridor_false_claim": (76, 8),
        "empty_desk_release": (-64, 42),
    }
    copy_x, copy_y = copy_offsets.get(layout, (-54, -14))
    entrance_start = max(0.0, start - 0.48) if start > 0 else start + 0.12
    lines = [
        f"tl.fromTo('#inner-{sid}', {{opacity:0,clipPath:'{start_clip}'}}, {{opacity:1,clipPath:'inset(0 0 0 0)',duration:0.64,ease:'power3.inOut'}}, {entrance_start:.3f});",
        f"tl.to('#inner-{sid}', {{opacity:0,duration:0.50,ease:'power3.inOut'}}, {tail:.3f});",
        f"tl.set('#inner-{sid}', {{opacity:0}}, {start + duration:.3f});",
        f"tl.fromTo('#inner-{sid}', {{scale:1.0001}}, {{scale:1.006,duration:{duration:.3f},ease:'none'}}, {start:.3f});",
        f"tl.fromTo('#copy-{sid}', {{opacity:0,x:{copy_x},y:{copy_y}}}, {{opacity:1,x:0,y:0,duration:0.78,ease:'expo.out'}}, {start + 0.30:.3f});",
        f"tl.fromTo('#grade-{sid}', {{opacity:.18}}, {{opacity:.74,duration:1.10,ease:'sine.out'}}, {start + 0.04:.3f});",
    ]
    if presentation == "intro" or layout == "empty_desk_release":
        lines.append(
            f"tl.fromTo('#tear-{sid}', {{y:190}}, {{y:0,duration:1.08,ease:'power4.out'}}, {start + 0.18:.3f});",
        )
    if presentation == "intro":
        return lines + [
            f"tl.fromTo('#hero-{sid}', {{scale:1.02,x:0,y:0}}, {{scale:1.18,x:-72,y:-34,duration:{duration:.3f},ease:'sine.inOut'}}, {start:.3f});",
            f"tl.fromTo('#cutout-{sid}', {{opacity:0,scale:.78,x:-160,rotation:-4}}, {{opacity:1,scale:1,x:0,rotation:-1,duration:1.05,ease:'power4.out'}}, {start + .24:.3f});",
            f"tl.fromTo('#portal-{sid}', {{opacity:0,scale:.36,x:210,y:80,rotation:7}}, {{opacity:1,scale:1,x:0,y:0,rotation:0,duration:1.32,ease:'back.out(1.08)'}}, {start + .58:.3f});",
            f"tl.fromTo('#object-{sid}', {{opacity:0,scale:.45,y:120}}, {{opacity:1,scale:1,y:0,duration:.82,ease:'expo.out'}}, {start + 1.06:.3f});",
            f"tl.to('#portal-{sid}', {{scale:3.45,x:-520,y:-190,duration:{duration * .34:.3f},ease:'power3.in'}}, {start + duration * .62:.3f});",
        ]
    if layout == "hero_left_details_right":
        return lines + [
            f"tl.fromTo('#hero-{sid}', {{scale:1.04,x:20,y:8}}, {{scale:1.15,x:-58,y:-24,duration:{duration:.3f},ease:'none'}}, {start:.3f});",
            f"tl.fromTo('#cutout-{sid}', {{opacity:0,scale:.86,x:-170,rotation:-3}}, {{opacity:1,scale:1,x:0,rotation:0,duration:1.02,ease:'power4.out'}}, {start + .24:.3f});",
            f"tl.fromTo('#portal-{sid}', {{opacity:0,scale:.70,x:220,rotation:4}}, {{opacity:1,scale:1,x:0,rotation:0,duration:1.18,ease:'expo.out'}}, {start + .52:.3f});",
            f"tl.fromTo('#object-{sid}', {{opacity:0,scale:.32,y:130}}, {{opacity:1,scale:1,y:0,duration:.76,ease:'back.out(1.2)'}}, {start + .94:.3f});",
            f"tl.to('#cutout-{sid}', {{x:72,y:-22,scale:1.08,duration:{duration * .72:.3f},ease:'sine.inOut'}}, {start + duration * .18:.3f});",
            f"tl.to('#portal-{sid}', {{x:-85,y:30,scale:1.12,duration:{duration * .68:.3f},ease:'sine.inOut',overwrite:'auto'}}, {start + duration * .22:.3f});",
        ]
    if layout == "phone_portal_insets":
        return lines + [
            f"tl.fromTo('#hero-{sid}', {{scale:1.04,x:30}}, {{scale:1.10,x:-30,duration:{duration:.3f},ease:'none'}}, {start:.3f});",
            f"tl.fromTo('#portal-{sid}', {{opacity:0,scale:.62,x:260,rotation:4}}, {{opacity:1,scale:1,x:0,rotation:0,duration:1.16,ease:'expo.out'}}, {start + .28:.3f});",
            f"tl.fromTo('#cutout-{sid}', {{opacity:0,x:-180,y:50,rotation:-5}}, {{opacity:1,x:0,y:0,rotation:-1,duration:.88,ease:'power3.out'}}, {start + .66:.3f});",
            f"tl.fromTo('#object-{sid}', {{opacity:0,scale:.2,rotation:12}}, {{opacity:1,scale:1,rotation:3,duration:.72,ease:'back.out(1.5)'}}, {start + 1.08:.3f});",
            f"tl.fromTo('#line-{sid} path', {{strokeDashoffset:2300}}, {{strokeDashoffset:0,duration:2.4,ease:'sine.inOut'}}, {start + .72:.3f});",
            f"tl.to('#portal-{sid}', {{scale:2.55,x:-410,y:-72,duration:{duration * .42:.3f},ease:'power3.inOut'}}, {start + duration * .50:.3f});",
        ]
    if layout == "message_cascade":
        return lines + [
            f"tl.fromTo('#hero-{sid}', {{scale:1.28,x:-110,y:-42}}, {{scale:1.05,x:26,y:0,duration:{duration:.3f},ease:'power1.out'}}, {start:.3f});",
            f"tl.fromTo('#cutout-{sid}', {{opacity:0,x:-260,y:-60,rotation:-7}}, {{opacity:1,x:0,y:0,rotation:-2,duration:.72,ease:'power4.out'}}, {start + .26:.3f});",
            f"tl.fromTo('#portal-{sid}', {{opacity:0,x:310,y:-90,rotation:8}}, {{opacity:1,x:0,y:0,rotation:2,duration:.86,ease:'expo.out'}}, {start + .48:.3f});",
            f"tl.fromTo('#object-{sid}', {{opacity:0,x:180,y:160,rotation:-14}}, {{opacity:1,x:0,y:0,rotation:4,duration:.64,ease:'back.out(1.2)'}}, {start + .82:.3f});",
            f"tl.fromTo('#line-{sid} path', {{strokeDashoffset:2300}}, {{strokeDashoffset:0,duration:1.9,ease:'power1.inOut'}}, {start + .62:.3f});",
            f"tl.to('#cutout-{sid}', {{x:-115,scale:1.16,duration:{duration * .36:.3f},ease:'sine.inOut'}}, {start + duration * .46:.3f});",
            f"tl.to('#portal-{sid}', {{x:-260,scale:1.44,duration:{duration * .36:.3f},ease:'sine.inOut'}}, {start + duration * .52:.3f});",
        ]
    if layout == "vertical_routine_triptych":
        return lines + [
            f"tl.fromTo('#hero-{sid}', {{scale:1.02,x:-18}}, {{scale:1.08,x:44,duration:{duration:.3f},ease:'none'}}, {start:.3f});",
            f"tl.fromTo('#cutout-{sid}', {{opacity:0,y:230}}, {{opacity:1,y:0,duration:.82,ease:'power3.out'}}, {start + .22:.3f});",
            f"tl.fromTo('#portal-{sid}', {{opacity:0,y:-260}}, {{opacity:1,y:0,duration:1.02,ease:'expo.out'}}, {start + .46:.3f});",
            f"tl.fromTo('#object-{sid}', {{opacity:0,y:260}}, {{opacity:1,y:0,duration:.72,ease:'power4.out'}}, {start + .74:.3f});",
            f"tl.fromTo('#timeline-{sid}', {{opacity:0,y:70}}, {{opacity:1,y:0,duration:.7,ease:'power2.out'}}, {start + 1.05:.3f});",
            f"tl.fromTo('#timeline-{sid} i', {{scaleX:0}}, {{scaleX:1,duration:{duration * .48:.3f},ease:'none'}}, {start + duration * .24:.3f});",
        ]
    if layout == "evidence_slits":
        return lines + [
            f"tl.fromTo('#hero-{sid}', {{scale:1.12,x:-70}}, {{scale:1.03,x:20,duration:{duration:.3f},ease:'none'}}, {start:.3f});",
            f"tl.fromTo('#portal-{sid}', {{opacity:0,scale:.84,x:360}}, {{opacity:1,scale:1,x:0,duration:.88,ease:'power4.out'}}, {start + .24:.3f});",
            f"tl.fromTo('#cutout-{sid}', {{opacity:0,x:-300}}, {{opacity:1,x:0,duration:1.06,ease:'expo.out'}}, {start + .50:.3f});",
            f"tl.fromTo('#object-{sid}', {{opacity:0,scale:.25,rotation:-8}}, {{opacity:1,scale:1,rotation:0,duration:.65,ease:'back.out(1.25)'}}, {start + .94:.3f});",
            f"tl.to('#object-{sid}', {{scale:2.38,x:-520,y:-150,duration:{duration * .34:.3f},ease:'power3.inOut'}}, {start + duration * .44:.3f});",
            f"tl.to('#portal-{sid}', {{filter:'blur(7px)',opacity:.58,duration:{duration * .22:.3f},ease:'sine.inOut'}}, {start + duration * .44:.3f});",
        ]
    if layout == "rumor_table_wide":
        return lines + [
            f"tl.fromTo('#hero-{sid}', {{scale:1.18,x:80,y:20}}, {{scale:1.06,x:-54,y:-8,duration:{duration:.3f},ease:'power1.out'}}, {start:.3f});",
            f"tl.fromTo('#cutout-{sid}', {{opacity:0,x:-340,rotation:-3}}, {{opacity:1,x:0,rotation:0,duration:.96,ease:'power4.out'}}, {start + .30:.3f});",
            f"tl.fromTo('#portal-{sid}', {{opacity:0,x:380,rotation:4}}, {{opacity:1,x:0,rotation:0,duration:1.12,ease:'expo.out'}}, {start + .44:.3f});",
            f"tl.fromTo('#object-{sid}', {{opacity:0,y:180,scale:.5}}, {{opacity:1,y:0,scale:1,duration:.74,ease:'back.out(1.1)'}}, {start + .92:.3f});",
            f"tl.fromTo('#line-{sid} path', {{strokeDashoffset:2300}}, {{strokeDashoffset:0,duration:3.2,ease:'sine.inOut'}}, {start + .68:.3f});",
            f"tl.to('#cutout-{sid}', {{x:90,scale:1.08,duration:{duration * .44:.3f},ease:'sine.inOut'}}, {start + duration * .40:.3f});",
            f"tl.to('#portal-{sid}', {{x:-120,scale:1.12,duration:{duration * .44:.3f},ease:'sine.inOut'}}, {start + duration * .40:.3f});",
        ]
    if layout == "corridor_false_claim":
        return lines + [
            f"tl.fromTo('#hero-{sid}', {{scale:1.01,y:20}}, {{scale:1.18,y:-40,duration:{duration:.3f},ease:'none'}}, {start:.3f});",
            f"tl.fromTo('#cutout-{sid}', {{opacity:0,scale:.65,x:-180}}, {{opacity:1,scale:1,x:0,duration:1.18,ease:'power3.out'}}, {start + .30:.3f});",
            f"tl.fromTo('#portal-{sid}', {{opacity:0,scale:.35,x:240}}, {{opacity:1,scale:1,x:0,duration:.92,ease:'expo.out'}}, {start + .72:.3f});",
            f"tl.fromTo('#object-{sid}', {{opacity:0,rotation:13,y:180}}, {{opacity:1,rotation:-2,y:0,duration:.76,ease:'back.out(1.15)'}}, {start + 1.02:.3f});",
            f"tl.fromTo('#dark-{sid}', {{opacity:0}}, {{opacity:.54,duration:{duration * .48:.3f},ease:'power2.in'}}, {start + duration * .34:.3f});",
            f"tl.to('#portal-{sid}', {{scale:1.92,x:-360,y:-55,duration:{duration * .40:.3f},ease:'power2.inOut'}}, {start + duration * .46:.3f});",
        ]
    if layout == "empty_desk_release":
        return lines + [
            f"tl.fromTo('#hero-{sid}', {{scale:1.24,x:-120,y:-28}}, {{scale:1.03,x:20,y:0,duration:{duration:.3f},ease:'power1.out'}}, {start:.3f});",
            f"tl.fromTo('#cutout-{sid}', {{opacity:0,y:160,rotation:-2}}, {{opacity:1,y:0,rotation:0,duration:1.05,ease:'power4.out'}}, {start + .28:.3f});",
            f"tl.fromTo('#portal-{sid}', {{opacity:0,x:330}}, {{opacity:1,x:0,duration:.92,ease:'expo.out'}}, {start + .60:.3f});",
            f"tl.fromTo('#object-{sid}', {{opacity:0,scale:.4}}, {{opacity:1,scale:1,duration:.64,ease:'back.out(1.1)'}}, {start + .96:.3f});",
            f"tl.to('#portal-{sid}', {{opacity:0,x:280,duration:.48,ease:'power3.in'}}, {start + duration * .50:.3f});",
            f"tl.to('#object-{sid}', {{opacity:0,y:140,duration:.42,ease:'power4.in'}}, {start + duration * .54:.3f});",
            f"tl.to('#cutout-{sid}', {{scale:1.20,x:-135,duration:{duration * .34:.3f},ease:'sine.inOut'}}, {start + duration * .56:.3f});",
        ]
    return lines


def _adult_animation_scene_tweens(scene: dict[str, Any]) -> list[str]:
    """Return one original animated-comic scene from the selected layout.

    Every profile shares the deterministic 2D medium, but each scene uses a
    different entry geometry.  The page rhythm is stored in the bound asset
    pack, so a retry remains frame-stable while a new source rotates through
    its profile's repertoire.
    """

    sid = _safe_id(str(scene["scene_id"]))
    start = float(scene["start_sec"])
    duration = float(scene["duration_sec"])
    tail = max(start + 0.2, start + duration - 0.38)
    layout = str(scene.get("page_layout") or "wide_room_reaction")
    presets = {
        "wide_room_reaction": ("inset(0 100% 0 0)", -190, 32, 230, -60, 0, 150),
        "two_shot_counterpoint": ("polygon(0 0,50% 0,50% 100%,0 100%)", -260, 0, 260, 0, 0, 190),
        "object_memory_insert": ("circle(0% at 74% 52%)", -70, 120, 310, -85, 60, 210),
        "doorway_arrival": ("inset(0 50% 0 50%)", -290, 70, 300, -20, 0, 220),
        "kitchen_table_turn": ("polygon(0 0,100% 0,100% 0,0 0)", -40, 210, 180, -150, -55, 260),
        "closeup_then_wide": ("circle(0% at 34% 42%)", -325, -25, 290, 30, 90, 200),
        "split_room_parallel": ("polygon(0 0,0 0,0 100%,0 100%)", -250, 70, 260, -80, 0, 240),
        "window_pause": ("inset(100% 0 0 0)", -95, 155, 205, -210, 65, 170),
        "phone_on_table": ("circle(0% at 68% 58%)", -215, 65, 305, 0, 15, 225),
        "stairwell_exit": ("polygon(0 100%,100% 100%,100% 100%,0 100%)", -170, 225, 235, -170, -70, 280),
        "office_grid_break": ("inset(0 0 0 100%)", -285, 20, 270, 50, 40, 240),
        "commute_strip": ("inset(0 0 100% 0)", -230, 165, 330, -30, 0, 290),
        "desk_object_closeup": ("circle(0% at 61% 64%)", -65, 210, 250, -90, 130, 130),
        "boss_doorway": ("inset(0 48% 0 48%)", -300, 45, 315, -45, 0, 250),
        "receipt_cascade": ("polygon(0 0,100% 0,100% 0,0 0)", -210, -85, 270, 120, -80, 250),
        "elevator_pause": ("inset(0 0 0 100%)", -245, 40, 295, 40, 0, 245),
        "exit_sign_release": ("polygon(0 100%,100% 100%,100% 100%,0 100%)", -115, 185, 245, -155, -60, 260),
        "empty_room_hold": ("inset(0 100% 0 0)", -40, 65, 175, -55, 110, 160),
        "corridor_long_take": ("circle(0% at 50% 50%)", -190, 10, 210, 0, 0, 210),
        "mirror_reaction": ("polygon(0 0,50% 0,50% 100%,0 100%)", -240, -15, 270, 15, 80, 205),
        "tool_closeup": ("circle(0% at 70% 60%)", -85, 140, 280, -70, 125, 165),
        "minimal_object_hold": ("inset(100% 0 0 0)", -45, 52, 140, -35, 65, 115),
    }
    clip, cutout_x, cutout_y, portal_x, portal_y, object_x, object_y = presets.get(
        layout, presets["wide_room_reaction"],
    )
    entrance_start = max(0.0, start - 0.34) if start else start + 0.08
    lines = [
        f"tl.fromTo('#inner-{sid}', {{opacity:0,clipPath:'{clip}'}}, {{opacity:1,clipPath:'inset(0 0 0 0)',duration:.58,ease:'power3.inOut'}}, {entrance_start:.3f});",
        f"tl.to('#inner-{sid}', {{opacity:0,duration:.42,ease:'power2.inOut'}}, {tail:.3f});",
        f"tl.set('#inner-{sid}', {{opacity:0}}, {start + duration:.3f});",
        f"tl.fromTo('#hero-{sid}', {{scale:1.025,x:0,y:0}}, {{scale:1.115,x:-36,y:-18,duration:{duration:.3f},ease:'none'}}, {start:.3f});",
        f"tl.fromTo('#cutout-{sid}', {{opacity:0,x:{cutout_x},y:{cutout_y},rotation:-3}}, {{opacity:1,x:0,y:0,rotation:0,duration:.82,ease:'power4.out'}}, {start + .17:.3f});",
        f"tl.fromTo('#portal-{sid}', {{opacity:0,x:{portal_x},y:{portal_y},scale:.62,rotation:4}}, {{opacity:1,x:0,y:0,scale:1,rotation:0,duration:.90,ease:'expo.out'}}, {start + .40:.3f});",
        f"tl.fromTo('#object-{sid}', {{opacity:0,x:{object_x},y:{object_y},scale:.35,rotation:-8}}, {{opacity:1,x:0,y:0,scale:1,rotation:0,duration:.64,ease:'back.out(1.18)'}}, {start + .72:.3f});",
        f"tl.fromTo('#copy-{sid}', {{opacity:0,x:-54,y:16}}, {{opacity:1,x:0,y:0,duration:.62,ease:'power3.out'}}, {start + .34:.3f});",
    ]
    if layout in {"phone_on_table", "receipt_cascade", "object_memory_insert", "tool_closeup"}:
        lines.append(
            f"tl.to('#object-{sid}', {{scale:1.38,x:-170,y:-45,duration:{duration * .32:.3f},ease:'power2.inOut'}}, {start + duration * .43:.3f});",
        )
    elif layout in {"empty_room_hold", "corridor_long_take", "window_pause", "minimal_object_hold"}:
        lines.append(
            f"tl.to('#portal-{sid}', {{scale:1.23,x:-105,y:24,duration:{duration * .56:.3f},ease:'sine.inOut'}}, {start + duration * .30:.3f});",
        )
    else:
        lines.append(
            f"tl.to('#cutout-{sid}', {{scale:1.08,x:54,y:-18,duration:{duration * .56:.3f},ease:'sine.inOut'}}, {start + duration * .27:.3f});",
        )
    return lines


def _cinematic_webtoon_scene_tweens(scene: dict[str, Any]) -> list[str]:
    """Read two complete comic pages without rebuilding them as a collage.

    The paid hero and detail assets are already composed webtoon pages.  Each
    remains intact while the camera establishes it and then moves toward a
    deterministic narration-relevant region.  The second page crossfades in
    once, so there is no mechanical push/pull/reset loop.
    """

    sid = _safe_id(str(scene["scene_id"]))
    start = float(scene["start_sec"])
    duration = float(scene["duration_sec"])
    layout = str(scene.get("page_layout") or "hero_left_details_right")
    module = str((scene.get("motion") or {}).get("module") or "living_photo_depth")
    entrance = max(0.0, start - 0.34) if start > 0 else start
    exit_at = max(start + 0.2, start + duration - 0.30)
    hero_focus = {
        "hero_left_details_right": (1.16, 92, -18),
        "phone_portal_insets": (1.22, -138, -26),
        "message_cascade": (1.18, 118, -34),
        "vertical_routine_triptych": (1.20, -42, -20),
        "evidence_slits": (1.24, -154, 4),
        "rumor_table_wide": (1.15, 0, -42),
        "corridor_false_claim": (1.21, 132, -22),
        "empty_desk_release": (1.14, -70, -20),
    }.get(layout, (1.16, 0, -20))
    detail_focus = {
        "living_photo_depth": (1.18, 74, -20),
        "evidence_transform": (1.30, -184, -48),
        "digital_memory_stack": (1.27, -152, -32),
        "graphic_timeline": (1.22, 108, -38),
        "dark_semantic_reveal": (1.25, -116, -34),
        "nested_collage_zoom": (1.32, -210, -54),
    }.get(module, (1.20, 0, -24))
    hero_scale, hero_x, hero_y = hero_focus
    detail_scale, detail_x, detail_y = detail_focus
    hero_move_at = start + 0.30
    page_turn_at = start + duration * 0.49
    detail_move_at = page_turn_at + 0.46
    hero_move_duration = max(0.4, page_turn_at - hero_move_at)
    detail_move_duration = max(0.4, exit_at - detail_move_at)
    return [
        f"tl.fromTo('#inner-{sid}', {{opacity:0}}, {{opacity:1,duration:.36,ease:'power1.out'}}, {entrance:.3f});",
        f"tl.to('#inner-{sid}', {{opacity:0,duration:.30,ease:'power1.in'}}, {exit_at:.3f});",
        f"tl.set('#inner-{sid}', {{opacity:0}}, {start + duration:.3f});",
        f"tl.set('#hero-{sid}', {{opacity:0}}, {start:.3f});",
        f"tl.set('#object-{sid}', {{opacity:0}}, {start:.3f});",
        f"tl.fromTo('#cutout-{sid}', {{opacity:1,scale:1,x:0,y:0}}, {{scale:{hero_scale:.3f},x:{hero_x},y:{hero_y},duration:{hero_move_duration:.3f},ease:'sine.inOut'}}, {hero_move_at:.3f});",
        f"tl.fromTo('#portal-{sid}', {{opacity:0,scale:1,x:0,y:0}}, {{opacity:1,duration:.46,ease:'power1.inOut'}}, {page_turn_at:.3f});",
        f"tl.to('#cutout-{sid}', {{opacity:0,duration:.46,ease:'power1.inOut'}}, {page_turn_at:.3f});",
        f"tl.to('#portal-{sid}', {{scale:{detail_scale:.3f},x:{detail_x},y:{detail_y},duration:{detail_move_duration:.3f},ease:'sine.inOut'}}, {detail_move_at:.3f});",
    ]


def _semantic_webtoon_scene_tweens(scene: dict[str, Any]) -> list[str]:
    """Animate one complete v3 page through its source-bound panel path."""

    sid = _safe_id(str(scene["scene_id"]))
    start = float(scene["start_sec"])
    duration = float(scene["duration_sec"])
    entrance = max(0.0, start - 0.24) if start > 0 else start
    exit_at = max(start + 0.2, start + duration - 0.30)
    camera_path = scene.get("camera_path")
    if not isinstance(camera_path, list) or len(camera_path) < 2:
        raise EditorialMotionRenderError(f"{sid} has no semantic camera path")
    overview = camera_path[0]
    initial = overview.get("transform") if isinstance(overview, dict) else None
    if not isinstance(initial, dict):
        raise EditorialMotionRenderError(f"{sid} semantic overview is invalid")
    lines = [
        (
            f"tl.set('#cutout-{sid}', {{opacity:1,scale:{float(initial['scale']):.3f},"
            f"x:{int(initial['x'])},y:{int(initial['y'])}}}, {entrance:.3f});"
        ),
        f"tl.fromTo('#inner-{sid}', {{opacity:0}}, {{opacity:1,duration:.32,ease:'power1.out'}}, {entrance:.3f});",
        f"tl.to('#inner-{sid}', {{opacity:0,duration:.30,ease:'power1.in'}}, {exit_at:.3f});",
        f"tl.set('#inner-{sid}', {{opacity:0}}, {start + duration:.3f});",
    ]
    transition_duration = min(1.25, max(0.68, duration * 0.055))
    first_focus_at = start + duration * float(camera_path[1]["at_fraction"])
    overview_duration = max(0.25, first_focus_at - start)
    lines.append(
        (
            f"tl.to('#cutout-{sid}', {{scale:{float(initial['scale']) + 0.012:.3f},"
            f"x:{int(initial['x']) + 3},y:{int(initial['y']) - 2},"
            f"duration:{overview_duration:.3f},ease:'none'}}, {start:.3f});"
        ),
    )
    focus_beats = camera_path[1:]
    for index, beat in enumerate(focus_beats):
        if not isinstance(beat, dict) or not isinstance(beat.get("transform"), dict):
            raise EditorialMotionRenderError(f"{sid} semantic camera beat is invalid")
        target = beat["transform"]
        at = start + duration * float(beat["at_fraction"])
        role = str(beat.get("semantic_role") or "")
        if "reaction" in role:
            ease = "power2.out"
        elif "evidence" in role or "cause" in role:
            ease = "power2.inOut"
        else:
            ease = "sine.inOut"
        lines.append(
            (
                f"tl.to('#cutout-{sid}', {{scale:{float(target['scale']):.3f},"
                f"x:{int(target['x'])},y:{int(target['y'])},"
                f"duration:{transition_duration:.3f},ease:'{ease}'}}, {at:.3f});"
            ),
        )
        next_at = (
            start + duration * float(focus_beats[index + 1]["at_fraction"])
            if index + 1 < len(focus_beats)
            else exit_at
        )
        settle_at = at + transition_duration
        settle_duration = max(0.25, next_at - settle_at)
        settle_x = int(target["x"]) + (6 if int(target["x"]) >= 0 else -6)
        settle_y = int(target["y"]) + (3 if int(target["y"]) >= 0 else -3)
        lines.append(
            (
                f"tl.to('#cutout-{sid}', {{scale:{float(target['scale']) + 0.014:.3f},"
                f"x:{settle_x},y:{settle_y},duration:{settle_duration:.3f},"
                f"ease:'none'}}, {settle_at:.3f});"
            ),
        )
    return lines


def _timeline_script(scenes: list[dict[str, Any]], *, style_profile: str) -> str:
    full_duration = max(float(scene["end_sec"]) for scene in scenes)
    lines = [
        "window.__timelines = window.__timelines || {};",
        "const tl = gsap.timeline({paused:true});",
        f"tl.fromTo('#root-fill', {{x:-4}}, {{x:4,duration:{full_duration:.3f},ease:'none'}}, 0);",
    ]
    for scene in scenes:
        sid = _safe_id(str(scene["scene_id"]))
        start = float(scene["start_sec"])
        duration = float(scene["duration_sec"])
        module = str(scene["motion"]["module"])
        tail = max(start + 0.2, start + duration - 0.8)
        if style_profile == FORMAT_VISUAL_SYSTEM_V3_STYLE_PROFILE:
            lines.extend(_semantic_webtoon_scene_tweens(scene))
            continue
        if style_profile == CINEMATIC_INK_WEBTOON_STYLE_PROFILE:
            lines.extend(_cinematic_webtoon_scene_tweens(scene))
            continue
        if style_profile == INK_GOUACHE_STORY_PAGES_STYLE_PROFILE:
            lines.extend(_ink_gouache_scene_tweens(scene))
            continue
        if is_adult_animation_style_profile(style_profile):
            lines.extend(_adult_animation_scene_tweens(scene))
            continue
        lines.extend([
            f"tl.fromTo('#inner-{sid}', {{opacity:0,clipPath:'polygon(0 0,0 0,0 100%,0 100%)'}}, {{opacity:1,clipPath:'polygon(0 0,100% 0,100% 100%,0 100%)',duration:0.9,ease:'power3.inOut'}}, {start:.3f});",
            f"tl.to('#inner-{sid}', {{opacity:0,duration:0.55,ease:'power2.in'}}, {tail:.3f});",
            f"tl.set('#inner-{sid}', {{opacity:0}}, {start + duration:.3f});",
            f"tl.fromTo('#hero-{sid}', {{scale:1.03,x:0,y:0}}, {{scale:1.14,x:-42,y:-22,duration:{duration:.3f},ease:'none'}}, {start:.3f});",
            f"tl.fromTo('#cutout-{sid}', {{opacity:0,x:-120,y:44,rotation:-2}}, {{opacity:1,x:0,y:0,rotation:0,duration:1.2,ease:'power3.out'}}, {start + 0.18:.3f});",
            f"tl.fromTo('#portal-{sid}', {{opacity:0,scale:0.55,x:210,y:40,rotation:5}}, {{opacity:1,scale:1,x:0,y:0,rotation:1,duration:1.35,ease:'back.out(1.12)'}}, {start + 0.42:.3f});",
            f"tl.fromTo('#object-{sid}', {{opacity:0,scale:0.45,rotation:-12}}, {{opacity:1,scale:1,rotation:-3,duration:1.0,ease:'power3.out'}}, {start + 0.9:.3f});",
            f"tl.fromTo('#blue-{sid}', {{x:-520,rotation:-4}}, {{x:0,rotation:0,duration:1.1,ease:'power3.out'}}, {start:.3f});",
            f"tl.fromTo('#coral-{sid}', {{x:620,rotation:5}}, {{x:0,rotation:0,duration:1.15,ease:'power3.out'}}, {start + 0.08:.3f});",
            f"tl.fromTo('#yellow-{sid}', {{y:350}}, {{y:0,duration:1.0,ease:'power3.out'}}, {start + 0.14:.3f});",
            f"tl.fromTo('#line-{sid} path', {{strokeDashoffset:2300}}, {{strokeDashoffset:0,duration:{min(4.2, max(1.4, duration * 0.28)):.3f},ease:'power1.inOut'}}, {start + 0.55:.3f});",
            f"tl.fromTo('#copy-{sid}', {{opacity:0,y:-36}}, {{opacity:1,y:0,duration:0.85,ease:'power2.out'}}, {start + 0.52:.3f});",
            f"tl.fromTo('#tear-{sid}', {{y:180}}, {{y:0,duration:1.0,ease:'power3.out'}}, {start + 0.25:.3f});",
        ])
        if module == "living_photo_depth":
            lines.extend([
                f"tl.to('#cutout-{sid}', {{x:54,y:-24,scale:1.07,duration:{max(1.0, duration - 1.5):.3f},ease:'none'}}, {start + 1.1:.3f});",
                f"tl.to('#portal-{sid}', {{x:-38,y:22,scale:1.08,duration:{max(1.0, duration - 1.7):.3f},ease:'none'}}, {start + 1.2:.3f});",
            ])
        elif module == "evidence_transform":
            lines.extend([
                f"tl.to('#object-{sid}', {{scale:1.65,x:-310,y:-120,rotation:0,duration:{duration * 0.38:.3f},ease:'power2.inOut'}}, {start + duration * 0.34:.3f});",
                f"tl.to('#portal-{sid}', {{scale:1.35,x:-180,duration:{duration * 0.42:.3f},ease:'power2.inOut'}}, {start + duration * 0.42:.3f});",
            ])
        elif module == "digital_memory_stack":
            lines.extend([
                f"tl.to('#portal-{sid}', {{scale:1.85,x:-360,y:-40,rotation:0,duration:{duration * 0.5:.3f},ease:'power2.inOut'}}, {start + duration * 0.34:.3f});",
                f"tl.to('#cutout-{sid}', {{x:-140,scale:1.12,duration:{duration * 0.45:.3f},ease:'power2.inOut'}}, {start + duration * 0.4:.3f});",
            ])
        elif module == "graphic_timeline":
            lines.extend([
                f"tl.fromTo('#timeline-{sid}', {{opacity:0,y:60}}, {{opacity:1,y:0,duration:0.8,ease:'power2.out'}}, {start + duration * 0.18:.3f});",
                f"tl.fromTo('#timeline-{sid} i', {{scaleX:0}}, {{scaleX:1,duration:{duration * 0.55:.3f},ease:'none'}}, {start + duration * 0.28:.3f});",
            ])
        elif module == "dark_semantic_reveal":
            lines.extend([
                f"tl.fromTo('#dark-{sid}', {{opacity:0}}, {{opacity:0.78,duration:{duration * 0.58:.3f},ease:'power2.in'}}, {start + duration * 0.32:.3f});",
                f"tl.to('#portal-{sid}', {{scale:1.5,x:-240,y:-70,duration:{duration * 0.5:.3f},ease:'power2.inOut'}}, {start + duration * 0.38:.3f});",
                f"tl.to('#object-{sid}', {{x:180,y:90,scale:0.78,duration:{duration * 0.42:.3f},ease:'power2.inOut'}}, {start + duration * 0.4:.3f});",
            ])
        elif module == "nested_collage_zoom":
            lines.extend([
                f"tl.to('#portal-{sid}', {{scale:3.7,x:-480,y:-180,rotation:0,duration:{duration * 0.62:.3f},ease:'power2.inOut'}}, {start + duration * 0.28:.3f});",
                f"tl.to('#cutout-{sid}', {{scale:1.35,x:-180,y:80,duration:{duration * 0.55:.3f},ease:'power2.inOut'}}, {start + duration * 0.3:.3f});",
            ])
    lines.extend([
        f"tl.to({{}}, {{duration:0.001}}, {max(float(scene['end_sec']) for scene in scenes):.3f});",
        "window.__timelines['editorial-motion'] = tl;",
    ])
    return "\n".join(lines)


def _composition_html(scenes: list[dict[str, Any]], duration: float, *, style_profile: str) -> str:
    scene_html = "\n".join(
        _scene_markup(scene, scene["workspace_assets"], style_profile=style_profile)
        for scene in scenes
    )
    timeline = _timeline_script(scenes, style_profile=style_profile)
    return f"""<!doctype html>
<html lang="ru"><head><meta charset="UTF-8"><meta name="viewport" content="width=1920,height=1080">
<title>ChonkerTalks Editorial Motion</title><script src="assets/gsap.min.js"></script>
<style>
:root{{--ink:#111820;--cream:#efe5cf;--paper:#f7efdf;--cobalt:#164fa3;--coral:#ef6549;--butter:#f2bd2f;--white:#fffaf0}}
*{{box-sizing:border-box;margin:0;padding:0}}html,body{{width:1920px;height:1080px;overflow:hidden;background:var(--ink);font-family:Arial,sans-serif;color:var(--ink)}}
#root{{position:relative;width:1920px;height:1080px;overflow:hidden}}#root-fill{{position:absolute;left:-8px;right:-8px;top:0;bottom:0;background:var(--cream);will-change:transform}}
.clip,.scene-inner{{position:absolute;inset:0;width:1920px;height:1080px;overflow:hidden}}.scene-inner{{opacity:0;will-change:transform,opacity,clip-path;background:var(--cream)}}
.hero-plate{{position:absolute;inset:-4%;width:108%;height:108%;object-fit:cover;filter:saturate(.78) contrast(1.03) brightness(.78);will-change:transform}}
.scene-grade{{position:absolute;inset:0;background:linear-gradient(90deg,rgba(239,229,207,.78) 0 17%,transparent 48%),linear-gradient(0deg,rgba(17,24,32,.12),transparent 50%)}}
.color-plane{{position:absolute;filter:drop-shadow(18px 22px 34px rgba(17,24,32,.2));will-change:transform}}
.plane-blue{{left:-80px;top:-90px;width:880px;height:790px;background:var(--cobalt);clip-path:polygon(5% 0,94% 3%,100% 18%,92% 42%,100% 72%,83% 100%,5% 92%,0 66%,8% 38%,0 16%)}}
.plane-coral{{right:-130px;top:-90px;width:910px;height:750px;background:var(--coral);clip-path:polygon(8% 5%,94% 0,100% 30%,91% 51%,100% 84%,75% 100%,42% 91%,17% 100%,0 70%,9% 42%,0 21%)}}
.plane-yellow{{left:-90px;bottom:-150px;width:1430px;height:470px;background:var(--butter);clip-path:polygon(0 20%,11% 4%,25% 15%,42% 0,57% 17%,73% 4%,86% 18%,100% 7%,97% 100%,0 100%)}}
.hero-cutout{{position:absolute;left:80px;top:155px;width:820px;height:790px;clip-path:polygon(3% 10%,31% 2%,62% 7%,94% 0,100% 28%,92% 55%,100% 89%,71% 100%,39% 92%,4% 100%,0 62%,7% 34%);filter:drop-shadow(28px 38px 42px rgba(17,24,32,.34));will-change:transform,opacity}}
.hero-cutout img{{position:absolute;width:116%;height:116%;left:-8%;top:-8%;object-fit:cover;filter:saturate(.9) contrast(1.04)}}
.portal-shell{{position:absolute;right:315px;top:130px;width:520px;height:720px;border:15px solid var(--ink);border-radius:72px;background:var(--ink);overflow:hidden;box-shadow:30px 45px 70px rgba(17,24,32,.35);transform-origin:center;will-change:transform,opacity}}
.portal-shell img{{position:absolute;inset:0;width:100%;height:100%;object-fit:cover;filter:saturate(.88) contrast(1.06)}}.portal-shell i{{position:absolute;left:50%;top:16px;width:116px;height:13px;border-radius:12px;background:var(--ink);transform:translateX(-50%)}}
.portal-glow{{position:absolute;inset:-45px;background:radial-gradient(circle,rgba(255,250,240,.7),transparent 62%);z-index:-1}}
.object-fragment{{position:absolute;right:58px;bottom:80px;width:360px;height:360px;clip-path:polygon(50% 0,91% 14%,100% 55%,82% 91%,39% 100%,5% 78%,0 35%,18% 7%);filter:drop-shadow(22px 28px 36px rgba(17,24,32,.34));will-change:transform,opacity}}
.object-fragment img{{width:145%;height:145%;object-fit:cover;object-position:74% 52%;transform:translate(-24%,-18%);filter:saturate(.94) contrast(1.08)}}
.story-line{{position:absolute;inset:0;width:1920px;height:1080px;overflow:visible;pointer-events:none}}.story-line path{{fill:none;stroke:var(--white);stroke-width:7;stroke-linecap:round;stroke-dasharray:2300;stroke-dashoffset:2300;filter:drop-shadow(0 2px 1px rgba(17,24,32,.22))}}
.story-copy{{position:absolute;left:92px;top:72px;width:650px;z-index:8;will-change:transform,opacity}}.story-copy span{{font:900 17px/1 monospace;letter-spacing:.17em;color:var(--butter);background:var(--ink);padding:12px 17px;display:inline-block}}.story-copy h2{{font:900 76px/.9 Arial,sans-serif;letter-spacing:-.055em;margin-top:20px;max-width:620px;color:var(--white);text-shadow:0 3px 0 rgba(17,24,32,.58)}}.story-copy p{{font:700 26px/1.12 Georgia,serif;margin-top:22px;max-width:470px;color:var(--white);text-shadow:0 2px 2px rgba(17,24,32,.95),0 0 18px rgba(17,24,32,.55)}}.story-copy b{{display:inline-block;margin-top:18px;padding:9px 11px;background:var(--paper);font:800 13px/1 monospace;letter-spacing:.12em;color:var(--ink);text-shadow:none}}
.timeline-rig{{position:absolute;left:145px;right:145px;bottom:145px;height:150px;padding-top:75px;display:flex;justify-content:space-between;font:900 17px/1 monospace;letter-spacing:.12em;z-index:7}}.timeline-rig i{{position:absolute;left:0;right:0;top:62px;height:8px;background:var(--ink);transform-origin:left center}}.timeline-rig b{{position:relative;background:var(--paper);padding:9px 12px}}.timeline-rig b:before{{content:'';position:absolute;left:50%;top:-35px;width:20px;height:20px;border-radius:50%;background:var(--coral);border:5px solid var(--paper);transform:translateX(-50%)}}
.dark-reveal{{position:absolute;inset:0;background:radial-gradient(circle at 68% 45%,transparent 0 13%,rgba(5,10,16,.92) 69%),linear-gradient(110deg,rgba(5,10,16,.03),rgba(5,10,16,.75));pointer-events:none;opacity:0;z-index:6}}
.foreground-tear{{position:absolute;left:-2%;right:-2%;bottom:-52px;height:190px;background:var(--paper);clip-path:polygon(0 33%,7% 14%,16% 27%,25% 4%,36% 22%,46% 0,58% 25%,69% 8%,81% 29%,91% 9%,100% 25%,100% 100%,0 100%);filter:drop-shadow(0 -14px 26px rgba(17,24,32,.18));z-index:9;will-change:transform}}
.module-living_photo_depth .timeline-rig,.module-living_photo_depth .dark-reveal{{opacity:0}}
.module-living_photo_depth .hero-cutout{{left:70px;top:170px;width:900px;height:760px}}.module-living_photo_depth .portal-shell{{right:210px;top:170px;width:470px;height:650px}}
.module-evidence_transform .timeline-rig,.module-evidence_transform .dark-reveal{{opacity:0}}.module-evidence_transform .hero-cutout{{left:155px;top:120px;width:710px;height:820px}}.module-evidence_transform .portal-shell{{right:120px;top:105px;width:720px;height:580px;border-radius:18px;clip-path:polygon(3% 0,100% 5%,96% 100%,0 94%)}}.module-evidence_transform .object-fragment{{right:690px;bottom:62px;width:410px;height:410px}}
.module-digital_memory_stack .timeline-rig,.module-digital_memory_stack .dark-reveal{{opacity:0}}.module-digital_memory_stack .hero-cutout{{left:130px;top:250px;width:700px;height:650px}}.module-digital_memory_stack .portal-shell{{right:250px;top:80px;width:560px;height:790px}}.module-digital_memory_stack .object-fragment{{right:70px;bottom:135px;width:320px;height:320px}}
.module-graphic_timeline .dark-reveal{{opacity:0}}.module-graphic_timeline .hero-cutout{{left:880px;top:100px;width:900px;height:680px}}.module-graphic_timeline .portal-shell{{left:130px;right:auto;top:125px;width:620px;height:500px;border-radius:28px;clip-path:polygon(0 4%,100% 0,96% 96%,4% 100%)}}.module-graphic_timeline .story-copy{{left:920px;top:75px}}.module-graphic_timeline .timeline-rig{{left:120px;right:120px;bottom:115px}}
.module-dark_semantic_reveal .timeline-rig{{opacity:0}}.module-dark_semantic_reveal .plane-blue{{background:#10243c}}.module-dark_semantic_reveal .plane-coral{{background:#6f2e31}}.module-dark_semantic_reveal .plane-yellow{{background:#b48729}}.module-dark_semantic_reveal .hero-cutout{{left:760px;top:55px;width:1040px;height:940px}}.module-dark_semantic_reveal .portal-shell{{left:170px;right:auto;top:200px;width:520px;height:650px;border-radius:10px}}.module-dark_semantic_reveal .story-copy{{left:105px;top:78px;width:700px}}
.module-nested_collage_zoom .timeline-rig,.module-nested_collage_zoom .dark-reveal{{opacity:0}}.module-nested_collage_zoom .hero-cutout{{left:330px;top:100px;width:1260px;height:860px}}.module-nested_collage_zoom .portal-shell{{right:560px;top:220px;width:520px;height:520px;border-radius:50%}}.module-nested_collage_zoom .story-copy{{left:95px;top:70px;width:590px}}
/* Cinematic Webtoon v2: paid assets are complete pages, never collage parts. */
#root.profile-cinematic_ink_webtoon_v1,#root.profile-acc1_format_visual_system_v3{{--webtoon-ink:#111317;--webtoon-paper:#e8dfcb;--webtoon-band:#090b0f}}
#root.profile-cinematic_ink_webtoon_v1 #root-fill,#root.profile-acc1_format_visual_system_v3 #root-fill{{background:var(--webtoon-ink)}}
#root.profile-cinematic_ink_webtoon_v1 .scene-inner,#root.profile-acc1_format_visual_system_v3 .scene-inner{{background:var(--webtoon-ink);isolation:isolate}}
#root.profile-cinematic_ink_webtoon_v1 .scene-inner:after,#root.profile-acc1_format_visual_system_v3 .scene-inner:after{{content:'';position:absolute;left:0;right:0;bottom:0;height:130px;background:rgba(9,11,15,.94);z-index:20;pointer-events:none}}
#root.profile-cinematic_ink_webtoon_v1 .hero-plate,#root.profile-cinematic_ink_webtoon_v1 .scene-grade,#root.profile-cinematic_ink_webtoon_v1 .color-plane,#root.profile-cinematic_ink_webtoon_v1 .object-fragment,#root.profile-cinematic_ink_webtoon_v1 .story-line,#root.profile-cinematic_ink_webtoon_v1 .story-copy,#root.profile-cinematic_ink_webtoon_v1 .timeline-rig,#root.profile-cinematic_ink_webtoon_v1 .dark-reveal,#root.profile-cinematic_ink_webtoon_v1 .foreground-tear,#root.profile-acc1_format_visual_system_v3 .hero-plate,#root.profile-acc1_format_visual_system_v3 .scene-grade,#root.profile-acc1_format_visual_system_v3 .color-plane,#root.profile-acc1_format_visual_system_v3 .object-fragment,#root.profile-acc1_format_visual_system_v3 .story-line,#root.profile-acc1_format_visual_system_v3 .story-copy,#root.profile-acc1_format_visual_system_v3 .timeline-rig,#root.profile-acc1_format_visual_system_v3 .dark-reveal,#root.profile-acc1_format_visual_system_v3 .foreground-tear{{display:none}}
#root.profile-cinematic_ink_webtoon_v1 .hero-cutout,#root.profile-cinematic_ink_webtoon_v1 .portal-shell,#root.profile-acc1_format_visual_system_v3 .hero-cutout,#root.profile-acc1_format_visual_system_v3 .portal-shell{{position:absolute;left:18px;right:18px;top:18px;bottom:18px;width:auto;height:auto;border:5px solid var(--webtoon-ink);border-radius:18px;background:var(--webtoon-paper);clip-path:none;box-shadow:none;filter:none;overflow:hidden;padding:0;transform-origin:center center;will-change:transform,opacity;z-index:3}}
#root.profile-cinematic_ink_webtoon_v1 .portal-shell,#root.profile-acc1_format_visual_system_v3 .portal-shell{{z-index:4}}
#root.profile-acc1_format_visual_system_v3 .portal-shell{{display:none}}
#root.profile-cinematic_ink_webtoon_v1 .hero-cutout img,#root.profile-cinematic_ink_webtoon_v1 .portal-shell img,#root.profile-acc1_format_visual_system_v3 .hero-cutout img,#root.profile-acc1_format_visual_system_v3 .portal-shell img{{position:absolute;inset:0;width:100%;height:100%;object-fit:contain;object-position:center;filter:none;transform:none}}
#root.profile-cinematic_ink_webtoon_v1 .portal-shell i,#root.profile-cinematic_ink_webtoon_v1 .portal-glow,#root.profile-acc1_format_visual_system_v3 .portal-shell i,#root.profile-acc1_format_visual_system_v3 .portal-glow{{display:none}}
/* Adult Animation v1: six original episodic comic series, not a single page skin. */
#root[class^="profile-adult_animation_"]{{--series-bg:#f1e1ca;--series-ink:#202325;--series-paper:#fff7e7;--series-accent:#ca5a43;--series-accent-two:#5c8b83;--series-line:5px}}
#root.profile-adult_animation_family_v1{{--series-bg:#e6c8ae;--series-ink:#283032;--series-paper:#fff2dc;--series-accent:#c76853;--series-accent-two:#78937b;--series-line:5px}}
#root.profile-adult_animation_work_v1{{--series-bg:#a9b49a;--series-ink:#1c2824;--series-paper:#f3edcf;--series-accent:#b55340;--series-accent-two:#3f6250;--series-line:6px}}
#root.profile-adult_animation_saga_absurd_v1{{--series-bg:#b4c4bd;--series-ink:#263338;--series-paper:#f2e8d0;--series-accent:#ba7451;--series-accent-two:#d1b64c;--series-line:4px}}
#root.profile-adult_animation_confessions_v1{{--series-bg:#d6a8a3;--series-ink:#2e2931;--series-paper:#fff3dd;--series-accent:#963f4a;--series-accent-two:#536881;--series-line:6px}}
#root.profile-adult_animation_professions_v1{{--series-bg:#92abc2;--series-ink:#172d3b;--series-paper:#f8eed6;--series-accent:#d87035;--series-accent-two:#426f76;--series-line:5px}}
#root.profile-adult_animation_daily_weird_v1{{--series-bg:#eeece1;--series-ink:#262728;--series-paper:#fffdf4;--series-accent:#bd5a50;--series-accent-two:#6189a1;--series-line:4px}}
#root[class^="profile-adult_animation_"] #root-fill{{background:var(--series-bg);background-image:radial-gradient(rgba(32,35,37,.13) .75px,transparent .75px);background-size:7px 7px}}
#root[class^="profile-adult_animation_"] .scene-inner{{background:var(--series-bg);color:var(--series-ink)}}
#root[class^="profile-adult_animation_"] .hero-plate{{inset:-3%;width:106%;height:106%;filter:saturate(.82) contrast(1.07) brightness(.86)}}
#root[class^="profile-adult_animation_"] .scene-grade{{background:linear-gradient(90deg,var(--series-bg) 0,rgba(255,255,255,.08) 44%,transparent 72%),linear-gradient(0deg,rgba(31,35,37,.20),transparent 52%);opacity:.78}}
#root[class^="profile-adult_animation_"] .color-plane{{display:none}}
#root[class^="profile-adult_animation_"] .hero-cutout{{background:var(--series-paper);padding:11px;clip-path:polygon(2% 5%,95% 0,100% 94%,4% 100%);filter:drop-shadow(12px 16px 0 rgba(32,35,37,.23));z-index:3}}
#root[class^="profile-adult_animation_"] .hero-cutout:before{{content:'';position:absolute;inset:0;border:var(--series-line) solid var(--series-ink);z-index:2;pointer-events:none}}
#root[class^="profile-adult_animation_"] .hero-cutout img{{left:0;top:0;width:100%;height:100%;filter:saturate(.9) contrast(1.03)}}
#root[class^="profile-adult_animation_"] .portal-shell{{border:var(--series-line) solid var(--series-ink);border-radius:18px;background:var(--series-paper);box-shadow:12px 16px 0 rgba(32,35,37,.28);z-index:4}}
#root[class^="profile-adult_animation_"] .portal-shell i,#root[class^="profile-adult_animation_"] .portal-glow{{display:none}}
#root[class^="profile-adult_animation_"] .object-fragment{{background:var(--series-paper);padding:9px;clip-path:polygon(5% 0,100% 5%,94% 100%,0 94%);filter:drop-shadow(9px 12px 0 rgba(32,35,37,.25));z-index:5}}
#root[class^="profile-adult_animation_"] .object-fragment img{{width:112%;height:112%;transform:translate(-6%,-6%);object-position:center;filter:saturate(.92) contrast(1.05)}}
#root[class^="profile-adult_animation_"] .story-line,#root[class^="profile-adult_animation_"] .timeline-rig,#root[class^="profile-adult_animation_"] .foreground-tear,#root[class^="profile-adult_animation_"] .dark-reveal{{display:none}}
#root[class^="profile-adult_animation_"] .story-copy{{left:74px;top:64px;width:670px;z-index:8}}
#root[class^="profile-adult_animation_"] .story-copy span{{display:inline-block;background:var(--series-ink);color:var(--series-paper);padding:9px 13px;font:800 14px/1 Arial,sans-serif;letter-spacing:.08em}}
#root[class^="profile-adult_animation_"] .story-copy h2{{max-width:680px;margin-top:15px;color:var(--series-ink);font:900 74px/.88 Arial,sans-serif;letter-spacing:-.07em;text-shadow:3px 3px 0 var(--series-paper)}}
#root[class^="profile-adult_animation_"] .story-copy p{{display:none}}
#root[class^="profile-adult_animation_"] .story-copy b{{display:inline-block;margin-top:15px;padding:8px 10px;background:var(--series-accent);color:var(--series-paper);font:800 12px/1 Arial,sans-serif;letter-spacing:.1em}}
/* Ten reusable page rhythms. The profiles choose only their own ten-item repertoire. */
#root[class^="profile-adult_animation_"] .layout-wide_room_reaction .hero-cutout,#root[class^="profile-adult_animation_"] .layout-closeup_then_wide .hero-cutout{{left:-30px;top:175px;width:1160px;height:770px}}#root[class^="profile-adult_animation_"] .layout-wide_room_reaction .portal-shell,#root[class^="profile-adult_animation_"] .layout-closeup_then_wide .portal-shell{{right:45px;top:170px;width:620px;height:570px}}#root[class^="profile-adult_animation_"] .layout-wide_room_reaction .object-fragment,#root[class^="profile-adult_animation_"] .layout-closeup_then_wide .object-fragment{{right:150px;bottom:55px;width:330px;height:250px}}
#root[class^="profile-adult_animation_"] .layout-two_shot_counterpoint .hero-cutout,#root[class^="profile-adult_animation_"] .layout-split_room_parallel .hero-cutout{{left:38px;top:150px;width:790px;height:820px}}#root[class^="profile-adult_animation_"] .layout-two_shot_counterpoint .portal-shell,#root[class^="profile-adult_animation_"] .layout-split_room_parallel .portal-shell{{right:55px;top:105px;width:815px;height:820px}}#root[class^="profile-adult_animation_"] .layout-two_shot_counterpoint .object-fragment,#root[class^="profile-adult_animation_"] .layout-split_room_parallel .object-fragment{{left:735px;bottom:42px;width:390px;height:285px}}
#root[class^="profile-adult_animation_"] .layout-object_memory_insert .hero-cutout,#root[class^="profile-adult_animation_"] .layout-phone_on_table .hero-cutout,#root[class^="profile-adult_animation_"] .layout-tool_closeup .hero-cutout{{left:-95px;top:205px;width:890px;height:760px}}#root[class^="profile-adult_animation_"] .layout-object_memory_insert .portal-shell,#root[class^="profile-adult_animation_"] .layout-phone_on_table .portal-shell,#root[class^="profile-adult_animation_"] .layout-tool_closeup .portal-shell{{right:185px;top:75px;width:640px;height:790px}}#root[class^="profile-adult_animation_"] .layout-object_memory_insert .object-fragment,#root[class^="profile-adult_animation_"] .layout-phone_on_table .object-fragment,#root[class^="profile-adult_animation_"] .layout-tool_closeup .object-fragment{{right:-20px;bottom:58px;width:450px;height:390px}}
#root[class^="profile-adult_animation_"] .layout-doorway_arrival .hero-cutout,#root[class^="profile-adult_animation_"] .layout-boss_doorway .hero-cutout{{left:550px;top:95px;width:1160px;height:930px}}#root[class^="profile-adult_animation_"] .layout-doorway_arrival .portal-shell,#root[class^="profile-adult_animation_"] .layout-boss_doorway .portal-shell{{left:-45px;right:auto;top:195px;width:690px;height:695px}}#root[class^="profile-adult_animation_"] .layout-doorway_arrival .object-fragment,#root[class^="profile-adult_animation_"] .layout-boss_doorway .object-fragment{{right:80px;bottom:18px;width:360px;height:300px}}
#root[class^="profile-adult_animation_"] .layout-kitchen_table_turn .hero-cutout,#root[class^="profile-adult_animation_"] .layout-receipt_cascade .hero-cutout{{left:-55px;top:250px;width:1300px;height:720px}}#root[class^="profile-adult_animation_"] .layout-kitchen_table_turn .portal-shell,#root[class^="profile-adult_animation_"] .layout-receipt_cascade .portal-shell{{right:-35px;top:55px;width:720px;height:610px}}#root[class^="profile-adult_animation_"] .layout-kitchen_table_turn .object-fragment,#root[class^="profile-adult_animation_"] .layout-receipt_cascade .object-fragment{{right:520px;bottom:38px;width:430px;height:315px}}
#root[class^="profile-adult_animation_"] .layout-window_pause .hero-cutout,#root[class^="profile-adult_animation_"] .layout-empty_room_hold .hero-cutout,#root[class^="profile-adult_animation_"] .layout-minimal_object_hold .hero-cutout{{left:380px;top:120px;width:1220px;height:840px}}#root[class^="profile-adult_animation_"] .layout-window_pause .portal-shell,#root[class^="profile-adult_animation_"] .layout-empty_room_hold .portal-shell,#root[class^="profile-adult_animation_"] .layout-minimal_object_hold .portal-shell{{left:60px;right:auto;top:220px;width:530px;height:570px}}#root[class^="profile-adult_animation_"] .layout-window_pause .object-fragment,#root[class^="profile-adult_animation_"] .layout-empty_room_hold .object-fragment,#root[class^="profile-adult_animation_"] .layout-minimal_object_hold .object-fragment{{right:80px;bottom:80px;width:290px;height:230px}}
#root[class^="profile-adult_animation_"] .layout-stairwell_exit .hero-cutout,#root[class^="profile-adult_animation_"] .layout-exit_sign_release .hero-cutout{{left:245px;top:-30px;width:1350px;height:1150px}}#root[class^="profile-adult_animation_"] .layout-stairwell_exit .portal-shell,#root[class^="profile-adult_animation_"] .layout-exit_sign_release .portal-shell{{left:-20px;right:auto;top:110px;width:640px;height:790px}}#root[class^="profile-adult_animation_"] .layout-stairwell_exit .object-fragment,#root[class^="profile-adult_animation_"] .layout-exit_sign_release .object-fragment{{right:-10px;bottom:70px;width:350px;height:330px}}
#root[class^="profile-adult_animation_"] .layout-commute_strip .hero-cutout,#root[class^="profile-adult_animation_"] .layout-elevator_pause .hero-cutout,#root[class^="profile-adult_animation_"] .layout-corridor_long_take .hero-cutout{{left:-40px;top:110px;width:700px;height:900px}}#root[class^="profile-adult_animation_"] .layout-commute_strip .portal-shell,#root[class^="profile-adult_animation_"] .layout-elevator_pause .portal-shell,#root[class^="profile-adult_animation_"] .layout-corridor_long_take .portal-shell{{left:665px;right:auto;top:100px;width:570px;height:900px}}#root[class^="profile-adult_animation_"] .layout-commute_strip .object-fragment,#root[class^="profile-adult_animation_"] .layout-elevator_pause .object-fragment,#root[class^="profile-adult_animation_"] .layout-corridor_long_take .object-fragment{{right:-25px;top:110px;bottom:auto;width:580px;height:900px}}
#root[class^="profile-adult_animation_"] .layout-office_grid_break .hero-cutout,#root[class^="profile-adult_animation_"] .layout-desk_object_closeup .hero-cutout,#root[class^="profile-adult_animation_"] .layout-mirror_reaction .hero-cutout{{left:90px;top:140px;width:750px;height:810px}}#root[class^="profile-adult_animation_"] .layout-office_grid_break .portal-shell,#root[class^="profile-adult_animation_"] .layout-desk_object_closeup .portal-shell,#root[class^="profile-adult_animation_"] .layout-mirror_reaction .portal-shell{{right:55px;top:85px;width:820px;height:700px}}#root[class^="profile-adult_animation_"] .layout-office_grid_break .object-fragment,#root[class^="profile-adult_animation_"] .layout-desk_object_closeup .object-fragment,#root[class^="profile-adult_animation_"] .layout-mirror_reaction .object-fragment{{right:505px;bottom:-20px;width:410px;height:350px}}
/* Ink & Gouache v2: the plates are travelling depth fields, not paper cards. */
#root.profile-ink_gouache_story_pages_v1{{--ink:#171813;--cream:#d9cfb6;--paper:#e7ddc4;--cobalt:#536353;--coral:#bd3e24;--butter:#aeb70d;--white:#eee8d8}}
#root.profile-ink_gouache_story_pages_v1 #root-fill{{background:#0c0e0d;background-image:radial-gradient(rgba(231,221,196,.06) .8px,transparent .8px);background-size:6px 6px}}
#root.profile-ink_gouache_story_pages_v1 .family-work{{--family-bg:#526052;--family-ink:#171813;--family-paper:#d9cfb6;--family-accent:#334238;--family-flash:#e7ddc4}}
#root.profile-ink_gouache_story_pages_v1 .family-digital{{--family-bg:#071025;--family-ink:#05070b;--family-paper:#dfe7e5;--family-accent:#1458d4;--family-flash:#b7c80d}}
#root.profile-ink_gouache_story_pages_v1 .family-dark_saga{{--family-bg:#08111b;--family-ink:#090d12;--family-paper:#d3c6a7;--family-accent:#6b2432;--family-flash:#9d3139}}
#root.profile-ink_gouache_story_pages_v1 .family-relationships{{--family-bg:#8e4d3c;--family-ink:#17162a;--family-paper:#d9c6a4;--family-accent:#2e315c;--family-flash:#c78648}}
#root.profile-ink_gouache_story_pages_v1 .family-memory{{--family-bg:#bc7964;--family-ink:#283d3f;--family-paper:#ddcfb4;--family-accent:#507a76;--family-flash:#dc9a79}}
#root.profile-ink_gouache_story_pages_v1 .family-odd_job{{--family-bg:#d05a1d;--family-ink:#102b4c;--family-paper:#e7dfcc;--family-accent:#164f91;--family-flash:#f07a24}}
#root.profile-ink_gouache_story_pages_v1 .scene-inner{{background:var(--family-bg);color:var(--family-ink);isolation:isolate}}
#root.profile-ink_gouache_story_pages_v1 .hero-plate{{inset:-4%;width:108%;height:108%;filter:saturate(.84) contrast(1.05) brightness(.76);z-index:0}}
#root.profile-ink_gouache_story_pages_v1 .scene-grade{{background:linear-gradient(90deg,var(--family-bg) 0,rgba(5,7,9,.10) 31%,transparent 57%),linear-gradient(0deg,rgba(5,7,9,.38),transparent 58%);opacity:.74;z-index:1}}
#root.profile-ink_gouache_story_pages_v1 .color-plane{{display:none;filter:none;opacity:.72;z-index:2}}
#root.profile-ink_gouache_story_pages_v1 .plane-blue{{left:-150px;top:-150px;width:520px;height:660px;background:var(--family-bg);clip-path:polygon(0 0,90% 0,100% 72%,65% 100%,0 88%)}}
#root.profile-ink_gouache_story_pages_v1 .plane-coral{{right:-150px;top:-120px;width:550px;height:500px;background:var(--family-accent);clip-path:polygon(20% 0,100% 4%,92% 100%,0 80%,9% 31%)}}
#root.profile-ink_gouache_story_pages_v1 .plane-yellow{{display:none}}
#root.profile-ink_gouache_story_pages_v1 .hero-cutout{{background:transparent;padding:0;clip-path:polygon(0 2%,97% 0,100% 94%,3% 100%);filter:drop-shadow(14px 18px 24px rgba(4,7,8,.30));transform-origin:center;z-index:3}}
#root.profile-ink_gouache_story_pages_v1 .hero-cutout img{{position:absolute;left:-3%;top:-3%;width:106%;height:106%;filter:saturate(.94) contrast(1.04)}}
#root.profile-ink_gouache_story_pages_v1 .portal-shell{{border:0;border-radius:0;background:transparent;clip-path:polygon(3% 0,100% 5%,96% 100%,0 94%);box-shadow:16px 21px 30px rgba(4,7,8,.31);z-index:4}}
#root.profile-ink_gouache_story_pages_v1 .portal-shell i,#root.profile-ink_gouache_story_pages_v1 .portal-glow{{display:none}}
#root.profile-ink_gouache_story_pages_v1 .object-fragment{{padding:0;background:transparent;clip-path:polygon(0 7%,94% 0,100% 88%,6% 100%);filter:drop-shadow(10px 14px 20px rgba(4,7,8,.32));z-index:5}}
#root.profile-ink_gouache_story_pages_v1 .object-fragment img{{width:110%;height:110%;transform:translate(-5%,-5%);object-position:center;filter:saturate(.96) contrast(1.05)}}
#root.profile-ink_gouache_story_pages_v1 .story-line{{opacity:0;z-index:7}}
#root.profile-ink_gouache_story_pages_v1 .story-line path{{stroke:#bd3e24;stroke-width:6;filter:none}}
#root.profile-ink_gouache_story_pages_v1 .layout-message_cascade .story-line,#root.profile-ink_gouache_story_pages_v1 .layout-rumor_table_wide .story-line{{opacity:.88}}
#root.profile-ink_gouache_story_pages_v1 .story-copy{{left:82px;top:62px;width:720px;z-index:8}}
#root.profile-ink_gouache_story_pages_v1 .story-copy span{{color:var(--family-paper);background:var(--family-ink);font-size:15px;padding:10px 14px}}
#root.profile-ink_gouache_story_pages_v1 .story-copy h2{{font-family:Georgia,serif;font-size:78px;line-height:.86;letter-spacing:-.066em;color:var(--family-paper);text-shadow:0 3px 1px rgba(0,0,0,.62);max-width:720px}}
#root.profile-ink_gouache_story_pages_v1 .story-copy p{{font-family:Georgia,serif;font-size:23px;line-height:1.16;color:var(--family-ink);text-shadow:none;background:rgba(231,221,196,.94);padding:11px 14px;max-width:500px}}
#root.profile-ink_gouache_story_pages_v1 .story-copy b{{background:var(--family-ink);color:var(--family-paper)}}
#root.profile-ink_gouache_story_pages_v1 .timeline-rig{{z-index:8;color:var(--family-ink)}}
#root.profile-ink_gouache_story_pages_v1 .timeline-rig i{{background:var(--family-ink)}}
#root.profile-ink_gouache_story_pages_v1 .timeline-rig b{{background:var(--family-paper)}}
#root.profile-ink_gouache_story_pages_v1 .timeline-rig b:before{{background:var(--family-accent);border-color:var(--family-paper)}}
#root.profile-ink_gouache_story_pages_v1 .foreground-tear{{display:none;background:var(--family-paper);filter:none;height:125px;opacity:.93}}
#root.profile-ink_gouache_story_pages_v1 .presentation-intro .foreground-tear,#root.profile-ink_gouache_story_pages_v1 .layout-empty_desk_release .foreground-tear{{display:block}}
#root.profile-ink_gouache_story_pages_v1 .dark-reveal{{display:none;background:radial-gradient(circle at 61% 47%,transparent 0 11%,rgba(2,5,9,.91) 74%);z-index:6}}
#root.profile-ink_gouache_story_pages_v1 .layout-corridor_false_claim .dark-reveal{{display:block}}
/* Eight genuinely different page rhythms, with typography participating in each composition. */
#root.profile-ink_gouache_story_pages_v1 .layout-hero_left_details_right .hero-cutout{{left:-75px;top:145px;width:1260px;height:825px}}#root.profile-ink_gouache_story_pages_v1 .layout-hero_left_details_right .portal-shell{{right:-70px;top:75px;width:780px;height:850px}}#root.profile-ink_gouache_story_pages_v1 .layout-hero_left_details_right .object-fragment{{right:285px;bottom:35px;width:360px;height:270px}}
#root.profile-ink_gouache_story_pages_v1 .layout-phone_portal_insets .hero-cutout{{left:-130px;top:220px;width:1000px;height:780px}}#root.profile-ink_gouache_story_pages_v1 .layout-phone_portal_insets .portal-shell{{right:155px;top:35px;width:735px;height:920px;clip-path:polygon(8% 0,100% 4%,94% 100%,0 92%)}}#root.profile-ink_gouache_story_pages_v1 .layout-phone_portal_insets .object-fragment{{right:-75px;bottom:75px;width:420px;height:360px}}#root.profile-ink_gouache_story_pages_v1 .layout-phone_portal_insets .story-copy{{left:88px;top:72px;width:650px}}
#root.profile-ink_gouache_story_pages_v1 .layout-message_cascade .hero-cutout{{left:-95px;top:-55px;width:1180px;height:1160px;clip-path:polygon(0 4%,95% 0,100% 92%,3% 100%)}}#root.profile-ink_gouache_story_pages_v1 .layout-message_cascade .portal-shell{{right:35px;top:90px;width:920px;height:720px;clip-path:polygon(6% 0,100% 10%,92% 100%,0 88%)}}#root.profile-ink_gouache_story_pages_v1 .layout-message_cascade .object-fragment{{right:210px;bottom:8px;width:520px;height:360px}}#root.profile-ink_gouache_story_pages_v1 .layout-message_cascade .story-copy{{left:auto;right:72px;top:58px;width:720px;text-align:right}}#root.profile-ink_gouache_story_pages_v1 .layout-message_cascade .story-copy p{{margin-left:auto;text-align:left}}
#root.profile-ink_gouache_story_pages_v1 .layout-vertical_routine_triptych .hero-cutout{{left:710px;top:-30px;width:420px;height:1140px;clip-path:polygon(0 0,96% 2%,100% 100%,3% 97%)}}#root.profile-ink_gouache_story_pages_v1 .layout-vertical_routine_triptych .portal-shell{{left:1115px;right:auto;top:-20px;width:420px;height:1130px;clip-path:polygon(3% 0,100% 3%,96% 100%,0 97%)}}#root.profile-ink_gouache_story_pages_v1 .layout-vertical_routine_triptych .object-fragment{{right:-5px;top:-10px;bottom:auto;width:420px;height:1120px;clip-path:polygon(0 3%,96% 0,100% 97%,4% 100%)}}#root.profile-ink_gouache_story_pages_v1 .layout-vertical_routine_triptych .story-copy{{left:80px;top:122px;width:590px}}#root.profile-ink_gouache_story_pages_v1 .layout-vertical_routine_triptych .timeline-rig{{left:85px;right:85px;bottom:54px}}
#root.profile-ink_gouache_story_pages_v1 .layout-evidence_slits .hero-cutout{{left:-70px;top:72px;width:920px;height:930px}}#root.profile-ink_gouache_story_pages_v1 .layout-evidence_slits .portal-shell{{right:-55px;top:-30px;width:1120px;height:790px;clip-path:polygon(0 3%,100% 0,96% 100%,3% 94%)}}#root.profile-ink_gouache_story_pages_v1 .layout-evidence_slits .object-fragment{{right:580px;bottom:-45px;width:560px;height:540px}}#root.profile-ink_gouache_story_pages_v1 .layout-evidence_slits .story-copy{{left:auto;right:75px;top:auto;bottom:68px;width:660px}}#root.profile-ink_gouache_story_pages_v1 .layout-evidence_slits .story-copy p{{max-width:620px}}
#root.profile-ink_gouache_story_pages_v1 .layout-rumor_table_wide .hero-cutout{{left:-70px;top:175px;width:1280px;height:850px}}#root.profile-ink_gouache_story_pages_v1 .layout-rumor_table_wide .portal-shell{{right:-95px;top:95px;width:850px;height:750px}}#root.profile-ink_gouache_story_pages_v1 .layout-rumor_table_wide .object-fragment{{right:320px;bottom:-55px;width:470px;height:330px}}#root.profile-ink_gouache_story_pages_v1 .layout-rumor_table_wide .story-copy{{left:595px;top:45px;width:850px;text-align:center}}#root.profile-ink_gouache_story_pages_v1 .layout-rumor_table_wide .story-copy p{{margin-left:auto;margin-right:auto;text-align:left}}
#root.profile-ink_gouache_story_pages_v1 .layout-corridor_false_claim .hero-cutout{{left:545px;top:-55px;width:1240px;height:1170px}}#root.profile-ink_gouache_story_pages_v1 .layout-corridor_false_claim .portal-shell{{left:-85px;right:auto;top:120px;width:760px;height:880px;clip-path:polygon(9% 0,100% 4%,89% 100%,0 93%)}}#root.profile-ink_gouache_story_pages_v1 .layout-corridor_false_claim .object-fragment{{right:-65px;bottom:55px;width:450px;height:510px}}#root.profile-ink_gouache_story_pages_v1 .layout-corridor_false_claim .story-copy{{left:auto;right:70px;top:70px;width:650px;text-align:right}}#root.profile-ink_gouache_story_pages_v1 .layout-corridor_false_claim .story-copy p{{margin-left:auto;text-align:left}}
#root.profile-ink_gouache_story_pages_v1 .layout-empty_desk_release .hero-cutout{{left:405px;top:-25px;width:1540px;height:1120px}}#root.profile-ink_gouache_story_pages_v1 .layout-empty_desk_release .portal-shell{{left:-90px;right:auto;top:235px;width:720px;height:700px}}#root.profile-ink_gouache_story_pages_v1 .layout-empty_desk_release .object-fragment{{display:none}}#root.profile-ink_gouache_story_pages_v1 .layout-empty_desk_release .story-copy{{left:88px;top:auto;bottom:98px;width:650px}}
</style></head><body>
<main id="root" class="profile-{html.escape(style_profile, quote=True)}" data-composition-id="editorial-motion" data-start="0" data-width="1920" data-height="1080" data-fps="30" data-duration="{duration:.3f}">
<section id="root-fill" class="clip" data-start="0" data-duration="{duration:.3f}" data-track-index="0"></section>
{scene_html}
</main><script>{timeline}</script></body></html>"""


def _write_workspace(
    scenes: list[dict[str, Any]], artifact_root: Path, audio: Path, duration: float, *, style_profile: str,
    workspace_path: Path | None = None,
) -> Path:
    workspace = (
        Path(workspace_path).resolve()
        if workspace_path is not None
        else artifact_root / "editorial-motion-hyperframes"
    )
    assets_dir = workspace / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)
    if not GSAP_RUNTIME.is_file():
        raise EditorialMotionRenderError("project-controlled GSAP runtime is missing")
    shutil.copy2(GSAP_RUNTIME, assets_dir / "gsap.min.js")
    materialized: list[dict[str, Any]] = []
    for scene_index, scene in enumerate(scenes, start=1):
        names: list[str] = []
        for asset in scene["verified_assets"]:
            source = Path(asset["verified_path"])
            name = f"scene-{scene_index:03d}-{asset['layer_role']}{source.suffix.lower()}"
            shutil.copy2(source, assets_dir / name)
            names.append(f"assets/{name}")
        materialized.append({**scene, "workspace_assets": names})
    (workspace / "index.html").write_text(
        _composition_html(materialized, duration, style_profile=style_profile), encoding="utf-8",
    )
    (workspace / "hyperframes.json").write_text(json.dumps({
        "$schema": "https://hyperframes.heygen.com/schema/hyperframes.json",
        "paths": {"blocks": "compositions", "components": "compositions/components", "assets": "assets"},
        "media": {"autoProxy": True},
    }, indent=2) + "\n", encoding="utf-8")
    (workspace / "meta.json").write_text(json.dumps({
        "id": "editorial-motion", "name": "ChonkerTalks Editorial Motion",
    }, indent=2) + "\n", encoding="utf-8")
    return workspace


def _run(command: list[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            command, cwd=cwd, check=True, capture_output=True, text=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        detail = ""
        if isinstance(exc, subprocess.CalledProcessError):
            detail = "\n".join(
                item.strip() for item in (exc.stdout or "", exc.stderr or "")
                if item.strip()
            )[-6000:]
        raise EditorialMotionRenderError(
            f"HyperFrames command failed: {' '.join(command)} {detail}",
        ) from exc


def _hyperframes_cli() -> list[str]:
    explicit = str(os.environ.get("HYPERFRAMES_CLI") or "").strip()
    if explicit:
        path = Path(explicit).expanduser().resolve()
        if not path.is_file():
            raise EditorialMotionRenderError("HYPERFRAMES_CLI does not name a file")
        node = shutil.which("node")
        if not node:
            raise EditorialMotionRenderError("node is required for HYPERFRAMES_CLI")
        return [node, str(path)]
    cache_root = Path.home() / ".npm/_npx"
    node = shutil.which("node")
    if node and cache_root.is_dir():
        for package in sorted(cache_root.glob("*/node_modules/hyperframes/package.json")):
            try:
                payload = json.loads(package.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            cli = package.parent / "bin/hyperframes.mjs"
            if payload.get("version") == HYPERFRAMES_VERSION and cli.is_file():
                return [node, str(cli)]
    npx = shutil.which("npx")
    if not npx:
        raise EditorialMotionRenderError("HyperFrames CLI is unavailable")
    return [npx, "--yes", f"hyperframes@{HYPERFRAMES_VERSION}"]


def _render_segment_plan(
    scenes: list[dict[str, Any]], *,
    max_duration_sec: float = DEFAULT_SEGMENT_MAX_DURATION_SEC,
) -> list[dict[str, Any]]:
    """Split contiguous scenes without cutting scenes or changing their duration."""

    if max_duration_sec <= 0:
        raise EditorialMotionRenderError("segment duration must be positive")
    groups: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    group_start = 0.0
    for scene in scenes:
        start = float(scene["start_sec"])
        end = float(scene["end_sec"])
        if current and end - group_start > max_duration_sec:
            groups.append(current)
            current = []
        if not current:
            group_start = start
        current.append(scene)
    if current:
        groups.append(current)

    plan: list[dict[str, Any]] = []
    for index, group in enumerate(groups, start=1):
        source_start = float(group[0]["start_sec"])
        source_end = float(group[-1]["end_sec"])
        duration = source_end - source_start
        if duration > max_duration_sec + 0.001:
            raise EditorialMotionRenderError(
                f"scene group {index} exceeds the {max_duration_sec:.3f}s render ceiling",
            )
        local_scenes: list[dict[str, Any]] = []
        for scene in group:
            local_start = float(scene["start_sec"]) - source_start
            local_end = float(scene["end_sec"]) - source_start
            local_scenes.append({
                **scene,
                "start_sec": round(local_start, 6),
                "end_sec": round(local_end, 6),
                "duration_sec": round(local_end - local_start, 6),
            })
        plan.append({
            "index": index,
            "source_start_sec": round(source_start, 6),
            "source_end_sec": round(source_end, 6),
            "duration_sec": round(duration, 6),
            "scene_ids": [str(scene["scene_id"]) for scene in group],
            "scenes": local_scenes,
        })
    return plan


def build_editorial_render_segment_plan(
    storyboard: dict[str, Any],
    artifact_root: Path,
    *,
    max_duration_sec: float = DEFAULT_SEGMENT_MAX_DURATION_SEC,
) -> dict[str, Any]:
    """Return the public path-free plan consumed by the GitHub render matrix."""

    scenes = preflight_editorial_motion_storyboard(
        storyboard,
        Path(artifact_root).resolve(),
    )
    segments = _render_segment_plan(scenes, max_duration_sec=max_duration_sec)
    return {
        "version": 2,
        "renderer": "hyperframes_segmented",
        "max_duration_sec": max_duration_sec,
        "timeline_duration_sec": float(storyboard["timeline_duration_sec"]),
        "segment_count": len(segments),
        "segments": [
            {key: value for key, value in segment.items() if key != "scenes"}
            for segment in segments
        ],
    }


def _probe_h264(path: Path, *, cwd: Path) -> dict[str, Any]:
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        raise EditorialMotionRenderError("ffprobe is required")
    probe = _run([
        ffprobe,
        "-v",
        "error",
        "-show_entries",
        "stream=codec_type,codec_name,width,height,avg_frame_rate:format=duration",
        "-of",
        "json",
        str(path),
    ], cwd=cwd)
    try:
        payload = json.loads(probe.stdout)
        stream = next(
            item for item in payload.get("streams") or []
            if item.get("codec_type") == "video"
        )
        duration = float((payload.get("format") or {}).get("duration") or 0)
    except (ValueError, StopIteration, json.JSONDecodeError) as exc:
        raise EditorialMotionRenderError("ffprobe could not verify editorial MP4") from exc
    if (
        stream.get("codec_name") != "h264"
        or [stream.get("width"), stream.get("height")]
        != [CANVAS_WIDTH, CANVAS_HEIGHT]
    ):
        raise EditorialMotionRenderError("editorial MP4 geometry or codec drifted")
    return {"stream": stream, "duration_sec": duration}


def render_editorial_motion_segment(
    storyboard: dict[str, Any],
    artifact_root: Path,
    segment_index: int,
    output: Path,
    *,
    max_duration_sec: float = DEFAULT_SEGMENT_MAX_DURATION_SEC,
) -> dict[str, Any]:
    """Render one bounded silent segment and discard its frame workspace."""

    root = Path(artifact_root).resolve()
    scenes = preflight_editorial_motion_storyboard(storyboard, root)
    segments = _render_segment_plan(scenes, max_duration_sec=max_duration_sec)
    if segment_index < 1 or segment_index > len(segments):
        raise EditorialMotionRenderError("segment index is outside the deterministic plan")
    segment = segments[segment_index - 1]
    output = Path(output).resolve()
    if output == root or root not in output.parents:
        raise EditorialMotionRenderError("segment output must remain under artifact_root")
    output.parent.mkdir(parents=True, exist_ok=True)
    cli = _hyperframes_cli()
    style_profile = str(storyboard["style_profile"])
    print(
        f"render segment {segment_index}/{len(segments)} "
        f"({segment['duration_sec']:.3f}s, {len(segment['scenes'])} scenes)",
        flush=True,
    )
    with tempfile.TemporaryDirectory(
        prefix=f".hf-segment-{segment_index:03d}-",
        dir=root,
    ) as temp:
        workspace = Path(temp) / "workspace"
        _write_workspace(
            segment["scenes"],
            root,
            root / "episode-script.json",
            float(segment["duration_sec"]),
            style_profile=style_profile,
            workspace_path=workspace,
        )
        check = _run([*cli, "check", "--json"], cwd=workspace)
        _run([
            *cli,
            "render",
            "--quality",
            "high",
            "--workers",
            "1",
            "--output",
            str(output),
        ], cwd=workspace)
        if not output.is_file() or output.stat().st_size <= 0:
            raise EditorialMotionRenderError("HyperFrames produced no segment MP4")
        probe = _probe_h264(output, cwd=workspace)
    if abs(float(probe["duration_sec"]) - float(segment["duration_sec"])) > 0.12:
        raise EditorialMotionRenderError("segment duration drifted")
    try:
        check_payload = json.loads(check.stdout or "{}")
    except json.JSONDecodeError:
        check_payload = {"raw": check.stdout[-2000:]}
    return {
        "version": 2,
        "status": "PASS",
        "segment_index": segment_index,
        "segment_count": len(segments),
        "segment_max_duration_sec": max_duration_sec,
        "source_start_sec": segment["source_start_sec"],
        "source_end_sec": segment["source_end_sec"],
        "duration_sec": round(float(probe["duration_sec"]), 3),
        "scene_ids": segment["scene_ids"],
        "output": output.name,
        "output_sha256": _sha256(output),
        "output_bytes": output.stat().st_size,
        "hyperframes_check_passed": True,
        "hyperframes_check": check_payload,
        "temporary_workspace_removed": True,
        "provider_calls": 0,
        "youtube_called": False,
    }


def assemble_editorial_motion_segments(
    storyboard: dict[str, Any],
    artifact_root: Path,
    segment_paths: list[Path],
    output: Path,
    *,
    audio: Path,
    max_duration_sec: float = DEFAULT_SEGMENT_MAX_DURATION_SEC,
) -> dict[str, Any]:
    """Concatenate verified silent segments and mux the existing narration."""

    root = Path(artifact_root).resolve()
    scenes = preflight_editorial_motion_storyboard(storyboard, root)
    plan = _render_segment_plan(scenes, max_duration_sec=max_duration_sec)
    if len(segment_paths) != len(plan):
        raise EditorialMotionRenderError(
            "segment file count does not match deterministic plan",
        )
    verified_paths: list[Path] = []
    segment_reports: list[dict[str, Any]] = []
    for segment, raw_path in zip(plan, segment_paths, strict=True):
        path = _under_root(raw_path, root, label="editorial segment")
        probe = _probe_h264(path, cwd=root)
        if abs(float(probe["duration_sec"]) - float(segment["duration_sec"])) > 0.12:
            raise EditorialMotionRenderError(
                "segment duration does not match deterministic plan",
            )
        verified_paths.append(path)
        segment_reports.append({
            "index": segment["index"],
            "duration_sec": round(float(probe["duration_sec"]), 3),
            "sha256": _sha256(path),
            "bytes": path.stat().st_size,
        })

    audio_path = _under_root(audio, root, label="editorial narration audio")
    output = Path(output).resolve()
    if output == root or root not in output.parents:
        raise EditorialMotionRenderError("editorial output must remain under artifact_root")
    output.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise EditorialMotionRenderError("ffmpeg is required for segment assembly")
    with tempfile.TemporaryDirectory(prefix=".hf-assembly-", dir=root) as temp:
        temp_root = Path(temp)
        concat_list = temp_root / "segments.txt"
        concat_lines = []
        for path in verified_paths:
            escaped = str(path).replace("'", "'\\''")
            concat_lines.append("file '" + escaped + "'\n")
        concat_list.write_text(
            "".join(concat_lines),
            encoding="utf-8",
        )
        silent_output = temp_root / "joined-silent.mp4"
        muxed_output = temp_root / "joined-with-audio.mp4"
        _run([
            ffmpeg,
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_list),
            "-c",
            "copy",
            "-movflags",
            "+faststart",
            str(silent_output),
        ], cwd=temp_root)
        _run([
            ffmpeg,
            "-y",
            "-i",
            str(silent_output),
            "-i",
            str(audio_path),
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-shortest",
            "-movflags",
            "+faststart",
            str(muxed_output),
        ], cwd=temp_root)
        caption_path = write_caption_srt(
            storyboard["caption_track"],
            root / "editorial-motion-captions.srt",
        )
        caption_ass_path = write_caption_ass(
            storyboard["caption_track"],
            root / "editorial-motion-captions.ass",
        )
        burn_captions(muxed_output, caption_ass_path, output)
    if not output.is_file() or output.stat().st_size <= 0:
        raise EditorialMotionRenderError("segment assembly produced no MP4")
    probe = _probe_h264(output, cwd=root)
    expected_duration = float(storyboard["timeline_duration_sec"])
    if abs(float(probe["duration_sec"]) - expected_duration) > 0.35:
        raise EditorialMotionRenderError("assembled MP4 duration drifted")
    return {
        "version": 3,
        "status": "PASS",
        "visual_mode": EDITORIAL_MOTION_MODE,
        "style_profile": str(storyboard["style_profile"]),
        "renderer": "hyperframes_segmented",
        "hyperframes_version": HYPERFRAMES_VERSION,
        "publication_authorized": False,
        "output_sha256": _sha256(output),
        "video_codec": "h264",
        "resolution": [CANVAS_WIDTH, CANVAS_HEIGHT],
        "fps": CANVAS_FPS,
        "duration_sec": round(float(probe["duration_sec"]), 3),
        "scene_count": len(scenes),
        "segment_count": len(plan),
        "segments": segment_reports,
        "segment_max_duration_sec": max_duration_sec,
        "temporary_frame_workspaces_removed": True,
        "caption_srt": str(caption_path),
        "caption_srt_sha256": _sha256(caption_path),
        "caption_ass": str(caption_ass_path),
        "caption_ass_sha256": _sha256(caption_ass_path),
        "captions_burned": True,
        "audio_sha256": _sha256(audio_path),
        "audio_mux": "ffmpeg_concat_then_post_render_mux_and_caption_burn",
        "motion_plan_sha256": storyboard["motion_plan_sha256"],
        "caption_track_sha256": storyboard["caption_track_sha256"],
        "module_usage": storyboard["motion_plan"]["module_usage"],
        "asset_pack_count": len({scene["asset_family_id"] for scene in scenes}),
        "background_video_used": False,
        "factual_text_rendering": "html_svg_only",
        "provider_calls": 0,
        "youtube_called": False,
    }


def render_editorial_motion_compilation(
    storyboard: dict[str, Any],
    artifact_root: Path,
    output: Path,
    *,
    audio: Path | None = None,
) -> dict[str, Any]:
    root = Path(artifact_root).resolve()
    scenes = preflight_editorial_motion_storyboard(storyboard, root)
    if audio is None:
        raise EditorialMotionRenderError("editorial motion requires final narration audio")
    audio_path = _under_root(audio, root, label="editorial narration audio")
    duration = float(storyboard["timeline_duration_sec"])
    output = Path(output).resolve()
    if output == root or root not in output.parents:
        raise EditorialMotionRenderError("editorial output must remain under artifact_root")
    output.parent.mkdir(parents=True, exist_ok=True)
    style_profile = str(storyboard["style_profile"])
    workspace = _write_workspace(scenes, root, audio_path, duration, style_profile=style_profile)
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        raise EditorialMotionRenderError("ffprobe is required")
    cli = _hyperframes_cli()
    check = _run([*cli, "check", "--json"], cwd=workspace)
    silent_output = output.with_name(f"{output.stem}-hyperframes-silent.mp4")
    _run(
        [*cli, "render", "--quality", "high", "--output", str(silent_output)],
        cwd=workspace,
    )
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise EditorialMotionRenderError("ffmpeg is required for narration mux")
    muxed_output = output.with_name(f"{output.stem}-with-audio.mp4")
    _run([
        ffmpeg, "-y", "-i", str(silent_output), "-i", str(audio_path),
        "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-c:a", "aac",
        "-b:a", "192k", "-shortest", "-movflags", "+faststart", str(muxed_output),
    ], cwd=workspace)
    caption_path = write_caption_srt(
        storyboard["caption_track"], root / "editorial-motion-captions.srt",
    )
    caption_ass_path = write_caption_ass(
        storyboard["caption_track"], root / "editorial-motion-captions.ass",
    )
    burn_captions(muxed_output, caption_ass_path, output)
    if not output.is_file() or output.stat().st_size <= 0:
        raise EditorialMotionRenderError("HyperFrames produced no MP4")
    probe = _run([
        ffprobe, "-v", "error", "-show_entries",
        "stream=codec_name,width,height,avg_frame_rate:format=duration",
        "-of", "json", str(output),
    ], cwd=workspace)
    try:
        probe_payload = json.loads(probe.stdout)
        video_stream = next(
            item for item in probe_payload.get("streams") or []
            if item.get("codec_name")
        )
        rendered_duration = float((probe_payload.get("format") or {}).get("duration") or 0)
    except (ValueError, StopIteration, json.JSONDecodeError) as exc:
        raise EditorialMotionRenderError("ffprobe could not verify editorial MP4") from exc
    if (
        video_stream.get("codec_name") != "h264"
        or [video_stream.get("width"), video_stream.get("height")]
        != [CANVAS_WIDTH, CANVAS_HEIGHT]
        or abs(rendered_duration - duration) > 0.35
    ):
        raise EditorialMotionRenderError("editorial MP4 geometry, codec, or duration drifted")

    try:
        check_payload = json.loads(check.stdout or "{}")
    except json.JSONDecodeError:
        check_payload = {"raw": check.stdout[-2000:]}
    return {
        "version": 1,
        "status": "PASS",
        "visual_mode": EDITORIAL_MOTION_MODE,
        "style_profile": style_profile,
        "renderer": "hyperframes",
        "hyperframes_version": HYPERFRAMES_VERSION,
        "hyperframes_check_passed": True,
        "hyperframes_check": check_payload,
        "publication_authorized": False,
        "output_sha256": _sha256(output),
        "video_codec": "h264",
        "resolution": [CANVAS_WIDTH, CANVAS_HEIGHT],
        "fps": CANVAS_FPS,
        "duration_sec": round(rendered_duration, 3),
        "scene_count": len(scenes),
        "module_usage": storyboard["motion_plan"]["module_usage"],
        "motion_plan_sha256": storyboard["motion_plan_sha256"],
        "caption_track_sha256": storyboard["caption_track_sha256"],
        "caption_srt": str(caption_path),
        "caption_srt_sha256": _sha256(caption_path),
        "caption_ass": str(caption_ass_path),
        "caption_ass_sha256": _sha256(caption_ass_path),
        "captions_burned": True,
        "audio_sha256": _sha256(audio_path),
        "audio_mux": "ffmpeg_post_render_then_caption_burn",
        "silent_hyperframes_output_sha256": _sha256(silent_output),
        "background_video_used": False,
        "factual_text_rendering": "html_svg_only",
        "asset_pack_count": len({scene["asset_family_id"] for scene in scenes}),
        "workspace": str(workspace),
    }
