"""Source-bound scene-image plan for acc1 SAGA/BUNDLE/THREAD episodes."""

from __future__ import annotations

import copy
import hashlib
import math
import re
import shutil
from pathlib import Path
from typing import Any, Callable

from PIL import Image, ImageOps, UnidentifiedImageError

from acc1_visual_contract import (
    ADULT_ANIMATION_SERIES,
    CINEMATIC_INK_WEBTOON_STYLE_PROFILE,
    CINEMATIC_STORY_MODE,
    EDITORIAL_MOTION_ASSETS_PER_PACK,
    EDITORIAL_MOTION_MAX_PACKS,
    EDITORIAL_MOTION_MODE,
    EDITORIAL_MOTION_MODULES,
    EDITORIAL_MOTION_STYLE_PROFILE,
    EDITORIAL_MOTION_STYLE_PROFILES,
    FORMAT_VISUAL_SYSTEM_V3_STYLE_PROFILE,
    INK_GOUACHE_STORY_PAGES_STYLE_PROFILE,
    INK_GOUACHE_STORY_FAMILIES,
    INK_GOUACHE_PAGE_LAYOUTS,
    is_adult_animation_style_profile,
    resolve_visual_mode,
    select_format_visual_system_v3_panel_grammar,
    select_adult_animation_layouts,
)
from vectorengine_client import DEFAULT_IMAGE_MODEL, call_image_generation


