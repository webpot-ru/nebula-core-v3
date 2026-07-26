"""Idempotent, resumable AI33 narration for ordered Reddit compilations."""

from __future__ import annotations

import hashlib
import json
import os
import argparse
import difflib
import math
import time
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Callable

from acc1_narration_profiles import (
    NarrationProfileError,
    canonicalize_voice_settings_json,
    resolve_narration_boundary_contract,
    verify_narration_boundary_contract,
)
from compilation_narration import (
    build_compilation_segments,
    resolve_compilation_narration_profile,
)
from translator_tts import (
    Ai33Error,
    collect_transcript_words,
    collect_reported_model_ids,
    concat_audio_segments,
    estimate_transcript_words,
    find_binary,
    poll_for_audio,
    post_tts_task,
    probe_audio_duration,
    split_long_text_for_tts,
    write_audio_from_payload,
)


STATE_VERSION = 3
TIMING_CONTRACT_VERSION = 1
REQUIRED_MODEL_ID = "eleven_v3"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
DEFAULT_POLL_CONCURRENCY = 4
MAX_POLL_CONCURRENCY = 16
DEADLINE_EPOCH_ENV = "AI33_TTS_DEADLINE_EPOCH"


class CompilationTtsError(RuntimeError):
    """A fail-closed compilation TTS state or provider-contract error."""


def _retryable_poll_error(exc: Exception) -> bool:
    message = str(exc).casefold().replace(" ", "")
    return isinstance(exc, Ai33Error) and any(marker in message for marker in (
        "retryable\":true", "failed(429)", "temporarilybusy",
        "failed(500)", "failed(502)", "failed(503)",
        "failed(504)", "timedout", "timeout",
    ))


def _poll_with_retries(
    poll_task: Callable[..., dict[str, Any]], *, retries: int,
    sleeper: Callable[[float], None], poll_kwargs: dict[str, Any],
    deadline: float, monotonic: Callable[[], float],
) -> dict[str, Any]:
    for attempt in range(retries + 1):
        remaining = deadline - monotonic()
        if remaining <= 0:
            raise CompilationTtsError("shared AI33 TTS deadline expired while polling saved tasks")
        bounded_kwargs = dict(poll_kwargs)
        bounded_kwargs["timeout_seconds"] = max(1, math.ceil(remaining))
        try:
            payload = poll_task(**bounded_kwargs)
            if not isinstance(payload, dict):
                raise CompilationTtsError("AI33 polling returned a non-object payload")
            return payload
        except Exception as exc:
            if attempt >= retries or not _retryable_poll_error(exc):
                raise
            remaining = deadline - monotonic()
            if remaining <= 0:
                raise CompilationTtsError(
                    "shared AI33 TTS deadline expired after a retryable polling error"
                ) from exc
            sleeper(min(remaining, 30, 5 * (2 ** attempt)))
    raise CompilationTtsError("unreachable polling retry state")


