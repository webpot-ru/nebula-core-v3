"""Single-source visual geometry and scheduling contract for acc1 long-form."""

from __future__ import annotations

import hashlib

CONTRACT_VERSION = 1

REDDIT_PAGES_MODE = "reddit_pages"
CINEMATIC_STORY_MODE = "cinematic_story_v1"
EDITORIAL_MOTION_MODE = "editorial_motion_v1"
DEFAULT_VISUAL_MODE = REDDIT_PAGES_MODE
VISUAL_MODES = frozenset({
    REDDIT_PAGES_MODE,
    CINEMATIC_STORY_MODE,
    EDITORIAL_MOTION_MODE,
})

CANVAS_WIDTH = 1920
CANVAS_HEIGHT = 1080
CANVAS_FPS = 30

# The approved copper-cat loop places the mascot on the right.  Text, story
# images and readability shading must be fully transparent at and beyond this
# boundary so generated imagery cannot darken the face, torso, microphone or
# right-hand props.
TEXT_LEFT_X = 92
MASCOT_SAFE_X = 1040
TEXT_RIGHT_X = MASCOT_SAFE_X
STORY_VISUAL_FEATHER_START_X = 800
STORY_VISUAL_FEATHER_END_X = MASCOT_SAFE_X
STORY_VISUAL_BRIGHTNESS = 0.56
READABILITY_SHADE_ALPHA = 145

MIN_VISUAL_SCENES = 3
MAX_VISUAL_SCENES = 5
WORDS_PER_VISUAL_SCENE = 420

CINEMATIC_SHOT_PLAN_VERSION = 1
CINEMATIC_CAPTION_TRACK_VERSION = 1
CINEMATIC_STORY_SHOT_MIN_SECONDS = 20.0
CINEMATIC_STORY_SHOT_MAX_SECONDS = 45.0
# The mixed timeline includes both provider audio padding and the deliberate
# post-segment pause. Keep the editorial target near 15 seconds while allowing
# that bounded tail without turning a service bumper into a story shot.
CINEMATIC_SERVICE_SHOT_MAX_SECONDS = 17.0
CINEMATIC_ZOOM_END_MIN = 1.06
CINEMATIC_ZOOM_END_MAX = 1.10
CINEMATIC_PAN_CENTER_MIN = 0.46
CINEMATIC_PAN_CENTER_MAX = 0.54
CINEMATIC_CAPTION_WORDS_PER_CUE = 8

EDITORIAL_MOTION_PLAN_VERSION = 2
EDITORIAL_MOTION_CAPTION_TRACK_VERSION = 1
EDITORIAL_MOTION_STYLE_PROFILE = "contemporary_cutup_v1"
INK_GOUACHE_STORY_PAGES_STYLE_PROFILE = "ink_gouache_story_pages_v1"
CINEMATIC_INK_WEBTOON_STYLE_PROFILE = "cinematic_ink_webtoon_v1"
ADULT_ANIMATION_FAMILY_STYLE_PROFILE = "adult_animation_family_v1"
ADULT_ANIMATION_WORK_STYLE_PROFILE = "adult_animation_work_v1"
ADULT_ANIMATION_SAGA_STYLE_PROFILE = "adult_animation_saga_absurd_v1"
ADULT_ANIMATION_CONFESSIONS_STYLE_PROFILE = "adult_animation_confessions_v1"
ADULT_ANIMATION_PROFESSIONS_STYLE_PROFILE = "adult_animation_professions_v1"
ADULT_ANIMATION_DAILY_WEIRD_STYLE_PROFILE = "adult_animation_daily_weird_v1"

