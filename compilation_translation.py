"""Fail-closed, source-preserving translation for Reddit compilations.

The module is intentionally provider-agnostic: callers inject ``provider`` in tests,
while the CLI imports the repository Gemini client only after ``--confirm-spend``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


DEFAULT_MODEL = "gemini-3.5-flash"
DEFAULT_MAX_OUTPUT_TOKENS = 16_384
Provider = Callable[..., dict[str, Any]]


class TranslationError(RuntimeError):
    pass


class IncompleteTranslation(TranslationError):
    pass


@dataclass(frozen=True)
class TranslationConfig:
    model: str = DEFAULT_MODEL
    max_output_tokens: int = DEFAULT_MAX_OUTPUT_TOKENS
    temperature: float = 0.2
    min_length_ratio: float = 0.65
    max_length_ratio: float = 1.45
    chunk_chars: int = 7_000
    max_story_revisions: int = 2

    def __post_init__(self) -> None:
        if self.max_output_tokens < 1024:
            raise ValueError("max_output_tokens must be at least 1024")
        if self.max_story_revisions not in (0, 1, 2):
            raise ValueError("max_story_revisions must be between 0 and 2")


def _sentences(text: str) -> list[str]:
    return [part.strip() for part in re.split(r"(?<=[.!?])\s+|\n+", text) if part.strip()]


def source_anchors(text: str) -> dict[str, str]:
    sentences = _sentences(text)
    if not sentences:
        raise TranslationError("source story body is empty")
    return {
        "opening": sentences[0][-500:],
        "middle": sentences[len(sentences) // 2][-500:],
        "ending": " ".join(sentences[-2:])[-900:],
    }


def _translation_prompt(title: str, body: str, anchors: dict[str, str]) -> str:
    return f"""Translate this complete Reddit horror story into natural narrated Russian.
Preserve every event, uncertainty, point of view, name, number, order, and the ending.
Do not summarize, expand, explain, censor, or invent. Return strict JSON:
{{"title":"...","body":"...","complete":true,"ending_preserved":true}}
The booleans are attestations; set either false if the response is incomplete.
Source anchors which must remain represented semantically: {json.dumps(anchors, ensure_ascii=False)}
SOURCE TITLE:\n{title}\nSOURCE BODY:\n{body}"""


def _review_prompt(source_title: str, source_body: str, translated: dict[str, Any]) -> str:
    return f"""Independently compare the complete source and Russian translation. Do not rewrite it.
