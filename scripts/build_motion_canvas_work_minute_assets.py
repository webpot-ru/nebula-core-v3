#!/usr/bin/env python3
"""Generate twenty source-bound plates for the local Motion Canvas work pilot.

The script is deliberately single-shot: each plate gets one gpt-image-2 call and
there are no automatic retries.  It is not a publishing path.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from vectorengine_client import DEFAULT_IMAGE_MODEL, call_image_generation, load_dotenv_file


SOURCE = {
    "source_id": "1i8nufm",
    "subreddit": "BestofRedditorUpdates",
    "title": "AITAH - my coworker got fired because of me",
    "url": "https://www.reddit.com/r/BestofRedditorUpdates/comments/1i8nufm/",
    "adaptation": "Local silent visual test; source-bound editorial illustration; not publication-authorized.",
}

STYLE = """
Original adult 2D animated comic-drama artwork for a YouTube story video.
Match this art direction only: warm cream paper, muted olive green, brick red,
burnt orange and charcoal; confident thin dark ink outlines; flat cel shading;
slight paper grain; expressive, believable adult characters with angular noses
and simple graphic shapes. Mature workplace animation, not a children's cartoon.
Wide 16:9 composition with a strong foreground, middle ground and background,
leaving clean margins for later camera moves. No text, speech bubbles, logos,
watermarks, interface labels, or readable documents. Do not imitate any named
show, artist, studio, or existing character. Keep the recurring characters
consistent: the protagonist is a 33-year-old woman with dark wavy hair in a low
bun, terracotta cardigan and cream blouse; the older male coworker has dark
slicked hair, a green suit, narrow tie and angular face; the HR lead is a calm
middle-aged woman with a mustard blouse and short dark hair.
""".strip()

BEATS = [
    ("01-new-job-wide", "wide establishing shot of a friendly open-plan office on the protagonist's first week, sunlight through blinds, coworkers at desks, protagonist settling at a desk with a small plant"),
    ("01-new-job-detail", "medium close detail: protagonist accepts an ordinary colleague contact card beside a keyboard, relaxed posture, harmless professional atmosphere"),
    ("02-family-video-wide", "the protagonist alone at her desk receives an unexpected silent video notification on a personal phone; in the small unlabelled screen image, the older coworker is seen beside an indistinct family group; she looks puzzled, office around her"),
    ("02-family-video-detail", "close-up of protagonist's hand lowering a phone beside a coffee cup and office badge, a faint uneasy reflection in the black phone screen, no readable UI"),
    ("03-invitation-wide", "over-the-shoulder office shot: a phone lies facedown near the protagonist's notebook while the older coworker watches from a nearby desk; visual tension remains restrained and realistic"),
    ("03-invitation-detail", "close detail of a clean desk: folded recipe card silhouette, language workbook, phone with blank message bubbles crossed out as abstract icons, protagonist's hand moves the phone aside"),
    ("04-corridor-wide", "office corridor after a shift: protagonist walks forward holding a folder, older coworker stands behind at a respectful-looking but uncomfortable distance with loose papers, fluorescent evening light"),
    ("04-corridor-detail", "tight non-graphic detail: a few loose paper sheets brush the back of a terracotta cardigan, protagonist's hand tenses around a folder, empty corridor background"),
    ("05-at-home-wide", "quiet apartment at night: protagonist sits at a small kitchen table reviewing the sequence of events with phone, notes and a closed laptop, the room is warm but she looks unsettled"),
    ("05-at-home-detail", "top-down editorial detail: neutral phone, crossed-out calendar note, a closed notebook and a single desk lamp pool of light; no readable text, no fabricated evidence"),
    ("06-hr-wide", "professional HR meeting in a calm small office: protagonist speaks with the HR lead across a table, a written statement folder between them, compassionate but serious mood"),
    ("06-hr-detail", "close detail of two hands across a conference table: protagonist releases a sealed unlabelled statement folder while HR lead receives it, a reassuring cup of tea nearby"),
    ("07-hallway-rumor-wide", "separate office building lounge after work: the older coworker speaks animatedly to a small group of coworkers, seen from a distance through glass, while the protagonist is absent"),
    ("07-hallway-rumor-detail", "editorial close detail of fragmented silhouettes and overlapping empty speech balloons dissolving into paper texture, no words or symbols that imply facts"),
    ("08-manager-support-wide", "back in the main office, a manager quietly stands beside the protagonist's desk in support while she keeps working, colleagues behave normally in the background"),
    ("08-manager-support-detail", "close detail of protagonist's shoulders easing as a manager leaves a supportive sticky note with no readable writing, muted office colors"),
    ("09-empty-desk-wide", "late afternoon wide office shot: the older coworker's desk is empty and orderly, chair pushed in, warm light across the room; protagonist works at a distant desk, no triumphal mood"),
    ("09-empty-desk-detail", "close quiet detail of an empty desk with an unplugged monitor, neatly stacked folders and a single shadow from blinds; no nameplates or readable documents"),
    ("10-resolution-wide", "sunlit next morning in the same office: protagonist walks in with steady posture, coworkers continuing their day, calm atmosphere of a workplace restored"),
    ("10-resolution-detail", "final symbolic close shot: protagonist's hand opens the office door toward warm daylight, flat graphic light shapes and paper grain, hopeful but restrained"),
]


def write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--env-file", required=True)
    parser.add_argument("--confirm-spend", action="store_true")
    args = parser.parse_args()

    if not args.confirm_spend:
        raise RuntimeError("refusing paid image generation without --confirm-spend")
    if not load_dotenv_file(args.env_file):
        raise RuntimeError("VectorEngine environment file was not found")

    output_dir = Path(args.output_dir).resolve()
    assets_dir = output_dir / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = output_dir / "paid-image-attempts.json"
    manifest: dict[str, object] = {
        "source": SOURCE,
        "model": DEFAULT_IMAGE_MODEL,
        "attempt_cap": len(BEATS),
        "automatic_retries": 0,
        "style_profile": "adult_animation_work_v1",
        "attempts": [],
    }
    write_json(manifest_path, manifest)

    for index, (slug, beat) in enumerate(BEATS, start=1):
        filename = f"{index:02d}-{slug}.png"
        output = assets_dir / filename
        prompt = f"{STYLE}\n\nScene: {beat}."
        record: dict[str, object] = {
            "attempt": index,
            "slug": slug,
            "output": f"assets/{filename}",
            "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
            "status": "started",
        }
        attempts = manifest["attempts"]
        assert isinstance(attempts, list)
        attempts.append(record)
        write_json(manifest_path, manifest)
        try:
            call_image_generation(
                prompt=prompt,
                output_path=output,
                model=DEFAULT_IMAGE_MODEL,
                size="1536x864",
                retries=0,
            )
        except Exception as exc:
            record["status"] = "failed"
            record["error_type"] = type(exc).__name__
            write_json(manifest_path, manifest)
            raise
        record["status"] = "complete"
        record["sha256"] = sha256(output)
        write_json(manifest_path, manifest)
        print(f"[{index:02d}/{len(BEATS)}] {filename}", flush=True)

    write_json(output_dir / "source-lock.json", SOURCE)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
