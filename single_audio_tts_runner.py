"""One-provider-task compilation narration with master MP3 and SRT output."""

from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path
from typing import Any, Callable

from compilation_tts_runner import (
    REQUIRED_MODEL_ID,
    _atomic_json,
    _build_chunk_timing,
    _canonical_hash,
    _probe_duration,
    _sha256_file,
    _state_timing_contract,
    _validate_completed_chunk_timing,
    build_tts_chunks,
)
from translator_tts import Ai33Error, poll_for_audio, post_tts_task


class SingleAudioTtsError(RuntimeError):
    pass


def _srt_time(seconds: float) -> str:
    millis = max(0, round(seconds * 1000))
    hours, millis = divmod(millis, 3_600_000)
    minutes, millis = divmod(millis, 60_000)
    secs, millis = divmod(millis, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def write_srt(words: list[dict[str, Any]], path: Path, *, max_words: int = 9) -> None:
    cues: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    for word in words:
        current.append(word)
        token = str(word.get("word") or "")
        if len(current) >= max_words or token.endswith((".", "!", "?", "…", ":", ";")):
            cues.append(current)
            current = []
    if current:
        cues.append(current)
    blocks = []
    for index, cue in enumerate(cues, start=1):
        blocks.append(
            f"{index}\n{_srt_time(float(cue[0]['start']))} --> {_srt_time(float(cue[-1]['end']))}\n"
            + " ".join(str(item["word"]) for item in cue)
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n\n".join(blocks) + "\n", encoding="utf-8")


def _slice_audio(source: Path, output: Path, start: float, end: float) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([
        "ffmpeg", "-y", "-v", "error", "-i", str(source),
        "-ss", f"{start:.6f}", "-to", f"{end:.6f}",
        "-c:a", "libmp3lame", "-q:a", "2", str(output),
    ], check=True)


def run_single_audio_tts(
    compilation: dict[str, Any], *, output_dir: Path, artifact_root: Path,
    api_key: str, voice_id: str, narration_profile_id: str,
    pronunciation_dictionary_id: int, pronunciation_dictionary_sha256: str,
    speed: float, voice_settings_json: str,
    post_task: Callable[..., dict[str, Any]] = post_tts_task,
    poll_task: Callable[..., dict[str, Any]] = poll_for_audio,
    slice_audio: Callable[[Path, Path, float, float], None] = _slice_audio,
    probe_duration: Callable[[Path], float] = _probe_duration,
    resume_only: bool = False,
    poll_busy_retries: int = 20,
    sleeper: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    output_dir = Path(output_dir)
    root = Path(artifact_root).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    planned = build_tts_chunks(
        compilation,
        voice_id=voice_id,
        narration_profile_id=narration_profile_id,
        model_id=REQUIRED_MODEL_ID,
        speed=speed,
        voice_settings_json=voice_settings_json,
        with_transcript=True,
        pronunciation_dictionary_id=pronunciation_dictionary_id,
        pronunciation_dictionary_sha256=pronunciation_dictionary_sha256,
    )
    if any(item.get("voice_role") != "narrator" for item in planned):
        raise SingleAudioTtsError("single-audio v1 supports one narrator voice only")
    master_text = " ".join(str(item["text"]).strip() for item in planned)
    if not master_text or len(master_text) > 1_000_000:
        raise SingleAudioTtsError("single AI33 narration text is empty or exceeds 1,000,000 characters")
    request = {
        "version": 1,
        "status": "READY",
        "text_sha256": _canonical_hash(master_text),
        "character_count": len(master_text),
        "voice_id": voice_id,
        "model_id": REQUIRED_MODEL_ID,
        "speed": speed,
        "voice_settings_json": voice_settings_json,
        "with_transcript": True,
        "pronunciation_dictionary_id": pronunciation_dictionary_id,
        "pronunciation_dictionary_sha256": pronunciation_dictionary_sha256,
        "provider_task_cap": 1,
        "publication_authorized": False,
    }
    request_path = output_dir / "single-audio-request.json"
    master_audio = output_dir / "narration-master.mp3"
    if resume_only:
        try:
            saved = json.loads(request_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise SingleAudioTtsError("saved single-audio request is unreadable") from exc
        for field in (
            "text_sha256", "character_count", "voice_id", "model_id", "speed",
            "voice_settings_json", "with_transcript", "pronunciation_dictionary_id",
            "pronunciation_dictionary_sha256", "provider_task_cap",
        ):
            if saved.get(field) != request.get(field):
                raise SingleAudioTtsError(f"saved single-audio request changed: {field}")
        if saved.get("status") != "SUBMITTED" or not str(saved.get("task_id") or "").strip():
            raise SingleAudioTtsError("resume requires one durable SUBMITTED task")
        request = saved
        task_id = str(saved["task_id"])
    else:
        _atomic_json(request_path, request)
        request["status"] = "SUBMITTING"
        _atomic_json(request_path, request)
        payload = post_task(
            api_key=api_key, text=master_text, voice_id=voice_id,
            model_id=REQUIRED_MODEL_ID, voice_settings_json=voice_settings_json,
            speed=speed, file_name=master_audio.name, with_transcript=True,
            context_chaining=False, receive_url=None,
            pronunciation_dictionary_id=pronunciation_dictionary_id,
        )
        task_id = str(payload.get("task_id") or "").strip()
        if not task_id:
            raise SingleAudioTtsError("single AI33 request returned no task_id")
        request.update({"status": "SUBMITTED", "task_id": task_id})
        _atomic_json(request_path, request)
    payload = None
    for attempt in range(poll_busy_retries + 1):
        try:
            payload = poll_task(
                api_key=api_key, task_id=task_id, output_path=master_audio,
                poll_interval=15, timeout_seconds=14_400,
            )
            break
        except Ai33Error as exc:
            message = str(exc).casefold()
            if attempt >= poll_busy_retries or "429" not in message or "temporarily busy" not in message:
                raise
            sleeper(min(120, 30 * (attempt + 1)))
    if payload is None:
        raise SingleAudioTtsError("saved AI33 task polling did not return a payload")
    duration = float(probe_duration(master_audio))
    timing_source, master_words = _build_chunk_timing(
        master_text, payload, duration, api_key=api_key,
    )
    if timing_source != "ai33":
        raise SingleAudioTtsError("single-audio production requires real AI33 transcript timing")
    srt_path = output_dir / "narration.srt"
    write_srt(master_words, srt_path)
    cursor = 0
    chunks: list[dict[str, Any]] = []
    for index, item in enumerate(planned):
        count = len(str(item["text"]).split())
        selected = master_words[cursor:cursor + count]
        if len(selected) != count:
            raise SingleAudioTtsError("AI33 transcript does not cover the planned narration")
        start = 0.0 if index == 0 else (float(master_words[cursor - 1]["end"]) + float(selected[0]["start"])) / 2
        end_index = cursor + count
        end = duration if end_index == len(master_words) else (float(selected[-1]["end"]) + float(master_words[end_index]["start"])) / 2
        segment_path = output_dir / "segments" / f"{item['chunk_id']}.mp3"
        slice_audio(master_audio, segment_path, start, end)
        segment_duration = float(probe_duration(segment_path))
        relative_words = [{
            "word": word["word"],
            "start": round(max(0.0, float(word["start"]) - start), 6),
            "end": round(min(segment_duration, float(word["end"]) - start), 6),
        } for word in selected]
        completed = {**item,
            "status": "COMPLETE",
            "audio_path": segment_path.resolve().relative_to(root).as_posix(),
            "audio_sha256": _sha256_file(segment_path),
            "audio_duration_sec": round(segment_duration, 6),
            "timing_source": "ai33",
            "word_timings": relative_words,
            "word_timings_sha256": _canonical_hash(relative_words),
        }
        _validate_completed_chunk_timing(completed)
        chunks.append(completed)
        cursor += count
    if cursor != len(master_words):
        raise SingleAudioTtsError("AI33 transcript contains unmatched narration words")
    raw_duration = sum(float(item["audio_duration_sec"]) for item in chunks)
    state = {
        "version": 3, "required_model_id": REQUIRED_MODEL_ID,
        "episode_plan_sha256": compilation["episode_plan_sha256"],
        "daily_plan_sha256": compilation["daily_plan_sha256"],
        "narration_profile_id": planned[0]["narration_profile_id"],
        "narration_profile_sha256": planned[0]["narration_profile_sha256"],
        "narration_pillar_id": planned[0]["narration_pillar_id"],
        "narration_plan_sha256": _canonical_hash([item["request_sha256"] for item in planned]),
        "plan_sha256": _canonical_hash([item["request_sha256"] for item in planned]),
        "chunks": chunks, "status": "COMPLETE", "publication_authorized": False,
        "final_audio_path": master_audio.resolve().relative_to(root).as_posix(),
        "final_audio_sha256": _sha256_file(master_audio),
        "timing_contract_version": 1,
        "final_audio_duration_sec": round(duration, 6),
        "raw_chunk_duration_sec": round(raw_duration, 6),
        "timeline_scale": round(duration / raw_duration, 12),
        "single_provider_task": True,
        "provider_task_count": 1,
        "master_srt_path": srt_path.resolve().relative_to(root).as_posix(),
        "master_srt_sha256": _sha256_file(srt_path),
    }
    state["timing_contract_sha256"] = _canonical_hash(_state_timing_contract(state))
    _atomic_json(output_dir / "compilation_tts_state.json", state)
    request.update({
        "status": "COMPLETE", "master_audio_sha256": state["final_audio_sha256"],
        "master_srt_sha256": state["master_srt_sha256"],
    })
    _atomic_json(request_path, request)
    return state
