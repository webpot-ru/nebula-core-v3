"""Source-bound Russian packaging for one acc1 episode candidate."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, Callable

from acc1_language_gate import is_russian_text

from vectorengine_client import DEFAULT_GEMINI_MODEL, VectorEngineError, call_gemini_json


Provider = Callable[..., dict[str, Any]]
THUMBNAIL_PROMPT_SAFETY_SUFFIX = "no rendered text, no logos, no gore"
WORD_RE = re.compile(r"[^\W_]+", re.UNICODE)


class EpisodePackagingError(ValueError):
    pass


def _text(value: Any) -> str:
    return str(value or "").strip()


def _sources(script: dict[str, Any]) -> list[dict[str, Any]]:
    sources: list[dict[str, Any]] = []
    prompt = script.get("thread_prompt")
    if isinstance(prompt, dict):
        sources.append(prompt)
    for story in script.get("stories") or []:
        if isinstance(story, dict) and isinstance(story.get("source_snapshot"), dict):
            sources.append(story["source_snapshot"])
    return sources


def _source_id(source: dict[str, Any]) -> str:
    return _text(source.get("source_id") or source.get("post_id") or source.get("id"))


def build_thumbnail_prompt(source_backing: str) -> str:
    """Return the only allowed image prompt for a source-backed thumbnail.

    Keeping the visual direction deterministic prevents a provider response from
    attaching an invented event to a token quote copied from Reddit.  The image
    remains an explicitly non-photoreal editorial illustration, not evidence.
    """
    quote = _text(source_backing)
    return (
        "16:9 non-photoreal editorial illustration based only on this exact "
        "Reddit excerpt, without adding events, people, identities, evidence, "
        f"or details: «{quote}». Keep the left side clean for later title placement; "
        f"{THUMBNAIL_PROMPT_SAFETY_SUFFIX}"
    )


def build_youtube_description(disclosure: str, source_urls: list[str]) -> str:
    """Build a neutral description with no model-authored factual claims."""
    unique_urls = list(dict.fromkeys(_text(url) for url in source_urls if _text(url)))
    source_lines = "\n".join(f"- {url}" for url in unique_urls)
    return (
        f"{_text(disclosure)}\n\n"
        "В выпуске пересказываются публикации пользователей Reddit. "
        "Это не независимое подтверждение описанных событий.\n\n"
        f"Источники Reddit:\n{source_lines}"
    )


def _winner_packaging_options(playoff: dict[str, Any]) -> list[dict[str, Any]] | None:
    if "winner_packaging_options" not in playoff:
        return None
    options = playoff.get("winner_packaging_options")
    if (
        not isinstance(options, list)
        or len(options) != 3
        or any(not isinstance(option, dict) for option in options)
    ):
        raise EpisodePackagingError(
            "playoff.winner_packaging_options must contain exactly three objects"
        )
    return options


def build_prompt(script: dict[str, Any], playoff: dict[str, Any]) -> str:
    winner = playoff.get("winner") if isinstance(playoff.get("winner"), dict) else {}
    locked_options = _winner_packaging_options(playoff)
    sources = _sources(script)
    summaries = [
        {
            "source_id": item.get("source_id") or item.get("post_id") or item.get("id"),
            "title": item.get("title"),
            "body": str(item.get("body") or item.get("source_body") or "")[:6000],
            "source_url": item.get("source_url") or item.get("url"),
            "truth_mode": item.get("truth_mode"),
        }
        for item in sources
    ]
    if locked_options is not None:
        return f"""
Select the strongest honest YouTube packaging option for one Russian long-form Reddit episode.

Rules:
- The three supplied options are an immutable lock and already source-validated.
- Choose exactly one option for click-through potential, first-screen clarity, retention promise, and honesty.
- Do not rewrite, translate, expand, or return the options.
- selected_option_index must be 0, 1, or 2.
- Return strict JSON only.

Episode: {json.dumps({
    'format': script.get('episode_format'),
    'pillar': script.get('pillar'),
    'title_ru': script.get('title_ru'),
    'truth_disclosure_ru': script.get('truth_disclosure_ru'),
    'winning_topic': winner,
    'winner_packaging_options': locked_options,
}, ensure_ascii=False)}

JSON shape:
{{"selected_option_index": 0}}
""".strip()
    packaging_rule = "- Return exactly three materially different title/thumbnail/first-screen angles."
    return f"""
Create high-retention but strictly honest Russian YouTube packaging for one long-form Reddit episode.

Rules:
- Work only from the supplied exact source text and the winning topic decision.
{packaging_rule}
- YouTube title: at most 95 characters. Thumbnail text: at most 32 characters and two short lines.
- source_backing must be a short exact quote copied from one supplied source body.
- Do not call an unverified Reddit account a confirmed fact. Do not call fiction real.
- youtube_description must equal this deterministic neutral template exactly: {build_youtube_description(_text(script.get('truth_disclosure_ru')), [_text(item.get('source_url') or item.get('url')) for item in sources])}.
- thumbnail_source_id must name one exact supplied source_id.
- thumbnail_source_backing must be a short exact quote from that named source body.
- thumbnail_prompt must equal this deterministic template exactly, substituting only the exact thumbnail_source_backing quote: {build_thumbnail_prompt('<thumbnail_source_backing>')}.
- The thumbnail scene must not invent events or visual evidence.
- selected_option_index must be 0, 1, or 2. risk_flags must be an empty array only when every promise is supported.
- Return strict JSON only.

