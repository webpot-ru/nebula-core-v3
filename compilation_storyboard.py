"""Build a deterministic local-asset storyboard for an acc1 compilation."""

from __future__ import annotations

from pathlib import Path
import argparse
import json
from typing import Any


class CompilationStoryboardError(RuntimeError):
    pass


def _verified_local_images(story: dict[str, Any], artifact_root: Path) -> list[dict[str, Any]]:
    images: list[dict[str, Any]] = []
    root = artifact_root.resolve()
    snapshot = story.get("source_snapshot") or {}
    for asset in list(snapshot.get("source_media") or []) + list(story.get("generated_media") or []):
        if not isinstance(asset, dict) or asset.get("download_status") != "verified":
            continue
        raw_path = str(asset.get("local_path") or "")
        if not raw_path:
            continue
        path = Path(raw_path).resolve()
        if root not in path.parents or not path.is_file():
            raise CompilationStoryboardError("source image must be an existing file under artifact_root")
        images.append({
            "kind": "source_image",
            "local_path": str(path),
            "fit": "contain",
            "caption": str(asset.get("caption") or ""),
            "sha256": asset.get("sha256"),
        })
    return images


def build_storyboard(compilation: dict[str, Any], artifact_root: Path) -> dict[str, Any]:
    slides: list[dict[str, Any]] = [{
        "slide_id": "intro",
        "kind": "title",
        "title": str(compilation.get("title_ru") or "Страшные истории с Reddit"),
    }]
    for index, story in enumerate(compilation.get("stories") or [], start=1):
        snapshot = story.get("source_snapshot") or {}
        slides.append({
            "slide_id": f"story-{index:02d}-title",
            "kind": "story_title",
            "story_index": index,
            "title": str(story.get("title_ru") or snapshot.get("title") or ""),
            "source_url": str(snapshot.get("source_url") or ""),
        })
        for image_index, visual in enumerate(_verified_local_images(story, artifact_root), start=1):
            slides.append({
                "slide_id": f"story-{index:02d}-image-{image_index:02d}",
                "kind": "source_image",
                "story_index": index,
                "visual": visual,
            })
    slides.append({"slide_id": "outro", "kind": "outro", "text": str(compilation.get("outro_ru") or "")})
    return {"version": 1, "format": "compilation_16x9", "resolution": [1920, 1080], "slides": slides}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compilation", required=True)
    parser.add_argument("--artifact-root", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    compilation = json.loads(Path(args.compilation).read_text(encoding="utf-8"))
    storyboard = build_storyboard(compilation, Path(args.artifact_root))
    Path(args.output).write_text(json.dumps(storyboard, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