# These are six original drawn-series identities, selected once per episode.
# They are deliberately not names or facsimiles of existing animated shows.
ADULT_ANIMATION_SERIES = {
    ADULT_ANIMATION_FAMILY_STYLE_PROFILE: {
        "pilot_id": "pilot_01",
        "story_family": "adult_family",
        "label": "warm personal domestic comic",
        "art_direction": (
            "original adult 2D domestic comic: warm slightly uneven linework, lived-in rooms, "
            "expressive believable adults, restrained peach, sage, ink and lamp-amber palette; "
            "quiet observational humour, never cute childrens animation"
        ),
        "motion_direction": "panel opens like a remembered room; reaction cut-ins and object pop-ins",
        "layouts": (
            "wide_room_reaction", "two_shot_counterpoint", "object_memory_insert",
            "doorway_arrival", "kitchen_table_turn", "closeup_then_wide",
            "split_room_parallel", "window_pause", "phone_on_table", "stairwell_exit",
        ),
    },
    ADULT_ANIMATION_WORK_STYLE_PROFILE: {
        "pilot_id": "pilot_02",
        "story_family": "adult_work",
        "label": "dense ironic city comedy",
        "art_direction": (
            "original adult 2D city-work comedy: angular elastic character design, dense green office "
            "or transit spaces, ink outlines, olive, paper-cream, brick and black palette; intelligent "
            "bureaucratic absurdity, no imitation of any television cartoon"
        ),
        "motion_direction": "architectural panels snap into place; paperwork and reaction cut-ins interrupt the frame",
        "layouts": (
            "office_grid_break", "commute_strip", "desk_object_closeup",
            "boss_doorway", "two_shot_counterpoint", "wide_room_reaction",
            "receipt_cascade", "elevator_pause", "split_room_parallel", "exit_sign_release",
        ),
    },
    ADULT_ANIMATION_SAGA_STYLE_PROFILE: {
        "pilot_id": "pilot_03",
        "story_family": "adult_saga_absurd",
        "label": "quiet adult absurdism",
        "art_direction": (
            "original adult 2D quiet absurdist comic: flat yet textured rooms, imperfect hand-drawn line, "
            "awkward human proportions, muted teal, clay, faded yellow and charcoal; ordinary details become "
            "strange through framing only, no noir, no horror gloss, no monsters or gore"
        ),
        "motion_direction": "slow panel expansion, uncanny empty-space holds, then a small object interrupts",
        "layouts": (
            "empty_room_hold", "doorway_arrival", "object_memory_insert",
            "corridor_long_take", "closeup_then_wide", "window_pause",
            "stairwell_exit", "split_room_parallel", "phone_on_table", "wide_room_reaction",
        ),
    },
    ADULT_ANIMATION_CONFESSIONS_STYLE_PROFILE: {
        "pilot_id": "pilot_04",
        "story_family": "adult_confessions",
        "label": "raw personal emotion-led comic",
        "art_direction": (
            "original adult 2D confession comic: bold face acting, loose lively contour, close emotional crops, "
            "dusty rose, cream, oxblood, navy and charcoal; candid and adult, not glossy romance and not pop art"
        ),
        "motion_direction": "close reaction panels rupture into an honest wide scene; props land with a small bounce",
        "layouts": (
            "closeup_then_wide", "two_shot_counterpoint", "phone_on_table",
            "mirror_reaction", "object_memory_insert", "wide_room_reaction",
            "split_room_parallel", "doorway_arrival", "window_pause", "stairwell_exit",
        ),
    },
    ADULT_ANIMATION_PROFESSIONS_STYLE_PROFILE: {
        "pilot_id": "pilot_05",
        "story_family": "adult_professions",
        "label": "observational work comedy",
        "art_direction": (
            "original adult 2D observational job comic: durable graphic line, specific tools and uniforms, "
            "workplace geometry, sun-faded blue, safety orange, cream and ink palette; dry human comedy, "
            "not a childrens workplace cartoon"
        ),
        "motion_direction": "tools and routines create rhythmic inserts; the camera follows a practical task",
        "layouts": (
            "tool_closeup", "commute_strip", "wide_room_reaction",
            "receipt_cascade", "desk_object_closeup", "two_shot_counterpoint",
            "elevator_pause", "doorway_arrival", "split_room_parallel", "exit_sign_release",
        ),
    },
    ADULT_ANIMATION_DAILY_WEIRD_STYLE_PROFILE: {
        "pilot_id": "pilot_06",
        "story_family": "adult_daily_weird",
        "label": "ultra-minimal animated daily comic",
        "art_direction": (
            "original adult 2D minimal daily weird comic: sparse off-white field, confident black hand-drawn line, "
            "one muted red and one muted blue accent, tiny ordinary object with an inexplicable behaviour; dry and "
            "matter-of-fact, no noir, no horror gloss, no cute mascot"
        ),
        "motion_direction": "a single clean panel changes scale; a small impossible detail pops in and the frame holds",
        "layouts": (
            "minimal_object_hold", "phone_on_table", "doorway_arrival",
            "object_memory_insert", "wide_room_reaction", "corridor_long_take",
            "closeup_then_wide", "window_pause", "split_room_parallel", "stairwell_exit",
        ),
    },
}
ADULT_ANIMATION_STYLE_PROFILES = frozenset(ADULT_ANIMATION_SERIES)
ADULT_ANIMATION_PROFILE_BY_PILOT = {
    value["pilot_id"]: profile for profile, value in ADULT_ANIMATION_SERIES.items()
}
EDITORIAL_MOTION_STYLE_PROFILES = frozenset({
    EDITORIAL_MOTION_STYLE_PROFILE,
    INK_GOUACHE_STORY_PAGES_STYLE_PROFILE,
    CINEMATIC_INK_WEBTOON_STYLE_PROFILE,
    *ADULT_ANIMATION_STYLE_PROFILES,
})
INK_GOUACHE_STORY_FAMILIES = (
    "relationships",
    "work",
    "digital",
    "memory",
    "odd_job",
    "dark_saga",
)
INK_GOUACHE_PAGE_LAYOUTS = (
    "hero_left_details_right",
    "phone_portal_insets",
    "message_cascade",
    "vertical_routine_triptych",
    "evidence_slits",
    "rumor_table_wide",
    "corridor_false_claim",
    "empty_desk_release",
)
EDITORIAL_MOTION_MIN_SCENE_SECONDS = 18.0
EDITORIAL_MOTION_TARGET_SCENE_SECONDS = 36.0
EDITORIAL_MOTION_MAX_SCENE_SECONDS = 48.0
EDITORIAL_MOTION_SERVICE_SCENE_MAX_SECONDS = 15.0
EDITORIAL_MOTION_ASSETS_PER_PACK = 2
EDITORIAL_MOTION_MAX_IMAGE_CALLS = 69
EDITORIAL_MOTION_RESERVED_THUMBNAIL_CALLS = 1
EDITORIAL_MOTION_MAX_PACKS = (
    EDITORIAL_MOTION_MAX_IMAGE_CALLS - EDITORIAL_MOTION_RESERVED_THUMBNAIL_CALLS
) // EDITORIAL_MOTION_ASSETS_PER_PACK
EDITORIAL_MOTION_MODULES = (
    "living_photo_depth",
    "evidence_transform",
    "digital_memory_stack",
    "graphic_timeline",
    "dark_semantic_reveal",
    "nested_collage_zoom",
)