Generator = Callable[..., Path]
SIZE = "1536x864"
STYLE = (
    "cinematic editorial illustration for a Russian Reddit storytelling video, "
    "realistic textured lighting, one clear focal event, restrained dark copper and teal palette, "
    "16:9, no text, no letters, no UI, no logo, no watermark, no gore, "
    "leave the rightmost forty percent calm because the copper cat mascot remains visible there"
)
CINEMATIC_STYLE = (
    "cinematic editorial illustration for a Russian Reddit storytelling video, "
    "realistic textured lighting, one clear focal event, restrained dark copper and teal palette, "
    "full-screen 16:9 composition, no text, no letters, no UI, no logo, no watermark, no gore, "
    "keep the important subject and source-supported action inside the central safe area so a "
    "subtle camera push and pan can crop every edge without losing the focal event"
)
EDITORIAL_MOTION_STYLE = (
    "premium contemporary cut-up editorial collage for a source-bound Russian storytelling film, "
    "photographic realism integrated directly into torn tactile paper, restrained surreal scale, "
    "cobalt blue, warm coral, butter yellow, cream and deep ink, cinematic but bright magazine light, "
    "full-screen 16:9, no frames, no dossier, no newspaper, no corkboard, no red string, no scrapbook, "
    "no text, no letters, no numbers, no UI, no logo, no watermark, no gore. Create one continuous "
    "composition rather than a card layout: foreground edge, human or object anchor, portal-shaped "
    "detail and background must overlap at different depths so deterministic HTML can travel through "
    "them. Preserve broad safe margins and one clear visual route through the source-supported moment"
)
INK_GOUACHE_STORY_PAGES_STYLE = (
    "adult ink and gouache reportage illustration for a source-bound Russian storytelling film, "
    "observational human figures with expressive but believable anatomy, rich matte watercolor washes, "
    "visible charcoal and ink linework, dry-brush shadow, opaque gouache and tactile uncoated paper; "
    "modern literary graphic-novel energy, "
    "not childish and not pop-art. Use one to five asymmetrical editorial panels of different shapes "
    "and scales inside a continuous full-screen 16:9 composition: a dominant scene panel, a small "
    "detail panel, and negative paper space. No photoreal people, no comic speech balloons, no halftone "
    "superhero style, no neon, no generic scrapbook, no dossier board, no newspaper columns, no text, "
    "no letters, no numbers, no UI, no logo, no watermark, no gore. Preserve broad safe margins and "
    "clear layers for deterministic HTML camera motion"
)
CINEMATIC_INK_WEBTOON_STYLE = (
    "premium adult cinematic ink webtoon for a source-bound Russian storytelling film, "
    "believable contemporary adults, expressive restrained acting, confident ink contours, "
    "matte gouache color, dry-brush shadows and tactile uncoated paper; sophisticated editorial "
    "graphic-novel staging for Gen Z and adult viewers, never childish, never superhero pop-art. "
    "Use one to three unequal panels inside a continuous full-screen 16:9 page, with one dominant "
    "emotional scene and smaller object or evidence details. No speech balloons, no generated text, "
    "no letters, no numbers, no UI, no logo, no watermark, no gore. Preserve safe margins and clear "
    "depth layers for page overview, guided panel push-in and pull-back camera motion"
)
FORMAT_VISUAL_SYSTEM_V3_STYLE = (
    "one complete premium adult hand-drawn graphic-novel page for a source-bound Russian "
    "long-form story video; believable adult anatomy and mature expressive faces, elegant "
    "variable ink contours, restrained cel shading, subtle matte gouache and tactile paper grain, "
    "cream gutters, unequal panels and one dominant emotional image. Fully illustrated art only: "
    "never photography, photomontage, photorealistic reconstruction, stock-video imitation, glossy "
    "romance manhwa, black-and-white manga, superhero pop art or childlike cartooning. Do not use an "
    "orange-dominated universal palette. No speech balloons, generated captions, paragraphs, letters, "
    "numbers, UI, logo, signature, watermark or gore. Keep faces, hands and evidence above the quiet "
    "bottom subtitle area, and compose every important beat for a full-page establish followed by a "
    "meaning-led guided crop"
)
FORMAT_VISUAL_SYSTEM_V3_FORMAT_DIRECTIONS = {
    "BUNDLE": (
        "BUNDLE grammar: this story is a separate mini-comic inside a multi-story episode. Give it a "
        "distinct cast, location, supporting accent colour and panel rhythm that do not leak into any "
        "other story. Establish the whole page before guiding attention to the narrated beat"
    ),
    "SAGA": (
        "SAGA grammar: one continuous cast, wardrobe and environment system spans the episode. Prefer "
        "a panoramic establishing image with smaller discovery, message, decision or payoff panels and "
        "clear foreground, character and background planes for restrained 2.5D parallax"
    ),
    "THREAD": (
        "THREAD grammar: preserve the prompt as the visual anchor and make this response a materially "
        "different portrait or compact situational vignette in a zigzag reading flow. Change character, "
        "pose, environment fragment and emotional role; never reuse one universal reaction card"
    ),
}
FORMAT_VISUAL_SYSTEM_V3_PILLAR_DIRECTIONS = {
    "relationships": (
        "relationships and family treatment: ivory, muted olive, dusty rose, burgundy and deep navy; "
        "intimate contemporary interiors and expressive close-ups"
    ),
    "work": (
        "work, money and justice treatment: graphite, cold blue, paper ivory and restrained red; "
        "specific workplaces, tools and documents with textured graphic realism"
    ),
    "confessions": (
        "confessions, awkward and taboo treatment: plum, dusty pink, cool lavender and desaturated teal; "
        "faces, hands, phones and generous negative space"
    ),
    "professions": (
        "professions and human-experience treatment: teal, cobalt, off-white and restrained muted yellow; "
        "observational environmental and tool detail"
    ),
    "strange": (
        "strange, dark and unexplained treatment: indigo, green-black, dirty ivory, steel blue and tiny "
        "dim brass accents; cinematic cel shading with limited neo-noir only at narrative peaks"
    ),
}
INK_GOUACHE_FAMILY_DIRECTIONS = {
    "relationships": (
        "relationship-family palette only: terracotta, deep indigo, tobacco brown and warm lamp amber; "
        "one dominant emotional frame with smaller message and object fragments"
    ),
    "work": (
        "work-family palette only: desaturated office green, paper cream and charcoal black; narrow "
        "vertical routine panels contrasted with one wide release frame; no blue, coral or mustard planes"
    ),
    "digital": (
        "digital-family palette only: electric cobalt-blue, carbon black, cold white and one sparse "
        "acid-lime accent; phone or interface space dominates with small inset traces"
    ),
    "memory": (
        "memory-family palette only: faded peach, dusty teal and warm paper; scattered unequal fragments "
        "orbit one central recollection"
    ),
    "odd_job": (
        "odd-job-family palette only: sodium orange, deep cobalt and off-white; two cinematic wides and "
        "one small symbolic detail"
    ),
    "dark_saga": (
        "dark-saga-family palette only: midnight blue-black, dirty ivory and restrained burgundy; one "
        "atmospheric large scene cut by narrow evidence slits"
    ),
}
EDITORIAL_LAYER_ROLES = ("hero_plate", "detail_plate")


