"""Generate one consistent GPT Image 2 visual per accepted compilation story."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Callable

from vectorengine_client import DEFAULT_IMAGE_MODEL, VectorEngineError, call_image_generation


STYLE = (
    "cinematic psychological horror, restrained dark blue and charcoal palette, realistic lighting, "
    "subtle film grain, one clear visual subject, 16:9 composition, no text, no logo, no watermark, "
    "no gore, leave safe negative space near the edges"
)


class CompilationImageError(RuntimeError):
    pass


def story_image_prompt(story: dict[str, Any]) -> str:
    if (story.get("editorial_review") or {}).get("verdict") != "PASS":
        raise CompilationImageError("image generation requires PASS editorial review")
    title = str(story.get("title_ru") or "").strip()
    hook = str(story.get("hook_ru") or "").strip()
    if not title:
        raise CompilationImageError("story title_ru is required")
    text_guard = ""
    if re.search(r"(?i)правил|список|\d{1,2}:\d{2}|rules?|list", f"{title} {hook}"):
        text_guard = (
            " Do not depict paper notes, written rules, signs, letters, numbers, or a readable clock face; "
            "convey the night-shift time pressure only through lighting and the character's expression."
        )
    return f"{STYLE}.{text_guard} Story concept: {title}. Key atmosphere: {hook or title}. Depict a moment supported by this concept; do not add a new plot event."


def generate_story_images(
    compilation: dict[str, Any], output_dir: Path, *,
    generator: Callable[..., Path] = call_image_generation,
    model: str = DEFAULT_IMAGE_MODEL,
    size: str = "1536x864",
    resume_compilation: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    stories = compilation.get("stories") or []
    if not 3 <= len(stories) <= 6:
        raise CompilationImageError("compilation requires 3-6 stories")
    output_dir.mkdir(parents=True, exist_ok=True)
    resume_by_post = {
        str((story.get("source_snapshot") or {}).get("post_id")): story
        for story in (resume_compilation or {}).get("stories") or []
        if isinstance(story, dict)
    }
    assets: list[dict[str, Any]] = []
    for index, story in enumerate(stories, start=1):
        post_id = str((story.get("source_snapshot") or {}).get("post_id") or index)
        output = output_dir / f"story-{index:02d}-{post_id}.png"
        prompt = story_image_prompt(story)
        resumed_asset = None
        for candidate in (resume_by_post.get(post_id) or {}).get("generated_media") or []:
            if (candidate.get("model") == model and candidate.get("size") == size
                    and candidate.get("prompt") == prompt):
                resumed_asset = candidate
                break
        if resumed_asset and output.is_file():
            digest = hashlib.sha256(output.read_bytes()).hexdigest()
            if digest != resumed_asset.get("sha256"):
                raise CompilationImageError(f"resumed image checksum changed for story {post_id}")
            path = output
        else:
            result = generator(prompt=prompt, output_path=output, model=model, size=size)
            path = Path(result)
        if not path.is_file() or path.stat().st_size <= 0:
            raise CompilationImageError(f"image generation produced no file for story {post_id}")
        asset = {
            "media_id": f"generated-{post_id}", "kind": "generated_image",
            "local_path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "download_status": "verified", "model": model, "size": size,
            "prompt": prompt, "caption": "",
        }
        story.setdefault("generated_media", []).append(asset)
        assets.append(asset)
    return assets


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compilation", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--updated-compilation", required=True)
    parser.add_argument("--model", default=DEFAULT_IMAGE_MODEL)
    parser.add_argument("--size", default="1536x864")
    parser.add_argument("--resume-compilation")
    parser.add_argument("--confirm-spend", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    compilation_path = Path(args.compilation)
    compilation = json.loads(compilation_path.read_text(encoding="utf-8"))
    prompts = [story_image_prompt(story) for story in compilation.get("stories") or []]
    if args.dry_run:
        print(json.dumps({"status": "dry_run", "would_call_image_model": False, "image_count": len(prompts), "model": args.model}))
        return 0
    if not args.confirm_spend:
        raise CompilationImageError("refusing image generation without --confirm-spend")
    resume_compilation = json.loads(Path(args.resume_compilation).read_text(encoding="utf-8")) if args.resume_compilation else None
    generate_story_images(compilation, Path(args.output_dir), model=args.model, size=args.size,
                          resume_compilation=resume_compilation)
    Path(args.updated_compilation).write_text(json.dumps(compilation, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, json.JSONDecodeError, VectorEngineError, CompilationImageError) as exc:
        print(f"ERROR: {exc}")
        raise SystemExit(1)
