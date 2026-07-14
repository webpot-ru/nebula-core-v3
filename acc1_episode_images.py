"""Source-bound scene-image plan for acc1 SAGA/BUNDLE/THREAD episodes."""

from __future__ import annotations

import copy
import hashlib
import re
from pathlib import Path
from typing import Any, Callable

from PIL import Image, UnidentifiedImageError

from vectorengine_client import DEFAULT_IMAGE_MODEL, call_image_generation


Generator = Callable[..., Path]
SIZE = "1536x864"
STYLE = (
    "cinematic editorial illustration for a Russian Reddit storytelling video, "
    "realistic textured lighting, one clear focal event, restrained dark copper and teal palette, "
    "16:9, no text, no letters, no UI, no logo, no watermark, no gore, "
    "leave the rightmost forty percent calm because the copper cat mascot remains visible there"
)


class EpisodeImageError(RuntimeError):
    """Raised when visuals would exceed spend or source-integrity contracts."""


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


def image_plan(script: dict[str, Any]) -> list[dict[str, Any]]:
    """Plan the smallest useful visual set without calling an image provider."""
    stories = script.get("stories")
    if not isinstance(stories, list) or not stories:
        raise EpisodeImageError("episode script must contain stories")
    format_id = str(script.get("episode_format") or "").upper()
    if format_id == "SAGA":
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
        for scene_index in range(1, scene_count + 1):
            excerpt = _scene_excerpt(story, scene_index, scene_count)
            plan.append({
                "story_index": story_index,
                "source_id": source_id,
                "scene_index": scene_index,
                "scene_count": scene_count,
                "source_excerpt": excerpt,
                "source_excerpt_sha256": hashlib.sha256(excerpt.encode("utf-8")).hexdigest(),
                "prompt": (
                    f"{STYLE}. Depict only this source-preserving translated moment: {excerpt}. "
                    "Do not add a person, clue, object, outcome, danger, or emotion not supported by that moment. "
                    "Keep the important scene in the left and center-left region."
                ),
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
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Generate the exact plan and bind every decoded file by checksum."""
    planned = image_plan(script)
    if isinstance(max_images, bool) or not isinstance(max_images, int) or max_images < 1:
        raise EpisodeImageError("max_images must be a positive integer")
    if len(planned) > max_images:
        raise EpisodeImageError(
            f"episode requires {len(planned)} scene images but max_images={max_images}"
        )
    updated = copy.deepcopy(script)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    root = Path(artifact_root) if artifact_root is not None else output_dir
    root = root.resolve()
    expected_size = _expected_dimensions(size)
    assets: list[dict[str, Any]] = []
    for item in planned:
        story_number = item["story_index"] + 1
        output = output_dir / (
            f"story-{story_number:02d}-{item['source_id']}-scene-{item['scene_index']:02d}.png"
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
        _validate_generated_image(resolved, expected_size=expected_size)
        digest = hashlib.sha256(result.read_bytes()).hexdigest()
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
            "source_excerpt_sha256": item["source_excerpt_sha256"],
            "episode_plan_sha256": script.get("episode_plan_sha256"),
        }
        updated["stories"][item["story_index"]].setdefault("generated_media", []).append(asset)
        assets.append(asset)
    return updated, assets