class EpisodeImageError(RuntimeError):
    """Raised when visuals would exceed spend or source-integrity contracts."""


def _safe_filename_token(value: str) -> str:
    raw = str(value or "").strip()
    if re.fullmatch(r"[A-Za-z0-9_-]{1,80}", raw):
        return raw
    normalized = re.sub(r"[^A-Za-z0-9_-]+", "-", raw).strip("-_")[:48] or "source"
    suffix = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:10]
    return f"{normalized}-{suffix}"


def _expected_dimensions(size: str) -> tuple[int, int]:
    match = re.fullmatch(r"([1-9][0-9]{1,4})x([1-9][0-9]{1,4})", str(size or ""))
    if not match:
        raise EpisodeImageError("image size must use the exact WIDTHxHEIGHT form")
    return int(match.group(1)), int(match.group(2))


def _validate_generated_image(path: Path, *, expected_size: tuple[int, int]) -> None:
    try:
        with Image.open(path) as image:
            actual_size = image.size
            actual_format = image.format
            image.verify()
        with Image.open(path) as image:
            image.load()
    except (OSError, UnidentifiedImageError) as exc:
        raise EpisodeImageError(
            f"image provider returned an undecodable file: {path.name}"
        ) from exc
    if actual_format not in {"PNG", "JPEG", "WEBP"}:
        raise EpisodeImageError(
            f"image provider returned unsupported format {actual_format or '(unknown)'}"
        )
    if actual_size != expected_size:
        raise EpisodeImageError(
            "image provider returned wrong dimensions: "
            f"expected {expected_size[0]}x{expected_size[1]}, "
            f"got {actual_size[0]}x{actual_size[1]}"
        )


def _normalize_editorial_image(
    path: Path,
    *,
    expected_size: tuple[int, int],
) -> dict[str, Any] | None:
    """Preserve and normalize a near-16:9 editorial provider response."""

    try:
        with Image.open(path) as image:
            actual_size = image.size
            actual_format = image.format
            image.load()
    except (OSError, UnidentifiedImageError) as exc:
        raise EpisodeImageError(
            f"image provider returned an undecodable file: {path.name}"
        ) from exc
    if actual_size == expected_size:
        return None
    if actual_format not in {"PNG", "JPEG", "WEBP"}:
        raise EpisodeImageError(
            f"image provider returned unsupported format {actual_format or '(unknown)'}"
        )
    expected_ratio = expected_size[0] / expected_size[1]
    actual_ratio = actual_size[0] / actual_size[1]
    if (
        actual_size[0] < expected_size[0]
        or actual_size[1] < expected_size[1]
        or abs(actual_ratio - expected_ratio) / expected_ratio > 0.02
    ):
        raise EpisodeImageError(
            "editorial image cannot be normalized without unsafe crop: "
            f"expected near {expected_size[0]}x{expected_size[1]}, "
            f"got {actual_size[0]}x{actual_size[1]}"
        )
    original = path.with_name(f"{path.stem}.provider-original{path.suffix.lower()}")
    if original.exists():
        raise EpisodeImageError(f"provider original already exists: {original.name}")
    shutil.copy2(path, original)
    original_sha256 = hashlib.sha256(original.read_bytes()).hexdigest()
    with Image.open(original) as image:
        normalized = ImageOps.fit(
            image.convert("RGB"), expected_size, method=Image.Resampling.LANCZOS,
        )
        normalized.save(path, format="PNG", optimize=True)
    return {
        "method": "center_crop_lanczos",
        "provider_original_path": original.name,
        "provider_original_sha256": original_sha256,
        "provider_original_dimensions": list(actual_size),
        "normalized_dimensions": list(expected_size),
    }


def _sentences(value: str) -> list[str]:
    return [item.strip() for item in re.split(r"(?<=[.!?…])\s+|\n+", value) if item.strip()]


def _scene_excerpt(story: dict[str, Any], index: int, count: int) -> str:
    narration = str(story.get("narration_ru") or "").strip()
    sentences = _sentences(narration)
    if not sentences:
        raise EpisodeImageError("scene imagery requires non-empty accepted narration")
    anchor = min(len(sentences) - 1, round((index - 0.5) * len(sentences) / count - 0.5))
    excerpt = sentences[anchor]
    if len(excerpt) < 100 and anchor + 1 < len(sentences):
        excerpt = f"{excerpt} {sentences[anchor + 1]}"
    return excerpt[:700]