Fail on omitted/added events, altered uncertainty, broken chronology, changed names/numbers,
unnatural Russian that changes meaning, or a missing/changed ending. Return strict JSON:
{{"verdict":"PASS|REVISE","issues":[{{"kind":"...","evidence":"...","instruction":"..."}}],"ending_preserved":true}}
SOURCE TITLE: {source_title}\nSOURCE BODY:\n{source_body}\nTRANSLATION:\n{json.dumps(translated, ensure_ascii=False)}"""


def _call(provider: Provider, prompt: str, config: TranslationConfig, *, temperature: float | None = None) -> dict[str, Any]:
    result = provider(
        prompt=prompt,
        model=config.model,
        temperature=config.temperature if temperature is None else temperature,
        max_output_tokens=config.max_output_tokens,
    )
    if not isinstance(result, dict):
        raise IncompleteTranslation("provider returned non-object JSON")
    return result


def _looks_like_truncated_json_error(exc: Exception) -> bool:
    message = str(exc).casefold()
    return any(marker in message for marker in (
        "did not return json", "returned empty text", "empty text",
        "unterminated string", "expecting ',' delimiter", "expecting value",
    ))


def _validate_translation(source_body: str, payload: dict[str, Any], config: TranslationConfig) -> None:
    body = str(payload.get("body") or "").strip()
    if not str(payload.get("title") or "").strip() or not body:
        raise IncompleteTranslation("translation is missing title or body")
    if payload.get("complete") is not True:
        raise IncompleteTranslation("provider did not attest complete translation")
    if payload.get("ending_preserved") is not True:
        raise IncompleteTranslation("provider did not attest ending preservation")
    source_words = max(1, len(source_body.split()))
    translated_words = len(body.split())
    if translated_words / source_words < config.min_length_ratio:
        raise IncompleteTranslation("translation is implausibly short")
    if translated_words / source_words > config.max_length_ratio:
        raise IncompleteTranslation("translation expanded beyond the source-preserving limit")


def _paragraph_chunks(body: str, limit: int) -> list[str]:
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", body) if p.strip()]
    chunks: list[str] = []
    current = ""
    for paragraph in paragraphs or [body]:
        pieces = [paragraph[i:i + limit] for i in range(0, len(paragraph), limit)]
        for piece in pieces:
            candidate = f"{current}\n\n{piece}".strip()
            if current and len(candidate) > limit:
                chunks.append(current)
                current = piece
            else:
                current = candidate
    if current:
        chunks.append(current)
    return chunks


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def _chunk_translate(
    provider: Provider, title: str, body: str, config: TranslationConfig,
    *, checkpoint_path: Path | None = None,
) -> dict[str, Any]:
    chunks = _paragraph_chunks(body, config.chunk_chars)
    source_hash = hashlib.sha256(json.dumps({"title": title, "body": body, "chunk_chars": config.chunk_chars}, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    state: dict[str, Any] = {"schema_version": 1, "source_hash": source_hash, "glossary": None, "chunks": []}
    if checkpoint_path and checkpoint_path.is_file():
        state = json.loads(checkpoint_path.read_text(encoding="utf-8"))
        if state.get("source_hash") != source_hash or not isinstance(state.get("chunks"), list):
            raise TranslationError("chunk translation checkpoint does not match source")
    glossary = state.get("glossary")
    if not isinstance(glossary, dict):
        glossary = _call(provider, f"Extract a continuity glossary from the complete story and translate its title. Return JSON "
            f'{{"translated_title":"...","glossary":{{}},"continuity":"..."}}. TITLE: {title}\nSTORY:\n{body}', config)
        state["glossary"] = glossary
        if checkpoint_path:
            _atomic_json(checkpoint_path, state)
    translated_title = str(glossary.get("translated_title") or "").strip()
    if not translated_title:
        raise IncompleteTranslation("chunk fallback glossary is missing translated_title")
    translated: list[str] = []
    for index, chunk in enumerate(chunks):
        chunk_hash = hashlib.sha256(chunk.encode()).hexdigest()
        saved_chunks = state["chunks"]
        if index < len(saved_chunks):
            saved = saved_chunks[index]
            if saved.get("source_sha256") != chunk_hash or not str(saved.get("body") or "").strip():
                raise TranslationError(f"chunk translation checkpoint changed at chunk {index + 1}")
            translated.append(str(saved["body"]).strip())
            continue
        prompt = f"""Translate chunk {index + 1}/{len(chunks)} into narrated Russian without omissions or additions.
