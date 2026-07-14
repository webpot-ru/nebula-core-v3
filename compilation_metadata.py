"""Gemini packaging for an accepted acc1 Reddit horror compilation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from vectorengine_client import DEFAULT_GEMINI_MODEL, VectorEngineError, call_gemini_json


class CompilationMetadataError(RuntimeError):
    pass


def load_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise CompilationMetadataError(f"{path} must contain a JSON object")
    return value


def accepted_story_summary(compilation: dict[str, Any]) -> list[dict[str, Any]]:
    summaries: list[dict[str, Any]] = []
    for story in compilation.get("stories") or []:
        if not isinstance(story, dict) or (story.get("editorial_review") or {}).get("verdict") != "PASS":
            raise CompilationMetadataError("metadata requires PASS editorial review for every story")
        snapshot = story.get("source_snapshot") or {}
        summaries.append({
            "post_id": snapshot.get("post_id"),
            "source_title": snapshot.get("title"),
            "russian_title": story.get("title_ru"),
            "truth_mode": snapshot.get("truth_mode"),
            "ending_preserved_evidence": story.get("ending_preserved_evidence"),
            "hook": story.get("hook_ru"),
        })
    if not 3 <= len(summaries) <= 6:
        raise CompilationMetadataError("metadata requires 3-6 accepted stories")
    return summaries


def build_prompt(compilation: dict[str, Any]) -> str:
    summaries = accepted_story_summary(compilation)
    return f"""
Create honest Russian YouTube packaging for one 45-60 minute horror compilation sourced from Reddit.

Rules:
- Use only promises and payoffs present in the accepted story summaries.
- Return exactly three materially different title/thumbnail angles, not punctuation variants.
- The main emotional premise comes first; "Reddit" and the series number are secondary.
- Title <= 95 characters. Thumbnail text <= 32 characters and at most two short lines.
- Do not call fiction real. Do not call unverified personal accounts verified fact.
- The description must include ordered story timestamps as placeholders and every source URL supplied below.
- Return strict JSON only.

Compilation:
{json.dumps({
    'source_mode': compilation.get('source_mode'),
    'series_number': compilation.get('series_number'),
    'stories': summaries,
    'source_urls': [(story.get('source_snapshot') or {}).get('source_url') for story in compilation.get('stories') or []],
}, ensure_ascii=False, indent=2)}

JSON:
{{
  "packaging_options": [
    {{"youtube_title":"", "thumbnail_text":"", "angle":"", "source_backing":""}}
  ],
  "selected_option_index": 0,
  "youtube_description": "",
  "thumbnail_prompt": "cinematic 16:9 image prompt without text or logos",
  "language": "ru",
  "risk_flags": []
}}
""".strip()


def validate_metadata(payload: dict[str, Any], compilation: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    options = payload.get("packaging_options") or []
    if not isinstance(options, list) or len(options) != 3:
        failures.append("packaging_options must contain exactly three options")
        options = []
    angles: set[str] = set()
    for index, option in enumerate(options):
        if not isinstance(option, dict):
            failures.append(f"packaging_options[{index}] must be an object")
            continue
        title = str(option.get("youtube_title") or "").strip()
        thumb = str(option.get("thumbnail_text") or "").strip()
        angle = str(option.get("angle") or "").strip().casefold()
        if not title or len(title) > 95:
            failures.append(f"packaging_options[{index}].youtube_title is empty or too long")
        if not thumb or len(thumb) > 32:
            failures.append(f"packaging_options[{index}].thumbnail_text is empty or too long")
        if not angle or angle in angles:
            failures.append(f"packaging_options[{index}].angle is empty or duplicated")
        angles.add(angle)
    description = str(payload.get("youtube_description") or "")
    for story in compilation.get("stories") or []:
        url = str((story.get("source_snapshot") or {}).get("source_url") or "")
        if url and url not in description:
            failures.append(f"youtube_description is missing source URL for {(story.get('source_snapshot') or {}).get('post_id')}")
    if payload.get("language") != "ru":
        failures.append("metadata language must be ru")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compilation", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--model", default=DEFAULT_GEMINI_MODEL)
    parser.add_argument("--confirm-spend", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    compilation = load_object(Path(args.compilation))
    prompt = build_prompt(compilation)
    if args.dry_run:
        print(json.dumps({"status": "dry_run", "would_call_gemini": False, "prompt_chars": len(prompt)}))
        return 0
    if not args.confirm_spend:
        raise CompilationMetadataError("refusing Gemini metadata call without --confirm-spend")
    try:
        payload = call_gemini_json(prompt=prompt, model=args.model, max_output_tokens=4096)
    except VectorEngineError as exc:
        raise CompilationMetadataError(str(exc)) from exc
    failures = validate_metadata(payload, compilation)
    if failures:
        raise CompilationMetadataError("; ".join(failures))
    Path(args.output).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