def _resolve_shared_deadline(
    *,
    timeout_seconds: int,
    overall_timeout_seconds: int | None,
    overall_deadline_epoch: float | None,
    monotonic: Callable[[], float],
    wall_clock: Callable[[], float],
) -> float:
    """Resolve one invocation-wide deadline, optionally bound to workflow wall time."""
    env_value = str(os.environ.get(DEADLINE_EPOCH_ENV) or "").strip()
    if overall_deadline_epoch is None and env_value:
        try:
            overall_deadline_epoch = float(env_value)
        except ValueError as exc:
            raise CompilationTtsError(
                f"{DEADLINE_EPOCH_ENV} must be a Unix epoch timestamp"
            ) from exc

    if overall_deadline_epoch is not None:
        try:
            remaining = float(overall_deadline_epoch) - float(wall_clock())
        except (TypeError, ValueError) as exc:
            raise CompilationTtsError("overall_deadline_epoch must be numeric") from exc
    else:
        selected_timeout = (
            overall_timeout_seconds
            if overall_timeout_seconds is not None
            else timeout_seconds
        )
        try:
            remaining = float(selected_timeout)
        except (TypeError, ValueError) as exc:
            raise CompilationTtsError("overall AI33 TTS timeout must be numeric") from exc

    if not math.isfinite(remaining) or remaining <= 0:
        raise CompilationTtsError("shared AI33 TTS deadline must be in the future")
    return monotonic() + remaining


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _canonical_hash(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return _sha256_bytes(encoded)


def _canonical_text(value: object) -> str:
    return " ".join(str(value or "").split())


def _split_semantic_text(text: str, max_chars: int) -> list[str]:
    """Split one semantic unit without rewriting its sanitized narration."""

    remaining = str(text or "").strip()
    if not remaining:
        return []
    chunks: list[str] = []
    while len(remaining) > max_chars:
        window = remaining[:max_chars + 1]
        sentence_cuts = [
            match.start()
            for match in re.finditer(r"(?<=[.!?…])\s+", window)
            if 0 < match.start() <= max_chars
        ]
        cut = sentence_cuts[-1] if sentence_cuts else -1
        if cut <= 0:
            cut = max(
                window.rfind(" ", 0, max_chars + 1),
                window.rfind("\n", 0, max_chars + 1),
                window.rfind("\t", 0, max_chars + 1),
            )
        if cut <= 0:
            cut = max_chars
        chunk = remaining[:cut].rstrip()
        if not chunk:
            raise CompilationTtsError("semantic chunking produced an empty chunk")
        chunks.append(chunk)
        remaining = remaining[cut:].lstrip()
    if remaining:
        chunks.append(remaining)
    if _canonical_text(" ".join(chunks)) != _canonical_text(text):
        raise CompilationTtsError(
            "semantic chunks changed the sanitized narration text"
        )
    return chunks


def _probe_duration(path: Path) -> float:
    """Read actual media duration or fail before a COMPLETE state is written."""
    try:
        duration = probe_audio_duration(find_binary("ffprobe"), path)
    except Ai33Error as exc:
        raise CompilationTtsError(f"could not verify audio duration for {path.name}") from exc
    if duration <= 0:
        raise CompilationTtsError(f"audio duration for {path.name} must be positive")
    return round(duration, 6)


def _token_identity(value: Any) -> str:
    return re.sub(
        r"[^\w]+", "", str(value or "").casefold().replace("ё", "е"),
        flags=re.UNICODE,
    )


def _validated_provider_words(
    text: str, payload: dict[str, Any], duration: float, *, api_key: str | None = None,
) -> list[dict[str, Any]]:
    """Bind provider transcription back to every exact script token."""
    expected = text.split()
    raw_words = collect_transcript_words(payload, api_key=api_key)
    if not raw_words:
        return []
    matcher = difflib.SequenceMatcher(
        None,
        [_token_identity(item) for item in expected],
        [_token_identity(item.get("word")) for item in raw_words],
        autojunk=False,
    )
    if matcher.ratio() < 0.9:
        return []
    mapping: list[tuple[int, int] | None] = [None] * len(expected)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            for offset in range(i2 - i1):
                mapping[i1 + offset] = (j1 + offset, j1 + offset + 1)
        elif tag == "replace" and i2 > i1 and j2 > j1:
            for offset in range(i2 - i1):
                start = j1 + ((j2 - j1) * offset) // (i2 - i1)
                end = j1 + ((j2 - j1) * (offset + 1)) // (i2 - i1)
                mapping[i1 + offset] = (min(start, j2 - 1), max(start + 1, end))
        elif tag == "delete":
            mapping[i1:i2] = [(j1, j1)] * (i2 - i1)
    normalized: list[dict[str, Any]] = []
    previous_start = 0.0
    for index, expected_word in enumerate(expected):
        span = mapping[index]
        if span is None:
            return []
        start_index, end_index = span
        try:
            if start_index == end_index:
                start = end = previous_start
                if start_index < len(raw_words):
                    start = end = max(start, float(raw_words[start_index]["start"]))
            else:
                start = float(raw_words[start_index]["start"])
                end = float(raw_words[end_index - 1]["end"])
        except (KeyError, IndexError, TypeError, ValueError):
            return []
        if start < 0 or end < start or start + 0.001 < previous_start or end > duration + 0.25:
            return []
        normalized.append({
            "word": expected_word,
            "start": round(min(start, duration), 3),
            "end": round(min(end, duration), 3),
            "timing_source": "ai33",
        })
        previous_start = start
    return normalized


def _build_chunk_timing(
    text: str, payload: dict[str, Any], duration: float, *, api_key: str | None = None,
) -> tuple[str, list[dict[str, Any]]]:
    words = _validated_provider_words(text, payload, duration, api_key=api_key)
    if words:
        return "ai33", words
    estimated = estimate_transcript_words(text, duration)
    if not estimated or len(estimated) != len(text.split()):
        raise CompilationTtsError("could not build complete word timing from verified audio")
    return "estimated_from_audio_duration", [
        {
            "word": str(word["word"]),
            "start": round(float(word["start"]), 3),
            "end": round(float(word["end"]), 3),
            "timing_source": "estimated_from_audio_duration",
        }
        for word in estimated
    ]


def _chunk_timing_contract(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "chunk_id": item.get("chunk_id"),
        "logical_segment_id": item.get("logical_segment_id"),
        "text_sha256": item.get("text_sha256"),
        "audio_sha256": item.get("audio_sha256"),
        "audio_duration_sec": item.get("audio_duration_sec"),
        "timing_source": item.get("timing_source"),
        "word_timings_sha256": item.get("word_timings_sha256"),
    }


def _validate_completed_chunk_timing(item: dict[str, Any]) -> None:
    try:
        duration = float(item.get("audio_duration_sec") or 0)
    except (TypeError, ValueError) as exc:
        raise CompilationTtsError(f"{item.get('chunk_id')} has invalid audio duration") from exc
    words = item.get("word_timings")
    if duration <= 0 or not isinstance(words, list) or len(words) != len(str(item.get("text") or "").split()):
        raise CompilationTtsError(f"{item.get('chunk_id')} has incomplete timing contract")
    if item.get("timing_source") not in {"ai33", "estimated_from_audio_duration"}:
        raise CompilationTtsError(f"{item.get('chunk_id')} has unknown timing source")
    expected_hash = _canonical_hash(words)
    if item.get("word_timings_sha256") != expected_hash:
        raise CompilationTtsError(f"{item.get('chunk_id')} word timing checksum mismatch")
    expected_tokens = str(item.get("text") or "").split()
    previous_start = 0.0
    for expected_word, word in zip(expected_tokens, words):
        try:
            start = float(word["start"])
            end = float(word["end"])
        except (KeyError, TypeError, ValueError) as exc:
            raise CompilationTtsError(f"{item.get('chunk_id')} has invalid word timing") from exc
        if (
            str(word.get("word") or "") != expected_word
            or start < 0
            or end < start
            or start + 0.001 < previous_start
            or end > duration + 0.001
        ):
            raise CompilationTtsError(f"{item.get('chunk_id')} word timings do not bind to exact text/audio")
        previous_start = start


def _state_timing_contract(state: dict[str, Any]) -> dict[str, Any]:
    return {
        "version": TIMING_CONTRACT_VERSION,
        "narration_plan_sha256": state.get("narration_plan_sha256"),
        "final_audio_sha256": state.get("final_audio_sha256"),
        "final_audio_duration_sec": state.get("final_audio_duration_sec"),
        "raw_chunk_duration_sec": state.get("raw_chunk_duration_sec"),
        "timeline_scale": state.get("timeline_scale"),
        "chunks": [_chunk_timing_contract(item) for item in state.get("chunks") or []],
    }


def _atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def _plan_bindings(compilation: dict[str, Any]) -> dict[str, str]:
    bindings: dict[str, str] = {}
    for field in ("episode_plan_sha256", "daily_plan_sha256"):
        digest = str(compilation.get(field) or "").strip().lower()
        if not SHA256_RE.fullmatch(digest):
            raise CompilationTtsError(f"compilation {field} must be a SHA-256 digest")
        bindings[field] = digest
    if compilation.get("publication_authorized") is not False:
        raise CompilationTtsError("compilation publication_authorized must remain false")
    return bindings


def _resolve_declared_boundary_contract(
    compilation: dict[str, Any],
    profile: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Verify an opt-in future-episode delivery contract without touching legacy runs."""

    declared = compilation.get("narration_boundary_contract")
    if declared is None:
        return None
    if profile is None:
        raise CompilationTtsError(
            "narration boundary contract requires a canonical narration profile"
        )
    if not isinstance(declared, dict) or not verify_narration_boundary_contract(
        declared,
    ):
        raise CompilationTtsError(
            "narration boundary contract checksum is invalid"
        )
    stories = compilation.get("stories")
    if not isinstance(stories, list) or not stories:
        raise CompilationTtsError(
            "narration boundary contract requires a non-empty stories list"
        )
    try:
        expected = resolve_narration_boundary_contract(
            profile,
            episode_format=compilation.get("episode_format"),
            source_count=len(stories),
        )
    except NarrationProfileError as exc:
        raise CompilationTtsError(str(exc)) from exc
    if declared != expected:
        raise CompilationTtsError(
            "narration boundary contract does not match format, source count, or profile"
        )
    return expected


def _validate_boundary_segments(
    logical_segments: list[dict[str, Any]],
    contract: dict[str, Any],
) -> None:
    """Fail before provider submission when spoken boundaries drift from format."""

    format_id = str(contract["episode_format"])
    stories = [
        item for item in logical_segments if item.get("kind") == "story"
    ]
    transitions = [
        item for item in logical_segments if item.get("kind") == "transition"
    ]
    if len(stories) != int(contract["source_count"]):
        raise CompilationTtsError(
            "narration boundary contract source count does not match logical stories"
        )
    if len(transitions) != int(contract["spoken_transition_count"]):
        raise CompilationTtsError(
            f"{format_id} spoken transition count violates the narration boundary contract"
        )
    if any(item.get("voice_role") != "narrator" for item in transitions):
        raise CompilationTtsError(
            "spoken story transitions must use the narrator voice"
        )
    if format_id == "THREAD":
        roles = [str(item.get("voice_role") or "") for item in stories]
        if not roles or roles[0] != "narrator" or any(
            role != "comment" for role in roles[1:]
        ):
            raise CompilationTtsError(
                "THREAD requires narrator prompt followed by distinct comment-role responses"
            )
    elif any(item.get("voice_role") != "narrator" for item in stories):
        raise CompilationTtsError(
            f"{format_id} story narration must use the narrator voice"
        )


def build_tts_chunks(
    compilation: dict[str, Any],
    *,
    voice_id: str,
    comment_voice_id: str | None = None,
    narration_profile_id: str | None = None,
    model_id: str = REQUIRED_MODEL_ID,
    max_chars: int = 4_500,
    speed: float = 1.0,
    voice_settings_json: str | None = None,
    with_transcript: bool = True,
    context_chaining: bool = False,
    pronunciation_dictionary_id: int | None = None,
    pronunciation_dictionary_sha256: str | None = None,
) -> list[dict[str, Any]]:
    """Build stable role-aware chunks bound to one immutable episode plan."""
    if model_id != REQUIRED_MODEL_ID:
        raise CompilationTtsError(f"required model is {REQUIRED_MODEL_ID!r}, got {model_id!r}")
    if max_chars < 500:
        raise CompilationTtsError("max_chars must be at least 500")
    if not str(voice_id or "").strip():
        raise CompilationTtsError("voice_id is required")
    if (pronunciation_dictionary_id is None) != (pronunciation_dictionary_sha256 is None):
        raise CompilationTtsError("pronunciation dictionary id and SHA-256 must be supplied together")
    if pronunciation_dictionary_id is not None:
        if isinstance(pronunciation_dictionary_id, bool) or pronunciation_dictionary_id <= 0:
            raise CompilationTtsError("pronunciation_dictionary_id must be a positive integer")
        if not SHA256_RE.fullmatch(str(pronunciation_dictionary_sha256 or "").lower()):
            raise CompilationTtsError("pronunciation_dictionary_sha256 must be a SHA-256 digest")

    bindings = _plan_bindings(compilation)
    try:
        profile = resolve_compilation_narration_profile(
            compilation, narration_profile_id,
        )
    except Exception as exc:
        if isinstance(exc, CompilationTtsError):
            raise
        raise CompilationTtsError(str(exc)) from exc

    effective_speed = speed
    effective_voice_settings_json = voice_settings_json
    effective_max_chars = max_chars
    if profile is not None:
        profile_speed = float(profile["speed"])
        if speed != 1.0 and not math.isclose(
            float(speed), profile_speed, rel_tol=0.0, abs_tol=1e-9,
        ):
            raise CompilationTtsError(
                "speed override conflicts with the canonical narration profile"
            )
        if voice_settings_json is not None:
            try:
                supplied_settings = canonicalize_voice_settings_json(
                    voice_settings_json,
                )
            except NarrationProfileError as exc:
                raise CompilationTtsError(str(exc)) from exc
            if supplied_settings != profile["voice_settings_json"]:
                raise CompilationTtsError(
                    "voice_settings_json conflicts with the canonical narration profile"
                )
        effective_speed = profile_speed
        effective_voice_settings_json = profile["voice_settings_json"]
        effective_max_chars = min(
            max_chars, int(profile["semantic_chunk_policy"]["max_chars"]),
        )

    boundary_contract = _resolve_declared_boundary_contract(
        compilation,
        profile,
    )
    logical_segments = build_compilation_segments(
        compilation,
        profile["profile_id"] if profile is not None else None,
    )
    if boundary_contract is not None:
        _validate_boundary_segments(logical_segments, boundary_contract)
    needs_comment_voice = any(
        item.get("voice_role") == "comment" for item in logical_segments
    )
    resolved_comment_voice = str(comment_voice_id or "").strip()
    if needs_comment_voice and not resolved_comment_voice:
        raise CompilationTtsError(
            "comment_voice_id is required when the script contains comment-role narration"
        )
    if needs_comment_voice and resolved_comment_voice == str(voice_id).strip():
        raise CompilationTtsError(
            "comment_voice_id must not fall back to the narrator voice"
        )

    chunks: list[dict[str, Any]] = []
    for logical in logical_segments:
        voice_role = str(logical.get("voice_role") or "")
        chunk_effective_speed = effective_speed
        if (
            boundary_contract is not None
            and boundary_contract["episode_format"] == "BUNDLE"
            and logical.get("kind") == "transition"
        ):
            chunk_effective_speed = float(
                boundary_contract["effective_transition_speed"],
            )
        selected_voice_id = (
            resolved_comment_voice if voice_role == "comment" else str(voice_id).strip()
        )
        if profile is None:
            semantic_parts = [
                {
                    "semantic_beat_id": None,
                    "semantic_beat_index": None,
                    "boundary_source": None,
                    "part_index": index,
                    "text": text,
                }
                for index, text in enumerate(
                    split_long_text_for_tts(logical["text"], max_chars),
                    start=1,
                )
            ]
        else:
            semantic_parts = []
            for unit in logical["semantic_units"]:
                for part_index, text in enumerate(
                    _split_semantic_text(unit["text"], effective_max_chars),
                    start=1,
                ):
                    semantic_parts.append({
                        "semantic_beat_id": unit["semantic_beat_id"],
                        "semantic_beat_index": unit["semantic_beat_index"],
                        "boundary_source": unit["boundary_source"],
                        "semantic_unit_text_sha256": unit["text_sha256"],
                        "part_index": part_index,
                        "text": text,
                    })

        segment_chunks: list[dict[str, Any]] = []
        for index, semantic_part in enumerate(semantic_parts, start=1):
            text = semantic_part["text"]
            chunk_id = f"{logical['segment_id']}__{index:03d}"
            request_contract = {
                "text": text,
                "voice_id": selected_voice_id,
                "voice_role": voice_role,
                "model_id": model_id,
                "speed": chunk_effective_speed,
                "voice_settings_json": effective_voice_settings_json,
                "with_transcript": with_transcript,
                "context_chaining": context_chaining,
            }
            if boundary_contract is not None:
                request_contract.update({
                    "narration_boundary_contract_sha256": boundary_contract[
                        "narration_boundary_contract_sha256"
                    ],
                    "narration_boundary_policy_id": boundary_contract["policy_id"],
                })
            if pronunciation_dictionary_id is not None:
                request_contract.update({
                    "pronunciation_dictionary_id": pronunciation_dictionary_id,
                    "pronunciation_dictionary_sha256": str(pronunciation_dictionary_sha256).lower(),
                })
            chunk = {
                "chunk_id": chunk_id,
                "logical_segment_id": logical["segment_id"],
                "logical_segment_kind": logical["kind"],
                "voice_role": voice_role,
                "chunk_index": index,
                "text": text,
                "text_sha256": _sha256_bytes(text.encode("utf-8")),
                "request_sha256": _canonical_hash(request_contract),
                "voice_id": selected_voice_id,
                "model_id": model_id,
                **bindings,
                "status": "READY",
            }
            if pronunciation_dictionary_id is not None:
                chunk.update({
                    "pronunciation_dictionary_id": pronunciation_dictionary_id,
                    "pronunciation_dictionary_sha256": str(pronunciation_dictionary_sha256).lower(),
                })
            if profile is not None:
                request_contract["narration_profile_sha256"] = profile[
                    "profile_sha256"
                ]
                chunk["request_sha256"] = _canonical_hash(request_contract)
                chunk.update({
                    "narration_profile_id": profile["profile_id"],
                    "narration_profile_sha256": profile["profile_sha256"],
                    "narration_pillar_id": profile["pillar_id"],
                    "effective_speed": chunk_effective_speed,
                    "effective_voice_settings_json": effective_voice_settings_json,
                    "effective_with_transcript": bool(with_transcript),
                    "effective_context_chaining": bool(context_chaining),
                    "effective_semantic_max_chars": effective_max_chars,
                    "semantic_chunk_policy_sha256": _canonical_hash(
                        profile["semantic_chunk_policy"],
                    ),
                    "logical_segment_text_sha256": logical["text_sha256"],
                    "semantic_unit_text_sha256": semantic_part[
                        "semantic_unit_text_sha256"
                    ],
                    "semantic_beat_id": semantic_part["semantic_beat_id"],
                    "semantic_beat_index": semantic_part["semantic_beat_index"],
                    "semantic_boundary_source": semantic_part["boundary_source"],
                    "semantic_part_index": semantic_part["part_index"],
                })
                if boundary_contract is not None:
                    chunk.update({
                        "narration_boundary_contract_sha256": boundary_contract[
                            "narration_boundary_contract_sha256"
                        ],
                        "narration_boundary_policy_id": boundary_contract[
                            "policy_id"
                        ],
                        "episode_format": boundary_contract["episode_format"],
                        "boundary_source_count": boundary_contract["source_count"],
                    })
            segment_chunks.append(chunk)

        if profile is not None:
            for index, chunk in enumerate(segment_chunks):
                next_chunk = (
                    segment_chunks[index + 1]
                    if index + 1 < len(segment_chunks)
                    else None
                )
                chunk["is_last_in_beat"] = (
                    next_chunk is None
                    or next_chunk.get("semantic_beat_id")
                    != chunk.get("semantic_beat_id")
                )
                chunk["is_last_in_segment"] = next_chunk is None
        chunks.extend(segment_chunks)
    return chunks


def _new_state(
    chunks: list[dict[str, Any]],
    bindings: dict[str, str],
    boundary_contract: dict[str, Any] | None = None,
) -> dict[str, Any]:
    profile_id = str(
        (chunks[0].get("narration_profile_id") if chunks else "") or "",
    ).strip()
    profile_sha256 = str(
        (chunks[0].get("narration_profile_sha256") if chunks else "") or "",
    ).strip()
    chunk_identity: list[dict[str, Any]] = []
    for item in chunks:
        identity = {
            "chunk_id": item["chunk_id"],
            "request_sha256": item["request_sha256"],
            "voice_role": item["voice_role"],
        }
        if profile_id:
            identity.update({
                "semantic_beat_id": item["semantic_beat_id"],
                "semantic_beat_index": item["semantic_beat_index"],
                "semantic_boundary_source": item["semantic_boundary_source"],
                "semantic_unit_text_sha256": item["semantic_unit_text_sha256"],
                "semantic_part_index": item["semantic_part_index"],
                "is_last_in_beat": item["is_last_in_beat"],
                "is_last_in_segment": item["is_last_in_segment"],
            })
        chunk_identity.append(identity)
    narration_plan_identity: Any = chunk_identity
    if profile_id:
        narration_plan_identity = {
            "chunks": chunk_identity,
            "narration_profile_sha256": profile_sha256,
        }
        if boundary_contract is not None:
            narration_plan_identity["narration_boundary_contract_sha256"] = (
                boundary_contract["narration_boundary_contract_sha256"]
            )
    narration_plan_sha256 = _canonical_hash(narration_plan_identity)
    state = {
        "version": STATE_VERSION,
        "required_model_id": REQUIRED_MODEL_ID,
        **bindings,
        "plan_sha256": narration_plan_sha256,
        "narration_plan_sha256": narration_plan_sha256,
        "chunks": chunks,
        "status": "IN_PROGRESS",
        "publication_authorized": False,
    }
    if profile_id:
        state.update({
            "narration_profile_id": profile_id,
            "narration_profile_sha256": profile_sha256,
            "narration_pillar_id": chunks[0]["narration_pillar_id"],
            "semantic_chunk_policy_sha256": chunks[0][
                "semantic_chunk_policy_sha256"
            ],
        })
        if boundary_contract is not None:
            state.update({
                "narration_boundary_contract": boundary_contract,
                "narration_boundary_contract_sha256": boundary_contract[
                    "narration_boundary_contract_sha256"
                ],
                "narration_boundary_policy_id": boundary_contract["policy_id"],
                "episode_format": boundary_contract["episode_format"],
                "boundary_source_count": boundary_contract["source_count"],
            })
    return state


def _load_or_create_state(
    path: Path,
    planned: list[dict[str, Any]],
    bindings: dict[str, str],
    boundary_contract: dict[str, Any] | None = None,
) -> dict[str, Any]:
    expected = _new_state(planned, bindings, boundary_contract)
    if not path.exists():
        _atomic_json(path, expected)
        return expected
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CompilationTtsError("TTS state manifest is unreadable; refusing to submit") from exc
    if state.get("version") != STATE_VERSION or state.get("required_model_id") != REQUIRED_MODEL_ID:
        raise CompilationTtsError("TTS state contract is incompatible; refusing to submit")
    for field, expected_digest in bindings.items():
        if state.get(field) != expected_digest:
            raise CompilationTtsError(f"TTS state {field} changed; refusing to submit")
    if state.get("publication_authorized") is not False:
        raise CompilationTtsError("TTS state cannot authorize publication")
    for field in (
        "narration_profile_id",
        "narration_profile_sha256",
        "narration_pillar_id",
        "semantic_chunk_policy_sha256",
    ):
        if field in expected and state.get(field) != expected[field]:
            raise CompilationTtsError(
                f"TTS state {field} changed; refusing to submit"
            )
        if field not in expected and state.get(field):
            raise CompilationTtsError(
                "profile-aware TTS state cannot be reused without its profile"
            )
    boundary_fields = (
        "narration_boundary_contract",
        "narration_boundary_contract_sha256",
        "narration_boundary_policy_id",
        "episode_format",
        "boundary_source_count",
    )
    for field in boundary_fields:
        if field in expected and state.get(field) != expected[field]:
            raise CompilationTtsError(
                f"TTS state {field} changed; refusing to submit"
            )
        if field not in expected and state.get(field):
            raise CompilationTtsError(
                "boundary-aware TTS state cannot be reused without its contract"
            )
    if state.get("plan_sha256") != expected["plan_sha256"]:
        raise CompilationTtsError("TTS request plan changed; refusing to reuse or resubmit")
    existing = state.get("chunks")
    if not isinstance(existing, list) or len(existing) != len(planned):
        raise CompilationTtsError("TTS state chunk list is ambiguous; refusing to submit")
    for saved, wanted in zip(existing, planned):
        if saved.get("chunk_id") != wanted["chunk_id"] or saved.get("request_sha256") != wanted["request_sha256"]:
            raise CompilationTtsError("TTS state chunk identity changed; refusing to submit")
    if state.get("status") == "COMPLETE":
        if state.get("timing_contract_version") != TIMING_CONTRACT_VERSION:
            raise CompilationTtsError("complete TTS state has incompatible timing contract")
        for item in existing:
            _validate_completed_chunk_timing(item)
        contract_sha256 = str(state.get("timing_contract_sha256") or "").lower()
        if not SHA256_RE.fullmatch(contract_sha256) or contract_sha256 != _canonical_hash(
            _state_timing_contract(state)
        ):
            raise CompilationTtsError("complete TTS state timing contract checksum mismatch")
    return state


def _validate_reported_model(payload: dict[str, Any]) -> None:
    reported = collect_reported_model_ids(payload)
    mismatches = [value for value in reported if value != REQUIRED_MODEL_ID]
    if mismatches:
        raise CompilationTtsError(f"AI33 reported unexpected model identifiers: {mismatches}")


def _validated_task_id(value: Any, *, chunk_id: str) -> str:
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise CompilationTtsError(f"{chunk_id} submit response has an invalid task_id")
    task_id = str(value).strip()
    if not task_id or len(task_id) > 512:
        raise CompilationTtsError(f"{chunk_id} submit response has an invalid task_id")
    return task_id


def _assert_unique_task_id(
    state: dict[str, Any], *, task_id: str, chunk_id: str,
) -> None:
    for other in state.get("chunks") or []:
        other_chunk_id = str(other.get("chunk_id") or "")
        if other_chunk_id == chunk_id or other.get("status") != "SUBMITTED":
            continue
        if str(other.get("task_id") or "").strip() == task_id:
            raise CompilationTtsError(
                f"{chunk_id} and {other_chunk_id} share duplicate task_id; refusing to poll"
            )


def _complete_chunk(
    *,
    item: dict[str, Any],
    payload: dict[str, Any],
    audio_path: Path,
    root: Path,
    state: dict[str, Any],
    state_path: Path,
    probe_duration: Callable[[Path], float],
) -> None:
    """Bind one provider result to exact text/audio/timing and persist it atomically."""
    _validate_reported_model(payload)
    if not audio_path.is_file() or audio_path.stat().st_size <= 0:
        raise CompilationTtsError(f"{item['chunk_id']} completed without audio")
    try:
        duration = float(probe_duration(audio_path))
    except CompilationTtsError:
        raise
    except Exception as exc:
        raise CompilationTtsError(
            f"could not verify audio duration for {item['chunk_id']}"
        ) from exc
    if duration <= 0:
        raise CompilationTtsError(f"{item['chunk_id']} audio duration must be positive")
    timing_source, word_timings = _build_chunk_timing(item["text"], payload, duration)
    item["status"] = "COMPLETE"
    item["audio_path"] = audio_path.resolve().relative_to(root).as_posix()
    item["audio_sha256"] = _sha256_file(audio_path)
    item["audio_duration_sec"] = round(duration, 6)
    item["timing_source"] = timing_source
    item["word_timings"] = word_timings
    item["word_timings_sha256"] = _canonical_hash(word_timings)
    _validate_completed_chunk_timing(item)
    _atomic_json(state_path, state)


def resume_compilation_tts_from_saved_state(
    *,
    output_dir: Path,
    artifact_root: Path | None = None,
    api_key: str,
    expected_task_id: str,
    timeout_seconds: int = 1_800,
    overall_timeout_seconds: int | None = None,
    poll_interval: int = 5,
    poll_task: Callable[..., dict[str, Any]] = poll_for_audio,
    poll_error_retries: int = 4,
    sleeper: Callable[[float], None] = time.sleep,
    monotonic: Callable[[], float] = time.monotonic,
    wall_clock: Callable[[], float] = time.time,
    concat: Callable[[list[Path], Path], None] = concat_audio_segments,
    probe_duration: Callable[[Path], float] = _probe_duration,
) -> dict[str, Any]:
    """Poll saved provider identities without rebuilding or submitting a plan."""
    deadline = _resolve_shared_deadline(
        timeout_seconds=timeout_seconds,
        overall_timeout_seconds=overall_timeout_seconds,
        overall_deadline_epoch=None,
        monotonic=monotonic,
        wall_clock=wall_clock,
    )
    output_dir = Path(output_dir)
    root = Path(artifact_root).resolve() if artifact_root is not None else output_dir.resolve()
    resolved_output_dir = output_dir.resolve()
    if resolved_output_dir != root and root not in resolved_output_dir.parents:
        raise CompilationTtsError("TTS output_dir must remain under artifact_root")
    state_path = output_dir / "compilation_tts_state.json"
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CompilationTtsError("saved TTS state is unreadable; refusing recovery") from exc
    if not isinstance(state, dict):
        raise CompilationTtsError("saved TTS state must be an object")
    if state.get("version") != STATE_VERSION or state.get("required_model_id") != REQUIRED_MODEL_ID:
        raise CompilationTtsError("saved TTS state contract is incompatible")
    if state.get("publication_authorized") is not False:
        raise CompilationTtsError("saved TTS state cannot authorize publication")
    chunks = state.get("chunks")
    if not isinstance(chunks, list) or not chunks:
        raise CompilationTtsError("saved TTS state has no chunks")
    expected = _validated_task_id(expected_task_id, chunk_id="recovery")
    submitted = [item for item in chunks if item.get("status") == "SUBMITTED"]
    if len(submitted) != 1:
        raise CompilationTtsError("direct recovery requires exactly one SUBMITTED chunk")
    item_to_poll = submitted[0]
    chunk_id_to_poll = str(item_to_poll.get("chunk_id") or "")
    saved_task_id = _validated_task_id(item_to_poll.get("task_id"), chunk_id=chunk_id_to_poll)
    if saved_task_id != expected:
        raise CompilationTtsError("saved AI33 task id does not match the recovery preflight")

    audio_paths: list[Path] = []
    submitted_audio_path: Path | None = None
    for item in chunks:
        chunk_id = str(item.get("chunk_id") or "")
        if not re.fullmatch(r"[A-Za-z0-9._-]+", chunk_id):
            raise CompilationTtsError("saved TTS chunk_id is unsafe")
        audio_path = output_dir / "segments" / f"{chunk_id}.mp3"
        audio_paths.append(audio_path)
        if item.get("status") == "COMPLETE":
            if not audio_path.is_file() or _sha256_file(audio_path) != item.get("audio_sha256"):
                raise CompilationTtsError(f"{chunk_id} COMPLETE audio checksum mismatch")
            _validate_completed_chunk_timing(item)
        elif item is item_to_poll:
            submitted_audio_path = audio_path
        else:
            raise CompilationTtsError(
                f"{chunk_id} has status {item.get('status')!r}; direct recovery cannot submit"
            )
    if submitted_audio_path is None:
        raise CompilationTtsError("saved SUBMITTED chunk has no audio destination")
    submitted_audio_path.parent.mkdir(parents=True, exist_ok=True)
    payload = _poll_with_retries(
        poll_task,
        retries=poll_error_retries,
        sleeper=sleeper,
        deadline=deadline,
        monotonic=monotonic,
        poll_kwargs={
            "api_key": api_key,
            "task_id": saved_task_id,
            "output_path": submitted_audio_path,
            "poll_interval": poll_interval,
        },
    )
    _complete_chunk(
        item=item_to_poll,
        payload=payload,
        audio_path=submitted_audio_path,
        root=root,
        state=state,
        state_path=state_path,
        probe_duration=probe_duration,
    )
    if deadline - monotonic() <= 0:
        raise CompilationTtsError("shared AI33 TTS deadline expired before final concatenation")
    final_path = output_dir / "compilation_narration.mp3"
    concat(audio_paths, final_path)
    if not final_path.is_file() or final_path.stat().st_size <= 0:
        raise CompilationTtsError("concatenation did not create final audio")
    final_duration = float(probe_duration(final_path))
    raw_chunk_duration = sum(float(item["audio_duration_sec"]) for item in chunks)
    if final_duration <= 0 or raw_chunk_duration <= 0:
        raise CompilationTtsError("final narration timing contract must have positive duration")
    state["final_audio_path"] = final_path.resolve().relative_to(root).as_posix()
    state["final_audio_sha256"] = _sha256_file(final_path)
    state["timing_contract_version"] = TIMING_CONTRACT_VERSION
    state["final_audio_duration_sec"] = round(final_duration, 6)
    state["raw_chunk_duration_sec"] = round(raw_chunk_duration, 6)
    state["timeline_scale"] = round(final_duration / raw_chunk_duration, 12)
    state["timing_contract_sha256"] = _canonical_hash(_state_timing_contract(state))
    state["status"] = "COMPLETE"
    _atomic_json(state_path, state)
    if state.get("narration_profile_id"):
        from compilation_audio_mix import build_pause_map

        pause_map_path = output_dir / "narration-pause-map.json"
        pause_map = build_pause_map(state, output_path=pause_map_path)
        state["pause_map_path"] = pause_map_path.resolve().relative_to(root).as_posix()
        state["pause_map_sha256"] = pause_map["pause_map_sha256"]
        state["pause_map_duration_sec"] = pause_map["timeline_duration_sec"]
        _atomic_json(state_path, state)
    return state


def run_compilation_tts(
    compilation: dict[str, Any],
    *,
    output_dir: Path,
    artifact_root: Path | None = None,
    api_key: str,
    voice_id: str,
    comment_voice_id: str | None = None,
    narration_profile_id: str | None = None,
    model_id: str = REQUIRED_MODEL_ID,
    max_chars: int = 4_500,
    speed: float = 1.0,
    voice_settings_json: str | None = None,
    with_transcript: bool = True,
    context_chaining: bool = False,
    pronunciation_dictionary_id: int | None = None,
    pronunciation_dictionary_sha256: str | None = None,
    timeout_seconds: int = 1_800,
    overall_timeout_seconds: int | None = None,
    overall_deadline_epoch: float | None = None,
    poll_interval: int = 5,
    poll_concurrency: int = DEFAULT_POLL_CONCURRENCY,
    post_task: Callable[..., dict[str, Any]] = post_tts_task,
    poll_task: Callable[..., dict[str, Any]] = poll_for_audio,
    poll_error_retries: int = 4,
    sleeper: Callable[[float], None] = time.sleep,
    monotonic: Callable[[], float] = time.monotonic,
    wall_clock: Callable[[], float] = time.time,
    write_payload: Callable[[dict[str, Any], Path, str], bool] = write_audio_from_payload,
    concat: Callable[[list[Path], Path], None] = concat_audio_segments,
    probe_duration: Callable[[Path], float] = _probe_duration,
) -> dict[str, Any]:
    """Submit every missing chunk, then poll saved task IDs under one shared deadline.

    ``timeout_seconds`` remains the backward-compatible timeout input, but it is
    now invocation-wide instead of being reset for every task. Callers may use
    ``overall_timeout_seconds`` explicitly or bind the run to an absolute Unix
    epoch via ``overall_deadline_epoch`` / ``AI33_TTS_DEADLINE_EPOCH``.
    """
    if isinstance(poll_concurrency, bool) or not isinstance(poll_concurrency, int):
        raise CompilationTtsError("poll_concurrency must be an integer")
    if poll_concurrency < 1 or poll_concurrency > MAX_POLL_CONCURRENCY:
        raise CompilationTtsError(
            f"poll_concurrency must be between 1 and {MAX_POLL_CONCURRENCY}"
        )
    if isinstance(poll_error_retries, bool) or not isinstance(poll_error_retries, int) or poll_error_retries < 0:
        raise CompilationTtsError("poll_error_retries must be a non-negative integer")
    deadline = _resolve_shared_deadline(
        timeout_seconds=timeout_seconds,
        overall_timeout_seconds=overall_timeout_seconds,
        overall_deadline_epoch=overall_deadline_epoch,
        monotonic=monotonic,
        wall_clock=wall_clock,
    )
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    root = Path(artifact_root).resolve() if artifact_root is not None else output_dir.resolve()
    resolved_output_dir = output_dir.resolve()
    if resolved_output_dir == root or root in resolved_output_dir.parents:
        pass
    else:
        raise CompilationTtsError("TTS output_dir must remain under artifact_root")
    state_path = output_dir / "compilation_tts_state.json"
    bindings = _plan_bindings(compilation)
    planned = build_tts_chunks(
        compilation,
        voice_id=voice_id,
        comment_voice_id=comment_voice_id,
        narration_profile_id=narration_profile_id,
        model_id=model_id,
        max_chars=max_chars,
        speed=speed,
        voice_settings_json=voice_settings_json,
        with_transcript=with_transcript,
        context_chaining=context_chaining,
        pronunciation_dictionary_id=pronunciation_dictionary_id,
        pronunciation_dictionary_sha256=pronunciation_dictionary_sha256,
    )
    try:
        resolved_profile = resolve_compilation_narration_profile(
            compilation,
            narration_profile_id,
        )
        boundary_contract = _resolve_declared_boundary_contract(
            compilation,
            resolved_profile,
        )
    except Exception as exc:
        if isinstance(exc, CompilationTtsError):
            raise
        raise CompilationTtsError(str(exc)) from exc
    state = _load_or_create_state(
        state_path,
        planned,
        bindings,
        boundary_contract,
    )

    audio_paths: list[Path] = []
    chunk_audio: list[tuple[dict[str, Any], Path]] = []
    for item in state["chunks"]:
        audio_path = output_dir / "segments" / f"{item['chunk_id']}.mp3"
        audio_path.parent.mkdir(parents=True, exist_ok=True)
        audio_paths.append(audio_path)
        chunk_audio.append((item, audio_path))
        status = item.get("status")

        if status == "COMPLETE":
            if not audio_path.is_file() or not item.get("audio_sha256"):
                raise CompilationTtsError(f"{item['chunk_id']} is COMPLETE without verifiable audio")
            if _sha256_file(audio_path) != item["audio_sha256"]:
                raise CompilationTtsError(f"{item['chunk_id']} audio checksum mismatch")
            _validate_completed_chunk_timing(item)
            continue
        if status == "SUBMITTED":
            task_id = _validated_task_id(
                item.get("task_id"), chunk_id=str(item["chunk_id"]),
            )
            _assert_unique_task_id(
                state, task_id=task_id, chunk_id=str(item["chunk_id"]),
            )
            continue
        if status == "READY":
            continue
        if status in {"SUBMITTING", "RESPONSE_RECEIVED"}:
            raise CompilationTtsError(
                f"{item['chunk_id']} has an ambiguous prior submit state {status!r}; "
                "refusing to resubmit"
            )
        raise CompilationTtsError(
            f"{item['chunk_id']} has ambiguous status {status!r}; refusing to submit"
        )

    # Submission phase. A durable SUBMITTING marker is written before every
    # external POST; a crash or uncertain transport result therefore blocks an
    # automatic duplicate. Every returned task ID is persisted immediately and
    # a final atomic barrier is written before the first poll starts.
    for item, audio_path in chunk_audio:
        if item.get("status") != "READY":
            continue
        if deadline - monotonic() <= 0:
            raise CompilationTtsError(
                "shared AI33 TTS deadline expired before all chunks were submitted"
            )
        item["status"] = "SUBMITTING"
        _atomic_json(state_path, state)
        payload = post_task(
            api_key=api_key,
            text=item["text"],
            voice_id=item["voice_id"],
            model_id=model_id,
            voice_settings_json=item.get(
                "effective_voice_settings_json", voice_settings_json,
            ),
            speed=item.get("effective_speed", speed),
            file_name=audio_path.name,
            with_transcript=item.get(
                "effective_with_transcript", with_transcript,
            ),
            context_chaining=item.get(
                "effective_context_chaining", context_chaining,
            ),
            receive_url=None,
            pronunciation_dictionary_id=item.get("pronunciation_dictionary_id"),
        )
        if not isinstance(payload, dict):
            raise CompilationTtsError(
                f"{item['chunk_id']} submit response is not an object; refusing to resubmit"
            )
        _validate_reported_model(payload)
        if "task_id" in payload:
            task_id = _validated_task_id(payload.get("task_id"), chunk_id=str(item["chunk_id"]))
            _assert_unique_task_id(
                state, task_id=task_id, chunk_id=str(item["chunk_id"]),
            )
            item["task_id"] = task_id
            item["status"] = "SUBMITTED"
            _atomic_json(state_path, state)
            continue

        item["status"] = "RESPONSE_RECEIVED"
        _atomic_json(state_path, state)
        if not write_payload(payload, audio_path, api_key):
            raise CompilationTtsError(
                f"{item['chunk_id']} response has neither task_id nor audio; refusing to resubmit"
            )
        _complete_chunk(
            item=item,
            payload=payload,
            audio_path=audio_path,
            root=root,
            state=state,
            state_path=state_path,
            probe_duration=probe_duration,
        )

    _atomic_json(state_path, state)  # all durable provider identities precede every poll

    submitted = [
        (item, audio_path)
        for item, audio_path in chunk_audio
        if item.get("status") == "SUBMITTED"
    ]
    if submitted:
        poll_errors: list[tuple[str, Exception]] = []

        def poll_saved_task(item: dict[str, Any], audio_path: Path) -> dict[str, Any]:
            return _poll_with_retries(
                poll_task,
                retries=poll_error_retries,
                sleeper=sleeper,
                deadline=deadline,
                monotonic=monotonic,
                poll_kwargs={
                    "api_key": api_key,
                    "task_id": _validated_task_id(
                        item.get("task_id"), chunk_id=str(item["chunk_id"]),
                    ),
                    "output_path": audio_path,
                    "poll_interval": poll_interval,
                },
            )

        with ThreadPoolExecutor(
            max_workers=min(poll_concurrency, len(submitted)),
            thread_name_prefix="ai33-poll",
        ) as executor:
            futures = {
                executor.submit(poll_saved_task, item, audio_path): (item, audio_path)
                for item, audio_path in submitted
            }
            for future in as_completed(futures):
                item, audio_path = futures[future]
                try:
                    payload = future.result()
                    _complete_chunk(
                        item=item,
                        payload=payload,
                        audio_path=audio_path,
                        root=root,
                        state=state,
                        state_path=state_path,
                        probe_duration=probe_duration,
                    )
                except Exception as exc:
                    poll_errors.append((str(item["chunk_id"]), exc))

        if poll_errors:
            chunk_id, error = poll_errors[0]
            if isinstance(error, CompilationTtsError):
                raise error
            raise CompilationTtsError(
                f"AI33 polling failed for saved task {chunk_id}: {error}"
            ) from error

    if deadline - monotonic() <= 0:
        raise CompilationTtsError(
            "shared AI33 TTS deadline expired before final concatenation"
        )

    final_path = output_dir / "compilation_narration.mp3"
    concat(audio_paths, final_path)
    if not final_path.is_file() or final_path.stat().st_size <= 0:
        raise CompilationTtsError("concatenation did not create final audio")
    try:
        final_duration = float(probe_duration(final_path))
    except CompilationTtsError:
        raise
    except Exception as exc:
        raise CompilationTtsError("could not verify final narration duration") from exc
    raw_chunk_duration = sum(float(item["audio_duration_sec"]) for item in state["chunks"])
    if final_duration <= 0 or raw_chunk_duration <= 0:
        raise CompilationTtsError("final narration timing contract must have positive duration")
    state["final_audio_path"] = final_path.resolve().relative_to(root).as_posix()
    state["final_audio_sha256"] = _sha256_file(final_path)
    state["timing_contract_version"] = TIMING_CONTRACT_VERSION
    state["final_audio_duration_sec"] = round(final_duration, 6)
    state["raw_chunk_duration_sec"] = round(raw_chunk_duration, 6)
    state["timeline_scale"] = round(final_duration / raw_chunk_duration, 12)
    state["timing_contract_sha256"] = _canonical_hash(_state_timing_contract(state))
    state["status"] = "COMPLETE"
    _atomic_json(state_path, state)
    if state.get("narration_profile_id"):
        from compilation_audio_mix import build_pause_map

        pause_map_path = output_dir / "narration-pause-map.json"
        pause_map = build_pause_map(state, output_path=pause_map_path)
        state["pause_map_path"] = pause_map_path.resolve().relative_to(root).as_posix()
        state["pause_map_sha256"] = pause_map["pause_map_sha256"]
        state["pause_map_duration_sec"] = pause_map["timeline_duration_sec"]
        _atomic_json(state_path, state)
    return state


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compilation", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--voice-id", required=True)
    parser.add_argument("--comment-voice-id")
    parser.add_argument("--narration-profile-id")
    parser.add_argument("--model-id", default=REQUIRED_MODEL_ID)
    parser.add_argument("--max-chars", type=int, default=4500)
    parser.add_argument("--overall-timeout-seconds", type=int)
    parser.add_argument("--overall-deadline-epoch", type=float)
    parser.add_argument("--poll-concurrency", type=int, default=DEFAULT_POLL_CONCURRENCY)
    parser.add_argument("--pronunciation-dictionary-id", type=int)
    parser.add_argument("--pronunciation-dictionary-sha256")
    parser.add_argument("--confirm-spend", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    compilation = json.loads(Path(args.compilation).read_text(encoding="utf-8"))
    chunks = build_tts_chunks(
        compilation,
        voice_id=args.voice_id,
        comment_voice_id=args.comment_voice_id,
        narration_profile_id=args.narration_profile_id,
        model_id=args.model_id,
        max_chars=args.max_chars,
        pronunciation_dictionary_id=args.pronunciation_dictionary_id,
        pronunciation_dictionary_sha256=args.pronunciation_dictionary_sha256,
    )
    if args.dry_run:
        print(json.dumps({"status": "dry_run", "would_call_ai33": False, "chunk_count": len(chunks), "model_id": args.model_id}))
        return 0
    if not args.confirm_spend:
        raise CompilationTtsError("refusing AI33 calls without --confirm-spend")
    api_key = os.environ.get("AI33_API_KEY") or os.environ.get("A133_API_KEY")
    if not api_key:
        raise CompilationTtsError("AI33_API_KEY is required")
    state = run_compilation_tts(
        compilation, output_dir=Path(args.output_dir), api_key=api_key,
        voice_id=args.voice_id, comment_voice_id=args.comment_voice_id,
        narration_profile_id=args.narration_profile_id,
        model_id=args.model_id, max_chars=args.max_chars,
        pronunciation_dictionary_id=args.pronunciation_dictionary_id,
        pronunciation_dictionary_sha256=args.pronunciation_dictionary_sha256,
        overall_timeout_seconds=args.overall_timeout_seconds,
        overall_deadline_epoch=args.overall_deadline_epoch,
        poll_concurrency=args.poll_concurrency,
    )
    print(json.dumps({"status": state["status"], "chunk_count": len(state["chunks"])}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
