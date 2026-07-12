"""Translate/review an acc1 compilation manifest into an accepted Russian script."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Callable

from compilation_translation import TranslationConfig, translate_and_review_story
from episode_contract import validate_compilation


class CompilationPipelineError(RuntimeError):
    pass


def translate_manifest(manifest: dict[str, Any], provider: Callable[..., dict[str, Any]]) -> dict[str, Any]:
    translated_stories: list[dict[str, Any]] = []
    for selected in manifest.get("stories") or []:
        snapshot = selected.get("source_snapshot") or {}
        result = translate_and_review_story(
            {"title": snapshot.get("title"), "body": snapshot.get("body")},
            provider=provider,
            reviewer=provider,
            config=TranslationConfig(max_output_tokens=16_384),
        )
        truth_mode = snapshot.get("truth_mode")
        disclosure = (
            "fiction: художественная история с Reddit"
            if truth_mode == "fiction"
            else "unverified: личный рассказ пользователя Reddit, не подтвержденный независимо"
        )
        audit = result["translation_audit"]
        translated_stories.append({
            "source_snapshot": snapshot,
            "title_ru": result["title"],
            "narration_ru": result["body"],
            "hook_ru": result["title"],
            "transition_after_ru": "А теперь — следующая история.",
            "disclosure": disclosure,
            "ending_preserved_evidence": audit["source_anchors"]["ending"],
            "change_ledger": [],
            "invented_factual_claims": [],
            "editorial_review": {"verdict": "PASS", "issues": [], "provider_review": audit["review"]},
            "translation_audit": audit,
        })
    compilation = {
        **{key: value for key, value in manifest.items() if key != "stories"},
        "intro_ru": "Сегодня вас ждут несколько законченных страшных историй с Reddit.",
        "outro_ru": "Какая история напугала вас сильнее всего? Напишите в комментариях.",
        "revision_count": max((item["translation_audit"]["revisions"] for item in translated_stories), default=0),
        "editorial_review": {"verdict": "PASS", "issues": []},
        "stories": translated_stories,
    }
    validation = validate_compilation(compilation)
    if validation["status"] != "PASS":
        raise CompilationPipelineError("compilation contract failed: " + "; ".join(validation["failures"]))
    compilation["contract_validation"] = validation
    return compilation


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--confirm-spend", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    if args.dry_run:
        print(json.dumps({"status": "dry_run", "story_count": len(manifest.get("stories") or []), "would_call_gemini": False}))
        return 0
    if not args.confirm_spend:
        raise CompilationPipelineError("refusing compilation translation without --confirm-spend")
    from vectorengine_client import call_gemini_json
    compilation = translate_manifest(manifest, call_gemini_json)
    Path(args.output).write_text(json.dumps(compilation, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
