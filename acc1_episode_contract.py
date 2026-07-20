"""Deterministic production-script contract for acc1 SAGA/BUNDLE/THREAD."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from acc1_language_gate import is_russian_text

from acc1_episode_manifest import disclosure_for_truth_mode, validate_episode_manifest


SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
WORD_RE = re.compile(r"[^\W_]+", re.UNICODE)
TRUTH_MODES = {"fiction", "unverified_personal_account"}
INTRO_CONTRACT_VERSION = 2
MID_STORY_CTA_CONTRACT_VERSION = 1
INTRO_PART_ORDER = (
    "cold_open",
    "truth_disclosure",
    "first_story_cue",
)
SOURCE_NOTE_RU = "Оригинальные публикации Reddit указаны в описании."
SUPPORT_THANKS_RU = "Спасибо всем, кто помогает каналу расти."
GENERIC_BRAND_STING_RU = (
    "Вы слушаете Chonker Talks. Устраивайтесь поудобнее. Мы начинаем."
)
DARK_BRAND_STING_RU = (
    "Вы слушаете Chonker Talks. Свет можно оставить включённым. Мы начинаем."
)
MAX_INTRO_WORDS = 60
MAX_MID_STORY_CTA_WORDS = 34

_STORY_COUNT_PHRASES = {
    1: "одна законченная история",
    2: "две законченные истории",
    3: "три законченные истории",
    4: "четыре законченные истории",
    5: "пять законченных историй",
    6: "шесть законченных историй",
}
_RESPONSE_COUNT_WORDS = {
    8: "восемь",
    9: "девять",
    10: "десять",
    11: "одиннадцать",
    12: "двенадцать",
    13: "тринадцать",
    14: "четырнадцать",
    15: "пятнадцать",
}


def canonical_hash(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _text(value: Any) -> str:
    return str(value or "").strip()


def _spoken_title(value: Any) -> str:
    title = re.sub(r"\s+", " ", _text(value)).strip(" \"'«»")
    if not title:
        raise ValueError("first translated title is required for the intro")
    title = re.sub(r"(?<!\d)911(?!\d)", "девять один один", title)
    head = re.split(r"\s*(?::|—|–)\s*", title, maxsplit=1)[0].strip()
    if 4 <= len(WORD_RE.findall(head)) <= 14:
        return head
    return title


def _episode_promise_ru(
    *, episode_format: str, source_count: int, response_count: int,
) -> str:
    format_id = _text(episode_format).upper()
    if format_id == "SAGA":
        if source_count != 1:
            raise ValueError("SAGA intro requires exactly one source")
        return "Сегодня — одна большая законченная история с Reddit."
    if format_id == "BUNDLE":
        phrase = _STORY_COUNT_PHRASES.get(source_count)
        if not phrase:
            raise ValueError("BUNDLE intro requires one to six story sources")
        return f"Сегодня — {phrase} с Reddit."
    if format_id == "THREAD":
        count_word = _RESPONSE_COUNT_WORDS.get(response_count)
        if source_count != response_count + 1 or not count_word:
            raise ValueError("THREAD intro requires one prompt and eight to fifteen responses")
        return f"Сегодня — одна тема и {count_word} полных ответов с Reddit."
    raise ValueError("intro episode_format must be SAGA, BUNDLE, or THREAD")


def _first_story_cue_ru(episode_format: str, title_ru: str) -> str:
    title = _spoken_title(title_ru)
    quoted_title = f"«{title}»" + (
        "" if title.endswith((".", "!", "?", "…")) else "."
    )
    format_id = _text(episode_format).upper()
    if format_id == "SAGA":
        return f"Название поста. {quoted_title}"
    if format_id == "BUNDLE":
        return f"История первая. {quoted_title}"
    if format_id == "THREAD":
        return f"Тема выпуска. {quoted_title}"
    raise ValueError("intro episode_format must be SAGA, BUNDLE, or THREAD")


def build_intro_contract(
    *,
    cold_open: dict[str, Any],
    episode_format: str,
    pillar: str,
    source_count: int,
    response_count: int,
    first_title_ru: str,
    truth_disclosure: str,
) -> dict[str, Any]:
    """Build the deterministic, source-bound acc1 spoken intro."""

    normalized_cold_open = {
        "text": _text(cold_open.get("text")),
        "source_id": _text(cold_open.get("source_id")),
        "source_quote": _text(cold_open.get("source_quote")),
    }
    if not all(normalized_cold_open.values()):
        raise ValueError("cold_open text, source_id, and source_quote are required")
    # Validate the format/count envelope even though the compact spoken intro
    # deliberately does not narrate a generic Reddit-format promise.
    _episode_promise_ru(
        episode_format=episode_format,
        source_count=source_count,
        response_count=response_count,
    )
    parts = [
        {"kind": "cold_open", "text": normalized_cold_open["text"]},
        {"kind": "truth_disclosure", "text": _text(truth_disclosure)},
        {
            "kind": "first_story_cue",
            "text": _first_story_cue_ru(episode_format, first_title_ru),
        },
    ]
    intro_ru = " ".join(part["text"] for part in parts)
    return {
        "version": INTRO_CONTRACT_VERSION,
        "cold_open": normalized_cold_open,
        "parts": parts,
        "intro_ru": intro_ru,
        "spoken_word_count": len(WORD_RE.findall(intro_ru)),
        "verified_supporter_manifest": None,
    }


def validate_intro_contract(
    contract: Any,
    *,
    intro_ru: str,
    episode_format: str,
    pillar: str,
    sources: list[dict[str, Any]],
    story_titles: list[str],
    expected_disclosure: str,
    expected_cold_open_sha256: str,
) -> list[str]:
    failures: list[str] = []
    if not isinstance(contract, dict):
        return ["intro_contract must be an object"]
    cold_open = contract.get("cold_open")
    if not isinstance(cold_open, dict):
        return ["intro_contract.cold_open must be an object"]
    source_id = _text(cold_open.get("source_id"))
    source_quote = _text(cold_open.get("source_quote"))
    source = next((item for item in sources if _source_id(item) == source_id), None)
    if source is None:
        failures.append("intro cold_open.source_id must name an exact episode source")
    elif not source_quote or source_quote not in _source_body(source):
        failures.append("intro cold_open.source_quote must be exact source evidence")
    cold_text = _text(cold_open.get("text"))
    cold_words = len(WORD_RE.findall(cold_text))
    if not 8 <= cold_words <= 30:
        failures.append("intro cold_open.text must contain 8-30 words")
    elif not is_russian_text(
        cold_text, minimum_cyrillic_words=3, minimum_cyrillic_letter_ratio=0.55,
    ):
        failures.append("intro cold_open.text must be demonstrably Russian")
    actual_cold_sha = canonical_hash({
        "text": cold_text,
        "source_id": source_id,
        "source_quote": source_quote,
    })
    if actual_cold_sha != _text(expected_cold_open_sha256):
        failures.append("intro cold open does not match the topic-playoff winner")
    response_count = sum(
        1
        for item in sources
        if _text(item.get("source_role") or item.get("role")).lower() == "response"
    )
    try:
        expected = build_intro_contract(
            cold_open={
                "text": cold_text,
                "source_id": source_id,
                "source_quote": source_quote,
            },
            episode_format=episode_format,
            pillar=pillar,
            source_count=len(sources),
            response_count=response_count,
            first_title_ru=story_titles[0] if story_titles else "",
            truth_disclosure=expected_disclosure,
        )
    except ValueError as exc:
        failures.append(str(exc))
        return failures
    if contract != expected:
        failures.append(
            "intro_contract must exactly match the approved deterministic structure"
        )
    if _text(intro_ru) != expected["intro_ru"]:
        failures.append("intro_ru must exactly match intro_contract parts and order")
    if expected["intro_ru"].count(expected_disclosure) != 1:
        failures.append("truth disclosure must appear exactly once in the intro")
    if expected["spoken_word_count"] > MAX_INTRO_WORDS:
        failures.append(f"intro must contain at most {MAX_INTRO_WORDS} spoken words")
    return failures


def build_outro_prompt(
    *, episode_format: str, pillar: str, first_source: dict[str, Any],
) -> str:
    """Return a grounded discussion question without asserting Reddit as fact."""

    source_text = " ".join((
        _text(first_source.get("title")),
        _source_body(first_source),
    )).lower()
    if _text(pillar) == "strange_dark_unexplained":
        if re.search(r"звон|телефон|диспетчер|911|call|phone|dispatch", source_text):
            return (
                "Вы бы ответили на такой звонок? А если у вас есть история, "
                "от которой до сих пор не по себе, расскажите её в комментариях."
            )
        return (
            "Есть история, от которой вам до сих пор не по себе? "
            "Расскажите её в комментариях."
        )
    if _text(episode_format).upper() == "THREAD":
        return "Какой ответ в этой теме вы бы написали сами? Расскажите в комментариях."
    if _text(pillar) == "relationships_family":
        return "Чью сторону вы бы заняли в этой истории — и почему? Расскажите в комментариях."
    if _text(pillar) == "work_money_consumer":
        return "Как бы вы поступили на этом месте? Расскажите в комментариях."
    return "Что в этой истории вы бы сделали иначе? Расскажите в комментариях."


def build_mid_story_cta_contract(
    *,
    episode_format: str,
    pillar: str,
    anchor_source: dict[str, Any],
    anchor_index: int,
    source_count: int,
) -> dict[str, Any]:
    """Build one source-bound mid-story discussion CTA.

    The CTA is deliberately framed as a viewer decision at a natural break,
    not as a generic like/subscribe interruption.  Its evidence quote must
    exist verbatim in the exact source snapshot used by the episode.
    """

    source_id = _source_id(anchor_source)
    body = _source_body(anchor_source)
    if not source_id or not body:
        raise ValueError("mid-story CTA requires an exact anchor source")
    words = body.split()
    quote = " ".join(words[: min(10, len(words))]).strip()
    if len(WORD_RE.findall(quote)) < 3:
        raise ValueError("mid-story CTA source quote is too short")
    if quote not in body:
        raise ValueError("mid-story CTA source quote must be exact source evidence")

    format_id = _text(episode_format).upper()
    pillar_id = _text(pillar)
    if format_id == "THREAD":
        question = "Какой ответ вы бы написали на месте автора этой темы?"
    elif pillar_id == "relationships_family":
        question = "На чьей стороне вы сейчас — и почему?"
    elif pillar_id in {"work_money_justice", "work_money_consumer"}:
        question = "Вы бы уже вмешались или сначала собрали доказательства?"
    elif pillar_id == "strange_dark_unexplained":
        question = "В какой момент вы бы поняли, что это уже не совпадение?"
    else:
        question = "Что бы вы сделали на этом месте?"
    cta_ru = (
        f"{question} Напишите в комментариях. "
        "Если нравятся полные истории без выдуманных продолжений — подписывайтесь. Продолжаем."
    )
    return {
        "version": MID_STORY_CTA_CONTRACT_VERSION,
        "placement": {
            "after_source_index": int(anchor_index),
            "source_count": int(source_count),
            "policy": "natural_break_after_anchor_source",
        },
        "source_anchor": {
            "source_id": source_id,
            "source_quote": quote,
            "source_quote_sha256": hashlib.sha256(quote.encode("utf-8")).hexdigest(),
        },
        "cta_ru": cta_ru,
        "spoken_word_count": len(WORD_RE.findall(cta_ru)),
    }


def validate_mid_story_cta_contract(
    contract: Any,
    *,
    mid_story_cta_ru: str,
    episode_format: str,
    pillar: str,
    sources: list[dict[str, Any]],
) -> list[str]:
    failures: list[str] = []
    if not isinstance(contract, dict):
        return ["mid_story_cta_contract must be an object"]
    placement = contract.get("placement")
    anchor = contract.get("source_anchor")
    if not isinstance(placement, dict):
        return ["mid_story_cta_contract.placement must be an object"]
    if not isinstance(anchor, dict):
        return ["mid_story_cta_contract.source_anchor must be an object"]
    try:
        anchor_index = int(placement.get("after_source_index"))
    except (TypeError, ValueError):
        failures.append("mid-story CTA placement index is invalid")
        anchor_index = 0
    if anchor_index < 1 or anchor_index > len(sources):
        failures.append("mid-story CTA placement must reference an episode source")
        anchor_source = sources[0] if sources else {}
    else:
        anchor_source = sources[anchor_index - 1]
    if int(placement.get("source_count") or 0) != len(sources):
        failures.append("mid-story CTA source count drifted")
    source_id = _text(anchor.get("source_id"))
    source_quote = _text(anchor.get("source_quote"))
    if source_id != _source_id(anchor_source):
        failures.append("mid-story CTA source_id must match its placement source")
    if not source_quote or source_quote not in _source_body(anchor_source):
        failures.append("mid-story CTA source_quote must be exact source evidence")
    expected_quote_sha = hashlib.sha256(source_quote.encode("utf-8")).hexdigest()
    if _text(anchor.get("source_quote_sha256")) != expected_quote_sha:
        failures.append("mid-story CTA source quote checksum is invalid")
    try:
        expected = build_mid_story_cta_contract(
            episode_format=episode_format,
            pillar=pillar,
            anchor_source=anchor_source,
            anchor_index=anchor_index,
            source_count=len(sources),
        )
    except ValueError as exc:
        failures.append(str(exc))
        return failures
    if contract != expected:
        failures.append("mid_story_cta_contract must exactly match the approved deterministic structure")
    if _text(mid_story_cta_ru) != expected["cta_ru"]:
        failures.append("mid_story_cta_ru must exactly match the deterministic CTA contract")
    if expected["spoken_word_count"] > MAX_MID_STORY_CTA_WORDS:
        failures.append(f"mid-story CTA must contain at most {MAX_MID_STORY_CTA_WORDS} spoken words")
    if not is_russian_text(
        expected["cta_ru"], minimum_cyrillic_words=4, minimum_cyrillic_letter_ratio=0.55,
    ):
        failures.append("mid_story_cta_ru must be demonstrably Russian")
    return failures


def _source_id(snapshot: dict[str, Any]) -> str:
    return _text(snapshot.get("source_id") or snapshot.get("post_id") or snapshot.get("id"))


def _source_body(snapshot: dict[str, Any]) -> str:
    return str(snapshot.get("body") or snapshot.get("source_body") or "")


def _source_body_sha(snapshot: dict[str, Any]) -> str:
    return _text(snapshot.get("body_sha256") or snapshot.get("source_body_sha256"))


def _source_url(snapshot: dict[str, Any]) -> str:
    return _text(snapshot.get("source_url") or snapshot.get("url"))


def truth_disclosure_ru(truth_modes: set[str], *, source_count: int = 1) -> str:
    if len(truth_modes) == 1:
        truth_mode = next(iter(truth_modes))
        if source_count <= 1:
            return disclosure_for_truth_mode(truth_mode)
        if truth_mode == "fiction":
            return "Это художественные истории с Reddit."
        if truth_mode == "unverified_personal_account":
            return (
                "Это личные рассказы пользователей Reddit, "
                "не подтверждённые независимо."
            )
    raise ValueError("one episode must not mix fiction and unverified personal accounts")


def _validate_snapshot(snapshot: Any, prefix: str) -> tuple[dict[str, Any] | None, list[str]]:
    failures: list[str] = []
    if not isinstance(snapshot, dict):
        return None, [f"{prefix} must be an object"]
    source_id = _source_id(snapshot)
    body = _source_body(snapshot)
    body_sha = _source_body_sha(snapshot)
    url = _source_url(snapshot)
    truth_mode = _text(snapshot.get("truth_mode"))
    if not source_id:
        failures.append(f"{prefix}.source_id is required")
    if not body.strip():
        failures.append(f"{prefix}.body is required")
    actual_sha = hashlib.sha256(body.encode("utf-8")).hexdigest()
    if body_sha != actual_sha:
        failures.append(f"{prefix}.body_sha256 does not match body")
    if not url.startswith("https://www.reddit.com/"):
        failures.append(f"{prefix}.source_url must be a canonical Reddit URL")
    if truth_mode not in TRUTH_MODES:
        failures.append(f"{prefix}.truth_mode is invalid")
    for field in ("author", "subreddit"):
        if not _text(snapshot.get(field)):
            failures.append(f"{prefix}.{field} is required")
    normalized = dict(snapshot)
    normalized.update(
        {
            "source_id": source_id,
            "body": body,
            "body_sha256": actual_sha,
            "source_url": url,
            "truth_mode": truth_mode,
            "word_count": len(WORD_RE.findall(body)),
        }
    )
    return normalized, failures


def _source_bound_creative_item(
    value: Any,
    *,
    sources_by_id: dict[str, dict[str, Any]],
    direction_field: str,
    prefix: str,
    failures: list[str],
) -> dict[str, str] | None:
    if not isinstance(value, dict):
        failures.append(f"{prefix} must be an object")
        return None
    direction = _text(value.get(direction_field))
    source_id = _text(value.get("source_id"))
    source_quote = _text(value.get("source_quote"))
    source = sources_by_id.get(source_id)
    if not direction:
        failures.append(f"{prefix}.{direction_field} is required")
    if source is None:
        failures.append(f"{prefix}.source_id must name an exact script source")
    if not source_quote or source is None or source_quote not in source["body"]:
        failures.append(f"{prefix}.source_quote must be an exact quote from the named source")
    if not direction or source is None or not source_quote or source_quote not in source["body"]:
        return None
    return {
        direction_field: direction,
        "source_id": source_id,
        "source_quote": source_quote,
    }


def validate_episode_script(
    script: dict[str, Any],
    *,
    plan: dict[str, Any],
    playoff: dict[str, Any],
) -> dict[str, Any]:
    failures: list[str] = []
    plan_report = validate_episode_manifest(plan)
    expected_plan_sha = str(plan.get("episode_plan_sha256") or "")
    if plan_report.get("status") != "PASS":
        failures.append("episode plan must be a valid immutable LOCKED manifest")
    if _text(script.get("episode_plan_sha256")) != expected_plan_sha:
        failures.append("episode script is not bound to the exact episode plan")
    expected_playoff_sha = _text(playoff.get("playoff_sha256"))
    if not SHA256_RE.fullmatch(expected_playoff_sha):
        failures.append("playoff_sha256 is invalid")
    elif _text(script.get("playoff_sha256")) != expected_playoff_sha:
        failures.append("episode script is not bound to the winning topic playoff")
    if playoff.get("status") != "READY_FOR_SCRIPTING":
        failures.append("topic playoff must be READY_FOR_SCRIPTING")
    if script.get("publication_authorized") is not False:
        failures.append("publication_authorized must remain false")

    format_id = _text(script.get("episode_format")).upper()
    pilot_id = _text(script.get("pilot_id"))
    pillar = _text(script.get("pillar"))
    if format_id != _text(plan.get("format")).upper():
        failures.append("episode_format does not match plan")
    if pilot_id != _text(plan.get("pilot_id")):
        failures.append("pilot_id does not match plan")
    if pillar != _text(plan.get("pillar")):
        failures.append("pillar does not match plan")
    for field in ("title_ru", "intro_ru", "mid_story_cta_ru", "outro_ru", "truth_disclosure_ru"):
        value = _text(script.get(field))
        if not value:
            failures.append(f"{field} is required")
        elif not is_russian_text(
            value,
            minimum_cyrillic_words=1 if field == "title_ru" else 2,
            minimum_cyrillic_letter_ratio=0.40 if field == "title_ru" else 0.55,
        ):
            failures.append(f"{field} must be demonstrably Russian")

    stories_raw = script.get("stories")
    if not isinstance(stories_raw, list):
        failures.append("stories must be a list")
        stories_raw = []
    normalized_sources: list[dict[str, Any]] = []
    story_roles: list[str] = []
    for index, story in enumerate(stories_raw):
        prefix = f"stories[{index}]"
        if not isinstance(story, dict):
            failures.append(f"{prefix} must be an object")
            continue
        snapshot, source_failures = _validate_snapshot(story.get("source_snapshot"), f"{prefix}.source_snapshot")
        failures.extend(source_failures)
        if snapshot:
            normalized_sources.append(snapshot)
        for field in ("title_ru", "narration_ru"):
            value = _text(story.get(field))
            if not value:
                failures.append(f"{prefix}.{field} is required")
            elif not is_russian_text(
                value,
                minimum_cyrillic_words=1 if field == "title_ru" else 3,
                minimum_cyrillic_letter_ratio=0.50 if field == "title_ru" else 0.65,
            ):
                failures.append(f"{prefix}.{field} must be demonstrably Russian")
        for field in ("hook_ru", "transition_after_ru"):
            value = _text(story.get(field))
            if value and not is_russian_text(
                value,
                minimum_cyrillic_words=1,
                minimum_cyrillic_letter_ratio=0.55,
            ):
                failures.append(f"{prefix}.{field} must be demonstrably Russian")
        role = _text(story.get("narration_role") or "narrator").lower()
        if role not in {"narrator", "comment"}:
            failures.append(f"{prefix}.narration_role must be narrator or comment")
        story_roles.append(role)
        audit = story.get("translation_audit")
        if not isinstance(audit, dict) or (audit.get("review") or {}).get("verdict") != "PASS":
            failures.append(f"{prefix} translation must have an independent PASS review")
        if not _text(story.get("ending_preserved_evidence")):
            failures.append(f"{prefix}.ending_preserved_evidence is required")

    if format_id == "THREAD":
        source_roles = [_text(source.get("source_role") or "response").lower() for source in normalized_sources]
        prompt_indexes = [index for index, role in enumerate(source_roles) if role == "prompt"]
        response_indexes = [index for index, role in enumerate(source_roles) if role == "response"]
        if prompt_indexes != [0] or not 8 <= len(response_indexes) <= 15:
            failures.append("THREAD requires one first prompt and 8-15 response sources")
        if story_roles and story_roles[0] != "narrator":
            failures.append("THREAD prompt must use the narrator voice role")
        if any(story_roles[index] != "comment" for index in response_indexes if index < len(story_roles)):
            failures.append("THREAD responses must use the comment voice role")
        response_words = sum(normalized_sources[index]["word_count"] for index in response_indexes)
        if not 1950 <= response_words <= 3250:
            failures.append("THREAD responses must contain 1950-3250 source words")
    elif format_id == "SAGA":
        if len(stories_raw) != 1:
            failures.append("SAGA requires exactly one story")
        if any(role != "narrator" for role in story_roles):
            failures.append("SAGA must use the narrator voice role")
    elif format_id == "BUNDLE":
        expected = (2, 3) if pilot_id == "pilot_01" else (3, 5) if pilot_id == "pilot_02" else None
        if expected is None or not expected[0] <= len(stories_raw) <= expected[1]:
            failures.append("BUNDLE story count does not match its pilot contract")
        if any(role != "narrator" for role in story_roles):
            failures.append("BUNDLE must use the narrator voice role")
    else:
        failures.append("episode_format must be SAGA, BUNDLE, or THREAD")

    if format_id in {"SAGA", "BUNDLE"}:
        total_words = sum(source["word_count"] for source in normalized_sources)
        if not 2340 <= total_words <= 3900:
            failures.append(f"{format_id} aggregate source words must be 2340-3900")

    sources_by_id = {source["source_id"]: source for source in normalized_sources}
    raw_beats = script.get("source_story_beats")
    normalized_beats: list[dict[str, str]] = []
    if not isinstance(raw_beats, list) or not 3 <= len(raw_beats) <= 12:
        failures.append("source_story_beats must contain 3-12 source-bound beats")
    if isinstance(raw_beats, list):
        for index, item in enumerate(raw_beats):
            normalized = _source_bound_creative_item(
                item,
                sources_by_id=sources_by_id,
                direction_field="beat",
                prefix=f"source_story_beats[{index}]",
                failures=failures,
            )
            if normalized is not None:
                normalized_beats.append(normalized)

    raw_originality = script.get("originality_plan")
    normalized_originality: dict[str, dict[str, str]] = {}
    if not isinstance(raw_originality, dict):
        failures.append("originality_plan must be an object")
    else:
        for field in ("editorial_frame", "visual_direction", "sound_direction"):
            normalized = _source_bound_creative_item(
                raw_originality.get(field),
                sources_by_id=sources_by_id,
                direction_field="direction",
                prefix=f"originality_plan.{field}",
                failures=failures,
            )
            if normalized is not None:
                normalized_originality[field] = normalized

    creative_plan_sha = canonical_hash({
        "story_beats": normalized_beats,
        "originality_plan": normalized_originality,
    })
    winner = playoff.get("winner") if isinstance(playoff.get("winner"), dict) else {}
    if creative_plan_sha != winner.get("creative_plan_sha256"):
        failures.append("episode script creative plan does not match the playoff winner")

    truth_modes = {source["truth_mode"] for source in normalized_sources if source.get("truth_mode")}
    try:
        expected_disclosure = truth_disclosure_ru(
            truth_modes, source_count=len(normalized_sources),
        )
    except ValueError as exc:
        failures.append(str(exc))
        expected_disclosure = ""
    actual_disclosure = _text(script.get("truth_disclosure_ru"))
    if expected_disclosure and actual_disclosure != expected_disclosure:
        failures.append("truth_disclosure_ru does not match source truth mode")
    if actual_disclosure and actual_disclosure not in _text(script.get("intro_ru")):
        failures.append("truth disclosure must be spoken in intro_ru")
    winner = playoff.get("winner") if isinstance(playoff.get("winner"), dict) else {}
    failures.extend(validate_intro_contract(
        script.get("intro_contract"),
        intro_ru=_text(script.get("intro_ru")),
        episode_format=format_id,
        pillar=pillar,
        sources=normalized_sources,
        story_titles=[
            _text(item.get("title_ru"))
            for item in stories_raw
            if isinstance(item, dict)
        ],
        expected_disclosure=expected_disclosure,
        expected_cold_open_sha256=_text(winner.get("cold_open_sha256")),
    ))
    failures.extend(validate_mid_story_cta_contract(
        script.get("mid_story_cta_contract"),
        mid_story_cta_ru=_text(script.get("mid_story_cta_ru")),
        episode_format=format_id,
        pillar=pillar,
        sources=normalized_sources,
    ))

    for field in ("source_id", "body_sha256", "source_url", "author"):
        values = [
            (source[field].casefold() if isinstance(source[field], str) else source[field])
            for source in normalized_sources
        ]
        if len(values) != len(set(values)):
            failures.append(f"episode sources contain duplicate {field}")

    source_set = [
        {
            "source_id": source["source_id"],
            "body_sha256": source["body_sha256"],
            "source_url": source["source_url"],
            "truth_mode": source["truth_mode"],
            "role": _text(source.get("source_role") or ("response" if format_id == "THREAD" else "story")).lower(),
        }
        for source in normalized_sources
    ]
    source_set_sha = canonical_hash(source_set) if source_set else None
    if source_set_sha != winner.get("source_set_sha256"):
        failures.append("episode script sources do not match the playoff winner")

    return {
        "status": "PASS" if not failures else "BLOCKED",
        "failures": failures,
        "episode_plan_sha256": expected_plan_sha,
        "playoff_sha256": expected_playoff_sha or None,
        "source_set_sha256": source_set_sha,
        "creative_plan_sha256": creative_plan_sha,
        "format": format_id or None,
        "story_count": len(stories_raw),
        "publication_authorized": False,
    }
