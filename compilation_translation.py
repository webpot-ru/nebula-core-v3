"""Fail-closed, source-preserving translation for Reddit compilations.

The module is intentionally provider-agnostic: callers inject ``provider`` in tests,
while the CLI imports the repository Gemini client only after ``--confirm-spend``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from acc1_language_gate import is_russian_text
from compilation_narration import narration_preflight


DEFAULT_MODEL = "gemini-3.5-flash"
DEFAULT_MAX_OUTPUT_TOKENS = 16_384
DEFAULT_MAX_CHARACTER_RATIO = 2.0
DEFAULT_MAX_CHARACTER_FLOOR = 512
DEFAULT_MAX_TOKEN_CHARACTERS = 80
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
    max_character_ratio: float = DEFAULT_MAX_CHARACTER_RATIO
    max_character_floor: int = DEFAULT_MAX_CHARACTER_FLOOR
    max_token_characters: int = DEFAULT_MAX_TOKEN_CHARACTERS
    chunk_chars: int = 7_000
    max_story_revisions: int = 2

    def __post_init__(self) -> None:
        if self.max_output_tokens < 1024:
            raise ValueError("max_output_tokens must be at least 1024")
        if self.max_story_revisions not in (0, 1, 2):
            raise ValueError("max_story_revisions must be between 0 and 2")
        if not 1.0 <= self.max_character_ratio <= 3.0:
            raise ValueError("max_character_ratio must be between 1.0 and 3.0")
        if self.max_character_floor < 128:
            raise ValueError("max_character_floor must be at least 128")
        if not 20 <= self.max_token_characters <= 160:
            raise ValueError("max_token_characters must be between 20 and 160")


def _sentences(text: str) -> list[str]:
    return [part.strip() for part in re.split(r"(?<=[.!?])\s+|\n+", text) if part.strip()]


def canonicalize_source_for_translation(value: Any) -> str:
    """Collapse non-semantic whitespace while preserving paragraph boundaries.

    The exact Reddit body and its hash remain in source evidence.  This working
    copy prevents tabs or very long space runs from inflating provider prompts
    and fallback chunk counts without changing words, punctuation, or order.
    """
    raw = str(value or "").replace("\r\n", "\n").replace("\r", "\n")
    paragraphs = [
        re.sub(r"\s+", " ", paragraph).strip()
        for paragraph in re.split(r"\n\s*\n", raw)
    ]
    return "\n\n".join(paragraph for paragraph in paragraphs if paragraph)


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
    return f"""Translate this complete Reddit story into natural narrated Russian.
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
{{"verdict":"PASS|REVISE","issues":[{{"kind":"...","source_quote":"exact source quote","translation_quote":"exact current Russian quote","replacement":"exact Russian replacement","explanation":"..."}}],"ending_preserved":true}}
For every REVISE issue, translation_quote must occur verbatim in the current translation and replacement
must be the complete local replacement for only that quote. Do not request or perform a full rewrite.
SOURCE TITLE: {source_title}\nSOURCE BODY:\n{source_body}\nTRANSLATION:\n{json.dumps(translated, ensure_ascii=False)}"""


def _apply_review_patches(source_title: str, source_body: str, translated: dict[str, Any], review: dict[str, Any]) -> dict[str, Any]:
    patched = dict(translated)
    fields = {"title": str(patched.get("title") or ""), "body": str(patched.get("body") or "")}
    issues = review.get("issues")
    if not isinstance(issues, list) or not issues:
        raise TranslationError("REVISE verdict requires structured issues")
    for index, issue in enumerate(issues, 1):
        if not isinstance(issue, dict):
            raise TranslationError(f"review issue {index} is not an object")
        source_quote = str(issue.get("source_quote") or "").strip()
        old = str(issue.get("translation_quote") or "").strip()
        new = str(issue.get("replacement") or "").strip()
        if not source_quote or (source_quote not in source_body and source_quote not in source_title):
            raise TranslationError(f"review issue {index} lacks an exact source quote")
        if not old or not new or old == new:
            raise TranslationError(f"review issue {index} lacks a usable local replacement")
        matches = [(field, text.count(old)) for field, text in fields.items() if old in text]
        if sum(count for _, count in matches) != 1:
            raise TranslationError(f"review issue {index} translation quote is not uniquely patchable")
        field = matches[0][0]
        fields[field] = fields[field].replace(old, new, 1)
    patched.update(fields)
    return patched


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
    title = str(payload.get("title") or "").strip()
    body = str(payload.get("body") or "").strip()
    if not title or not body:
        raise IncompleteTranslation("translation is missing title or body")
    if not is_russian_text(
        title,
        minimum_cyrillic_words=1,
        minimum_cyrillic_letter_ratio=0.50,
    ):
        raise IncompleteTranslation("translated title is not demonstrably Russian")
    if not is_russian_text(
        body,
        minimum_cyrillic_words=3,
        minimum_cyrillic_letter_ratio=0.65,
    ):
        raise IncompleteTranslation("translated body is not demonstrably Russian")
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
    narration = narration_preflight(body)
    if narration.get("status") != "PASS":
        issue_kinds = ", ".join(
            sorted({str(item.get("kind") or "unknown") for item in narration.get("issues") or []})
        )
        raise IncompleteTranslation(
            f"translation is not safe for deterministic narration: {issue_kinds}"
        )
    narration_body = str(narration.get("narration_text") or "").strip()
    if not narration_body:
        raise IncompleteTranslation("translation produced empty spoken narration")
    source_characters = len(re.sub(r"\s+", " ", source_body).strip())
    translated_characters = len(re.sub(r"\s+", " ", narration_body).strip())
    character_ceiling = max(
        config.max_character_floor,
        math.ceil(max(1, source_characters) * config.max_character_ratio),
    )
    if translated_characters > character_ceiling:
        raise IncompleteTranslation(
            "spoken narration character expansion exceeds the source-bound limit"
        )
    if any(
        len(token) > config.max_token_characters
        for token in (body.split() + narration_body.split())
    ):
        raise IncompleteTranslation(
            "translation contains an overlong narration token"
        )


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
        glossary = _call(provider, f"Extract a continuity glossary from the complete story and translate its title into natural Russian Cyrillic. "
            f"translated_title MUST contain only the translated Russian title, not analysis or alternatives. Return JSON "
            f'{{"translated_title":"...","glossary":{{}},"continuity":"..."}}. TITLE: {title}\nSTORY:\n{body}', config)
        state["glossary"] = glossary
        if checkpoint_path:
            _atomic_json(checkpoint_path, state)
    translated_title = str(glossary.get("translated_title") or "").strip()
    if not translated_title:
        raise IncompleteTranslation("chunk fallback glossary is missing translated_title")
    if not is_russian_text(
        translated_title,
        minimum_cyrillic_words=1,
        minimum_cyrillic_letter_ratio=0.50,
    ):
        repaired_title = _call(
            provider,
            "Translate only this exact story title into concise natural Russian Cyrillic. "
            "Do not explain, transliterate, list alternatives, or add analysis. "
            f'Return JSON {{"translated_title":"..."}}. TITLE: {title}',
            config,
            temperature=0.0,
        )
        translated_title = str(repaired_title.get("translated_title") or "").strip()
        if not is_russian_text(
            translated_title,
            minimum_cyrillic_words=1,
            minimum_cyrillic_letter_ratio=0.50,
        ):
            raise IncompleteTranslation(
                "chunk fallback title repair is not demonstrably Russian"
            )
        glossary = dict(glossary)
        glossary["translated_title"] = translated_title
        state["glossary"] = glossary
        if checkpoint_path:
            _atomic_json(checkpoint_path, state)
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
    title = str(story.get("title") or "")
    raw_body = str(story.get("body") or "")
    body = canonicalize_source_for_translation(raw_body)
    anchors = source_anchors(body)
    used_chunk_fallback = False
    saved_review: dict[str, Any] | None = None
    if review_checkpoint_path and review_checkpoint_path.is_file():
        candidate = json.loads(review_checkpoint_path.read_text(encoding="utf-8"))
        if (candidate.get("schema_version") == 2
                and candidate.get("source_sha256") == hashlib.sha256(body.encode()).hexdigest()
                and isinstance(candidate.get("current_translation"), dict)):
            saved_review = candidate
    try:
        if saved_review:
            translated = saved_review["current_translation"]
            _validate_translation(body, translated, config)
        elif chunk_checkpoint_path and chunk_checkpoint_path.is_file():
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
    revisions = int(saved_review.get("revisions_completed") or 0) if saved_review else 0
    review_history: list[dict[str, Any]] = list(saved_review.get("review_history") or []) if saved_review else []
    while True:
        review = _call(review_provider, _review_prompt(title, body, translated), config, temperature=0.0)
        review_history.append(review)
        if review_checkpoint_path:
            _atomic_json(review_checkpoint_path, {
                "schema_version": 2,
                "source_sha256": hashlib.sha256(body.encode()).hexdigest(),
                "revisions_completed": revisions,
                "review_history": review_history,
                "current_translation": translated,
            })
        if review.get("verdict") == "PASS" and review.get("ending_preserved") is True:
            break
        if review.get("verdict") != "REVISE":
            raise TranslationError("reviewer returned invalid or unsafe verdict")
        if revisions >= config.max_story_revisions:
            raise TranslationError("translation remains REVISE after maximum story revisions")
        revisions += 1
        translated = _apply_review_patches(title, body, translated, review)
        _validate_translation(body, translated, config)
        if review_checkpoint_path:
            _atomic_json(review_checkpoint_path, {
                "schema_version": 2,
                "source_sha256": hashlib.sha256(body.encode()).hexdigest(),
                "revisions_completed": revisions,
                "review_history": review_history,
                "current_translation": translated,
            })

    return {
        **story,
        "title": str(translated["title"]).strip(),
        "body": str(translated["body"]).strip(),
        "source_title": title,
        "source_body": raw_body,
        "translation_audit": {
            "model": config.model, "max_output_tokens": config.max_output_tokens,
            "full_story_first": True, "chunk_fallback": used_chunk_fallback,
            "revisions": revisions, "review": review, "source_anchors": anchors,
            "source_text_normalization": {
                "mode": "collapse_whitespace_preserve_paragraphs_v1",
                "applied": raw_body != body,
                "raw_sha256": hashlib.sha256(raw_body.encode()).hexdigest(),
                "working_sha256": hashlib.sha256(body.encode()).hexdigest(),
                "raw_character_count": len(raw_body),
                "working_character_count": len(body),
            },
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