def _editorial_pack_allocations(stories: list[dict[str, Any]]) -> dict[int, int]:
    """Allocate packs while respecting the canonical image-call ceiling."""

    explicit_targets = [story.get("image_target") for story in stories]
    if any(target is not None for target in explicit_targets):
        if not all(
            isinstance(target, int) and not isinstance(target, bool) and target >= 2
            and target % EDITORIAL_MOTION_ASSETS_PER_PACK == 0
            for target in explicit_targets
        ):
            raise EpisodeImageError(
                "explicit image_target must be an even positive integer for every story",
            )
        allocations = {
            index: target // EDITORIAL_MOTION_ASSETS_PER_PACK
            for index, target in enumerate(explicit_targets)
        }
        if sum(allocations.values()) > EDITORIAL_MOTION_MAX_PACKS:
            raise EpisodeImageError("explicit image targets exceed the image-call ceiling")
        return allocations

    allocations: dict[int, int] = {}
    for index, story in enumerate(stories):
        words = len(str(story.get("narration_ru") or "").split())
        allocations[index] = max(2, math.ceil(words / 78))
    if len(allocations) * 2 > EDITORIAL_MOTION_MAX_PACKS:
        raise EpisodeImageError("too many stories for bounded editorial asset packs")
    while sum(allocations.values()) > EDITORIAL_MOTION_MAX_PACKS:
        candidate = max(allocations, key=lambda item: (allocations[item], -item))
        if allocations[candidate] <= 2:
            raise EpisodeImageError("editorial asset packs cannot fit the image-call ceiling")
        allocations[candidate] -= 1
    return allocations


def _editorial_motion_module(excerpt: str, pack_index: int, pack_count: int) -> str:
    lowered = excerpt.casefold()
    if any(token in lowered for token in ("сообщен", "телефон", "написал", "переписк")):
        return "digital_memory_stack"
    if any(token in lowered for token in ("дата", "час", "день", "недел", "месяц", "потом")):
        return "graphic_timeline"
    if any(token in lowered for token in ("документ", "письмо", "ключ", "чек", "камера", "запись")):
        return "evidence_transform"
    if pack_index == pack_count:
        return "dark_semantic_reveal"
    if pack_index > 1 and pack_index % 6 == 0:
        return "nested_collage_zoom"
    return EDITORIAL_MOTION_MODULES[(pack_index - 1) % 3]


def _v3_pillar(script: dict[str, Any]) -> str:
    raw = str(script.get("pillar") or "").casefold()
    for key in FORMAT_VISUAL_SYSTEM_V3_PILLAR_DIRECTIONS:
        if key in raw:
            return key
    if any(token in raw for token in ("family", "relationship")):
        return "relationships"
    if any(token in raw for token in ("money", "justice", "career")):
        return "work"
    if any(token in raw for token in ("awkward", "taboo", "confession")):
        return "confessions"
    if any(token in raw for token in ("profession", "human")):
        return "professions"
    if any(token in raw for token in ("dark", "unexplained", "strange")):
        return "strange"
    return "relationships"


def _v3_layout(format_id: str, scene_index: int) -> str:
    layouts = {
        "BUNDLE": ("bundle_story_opener", "bundle_guided_page"),
        "SAGA": ("saga_panorama", "saga_discovery_panels"),
        "THREAD": ("thread_prompt_anchor", "thread_response_vignette"),
    }[format_id]
    return layouts[(scene_index - 1) % len(layouts)]


