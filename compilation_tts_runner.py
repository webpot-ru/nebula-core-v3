"""Idempotent, resumable AI33 narration for ordered Reddit compilations."""

from __future__ import annotations

import hashlib
import json
import os
import argparse
from pathlib import Path
from typing import Any, Callable

from compilation_narration import build_compilation_segments
from translator_tts import (
    Ai33Error,
    collect_reported_model_ids,
    concat_audio_segments,
    poll_for_audio,
    post_tts_task,
    split_long_text_for_tts,
    write_audio_from_payload,
)


STATE_VERSION = 1
REQUIRED_MODEL_ID = "eleven_v3"


class CompilationTtsError(RuntimeError):
    """A fail-closed compilation TTS state or provider-contract error."""


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _canonical_hash(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return _sha256_bytes(encoded)


def _atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def build_tts_chunks(
    compilation: dict[str, Any],
    *,
    voice_id: str,
    model_id: str = REQUIRED_MODEL_ID,
    max_chars: int = 4_500,
    speed: float = 1.0,
    voice_settings_json: str | None = None,
    with_transcript: bool = True,
    context_chaining: bool = False,
) -> list[dict[str, Any]]:
    """Build stable chunks even when every logical segment has one narrator."""
    if model_id != REQUIRED_MODEL_ID:
        raise CompilationTtsError(f"required model is {REQUIRED_MODEL_ID!r}, got {model_id!r}")
    if max_chars < 500:
        raise CompilationTtsError("max_chars must be at least 500")
    if not str(voice_id or "").strip():
        raise CompilationTtsError("voice_id is required")

    chunks: list[dict[str, Any]] = []
    for logical in build_compilation_segments(compilation):
        parts = split_long_text_for_tts(logical["text"], max_chars)
        for index, text in enumerate(parts, start=1):
            chunk_id = f"{logical['segment_id']}__{index:03d}"
            request_contract = {
                "text": text,
                "voice_id": voice_id,
                "model_id": model_id,
                "speed": speed,
                "voice_settings_json": voice_settings_json,
                "with_transcript": with_transcript,
                "context_chaining": context_chaining,
            }
            chunks.append({
                "chunk_id": chunk_id,
                "logical_segment_id": logical["segment_id"],
                "chunk_index": index,
                "text": text,
                "text_sha256": _sha256_bytes(text.encode("utf-8")),
                "request_sha256": _canonical_hash(request_contract),
                "voice_id": voice_id,
                "model_id": model_id,
                "status": "READY",
            })
    return chunks


def _new_state(chunks: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "version": STATE_VERSION,
        "required_model_id": REQUIRED_MODEL_ID,
        "plan_sha256": _canonical_hash([
            {"chunk_id": item["chunk_id"], "request_sha256": item["request_sha256"]} for item in chunks
        ]),
        "chunks": chunks,
        "status": "IN_PROGRESS",
    }


def _load_or_create_state(path: Path, planned: list[dict[str, Any]]) -> dict[str, Any]:
    expected = _new_state(planned)
    if not path.exists():
        _atomic_json(path, expected)
        return expected
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CompilationTtsError("TTS state manifest is unreadable; refusing to submit") from exc
    if state.get("version") != STATE_VERSION or state.get("required_model_id") != REQUIRED_MODEL_ID:
        raise CompilationTtsError("TTS state contract is incompatible; refusing to submit")
    if state.get("plan_sha256") != expected["plan_sha256"]:
        raise CompilationTtsError("TTS request plan changed; refusing to reuse or resubmit")
    existing = state.get("chunks")
    if not isinstance(existing, list) or len(existing) != len(planned):
        raise CompilationTtsError("TTS state chunk list is ambiguous; refusing to submit")
    for saved, wanted in zip(existing, planned):
        if saved.get("chunk_id") != wanted["chunk_id"] or saved.get("request_sha256") != wanted["request_sha256"]:
            raise CompilationTtsError("TTS state chunk identity changed; refusing to submit")
    return state


def _validate_reported_model(payload: dict[str, Any]) -> None:
    reported = collect_reported_model_ids(payload)
    mismatches = [value for value in reported if value != REQUIRED_MODEL_ID]
    if mismatches:
        raise CompilationTtsError(f"AI33 reported unexpected model identifiers: {mismatches}")


def run_compilation_tts(
    compilation: dict[str, Any],
    *,
    output_dir: Path,
    api_key: str,
    voice_id: str,
    model_id: str = REQUIRED_MODEL_ID,
    max_chars: int = 4_500,
    speed: float = 1.0,
    voice_settings_json: str | None = None,
    with_transcript: bool = True,
    context_chaining: bool = False,
    timeout_seconds: int = 1_800,
    poll_interval: int = 5,
    post_task: Callable[..., dict[str, Any]] = post_tts_task,
    poll_task: Callable[..., dict[str, Any]] = poll_for_audio,
    write_payload: Callable[[dict[str, Any], Path, str], bool] = write_audio_from_payload,
    concat: Callable[[list[Path], Path], None] = concat_audio_segments,
) -> dict[str, Any]:
    """Generate missing chunks, poll saved tasks, and concatenate in plan order."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    state_path = output_dir / "compilation_tts_state.json"
    planned = build_tts_chunks(
        compilation,
        voice_id=voice_id,
        model_id=model_id,
        max_chars=max_chars,
        speed=speed,
        voice_settings_json=voice_settings_json,
        with_transcript=with_transcript,
        context_chaining=context_chaining,
    )
    state = _load_or_create_state(state_path, planned)

    audio_paths: list[Path] = []
    for item in state["chunks"]:
        audio_path = output_dir / "segments" / f"{item['chunk_id']}.mp3"
        audio_path.parent.mkdir(parents=True, exist_ok=True)
        audio_paths.append(audio_path)
        status = item.get("status")

        if status == "COMPLETE":
            if not audio_path.is_file() or not item.get("audio_sha256"):
                raise CompilationTtsError(f"{item['chunk_id']} is COMPLETE without verifiable audio")
            if _sha256_file(audio_path) != item["audio_sha256"]:
                raise CompilationTtsError(f"{item['chunk_id']} audio checksum mismatch")
            continue

        if status == "SUBMITTED":
            task_id = item.get("task_id")
            if not task_id:
                raise CompilationTtsError(f"{item['chunk_id']} is SUBMITTED without task_id")
            payload = poll_task(
                api_key=api_key,
                task_id=task_id,
                output_path=audio_path,
                timeout_seconds=timeout_seconds,
                poll_interval=poll_interval,
            )
        elif status == "READY":
            payload = post_task(
                api_key=api_key,
                text=item["text"],
                voice_id=voice_id,
                model_id=model_id,
                voice_settings_json=voice_settings_json,
                speed=speed,
                file_name=audio_path.name,
                with_transcript=with_transcript,
                context_chaining=context_chaining,
                receive_url=None,
                pronunciation_dictionary_id=None,
            )
            task_id = payload.get("task_id")
            item["status"] = "SUBMITTED" if task_id else "RESPONSE_RECEIVED"
            if task_id:
                item["task_id"] = str(task_id)
            _atomic_json(state_path, state)  # persist provider identity before polling/writing
            if task_id:
                payload = poll_task(
                    api_key=api_key,
                    task_id=str(task_id),
                    output_path=audio_path,
                    timeout_seconds=timeout_seconds,
                    poll_interval=poll_interval,
                )
            elif not write_payload(payload, audio_path, api_key):
                raise CompilationTtsError(f"{item['chunk_id']} response has neither task_id nor audio")
        else:
            raise CompilationTtsError(f"{item['chunk_id']} has ambiguous status {status!r}; refusing to submit")

        _validate_reported_model(payload)
        if not audio_path.is_file() or audio_path.stat().st_size <= 0:
            raise CompilationTtsError(f"{item['chunk_id']} completed without audio")
        item["status"] = "COMPLETE"
        item["audio_path"] = str(audio_path)
        item["audio_sha256"] = _sha256_file(audio_path)
        _atomic_json(state_path, state)

    final_path = output_dir / "compilation_narration.mp3"
    concat(audio_paths, final_path)
    if not final_path.is_file() or final_path.stat().st_size <= 0:
        raise CompilationTtsError("concatenation did not create final audio")
    state["status"] = "COMPLETE"
    state["final_audio_path"] = str(final_path)
    state["final_audio_sha256"] = _sha256_file(final_path)
    _atomic_json(state_path, state)
    return state


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compilation", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--voice-id", required=True)
    parser.add_argument("--model-id", default=REQUIRED_MODEL_ID)
    parser.add_argument("--max-chars", type=int, default=4500)
    parser.add_argument("--confirm-spend", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    compilation = json.loads(Path(args.compilation).read_text(encoding="utf-8"))
    chunks = build_tts_chunks(compilation, voice_id=args.voice_id, model_id=args.model_id, max_chars=args.max_chars)
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
        voice_id=args.voice_id, model_id=args.model_id, max_chars=args.max_chars,
    )
    print(json.dumps({"status": state["status"], "chunk_count": len(state["chunks"])}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
