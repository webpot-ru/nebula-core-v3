"""Approved Chrome/HyperFrames renderer facade for acc1 webtoon v2.

The underlying editorial renderer owns deterministic browser capture.  This
facade adds the approved production contract: meaning-led scene selection,
motion variation, and an explicit renderer identity in the review report.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from compilation_editorial_motion_renderer import (
    EditorialMotionRenderError,
    preflight_editorial_motion_storyboard,
    render_editorial_motion_compilation,
)
from acc1_visual_contract import (
    CINEMATIC_INK_WEBTOON_STYLE_PROFILE,
    FORMAT_VISUAL_SYSTEM_V3_STYLE_PROFILE,
)


RENDERER_ID = "chrome_guided_webtoon_v2"


class ChromeGuidedWebtoonRenderError(RuntimeError):
    """Raised when a storyboard cannot satisfy the approved camera contract."""


def _semantic_camera_plan(storyboard: dict[str, Any], artifact_root: Path) -> list[dict[str, Any]]:
    scenes = preflight_editorial_motion_storyboard(storyboard, artifact_root)
    style_profile = str(storyboard.get("style_profile") or "")
    if style_profile not in {
        CINEMATIC_INK_WEBTOON_STYLE_PROFILE,
        FORMAT_VISUAL_SYSTEM_V3_STYLE_PROFILE,
    }:
        raise ChromeGuidedWebtoonRenderError(
            "chrome guided webtoon v2 requires an approved webtoon style profile",
        )
    if style_profile == FORMAT_VISUAL_SYSTEM_V3_STYLE_PROFILE:
        signatures = {
            tuple(
                str(beat.get("panel_id") or "overview")
                for beat in scene.get("camera_path") or []
            )
            for scene in scenes
        }
        if len(scenes) > 1 and len(signatures) < 2:
            raise ChromeGuidedWebtoonRenderError(
                "webtoon v3 requires varied source-bound panel paths",
            )
    else:
        modules = [str((scene.get("motion") or {}).get("module") or "") for scene in scenes]
        if len(set(modules)) < 2:
            raise ChromeGuidedWebtoonRenderError(
                "webtoon v2 requires varied meaning-led camera modules",
            )
    return [
        {
            "scene_id": scene["scene_id"],
            "narration_text": scene["narration_text"],
            "focus": (
                scene.get("semantic_focus")
                if style_profile == FORMAT_VISUAL_SYSTEM_V3_STYLE_PROFILE
                else (scene.get("motion") or {}).get("module")
            ),
            "page_layout": scene.get("page_layout"),
            "panel_regions": scene.get("panel_regions") or [],
            "camera_beats": (
                scene.get("camera_path")
                if style_profile == FORMAT_VISUAL_SYSTEM_V3_STYLE_PROFILE
                else [
                    "hero_page_overview",
                    "hero_narration_selected_region",
                    "detail_page_crossfade",
                    "detail_narration_selected_region",
                ]
            ),
            "mandatory_pull_back": False,
            "rebuild_page_as_collage": False,
            "start_sec": scene["start_sec"],
            "end_sec": scene["end_sec"],
        }
        for scene in scenes
    ]


def render_chrome_guided_webtoon(
    storyboard: dict[str, Any],
    artifact_root: Path,
    output: Path,
    *,
    audio: Path | None = None,
) -> dict[str, Any]:
    """Render the approved webtoon in Chromium with semantic camera choices."""

    root = Path(artifact_root).resolve()
    semantic_plan = _semantic_camera_plan(storyboard, root)
    try:
        report = render_editorial_motion_compilation(
            storyboard, root, output, audio=audio,
        )
    except EditorialMotionRenderError as exc:
        raise ChromeGuidedWebtoonRenderError(str(exc)) from exc
    return {
        **report,
        "renderer": RENDERER_ID,
        "camera_policy": "meaning_led_guided_reading",
        "semantic_camera_plan": semantic_plan,
        "fixed_subtitle_band": {
            "y": 950,
            "height": 130,
            "line_count": 1,
        },
    }