def image_plan(
    script: dict[str, Any], *, visual_mode: str | None = None,
    style_profile: str | None = None,
) -> list[dict[str, Any]]:
    """Plan the smallest useful visual set without calling an image provider."""
    try:
        mode = resolve_visual_mode(
            visual_mode if visual_mode is not None else script.get("visual_mode"),
        )
    except ValueError as exc:
        raise EpisodeImageError(str(exc)) from exc
    stories = script.get("stories")
    if not isinstance(stories, list) or not stories:
        raise EpisodeImageError("episode script must contain stories")
    format_id = str(script.get("episode_format") or "").upper()
    active_style_profile = str(
        style_profile or script.get("style_profile") or EDITORIAL_MOTION_STYLE_PROFILE,
    ).strip()
    if mode == EDITORIAL_MOTION_MODE and active_style_profile not in EDITORIAL_MOTION_STYLE_PROFILES:
        raise EpisodeImageError("unsupported editorial motion style profile")
    if mode == EDITORIAL_MOTION_MODE:
        if format_id == "THREAD" and active_style_profile != FORMAT_VISUAL_SYSTEM_V3_STYLE_PROFILE:
            raise EpisodeImageError(
                "editorial_motion_v1 supports SAGA/BUNDLE; THREAD needs its hybrid contract",
            )
        if format_id == "THREAD":
            allocations = {index: 1 for index in range(len(stories))}
            if sum(allocations.values()) > EDITORIAL_MOTION_MAX_PACKS:
                raise EpisodeImageError("THREAD responses exceed the image-call ceiling")
        else:
            allocations = _editorial_pack_allocations(stories)
    elif format_id == "SAGA":
        allocations = {0: 5}
    elif format_id == "BUNDLE":
        allocations = {index: 3 for index in range(len(stories))}
    elif format_id == "THREAD":
        # The prompt gets three mood changes; comment cards remain visually
        # stable so rapid response changes do not become distracting slideshow.
        allocations = {0: 3}
    else:
        raise EpisodeImageError("episode_format must be SAGA, BUNDLE, or THREAD")

    plan: list[dict[str, Any]] = []
    for story_index, scene_count in allocations.items():
        story = stories[story_index]
        if not isinstance(story, dict):
            raise EpisodeImageError(f"stories[{story_index}] must be an object")
        snapshot = story.get("source_snapshot")
        if not isinstance(snapshot, dict):
            raise EpisodeImageError(f"stories[{story_index}].source_snapshot is required")
        source_id = str(snapshot.get("source_id") or snapshot.get("post_id") or "").strip()
        if not source_id:
            raise EpisodeImageError(f"stories[{story_index}] has no source id")
        editorial_modules = story.get("editorial_motion_modules")
        if mode == EDITORIAL_MOTION_MODE and editorial_modules is not None and (
            not isinstance(editorial_modules, list)
            or len(editorial_modules) != scene_count
            or any(str(item) not in EDITORIAL_MOTION_MODULES for item in editorial_modules)
        ):
            raise EpisodeImageError(
                f"stories[{story_index}].editorial_motion_modules must match its pack count",
            )
        editorial_families = story.get("editorial_motion_families")
        editorial_layouts = story.get("editorial_page_layouts")
        editorial_panel_grammars = story.get("editorial_panel_grammars")
        visual_identity_contract = " ".join(
            str(story.get("visual_identity_contract") or "").split(),
        )
        if mode == EDITORIAL_MOTION_MODE and active_style_profile == FORMAT_VISUAL_SYSTEM_V3_STYLE_PROFILE:
            if len(visual_identity_contract) < 40:
                raise EpisodeImageError(
                    f"stories[{story_index}].visual_identity_contract is required for v3 continuity",
                )
            story_family = _v3_pillar(script)
            if editorial_families is None:
                editorial_families = [story_family] * scene_count
            if editorial_layouts is None:
                editorial_layouts = [
                    _v3_layout(format_id, scene_index)
                    for scene_index in range(1, scene_count + 1)
                ]
            expected_panel_grammars = [
                select_format_visual_system_v3_panel_grammar(
                    format_id, scene_index, scene_count,
                )["id"]
                for scene_index in range(1, scene_count + 1)
            ]
            if editorial_panel_grammars is None:
                editorial_panel_grammars = expected_panel_grammars
            elif (
                not isinstance(editorial_panel_grammars, list)
                or [str(item) for item in editorial_panel_grammars] != expected_panel_grammars
            ):
                raise EpisodeImageError(
                    f"stories[{story_index}].editorial_panel_grammars must follow the v3 meaning-led rhythm",
                )
            if (
                not isinstance(editorial_families, list)
                or len(editorial_families) != scene_count
                or any(str(item) not in FORMAT_VISUAL_SYSTEM_V3_PILLAR_DIRECTIONS for item in editorial_families)
            ):
                raise EpisodeImageError(
                    f"stories[{story_index}].editorial_motion_families must match v3 packs",
                )
            if (
                not isinstance(editorial_layouts, list)
                or len(editorial_layouts) != scene_count
                or any(str(item) not in INK_GOUACHE_PAGE_LAYOUTS for item in editorial_layouts)
            ):
                raise EpisodeImageError(
                    f"stories[{story_index}].editorial_page_layouts must match v3 packs",
                )
        if mode == EDITORIAL_MOTION_MODE and active_style_profile in {
            INK_GOUACHE_STORY_PAGES_STYLE_PROFILE,
            CINEMATIC_INK_WEBTOON_STYLE_PROFILE,
        }:
            if len(visual_identity_contract) < 80:
                raise EpisodeImageError(
                    f"stories[{story_index}].visual_identity_contract is required for episode continuity",
                )
            if (
                not isinstance(editorial_families, list)
                or len(editorial_families) != scene_count
                or any(str(item) not in INK_GOUACHE_STORY_FAMILIES for item in editorial_families)
            ):
                raise EpisodeImageError(
                    f"stories[{story_index}].editorial_motion_families must match its pack count",
                )
            if (
                not isinstance(editorial_layouts, list)
                or len(editorial_layouts) != scene_count
                or any(str(item) not in INK_GOUACHE_PAGE_LAYOUTS for item in editorial_layouts)
            ):
                raise EpisodeImageError(
                    f"stories[{story_index}].editorial_page_layouts must match its pack count",
                )
        elif mode == EDITORIAL_MOTION_MODE and is_adult_animation_style_profile(active_style_profile):
            if len(visual_identity_contract) < 80:
                raise EpisodeImageError(
                    f"stories[{story_index}].visual_identity_contract is required for episode continuity",
                )
            series = ADULT_ANIMATION_SERIES[active_style_profile]
            if editorial_families is not None and (
                not isinstance(editorial_families, list)
                or len(editorial_families) != scene_count
                or any(str(item) != series["story_family"] for item in editorial_families)
            ):
                raise EpisodeImageError(
                    f"stories[{story_index}].editorial_motion_families must use the active adult-animation series",
                )
            if editorial_layouts is not None and (
                not isinstance(editorial_layouts, list)
                or len(editorial_layouts) != scene_count
                or len(set(str(item) for item in editorial_layouts)) != scene_count
                or any(str(item) not in series["layouts"] for item in editorial_layouts)
            ):
                raise EpisodeImageError(
                    f"stories[{story_index}].editorial_page_layouts must be unique approved adult-animation layouts",
                )
            if editorial_layouts is None:
                editorial_layouts = list(select_adult_animation_layouts(
                    active_style_profile, source_id, scene_count,
                ))
            if editorial_families is None:
                editorial_families = [str(series["story_family"])] * scene_count
        for scene_index in range(1, scene_count + 1):
            excerpt = _scene_excerpt(story, scene_index, scene_count)
            if mode == EDITORIAL_MOTION_MODE:
                module = (
                    str(editorial_modules[scene_index - 1])
                    if editorial_modules is not None
                    else _editorial_motion_module(excerpt, scene_index, scene_count)
                )
                family_id = f"story-{story_index + 1:02d}-pack-{scene_index:03d}"
                story_family = (
                    str(editorial_families[scene_index - 1])
                    if (
                        active_style_profile in {
                            INK_GOUACHE_STORY_PAGES_STYLE_PROFILE,
                            CINEMATIC_INK_WEBTOON_STYLE_PROFILE,
                            FORMAT_VISUAL_SYSTEM_V3_STYLE_PROFILE,
                        }
                        or is_adult_animation_style_profile(active_style_profile)
                    )
                    else ""
                )
                page_layout = (
                    str(editorial_layouts[scene_index - 1])
                    if (
                        active_style_profile in {
                            INK_GOUACHE_STORY_PAGES_STYLE_PROFILE,
                            CINEMATIC_INK_WEBTOON_STYLE_PROFILE,
                            FORMAT_VISUAL_SYSTEM_V3_STYLE_PROFILE,
                        }
                        or is_adult_animation_style_profile(active_style_profile)
                    )
                    else ""
                )
                panel_grammar = (
                    select_format_visual_system_v3_panel_grammar(
                        format_id, scene_index, scene_count,
                    )
                    if active_style_profile == FORMAT_VISUAL_SYSTEM_V3_STYLE_PROFILE
                    else None
                )
                for layer_role in EDITORIAL_LAYER_ROLES:
                    role_direction = (
                        "Create the wide hero plate: an establishing documentary composition with "
                        "clear spatial depth and room for later HTML evidence overlays."
                        if layer_role == "hero_plate"
                        else
                        "Create the paired detail plate: a closer, materially different view of the "
                        "same source-supported place, person or object, suitable for a paper-card crop "
                        "and semantic reveal."
                    )
                    active_style = (
                        FORMAT_VISUAL_SYSTEM_V3_STYLE
                        if active_style_profile == FORMAT_VISUAL_SYSTEM_V3_STYLE_PROFILE
                        else CINEMATIC_INK_WEBTOON_STYLE
                        if active_style_profile == CINEMATIC_INK_WEBTOON_STYLE_PROFILE
                        else INK_GOUACHE_STORY_PAGES_STYLE
                        if active_style_profile == INK_GOUACHE_STORY_PAGES_STYLE_PROFILE
                        else ADULT_ANIMATION_SERIES[active_style_profile]["art_direction"]
                        if is_adult_animation_style_profile(active_style_profile)
                        else EDITORIAL_MOTION_STYLE
                    )
                    profile_direction = (
                        f"{FORMAT_VISUAL_SYSTEM_V3_FORMAT_DIRECTIONS[format_id]}. "
                        f"{FORMAT_VISUAL_SYSTEM_V3_PILLAR_DIRECTIONS[story_family]}. "
                        if active_style_profile == FORMAT_VISUAL_SYSTEM_V3_STYLE_PROFILE
                        else f"{INK_GOUACHE_FAMILY_DIRECTIONS.get(story_family, '')}. "
                        if active_style_profile in {
                            INK_GOUACHE_STORY_PAGES_STYLE_PROFILE,
                            CINEMATIC_INK_WEBTOON_STYLE_PROFILE,
                        }
                        else f"{ADULT_ANIMATION_SERIES[active_style_profile]['motion_direction']}. "
                        if is_adult_animation_style_profile(active_style_profile)
                        else ""
                    )
                    panel_direction = (
                        f"Panel grammar {panel_grammar['id']}: {panel_grammar['direction']} "
                        if panel_grammar is not None
                        else ""
                    )
                    prompt = (
                        f"{active_style}. "
                        f"Style profile {active_style_profile}; "
                        f"asset family {family_id}; motion role {module}. "
                        f"{profile_direction}"
                        f"{panel_direction}"
                        f"Page-layout intent {page_layout or 'continuous_cutup'}; vary panel scale, crop and "
                        "dominant focal position from adjacent beats without changing this exact panel count. "
                        f"Episode-wide identity contract: {visual_identity_contract}. Preserve these exact "
                        "recurring illustrated identities across every asset family; no age, face, hair, "
                        "wardrobe or body-shape drift. "
                        f"{role_direction} Depict only this translated source moment: {excerpt}. "
                        "Do not invent a person, clue, document, outcome, danger, or emotion. Keep "
                        "identity, location, time of day, wardrobe, props, palette and light coherent "
                        "with the paired plate in this asset family."
                    )
                    plan.append({
                        "story_index": story_index,
                        "source_id": source_id,
                        "scene_index": scene_index,
                        "scene_count": scene_count,
                        "asset_family_id": family_id,
                        "layer_role": layer_role,
                        "motion_module": module,
                        "story_family": story_family or None,
                        "page_layout": page_layout or None,
                        "panel_grammar": panel_grammar["id"] if panel_grammar is not None else None,
                        "panel_count": panel_grammar["panel_count"] if panel_grammar is not None else None,
                        "panel_beat_role": panel_grammar["beat_role"] if panel_grammar is not None else None,
                        "source_excerpt": excerpt,
                        "source_excerpt_sha256": hashlib.sha256(
                            excerpt.encode("utf-8"),
                        ).hexdigest(),
                        "prompt": prompt,
                    })
                continue
            if mode == CINEMATIC_STORY_MODE:
                prompt = (
                    f"{CINEMATIC_STYLE}. Depict only this source-preserving translated moment: "
                    f"{excerpt}. Do not add a person, clue, object, outcome, danger, or emotion "
                    "not supported by that moment."
                )
            else:
                prompt = (
                    f"{STYLE}. Depict only this source-preserving translated moment: {excerpt}. "
                    "Do not add a person, clue, object, outcome, danger, or emotion not supported "
                    "by that moment. Keep the important scene in the left and center-left region."
                )
            plan.append({
                "story_index": story_index,
                "source_id": source_id,
                "scene_index": scene_index,
                "scene_count": scene_count,
                "source_excerpt": excerpt,
                "source_excerpt_sha256": hashlib.sha256(excerpt.encode("utf-8")).hexdigest(),
                "prompt": prompt,
            })
    return plan


