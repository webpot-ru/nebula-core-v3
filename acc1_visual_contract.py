"""Single-source visual geometry and scheduling contract for acc1 long-form."""

from __future__ import annotations


CONTRACT_VERSION = 1

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

BACKGROUND_ASSET_PATH = "assets/acc1/video/chonker-reading-loop-v1.mp4"
BACKGROUND_ASSET_SHA256 = "88e943c6c675f1327eb7020d755e312dbec3864e19dae0d021d909131c349e61"
