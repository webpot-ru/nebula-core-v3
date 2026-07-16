"""Source-bound scene-image plan for acc1 SAGA/BUNDLE/THREAD episodes."""

from __future__ import annotations

import copy
import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any, Callable

from PIL import Image, ImageEnhance, ImageOps, UnidentifiedImageError

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


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical_hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")).hexdigest()


def _inspect_generated_image(path: Path) -> tuple[str, tuple[int, int]]:
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
    return actual_format, actual_size


def _normalize_generated_image(
    path: Path,
    *,
    expected_size: tuple[int, int],
    provider_path: Path,
) -> tuple[tuple[int, int], bool, Path]:
    _actual_format, actual_size = _inspect_generated_image(path)
    if actual_size == expected_size:
        return actual_size, False, path
    expected_ratio = expected_size[0] / expected_size[1]
    actual_ratio = actual_size[0] / actual_size[1]
    if (
        actual_size[0] < expected_size[0]
        or actual_size[1] < expected_size[1]
        or abs(actual_ratio - expected_ratio) / expected_ratio > 0.01
    ):
        raise EpisodeImageError(
            "image provider returned wrong dimensions: "
            f"expected {expected_size[0]}x{expected_size[1]}, "
            f"got {actual_size[0]}x{actual_size[1]}"
        )
    if provider_path.exists():
        raise EpisodeImageError(f"unexpected existing raw provider image: {provider_path.name}")
    os.replace(path, provider_path)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with Image.open(provider_path) as image:
        normalized = ImageOps.fit(
            image.convert("RGB"), expected_size, method=Image.Resampling.LANCZOS,
        )
        normalized.save(temporary, format="PNG")
    os.replace(temporary, path)
    _format, normalized_size = _inspect_generated_image(path)
    if normalized_size != expected_size:
        raise EpisodeImageError("normalized image does not match the requested dimensions")
    return actual_size, True, provider_path