def generate_episode_images(
    script: dict[str, Any],
    output_dir: Path,
    *,
    max_images: int,
    generator: Generator = call_image_generation,
    model: str = DEFAULT_IMAGE_MODEL,
    size: str = SIZE,
    artifact_root: Path | None = None,
    visual_mode: str | None = None,
    style_profile: str | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Generate the exact plan and bind every decoded file by checksum."""
    active_visual_mode = resolve_visual_mode(visual_mode or script.get("visual_mode"))
    planned = image_plan(
        script, visual_mode=active_visual_mode, style_profile=style_profile,
    )
    if isinstance(max_images, bool) or not isinstance(max_images, int) or max_images < 1:
        raise EpisodeImageError("max_images must be a positive integer")
    if len(planned) > max_images:
        raise EpisodeImageError(
            f"episode requires {len(planned)} scene images but max_images={max_images}"
        )
    updated = copy.deepcopy(script)
    output_dir = Path(output_dir)
    root = Path(artifact_root) if artifact_root is not None else output_dir
    root = root.resolve()
    expected_size = _expected_dimensions(size)
    resolved_output_dir = output_dir.resolve()
    if artifact_root is not None and (
        resolved_output_dir != root and root not in resolved_output_dir.parents
    ):
        raise EpisodeImageError("image output_dir must remain under artifact_root")
    output_dir.mkdir(parents=True, exist_ok=True)
    assets: list[dict[str, Any]] = []
    for item in planned:
        story_number = item["story_index"] + 1
        source_token = _safe_filename_token(item["source_id"])
        if item.get("layer_role"):
            filename = (
                f"story-{story_number:02d}-{source_token}-scene-{item['scene_index']:03d}"
                f"-{item['layer_role']}.png"
            )
        else:
            filename = (
                f"story-{story_number:02d}-{source_token}-scene-{item['scene_index']:02d}.png"
            )
        output = output_dir / filename
        resolved_output = output.resolve()
        if resolved_output == root or root not in resolved_output.parents:
            raise EpisodeImageError(
                "planned image output must remain under artifact_root",
            )
        result = Path(generator(
            prompt=item["prompt"],
            output_path=output,
            model=model,
            size=size,
        ))
        if not result.is_file() or result.stat().st_size <= 0:
            raise EpisodeImageError(f"image provider produced no file for {item['source_id']}")
        resolved = result.resolve()
        if resolved == root or root not in resolved.parents:
            raise EpisodeImageError("generated image must remain under artifact_root")
        normalization = None
        if active_visual_mode == EDITORIAL_MOTION_MODE:
            normalization = _normalize_editorial_image(
                resolved, expected_size=expected_size,
            )
        _validate_generated_image(resolved, expected_size=expected_size)
        digest = hashlib.sha256(resolved.read_bytes()).hexdigest()
        asset = {
            "media_id": f"generated-{item['source_id']}-scene-{item['scene_index']:02d}",
            "kind": "generated_image",
            "local_path": resolved.relative_to(root).as_posix(),
            "sha256": digest,
            "download_status": "verified",
            "model": model,
            "size": size,
            "prompt": item["prompt"],
            "caption": "",
            "scene_index": item["scene_index"],
            "scene_count": item["scene_count"],
            "asset_family_id": item.get("asset_family_id"),
            "layer_role": item.get("layer_role"),
            "motion_module": item.get("motion_module"),
            "story_family": item.get("story_family"),
            "page_layout": item.get("page_layout"),
            "panel_grammar": item.get("panel_grammar"),
            "panel_count": item.get("panel_count"),
            "panel_beat_role": item.get("panel_beat_role"),
            "source_excerpt_sha256": item["source_excerpt_sha256"],
            "episode_plan_sha256": script.get("episode_plan_sha256"),
        }
        if normalization is not None:
            original = resolved.with_name(normalization["provider_original_path"])
            normalization["provider_original_path"] = original.relative_to(root).as_posix()
            asset["normalization"] = normalization
        updated["stories"][item["story_index"]].setdefault("generated_media", []).append(asset)
        assets.append(asset)
    return updated, assets
