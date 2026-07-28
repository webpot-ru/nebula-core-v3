"""One-command, fail-closed acc1 episode artifact factory.

The factory has two explicit live stages.  ``source`` may perform only a
bounded read-only Reddit collection.  ``produce`` may call OpenAI GPT-5.4 Flex,
GPT Image 2 through VectorEngine, and AI33 only after exact confirmations and hard caps.
Neither stage uploads to YouTube, mutates publication history, or authorizes a
release.  The highest possible result is ``READY_FOR_HUMAN_REVIEW``.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

from acc1_bundle_selector import (
    BundleSelectionError,
    select_bundle_finalists,
    verify_finalists_manifest,
)
from acc1_daily_planner import build_daily_plan
from acc1_episode_contract import (
    TRANSLATION_FINAL_ADJUDICATION_BASIS,
    TRANSLATION_FINAL_ADJUDICATION_CONTRACT_VERSION,
    build_intro_contract,
    build_mid_story_cta_contract,
    build_outro_prompt,
    truth_disclosure_ru,
    validate_episode_script,
)
from acc1_episode_images import generate_episode_images
from acc1_episode_manifest import (
    build_episode_manifest,
    canonical_hash,
    validate_episode_manifest,
)
from acc1_episode_packaging import generate_packaging, validate_packaging
from acc1_narration_profiles import (
    NARRATION_PROFILE_IDS_BY_PILLAR,
    NarrationProfileError,
    resolve_narration_boundary_contract,
    resolve_narration_profile,
)
from acc1_pronunciation_dictionary import (
    PronunciationDictionaryError,
    load_acc1_pronunciation_dictionary,
    resolve_acc1_pronunciation_dictionary_id,
)
from acc1_thread_collector import (
    MAX_NATURAL_RESPONSE_WORDS,
    MIN_NATURAL_RESPONSE_WORDS,
    verify_manifest as verify_thread_manifest,
)
from acc1_thread_source import ThreadSourceError, collect_thread_source_candidates
from acc1_thread_contract import THREAD_COMIC_PAGE_COUNT
from acc1_topic_playoff import (
    HARD_VETOES,
    SCORE_MAXIMA,
    SCORE_MINIMA,
    run_playoff,
    validate_base_candidate,
)
from acc1_visual_contract import (
    CINEMATIC_STORY_MODE,
    DEFAULT_VISUAL_MODE,
    EDITORIAL_MOTION_MODE,
    FORMAT_VISUAL_SYSTEM_V3_STYLE_PROFILE,
    VISUAL_MODES,
    resolve_visual_mode,
)
from compilation_audio_mix import (
    CompilationAudioMixError,
    build_pause_map,
    mix_compilation_audio,
)
from compilation_qa import run_qa
from compilation_renderer import (
    CompilationRenderError,
    render_compilation,
    validate_compilation_text_layout,
)
from compilation_storyboard import (
    CompilationStoryboardError,
    build_storyboard,
    narration_text,
)
from compilation_translation import (
    DEFAULT_MAX_CHARACTER_FLOOR,
    DEFAULT_MAX_CHARACTER_RATIO,
    FINAL_ADJUDICATION_RESOLUTION,
    TranslationConfig,
    _paragraph_chunks,
    canonicalize_source_for_translation,
    translate_and_review_story,
)
from compilation_tts_runner import build_tts_chunks, run_compilation_tts
from openai_client import (
    DEFAULT_TIMEOUT_SECONDS as OPENAI_REQUEST_TIMEOUT_SECONDS,
    FALLBACK_SERVICE_TIER,
    OPENAI_MODEL,
    PROMPT_CACHE_KEY,
    REQUIRED_SERVICE_TIER,
    OpenAIFlexResourceUnavailableError,
    OpenAIJSONResult,
    call_openai_json,
)
from openai_flex_recovery import (
    FLEX_RESOURCE_UNAVAILABLE_MARKER,
    FLEX_RESOURCE_UNAVAILABLE_MARKER_SHA256,
    FlexRecoveryError,
    REJECTED_FLEX_429_ERROR_TYPE,
    REJECTED_FLEX_429_REASON,
    REJECTED_FLEX_429_STATUS,
    validate_openai_attempt_sequence,
)
from scraper import fetch_best_story, get_reddit, history_posts, load_channel_config, load_history
from source_text_quality import source_text_quality_blockers
from source_safety import source_safety_evidence
from scripts.build_acc1_creative_review_template import build_template
from scripts.acc1_spend_lock import (
    PROVIDER_CONTRACT as SPEND_LOCK_PROVIDER_CONTRACT,
    WORKFLOW_PATH as SPEND_LOCK_WORKFLOW_PATH,
    SpendLockError,
    validate_lease_for_production,
)
from scripts.acc1_resume_lock import (
    ResumeLockError,
    canonical_hash as resume_canonical_hash,
    validate_resume_lease,
)
from scripts.review_reddit_topics import build_review
from thumbnail_generator import FONT_CANDIDATES, overlay_thumbnail_text, write_thumbnail_report
from vectorengine_client import (
    DEFAULT_IMAGE_MODEL,
    call_image_generation,
    get_vectorengine_api_key,
    VectorEngineError,
)


FACTORY_VERSION = 2
SOURCE_ONLY_SCHEMA_VERSION = "acc1_source_only_result_v1"
MIN_SOURCE_REVIEW_CANDIDATES = 3
MAX_SOURCE_REVIEW_CANDIDATES = 5
MIN_PASSING_FINALISTS = 3
THREAD_PROMPT_CANDIDATE_LIMIT = 43
THREAD_REDDIT_OAUTH_REQUEST_BUDGET = 1
NARRATOR_VOICE_ID = "elevenlabs_JBFqnCBsd6RMkjVDRZzb"
COMMENT_VOICE_ID = "elevenlabs_MOgsVr0EwwxqQs5cNDhu"
TTS_MODEL_ID = "eleven_v3"
TTS_MAX_CHARS = 4_500
BACKGROUND_ASSET = Path("assets/acc1/video/chonker-reading-loop-v1.mp4")
BACKGROUND_MANIFEST = Path("assets/acc1/video/chonker-reading-loop-v1.json")
BRAND_STING_ASSET = Path(
    "videos/chonker-talks-intro/renders/"
    "chonker-talks-editorial-intro-preview-v2.mp4",
)
BRAND_CTA_ASSET = Path(
    "videos/chonker-talks-cta/renders/"
    "chonker-talks-midroll-cta-v2.webm",
)
BRAND_OUTRO_ASSET = Path(
    "videos/chonker-talks-outro/renders/"
    "chonker-talks-youtube-outro-v1.mp4",
)
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
HEAD_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
REPOSITORY_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
TRUTH_MODES = {"fiction", "unverified_personal_account"}
SOURCE_WORD_RE = re.compile(r"[^\W_]+", re.UNICODE)
MAX_SOURCE_CHARACTERS_PER_WORD = 12
MAX_SOURCE_TOKEN_CHARACTERS = 80
MAX_THREAD_PROMPT_CHARACTERS = 2_000
RUNTIME_ESTIMATE_WORDS_PER_MINUTE = 130
RUNTIME_ESTIMATE_TOLERANCE = 0.10
WORKFLOW_TIMEOUT_MINUTES = 360
PRODUCE_TIMEOUT_MINUTES = 300
AI33_DEADLINE_FROM_PRODUCE_START_MINUTES = 240
POST_AI33_RENDER_QA_RESERVE_MINUTES = (
    PRODUCE_TIMEOUT_MINUTES - AI33_DEADLINE_FROM_PRODUCE_START_MINUTES
)


class EpisodeFactoryError(RuntimeError):
    """Raised whenever the factory cannot prove a required production gate."""


def _atomic_json(path: Path, value: dict[str, Any]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _read_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise EpisodeFactoryError(f"cannot read JSON artifact {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise EpisodeFactoryError(f"{path} must contain a JSON object")
    return value


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _self_hash(value: dict[str, Any], field: str) -> str:
    unhashed = copy.deepcopy(value)
    unhashed.pop(field, None)
    return canonical_hash(unhashed)


def _journal_hashable(value: Any) -> Any:
    """Convert provider output to a secret-safe deterministic hash payload."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, bytes):
        return {
            "binary_sha256": hashlib.sha256(value).hexdigest(),
            "binary_size": len(value),
        }
    if isinstance(value, Path):
        return {
            "path_name": value.name,
            "file_sha256": _sha256_file(value) if value.is_file() else None,
        }
    if isinstance(value, dict):
        return {
            str(key): _journal_hashable(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, (list, tuple)):
        return [_journal_hashable(item) for item in value]
    return {"unsupported_response_type": type(value).__name__}


def _verify_self_hash(value: dict[str, Any], field: str) -> bool:
    expected = str(value.get(field) or "")
    return bool(SHA256_RE.fullmatch(expected)) and expected == _self_hash(value, field)


def _exact_confirmation(value: str | bool, label: str) -> None:
    normalized = value if isinstance(value, bool) else str(value).strip().casefold() == "true"
    if normalized is not True:
        raise EpisodeFactoryError(f"{label} must be exactly true")


def _positive_cap(value: int, label: str, *, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= maximum:
        raise EpisodeFactoryError(f"{label} must be an integer between 1 and {maximum}")
    return value


def _canonical_reddit_url(value: Any) -> str:
    raw = str(value or "").strip()
    if raw.startswith("/"):
        return f"https://www.reddit.com{raw}"
    parsed = urlparse(raw)
    host = (parsed.hostname or "").casefold()
    if parsed.scheme != "https" or host not in {"reddit.com", "www.reddit.com", "old.reddit.com"}:
        raise EpisodeFactoryError(f"source URL is not canonical Reddit HTTPS: {raw or '(missing)'}")
    return f"https://www.reddit.com{parsed.path}"


def _channel_config(channels_path: Path) -> dict[str, Any]:
    config = _read_object(channels_path)
    matches = [
        item for item in config.get("channels") or []
        if isinstance(item, dict) and item.get("id") == "acc1"
    ]
    if len(matches) != 1:
        raise EpisodeFactoryError("channels.json must contain exactly one acc1 channel")
    return matches[0]


def validate_daily_plan(plan: dict[str, Any], channels_path: Path) -> dict[str, Any]:
    """Re-derive the plan from channels.json so a hand-edited plan cannot run."""
    selection = plan.get("selection")
    if not isinstance(selection, dict):
        raise EpisodeFactoryError("daily plan selection contract is missing")
    selection_mode = str(selection.get("mode") or "")
    if selection_mode == "canonical_daily_cycle":
        pilot_override = None
    elif selection_mode == "exact_pilot_override":
        pilot_override = str(plan.get("pilot_id") or "")
    else:
        raise EpisodeFactoryError(f"daily plan selection mode is invalid: {selection_mode or '(missing)'}")
    try:
        expected = build_daily_plan(
            channels_path,
            production_date=str(plan.get("production_date") or ""),
            pilot_override=pilot_override,
        )
    except Exception as exc:
        raise EpisodeFactoryError(f"daily plan cannot be re-derived: {exc}") from exc
    if canonical_hash(plan) != canonical_hash(expected):
        raise EpisodeFactoryError("daily plan does not exactly match channels.json and canonical planner")
    if plan.get("publication_authorized") is not False:
        raise EpisodeFactoryError("daily plan must not authorize publication")
    if plan.get("provider_spend_authorized") is not False:
        raise EpisodeFactoryError("daily plan must not pre-authorize provider spend")
    if plan.get("max_release_status") != "READY_FOR_HUMAN_REVIEW":
        raise EpisodeFactoryError("daily plan release ceiling is invalid")
    return expected


def _queue_lookup(queue: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(item.get("post_id") or ""): item
        for item in queue.get("entries") or []
        if isinstance(item, dict) and str(item.get("post_id") or "")
    }


def _validate_source_narratability(body: str, *, source_id: str, role: str) -> None:
    normalized = re.sub(r"\s+", " ", str(body or "")).strip()
    words = SOURCE_WORD_RE.findall(normalized)
    if not words:
        raise EpisodeFactoryError(f"source {source_id or '(missing)'} has no narration words")
    blockers = source_text_quality_blockers(normalized)
    if blockers:
        raise EpisodeFactoryError(
            f"source {source_id or '(missing)'} failed lexical narration quality: "
            + ", ".join(blockers)
        )
    safety = source_safety_evidence({}, normalized)
    if not safety["passed"]:
        raise EpisodeFactoryError(
            f"source {source_id or '(missing)'} failed high-confidence safety/PII gate: "
            + ", ".join(safety["matched_blocker_ids"])
        )
    if role == "prompt" and len(normalized) > MAX_THREAD_PROMPT_CHARACTERS:
        raise EpisodeFactoryError(
            f"THREAD prompt {source_id or '(missing)'} exceeds the narration limit"
        )


def _story_source(
    entry: dict[str, Any],
    reviewed: dict[str, Any],
    plan: dict[str, Any],
) -> dict[str, Any]:
    body = str(entry.get("source_body") or reviewed.get("source_body") or "")
    source_id = str(entry.get("post_id") or reviewed.get("post_id") or "").strip()
    body_sha = hashlib.sha256(body.encode("utf-8")).hexdigest()
    recorded = str(entry.get("source_body_sha256") or reviewed.get("source_body_sha256") or "")
    if not body or recorded != body_sha:
        raise EpisodeFactoryError(f"source {source_id or '(missing)'} body/hash is incomplete")
    _validate_source_narratability(body, source_id=source_id, role="story")
    truth_mode = str(reviewed.get("truth_mode") or "")
    if truth_mode not in TRUTH_MODES:
        raise EpisodeFactoryError(f"source {source_id} has no safe truth mode")
    return {
        "source_id": source_id,
        "post_id": source_id,
        "title": str(entry.get("title") or reviewed.get("title") or "").strip(),
        "body": body,
        "source_body": body,
        "body_sha256": body_sha,
        "source_body_sha256": body_sha,
        "source_url": _canonical_reddit_url(entry.get("url") or reviewed.get("source_url")),
        "author": str(entry.get("author") or reviewed.get("author") or "").strip(),
        "subreddit": str(entry.get("subreddit") or reviewed.get("subreddit") or "").strip(),
        "story_signature": str(entry.get("story_signature") or reviewed.get("story_signature") or "").strip(),
        "truth_mode": truth_mode,
        "role": "story",
        "source_role": "story",
        "pillar": str(plan["pillar"]),
        "complete": reviewed.get("complete", reviewed.get("review_status") in {
            "SAGA_SOURCE_ELIGIBLE_FOR_GREENLIGHT", "BUNDLE_COMPONENT_ELIGIBLE",
        }) is True,
        "payoff_complete": reviewed.get("payoff_complete") is True,
        # Preserve the review contract: False means the text is self-contained.
        # Missing/unknown values remain fail-closed by becoming True here.
        "depends_on_screenshot_or_link": reviewed.get("depends_on_screenshot_or_link") is not False,
        "fictional_as_real": False,
        "score": entry.get("upvotes"),
        "num_comments": entry.get("comments"),
        "source_media": entry.get("source_media") if isinstance(entry.get("source_media"), list) else [],
        "source_discovery_signals": {
            "local_score": entry.get("local_score"),
            "time_window": entry.get("time_window"),
            "velocity": entry.get("velocity"),
            "reddit_metrics_are_truth_evidence": False,
        },
    }


def _saga_candidates(queue: dict[str, Any], review: dict[str, Any], plan: dict[str, Any]) -> list[dict[str, Any]]:
    lookup = _queue_lookup(queue)
    candidates: list[dict[str, Any]] = []
    for item in review.get("top_topics") or []:
        if not isinstance(item, dict):
            continue
        post_id = str(item.get("post_id") or "")
        entry = lookup.get(post_id)
        if not entry:
            continue
        source = _story_source(entry, item, plan)
        candidates.append({
            "candidate_id": f"saga-{post_id}",
            "pilot_id": plan["pilot_id"],
            "format": "SAGA",
            "pillar": plan["pillar"],
            "sources": [source],
        })
        if len(candidates) == MAX_SOURCE_REVIEW_CANDIDATES:
            break
    return candidates


def _validate_base_candidate_pool(
    candidates: list[dict[str, Any]], daily_plan: dict[str, Any],
) -> None:
    if (
        not MIN_SOURCE_REVIEW_CANDIDATES
        <= len(candidates)
        <= MAX_SOURCE_REVIEW_CANDIDATES
        or any(not isinstance(item, dict) for item in candidates)
    ):
        raise EpisodeFactoryError(
            f"source pool must contain {MIN_SOURCE_REVIEW_CANDIDATES}-"
            f"{MAX_SOURCE_REVIEW_CANDIDATES} candidate objects"
        )
    for candidate_index, candidate in enumerate(candidates):
        for source in candidate.get("sources") or []:
            if not isinstance(source, dict):
                raise EpisodeFactoryError("episode candidate source must be an object")
            _validate_source_narratability(
                str(source.get("body") or source.get("source_body") or ""),
                source_id=str(source.get("source_id") or source.get("post_id") or ""),
                role=str(source.get("role") or source.get("source_role") or "story"),
            )
        base_review = validate_base_candidate(
            candidate, plan=daily_plan, index=candidate_index,
        )
        if base_review.get("status") != "PASS":
            raise EpisodeFactoryError(
                "source finalist failed deterministic base contract before paid review: "
                + "; ".join(base_review.get("failures") or [])
            )


def _required_image_calls(
    format_id: str,
    source_count: int,
    visual_mode: str = DEFAULT_VISUAL_MODE,
) -> int:
    if visual_mode == EDITORIAL_MOTION_MODE:
        if format_id == "THREAD":
            # Long THREAD episodes reserve their full 20-page ceiling before
            # any paid call. Every page uses a paired hero/detail plate; the
            # separately generated thumbnail remains part of the leased cap.
            return THREAD_COMIC_PAGE_COUNT[1] * 2 + 1
        # Paid preflight only proves a safe floor. The exact narration-bound
        # plan is calculated before the first image call and may require a
        # higher explicitly leased cap, up to the canonical 69-call ceiling.
        scene_count = 4 if format_id == "SAGA" else 2 * source_count
        return scene_count * 2 + 1
    if format_id == "SAGA":
        scene_count = 5
    elif format_id == "BUNDLE":
        scene_count = 3 * source_count
    elif format_id == "THREAD":
        scene_count = 3
    else:
        raise EpisodeFactoryError(f"unsupported episode format for image budget: {format_id}")
    return scene_count


def _translation_fallback_piece_ceiling(body: str, chunk_chars: int = 7_000) -> int:
    """Use the exact deterministic fallback partition without provider access."""
    working_body = canonicalize_source_for_translation(body)
    return max(1, len(_paragraph_chunks(working_body, chunk_chars)))


def _required_openai_calls(candidates: list[dict[str, Any]]) -> int:
    """Budget reviews, evidence correction, and bounded winner production."""
    translation_calls = max(
        (
            (
                sum(
                    (9 if str(candidate.get("format") or "").upper() == "SAGA" else 6)
                    + _translation_fallback_piece_ceiling(
                        str(source.get("body") or "")
                    )
                    for source in candidate.get("sources") or []
                    if isinstance(source, dict)
                )
                # A THREAD reserves one final adjudication in its base envelope.
                # Production may expose more only from the explicitly approved
                # unused headroom above this complete conservative envelope.
                + (
                    1
                    if str(candidate.get("format") or "").upper() == "THREAD"
                    and any(
                        isinstance(source, dict)
                        for source in candidate.get("sources") or []
                    )
                    else 0
                )
            )
            for candidate in candidates
        ),
        default=0,
    )
    # Three source-validation passes per finalist. Packaging is selected
    # deterministically from the already locked winner options.
    creative_calls = len(candidates) * 3
    return translation_calls + creative_calls


def _thread_final_adjudication_limit(
    *,
    openai_call_cap: int,
    required_openai_calls: int,
    source_count: int,
) -> int:
    """Spend only explicit call-cap headroom on additional THREAD adjudications."""
    cap = _positive_cap(openai_call_cap, "openai_call_cap", maximum=256)
    required = _positive_cap(
        required_openai_calls,
        "required_openai_calls",
        maximum=256,
    )
    sources = _positive_cap(source_count, "source_count", maximum=256)
    if required > cap:
        raise EpisodeFactoryError(
            "required OpenAI envelope exceeds the approved call cap"
        )
    # The conservative required envelope already reserves one adjudication.
    # Every additional adjudication consumes exactly one otherwise-unused
    # approved call, so the complete worst case still cannot exceed ``cap``.
    return min(sources, 1 + (cap - required))


def _minimum_tts_calls(format_id: str, source_count: int) -> int:
    """Return the unavoidable task floor before translated lengths are known."""
    if source_count < 1:
        raise EpisodeFactoryError("episode candidate must contain at least one source")
    if format_id == "SAGA":
        return 3  # intro, one story, outro
    if format_id == "BUNDLE":
        return source_count + (source_count - 1) + 2  # stories, transitions, bookends
    if format_id == "THREAD":
        return source_count + 2  # visible response boundaries are not spoken
    raise EpisodeFactoryError(f"unsupported episode format for TTS budget: {format_id}")


def _translation_character_ceiling(source_body: str) -> int:
    """Mirror the fail-closed translation validator without calling Gemini."""
    source_characters = len(re.sub(r"\s+", " ", str(source_body or "")).strip())
    return max(
        DEFAULT_MAX_CHARACTER_FLOOR,
        math.ceil(max(1, source_characters) * DEFAULT_MAX_CHARACTER_RATIO),
    )


def _tts_chunk_ceiling(character_ceiling: int, max_chars: int = TTS_MAX_CHARS) -> int:
    """Bound the greedy sentence/word splitter for any accepted translation.

    Every overflow boundary accounts for more than ``max_chars`` characters
    across two neighboring chunks.  The extra chunk covers the final remainder;
    the translation validator separately rejects tokens longer than 80 chars.
    """
    if character_ceiling < 1 or max_chars < 1:
        raise EpisodeFactoryError("TTS character ceilings must be positive")
    return max(1, math.ceil((2 * character_ceiling) / max_chars) + 1)


def _required_ai33_calls(
    candidates: list[dict[str, Any]], format_id: str,
) -> int:
    """Return a safe pre-Gemini task ceiling for every possible winner."""
    if format_id not in {"SAGA", "BUNDLE", "THREAD"}:
        raise EpisodeFactoryError(f"unsupported episode format for TTS budget: {format_id}")
    candidate_ceilings: list[int] = []
    for candidate in candidates:
        sources = candidate.get("sources") or []
        if not sources or any(not isinstance(source, dict) for source in sources):
            raise EpisodeFactoryError("episode candidate must contain complete source objects")
        story_chunks = sum(
            _tts_chunk_ceiling(
                _translation_character_ceiling(
                    str(source.get("body") or source.get("source_body") or "")
                )
            )
            for source in sources
        )
        transition_chunks = len(sources) - 1 if format_id == "BUNDLE" else 0
        candidate_ceilings.append(story_chunks + transition_chunks + 2)
    if not candidate_ceilings:
        raise EpisodeFactoryError("source pool must contain candidate objects")
    return max(candidate_ceilings)


def _bundle_candidates(queue: dict[str, Any], review: dict[str, Any], plan: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    reviewed_candidates = [
        item for item in review.get("candidate_reviews") or [] if isinstance(item, dict)
    ]
    finalists_manifest: dict[str, Any] | None = None
    last_error: BundleSelectionError | None = None
    for finalist_count in range(
        MAX_SOURCE_REVIEW_CANDIDATES,
        MIN_SOURCE_REVIEW_CANDIDATES - 1,
        -1,
    ):
        try:
            finalists_manifest = select_bundle_finalists(
                reviewed_candidates,
                source_plan=plan["source_plan"],
                finalist_count=finalist_count,
            )
            break
        except BundleSelectionError as exc:
            last_error = exc
    if finalists_manifest is None:
        raise EpisodeFactoryError(
            "BUNDLE source pool cannot supply three materially distinct complete candidates: "
            f"{last_error}"
        ) from last_error
    if not verify_finalists_manifest(finalists_manifest):
        raise EpisodeFactoryError("BUNDLE finalists manifest failed its own hash contract")
    lookup = _queue_lookup(queue)
    candidates: list[dict[str, Any]] = []
    for finalist in finalists_manifest["finalists"]:
        sources = [
            _story_source(lookup[str(item["post_id"])], item, plan)
            for item in finalist["stories"]
        ]
        candidates.append({
            "candidate_id": finalist["finalist_id"],
            "pilot_id": plan["pilot_id"],
            "format": "BUNDLE",
            "pillar": plan["pillar"],
            "sources": sources,
            "source_finalist_sha256": finalist["finalist_sha256"],
        })
    return candidates, finalists_manifest


def _thread_source(source: dict[str, Any], *, role: str, plan: dict[str, Any], prompt: dict[str, Any]) -> dict[str, Any]:
    if role == "prompt":
        title = str(source.get("title") or "").strip()
        raw_body = str(source.get("body") or "").strip()
        body = "\n\n".join(item for item in (title, raw_body) if item)
        source_id = str(source.get("id") or "")
        signature = str(source.get("prompt_sha256") or hashlib.sha256(body.encode()).hexdigest())
        subreddit = str(source.get("subreddit") or "AskReddit")
    else:
        body = str(source.get("body") or "")
        source_id = str(source.get("id") or "")
        title = f"Ответ пользователя {source.get('rank') or ''}".strip()
        signature = hashlib.sha256(f"{prompt.get('id')}\n{source_id}\n{body}".encode("utf-8")).hexdigest()
        subreddit = str(prompt.get("subreddit") or "AskReddit")
    if not body.strip():
        raise EpisodeFactoryError(f"THREAD {role} {source_id} has empty source text")
    _validate_source_narratability(body, source_id=source_id, role=role)
    author = str(source.get("author") or "").strip()
    if not author:
        raise EpisodeFactoryError(f"THREAD {role} {source_id} has no author provenance")
    return {
        "source_id": source_id,
        "post_id": source_id,
        "title": title,
        "body": body,
        "source_body": body,
        "body_sha256": hashlib.sha256(body.encode("utf-8")).hexdigest(),
        "source_body_sha256": hashlib.sha256(body.encode("utf-8")).hexdigest(),
        "source_url": _canonical_reddit_url(source.get("source_url")),
        "author": author,
        "subreddit": subreddit,
        "story_signature": signature,
        "truth_mode": "unverified_personal_account",
        "role": role,
        "source_role": role,
        "pillar": plan["pillar"],
        "complete": True,
        "payoff_complete": True,
        "depends_on_screenshot_or_link": False,
        "fictional_as_real": False,
        "score": source.get("score"),
        "editorial_role": source.get("editorial_role"),
        "num_comments": None,
        "source_media": [],
        "source_discovery_signals": {
            "reddit_score": source.get("score"),
            "reddit_metrics_are_truth_evidence": False,
        },
    }


def _thread_candidates(
    results: list[tuple[dict[str, Any], dict[str, Any]]],
    plan: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    snapshots: list[dict[str, Any]] = []
    manifests: list[dict[str, Any]] = []
    queue_entries: dict[str, dict[str, Any]] = {}
    for snapshot, manifest in results:
        prompt = manifest["prompt"]
        sources = [_thread_source(prompt, role="prompt", plan=plan, prompt=prompt)]
        sources.extend(
            _thread_source(item, role="response", plan=plan, prompt=prompt)
            for item in manifest["responses"]
        )
        for source in sources:
            queue_entries[source["post_id"]] = {
                "post_id": source["post_id"],
                "author": source["author"],
                "subreddit": source["subreddit"],
                "title": source["title"],
                "url": source["source_url"],
                "source_body": source["body"],
                "source_body_sha256": source["body_sha256"],
                "source_word_count": len(source["body"].split()),
                "story_signature": source["story_signature"],
                "truth_mode": source["truth_mode"],
                "source_role": source["source_role"],
            }
        candidates.append({
            "candidate_id": f"thread-{prompt['id']}",
            "pilot_id": plan["pilot_id"],
            "format": "THREAD",
            "pillar": plan["pillar"],
            "sources": sources,
            "thread_manifest_sha256": manifest["manifest_sha256"],
        })
        snapshots.append(snapshot)
        manifests.append(manifest)
    queue = {
        "version": 1,
        "channel_id": "acc1",
        "format_intent": "thread",
        "source_plan": plan["source_plan"],
        "entries": sorted(queue_entries.values(), key=lambda item: item["post_id"]),
        "quality_review_status": "DETERMINISTIC_THREAD_SOURCE_REVIEW",
    }
    review = {
        "version": 1,
        "status": "review_ready",
        "review_mode": "bounded_full_thread_finalists",
        "channel_id": "acc1",
        "format_intent": "thread",
        "source_plan": plan["source_plan"],
        "candidate_count": len(candidates),
        "snapshots": snapshots,
        "thread_manifests": manifests,
        "production_authorized": False,
    }
    return candidates, queue, review


def _reddit_request_count(reddit: Any) -> int | None:
    core = getattr(reddit, "_core", None)
    # PRAW 8 exposes the requestor through Session.requestor.  Keep the legacy
    # private fallback for older fixtures/releases without making a network call.
    requestor = getattr(core, "requestor", None)
    value = getattr(requestor, "request_count", None)
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    legacy_requestor = getattr(core, "_requestor", None)
    legacy_value = getattr(legacy_requestor, "request_count", None)
    return (
        legacy_value
        if isinstance(legacy_value, int) and not isinstance(legacy_value, bool)
        else None
    )


def run_source_stage(
    *,
    daily_plan: dict[str, Any],
    workdir: Path,
    channels_path: Path,
    confirm_reddit_read: str | bool,
    reddit_request_cap: int,
    reserved_source_exclusions_path: Path | None = None,
    reddit_factory: Callable[..., Any] = get_reddit,
) -> dict[str, Any]:
    """Perform the only network-facing source read and write immutable evidence."""
    _exact_confirmation(confirm_reddit_read, "confirm_reddit_read")
    workdir = Path(workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    validate_daily_plan(daily_plan, channels_path)
    # The source stage is not allowed to inherit the scraper's historical
    # default-on AI gate.  It must be explicitly disabled before Reddit access.
    import scraper as scraper_module
    if scraper_module.AI_QUALITY_ENABLED:
        raise EpisodeFactoryError(
            "source stage requires AI_QUALITY_CHECK=0; refusing any implicit Gemini call"
        )
    if scraper_module.AI_QUALITY_FAIL_OPEN:
        raise EpisodeFactoryError(
            "source stage requires AI_QUALITY_FAIL_OPEN=0"
        )
    cap = _positive_cap(reddit_request_cap, "reddit_request_cap", maximum=100)
    channel = _channel_config(channels_path)
    excluded_source_ids: set[str] = set()
    excluded_story_signatures: set[str] = set()
    if reserved_source_exclusions_path is not None:
        exclusions = _read_object(Path(reserved_source_exclusions_path))
        claimed = str(exclusions.get("reserved_source_exclusions_sha256") or "")
        if (
            exclusions.get("status") != "VALIDATED_RESERVED_SOURCE_EXCLUSIONS"
            or exclusions.get("publication_authorized") is not False
            or not _verify_self_hash(exclusions, "reserved_source_exclusions_sha256")
            or not claimed
        ):
            raise EpisodeFactoryError("reserved source exclusions manifest is invalid")
        source_ids = exclusions.get("source_ids")
        signatures = exclusions.get("story_signatures")
        if not isinstance(source_ids, list) or not isinstance(signatures, list):
            raise EpisodeFactoryError("reserved source exclusions lists are invalid")
        excluded_source_ids = {str(item).strip().casefold() for item in source_ids}
        excluded_story_signatures = {str(item).strip().casefold() for item in signatures}
    reddit = reddit_factory(request_cap=cap)
    format_id = str(daily_plan["format"])
    finalists_manifest: dict[str, Any] | None = None

    if format_id in {"SAGA", "BUNDLE"}:
        queue_path = workdir / "source-queue.json"
        story = fetch_best_story(
            subreddits=list(daily_plan["source_plan"]["subreddits"]),
            time_filter="auto",
            min_upvotes=1000,
            min_body_length=300,
            comment_limit=0,
            channel_id="acc1",
            channel_config=channel,
            skip_rank=0,
            max_ai_candidates=0,
            candidate_limit=25,
            topic_family=daily_plan["source_plan"]["topic_family"],
            include_source_body_in_queue=True,
            format_intent=daily_plan["source_plan"]["format_intent"],
            producer_queue_output=str(queue_path.resolve()),
            pilot_id=daily_plan["pilot_id"],
            max_time_windows_per_topic=3,
            excluded_source_ids=excluded_source_ids,
            excluded_story_signatures=excluded_story_signatures,
            reddit_client=reddit,
        )
        if not story or not queue_path.is_file():
            raise EpisodeFactoryError("bounded Reddit read did not produce a source queue")
        queue = _read_object(queue_path)
        review = build_review(queue, 30)
        if review.get("status") != "review_ready":
            raise EpisodeFactoryError(f"deterministic source review blocked: {review.get('status')}")
        if format_id == "SAGA":
            candidates = _saga_candidates(queue, review, daily_plan)
        else:
            try:
                candidates, finalists_manifest = _bundle_candidates(queue, review, daily_plan)
            except EpisodeFactoryError as exc:
                source_diagnostics = {
                    "version": 1,
                    "status": "BLOCKED_BUNDLE_FINALISTS",
                    "channel_id": "acc1",
                    "episode_key": daily_plan["episode_key"],
                    "pilot_id": daily_plan["pilot_id"],
                    "format": format_id,
                    "pillar": daily_plan["pillar"],
                    "daily_plan_sha256": canonical_hash(daily_plan),
                    "failure": str(exc),
                    "reddit_http_request_cap": cap,
                    "reddit_http_requests_observed": _reddit_request_count(reddit),
                    "queue": queue,
                    "review": review,
                    "production_authorized": False,
                    "publication_authorized": False,
                }
                source_diagnostics["source_diagnostics_sha256"] = _self_hash(
                    source_diagnostics, "source_diagnostics_sha256",
                )
                _atomic_json(workdir / "source-diagnostics.json", source_diagnostics)
                raise
    else:
        source_plan = daily_plan["source_plan"]
        search_queries = source_plan.get("search_queries")
        if (
            not isinstance(search_queries, list)
            or not search_queries
            or any(not isinstance(query, str) or not query.strip() for query in search_queries)
        ):
            raise EpisodeFactoryError("THREAD source plan requires search_queries")
        request_upper_bound = (
            THREAD_REDDIT_OAUTH_REQUEST_BUDGET
            + len(search_queries)
            + THREAD_PROMPT_CANDIDATE_LIMIT
        )
        if request_upper_bound > cap:
            raise EpisodeFactoryError(
                "THREAD discovery request envelope exceeds reddit_request_cap: "
                f"{THREAD_REDDIT_OAUTH_REQUEST_BUDGET} OAuth read + "
                f"{len(search_queries)} listing reads + "
                f"{THREAD_PROMPT_CANDIDATE_LIMIT} comment-tree reads = "
                f"{request_upper_bound} > {cap}"
            )
        try:
            results = collect_thread_source_candidates(
                reddit,
                subreddit_name=source_plan["subreddits"][0],
                time_filter=source_plan["search_time_filter"],
                candidate_limit=THREAD_PROMPT_CANDIDATE_LIMIT,
                response_scan_limit=60,
                max_responses=15,
                truth_mode="unverified_personal_account",
                search_queries=search_queries,
                search_sort=source_plan["search_sort"],
                prompt_policy=source_plan.get("prompt_policy"),
                finalist_limit=MAX_SOURCE_REVIEW_CANDIDATES,
                minimum_finalists=MIN_SOURCE_REVIEW_CANDIDATES,
                require_episode_runtime=True,
                # Prompt IDs are Reddit source IDs too. Response-level overlap is
                # still enforced by the post-source reservation scan.
                excluded_prompt_ids=(
                    set(history_posts(load_history()).keys()) | excluded_source_ids
                ),
            )
        except ThreadSourceError as exc:
            source_diagnostics = {
                "version": 1,
                "status": "BLOCKED_THREAD_SOURCE_DISCOVERY",
                "channel_id": "acc1",
                "episode_key": daily_plan["episode_key"],
                "pilot_id": daily_plan["pilot_id"],
                "format": format_id,
                "pillar": daily_plan["pillar"],
                "daily_plan_sha256": canonical_hash(daily_plan),
                "failure": str(exc),
                "reddit_http_request_cap": cap,
                "reddit_http_requests_observed": _reddit_request_count(reddit),
                "planned_reddit_request_upper_bound": request_upper_bound,
                "thread_source_diagnostics": exc.diagnostics,
                "production_authorized": False,
                "publication_authorized": False,
            }
            source_diagnostics["source_diagnostics_sha256"] = _self_hash(
                source_diagnostics, "source_diagnostics_sha256",
            )
            _atomic_json(workdir / "source-diagnostics.json", source_diagnostics)
            raise EpisodeFactoryError(str(exc)) from exc
        candidates, queue, review = _thread_candidates(results, daily_plan)

    if not MIN_SOURCE_REVIEW_CANDIDATES <= len(candidates) <= MAX_SOURCE_REVIEW_CANDIDATES:
        source_diagnostics: dict[str, Any] = {
            "version": 1,
            "status": "BLOCKED_INSUFFICIENT_SOURCE_FINALISTS",
            "channel_id": "acc1",
            "episode_key": daily_plan["episode_key"],
            "pilot_id": daily_plan["pilot_id"],
            "format": format_id,
            "pillar": daily_plan["pillar"],
            "daily_plan_sha256": canonical_hash(daily_plan),
            "required_candidate_range": [
                MIN_SOURCE_REVIEW_CANDIDATES,
                MAX_SOURCE_REVIEW_CANDIDATES,
            ],
            "candidate_count": len(candidates),
            "candidate_ids": [str(item.get("candidate_id") or "") for item in candidates],
            "reddit_http_request_cap": cap,
            "reddit_http_requests_observed": _reddit_request_count(reddit),
            "queue": queue,
            "review": review,
            "production_authorized": False,
            "publication_authorized": False,
        }
        source_diagnostics["source_diagnostics_sha256"] = _self_hash(
            source_diagnostics, "source_diagnostics_sha256",
        )
        _atomic_json(workdir / "source-diagnostics.json", source_diagnostics)
        raise EpisodeFactoryError(
            f"topic playoff requires {MIN_SOURCE_REVIEW_CANDIDATES}-"
            f"{MAX_SOURCE_REVIEW_CANDIDATES} complete candidates before paid review; "
            f"found {len(candidates)}"
        )
    try:
        _validate_base_candidate_pool(candidates, daily_plan)
    except EpisodeFactoryError as exc:
        source_diagnostics = {
            "version": 1,
            "status": "BLOCKED_BASE_SOURCE_CONTRACT",
            "channel_id": "acc1",
            "episode_key": daily_plan["episode_key"],
            "pilot_id": daily_plan["pilot_id"],
            "format": format_id,
            "pillar": daily_plan["pillar"],
            "daily_plan_sha256": canonical_hash(daily_plan),
            "failure": str(exc),
            "candidate_count": len(candidates),
            "candidate_ids": [str(item.get("candidate_id") or "") for item in candidates],
            "reddit_http_request_cap": cap,
            "reddit_http_requests_observed": _reddit_request_count(reddit),
            "queue": queue,
            "review": review,
            "candidates": candidates,
            "production_authorized": False,
            "publication_authorized": False,
        }
        source_diagnostics["source_diagnostics_sha256"] = _self_hash(
            source_diagnostics, "source_diagnostics_sha256",
        )
        _atomic_json(workdir / "source-diagnostics.json", source_diagnostics)
        raise
    daily_plan_sha = canonical_hash(daily_plan)
    candidate_pool: dict[str, Any] = {
        "version": 1,
        "status": "SOURCE_FINALISTS_READY",
        "channel_id": "acc1",
        "episode_key": daily_plan["episode_key"],
        "pilot_id": daily_plan["pilot_id"],
        "format": format_id,
        "pillar": daily_plan["pillar"],
        "daily_plan_sha256": daily_plan_sha,
        "candidates": candidates,
        "candidate_count": len(candidates),
        "paid_review_candidate_count": len(candidates),
        "target_review_candidate_count": MAX_SOURCE_REVIEW_CANDIDATES,
        "minimum_passing_finalists": MIN_PASSING_FINALISTS,
        "source_truth_policy": "reddit_is_source_not_independent_fact_verification",
        "production_authorized": False,
        "publication_authorized": False,
    }
    candidate_pool["candidate_pool_sha256"] = _self_hash(candidate_pool, "candidate_pool_sha256")
    review["daily_plan_sha256"] = daily_plan_sha
    review["publication_authorized"] = False
    queue["daily_plan_sha256"] = daily_plan_sha
    queue["publication_authorized"] = False
    observed_requests = _reddit_request_count(reddit)
    if observed_requests is None or not 0 <= observed_requests <= cap:
        raise EpisodeFactoryError(
            "bounded Reddit requestor count is unavailable or exceeds the approved cap"
        )
    source_stage: dict[str, Any] = {
        "version": 1,
        "status": "SOURCE_READY",
        "network_accessed": True,
        "network_mode": "bounded_read_only_reddit",
        "reddit_http_request_cap": cap,
        "reddit_http_requests_observed": observed_requests,
        "daily_plan_sha256": daily_plan_sha,
        "source_queue_sha256": canonical_hash(queue),
        "source_review_sha256": canonical_hash(review),
        "candidate_pool_sha256": candidate_pool["candidate_pool_sha256"],
        "candidate_count": len(candidates),
        "publication_authorized": False,
    }
    source_stage["source_stage_sha256"] = _self_hash(source_stage, "source_stage_sha256")

    _atomic_json(workdir / "daily-plan.json", daily_plan)
    _atomic_json(workdir / "source-queue.json", queue)
    _atomic_json(workdir / "source-review.json", review)
    _atomic_json(workdir / "candidate-pool.json", candidate_pool)
    if finalists_manifest is not None:
        _atomic_json(workdir / "bundle-finalists.json", finalists_manifest)
    _atomic_json(workdir / "source-stage.json", source_stage)
    return source_stage


def run_source_only_receipt(
    *,
    daily_plan: dict[str, Any],
    workdir: Path,
    channels_path: Path,
    reddit_request_cap: int,
    repository: str,
    workflow_path: str,
    run_id: int,
    run_attempt: int,
    head_sha: str,
) -> dict[str, Any]:
    """Seal a successful Reddit-only source run without authorizing paid work."""
    validate_daily_plan(daily_plan, channels_path)
    cap = _positive_cap(reddit_request_cap, "reddit_request_cap", maximum=100)
    repository = str(repository or "").strip()
    workflow_path = str(workflow_path or "").strip()
    head_sha = str(head_sha or "").strip().lower()
    if not REPOSITORY_RE.fullmatch(repository):
        raise EpisodeFactoryError("source-only repository identity is invalid")
    if workflow_path != SPEND_LOCK_WORKFLOW_PATH:
        raise EpisodeFactoryError("source-only workflow path is invalid")
    if isinstance(run_id, bool) or not isinstance(run_id, int) or run_id < 1:
        raise EpisodeFactoryError("source-only run_id must be a positive integer")
    if run_attempt != 1:
        raise EpisodeFactoryError("source-only receipt refuses replayed workflow attempts")
    if not HEAD_SHA_RE.fullmatch(head_sha):
        raise EpisodeFactoryError("source-only head_sha must be a 40-character commit SHA")

    root = Path(workdir)
    stored_plan = _read_object(root / "daily-plan.json")
    source_stage = _read_object(root / "source-stage.json")
    candidate_pool = _read_object(root / "candidate-pool.json")
    source_queue = _read_object(root / "source-queue.json")
    source_review = _read_object(root / "source-review.json")
    daily_plan_sha256 = canonical_hash(daily_plan)
    if canonical_hash(stored_plan) != daily_plan_sha256:
        raise EpisodeFactoryError("source-only stored daily plan does not match dispatch plan")
    if (
        source_stage.get("status") != "SOURCE_READY"
        or source_stage.get("network_accessed") is not True
        or source_stage.get("network_mode") != "bounded_read_only_reddit"
        or source_stage.get("publication_authorized") is not False
        or not _verify_self_hash(source_stage, "source_stage_sha256")
    ):
        raise EpisodeFactoryError("source-only source-stage artifact is not valid SOURCE_READY")
    observed_requests = source_stage.get("reddit_http_requests_observed")
    if (
        source_stage.get("reddit_http_request_cap") != cap
        or isinstance(observed_requests, bool)
        or not isinstance(observed_requests, int)
        or not 1 <= observed_requests <= cap
    ):
        raise EpisodeFactoryError("source-only Reddit request evidence violates the approved cap")
    if source_stage.get("daily_plan_sha256") != daily_plan_sha256:
        raise EpisodeFactoryError("source-only source-stage plan binding mismatch")

    if (
        candidate_pool.get("status") != "SOURCE_FINALISTS_READY"
        or candidate_pool.get("publication_authorized") is not False
        or candidate_pool.get("production_authorized") is not False
        or not _verify_self_hash(candidate_pool, "candidate_pool_sha256")
    ):
        raise EpisodeFactoryError("source-only candidate pool is not self-verifying")
    if source_stage.get("candidate_pool_sha256") != candidate_pool.get(
        "candidate_pool_sha256"
    ):
        raise EpisodeFactoryError("source-only candidate-pool binding mismatch")
    if source_stage.get("source_queue_sha256") != canonical_hash(source_queue):
        raise EpisodeFactoryError("source-only queue binding mismatch")
    if source_stage.get("source_review_sha256") != canonical_hash(source_review):
        raise EpisodeFactoryError("source-only review binding mismatch")
    for label, artifact in (
        ("source queue", source_queue),
        ("source review", source_review),
    ):
        if artifact.get("publication_authorized") is not False:
            raise EpisodeFactoryError(f"source-only {label} may not authorize publication")

    candidates = candidate_pool.get("candidates")
    candidate_count = candidate_pool.get("candidate_count")
    if (
        not isinstance(candidates, list)
        or isinstance(candidate_count, bool)
        or candidate_count != len(candidates)
        or source_stage.get("candidate_count") != candidate_count
        or candidate_pool.get("paid_review_candidate_count") != candidate_count
        or not MIN_SOURCE_REVIEW_CANDIDATES
        <= candidate_count
        <= MAX_SOURCE_REVIEW_CANDIDATES
    ):
        raise EpisodeFactoryError("source-only candidate count contract is invalid")
    _validate_base_candidate_pool(candidates, daily_plan)

    candidate_ids: set[str] = set()
    candidate_metrics: list[dict[str, Any]] = []
    format_id = str(daily_plan.get("format") or "")
    thread_manifests = source_review.get("thread_manifests")
    if format_id == "THREAD" and (
        not isinstance(thread_manifests, list)
        or len(thread_manifests) != candidate_count
    ):
        raise EpisodeFactoryError("source-only THREAD review has incomplete manifests")

    for index, candidate in enumerate(candidates):
        candidate_id = str(candidate.get("candidate_id") or "").strip()
        if not candidate_id or candidate_id in candidate_ids:
            raise EpisodeFactoryError("source-only candidate identities must be unique")
        candidate_ids.add(candidate_id)
        if (
            candidate.get("pilot_id") != daily_plan.get("pilot_id")
            or candidate.get("format") != format_id
            or candidate.get("pillar") != daily_plan.get("pillar")
        ):
            raise EpisodeFactoryError(
                f"source-only candidate {candidate_id} routing mismatch"
            )
        sources = candidate.get("sources")
        if not isinstance(sources, list) or not sources:
            raise EpisodeFactoryError(
                f"source-only candidate {candidate_id} has no source objects"
            )
        response_sources = [
            source
            for source in sources
            if isinstance(source, dict) and source.get("source_role") == "response"
        ]
        response_word_counts = [
            len(SOURCE_WORD_RE.findall(str(source.get("body") or "")))
            for source in response_sources
        ]
        metric: dict[str, Any] = {
            "candidate_id": candidate_id,
            "source_count": len(sources),
            "response_count": len(response_sources),
            "aggregate_response_word_count": sum(response_word_counts),
        }
        if format_id == "THREAD":
            prompt_sources = [
                source
                for source in sources
                if isinstance(source, dict) and source.get("source_role") == "prompt"
            ]
            manifest = thread_manifests[index]
            if (
                len(prompt_sources) != 1
                or not verify_thread_manifest(manifest)
                or candidate.get("thread_manifest_sha256")
                != manifest.get("manifest_sha256")
            ):
                raise EpisodeFactoryError(
                    f"source-only THREAD candidate {candidate_id} manifest mismatch"
                )
            response_range = daily_plan["source_plan"]["response_count"]
            aggregate_range = daily_plan["source_plan"][
                "aggregate_response_word_count"
            ]
            if (
                not response_range[0]
                <= len(response_sources)
                <= response_range[1]
                or manifest.get("response_count") != len(response_sources)
                or manifest.get("aggregate_response_word_count")
                != metric["aggregate_response_word_count"]
                or not aggregate_range[0]
                <= metric["aggregate_response_word_count"]
                <= aggregate_range[1]
                or any(
                    not MIN_NATURAL_RESPONSE_WORDS
                    <= count
                    <= MAX_NATURAL_RESPONSE_WORDS
                    for count in response_word_counts
                )
            ):
                raise EpisodeFactoryError(
                    f"source-only THREAD candidate {candidate_id} runtime contract mismatch"
                )
        candidate_metrics.append(metric)

    result: dict[str, Any] = {
        "schema_version": SOURCE_ONLY_SCHEMA_VERSION,
        "status": "SOURCE_ONLY_READY",
        "source_only": True,
        "repository": repository,
        "workflow_path": workflow_path,
        "run_id": run_id,
        "run_attempt": run_attempt,
        "head_sha": head_sha,
        "episode_key": daily_plan["episode_key"],
        "production_date": daily_plan["production_date"],
        "pilot_id": daily_plan["pilot_id"],
        "format": format_id,
        "pillar": daily_plan["pillar"],
        "daily_plan_sha256": daily_plan_sha256,
        "source_stage_sha256": source_stage["source_stage_sha256"],
        "candidate_pool_sha256": candidate_pool["candidate_pool_sha256"],
        "source_queue_sha256": source_stage["source_queue_sha256"],
        "source_review_sha256": source_stage["source_review_sha256"],
        "candidate_count": candidate_count,
        "candidate_metrics": candidate_metrics,
        "reddit_http_request_cap": cap,
        "reddit_http_requests_observed": observed_requests,
        "network_mode": "bounded_read_only_reddit",
        "paid_provider_calls_submitted": {
            "openai": 0,
            "vectorengine": 0,
            "ai33": 0,
        },
        "youtube_called": False,
        "provider_spend_authorized": False,
        "production_authorized": False,
        "publication_authorized": False,
    }
    result["source_only_result_sha256"] = _self_hash(
        result, "source_only_result_sha256"
    )
    _atomic_json(root / "source-only-result.json", result)
    return result


class CallBudget:
    """Count provider generation calls before issuing them."""

    def __init__(
        self,
        provider: Callable[..., Any],
        *,
        cap: int,
        label: str,
        journal_path: Path | None = None,
        token_cap: int | None = None,
        allow_completed_resume: bool = False,
        allow_openai_default_fallback: bool = False,
    ):
        self.provider = provider
        self.cap = _positive_cap(cap, f"{label}_call_cap", maximum=256)
        self.label = label
        self.token_cap = (
            _positive_cap(token_cap, f"{label}_token_cap", maximum=1_000_000)
            if token_cap is not None else None
        )
        self.journal_path = Path(journal_path) if journal_path is not None else None
        if allow_openai_default_fallback and label != "openai":
            raise EpisodeFactoryError(
                "default service-tier fallback is valid only for OpenAI"
            )
        self.allow_openai_default_fallback = allow_openai_default_fallback
        self._openai_use_default_service_tier = False
        self._pending_flex_retry_request_sha256: str | None = None
        self.journal: dict[str, Any] = {
            "version": 1,
            "provider": label,
            "cap": self.cap,
            "attempts": [],
            "publication_authorized": False,
        }
        if self.token_cap is not None:
            self.journal["token_cap"] = self.token_cap
            self.journal["usage_totals"] = {
                "input_tokens": 0,
                "cached_input_tokens": 0,
                "output_tokens": 0,
                "total_tokens": 0,
                "reasoning_tokens": 0,
            }
        if self.journal_path is not None and self.journal_path.exists():
            previous = _read_object(self.journal_path)
            if (
                previous.get("version") != 1
                or previous.get("provider") != label
                or previous.get("cap") != self.cap
                or previous.get("token_cap") != self.token_cap
                or not isinstance(previous.get("attempts"), list)
            ):
                raise EpisodeFactoryError(f"{label} provider attempt journal is incompatible")
            if previous["attempts"] and not allow_completed_resume:
                raise EpisodeFactoryError(
                    f"{label} provider attempt journal is non-empty; inspect it before a new dispatch"
                )
            if previous["attempts"]:
                attempts = previous["attempts"]
                if label == "openai":
                    try:
                        _, self._pending_flex_retry_request_sha256 = (
                            validate_openai_attempt_sequence(attempts)
                        )
                    except FlexRecoveryError as exc:
                        raise EpisodeFactoryError(
                            "openai completed resume journal contains an "
                            "unresolved or invalid attempt"
                        ) from exc
                elif any(
                    not isinstance(item, dict)
                    or item.get("index") != index
                    or (
                        item.get("status") != "COMPLETE"
                        and not (
                            label == "image"
                            and item.get("status") == "AMBIGUOUS_ERROR"
                            and index == len(attempts)
                            and item.get("output_sha256") is None
                            and re.fullmatch(
                                r"[0-9a-f]{64}",
                                str(item.get("request_sha256") or ""),
                            )
                        )
                    )
                    for index, item in enumerate(attempts, start=1)
                ):
                    raise EpisodeFactoryError(
                        f"{label} completed resume journal contains an unresolved or invalid attempt"
                    )
                if self.token_cap is not None:
                    totals = previous.get("usage_totals")
                    usage_keys = {
                        "input_tokens", "cached_input_tokens", "output_tokens",
                        "total_tokens", "reasoning_tokens",
                    }
                    if not isinstance(totals, dict) or set(totals) != usage_keys:
                        raise EpisodeFactoryError(
                            f"{label} completed resume journal has invalid usage totals"
                        )
                    recomputed = {key: 0 for key in usage_keys}
                    for item in attempts:
                        if item.get("status") == REJECTED_FLEX_429_STATUS:
                            continue
                        usage = item.get("usage")
                        if not isinstance(usage, dict) or set(usage) != usage_keys:
                            raise EpisodeFactoryError(
                                f"{label} completed resume journal has incomplete usage evidence"
                            )
                        for key in usage_keys:
                            value = usage[key]
                            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                                raise EpisodeFactoryError(
                                    f"{label} completed resume journal has invalid token usage"
                                )
                            recomputed[key] += value
                    if recomputed != totals or totals["total_tokens"] > self.token_cap:
                        raise EpisodeFactoryError(
                            f"{label} completed resume journal usage totals do not reconcile"
                        )
                self.journal = previous
        if self.label == "openai" and self.allow_openai_default_fallback:
            self._openai_use_default_service_tier = any(
                item.get("status") == REJECTED_FLEX_429_STATUS
                or (
                    item.get("status") == "COMPLETE"
                    and item.get("service_tier") == FALLBACK_SERVICE_TIER
                )
                for item in self.journal["attempts"]
            )
        self.calls: list[dict[str, Any]] = self.journal["attempts"]
        self._write_journal()

    def _write_journal(self) -> None:
        if self.journal_path is not None:
            _atomic_json(self.journal_path, self.journal)

    def __call__(self, **kwargs):
        if len(self.calls) >= self.cap:
            raise EpisodeFactoryError(f"{self.label} call cap exhausted ({self.cap})")
        # Keep one logical budget unit equal to one paid generation request.
        # Automatic provider retries would otherwise multiply spend behind the
        # explicit factory cap.
        if self.label in {"openai", "image"}:
            kwargs.setdefault("retries", 0)
        prompt = str(kwargs.get("prompt") or kwargs.get("text") or "")
        request_sha256 = canonical_hash({
            "prompt": prompt,
            "model": kwargs.get("model") or kwargs.get("model_id"),
            "max_output_tokens": kwargs.get("max_output_tokens"),
            "voice_id": kwargs.get("voice_id"),
        })
        unresolved = [
            item for item in self.calls
            if item.get("status") != "COMPLETE"
            and not (
                self.label == "openai"
                and item.get("status") == REJECTED_FLEX_429_STATUS
                and item.get("index", 0) < len(self.calls)
                and self.calls[item["index"]].get("status") == "COMPLETE"
                and self.calls[item["index"]].get("request_sha256")
                == item.get("request_sha256")
            )
        ]
        pending_retry = self._pending_flex_retry_request_sha256
        if unresolved:
            if not (
                self.label == "openai"
                and pending_retry is not None
                and len(unresolved) == 1
                and unresolved[0] is self.calls[-1]
                and unresolved[0].get("status") == REJECTED_FLEX_429_STATUS
            ):
                raise EpisodeFactoryError(
                    f"{self.label} has an unresolved paid attempt; inspect the journal "
                    "before any further request"
                )
            if request_sha256 != pending_retry:
                raise EpisodeFactoryError(
                    "openai confirmed Flex 429 may retry only the exact saved request hash"
                )
        if self.token_cap is not None:
            used = int((self.journal.get("usage_totals") or {}).get("total_tokens") or 0)
            output_ceiling = int(kwargs.get("max_output_tokens") or 0)
            # UTF-8 bytes are a deliberately conservative upper bound for text
            # tokenization; reserve before transport so the cap is fail-closed.
            reserved_ceiling = len(prompt.encode("utf-8")) + 512 + output_ceiling
            if used + reserved_ceiling > self.token_cap:
                raise EpisodeFactoryError(
                    f"{self.label} token cap cannot reserve the next request "
                    f"({used}+{reserved_ceiling}>{self.token_cap})"
                )
        requested_service_tier: str | None = None
        fallback_from_attempt_index: int | None = None
        if self.label == "openai" and self.allow_openai_default_fallback:
            requested_service_tier = (
                FALLBACK_SERVICE_TIER
                if self._openai_use_default_service_tier or pending_retry is not None
                else REQUIRED_SERVICE_TIER
            )
            kwargs["service_tier"] = requested_service_tier
            if pending_retry is not None:
                fallback_from_attempt_index = int(unresolved[0]["index"])
        attempt = {
            "index": len(self.calls) + 1,
            "request_sha256": request_sha256,
            "model": kwargs.get("model") or kwargs.get("model_id"),
            "status": "IN_FLIGHT",
        }
        if requested_service_tier is not None:
            attempt["requested_service_tier"] = requested_service_tier
        if fallback_from_attempt_index is not None:
            attempt["fallback_from_attempt_index"] = fallback_from_attempt_index
        self.calls.append(attempt)
        self._pending_flex_retry_request_sha256 = None
        self._write_journal()
        while True:
            try:
                raw_response = self.provider(**kwargs)
                break
            except OpenAIFlexResourceUnavailableError:
                if kwargs.get("service_tier") == FALLBACK_SERVICE_TIER:
                    attempt["status"] = "AMBIGUOUS_ERROR"
                    attempt["error_type"] = "OpenAIFlexResourceUnavailableError"
                    self._write_journal()
                    raise
                attempt.update({
                    "status": REJECTED_FLEX_429_STATUS,
                    "error_type": REJECTED_FLEX_429_ERROR_TYPE,
                    "http_status": 429,
                    "service_tier": REQUIRED_SERVICE_TIER,
                    "rejection_reason": REJECTED_FLEX_429_REASON,
                    "provider_documented_not_charged": True,
                    "error_message_sha256": FLEX_RESOURCE_UNAVAILABLE_MARKER_SHA256,
                })
                self._openai_use_default_service_tier = True
                self._write_journal()
                if not self.allow_openai_default_fallback:
                    raise
                if len(self.calls) >= self.cap:
                    raise EpisodeFactoryError(
                        "openai call cap exhausted before the approved default-tier fallback"
                    )
                fallback_attempt = {
                    "index": len(self.calls) + 1,
                    "request_sha256": request_sha256,
                    "model": kwargs.get("model") or kwargs.get("model_id"),
                    "status": "IN_FLIGHT",
                    "requested_service_tier": FALLBACK_SERVICE_TIER,
                    "fallback_from_attempt_index": attempt["index"],
                }
                self.calls.append(fallback_attempt)
                attempt = fallback_attempt
                kwargs["service_tier"] = FALLBACK_SERVICE_TIER
                self._write_journal()
            except Exception as exc:
                attempt["status"] = "AMBIGUOUS_ERROR"
                attempt["error_type"] = type(exc).__name__
                self._write_journal()
                raise
        response = raw_response
        if isinstance(raw_response, OpenAIJSONResult):
            response = raw_response.payload
            usage = raw_response.usage
            attempt["usage"] = {
                "input_tokens": usage.input_tokens,
                "cached_input_tokens": usage.cached_input_tokens,
                "output_tokens": usage.output_tokens,
                "total_tokens": usage.total_tokens,
                "reasoning_tokens": usage.reasoning_tokens,
            }
            attempt["service_tier"] = raw_response.service_tier
            totals = self.journal.get("usage_totals")
            if not isinstance(totals, dict) or self.token_cap is None:
                attempt["status"] = "BLOCKED_MISSING_TOKEN_CAP"
                self._write_journal()
                raise EpisodeFactoryError("OpenAI response cannot be accepted without token cap")
            for key in totals:
                totals[key] = int(totals[key]) + int(attempt["usage"][key])
            if totals["total_tokens"] > self.token_cap:
                attempt["status"] = "BLOCKED_TOKEN_CAP_EXCEEDED"
                self._write_journal()
                raise EpisodeFactoryError("OpenAI actual usage exceeded the approved token cap")
            expected_service_tier = attempt.get(
                "requested_service_tier", REQUIRED_SERVICE_TIER,
            )
            if raw_response.service_tier != expected_service_tier:
                attempt["status"] = "BLOCKED_SERVICE_TIER_MISMATCH"
                self._write_journal()
                raise EpisodeFactoryError(
                    "OpenAI response did not prove the explicitly requested service tier"
                )
        elif self.token_cap is not None:
            attempt["status"] = "BLOCKED_MISSING_USAGE"
            self._write_journal()
            raise EpisodeFactoryError("OpenAI provider returned no validated usage envelope")
        attempt["status"] = "COMPLETE"
        if isinstance(response, dict):
            attempt["response_sha256"] = canonical_hash(_journal_hashable(response))
            task_id = str(response.get("task_id") or "").strip()
            if task_id:
                attempt["task_id"] = task_id
        elif isinstance(response, Path) and response.is_file():
            attempt["output_sha256"] = _sha256_file(response)
        else:
            attempt["response_sha256"] = canonical_hash(response)
        self._write_journal()
        return response


def _candidate_prompt(candidate: dict[str, Any], daily_plan: dict[str, Any], role: str) -> str:
    sources = [{
        "source_id": item["source_id"],
        "role": item["role"],
        "title": item["title"],
        "body": item["body"],
        "truth_mode": item["truth_mode"],
        "source_url": item["source_url"],
        "payoff_complete": item.get("payoff_complete") is True,
        "depends_on_screenshot_or_link": item.get("depends_on_screenshot_or_link") is not False,
        "reddit_discovery_signals": item.get("source_discovery_signals"),
    } for item in candidate["sources"]]
    maxima = json.dumps(SCORE_MAXIMA, ensure_ascii=False, sort_keys=True)
    minima = json.dumps(SCORE_MINIMA, ensure_ascii=False, sort_keys=True)
    veto_names = json.dumps(sorted(HARD_VETOES), ensure_ascii=False)
    common = f"""
You are the {role} in a strict Russian YouTube long-form topic playoff.
Assess this one complete Reddit candidate for the exact acc1 viewer promise.

Non-negotiable rules:
- Reddit votes/comments are discovery signals, never independent proof of truth or demand.
- Fiction must remain fiction; personal accounts remain independently unverified.
- A supplied r/nosleep source with truth_mode=fiction IS inside the acc1 viewer promise.
  "Без выдуманных продолжений" means preserve the supplied plot and ending; it does not
  exclude clearly labeled fiction. The downstream episode contract automatically requires
  the exact audible and metadata disclosure "Это художественная история с Reddit."
  Do not use fictional_as_real or viewer_promise_mismatch merely because a source is fiction.
  Use fictional_as_real only when the proposed framing explicitly presents fiction as a
  verified/real event or suppresses/contradicts that required disclosure.
- Do not invent facts, chronology, outcomes, hooks, people, or visual events.
- Any evidence field must be a short exact substring copied from a supplied source body.
- Every evidence quote must contain at least 24 characters, four words, and three unique words.
- The direction is fixed: format={daily_plan['format']}, pillar={daily_plan['pillar']}.
- Scorecard values are WEIGHTED POINTS, never percentages or 0-100 ratings.
  Exact maxima: {maxima}
  S-tier minima: {minima}
  The ten values sum to at most 100; PASS requires total >=90 and every category minimum.
  Never return a category value above its exact maximum.
- Allowed canonical veto names: {veto_names}. Use an empty list when no veto is proven.
- A canonical Reddit source_url is provenance, not screenshot/link dependency. Only declare
  screenshot_or_link_dependent when the supplied body itself cannot be understood or completed
  without external linked/screenshot/media content. Respect the supplied deterministic
  depends_on_screenshot_or_link=false unless an exact source quote proves otherwise.
- Use hard vetoes for wrong pillar, incomplete payoff, actual screenshot/link dependency,
  fictional-as-real framing, viewer-promise mismatch, unsafe/private-personal-data material,
  or advertiser-hostile treatment.

Viewer promise: {daily_plan.get('viewer_promise')}
Candidate: {json.dumps({'candidate_id': candidate['candidate_id'], 'sources': sources}, ensure_ascii=False)}
"""
    if role == "producer":
        return common + """
Return strict JSON:
{
  "viewer_promise_fit": true,
  "pillar_evidence": {"source_id":"exact candidate source_id","source_quote":"meaningful exact source quote"},
  "cold_open": {"text":"8-30 word natural Russian source-faithful cold open","source_id":"exact candidate source_id","source_quote":"meaningful exact source quote"},
  "payoff_evidence": {"source_id":"exact candidate source_id","source_quote":"meaningful exact ending quote; required for SAGA/BUNDLE"},
  "story_beats": [
    {"beat":"specific source-faithful editorial beat","source_id":"exact candidate source_id","source_quote":"exact quote from that source"}
  ],
  "originality_plan": {
    "editorial_frame":{"direction":"specific original framing","source_id":"exact candidate source_id","source_quote":"exact quote"},
    "visual_direction":{"direction":"specific source-supported visual treatment","source_id":"exact candidate source_id","source_quote":"exact quote"},
    "sound_direction":{"direction":"specific source-supported sound treatment","source_id":"exact candidate source_id","source_quote":"exact quote"}
  },
  "packaging_options": [
    {"youtube_title":"<=95 Russian chars","thumbnail_text":"<=32 Russian chars","first_screen_promise":"","angle":"distinct angle","source_id":"exact candidate source_id","source_backing":"meaningful exact source quote"}
  ],
  "veto_flags": [],
  "review": {
    "verdict":"PASS|BLOCK","veto_flags":[],
    "scorecard":{"hook_specificity":0,"stakes_clarity":0,"escalation":0,"payoff":0,"novelty":0,"russian_fit":0,"discussion_potential":0,"renderability":0,"packaging_honesty":0,"source_truth":0},
    "decision_reason":"specific reason"
  }
}
Return exactly 3-12 materially distinct story_beats and exactly three materially different packaging_options.
"""
    return common + f"""
Independently audit this producer proposal; do not copy its score and do not repair it:
{json.dumps(candidate.get('producer_proposal'), ensure_ascii=False)}
Return strict JSON:
{{"verdict":"PASS|BLOCK","veto_flags":[],"scorecard":{{"hook_specificity":0,"stakes_clarity":0,"escalation":0,"payoff":0,"novelty":0,"russian_fit":0,"discussion_potential":0,"renderability":0,"packaging_honesty":0,"source_truth":0}},"decision_reason":"specific independent reason"}}
"""


def _enrich_candidates(
    candidates: list[dict[str, Any]],
    daily_plan: dict[str, Any],
    openai: CallBudget,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    enriched: list[dict[str, Any]] = []
    producer_reports: list[dict[str, Any]] = []
    critic_reports: list[dict[str, Any]] = []
    for base in candidates:
        producer = openai(
            prompt=_candidate_prompt(base, daily_plan, "producer"),
            model=OPENAI_MODEL,
            temperature=0.25,
            max_output_tokens=8192,
        )
        if not isinstance(producer, dict) or not isinstance(producer.get("review"), dict):
            producer_reports.append({
                "candidate_id": base["candidate_id"],
                "status": "BLOCKED_INVALID_STRUCTURED_RESPONSE",
                "result": producer,
            })
            critic_reports.append({
                "candidate_id": base["candidate_id"],
                "status": "NOT_RUN_INVALID_PRODUCER_RESPONSE",
                "result": None,
            })
            continue
        candidate = copy.deepcopy(base)
        for field in (
            "viewer_promise_fit", "pillar_evidence", "cold_open", "payoff_evidence",
            "story_beats", "originality_plan", "packaging_options", "veto_flags",
        ):
            candidate[field] = copy.deepcopy(producer.get(field))
        candidate["producer_proposal"] = copy.deepcopy(producer)
        critic = openai(
            prompt=_candidate_prompt(candidate, daily_plan, "critic"),
            model=OPENAI_MODEL,
            temperature=0.0,
            max_output_tokens=4096,
        )
        if not isinstance(critic, dict):
            producer_reports.append({
                "candidate_id": base["candidate_id"],
                "status": "COMPLETE",
                "result": producer,
            })
            critic_reports.append({
                "candidate_id": base["candidate_id"],
                "status": "BLOCKED_INVALID_STRUCTURED_RESPONSE",
                "result": critic,
            })
            continue
        producer_review = copy.deepcopy(producer["review"])
        producer_review["role"] = "producer"
        critic_review = copy.deepcopy(critic)
        critic_review["role"] = "critic"
        candidate["reviews"] = [producer_review, critic_review]
        candidate.pop("producer_proposal", None)
        enriched.append(candidate)
        producer_reports.append({
            "candidate_id": base["candidate_id"],
            "status": "COMPLETE",
            "result": producer,
        })
        critic_reports.append({
            "candidate_id": base["candidate_id"],
            "status": "COMPLETE",
            "result": critic,
        })
    return enriched, producer_reports, critic_reports


EVIDENCE_FAILURE_RE = re.compile(
    r"^(?:candidates\[[0-9]+\]\.)?((?:pillar_evidence|cold_open|payoff_evidence)\.source_quote|"
    r"story_beats\[[0-9]+\]\.source_quote|"
    r"originality_plan\.(?:editorial_frame|visual_direction|sound_direction)\.source_quote|"
    r"packaging_options\[[0-9]+\]\.evidence\.source_quote) "
)


def _evidence_target(candidate: dict[str, Any], path: str) -> tuple[dict[str, Any], str]:
    simple = re.fullmatch(r"(pillar_evidence|cold_open|payoff_evidence)\.source_quote", path)
    if simple:
        return candidate[simple.group(1)], "source_quote"
    beat = re.fullmatch(r"story_beats\[([0-9]+)\]\.source_quote", path)
    if beat:
        return candidate["story_beats"][int(beat.group(1))], "source_quote"
    direction = re.fullmatch(
        r"originality_plan\.(editorial_frame|visual_direction|sound_direction)\.source_quote",
        path,
    )
    if direction:
        return candidate["originality_plan"][direction.group(1)], "source_quote"
    packaging = re.fullmatch(
        r"packaging_options\[([0-9]+)\]\.evidence\.source_quote", path,
    )
    if packaging:
        return candidate["packaging_options"][int(packaging.group(1))], "source_backing"
    raise EpisodeFactoryError(f"unsupported evidence repair path: {path}")


def _evidence_repair_prompt(candidate: dict[str, Any], paths: list[str]) -> str:
    targets = []
    for path in paths:
        holder, quote_field = _evidence_target(candidate, path)
        targets.append({
            "path": path,
            "source_id": str(holder.get("source_id") or ""),
            "current_quote": str(holder.get(quote_field) or ""),
        })
    sources = [
        {"source_id": item["source_id"], "body": item["body"]}
        for item in candidate["sources"]
    ]
    return f"""
You are correcting source evidence only. Do not rewrite or score any creative claim.
For every target, copy a meaningful verbatim substring from the named source body.
Preserve the exact source characters, punctuation, apostrophes, and whitespace.
Each quote must be at least 24 characters, at least four words, and at least three unique words.
Return every requested path exactly once and no other path. Keep each target's source_id unchanged.

Sources: {json.dumps(sources, ensure_ascii=False)}
Targets: {json.dumps(targets, ensure_ascii=False)}

Return strict JSON:
{{"repairs":[{{"path":"exact requested path","source_id":"unchanged source_id","source_quote":"exact source substring"}}]}}
"""


def _repair_quote_only_candidates(
    candidates: list[dict[str, Any]],
    preliminary_playoff: dict[str, Any],
    openai: CallBudget,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    repaired = copy.deepcopy(candidates)
    reports: list[dict[str, Any]] = []
    reviews_by_id = {
        str(item.get("candidate_id") or ""): item
        for item in preliminary_playoff.get("candidate_reviews") or []
        if isinstance(item, dict)
    }
    for candidate in repaired:
        candidate_id = str(candidate.get("candidate_id") or "")
        review = reviews_by_id.get(candidate_id) or {}
        failures = [str(item) for item in review.get("failures") or []]
        matches = [EVIDENCE_FAILURE_RE.match(item) for item in failures]
        paths = sorted({match.group(1) for match in matches if match})
        candidate_reviews = candidate.get("reviews") or []
        independent_passes = (
            len(candidate_reviews) == 2
            and all(
                isinstance(item, dict)
                and item.get("verdict") == "PASS"
                and not (item.get("veto_flags") or [])
                for item in candidate_reviews
            )
        )
        if not failures or len(paths) != len(failures) or not independent_passes:
            reports.append({
                "candidate_id": candidate_id,
                "status": "NOT_ELIGIBLE_FOR_EVIDENCE_ONLY_REPAIR",
                "failure_count": len(failures),
            })
            continue
        response = openai(
            prompt=_evidence_repair_prompt(candidate, paths),
            model=OPENAI_MODEL,
            temperature=0.0,
            max_output_tokens=4096,
        )
        repairs = response.get("repairs") if isinstance(response, dict) else None
        if not isinstance(repairs, list) or len(repairs) != len(paths):
            reports.append({
                "candidate_id": candidate_id,
                "status": "BLOCKED_INVALID_EVIDENCE_REPAIR",
                "requested_paths": paths,
            })
            continue
        by_path = {
            str(item.get("path") or ""): item
            for item in repairs
            if isinstance(item, dict)
        }
        if set(by_path) != set(paths):
            reports.append({
                "candidate_id": candidate_id,
                "status": "BLOCKED_INVALID_EVIDENCE_REPAIR",
                "requested_paths": paths,
            })
            continue
        valid = True
        for path in paths:
            holder, quote_field = _evidence_target(candidate, path)
            item = by_path[path]
            source_id = str(item.get("source_id") or "")
            quote = str(item.get("source_quote") or "")
            source = next(
                (value for value in candidate["sources"] if value["source_id"] == source_id),
                None,
            )
            words = [match.group(0).casefold() for match in SOURCE_WORD_RE.finditer(quote)]
            if (
                source_id != str(holder.get("source_id") or "")
                or source is None
                or quote not in source["body"]
                or len(quote) < 24
                or len(words) < 4
                or len(set(words)) < 3
            ):
                valid = False
                break
        if not valid:
            reports.append({
                "candidate_id": candidate_id,
                "status": "BLOCKED_INVALID_EVIDENCE_REPAIR",
                "requested_paths": paths,
            })
            continue
        for path in paths:
            holder, quote_field = _evidence_target(candidate, path)
            holder[quote_field] = str(by_path[path]["source_quote"])
        reports.append({
            "candidate_id": candidate_id,
            "status": "EVIDENCE_ONLY_REPAIR_APPLIED",
            "repaired_paths": paths,
        })
    return repaired, reports


def _validate_estimated_runtime(
    script: dict[str, Any], daily_plan: dict[str, Any],
) -> dict[str, Any]:
    target = (daily_plan.get("source_plan") or {}).get("target_duration_minutes")
    if (
        not isinstance(target, list)
        or len(target) != 2
        or any(
            isinstance(value, bool) or not isinstance(value, (int, float))
            for value in target
        )
    ):
        raise EpisodeFactoryError("daily plan has no exact two-value runtime target")
    minimum, maximum = float(target[0]), float(target[1])
    if minimum <= 0 or maximum <= minimum:
        raise EpisodeFactoryError("daily plan runtime target is invalid")
    try:
        spoken = narration_text(script)
    except CompilationStoryboardError as exc:
        raise EpisodeFactoryError("translated narration cannot be measured") from exc
    word_count = len(SOURCE_WORD_RE.findall(spoken))
    estimated_minutes = word_count / RUNTIME_ESTIMATE_WORDS_PER_MINUTE
    accepted_minimum = minimum * (1.0 - RUNTIME_ESTIMATE_TOLERANCE)
    accepted_maximum = maximum * (1.0 + RUNTIME_ESTIMATE_TOLERANCE)
    if not accepted_minimum <= estimated_minutes <= accepted_maximum:
        raise EpisodeFactoryError(
            "translated narration estimate "
            f"{estimated_minutes:.2f} minutes is outside the pre-TTS "
            f"{accepted_minimum:.2f}-{accepted_maximum:.2f} minute envelope"
        )
    return {
        "version": 1,
        "status": "PASS",
        "word_count": word_count,
        "words_per_minute": RUNTIME_ESTIMATE_WORDS_PER_MINUTE,
        "estimated_minutes": round(estimated_minutes, 3),
        "locked_target_minutes": [minimum, maximum],
        "pre_tts_tolerance": RUNTIME_ESTIMATE_TOLERANCE,
        "accepted_estimate_minutes": [
            round(accepted_minimum, 3), round(accepted_maximum, 3),
        ],
        "publication_authorized": False,
    }


def _git_sha() -> str:
    value = str(os.environ.get("GITHUB_SHA") or "").strip().lower()
    if re.fullmatch(r"[0-9a-f]{7,64}", value):
        return value
    try:
        value = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip().lower()
    except (OSError, subprocess.CalledProcessError) as exc:
        raise EpisodeFactoryError("cannot resolve git revision for immutable episode plan") from exc
    if not re.fullmatch(r"[0-9a-f]{7,64}", value):
        raise EpisodeFactoryError("git revision is invalid")
    return value


def _greenlight(daily_plan: dict[str, Any], winner: dict[str, Any], playoff: dict[str, Any]) -> dict[str, Any]:
    sources = [{
        "post_id": item["source_id"],
        "source_body_sha256": item["body_sha256"],
        "truth_mode": item["truth_mode"],
    } for item in winner["sources"]]
    return {
        "version": 1,
        "status": "PASS",
        "channel_id": "acc1",
        "episode_key": daily_plan["episode_key"],
        "pilot_id": daily_plan["pilot_id"],
        "format": daily_plan["format"],
        "pillar": daily_plan["pillar"],
        "candidate_id": winner["candidate_id"],
        "sources": sources,
        "playoff_sha256": playoff["playoff_sha256"],
        "production_authorized": True,
        "publication_authorized": False,
    }


def _transition_after(format_id: str, index: int, source_count: int) -> str:
    if index >= source_count:
        return ""
    if format_id == "BUNDLE":
        return "А теперь — следующая полная история."
    # THREAD already has a visible response boundary and a distinct comment
    # voice.  A separate spoken transition for every response wastes TTS tasks
    # and makes the reading less natural.
    return ""


def _visual_identity_contract(
    *,
    format_id: str,
    source: dict[str, Any],
    source_index: int,
    source_count: int,
) -> str:
    """Bind format-specific visual continuity without inventing source facts."""

    source_id = str(source.get("source_id") or source.get("post_id") or source_index)
    identity_token = hashlib.sha256(
        f"{format_id}\n{source_index}\n{source_id}".encode("utf-8"),
    ).hexdigest()[:12]
    if format_id == "SAGA":
        return (
            f"SAGA identity lock {identity_token}: this is one continuous illustrated story. "
            "Keep every source-supported recurring adult, face, body shape, hair, wardrobe, "
            "location, prop and time-of-day relationship stable across all page packs. "
            "Do not invent age, ethnicity, kinship, occupation, danger, evidence or emotion."
        )
    if format_id == "BUNDLE":
        return (
            f"BUNDLE mini-comic {source_index} of {source_count}, identity lock {identity_token}: "
            "keep this source's supported adult cast, silhouettes, wardrobe, location and props "
            "stable inside this mini-comic only. Give it a distinct supporting accent and panel "
            "rhythm, and never reuse its faces, clothing or story motif in another story. "
            "Do not invent demographic, relationship, evidence or outcome details."
        )
    source_role = str(
        source.get("source_role") or source.get("role") or "response",
    ).lower()
    if source_role == "prompt":
        return (
            f"THREAD prompt anchor {identity_token}: create one neutral community-question anchor "
            "from only the prompt's supported setting and objects. Avoid assigning a specific "
            "identity, demographic or personal backstory that the prompt does not state. Keep the "
            "paired plates coherent and visibly different from every response vignette."
        )
    response_number = max(1, source_index - 1)
    editorial_role = str(source.get("editorial_role") or "distinct viewpoint")
    return (
        f"THREAD response {response_number} of {max(1, source_count - 1)}, identity lock "
        f"{identity_token}, editorial role {editorial_role}: use one anonymous illustrative adult "
        "or source-supported group and one compact situation unique to this response. Keep the "
        "paired plates consistent, but change face, silhouette, pose, wardrobe palette, environment "
        "fragment and emotional function from every other response. Do not infer ethnicity, age, "
        "occupation, relationship, evidence or outcome beyond the exact response."
    )


def _translate_script(
    winner: dict[str, Any],
    *,
    daily_plan: dict[str, Any],
    episode_plan: dict[str, Any],
    playoff: dict[str, Any],
    openai: CallBudget,
    checkpoint_dir: Path,
    thread_final_adjudication_limit: int = 1,
) -> dict[str, Any]:
    translated_stories: list[dict[str, Any]] = []
    sources = winner["sources"]
    format_id = str(daily_plan["format"]).upper()
    if format_id not in {"BUNDLE", "SAGA", "THREAD"}:
        raise EpisodeFactoryError(
            f"unsupported episode format for translation review: {format_id}"
        )
    if (
        isinstance(thread_final_adjudication_limit, bool)
        or not isinstance(thread_final_adjudication_limit, int)
        or thread_final_adjudication_limit < 1
        or thread_final_adjudication_limit > len(sources)
    ):
        raise EpisodeFactoryError(
            "THREAD final adjudication limit must fit the exact source count"
        )
    thread_final_adjudications_used = 0
    for index, source in enumerate(sources, start=1):
        allow_final_adjudication = (
            format_id == "SAGA"
            or (
                format_id == "THREAD"
                and thread_final_adjudications_used
                < thread_final_adjudication_limit
            )
        )
        translated = translate_and_review_story(
            {"title": source["title"], "body": source["body"]},
            provider=openai,
            reviewer=openai,
            config=TranslationConfig(
                model=OPENAI_MODEL,
                max_output_tokens=16_384,
                max_story_revisions=(4 if format_id == "SAGA" else 2),
                allow_final_adjudication=allow_final_adjudication,
            ),
            chunk_checkpoint_path=checkpoint_dir / f"source-{index:02d}-translation.json",
            review_checkpoint_path=checkpoint_dir / f"source-{index:02d}-review.json",
        )
        review = translated["translation_audit"].get("review") or {}
        if (
            format_id == "THREAD"
            and review.get("resolution") == FINAL_ADJUDICATION_RESOLUTION
        ):
            thread_final_adjudications_used += 1
            if (
                thread_final_adjudications_used
                > thread_final_adjudication_limit
            ):
                raise EpisodeFactoryError(
                    "THREAD translation exceeded its bounded final adjudications"
                )
        role = "comment" if source["role"] == "response" else "narrator"
        translated_stories.append({
            "title_ru": translated["title"],
            "narration_ru": translated["body"],
            "hook_ru": translated["body"].split(".", 1)[0].strip()[:500],
            "transition_after_ru": _transition_after(
                daily_plan["format"], index, len(sources),
            ),
            "narration_role": role,
            "visual_identity_contract": _visual_identity_contract(
                format_id=str(daily_plan["format"]),
                source=source,
                source_index=index,
                source_count=len(sources),
            ),
            "source_snapshot": copy.deepcopy(source),
            "translation_audit": translated["translation_audit"],
            "ending_preserved_evidence": source["body"][-600:].strip(),
            "editorial_review": {"verdict": "PASS", "issues": []},
            "invented_factual_claims": [],
            "change_ledger": [],
            "disclosure": "fiction" if source["truth_mode"] == "fiction" else "unverified",
        })
    truth_modes = {item["truth_mode"] for item in sources}
    if len(truth_modes) != 1:
        raise EpisodeFactoryError("one episode must not mix fiction and unverified accounts")
    disclosure = truth_disclosure_ru(truth_modes, source_count=len(sources))
    cold_open = str((winner.get("cold_open") or {}).get("text") or "").strip()
    if not cold_open:
        raise EpisodeFactoryError("winning candidate has no source-backed cold open")
    format_label = {"SAGA": "большая история", "BUNDLE": "подборка историй", "THREAD": "ветка ответов"}[daily_plan["format"]]
    response_count = sum(1 for item in sources if item.get("role") == "response")
    try:
        intro_contract = build_intro_contract(
            cold_open=copy.deepcopy(winner.get("cold_open") or {}),
            episode_format=daily_plan["format"],
            pillar=daily_plan["pillar"],
            source_count=len(sources),
            response_count=response_count,
            first_title_ru=translated_stories[0]["title_ru"],
            truth_disclosure=disclosure,
        )
    except ValueError as exc:
        raise EpisodeFactoryError(f"cannot build the deterministic intro: {exc}") from exc
    cta_anchor_index = max(1, len(sources) // 2)
    try:
        mid_story_cta_contract = build_mid_story_cta_contract(
            episode_format=daily_plan["format"],
            pillar=daily_plan["pillar"],
            anchor_source=sources[cta_anchor_index - 1],
            anchor_index=cta_anchor_index,
            source_count=len(sources),
        )
    except ValueError as exc:
        raise EpisodeFactoryError(f"cannot build the deterministic mid-story CTA: {exc}") from exc
    script: dict[str, Any] = {
        "version": 1,
        "status": "ACCEPTED_FOR_ARTIFACT_PRODUCTION",
        "channel_id": "acc1",
        "episode_key": daily_plan["episode_key"],
        "pilot_id": daily_plan["pilot_id"],
        "episode_format": daily_plan["format"],
        "pillar": daily_plan["pillar"],
        "title_ru": f"Chonker Talks — {format_label}",
        "intro_contract": intro_contract,
        "intro_ru": intro_contract["intro_ru"],
        "mid_story_cta_contract": mid_story_cta_contract,
        "mid_story_cta_ru": mid_story_cta_contract["cta_ru"],
        "outro_ru": build_outro_prompt(
            episode_format=daily_plan["format"],
            pillar=daily_plan["pillar"],
            first_source=sources[0],
        ),
        "truth_disclosure_ru": disclosure,
        "source_story_beats": copy.deepcopy(winner.get("story_beats") or []),
        "originality_plan": copy.deepcopy(winner.get("originality_plan") or {}),
        "stories": translated_stories,
        "episode_plan_sha256": episode_plan["episode_plan_sha256"],
        "daily_plan_sha256": episode_plan["daily_plan_sha256"],
        "playoff_sha256": playoff["playoff_sha256"],
        "rights_mode": "test_only_not_cleared",
        "source_mode": "reddit_exact_sources",
        "revision_count": sum(int(item["translation_audit"].get("revisions") or 0) for item in translated_stories),
        "translation_final_adjudication_contract": {
            "version": TRANSLATION_FINAL_ADJUDICATION_CONTRACT_VERSION,
            "format": format_id,
            "thread_limit": (
                thread_final_adjudication_limit if format_id == "THREAD" else 0
            ),
            "thread_used": (
                thread_final_adjudications_used if format_id == "THREAD" else 0
            ),
            "basis": TRANSLATION_FINAL_ADJUDICATION_BASIS,
            "automatic_retries": 0,
            "publication_authorized": False,
        },
        "editorial_review": {"verdict": "PASS", "issues": []},
        "publication_authorized": False,
    }
    if daily_plan["format"] == "THREAD":
        comic_page_count = (
            daily_plan.get("source_plan") or {}
        ).get("comic_page_count")
        if comic_page_count != list(THREAD_COMIC_PAGE_COUNT):
            raise EpisodeFactoryError(
                "THREAD daily plan must carry the canonical comic-page target"
            )
        script["comic_page_count_target"] = list(comic_page_count)
    report = validate_episode_script(script, plan=episode_plan, playoff=playoff)
    if report["status"] != "PASS":
        raise EpisodeFactoryError("episode script contract blocked: " + "; ".join(report["failures"]))
    script["episode_contract"] = report
    return script


def _source_artifacts(workdir: Path, daily_plan: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    queue = _read_object(workdir / "source-queue.json")
    review = _read_object(workdir / "source-review.json")
    pool = _read_object(workdir / "candidate-pool.json")
    stage = _read_object(workdir / "source-stage.json")
    daily_sha = canonical_hash(daily_plan)
    if stage.get("status") != "SOURCE_READY" or not _verify_self_hash(stage, "source_stage_sha256"):
        raise EpisodeFactoryError("source-stage artifact is not self-verifying SOURCE_READY")
    if pool.get("status") != "SOURCE_FINALISTS_READY" or not _verify_self_hash(pool, "candidate_pool_sha256"):
        raise EpisodeFactoryError("candidate-pool artifact is not self-verifying")
    expected = {
        "daily_plan_sha256": daily_sha,
        "source_queue_sha256": canonical_hash(queue),
        "source_review_sha256": canonical_hash(review),
        "candidate_pool_sha256": pool["candidate_pool_sha256"],
    }
    for field, value in expected.items():
        if stage.get(field) != value:
            raise EpisodeFactoryError(f"source stage binding mismatch: {field}")
    if (
        pool.get("daily_plan_sha256") != daily_sha
        or not MIN_SOURCE_REVIEW_CANDIDATES
        <= len(pool.get("candidates") or [])
        <= MAX_SOURCE_REVIEW_CANDIDATES
        or pool.get("candidate_count") != len(pool.get("candidates") or [])
    ):
        raise EpisodeFactoryError("source finalists do not match the exact daily plan")
    return queue, review, pool, stage


def _factory_provider_contract() -> dict[str, Any]:
    return {
        "openai": {
            "provider": "openai",
            "model": OPENAI_MODEL,
            "reasoning_effort": "none",
            "max_output_tokens": 16_384,
            "automatic_retries": 0,
            "service_tier": REQUIRED_SERVICE_TIER,
            "fallback_service_tier": FALLBACK_SERVICE_TIER,
            "fallback_condition": "exact_flex_resource_unavailable_429",
            "maximum_fallback_requests_per_flex_rejection": 1,
            "prompt_cache_key": PROMPT_CACHE_KEY,
            "request_timeout_seconds": OPENAI_REQUEST_TIMEOUT_SECONDS,
        },
        "image": {
            "provider": "vectorengine",
            "model": DEFAULT_IMAGE_MODEL,
            "size": "1536x864",
            "automatic_retries": 0,
        },
        "ai33": {
            "provider": "ai33",
            "model_id": TTS_MODEL_ID,
            "narrator_voice_id": NARRATOR_VOICE_ID,
            "comment_voice_id": COMMENT_VOICE_ID,
            "speed": 1.0,
            "emotion_tags": False,
        },
    }


def _paid_candidate_cap_contract(
    candidates: list[dict[str, Any]],
    *,
    daily_plan: dict[str, Any],
    openai_call_cap: int,
    openai_token_cap: int,
    image_call_cap: int,
    ai33_call_cap: int,
    visual_mode: str = DEFAULT_VISUAL_MODE,
) -> dict[str, int]:
    openai_cap = _positive_cap(openai_call_cap, "openai_call_cap", maximum=256)
    openai_tokens = _positive_cap(openai_token_cap, "openai_token_cap", maximum=1_000_000)
    image_cap = _positive_cap(image_call_cap, "image_call_cap", maximum=256)
    ai33_cap = _positive_cap(ai33_call_cap, "ai33_call_cap", maximum=256)
    _validate_base_candidate_pool(candidates, daily_plan)
    source_counts = [len(item.get("sources") or []) for item in candidates]
    format_id = str(daily_plan["format"])
    image_floor = max(
        _required_image_calls(format_id, count, visual_mode)
        for count in source_counts
    )
    tts_ceiling = _required_ai33_calls(candidates, format_id)
    required_openai_calls = _required_openai_calls(candidates)
    if openai_cap < required_openai_calls:
        raise EpisodeFactoryError(
            f"source finalists require OpenAI cap {required_openai_calls} before the first "
            f"creative or translation request; configured cap is {openai_cap}"
        )
    if image_cap < image_floor:
        raise EpisodeFactoryError(
            f"source finalists require at least {image_floor} scene-image calls"
        )
    if ai33_cap < tts_ceiling:
        raise EpisodeFactoryError(
            f"source finalists require AI33 cap {tts_ceiling} before the first "
            f"paid text request; configured cap is {ai33_cap}"
        )
    return {
        "openai_call_cap": openai_cap,
        "openai_token_cap": openai_tokens,
        "image_call_cap": image_cap,
        "ai33_call_cap": ai33_cap,
        "required_openai_calls": required_openai_calls,
        "required_image_calls": image_floor,
        "required_ai33_calls": tts_ceiling,
    }


def _paid_preflight_contract(
    *,
    daily_plan: dict[str, Any],
    workdir: Path,
    channels_path: Path,
    confirm_openai_spend: str | bool,
    openai_call_cap: int,
    openai_token_cap: int,
    confirm_image_spend: str | bool,
    image_call_cap: int,
    confirm_ai33_spend: str | bool,
    ai33_call_cap: int,
    visual_mode: str,
    write_report: bool,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    try:
        resolved_visual_mode = resolve_visual_mode(visual_mode)
    except ValueError as exc:
        raise EpisodeFactoryError(str(exc)) from exc
    if (
        resolved_visual_mode == CINEMATIC_STORY_MODE
        and str(daily_plan.get("format") or "").upper() == "THREAD"
    ):
        raise EpisodeFactoryError(
            "cinematic_story_v1 supports SAGA/BUNDLE; THREAD uses the approved "
            "editorial_motion_v1 response-vignette contract",
        )
    if resolved_visual_mode == EDITORIAL_MOTION_MODE:
        style_profile = str(
            daily_plan.get("editorial_motion_style_profile") or "",
        ).strip()
        if style_profile != FORMAT_VISUAL_SYSTEM_V3_STYLE_PROFILE:
            raise EpisodeFactoryError(
                "daily plan editorial_motion_style_profile must use the "
                "approved v3 format system",
            )

    pillar_id = str(daily_plan.get("pillar") or "").strip()
    try:
        narration_profile = resolve_narration_profile(
            NARRATION_PROFILE_IDS_BY_PILLAR.get(pillar_id, ""),
            pillar_id=pillar_id,
        )
    except NarrationProfileError as exc:
        raise EpisodeFactoryError(str(exc)) from exc
    _exact_confirmation(confirm_openai_spend, "confirm_openai_spend")
    _exact_confirmation(confirm_image_spend, "confirm_image_spend")
    _exact_confirmation(confirm_ai33_spend, "confirm_ai33_spend")
    workdir = Path(workdir)
    validate_daily_plan(daily_plan, channels_path)
    queue, source_review, pool, source_stage = _source_artifacts(workdir, daily_plan)
    candidates = pool.get("candidates") or []
    cap_contract = _paid_candidate_cap_contract(
        candidates,
        daily_plan=daily_plan,
        openai_call_cap=openai_call_cap,
        openai_token_cap=openai_token_cap,
        image_call_cap=image_call_cap,
        ai33_call_cap=ai33_call_cap,
        visual_mode=resolved_visual_mode,
    )
    try:
        get_vectorengine_api_key()
    except VectorEngineError as exc:
        raise EpisodeFactoryError("paid preflight could not resolve image credentials") from exc
    if not str(os.environ.get("OPENAI_API_KEY") or "").strip():
        raise EpisodeFactoryError("OPENAI_API_KEY is required before creating the paid spend lease")
    api_key = str(os.environ.get("AI33_API_KEY") or os.environ.get("A133_API_KEY") or "")
    if not api_key:
        raise EpisodeFactoryError("AI33_API_KEY is required before creating the paid spend lease")
    provider_contract = _factory_provider_contract()
    if provider_contract != SPEND_LOCK_PROVIDER_CONTRACT:
        raise EpisodeFactoryError("factory provider/model contract drifted from spend-lock schema")
    report = {
        "version": FACTORY_VERSION,
        "status": "PAID_PREFLIGHT_PASS",
        "visual_mode": resolved_visual_mode,
        "narration_profile_id": narration_profile["profile_id"],
        "narration_profile_sha256": narration_profile["profile_sha256"],
        "daily_plan_sha256": canonical_hash(daily_plan),
        "source_stage_sha256": source_stage["source_stage_sha256"],
        "candidate_pool_sha256": pool["candidate_pool_sha256"],
        "candidate_count": len(candidates),
        "caps": cap_contract,
        "provider_contract": provider_contract,
        "runtime_budget": {
            "workflow_timeout_minutes": WORKFLOW_TIMEOUT_MINUTES,
            "produce_timeout_minutes": PRODUCE_TIMEOUT_MINUTES,
            "ai33_deadline_from_produce_start_minutes": (
                AI33_DEADLINE_FROM_PRODUCE_START_MINUTES
            ),
            "post_ai33_render_qa_reserve_minutes": POST_AI33_RENDER_QA_RESERVE_MINUTES,
            "required_openai_calls": cap_contract["required_openai_calls"],
            "openai_token_cap": cap_contract["openai_token_cap"],
            "required_ai33_calls": cap_contract["required_ai33_calls"],
            "timeout_is_a_ceiling_not_an_sla": True,
            "automatic_paid_resume": False,
        },
        "would_call_openai": False,
        "would_call_image_provider": False,
        "would_call_ai33": False,
        "publication_authorized": False,
    }
    if write_report:
        _atomic_json(workdir / "paid-preflight.json", report)
    return queue, source_review, pool, source_stage, report


def run_paid_preflight(
    *,
    daily_plan: dict[str, Any],
    workdir: Path,
    channels_path: Path,
    confirm_openai_spend: str | bool,
    openai_call_cap: int,
    openai_token_cap: int,
    confirm_image_spend: str | bool,
    image_call_cap: int,
    confirm_ai33_spend: str | bool,
    ai33_call_cap: int,
    visual_mode: str = DEFAULT_VISUAL_MODE,
) -> dict[str, Any]:
    """Prove paid readiness without issuing any provider generation request."""
    *_, report = _paid_preflight_contract(
        daily_plan=daily_plan,
        workdir=workdir,
        channels_path=channels_path,
        confirm_openai_spend=confirm_openai_spend,
        openai_call_cap=openai_call_cap,
        openai_token_cap=openai_token_cap,
        confirm_image_spend=confirm_image_spend,
        image_call_cap=image_call_cap,
        confirm_ai33_spend=confirm_ai33_spend,
        ai33_call_cap=ai33_call_cap,
        visual_mode=visual_mode,
        write_report=True,
    )
    return report


def _github_lease_identity(lease: dict[str, Any]) -> tuple[str, int | None, int | None, str | None]:
    repository = str(os.environ.get("GITHUB_REPOSITORY") or lease.get("repository") or "")
    if str(os.environ.get("GITHUB_ACTIONS") or "").lower() != "true":
        return repository, None, None, None
    required = {
        "GITHUB_REPOSITORY": os.environ.get("GITHUB_REPOSITORY"),
        "GITHUB_RUN_ID": os.environ.get("GITHUB_RUN_ID"),
        "GITHUB_RUN_ATTEMPT": os.environ.get("GITHUB_RUN_ATTEMPT"),
        "GITHUB_SHA": os.environ.get("GITHUB_SHA"),
    }
    missing = [name for name, value in required.items() if not str(value or "").strip()]
    if missing:
        raise EpisodeFactoryError(
            "GitHub spend-lease identity is incomplete: " + ", ".join(sorted(missing))
        )
    try:
        run_id = int(str(required["GITHUB_RUN_ID"]))
        run_attempt = int(str(required["GITHUB_RUN_ATTEMPT"]))
    except ValueError as exc:
        raise EpisodeFactoryError("GitHub spend-lease run identity is invalid") from exc
    return repository, run_id, run_attempt, str(required["GITHUB_SHA"])


def _validate_spend_lease_contract(
    spend_lease_path: Path | None,
    *,
    daily_plan: dict[str, Any],
    workdir: Path,
    queue: dict[str, Any],
    source_review: dict[str, Any],
    pool: dict[str, Any],
    source_stage: dict[str, Any],
    reddit_request_cap: int,
    openai_call_cap: int,
    openai_token_cap: int,
    image_call_cap: int,
    ai33_call_cap: int,
) -> dict[str, Any]:
    expected_path = (Path(workdir) / "spend-lease.json").resolve()
    if spend_lease_path is None or Path(spend_lease_path).resolve() != expected_path:
        raise EpisodeFactoryError("produce requires the exact workdir spend-lease.json")
    lease = _read_object(expected_path)
    repository, run_id, run_attempt, head_sha = _github_lease_identity(lease)
    try:
        validate_lease_for_production(
            lease,
            plan=daily_plan,
            source_stage=source_stage,
            candidate_pool=pool,
            source_queue=queue,
            source_review=source_review,
            repository=repository,
            workflow_path=SPEND_LOCK_WORKFLOW_PATH,
            requested_caps={
                "reddit_request_cap": _positive_cap(
                    reddit_request_cap, "reddit_request_cap", maximum=100,
                ),
                "openai_call_cap": openai_call_cap,
                "openai_token_cap": openai_token_cap,
                "image_call_cap": image_call_cap,
                "ai33_call_cap": ai33_call_cap,
            },
            confirmations={
                "reddit_read": True,
                "openai_spend": True,
                "image_spend": True,
                "ai33_spend": True,
            },
            provider_contract=_factory_provider_contract(),
            run_id=run_id,
            run_attempt=run_attempt,
            head_sha=head_sha,
        )
    except SpendLockError as exc:
        raise EpisodeFactoryError(f"paid spend lease blocked: {exc}") from exc
    return lease


def _validate_resume_contract(
    *,
    resume_lease_path: Path | None,
    parent_run_id: int,
    daily_plan: dict[str, Any],
    workdir: Path,
    queue: dict[str, Any],
    source_review: dict[str, Any],
    pool: dict[str, Any],
    source_stage: dict[str, Any],
    openai_call_cap: int,
    openai_token_cap: int,
    image_call_cap: int,
    ai33_call_cap: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    expected_path = (workdir / "resume-spend-lease.json").resolve()
    if resume_lease_path is None or Path(resume_lease_path).resolve() != expected_path:
        raise EpisodeFactoryError("resume produce requires the exact workdir resume-spend-lease.json")
    resume_lease = _read_object(expected_path)
    repository, run_id, run_attempt, head_sha = _github_lease_identity(resume_lease)
    try:
        validate_resume_lease(
            resume_lease,
            repository=repository,
            run_id=run_id,
            run_attempt=run_attempt,
            head_sha=head_sha,
            parent_run_id=parent_run_id,
        )
    except ResumeLockError as exc:
        raise EpisodeFactoryError(f"paid resume lease blocked: {exc}") from exc
    requested_caps = {
        "openai_call_cap": openai_call_cap,
        "openai_token_cap": openai_token_cap,
        "image_call_cap": image_call_cap,
        "ai33_call_cap": ai33_call_cap,
    }
    if resume_lease.get("caps") != requested_caps:
        raise EpisodeFactoryError("paid resume lease caps do not match this dispatch")

    parent_lease = _read_object(workdir / "spend-lease.json")
    try:
        validate_lease_for_production(
            parent_lease,
            plan=daily_plan,
            source_stage=source_stage,
            candidate_pool=pool,
            source_queue=queue,
            source_review=source_review,
            repository=repository,
            workflow_path=SPEND_LOCK_WORKFLOW_PATH,
            requested_caps=parent_lease.get("requested_caps") or {},
            confirmations=parent_lease.get("confirmations") or {},
            provider_contract=parent_lease.get("provider_contract") or {},
            run_id=parent_lease.get("run_id"),
            run_attempt=parent_lease.get("run_attempt"),
            head_sha=parent_lease.get("head_sha"),
            require_current_provider_contract=False,
        )
    except SpendLockError as exc:
        raise EpisodeFactoryError(f"parent paid spend lease blocked: {exc}") from exc

    paths = {
        "parent_spend_lease_sha256": workdir / "spend-lease.json",
        "parent_topic_input_sha256": workdir / "topic-playoff-input.json",
        "parent_producer_review_sha256": workdir / "producer-review.json",
        "parent_critic_review_sha256": workdir / "critic-review.json",
        "parent_openai_journal_sha256": workdir / "provider-attempts" / "openai.json",
    }
    if resume_lease.get("parent_openai_flex_rejection_proof_sha256") is not None:
        paths["parent_openai_flex_rejection_proof_sha256"] = (
            workdir / "openai-flex-429-rejection.json"
        )
    if resume_lease.get("parent_image_journal_sha256") is not None:
        paths["parent_image_journal_sha256"] = (
            workdir / "provider-attempts" / "image.json"
        )
    if resume_lease.get("parent_image_checkpoint_sha256") is not None:
        paths["parent_image_checkpoint_sha256"] = workdir / "scene-image-checkpoint.json"
    if resume_lease.get("parent_ai33_journal_sha256") is not None:
        paths["parent_ai33_journal_sha256"] = (
            workdir / "provider-attempts" / "ai33.json"
        )
    if resume_lease.get("parent_tts_state_sha256") is not None:
        paths["parent_tts_state_sha256"] = workdir / "tts" / "compilation_tts_state.json"
    parent_resume_hash = resume_lease.get("parent_resume_lease_sha256")
    if parent_resume_hash is not None:
        parent_resume_path = workdir / "parent-resume-spend-lease.json"
        parent_resume = _read_object(parent_resume_path)
        try:
            validate_resume_lease(
                parent_resume,
                repository=repository,
                run_id=parent_run_id,
            )
        except ResumeLockError as exc:
            raise EpisodeFactoryError(f"parent paid resume lease blocked: {exc}") from exc
        if resume_canonical_hash(parent_resume) != parent_resume_hash:
            raise EpisodeFactoryError("paid resume parent resume-lease hash mismatch")
    payloads = {field: _read_object(path) for field, path in paths.items()}
    for field, payload in payloads.items():
        if resume_canonical_hash(payload) != resume_lease.get(field):
            raise EpisodeFactoryError(f"paid resume parent evidence hash mismatch: {field}")
    journal_attempts = payloads["parent_openai_journal_sha256"].get("attempts") or []
    if len(journal_attempts) != resume_lease.get("parent_completed_openai_attempts"):
        raise EpisodeFactoryError("paid resume parent OpenAI attempt count mismatch")
    if "parent_image_journal_sha256" in payloads:
        image_attempts = payloads["parent_image_journal_sha256"].get("attempts") or []
        if len(image_attempts) != resume_lease.get("parent_completed_image_attempts"):
            raise EpisodeFactoryError("paid resume parent image attempt count mismatch")
    if "parent_ai33_journal_sha256" in payloads:
        ai33_attempts = payloads["parent_ai33_journal_sha256"].get("attempts") or []
        if len(ai33_attempts) != resume_lease.get("parent_completed_ai33_attempts"):
            raise EpisodeFactoryError("paid resume parent AI33 attempt count mismatch")

    playoff_input = payloads["parent_topic_input_sha256"]
    if playoff_input.get("daily_plan_sha256") != canonical_hash(daily_plan):
        raise EpisodeFactoryError("paid resume topic input is not bound to the restored plan")
    enriched = playoff_input.get("candidates")
    if not isinstance(enriched, list) or not enriched:
        raise EpisodeFactoryError("paid resume topic input has no reviewed candidates")
    pool_ids = [str(item.get("candidate_id") or "") for item in pool.get("candidates") or []]
    enriched_ids = [str(item.get("candidate_id") or "") for item in enriched]
    if pool_ids != enriched_ids:
        raise EpisodeFactoryError("paid resume reviewed candidates do not match the restored source pool")
    producer_reports = payloads["parent_producer_review_sha256"].get("results")
    critic_reports = payloads["parent_critic_review_sha256"].get("results")
    if not isinstance(producer_reports, list) or not isinstance(critic_reports, list):
        raise EpisodeFactoryError("paid resume review evidence is malformed")
    return copy.deepcopy(enriched), copy.deepcopy(producer_reports), copy.deepcopy(critic_reports)


def _resolve_episode_plan(
    *, is_resume: bool, path: Path, daily_plan: dict[str, Any],
    queue: dict[str, Any], playoff: dict[str, Any], greenlight: dict[str, Any],
    channel: dict[str, Any], provider_settings: dict[str, Any],
    winner: dict[str, Any], visual_mode: str, narration_profile_id: str,
) -> dict[str, Any]:
    """Reuse an exact validated plan across commits instead of changing its identity."""
    if is_resume and path.exists():
        episode_plan = _read_object(path)
        report = validate_episode_manifest(
            episode_plan,
            source_queue=queue,
            topic_review=playoff,
            greenlight=greenlight,
            config=channel,
            daily_plan=daily_plan,
        )
        if report.get("status") != "PASS":
            raise EpisodeFactoryError(
                "restored episode plan is incompatible: "
                + "; ".join(report.get("failures") or [])
            )
        if episode_plan.get("provider_settings") != provider_settings:
            raise EpisodeFactoryError(
                "restored episode plan provider settings do not match the current contract"
            )
        if episode_plan.get("visual_mode") != visual_mode:
            raise EpisodeFactoryError(
                "restored episode plan visual mode does not match the current contract"
            )
        if episode_plan.get("narration_profile_id") != narration_profile_id:
            raise EpisodeFactoryError(
                "restored episode plan narration profile does not match the current contract"
            )
        return episode_plan
    return build_episode_manifest(
        episode_key=daily_plan["episode_key"],
        episode_date=daily_plan["production_date"],
        pilot_id=daily_plan["pilot_id"],
        format_id=daily_plan["format"],
        pillar=daily_plan["pillar"],
        source_queue=queue,
        topic_review=playoff,
        greenlight=greenlight,
        config=channel,
        daily_plan=daily_plan,
        git_sha=_git_sha(),
        provider_settings=provider_settings,
        sources=[{
            "post_id": item["source_id"],
            "body_sha256": item["body_sha256"],
            "truth_mode": item["truth_mode"],
        } for item in winner["sources"]],
        visual_mode=visual_mode,
        narration_profile_id=narration_profile_id,
    )


def run_produce_stage(
    *,
    daily_plan: dict[str, Any],
    workdir: Path,
    channels_path: Path,
    confirm_openai_spend: str | bool,
    openai_call_cap: int,
    openai_token_cap: int,
    confirm_image_spend: str | bool,
    image_call_cap: int,
    confirm_ai33_spend: str | bool,
    ai33_call_cap: int,
    reddit_request_cap: int = 24,
    spend_lease_path: Path | None = None,
    resume_review_run_id: int | None = None,
    resume_lease_path: Path | None = None,
    openai_provider: Callable[..., OpenAIJSONResult] = call_openai_json,
    image_provider: Callable[..., Path] = call_image_generation,
    visual_mode: str = DEFAULT_VISUAL_MODE,
) -> dict[str, Any]:
    """Create the review artifact after source and all spend gates have passed."""
    workdir = Path(workdir)
    try:
        resolved_visual_mode = resolve_visual_mode(visual_mode)
    except ValueError as exc:
        raise EpisodeFactoryError(str(exc)) from exc
    if (
        resolved_visual_mode == CINEMATIC_STORY_MODE
        and str(daily_plan.get("format") or "").upper() == "THREAD"
    ):
        raise EpisodeFactoryError(
            "cinematic_story_v1 supports SAGA/BUNDLE; THREAD uses the approved "
            "editorial_motion_v1 response-vignette contract",
        )
    style_profile: str | None = None
    if resolved_visual_mode == EDITORIAL_MOTION_MODE:
        style_profile = str(
            daily_plan.get("editorial_motion_style_profile") or "",
        ).strip()
        if style_profile != FORMAT_VISUAL_SYSTEM_V3_STYLE_PROFILE:
            raise EpisodeFactoryError(
                "daily plan editorial_motion_style_profile must use the "
                "approved v3 format system",
            )
    pillar_id = str(daily_plan.get("pillar") or "").strip()
    narration_profile_id = NARRATION_PROFILE_IDS_BY_PILLAR.get(pillar_id, "")
    try:
        narration_profile = resolve_narration_profile(
            narration_profile_id,
            pillar_id=pillar_id,
        )
    except NarrationProfileError as exc:
        raise EpisodeFactoryError(str(exc)) from exc
    queue, source_review, pool, source_stage, paid_preflight = _paid_preflight_contract(
        daily_plan=daily_plan,
        workdir=workdir,
        channels_path=channels_path,
        confirm_openai_spend=confirm_openai_spend,
        openai_call_cap=openai_call_cap,
        openai_token_cap=openai_token_cap,
        confirm_image_spend=confirm_image_spend,
        image_call_cap=image_call_cap,
        confirm_ai33_spend=confirm_ai33_spend,
        ai33_call_cap=ai33_call_cap,
        visual_mode=resolved_visual_mode,
        write_report=True,
    )
    openai_cap = int(paid_preflight["caps"]["openai_call_cap"])
    openai_tokens = int(paid_preflight["caps"]["openai_token_cap"])
    image_cap = int(paid_preflight["caps"]["image_call_cap"])
    ai33_cap = int(paid_preflight["caps"]["ai33_call_cap"])
    is_resume = resume_review_run_id is not None
    if is_resume:
        enriched, producer_reports, critic_reports = _validate_resume_contract(
            resume_lease_path=resume_lease_path,
            parent_run_id=int(resume_review_run_id),
            daily_plan=daily_plan,
            workdir=workdir,
            queue=queue,
            source_review=source_review,
            pool=pool,
            source_stage=source_stage,
            openai_call_cap=openai_cap,
            openai_token_cap=openai_tokens,
            image_call_cap=image_cap,
            ai33_call_cap=ai33_cap,
        )
    else:
        _validate_spend_lease_contract(
            spend_lease_path,
            daily_plan=daily_plan,
            workdir=workdir,
            queue=queue,
            source_review=source_review,
            pool=pool,
            source_stage=source_stage,
            reddit_request_cap=reddit_request_cap,
            openai_call_cap=openai_cap,
            openai_token_cap=openai_tokens,
            image_call_cap=image_cap,
            ai33_call_cap=ai33_cap,
        )
    api_key = str(os.environ.get("AI33_API_KEY") or os.environ.get("A133_API_KEY") or "")
    channel = _channel_config(channels_path)
    provider_journal_dir = workdir / "provider-attempts"
    candidates = pool.get("candidates") or []

    openai = CallBudget(
        openai_provider,
        cap=openai_cap,
        token_cap=openai_tokens,
        label="openai",
        journal_path=provider_journal_dir / "openai.json",
        allow_completed_resume=is_resume,
        allow_openai_default_fallback=True,
    )
    images = CallBudget(
        image_provider,
        cap=image_cap,
        label="image",
        journal_path=provider_journal_dir / "image.json",
        allow_completed_resume=is_resume,
    )

    if not is_resume:
        enriched, producer_reports, critic_reports = _enrich_candidates(
            candidates, daily_plan, openai,
        )
    _atomic_json(workdir / "producer-review.json", {
        "version": 1, "results": producer_reports,
        "daily_plan_sha256": canonical_hash(daily_plan), "publication_authorized": False,
    })
    _atomic_json(workdir / "critic-review.json", {
        "version": 1, "results": critic_reports,
        "daily_plan_sha256": canonical_hash(daily_plan), "publication_authorized": False,
    })
    preliminary_playoff_input = {
        "daily_plan": daily_plan,
        "daily_plan_sha256": canonical_hash(daily_plan),
        "candidates": enriched,
    }
    preliminary_playoff = run_playoff(preliminary_playoff_input)
    _atomic_json(workdir / "topic-playoff-pre-repair.json", preliminary_playoff)
    if preliminary_playoff.get("status") != "READY_FOR_SCRIPTING":
        enriched, repair_reports = _repair_quote_only_candidates(
            enriched, preliminary_playoff, openai,
        )
    else:
        repair_reports = []
    _atomic_json(workdir / "evidence-repair.json", {
        "version": 1,
        "results": repair_reports,
        "preliminary_playoff_sha256": preliminary_playoff.get("playoff_sha256"),
        "publication_authorized": False,
    })
    playoff_input = {
        "daily_plan": daily_plan,
        "daily_plan_sha256": canonical_hash(daily_plan),
        "candidates": enriched,
    }
    _atomic_json(workdir / "topic-playoff-input.json", playoff_input)
    playoff = run_playoff(playoff_input)
    _atomic_json(workdir / "topic-playoff.json", playoff)
    if playoff.get("status") != "READY_FOR_SCRIPTING":
        raise EpisodeFactoryError("S-tier topic playoff blocked: " + "; ".join(playoff.get("failures") or []))
    if not _verify_self_hash(playoff, "playoff_sha256"):
        raise EpisodeFactoryError("topic playoff output failed its self-hash contract")
    if playoff.get("playoff_input_sha256") != canonical_hash(playoff_input):
        raise EpisodeFactoryError("topic playoff is not bound to the exact finalist input")
    winner_id = str(playoff["winner"]["candidate_id"])
    winner = next((item for item in enriched if item["candidate_id"] == winner_id), None)
    if winner is None:
        raise EpisodeFactoryError("topic playoff winner is absent from bound finalists")
    if playoff["winner"].get("candidate_contract_sha256") != canonical_hash(winner):
        raise EpisodeFactoryError("topic playoff winner contract does not match the exact finalist")
    try:
        narration_boundary_contract = resolve_narration_boundary_contract(
            narration_profile,
            episode_format=daily_plan["format"],
            source_count=len(winner["sources"]),
        )
    except NarrationProfileError as exc:
        raise EpisodeFactoryError(str(exc)) from exc
    required_image_calls = _required_image_calls(
        str(daily_plan["format"]),
        len(winner["sources"]),
        resolved_visual_mode,
    )
    if images.cap < required_image_calls:
        raise EpisodeFactoryError(
            f"episode requires {required_image_calls} scene-image calls "
            f"but image_call_cap is {images.cap}"
        )
    thread_final_adjudication_limit = 1
    if str(daily_plan["format"]).upper() == "THREAD":
        thread_final_adjudication_limit = _thread_final_adjudication_limit(
            openai_call_cap=openai.cap,
            required_openai_calls=int(
                paid_preflight["caps"]["required_openai_calls"]
            ),
            source_count=len(winner["sources"]),
        )

    greenlight = _greenlight(daily_plan, winner, playoff)
    try:
        pronunciation_dictionary = load_acc1_pronunciation_dictionary()
        pronunciation_dictionary_id = resolve_acc1_pronunciation_dictionary_id(required=True)
    except PronunciationDictionaryError as exc:
        raise EpisodeFactoryError(str(exc)) from exc
    provider_settings = {
        "creative": {
            "provider": "openai",
            "model": OPENAI_MODEL,
            "reasoning_effort": "none",
            "max_output_tokens": 16_384,
            "service_tier": REQUIRED_SERVICE_TIER,
            "fallback_service_tier": FALLBACK_SERVICE_TIER,
            "fallback_condition": "exact_flex_resource_unavailable_429",
            "prompt_cache_key": PROMPT_CACHE_KEY,
            "request_timeout_seconds": OPENAI_REQUEST_TIMEOUT_SECONDS,
        },
        "translation": {
            "provider": "openai",
            "model": OPENAI_MODEL,
            "reviewer_provider": "openai",
            "reviewer_model": OPENAI_MODEL,
            "reasoning_effort": "none",
            "max_output_tokens": 16_384,
            "service_tier": REQUIRED_SERVICE_TIER,
            "fallback_service_tier": FALLBACK_SERVICE_TIER,
            "fallback_condition": "exact_flex_resource_unavailable_429",
            "prompt_cache_key": PROMPT_CACHE_KEY,
            "request_timeout_seconds": OPENAI_REQUEST_TIMEOUT_SECONDS,
        },
        "image": {"provider": "vectorengine", "model": DEFAULT_IMAGE_MODEL, "size": "1536x864"},
        "tts": {
            "provider": "ai33", "model_id": TTS_MODEL_ID,
            "narrator_voice_id": NARRATOR_VOICE_ID,
            "comment_voice_id": COMMENT_VOICE_ID,
            "narration_profile_id": narration_profile["profile_id"],
            "narration_profile_sha256": narration_profile["profile_sha256"],
            "narration_boundary_contract": copy.deepcopy(
                narration_boundary_contract,
            ),
            "narration_boundary_contract_sha256": narration_boundary_contract[
                "narration_boundary_contract_sha256"
            ],
            "speed": narration_profile["speed"],
            "voice_settings_json": narration_profile["voice_settings_json"],
            "emotion_tags": False,
            "pronunciation_dictionary_id": pronunciation_dictionary_id,
            "pronunciation_dictionary_sha256": pronunciation_dictionary["sha256"],
        },
    }
    episode_plan_path = workdir / "episode-plan.json"
    episode_plan = _resolve_episode_plan(
        is_resume=is_resume,
        path=episode_plan_path,
        daily_plan=daily_plan,
        queue=queue,
        playoff=playoff,
        greenlight=greenlight,
        channel=channel,
        provider_settings=provider_settings,
        winner=winner,
        visual_mode=resolved_visual_mode,
        narration_profile_id=narration_profile["profile_id"],
    )

    _atomic_json(workdir / "episode-greenlight.json", greenlight)
    _atomic_json(episode_plan_path, episode_plan)

    script = _translate_script(
        winner,
        daily_plan=daily_plan,
        episode_plan=episode_plan,
        playoff=playoff,
        openai=openai,
        checkpoint_dir=workdir / "translation-checkpoints",
        thread_final_adjudication_limit=thread_final_adjudication_limit,
    )
    script["visual_mode"] = resolved_visual_mode
    if style_profile:
        script["style_profile"] = style_profile
    script["narration_profile_id"] = narration_profile["profile_id"]
    script["narration_profile_sha256"] = narration_profile["profile_sha256"]
    script["narration_boundary_contract"] = copy.deepcopy(
        narration_boundary_contract,
    )
    script["pillar"] = pillar_id
    if resolved_visual_mode == DEFAULT_VISUAL_MODE:
        try:
            text_layout_report = validate_compilation_text_layout(script)
        except CompilationRenderError as exc:
            raise EpisodeFactoryError(
                "translated episode cannot fit the production Reddit-card "
                f"layout: {exc}"
            ) from exc
    else:
        text_layout_report = {
            "version": 1,
            "status": "PASS",
            "visual_mode": resolved_visual_mode,
            "check": "reddit_page_text_layout_not_applicable",
            "full_screen_scene_contract_required": True,
            "publication_authorized": False,
        }
    text_layout_report["episode_plan_sha256"] = episode_plan["episode_plan_sha256"]
    text_layout_report["daily_plan_sha256"] = episode_plan["daily_plan_sha256"]
    _atomic_json(workdir / "text-layout-report.json", text_layout_report)
    runtime_estimate_report = _validate_estimated_runtime(script, daily_plan)
    runtime_estimate_report["episode_plan_sha256"] = episode_plan["episode_plan_sha256"]
    runtime_estimate_report["daily_plan_sha256"] = episode_plan["daily_plan_sha256"]
    _atomic_json(workdir / "runtime-estimate-report.json", runtime_estimate_report)
    # Packaging may select among the three producer angles, but it must not
    # silently rewrite them after the deterministic playoff has passed.
    winner_packaging_options = winner.get("packaging_options")
    if not isinstance(winner_packaging_options, list) or len(winner_packaging_options) != 3:
        raise EpisodeFactoryError("playoff winner is missing the three locked packaging options")
    if (
        playoff["winner"].get("packaging_options_sha256")
        != canonical_hash(winner_packaging_options)
    ):
        raise EpisodeFactoryError("winning packaging options do not match the topic playoff hash")
    packaging_playoff = copy.deepcopy(playoff)
    packaging_playoff["winner_packaging_options"] = copy.deepcopy(winner_packaging_options)
    packaging = generate_packaging(
        script,
        packaging_playoff,
        provider=None,
        model=OPENAI_MODEL,
    )
    packaging["daily_plan_sha256"] = episode_plan["daily_plan_sha256"]
    selected_option = packaging["packaging_options"][packaging["selected_option_index"]]
    packaging["youtube_title"] = selected_option["youtube_title"]
    packaging["thumbnail_text"] = selected_option["thumbnail_text"]
    packaging["first_screen_promise"] = selected_option["first_screen_promise"]
    if validate_packaging(packaging, script, packaging_playoff):
        raise EpisodeFactoryError("packaging changed after provider validation")

    planned_chunks = build_tts_chunks(
        script,
        voice_id=NARRATOR_VOICE_ID,
        comment_voice_id=COMMENT_VOICE_ID,
        narration_profile_id=narration_profile["profile_id"],
        model_id=TTS_MODEL_ID,
        pronunciation_dictionary_id=pronunciation_dictionary_id,
        pronunciation_dictionary_sha256=pronunciation_dictionary["sha256"],
    )
    if len(planned_chunks) > ai33_cap:
        raise EpisodeFactoryError(
            f"AI33 requires {len(planned_chunks)} task submissions but cap is {ai33_cap}"
        )

    script, scene_assets = generate_episode_images(
        script,
        workdir / "scene-images",
        max_images=images.cap,
        generator=images,
        model=DEFAULT_IMAGE_MODEL,
        artifact_root=workdir,
        provider_attempts=images.calls,
        checkpoint_path=workdir / "scene-image-checkpoint.json",
        visual_mode=resolved_visual_mode,
    )
    _atomic_json(workdir / "episode-script.json", script)
    _atomic_json(workdir / "youtube-metadata.json", packaging)
    _atomic_json(workdir / "scene-images-manifest.json", {
        "version": 2,
        "status": "PASS",
        "episode_plan_sha256": episode_plan["episode_plan_sha256"],
        "daily_plan_sha256": episode_plan["daily_plan_sha256"],
        "visual_mode": resolved_visual_mode,
        "narration_profile_id": narration_profile["profile_id"],
        "narration_profile_sha256": narration_profile["profile_sha256"],
        "narration_boundary_contract_sha256": narration_boundary_contract[
            "narration_boundary_contract_sha256"
        ],
        "assets": scene_assets,
        "publication_authorized": False,
    })

    if not scene_assets:
        raise EpisodeFactoryError("thumbnail requires at least one verified scene image")
    thumbnail_source = workdir / str(scene_assets[0]["local_path"])
    if not thumbnail_source.is_file():
        raise EpisodeFactoryError("thumbnail scene source is missing")
    thumbnail_base = workdir / "thumbnail-base.png"
    shutil.copyfile(thumbnail_source, thumbnail_base)
    thumbnail_path = overlay_thumbnail_text(
        thumbnail_base,
        workdir / "youtube-thumbnail.png",
        str(packaging["thumbnail_text"]),
    )
    thumbnail_report = write_thumbnail_report(
        workdir / "thumbnail-manifest.json",
        thumbnail_path,
        mode="scene-derivative-plus-local-overlay",
        provider_called=False,
    )
    thumbnail_report["source_scene_path"] = thumbnail_source.relative_to(workdir).as_posix()
    thumbnail_report["source_scene_sha256"] = _sha256_file(thumbnail_source)
    thumbnail_report["episode_plan_sha256"] = episode_plan["episode_plan_sha256"]
    thumbnail_report["daily_plan_sha256"] = episode_plan["daily_plan_sha256"]
    thumbnail_report["publication_authorized"] = False
    thumbnail_report["output"] = "youtube-thumbnail.png"
    _atomic_json(workdir / "thumbnail-manifest.json", thumbnail_report)

    from translator_tts import post_tts_task
    ai33 = CallBudget(
        post_tts_task,
        cap=ai33_cap,
        label="ai33",
        journal_path=provider_journal_dir / "ai33.json",
        allow_completed_resume=is_resume,
    )
    tts_state = run_compilation_tts(
        script,
        output_dir=workdir / "tts",
        artifact_root=workdir,
        api_key=api_key,
        voice_id=NARRATOR_VOICE_ID,
        comment_voice_id=COMMENT_VOICE_ID,
        narration_profile_id=narration_profile["profile_id"],
        model_id=TTS_MODEL_ID,
        pronunciation_dictionary_id=pronunciation_dictionary_id,
        pronunciation_dictionary_sha256=pronunciation_dictionary["sha256"],
        post_task=ai33,
    )
    pause_map_path = workdir / "tts" / "narration-pause-map.json"
    try:
        pause_map = build_pause_map(tts_state, output_path=pause_map_path)
        audio_mix_report = mix_compilation_audio(
            tts_state,
            artifact_root=workdir,
            pause_map=pause_map,
            pause_map_path=pause_map_path,
            output_path=workdir / "tts" / "compilation_voice_mix.wav",
            report_path=workdir / "tts" / "audio-mix-report.json",
        )
    except CompilationAudioMixError as exc:
        raise EpisodeFactoryError(f"voice-only audio mix blocked: {exc}") from exc
    audio_path = workdir / str(audio_mix_report["output_path"])

    brand_assets = {
        "brand_sting": (BRAND_STING_ASSET, 1.5, "after_cold_open"),
        "brand_cta": (BRAND_CTA_ASSET, 3.0, "first_story_midpoint"),
        "brand_outro": (BRAND_OUTRO_ASSET, 6.0, "timeline_end"),
    }
    for field, (source_asset, duration_sec, placement) in brand_assets.items():
        source = source_asset.resolve()
        if not source.is_file():
            raise EpisodeFactoryError(
                f"verified {field} is missing: {source_asset}",
            )
        artifact_path = workdir / "branding" / source_asset.name
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, artifact_path)
        script[field] = {
            "local_path": artifact_path.relative_to(workdir).as_posix(),
            "sha256": _sha256_file(artifact_path),
            "duration_sec": duration_sec,
            "placement": placement,
            "audio_policy": "discard",
        }
    _atomic_json(workdir / "episode-script.json", script)

    background_path: Path | None = None
    if resolved_visual_mode == DEFAULT_VISUAL_MODE:
        background_source = BACKGROUND_ASSET.resolve()
        if not background_source.is_file():
            raise EpisodeFactoryError(
                f"verified background asset is missing: {BACKGROUND_ASSET}",
            )
        background_path = workdir / "assets" / BACKGROUND_ASSET.name
        background_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(background_source, background_path)
    storyboard = build_storyboard(
        script,
        workdir,
        background_video=(
            background_path.relative_to(workdir)
            if background_path is not None
            else None
        ),
        tts_state=tts_state,
        visual_mode=resolved_visual_mode,
        pause_map=pause_map,
        audio_mix_report=audio_mix_report,
    )
    storyboard_path = workdir / "storyboard.json"
    _atomic_json(storyboard_path, storyboard)
    shot_plan_path: Path | None = None
    caption_track_path: Path | None = None
    if resolved_visual_mode == CINEMATIC_STORY_MODE:
        shot_plan_path = workdir / "shot-plan.json"
        caption_track_path = workdir / "caption-track.json"
        _atomic_json(shot_plan_path, storyboard["shot_plan"])
        _atomic_json(caption_track_path, storyboard["caption_track"])

    video_path = workdir / "final-output.mp4"
    render_report = render_compilation(
        storyboard,
        workdir,
        video_path,
        audio=audio_path,
    )
    render_report["output"] = "final-output.mp4"
    if render_report.get("caption_srt"):
        render_report["caption_srt"] = Path(
            render_report["caption_srt"],
        ).resolve().relative_to(workdir.resolve()).as_posix()
    _atomic_json(workdir / "render-report.json", render_report)

    artifact_paths = {
        "script_sha256": workdir / "episode-script.json",
        "audio_sha256": audio_path,
        "metadata_sha256": workdir / "youtube-metadata.json",
        "storyboard_sha256": storyboard_path,
        "video_sha256": video_path,
        "thumbnail_sha256": thumbnail_path,
    }
    artifact_hashes = {field: _sha256_file(path) for field, path in artifact_paths.items()}
    media_qa = run_qa(
        script,
        packaging,
        tts_state,
        storyboard,
        render_report,
        artifact_root=workdir,
        video_path=video_path,
        thumbnail_path=thumbnail_path,
        creative_manifest=storyboard.get("creative_manifest"),
        expected_voice_id=NARRATOR_VOICE_ID,
        expected_comment_voice_id=COMMENT_VOICE_ID,
        episode_plan=episode_plan,
        topic_playoff=playoff,
        artifact_hashes=artifact_hashes,
        audio_path=audio_path,
        pause_map=pause_map,
        audio_mix_report=audio_mix_report,
        target_duration_minutes=daily_plan["source_plan"]["target_duration_minutes"],
    )
    _atomic_json(workdir / "media-qa.json", media_qa)
    if media_qa.get("status") != "PASS":
        raise EpisodeFactoryError("media QA blocked: " + "; ".join(media_qa.get("failures") or []))

    creative_review = build_template(
        video_path,
        thumbnail_path,
        visual_mode=resolved_visual_mode,
    )
    creative_review["episode_plan_sha256"] = episode_plan["episode_plan_sha256"]
    creative_review["daily_plan_sha256"] = episode_plan["daily_plan_sha256"]
    creative_review["visual_mode"] = resolved_visual_mode
    creative_review["narration_profile_id"] = narration_profile["profile_id"]
    creative_review["narration_profile_sha256"] = narration_profile[
        "profile_sha256"
    ]
    creative_review["narration_boundary_contract_sha256"] = (
        narration_boundary_contract["narration_boundary_contract_sha256"]
    )
    creative_review["audio_sha256"] = audio_mix_report["output_sha256"]
    creative_review["pause_map_sha256"] = pause_map["pause_map_sha256"]
    creative_review["audio_mix_report_sha256"] = audio_mix_report[
        "audio_mix_report_sha256"
    ]
    creative_review["shot_plan_sha256"] = storyboard.get("shot_plan_sha256")
    creative_review["caption_track_sha256"] = storyboard.get(
        "caption_track_sha256"
    )
    _atomic_json(workdir / "creative-review.json", creative_review)

    evidence_paths = {
        "daily_plan": workdir / "daily-plan.json",
        "source_queue": workdir / "source-queue.json",
        "source_review": workdir / "source-review.json",
        "candidate_pool": workdir / "candidate-pool.json",
        "source_stage": workdir / "source-stage.json",
        "spend_lease": workdir / "spend-lease.json",
        "paid_preflight": workdir / "paid-preflight.json",
        "producer_review": workdir / "producer-review.json",
        "critic_review": workdir / "critic-review.json",
        "topic_playoff_input": workdir / "topic-playoff-input.json",
        "topic_playoff": workdir / "topic-playoff.json",
        "episode_greenlight": workdir / "episode-greenlight.json",
        "episode_plan": workdir / "episode-plan.json",
        "text_layout_report": workdir / "text-layout-report.json",
        "runtime_estimate_report": workdir / "runtime-estimate-report.json",
        "scene_images_manifest": workdir / "scene-images-manifest.json",
        "scene_image_checkpoint": workdir / "scene-image-checkpoint.json",
        "thumbnail_manifest": workdir / "thumbnail-manifest.json",
        "tts_state": workdir / "tts" / "compilation_tts_state.json",
        "pause_map": pause_map_path,
        "audio_mix_report": workdir / "tts" / "audio-mix-report.json",
        "render_report": workdir / "render-report.json",
        "media_qa": workdir / "media-qa.json",
        "creative_review": workdir / "creative-review.json",
        "openai_attempts": provider_journal_dir / "openai.json",
        "image_attempts": provider_journal_dir / "image.json",
        "ai33_attempts": provider_journal_dir / "ai33.json",
    }
    if resolved_visual_mode == CINEMATIC_STORY_MODE:
        evidence_paths.update({
            "shot_plan": shot_plan_path,
            "caption_track": caption_track_path,
            "caption_srt": video_path.with_suffix(".srt"),
        })
    missing_evidence = [name for name, path in evidence_paths.items() if not path.is_file()]
    if missing_evidence:
        raise EpisodeFactoryError(
            "release evidence is incomplete: " + ", ".join(sorted(missing_evidence))
        )
    evidence_hashes = {
        name: _sha256_file(path) for name, path in evidence_paths.items()
    }

    release_manifest: dict[str, Any] = {
        "version": FACTORY_VERSION,
        "status": "READY_FOR_HUMAN_REVIEW",
        "publication_authorized": False,
        "performance_outcome_guaranteed": False,
        "episode_key": daily_plan["episode_key"],
        "pilot_id": daily_plan["pilot_id"],
        "format": daily_plan["format"],
        "pillar": daily_plan["pillar"],
        "visual_mode": resolved_visual_mode,
        "narration_profile_id": narration_profile["profile_id"],
        "narration_profile_sha256": narration_profile["profile_sha256"],
        "narration_boundary_contract_sha256": narration_boundary_contract[
            "narration_boundary_contract_sha256"
        ],
        "winner_candidate_id": winner_id,
        "episode_plan_sha256": episode_plan["episode_plan_sha256"],
        "daily_plan_sha256": episode_plan["daily_plan_sha256"],
        "topic_playoff_sha256": playoff["playoff_sha256"],
        "topic_playoff_input_sha256": playoff["playoff_input_sha256"],
        "winner_candidate_contract_sha256": playoff["winner"]["candidate_contract_sha256"],
        "winner_packaging_options_sha256": playoff["winner"]["packaging_options_sha256"],
        "winner_creative_plan_sha256": playoff["winner"]["creative_plan_sha256"],
        "source_stage_sha256": source_stage["source_stage_sha256"],
        "artifact_sha256": artifact_hashes,
        "evidence_sha256": evidence_hashes,
        "pause_map_sha256": pause_map["pause_map_sha256"],
        "audio_mix_report_sha256": audio_mix_report[
            "audio_mix_report_sha256"
        ],
        "shot_plan_sha256": storyboard.get("shot_plan_sha256"),
        "caption_track_sha256": storyboard.get("caption_track_sha256"),
        "caption_srt_sha256": render_report.get("caption_srt_sha256"),
        "timing_contract_sha256": tts_state.get("timing_contract_sha256"),
        "audio_sha256": audio_mix_report["output_sha256"],
        "media_qa_status": "PASS",
        "creative_review_status": "BLOCKED_PENDING_HUMAN",
        "provider_usage": {
            "openai_calls": len(openai.calls),
            "openai_call_cap": openai.cap,
            "openai_token_cap": openai.token_cap,
            "openai_usage": copy.deepcopy(
                openai.journal.get("usage_totals") or {}
            ),
            "image_calls": len(images.calls),
            "image_call_cap": images.cap,
            "ai33_task_submissions": len(ai33.calls),
            "ai33_task_cap": ai33.cap,
        },
        "next_gate": "human creative review; no uploader is present in this workflow",
    }
    release_manifest["release_candidate_manifest_sha256"] = _self_hash(
        release_manifest, "release_candidate_manifest_sha256",
    )
    _atomic_json(workdir / "release-candidate-manifest.json", release_manifest)
    result = {
        "version": FACTORY_VERSION,
        "status": "READY_FOR_HUMAN_REVIEW",
        "publication_authorized": False,
        "performance_outcome_guaranteed": False,
        "episode_key": daily_plan["episode_key"],
        "visual_mode": resolved_visual_mode,
        "narration_profile_id": narration_profile["profile_id"],
        "narration_profile_sha256": narration_profile["profile_sha256"],
        "narration_boundary_contract_sha256": narration_boundary_contract[
            "narration_boundary_contract_sha256"
        ],
        "episode_plan_sha256": episode_plan["episode_plan_sha256"],
        "release_candidate_manifest_sha256": release_manifest["release_candidate_manifest_sha256"],
        "pause_map_sha256": pause_map["pause_map_sha256"],
        "audio_mix_report_sha256": audio_mix_report[
            "audio_mix_report_sha256"
        ],
        "shot_plan_sha256": storyboard.get("shot_plan_sha256"),
        "caption_track_sha256": storyboard.get("caption_track_sha256"),
        "caption_srt_sha256": render_report.get("caption_srt_sha256"),
        "timing_contract_sha256": tts_state.get("timing_contract_sha256"),
        "audio_sha256": audio_mix_report["output_sha256"],
        "artifact_directory": ".",
    }
    _atomic_json(workdir / "factory-result.json", result)
    return result


def run_preflight(
    *,
    daily_plan: dict[str, Any],
    workdir: Path,
    channels_path: Path,
    visual_mode: str = DEFAULT_VISUAL_MODE,
) -> dict[str, Any]:
    validate_daily_plan(daily_plan, channels_path)
    try:
        resolved_visual_mode = resolve_visual_mode(visual_mode)
    except ValueError as exc:
        raise EpisodeFactoryError(str(exc)) from exc
    if (
        resolved_visual_mode == CINEMATIC_STORY_MODE
        and str(daily_plan.get("format") or "").upper() == "THREAD"
    ):
        raise EpisodeFactoryError(
            "cinematic_story_v1 supports SAGA/BUNDLE; THREAD uses the approved "
            "editorial_motion_v1 response-vignette contract",
        )
    if resolved_visual_mode == EDITORIAL_MOTION_MODE:
        style_profile = str(
            daily_plan.get("editorial_motion_style_profile") or "",
        ).strip()
        if style_profile != FORMAT_VISUAL_SYSTEM_V3_STYLE_PROFILE:
            raise EpisodeFactoryError(
                "daily plan editorial_motion_style_profile must use the "
                "approved v3 format system",
            )

    pillar_id = str(daily_plan.get("pillar") or "").strip()
    try:
        narration_profile = resolve_narration_profile(
            NARRATION_PROFILE_IDS_BY_PILLAR.get(pillar_id, ""),
            pillar_id=pillar_id,
        )
    except NarrationProfileError as exc:
        raise EpisodeFactoryError(str(exc)) from exc

    ffmpeg = shutil.which("ffmpeg")
    ffprobe = shutil.which("ffprobe")
    if not ffmpeg or not ffprobe:
        raise EpisodeFactoryError(
            "ffmpeg and ffprobe are required before any live source or provider call",
        )
    font = next((path for path in FONT_CANDIDATES if path.is_file()), None)
    if font is None:
        raise EpisodeFactoryError(
            "a Cyrillic-capable production font is required before provider calls",
        )

    background_sha256: str | None = None
    background_manifest_sha256: str | None = None
    duration: float | None = None
    if resolved_visual_mode == DEFAULT_VISUAL_MODE:
        background = BACKGROUND_ASSET.resolve()
        if not background.is_file():
            raise EpisodeFactoryError(
                f"background asset is missing: {BACKGROUND_ASSET}",
            )
        background_manifest = _read_object(BACKGROUND_MANIFEST)
        background_sha256 = _sha256_file(background)
        background_manifest_sha256 = _sha256_file(BACKGROUND_MANIFEST)
        if background_manifest.get("asset") != str(BACKGROUND_ASSET):
            raise EpisodeFactoryError(
                "background manifest does not name the canonical acc1 asset",
            )
        if background_manifest.get("sha256") != background_sha256:
            raise EpisodeFactoryError(
                "background asset checksum does not match its approved manifest",
            )
        if (
            background_manifest.get("audio_policy") != "discard"
            or background_manifest.get("loop") is not True
        ):
            raise EpisodeFactoryError(
                "background manifest must require looping video with discarded audio",
            )
        try:
            probe_result = subprocess.run(
                [
                    ffprobe, "-v", "error", "-select_streams", "v:0",
                    "-show_entries",
                    "stream=codec_name,width,height:format=duration",
                    "-of", "json", str(background),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            probe = json.loads(probe_result.stdout)
            stream = (probe.get("streams") or [])[0]
            duration = float((probe.get("format") or {}).get("duration") or 0)
        except (
            OSError,
            subprocess.CalledProcessError,
            ValueError,
            json.JSONDecodeError,
            IndexError,
        ) as exc:
            raise EpisodeFactoryError(
                "approved background asset is not decodable by ffprobe",
            ) from exc
        if [stream.get("width"), stream.get("height")] != background_manifest.get(
            "resolution",
        ):
            raise EpisodeFactoryError(
                "background video resolution does not match its manifest",
            )
        if stream.get("codec_name") != background_manifest.get("video_codec"):
            raise EpisodeFactoryError(
                "background video codec does not match its manifest",
            )
        if abs(duration - float(background_manifest.get("duration_sec") or 0)) > 0.25:
            raise EpisodeFactoryError(
                "background video duration does not match its manifest",
            )

    report = {
        "version": FACTORY_VERSION,
        "status": "PREFLIGHT_PASS",
        "visual_mode": resolved_visual_mode,
        "narration_profile_id": narration_profile["profile_id"],
        "narration_profile_sha256": narration_profile["profile_sha256"],
        "would_call_reddit": False,
        "would_call_image_provider": False,
        "would_call_ai33": False,
        "would_upload_youtube": False,
        "daily_plan_sha256": canonical_hash(daily_plan),
        "background_required": resolved_visual_mode == DEFAULT_VISUAL_MODE,
        "background_sha256": background_sha256,
        "background_manifest_sha256": background_manifest_sha256,
        "background_duration_sec": duration,
        "ffmpeg_preflight": True,
        "font_preflight": True,
        "publication_authorized": False,
    }
    _atomic_json(Path(workdir) / "factory-preflight.json", report)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", required=True)
    parser.add_argument("--workdir", required=True)
    parser.add_argument("--channels", default="channels.json")
    parser.add_argument(
        "--stage",
        choices=(
            "preflight",
            "source",
            "source-receipt",
            "paid-preflight",
            "produce",
        ),
        required=True,
    )
    parser.add_argument("--confirm-reddit-read", default="false")
    parser.add_argument("--reddit-request-cap", type=int, default=24)
    parser.add_argument("--reserved-source-exclusions")
    parser.add_argument("--repository", default=os.getenv("GITHUB_REPOSITORY", ""))
    parser.add_argument("--workflow-path", default=SPEND_LOCK_WORKFLOW_PATH)
    parser.add_argument("--run-id", type=int, default=0)
    parser.add_argument("--run-attempt", type=int, default=0)
    parser.add_argument("--head-sha", default=os.getenv("GITHUB_SHA", ""))
    parser.add_argument("--confirm-openai-spend", default="false")
    parser.add_argument("--openai-call-cap", type=int, default=96)
    parser.add_argument("--openai-token-cap", type=int, default=500_000)
    parser.add_argument("--confirm-image-spend", default="false")
    parser.add_argument("--image-call-cap", type=int, default=16)
    parser.add_argument("--confirm-ai33-spend", default="false")
    parser.add_argument("--ai33-call-cap", type=int, default=24)
    parser.add_argument("--spend-lease")
    parser.add_argument("--resume-reviewed-run-id", type=int)
    parser.add_argument("--resume-lease")
    parser.add_argument(
        "--visual-mode",
        choices=tuple(sorted(VISUAL_MODES)),
        default=DEFAULT_VISUAL_MODE,
        help="Explicit renderer contract; never selected by fallback.",
    )
    args = parser.parse_args(argv)
    plan = _read_object(Path(args.plan))
    workdir = Path(args.workdir)
    channels = Path(args.channels)
    if args.stage == "preflight":
        result = run_preflight(
            daily_plan=plan,
            workdir=workdir,
            channels_path=channels,
            visual_mode=args.visual_mode,
        )
    elif args.stage == "source":
        result = run_source_stage(
            daily_plan=plan,
            workdir=workdir,
            channels_path=channels,
            confirm_reddit_read=args.confirm_reddit_read,
            reddit_request_cap=args.reddit_request_cap,
            reserved_source_exclusions_path=(
                Path(args.reserved_source_exclusions)
                if args.reserved_source_exclusions
                else None
            ),
        )
    elif args.stage == "source-receipt":
        result = run_source_only_receipt(
            daily_plan=plan,
            workdir=workdir,
            channels_path=channels,
            reddit_request_cap=args.reddit_request_cap,
            repository=args.repository,
            workflow_path=args.workflow_path,
            run_id=args.run_id,
            run_attempt=args.run_attempt,
            head_sha=args.head_sha,
        )
    elif args.stage == "paid-preflight":
        result = run_paid_preflight(
            daily_plan=plan,
            workdir=workdir,
            channels_path=channels,
            confirm_openai_spend=args.confirm_openai_spend,
            openai_call_cap=args.openai_call_cap,
            openai_token_cap=args.openai_token_cap,
            confirm_image_spend=args.confirm_image_spend,
            image_call_cap=args.image_call_cap,
            confirm_ai33_spend=args.confirm_ai33_spend,
            ai33_call_cap=args.ai33_call_cap,
            visual_mode=args.visual_mode,
        )
    else:
        result = run_produce_stage(
            daily_plan=plan,
            workdir=workdir,
            channels_path=channels,
            confirm_openai_spend=args.confirm_openai_spend,
            openai_call_cap=args.openai_call_cap,
            openai_token_cap=args.openai_token_cap,
            confirm_image_spend=args.confirm_image_spend,
            image_call_cap=args.image_call_cap,
            confirm_ai33_spend=args.confirm_ai33_spend,
            ai33_call_cap=args.ai33_call_cap,
            reddit_request_cap=args.reddit_request_cap,
            spend_lease_path=Path(args.spend_lease) if args.spend_lease else None,
            resume_review_run_id=args.resume_reviewed_run_id,
            resume_lease_path=Path(args.resume_lease) if args.resume_lease else None,
            visual_mode=args.visual_mode,
        )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except EpisodeFactoryError as exc:
        print(json.dumps({"status": "BLOCKED", "error": str(exc)}, ensure_ascii=False))
        raise SystemExit(1)