Episode: {json.dumps({
    'format': script.get('episode_format'),
    'pillar': script.get('pillar'),
    'title_ru': script.get('title_ru'),
    'truth_disclosure_ru': script.get('truth_disclosure_ru'),
    'winning_topic': winner,
    'winner_packaging_options': locked_options,
    'sources': summaries,
}, ensure_ascii=False)}

JSON shape:
{{
  "packaging_options": [
    {{"youtube_title":"", "thumbnail_text":"", "first_screen_promise":"", "angle":"", "source_id":"", "source_backing":""}}
  ],
  "selected_option_index": 0,
  "youtube_description": "",
  "thumbnail_prompt": "",
  "thumbnail_source_id": "",
  "thumbnail_source_backing": "",
  "language": "ru",
  "risk_flags": []
}}
""".strip()


def validate_packaging(
    payload: dict[str, Any],
    script: dict[str, Any],
    playoff: dict[str, Any] | None = None,
) -> list[str]:
    failures: list[str] = []
    sources = _sources(script)
    urls = [
        _text(item.get("source_url") or item.get("url"))
        for item in sources
        if _text(item.get("source_url") or item.get("url"))
    ]
    options = payload.get("packaging_options")
    if not isinstance(options, list) or len(options) != 3:
        failures.append("packaging_options must contain exactly three options")
        options = []
    locked_options: list[dict[str, Any]] | None = None
    if isinstance(playoff, dict):
        try:
            locked_options = _winner_packaging_options(playoff)
        except EpisodePackagingError as exc:
            failures.append(str(exc))
        if locked_options is not None and options != locked_options:
            failures.append(
                "packaging_options must exactly equal playoff.winner_packaging_options"
            )
    signatures: set[tuple[str, str, str]] = set()
    angles: set[str] = set()
    for index, option in enumerate(options):
        if not isinstance(option, dict):
            failures.append(f"packaging_options[{index}] must be an object")
            continue
        title = _text(option.get("youtube_title"))
        thumb = _text(option.get("thumbnail_text"))
        first = _text(option.get("first_screen_promise"))
        angle = _text(option.get("angle")).casefold()
        option_source_id = _text(option.get("source_id"))
        backing = _text(option.get("source_backing"))
        if not title or len(title) > 95:
            failures.append(f"packaging_options[{index}].youtube_title is empty or too long")
        elif not is_russian_text(title, minimum_cyrillic_letter_ratio=0.50):
            failures.append(f"packaging_options[{index}].youtube_title must be Russian")
        if not thumb or len(thumb) > 32 or len([line for line in thumb.splitlines() if line.strip()]) > 2:
            failures.append(f"packaging_options[{index}].thumbnail_text is empty or too long")
        elif not is_russian_text(thumb, minimum_cyrillic_letter_ratio=0.50):
            failures.append(f"packaging_options[{index}].thumbnail_text must be Russian")
        if not first:
            failures.append(f"packaging_options[{index}].first_screen_promise is required")
        elif not is_russian_text(first, minimum_cyrillic_letter_ratio=0.55):
            failures.append(f"packaging_options[{index}].first_screen_promise must be Russian")
        if not angle:
            failures.append(f"packaging_options[{index}].angle is required")
        matching_option_sources = [
            source for source in sources if _source_id(source) == option_source_id
        ]
        if len(matching_option_sources) != 1:
            failures.append(
                f"packaging_options[{index}].source_id must name exactly one script source"
            )
        backing_words = [match.group(0).casefold() for match in WORD_RE.finditer(backing)]
        if len(backing) < 24 or len(backing_words) < 4 or len(set(backing_words)) < 3:
            failures.append(
                f"packaging_options[{index}].source_backing is too generic"
            )
        option_body = (
            str(
                matching_option_sources[0].get("body")
                or matching_option_sources[0].get("source_body")
                or ""
            )
            if len(matching_option_sources) == 1 else ""
        )
        if not backing or backing not in option_body:
            failures.append(
                f"packaging_options[{index}].source_backing must be an exact quote from source_id"
            )
        signatures.add((title.casefold(), thumb.casefold(), first.casefold()))
        angles.add(angle)
    if len(signatures) != 3 or len(angles) != 3:
        failures.append("packaging options must be materially distinct")

    selected = payload.get("selected_option_index")
    if isinstance(selected, bool) or not isinstance(selected, int) or selected not in range(3):
        failures.append("selected_option_index must be 0, 1, or 2")
    description = _text(payload.get("youtube_description"))
    disclosure = _text(script.get("truth_disclosure_ru"))
    if not disclosure or disclosure not in description:
        failures.append("youtube_description must include the exact truth disclosure")
    for url in urls:
        if url not in description:
            failures.append(f"youtube_description is missing source URL: {url}")
    if description and description != build_youtube_description(disclosure, urls):
        failures.append(
            "youtube_description must equal the deterministic neutral source template"
        )
    if payload.get("language") != "ru":
        failures.append("language must be ru")
    thumbnail_prompt = _text(payload.get("thumbnail_prompt"))
    if not thumbnail_prompt:
        failures.append("thumbnail_prompt is required")
    thumbnail_source_id = _text(payload.get("thumbnail_source_id"))
    thumbnail_source_backing = _text(payload.get("thumbnail_source_backing"))
    if not thumbnail_source_id:
        failures.append("thumbnail_source_id is required")
    matching_sources = [source for source in sources if _source_id(source) == thumbnail_source_id]
    if thumbnail_source_id and len(matching_sources) != 1:
        failures.append("thumbnail_source_id must name exactly one script source")
    if not thumbnail_source_backing:
        failures.append("thumbnail_source_backing is required")
    backing_words = [
        match.group(0).casefold()
        for match in WORD_RE.finditer(thumbnail_source_backing)
    ]
    if (
        thumbnail_source_backing
        and (
            len(thumbnail_source_backing) < 24
            or len(backing_words) < 4
            or len(set(backing_words)) < 3
        )
    ):
        failures.append("thumbnail_source_backing is too generic")
    if thumbnail_source_backing and len(matching_sources) == 1:
        named_body = str(
            matching_sources[0].get("body")
            or matching_sources[0].get("source_body")
            or ""
        )
        if thumbnail_source_backing not in named_body:
            failures.append(
                "thumbnail_source_backing must be an exact quote from thumbnail_source_id"
            )
    if thumbnail_source_backing and thumbnail_source_backing not in thumbnail_prompt:
        failures.append("thumbnail_prompt must contain thumbnail_source_backing verbatim")
    if (
        thumbnail_prompt
        and thumbnail_source_backing
        and thumbnail_prompt != build_thumbnail_prompt(thumbnail_source_backing)
    ):
        failures.append(
            "thumbnail_prompt must equal the deterministic source-bound template"
        )
    if (
        thumbnail_prompt
        and THUMBNAIL_PROMPT_SAFETY_SUFFIX not in thumbnail_prompt.casefold()
    ):
        failures.append(
            "thumbnail_prompt must contain the no-text/no-logo/no-gore safety suffix"
        )
    risk_flags = payload.get("risk_flags")
    if risk_flags != []:
        failures.append("risk_flags must be an empty array before production")
    return failures


def generate_packaging(
    script: dict[str, Any],
    playoff: dict[str, Any],
    *,
    provider: Provider = call_gemini_json,
    model: str = DEFAULT_GEMINI_MODEL,
) -> dict[str, Any]:
    payload = provider(
        prompt=build_prompt(script, playoff),
        model=model,
        temperature=0.25,
        max_output_tokens=4096,
    )
    if not isinstance(payload, dict):
        raise EpisodePackagingError("packaging provider returned a non-object")
    locked_options = _winner_packaging_options(playoff)
    if locked_options is not None:
        selected = payload.get("selected_option_index")
        if isinstance(selected, bool) or not isinstance(selected, int) or selected not in range(3):
            raise EpisodePackagingError("selected_option_index must be 0, 1, or 2")
        selected_option = locked_options[selected]
        source_id = _text(selected_option.get("source_id"))
        source_backing = _text(selected_option.get("source_backing"))
        sources = _sources(script)
        payload = {
            "packaging_options": locked_options,
            "selected_option_index": selected,
            "youtube_description": build_youtube_description(
                _text(script.get("truth_disclosure_ru")),
                [_text(item.get("source_url") or item.get("url")) for item in sources],
            ),
            "thumbnail_prompt": build_thumbnail_prompt(source_backing),
            "thumbnail_source_id": source_id,
            "thumbnail_source_backing": source_backing,
            "language": "ru",
            "risk_flags": [],
        }
    failures = validate_packaging(payload, script, playoff)
    if failures:
        raise EpisodePackagingError("; ".join(failures))
    result = dict(payload)
    result["episode_plan_sha256"] = script.get("episode_plan_sha256")
    result["publication_authorized"] = False
    result["status"] = "PASS"
    return result


def _read_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise EpisodePackagingError(f"{path} must contain a JSON object")
    return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--episode-script", required=True)
    parser.add_argument("--playoff", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--model", default=DEFAULT_GEMINI_MODEL)
    parser.add_argument("--confirm-spend", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    script = _read_object(Path(args.episode_script))
    playoff = _read_object(Path(args.playoff))
    if args.dry_run:
        print(json.dumps({"status": "dry_run", "would_call_gemini": False, "prompt_chars": len(build_prompt(script, playoff))}))
        return 0
    if not args.confirm_spend:
        raise EpisodePackagingError("refusing Gemini packaging without --confirm-spend")
    result = generate_packaging(script, playoff, model=args.model)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, json.JSONDecodeError, VectorEngineError, EpisodePackagingError) as exc:
        print(f"ERROR: {exc}")
        raise SystemExit(1)