def _atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _continuity_fallback(source: Path, output: Path, expected_size: tuple[int, int]) -> None:
    """Create a deterministic local variation without repeating a paid request."""
    temporary = output.with_name(f".{output.name}.{os.getpid()}.tmp")
    with Image.open(source) as image:
        frame = ImageOps.fit(
            image.convert("RGB"), expected_size,
            method=Image.Resampling.LANCZOS,
            bleed=0.012,
            centering=(0.46, 0.5),
        )
        frame = ImageEnhance.Brightness(frame).enhance(0.96)
        frame.save(temporary, format="PNG")
    os.replace(temporary, output)


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
    provider_attempts: list[dict[str, Any]] | None = None,
    checkpoint_path: Path | None = None,
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
    attempts = provider_attempts if provider_attempts is not None else []
    if len(attempts) > len(planned):
        raise EpisodeImageError("image journal has more attempts than the scene plan")
    checkpoint_file = Path(checkpoint_path) if checkpoint_path is not None else None
    if checkpoint_file is not None and provider_attempts is None:
        raise EpisodeImageError("image checkpoint requires the provider attempt journal")
    checkpoint = {
        "version": 1,
        "episode_plan_sha256": script.get("episode_plan_sha256"),
        "model": model,
        "size": size,
        "entries": [],
        "publication_authorized": False,
    }
    if checkpoint_file is not None and checkpoint_file.exists():
        loaded = json.loads(checkpoint_file.read_text(encoding="utf-8"))
        if not isinstance(loaded, dict) or any(
            loaded.get(key) != checkpoint[key]
            for key in ("version", "episode_plan_sha256", "model", "size", "publication_authorized")
        ) or not isinstance(loaded.get("entries"), list):
            raise EpisodeImageError("image checkpoint is incompatible")
        checkpoint = loaded
    if len(checkpoint["entries"]) > len(attempts):
        raise EpisodeImageError("image checkpoint exceeds the provider journal")
    assets: list[dict[str, Any]] = []
    for plan_index, item in enumerate(planned):
        story_number = item["story_index"] + 1
        output = output_dir / (
            f"story-{story_number:02d}-{item['source_id']}-scene-{item['scene_index']:02d}.png"
        )
        request_sha256 = _canonical_hash({
            "prompt": item["prompt"], "model": model,
            "max_output_tokens": None, "voice_id": None,
        })
        entry = checkpoint["entries"][plan_index] if plan_index < len(checkpoint["entries"]) else None
        attempt = attempts[plan_index] if plan_index < len(attempts) else None
        ambiguous = bool(
            attempt is not None
            and attempt.get("status") == "AMBIGUOUS_ERROR"
            and plan_index == len(attempts) - 1
            and attempt.get("output_sha256") is None
        )
        if attempt is not None and (
            attempt.get("index") != plan_index + 1
            or (attempt.get("status") != "COMPLETE" and not ambiguous)
            or attempt.get("request_sha256") != request_sha256
        ):
            raise EpisodeImageError("image journal attempt does not match the scene plan")
        if entry is not None:
            expected_output_path = output.resolve().relative_to(root).as_posix()
            expected_raw_path = output.with_name(
                f"{output.stem}.provider{output.suffix}"
            ).resolve().relative_to(root).as_posix()
            is_fallback = entry.get("local_fallback") is True
            if is_fallback:
                if (
                    not ambiguous
                    or entry.get("index") != plan_index + 1
                    or entry.get("request_sha256") != request_sha256
                    or entry.get("provider_path") is not None
                    or entry.get("provider_output_sha256") is not None
                    or entry.get("output_path") != expected_output_path
                    or plan_index < 1
                ):
                    raise EpisodeImageError("image fallback checkpoint is invalid")
                previous = checkpoint["entries"][plan_index - 1]
                source = root / str(entry.get("fallback_source_path") or "")
                if (
                    entry.get("fallback_source_path") != previous.get("output_path")
                    or entry.get("fallback_source_sha256") != previous.get("output_sha256")
                    or not source.is_file()
                    or _sha256(source) != entry.get("fallback_source_sha256")
                ):
                    raise EpisodeImageError("image fallback source hash mismatch")
            elif (
                attempt is None
                or entry.get("index") != plan_index + 1
                or entry.get("request_sha256") != request_sha256
                or entry.get("provider_output_sha256") != attempt.get("output_sha256")
                or entry.get("output_path") != expected_output_path
                or entry.get("provider_path") not in {expected_output_path, expected_raw_path}
            ):
                raise EpisodeImageError("image checkpoint is not bound to the provider attempt")
            result = root / str(entry.get("output_path") or "")
            provider_file = root / str(entry.get("provider_path") or "") if not is_fallback else None
            if not result.is_file() or _sha256(result) != entry.get("output_sha256"):
                raise EpisodeImageError("image checkpoint file hash mismatch")
            if not is_fallback and (
                provider_file is None
                or not provider_file.is_file()
                or _sha256(provider_file) != attempt.get("output_sha256")
            ):
                raise EpisodeImageError("image checkpoint file hash mismatch")
            provider_size = tuple(entry.get("provider_size") or ())
            normalized = bool(entry.get("normalized"))
        else:
            if ambiguous:
                if plan_index < 1 or len(checkpoint["entries"]) != plan_index:
                    raise EpisodeImageError("ambiguous image requires the prior verified scene")
                previous = checkpoint["entries"][plan_index - 1]
                fallback_source = root / str(previous.get("output_path") or "")
                if (
                    not fallback_source.is_file()
                    or _sha256(fallback_source) != previous.get("output_sha256")
                ):
                    raise EpisodeImageError("ambiguous image fallback source is invalid")
                _continuity_fallback(fallback_source, output, expected_size)
                result = output
                provider_size = expected_size
                normalized = False
                digest = _sha256(output)
                entry = {
                    "index": plan_index + 1,
                    "request_sha256": request_sha256,
                    "provider_path": None,
                    "provider_output_sha256": None,
                    "provider_size": list(expected_size),
                    "output_path": output.resolve().relative_to(root).as_posix(),
                    "output_sha256": digest,
                    "normalized": False,
                    "local_fallback": True,
                    "fallback_reason": "ambiguous_provider_attempt_not_retried",
                    "fallback_source_path": previous["output_path"],
                    "fallback_source_sha256": previous["output_sha256"],
                }
                checkpoint["entries"].append(entry)
                if checkpoint_file is not None:
                    _atomic_json(checkpoint_file, checkpoint)
            elif attempt is None:
                result = Path(generator(
                    prompt=item["prompt"], output_path=output, model=model, size=size,
                ))
                if provider_attempts is not None and plan_index >= len(attempts):
                    raise EpisodeImageError("image provider call was not persisted in the journal")
                if provider_attempts is not None:
                    attempt = attempts[plan_index]
                    if (
                        attempt.get("status") != "COMPLETE"
                        or attempt.get("request_sha256") != request_sha256
                    ):
                        raise EpisodeImageError("completed image call does not match the scene plan")
                else:
                    attempt = {
                        "index": plan_index + 1,
                        "status": "COMPLETE",
                        "request_sha256": request_sha256,
                    }
            else:
                result = output
        if not result.is_file() or result.stat().st_size <= 0:
            raise EpisodeImageError(f"image provider produced no file for {item['source_id']}")
        if not ambiguous and attempt.get("output_sha256") is None:
            attempt["output_sha256"] = _sha256(result)
        resolved = result.resolve()
        if resolved == root or root not in resolved.parents:
            raise EpisodeImageError("generated image must remain under artifact_root")
        if entry is None:
            if _sha256(resolved) != attempt.get("output_sha256"):
                raise EpisodeImageError("provider image file does not match its journal hash")
            raw_path = output.with_name(f"{output.stem}.provider{output.suffix}")
            provider_size, normalized, provider_file = _normalize_generated_image(
                resolved, expected_size=expected_size, provider_path=raw_path,
            )
            digest = _sha256(output)
            entry = {
                "index": plan_index + 1,
                "request_sha256": request_sha256,
                "provider_path": provider_file.resolve().relative_to(root).as_posix(),
                "provider_output_sha256": attempt["output_sha256"],
                "provider_size": list(provider_size),
                "output_path": output.resolve().relative_to(root).as_posix(),
                "output_sha256": digest,
                "normalized": normalized,
            }
            checkpoint["entries"].append(entry)
            if checkpoint_file is not None:
                _atomic_json(checkpoint_file, checkpoint)
        else:
            _format, actual_size = _inspect_generated_image(resolved)
            if actual_size != expected_size:
                raise EpisodeImageError("checkpoint image has wrong normalized dimensions")
            digest = _sha256(resolved)
        asset = {
            "media_id": f"generated-{item['source_id']}-scene-{item['scene_index']:02d}",
            "kind": "local_continuity_fallback" if entry.get("local_fallback") else "generated_image",
            "local_path": resolved.relative_to(root).as_posix(),
            "sha256": digest,
            "download_status": "verified",
            "model": model,
            "size": size,
            "provider_size": list(provider_size),
            "normalized_from_provider_size": normalized,
            "local_fallback": bool(entry.get("local_fallback")),
            "fallback_reason": entry.get("fallback_reason"),
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
