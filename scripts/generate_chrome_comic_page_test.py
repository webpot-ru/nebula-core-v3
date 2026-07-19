#!/usr/bin/env python3
"""Generate two original silent comic pages for the lightweight Chrome pilot.

The script deliberately makes exactly two paid VectorEngine image calls and
disables automatic retries.  It is a local visual test, not a publishing path.
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


STYLE = """
Use case: illustration-story.
Asset type: a full comic story page for a silent YouTube visual test.
Style/medium: original adult 2D animated comic, hand-inked dark outlines, flat
cel shading and subtle cream paper grain; mature, expressive, believable adult
characters; elegant unequal panel borders. Do not imitate a named show, artist,
studio, or existing character.
Color palette: warm cream paper, muted olive office green, terracotta red,
burnt orange, charcoal and small pale-blue window highlights.
Constraints: keep the recurring protagonist identical: a 33-year-old woman with
dark wavy hair in a low bun, terracotta cardigan, cream blouse and charcoal
trousers. Keep the recurring manager identical: middle-aged man with black hair,
olive suit, narrow rust tie and an angular face. A small brass desk clock is the
recurring visual object. The page must read as one coherent short scene.
Avoid: no words, letters, numbers, speech bubbles, thought bubbles, captions,
logos, watermarks, readable documents, UI, brand marks, celebrities, extra
panels, panel captions, gore, or photorealism.
""".strip()


PAGES = [
    (
        "work-page-01-arrival.png",
        """
Primary request: create one complete 16:9 comic page with exactly three unequal
panels separated by cream paper gutters, no panel labels.

Panel layout: a large wide panel across the upper two-thirds; two smaller,
different-width panels along the bottom.

Scene/backdrop: a slightly cluttered but professional city office, morning light
through blinds, old green filing cabinet, potted plant, analog wall clock.

Narrative without words: in the large top panel the protagonist has just arrived
at her workstation and notices the manager placing a small brass desk clock near
her keyboard; the gesture is politely ambiguous. Bottom-left is a close-up of
her hand hovering over the clock beside an unlabelled folder. Bottom-right is a
close reaction in which she looks toward a long office corridor while the manager
is only a distant, non-threatening silhouette. Clear eye-lines and a calm uneasy
turning point. No text anywhere.
""".strip(),
    ),
    (
        "work-page-02-choice.png",
        """
Primary request: create one complete 16:9 comic page with exactly four unequal
panels separated by cream paper gutters, no panel labels.

Panel layout: a tall portrait panel on the left; a wide panel across the upper
right; two narrow, unequal panels along the lower right.

Scene/backdrop: the same office later that day with warm late-afternoon light.

Narrative without words: left tall panel shows the protagonist quietly placing
the brass desk clock into an unlabelled storage drawer. Upper-right shows her
calmly speaking to a supportive middle-aged HR lead in a mustard blouse across a
small table; their open body language shows a measured professional conversation,
not conflict. Lower-right first panel is a close-up of her hand closing the
drawer. Lower-right final panel is a wider view of her walking back into daylight
through the office with steady posture while ordinary coworkers continue working.
The visual outcome is self-possession and relief, not triumph. No text anywhere.
""".strip(),
    ),
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
    parser.add_argument(
        "--page-index",
        type=int,
        choices=tuple(range(1, len(PAGES) + 1)),
        help="generate one named page; records a separately auditable manual recovery attempt",
    )
    args = parser.parse_args()

    if not args.confirm_spend:
        raise RuntimeError("refusing paid image generation without --confirm-spend")
    if not load_dotenv_file(args.env_file):
        raise RuntimeError("VectorEngine environment file was not found")

    output_dir = Path(args.output_dir).resolve()
    pages_dir = output_dir / "pages"
    pages_dir.mkdir(parents=True, exist_ok=True)
    journal_path = output_dir / "paid-image-attempts.json"
    if journal_path.exists():
        journal = json.loads(journal_path.read_text(encoding="utf-8"))
        if not isinstance(journal, dict):
            raise RuntimeError(f"journal must be an object: {journal_path}")
    else:
        journal = {
            "purpose": "local silent Chrome comic-page test; not publication-authorized",
            "model": DEFAULT_IMAGE_MODEL,
            "attempt_cap": 60,
            "automatic_retries": 0,
            "style_profile": "adult_animation_work_v1",
            "attempts": [],
        }
        write_json(journal_path, journal)

    selected = (
        [(args.page_index, PAGES[args.page_index - 1])]
        if args.page_index
        else list(enumerate(PAGES, start=1))
    )

    for page_index, (filename, scene) in selected:
        prompt = f"{STYLE}\n\n{scene}"
        output = pages_dir / filename
        if output.exists():
            print(f"[skip] already exists: {filename}", flush=True)
            continue
        attempts = journal.get("attempts")
        if not isinstance(attempts, list):
            raise RuntimeError("journal attempts must be a list")
        attempt_index = len(attempts) + 1
        record: dict[str, object] = {
            "attempt": attempt_index,
            "page_index": page_index,
            "output": f"pages/{filename}",
            "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
            "status": "started",
        }
        attempts.append(record)
        write_json(journal_path, journal)
        try:
            print(f"[calling] {filename}", flush=True)
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
            record["error"] = str(exc)[:500]
            write_json(journal_path, journal)
            raise
        record["status"] = "complete"
        record["sha256"] = sha256(output)
        write_json(journal_path, journal)
        print(f"[complete] {filename}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
