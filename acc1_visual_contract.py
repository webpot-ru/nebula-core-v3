"""Single-source visual geometry and scheduling contract for acc1 long-form."""

from __future__ import annotations


CONTRACT_VERSION = 1

REDDIT_PAGES_MODE = "reddit_pages"
CINEMATIC_STORY_MODE = "cinematic_story_v1"
DEFAULT_VISUAL_MODE = REDDIT_PAGES_MODE
VISUAL_MODES = frozenset({REDDIT_PAGES_MODE, CINEMATIC_STORY_MODE})

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