Return JSON {{"body":"...","complete":true}}. Keep continuity with prior translation and glossary.
GLOSSARY: {json.dumps(glossary, ensure_ascii=False)}
PRIOR END: {' '.join(translated)[-1000:]}
CHUNK:\n{chunk}"""
        payload = _call(provider, prompt, config)
        if payload.get("complete") is not True or not str(payload.get("body") or "").strip():
            raise IncompleteTranslation(f"chunk {index + 1} is incomplete")
        translated.append(str(payload["body"]).strip())
        saved_chunks.append({"index": index, "source_sha256": chunk_hash, "body": translated[-1]})
        if checkpoint_path:
            _atomic_json(checkpoint_path, state)
    result = {"title": translated_title, "body": "\n\n".join(translated), "complete": True, "ending_preserved": True}
    _validate_translation(body, result, config)
    return result


def translate_and_review_story(
    story: dict[str, Any], *, provider: Provider, reviewer: Provider | None = None,
    config: TranslationConfig | None = None, chunk_checkpoint_path: Path | None = None,
    review_checkpoint_path: Path | None = None,
) -> dict[str, Any]:
    """Translate full-story-first, fallback only on incomplete output, then review."""
    config = config or TranslationConfig()
    title, body = str(story.get("title") or ""), str(story.get("body") or "")
    anchors = source_anchors(body)
    used_chunk_fallback = False
    try:
        if chunk_checkpoint_path and chunk_checkpoint_path.is_file():
            used_chunk_fallback = True
            translated = _chunk_translate(provider, title, body, config, checkpoint_path=chunk_checkpoint_path)
        else:
            translated = _call(provider, _translation_prompt(title, body, anchors), config)
            _validate_translation(body, translated, config)
    except IncompleteTranslation:
        used_chunk_fallback = True
        translated = _chunk_translate(provider, title, body, config, checkpoint_path=chunk_checkpoint_path)
    except Exception as exc:
        if not _looks_like_truncated_json_error(exc):
            raise
        used_chunk_fallback = True
        translated = _chunk_translate(provider, title, body, config, checkpoint_path=chunk_checkpoint_path)

    review_provider = reviewer or provider
    revisions = 0
    review_history: list[dict[str, Any]] = []
    while True:
        review = _call(review_provider, _review_prompt(title, body, translated), config, temperature=0.0)
        review_history.append(review)
        if review_checkpoint_path:
            _atomic_json(review_checkpoint_path, {
                "schema_version": 1,
                "source_sha256": hashlib.sha256(body.encode()).hexdigest(),
                "revisions_completed": revisions,
                "review_history": review_history,
            })
        if review.get("verdict") == "PASS" and review.get("ending_preserved") is True:
            break
        if review.get("verdict") != "REVISE":
            raise TranslationError("reviewer returned invalid or unsafe verdict")
        if revisions >= config.max_story_revisions:
            raise TranslationError("translation remains REVISE after maximum story revisions")
        revisions += 1
        translated = _call(provider, "Revise only the cited translation defects. Preserve all other wording. "
            "Return the full strict translation JSON with complete=true and ending_preserved=true.\n"
            f"ISSUES: {json.dumps(review.get('issues') or [], ensure_ascii=False)}\n"
            f"SOURCE: {body}\nCURRENT: {json.dumps(translated, ensure_ascii=False)}", config)
        _validate_translation(body, translated, config)
        if review_checkpoint_path:
            _atomic_json(review_checkpoint_path, {
                "schema_version": 1,
                "source_sha256": hashlib.sha256(body.encode()).hexdigest(),
                "revisions_completed": revisions,
                "review_history": review_history,
            })

    return {
        **story,
        "title": str(translated["title"]).strip(),
        "body": str(translated["body"]).strip(),
        "source_title": title,
        "source_body": body,
        "translation_audit": {
            "model": config.model, "max_output_tokens": config.max_output_tokens,
            "full_story_first": True, "chunk_fallback": used_chunk_fallback,
            "revisions": revisions, "review": review, "source_anchors": anchors,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--story", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--max-output-tokens", type=int, default=DEFAULT_MAX_OUTPUT_TOKENS)
    parser.add_argument("--confirm-spend", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if args.dry_run:
        print(json.dumps({"would_call_gemini": False, "model": args.model,
                          "max_output_tokens": args.max_output_tokens}, indent=2))
        return 0
    if not args.confirm_spend:
        parser.error("live Gemini translation requires --confirm-spend (or use --dry-run)")
    if not args.output:
        parser.error("--output is required for a live translation")
    from vectorengine_client import call_gemini_json
    story = json.loads(args.story.read_text(encoding="utf-8"))
    result = translate_and_review_story(story, provider=call_gemini_json,
        config=TranslationConfig(model=args.model, max_output_tokens=args.max_output_tokens))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