def is_adult_animation_style_profile(value: object) -> bool:
    """Return whether ``value`` is one of the six approved drawn-series profiles."""

    return str(value or "").strip() in ADULT_ANIMATION_STYLE_PROFILES


def adult_animation_profile_for_pilot(pilot_id: object) -> str:
    """Resolve one exact profile for a configured acc1 six-slot pilot."""

    profile = ADULT_ANIMATION_PROFILE_BY_PILOT.get(str(pilot_id or "").strip())
    if not profile:
        raise ValueError("pilot_id has no approved adult-animation profile")
    return profile


def adult_animation_series(profile: object) -> dict[str, object]:
    """Return immutable-by-convention metadata for one approved series profile."""

    resolved = str(profile or "").strip()
    value = ADULT_ANIMATION_SERIES.get(resolved)
    if not value:
        raise ValueError("unsupported adult-animation style profile")
    return value


def select_adult_animation_layouts(
    profile: object, story_seed: object, count: int,
) -> tuple[str, ...]:
    """Choose non-repeating page rhythms for one source-bound story.

    The source id is intentional: the same accepted source renders identically
    on a retry, while different stories begin at different positions and walk
    the ten-layout ring with a coprime stride.  It prevents a category from
    becoming one repeated comic page without using render-time randomness.
    """

    if not isinstance(count, int) or count < 1:
        raise ValueError("adult-animation layout count must be a positive integer")
    series = adult_animation_series(profile)
    layouts = tuple(str(item) for item in series["layouts"])
    if count > len(layouts):
        raise ValueError("adult-animation story exceeds its unique layout repertoire")
    seed = f"{profile}|{str(story_seed or '').strip()}".encode("utf-8")
    start = int(hashlib.sha256(seed).hexdigest()[:8], 16) % len(layouts)
    return tuple(layouts[(start + index * 3) % len(layouts)] for index in range(count))

BACKGROUND_ASSET_PATH = "assets/acc1/video/chonker-reading-loop-v1.mp4"
BACKGROUND_ASSET_SHA256 = "88e943c6c675f1327eb7020d755e312dbec3864e19dae0d021d909131c349e61"


def resolve_visual_mode(value: object = None) -> str:
    """Return one explicit supported mode, defaulting only to the baseline."""

    mode = str(value or DEFAULT_VISUAL_MODE).strip()
    if mode not in VISUAL_MODES:
        raise ValueError(
            f"visual_mode must be one of {', '.join(sorted(VISUAL_MODES))}"
        )
    return mode
