#!/usr/bin/env python3
"""Generate one source-bound HR replacement plate for the local Motion Canvas pilot."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from vectorengine_client import DEFAULT_IMAGE_MODEL, call_image_generation, load_dotenv_file


HR_PRIVATE_PROMPT = """
Original adult 2D animated comic-drama artwork for a YouTube story video.
Warm cream paper, muted olive green, brick red, burnt orange and charcoal;
confident thin dark ink outlines; flat cel shading; slight paper grain; mature
workplace animation. Wide 16:9 with foreground, middle ground and background.
No text, speech bubbles, logos, watermarks, interface labels, or readable
documents. Do not imitate any named show, artist, studio, or existing character.

Private HR meeting: only two people are present. A 33-year-old woman with dark
wavy hair in a low bun, terracotta cardigan and cream blouse calmly speaks with
a supportive middle-aged HR lead with short dark hair and a mustard blouse.
They sit across a table in a small professional office. A sealed unlabelled
statement folder is between them; a cup of tea and a small plant make the room
feel safe. No other person, no male coworker, no person in the background, no
reflection, no silhouette behind glass.
""".strip()

RUMOR_MONTAGE_PROMPT = """
Original adult 2D animated comic-drama artwork for a YouTube story video.
Warm cream paper, muted olive green, brick red, burnt orange and charcoal;
confident thin dark ink outlines; flat cel shading; slight paper grain; mature
workplace animation. Wide 16:9 with foreground, middle ground and background.
No text, speech bubbles, thought bubbles, word balloons, logos, watermarks,
interface labels, or readable documents. Do not imitate any named show, artist,
studio, or existing character.

Editorial montage about a workplace rumor: fragmented paper panels show an
anonymous older male coworker in a green suit talking to several indistinct
colleagues after work, while a 33-year-old woman with dark wavy hair in a low
bun and terracotta cardigan is alone in a separate quiet office frame. Torn
paper transitions and overlapping silhouettes suggest conflicting versions,
but no literal dialogue, no comic balloons, no text and no allegations written
into the image. Original mature office-animation look.
""".strip()

EMPTY_DESK_PROMPT = """
Original adult 2D animated comic-drama artwork for a YouTube story video.
Warm cream paper, muted olive green, brick red, burnt orange and charcoal;
confident thin dark ink outlines; flat cel shading; slight paper grain; mature
workplace animation. Wide 16:9 with foreground, middle ground and background.
No text, speech bubbles, logos, watermarks, interface labels, or readable
documents. Do not imitate any named show, artist, studio, or existing character.

Late-afternoon office after an employment decision: an empty green desk chair,
unplugged monitor, a neat stack of unlabelled folders and blinds casting long
warm shadows. The 33-year-old woman with dark wavy hair in a low bun and a
terracotta cardigan works quietly at a distant desk. No male coworker, no male
person, no person in a green suit, no reflection, no silhouette that resembles
an absent employee. Restrained, non-triumphal atmosphere.
""".strip()

RESOLUTION_PROMPT = """
Original adult 2D animated comic-drama artwork for a YouTube story video.
Warm cream paper, muted olive green, brick red, burnt orange and charcoal;
confident thin dark ink outlines; flat cel shading; slight paper grain; mature
workplace animation. Wide 16:9 with foreground, middle ground and background.
No text, speech bubbles, logos, watermarks, interface labels, or readable
documents. Do not imitate any named show, artist, studio, or existing character.

Next morning in the same office: the 33-year-old woman with dark wavy hair in a
low bun and terracotta cardigan walks calmly past a clearly empty workstation
toward daylight while ordinary coworkers continue their work in the background.
The absent male coworker must not appear anywhere: no man in a green suit, no
male foreground character, no reflection, no silhouette of him. Calm restored
workplace, not a celebration.
""".strip()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    parser.add_argument("--env-file", required=True)
    parser.add_argument(
        "--kind",
        choices=("hr-private", "rumor-montage", "empty-desk", "resolution"),
        required=True,
    )
    parser.add_argument("--confirm-spend", action="store_true")
    args = parser.parse_args()
    if not args.confirm_spend:
        raise RuntimeError("refusing paid image generation without --confirm-spend")
    if not load_dotenv_file(args.env_file):
        raise RuntimeError("VectorEngine environment file was not found")
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    prompts = {
        "hr-private": HR_PRIVATE_PROMPT,
        "rumor-montage": RUMOR_MONTAGE_PROMPT,
        "empty-desk": EMPTY_DESK_PROMPT,
        "resolution": RESOLUTION_PROMPT,
    }
    prompt = prompts[args.kind]
    call_image_generation(
        prompt=prompt,
        output_path=output,
        model=DEFAULT_IMAGE_MODEL,
        size="1536x864",
        retries=0,
    )
    print(json.dumps({"model": DEFAULT_IMAGE_MODEL, "output": output.name, "retries": 0}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
