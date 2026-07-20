#!/usr/bin/env python3
"""Build a real, local-only acc1 baseline/cinematic comparison artifact.

The fixture uses the production manifest, pause/mix, storyboard, renderer and
QA functions.  Synthetic source text, drawings and WAV tones prove mechanics
only; they are not a creative or voice-quality verdict.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import shutil
import subprocess
import sys
import wave
from array import array
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from acc1_episode_contract import (
    build_intro_contract,
    build_mid_story_cta_contract,
    canonical_hash,
    truth_disclosure_ru,
    validate_episode_script,
)
from acc1_episode_manifest import build_episode_manifest
from acc1_episode_packaging import (
    build_thumbnail_prompt,
    build_youtube_description,
    validate_packaging,
)
from acc1_narration_profiles import (
    STRANGE_DARK_UNEXPLAINED_PROFILE_ID,
    resolve_narration_profile,
)
from acc1_visual_contract import CINEMATIC_STORY_MODE, DEFAULT_VISUAL_MODE
from compilation_audio_mix import build_pause_map, mix_compilation_audio
from compilation_narration import build_compilation_segments
from compilation_qa import run_qa
from compilation_renderer import render_compilation
from compilation_storyboard import build_storyboard, narration_sha256
from compilation_tts_runner import TIMING_CONTRACT_VERSION, _state_timing_contract


MODES = (DEFAULT_VISUAL_MODE, CINEMATIC_STORY_MODE)
PILLAR_ID = "strange_dark_unexplained"
PROFILE_ID = STRANGE_DARK_UNEXPLAINED_PROFILE_ID
VOICE_ID = "fixture-narrator"
CANDIDATE_ID = "acc1-local-cinematic-comparison-v1"
SOURCE_ID = "local-saga-001"
SOURCE_BACKING = "ночной коридор был пуст и свет погас у двери"


class FixtureError(RuntimeError):
    """Raised when the deterministic comparison cannot prove its contract."""


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json(path: Path, value: dict[str, Any] | list[Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _run(command: list[str]) -> None:
    try:
        subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
            timeout=900,
        )
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or "").strip()[-1600:]
        raise FixtureError(f"local media command failed: {detail}") from exc
    except subprocess.TimeoutExpired as exc:
        raise FixtureError("local media command timed out") from exc


def _make_tone(path: Path, *, seconds: float, frequency: float) -> None:
    sample_rate = 48_000
    sample_count = round(sample_rate * seconds)
    samples = array(
        "h",
        (
            round(2_400 * math.sin(2 * math.pi * frequency * index / sample_rate))
            for index in range(sample_count)
        ),
    )
    if sys.byteorder != "little":
        samples.byteswap()
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as output:
        output.setparams((1, 2, sample_rate, sample_count, "NONE", "not compressed"))
        output.writeframes(samples.tobytes())


def _concat_wav(inputs: list[Path], output: Path) -> None:
    if not inputs:
        raise FixtureError("raw narration requires at least one WAV chunk")
    frames: list[bytes] = []
    parameters: tuple[int, int, int, int, str, str] | None = None
    for path in inputs:
        with wave.open(str(path), "rb") as source:
            current = source.getparams()
            comparable = (
                current.nchannels,
                current.sampwidth,
                current.framerate,
                0,
                current.comptype,
                current.compname,
            )
            if parameters is None:
                parameters = comparable
            elif comparable != parameters:
                raise FixtureError("fixture WAV chunks must use one exact format")
            frames.append(source.readframes(source.getnframes()))
    output.parent.mkdir(parents=True, exist_ok=True)
    assert parameters is not None
    with wave.open(str(output), "wb") as destination:
        destination.setparams(parameters)
        for payload in frames:
            destination.writeframes(payload)


def _make_scene(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    canvas = Image.new("RGB", (1920, 1080), (8, 15, 27))
    draw = ImageDraw.Draw(canvas)
    draw.rectangle((0, 650, 1920, 1080), fill=(18, 25, 37))
    draw.polygon(
        [(180, 880), (760, 180), (1350, 180), (1760, 880)],
        fill=(33, 48, 63),
    )
    draw.rectangle((870, 270, 1170, 880), fill=(15, 23, 31))
    draw.ellipse((1420, 180, 1710, 470), fill=(176, 93, 51))
    draw.line((960, 180, 960, 880), fill=(87, 112, 128), width=8)
    draw.text((70, 60), "LOCAL CONTRACT FIXTURE", fill=(210, 219, 224))
    canvas.save(path, format="PNG")


def _make_baseline_loop(scene: Path, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    _run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-loop", "1", "-i", str(scene), "-t", "1", "-r", "30",
        "-an", "-c:v", "libx264", "-preset", "ultrafast", "-crf", "22",
        "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(output),
    ])


def _source_snapshot() -> dict[str, Any]:
    body = ((SOURCE_BACKING + " ") * 270 + "старый ключ лежал у двери").strip()
    return {
        "source_id": SOURCE_ID,
        "post_id": SOURCE_ID,
        "title": "Ключ у двери",
        "body": body,
        "body_sha256": hashlib.sha256(body.encode("utf-8")).hexdigest(),
        "source_url": (
            "https://www.reddit.com/r/nosleep/comments/"
            "local-saga-001/local_fixture/"
        ),
        "author": "fixture_author",
        "subreddit": "nosleep",
        "truth_mode": "unverified_personal_account",
        "source_media": [],
    }


def _story_narration() -> str:
    return (
        "Ночной коридор был пуст. Свет погас у двери, и старый ключ остался "
        "лежать на полу. Сначала казалось, что в доме просто отключили лампу. "
        "Потом свет вернулся, но коридор всё равно выглядел пустым. Ключ никто "
        "не поднял, дверь не открылась, шагов за стеной не было. Через минуту "
        "лампа снова погасла. Когда она зажглась, ключ лежал уже ближе к двери. "
        "Коридор оставался пустым, и никто не мог объяснить, почему предмет "
        "сдвинулся. Свет мигнул в третий раз. После этого ключ оказался прямо "
        "у порога. До утра дверь так и не открылась, а ночной коридор больше "
        "не освещался. Утром старый ключ всё ещё лежал у двери."
    )


def _shared_contracts() -> dict[str, Any]:
    source = _source_snapshot()
    daily_plan = {
        "episode_key": "acc1/2026-07-17/pilot_03",
        "production_date": "2026-07-17",
        "pilot_id": "pilot_03",
        "format": "SAGA",
        "pillar": PILLAR_ID,
        "publication_authorized": False,
    }
    source_queue = {
        "channel_id": "acc1",
        "entries": [{
            "post_id": source["post_id"],
            "source_body": source["body"],
            "source_body_sha256": source["body_sha256"],
        }],
    }
    topic_review = {
        "status": "review_ready",
        "top_topics": [{"post_id": source["post_id"]}],
    }
    greenlight = {
        "channel_id": "acc1",
        "pilot_id": daily_plan["pilot_id"],
        "format": daily_plan["format"],
        "pillar": daily_plan["pillar"],
        "publication_authorized": False,
        "sources": [{
            "post_id": source["post_id"],
            "source_body_sha256": source["body_sha256"],
            "truth_mode": source["truth_mode"],
        }],
    }
    beats = [
        {
            "beat": "Пустой коридор задаёт исходную сцену",
            "source_id": SOURCE_ID,
            "source_quote": "ночной коридор был пуст",
        },
        {
            "beat": "Свет у двери гаснет",
            "source_id": SOURCE_ID,
            "source_quote": "свет погас у двери",
        },
        {
            "beat": "Ключ остаётся у двери",
            "source_id": SOURCE_ID,
            "source_quote": SOURCE_BACKING,
        },
    ]
    originality_plan = {
        "editorial_frame": {
            "direction": "Сохранить спокойный наблюдательный тон без новых фактов",
            "source_id": SOURCE_ID,
            "source_quote": beats[0]["source_quote"],
        },
        "visual_direction": {
            "direction": "Показывать только пустой ночной коридор и дверь",
            "source_id": SOURCE_ID,
            "source_quote": beats[1]["source_quote"],
        },
        "sound_direction": {
            "direction": "Оставить голос без драматических звуковых утверждений",
            "source_id": SOURCE_ID,
            "source_quote": beats[2]["source_quote"],
        },
    }
    cold_open = {
        "text": "Свет в пустом ночном коридоре погас, а старый ключ остался у двери.",
        "source_id": SOURCE_ID,
        "source_quote": SOURCE_BACKING,
    }
    source_set = [{
        "source_id": SOURCE_ID,
        "body_sha256": source["body_sha256"],
        "source_url": source["source_url"],
        "truth_mode": source["truth_mode"],
        "role": "story",
    }]
    playoff = {
        "status": "READY_FOR_SCRIPTING",
        "playoff_sha256": "2" * 64,
        "winner": {
            "source_set_sha256": canonical_hash(source_set),
            "creative_plan_sha256": canonical_hash({
                "story_beats": beats,
                "originality_plan": originality_plan,
            }),
            "cold_open_sha256": canonical_hash(cold_open),
        },
    }
    disclosure = truth_disclosure_ru({source["truth_mode"]})
    intro = build_intro_contract(
        cold_open=cold_open,
        episode_format=daily_plan["format"],
        pillar=daily_plan["pillar"],
        source_count=1,
        response_count=0,
        first_title_ru="Ключ у двери",
        truth_disclosure=disclosure,
    )
    mid_story_cta = build_mid_story_cta_contract(
        episode_format=daily_plan["format"],
        pillar=daily_plan["pillar"],
        anchor_source=source,
        anchor_index=1,
        source_count=1,
    )
    base_script = {
        "playoff_sha256": playoff["playoff_sha256"],
        "publication_authorized": False,
        "episode_format": daily_plan["format"],
        "pilot_id": daily_plan["pilot_id"],
        "pillar": daily_plan["pillar"],
        "title_ru": "Ключ у двери",
        "truth_disclosure_ru": disclosure,
        "intro_contract": intro,
        "intro_ru": intro["intro_ru"],
        "mid_story_cta_contract": mid_story_cta,
        "mid_story_cta_ru": mid_story_cta["cta_ru"],
        "outro_ru": "Что бы вы сделали, если бы нашли такой ключ у двери?",
        "source_story_beats": beats,
        "originality_plan": originality_plan,
        "rights_mode": "test_only_not_cleared",
        "revision_count": 0,
        "editorial_review": {"verdict": "PASS", "issues": []},
        "stories": [{
            "title_ru": "Ключ у двери",
            "narration_ru": _story_narration(),
            "narration_role": "narrator",
            "source_snapshot": source,
            "ending_preserved_evidence": "старый ключ всё ещё лежал у двери",
            "translation_audit": {"review": {"verdict": "PASS"}},
            "change_ledger": [],
            "invented_factual_claims": [],
            "editorial_review": {"verdict": "PASS", "issues": []},
            "disclosure": "unverified personal account from Reddit",
        }],
    }
    return {
        "source": source,
        "daily_plan": daily_plan,
        "source_queue": source_queue,
        "topic_review": topic_review,
        "greenlight": greenlight,
        "playoff": playoff,
        "base_script": base_script,
    }


def _episode_plan(shared: dict[str, Any], visual_mode: str) -> dict[str, Any]:
    daily = shared["daily_plan"]
    return build_episode_manifest(
        episode_key=daily["episode_key"],
        episode_date=daily["production_date"],
        pilot_id=daily["pilot_id"],
        format_id=daily["format"],
        pillar=daily["pillar"],
        source_queue=shared["source_queue"],
        topic_review=shared["topic_review"],
        greenlight=shared["greenlight"],
        config={
            "channel_id": "acc1",
            "format": daily["format"],
            "visual_mode": visual_mode,
        },
        daily_plan=daily,
        git_sha="1" * 40,
        provider_settings={
            "tts": {"model_id": "eleven_v3", "voice_id": VOICE_ID},
        },
        visual_mode=visual_mode,
        narration_profile_id=PROFILE_ID,
    )


def _bound_script(
    shared: dict[str, Any],
    plan: dict[str, Any],
    *,
    visual_mode: str,
    scene_path: Path,
    artifact_root: Path,
) -> dict[str, Any]:
    script = copy.deepcopy(shared["base_script"])
    script.update({
        "episode_plan_sha256": plan["episode_plan_sha256"],
        "daily_plan_sha256": plan["daily_plan_sha256"],
        "visual_mode": visual_mode,
        "narration_profile_id": plan["narration_profile_id"],
        "narration_profile_sha256": plan["narration_profile_sha256"],
    })
    if visual_mode == CINEMATIC_STORY_MODE:
        script["stories"][0]["generated_media"] = [{
            "download_status": "verified",
            "artifact_path": scene_path.resolve().relative_to(
                artifact_root.resolve(),
            ).as_posix(),
            "sha256": _sha256_file(scene_path),
        }]
    return script


def _metadata(
    script: dict[str, Any],
    plan: dict[str, Any],
) -> dict[str, Any]:
    source = script["stories"][0]["source_snapshot"]
    options = [
        {
            "youtube_title": "Ключ появился у закрытой двери",
            "thumbnail_text": "КЛЮЧ У ДВЕРИ",
            "first_screen_promise": "Что случилось в пустом ночном коридоре",
            "angle": "необъяснимое перемещение",
            "source_id": SOURCE_ID,
            "source_backing": SOURCE_BACKING,
        },
        {
            "youtube_title": "Свет погас, а ключ оказался ближе",
            "thumbnail_text": "СВЕТ ПОГАС",
            "first_screen_promise": "Одна короткая история из ночного коридора",
            "angle": "нарастающее напряжение",
            "source_id": SOURCE_ID,
            "source_backing": SOURCE_BACKING,
        },
        {
            "youtube_title": "Пустой коридор и старый ключ",
            "thumbnail_text": "КОРИДОР ПУСТ",
            "first_screen_promise": "Почему дверь не открылась до самого утра",
            "angle": "неразрешённая загадка",
            "source_id": SOURCE_ID,
            "source_backing": SOURCE_BACKING,
        },
    ]
    return {
        "status": "PASS",
        "packaging_options": options,
        "selected_option_index": 0,
        "youtube_title": options[0]["youtube_title"],
        "thumbnail_text": options[0]["thumbnail_text"],
        "youtube_description": build_youtube_description(
            script["truth_disclosure_ru"],
            [source["source_url"]],
        ),
        "thumbnail_prompt": build_thumbnail_prompt(SOURCE_BACKING),
        "thumbnail_source_id": SOURCE_ID,
        "thumbnail_source_backing": SOURCE_BACKING,
        "language": "ru",
        "risk_flags": [],
        "episode_plan_sha256": plan["episode_plan_sha256"],
        "daily_plan_sha256": plan["daily_plan_sha256"],
        "publication_authorized": False,
    }


def _shared_audio_contract(
    base_script: dict[str, Any],
    artifact_root: Path,
) -> dict[str, Any]:
    segments = build_compilation_segments(base_script)
    duration_by_kind = {
        "intro": 2.2,
        "story": 24.0,
        "mid_story_cta": 2.5,
        "outro": 2.1,
    }
    chunks: list[dict[str, Any]] = []
    chunk_paths: list[Path] = []
    for index, segment in enumerate(segments):
        try:
            duration = duration_by_kind[segment["kind"]]
        except KeyError as exc:
            raise FixtureError(
                f"unexpected fixture narration segment kind: {segment['kind']}",
            ) from exc
        chunk_path = (
            artifact_root / "shared" / "audio" / "chunks"
            / f"{index:02d}-{segment['segment_id']}.wav"
        )
        _make_tone(
            chunk_path,
            seconds=duration,
            frequency=170.0 + index * 37.0,
        )
        words = segment["text"].split()
        timings = [
            {
                "word": word,
                "start": round(position * duration / len(words), 3),
                "end": round((position + 1) * duration / len(words), 3),
                "timing_source": "estimated_from_audio_duration",
            }
            for position, word in enumerate(words)
        ]
        chunks.append({
            "chunk_id": f"{segment['segment_id']}__001",
            "chunk_index": 1,
            "logical_segment_id": segment["segment_id"],
            "logical_segment_kind": segment["kind"],
            "semantic_beat_id": f"{segment['segment_id']}-beat-01",
            "semantic_beat_index": 1,
            "voice_role": segment["voice_role"],
            "text": segment["text"],
            "text_sha256": hashlib.sha256(
                segment["text"].encode("utf-8"),
            ).hexdigest(),
            "audio_path": chunk_path.resolve().relative_to(
                artifact_root.resolve(),
            ).as_posix(),
            "audio_sha256": _sha256_file(chunk_path),
            "audio_duration_sec": duration,
            "timing_source": "estimated_from_audio_duration",
            "word_timings": timings,
            "word_timings_sha256": canonical_hash(timings),
            "is_last_in_beat": True,
            "is_last_in_segment": True,
        })
        chunk_paths.append(chunk_path)

    raw_audio = artifact_root / "shared" / "audio" / "raw-narration.wav"
    _concat_wav(chunk_paths, raw_audio)
    narration_plan = [
        {
            "segment_id": segment["segment_id"],
            "kind": segment["kind"],
            "voice_role": segment["voice_role"],
            "text": segment["text"],
        }
        for segment in segments
    ]
    narration_plan_sha256 = canonical_hash(narration_plan)
    _write_json(
        artifact_root / "shared" / "audio" / "narration-plan.json",
        {
            "segments": narration_plan,
            "narration_plan_sha256": narration_plan_sha256,
            "publication_authorized": False,
        },
    )
    return {
        "chunks": chunks,
        "raw_audio_path": raw_audio,
        "raw_audio_relative": raw_audio.resolve().relative_to(
            artifact_root.resolve(),
        ).as_posix(),
        "raw_audio_sha256": _sha256_file(raw_audio),
        "raw_duration_sec": round(
            sum(float(chunk["audio_duration_sec"]) for chunk in chunks),
            6,
        ),
        "narration_plan_sha256": narration_plan_sha256,
        "input_chunks_sha256": canonical_hash([
            {
                "chunk_id": chunk["chunk_id"],
                "audio_path": chunk["audio_path"],
                "audio_sha256": chunk["audio_sha256"],
                "audio_duration_sec": chunk["audio_duration_sec"],
                "timing_source": chunk["timing_source"],
                "word_timings_sha256": chunk["word_timings_sha256"],
            }
            for chunk in chunks
        ]),
    }


def _tts_state(
    plan: dict[str, Any],
    shared_audio: dict[str, Any],
) -> dict[str, Any]:
    profile = resolve_narration_profile(
        plan["narration_profile_id"],
        pillar_id=PILLAR_ID,
    )
    chunks: list[dict[str, Any]] = []
    for shared_chunk in shared_audio["chunks"]:
        chunk = copy.deepcopy(shared_chunk)
        chunk.update({
            "status": "COMPLETE",
            "model_id": "eleven_v3",
            "voice_id": VOICE_ID,
            "episode_plan_sha256": plan["episode_plan_sha256"],
            "daily_plan_sha256": plan["daily_plan_sha256"],
            "narration_profile_id": profile["profile_id"],
            "narration_profile_sha256": profile["profile_sha256"],
        })
        chunks.append(chunk)
    state = {
        "status": "COMPLETE",
        "required_model_id": "eleven_v3",
        "chunks": chunks,
        "episode_plan_sha256": plan["episode_plan_sha256"],
        "daily_plan_sha256": plan["daily_plan_sha256"],
        "narration_plan_sha256": shared_audio["narration_plan_sha256"],
        "narration_profile_id": profile["profile_id"],
        "narration_profile_sha256": profile["profile_sha256"],
        "narration_pillar_id": profile["pillar_id"],
        "final_audio_path": shared_audio["raw_audio_relative"],
        "final_audio_sha256": shared_audio["raw_audio_sha256"],
        "timing_contract_version": TIMING_CONTRACT_VERSION,
        "final_audio_duration_sec": shared_audio["raw_duration_sec"],
        "raw_chunk_duration_sec": shared_audio["raw_duration_sec"],
        "timeline_scale": 1.0,
        "network_used": False,
        "publication_authorized": False,
    }
    state["timing_contract_sha256"] = canonical_hash(
        _state_timing_contract(state),
    )
    return state


def _mode_run(
    artifact_root: Path,
    shared: dict[str, Any],
    shared_audio: dict[str, Any],
    *,
    visual_mode: str,
    scene_path: Path,
    baseline_loop: Path,
    thumbnail_path: Path,
) -> dict[str, Any]:
    mode_dir = artifact_root / "modes" / visual_mode
    mode_dir.mkdir(parents=True, exist_ok=True)
    plan = _episode_plan(shared, visual_mode)
    script = _bound_script(
        shared,
        plan,
        visual_mode=visual_mode,
        scene_path=scene_path,
        artifact_root=artifact_root,
    )
    metadata = _metadata(script, plan)
    script_report = validate_episode_script(
        script,
        plan=plan,
        playoff=shared["playoff"],
    )
    if script_report["status"] != "PASS":
        raise FixtureError(
            f"{visual_mode} script contract blocked: "
            + "; ".join(script_report["failures"]),
        )
    packaging_failures = validate_packaging(metadata, script)
    if packaging_failures:
        raise FixtureError(
            f"{visual_mode} packaging contract blocked: "
            + "; ".join(packaging_failures),
        )

    tts_state = _tts_state(plan, shared_audio)
    pause_path = mode_dir / "narration-pause-map.json"
    pause_map = build_pause_map(tts_state, output_path=pause_path)
    mix_path = mode_dir / "voice-only-mix.wav"
    mix_report_path = mode_dir / "audio-mix-report.json"
    mix_report = mix_compilation_audio(
        tts_state,
        artifact_root=artifact_root,
        pause_map=pause_map,
        pause_map_path=pause_path,
        output_path=mix_path,
        report_path=mix_report_path,
    )
    tts_state.update({
        "pause_map_path": pause_path.resolve().relative_to(
            artifact_root.resolve(),
        ).as_posix(),
        "pause_map_sha256": pause_map["pause_map_sha256"],
        "pause_map_duration_sec": pause_map["timeline_duration_sec"],
    })
    audio_path = artifact_root / str(mix_report["output_path"])
    if not audio_path.is_file():
        raise FixtureError(f"{visual_mode} final mix is missing")

    storyboard = build_storyboard(
        script,
        artifact_root,
        background_video=(baseline_loop if visual_mode == DEFAULT_VISUAL_MODE else None),
        tts_state=tts_state,
        visual_mode=visual_mode,
        pause_map=pause_map,
        audio_mix_report=mix_report,
    )
    storyboard_path = mode_dir / "storyboard.json"
    if visual_mode == CINEMATIC_STORY_MODE:
        _write_json(mode_dir / "shot-plan.json", storyboard["shot_plan"])
        _write_json(mode_dir / "caption-track.json", storyboard["caption_track"])
    _write_json(mode_dir / "episode-plan.json", plan)
    _write_json(mode_dir / "episode-script.json", script)
    _write_json(mode_dir / "youtube-metadata.json", metadata)
    _write_json(mode_dir / "tts-state.json", tts_state)
    _write_json(storyboard_path, storyboard)

    video_path = mode_dir / "final-output.mp4"
    render_report = render_compilation(
        storyboard,
        artifact_root,
        video_path,
        audio=audio_path,
    )
    render_report["output"] = video_path.resolve().relative_to(
        artifact_root.resolve(),
    ).as_posix()
    if render_report.get("caption_srt"):
        render_report["caption_srt"] = Path(
            render_report["caption_srt"],
        ).resolve().relative_to(artifact_root.resolve()).as_posix()
    render_report_path = mode_dir / "render-report.json"
    _write_json(render_report_path, render_report)
    artifact_hashes = {
        "script_sha256": _sha256_file(mode_dir / "episode-script.json"),
        "audio_sha256": _sha256_file(audio_path),
        "metadata_sha256": _sha256_file(mode_dir / "youtube-metadata.json"),
        "storyboard_sha256": _sha256_file(storyboard_path),
        "video_sha256": _sha256_file(video_path),
        "thumbnail_sha256": _sha256_file(thumbnail_path),
    }
    qa_report = run_qa(
        script,
        metadata,
        tts_state,
        storyboard,
        render_report,
        artifact_root=artifact_root,
        video_path=video_path,
        thumbnail_path=thumbnail_path,
        creative_manifest=storyboard.get("creative_manifest"),
        expected_voice_id=VOICE_ID,
        episode_plan=plan,
        topic_playoff=shared["playoff"],
        artifact_hashes=artifact_hashes,
        audio_path=audio_path,
        pause_map=pause_map,
        audio_mix_report=mix_report,
    )
    _write_json(mode_dir / "media-qa.json", qa_report)
    if qa_report["status"] != "PASS":
        raise FixtureError(
            f"{visual_mode} production QA blocked: "
            + "; ".join(qa_report["failures"]),
        )

    loudness = mix_report["loudness"]
    return {
        "visual_mode": visual_mode,
        "episode_plan_sha256": plan["episode_plan_sha256"],
        "daily_plan_sha256": plan["daily_plan_sha256"],
        "narration_sha256": narration_sha256(script),
        "narration_plan_sha256": tts_state["narration_plan_sha256"],
        "timing_contract_sha256": tts_state["timing_contract_sha256"],
        "raw_audio_sha256": tts_state["final_audio_sha256"],
        "input_chunks_sha256": pause_map["input_chunks_sha256"],
        "final_audio_sha256": mix_report["output_sha256"],
        "pause_map_sha256": pause_map["pause_map_sha256"],
        "audio_mix_report_sha256": mix_report["audio_mix_report_sha256"],
        "measured_integrated_lufs": loudness["measured_integrated_lufs"],
        "measured_true_peak_dbtp": loudness["measured_true_peak_dbtp"],
        "storyboard_sha256": artifact_hashes["storyboard_sha256"],
        "video_sha256": artifact_hashes["video_sha256"],
        "qa_status": qa_report["status"],
        "qa_sha256": _sha256_file(mode_dir / "media-qa.json"),
        "shot_plan_sha256": storyboard.get("shot_plan_sha256"),
        "caption_track_sha256": storyboard.get("caption_track_sha256"),
        "caption_srt_sha256": render_report.get("caption_srt_sha256"),
        "paths": {
            "mode_dir": mode_dir.resolve().relative_to(
                artifact_root.resolve(),
            ).as_posix(),
            "video": video_path.resolve().relative_to(
                artifact_root.resolve(),
            ).as_posix(),
            "audio": audio_path.resolve().relative_to(
                artifact_root.resolve(),
            ).as_posix(),
            "media_qa": (mode_dir / "media-qa.json").resolve().relative_to(
                artifact_root.resolve(),
            ).as_posix(),
            "caption_srt": (
                str(render_report["caption_srt"])
                if render_report.get("caption_srt")
                else None
            ),
        },
    }


def build(output_dir: Path) -> dict[str, Any]:
    output_dir = Path(output_dir)
    if output_dir.exists() and any(output_dir.iterdir()):
        raise FixtureError("--output-dir must be empty")
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        raise FixtureError("ffmpeg and ffprobe are required")
    output_dir.mkdir(parents=True, exist_ok=True)

    shared = _shared_contracts()
    shared_dir = output_dir / "shared"
    assets_dir = shared_dir / "assets"
    scene_path = assets_dir / "cinematic-scene.png"
    baseline_loop = assets_dir / "baseline-loop.mp4"
    thumbnail_path = assets_dir / "thumbnail.png"
    _make_scene(scene_path)
    _make_baseline_loop(scene_path, baseline_loop)
    Image.new("RGB", (1280, 720), (24, 38, 52)).save(
        thumbnail_path,
        format="PNG",
    )
    _write_json(shared_dir / "source-snapshot.json", shared["source"])
    _write_json(shared_dir / "daily-plan.json", shared["daily_plan"])
    _write_json(shared_dir / "source-queue.json", shared["source_queue"])
    _write_json(shared_dir / "topic-review.json", shared["topic_review"])
    _write_json(shared_dir / "greenlight.json", shared["greenlight"])
    _write_json(shared_dir / "topic-playoff.json", shared["playoff"])
    _write_json(shared_dir / "base-script.json", shared["base_script"])
    shared_audio = _shared_audio_contract(shared["base_script"], output_dir)

    runs = {
        mode: _mode_run(
            output_dir,
            shared,
            shared_audio,
            visual_mode=mode,
            scene_path=scene_path,
            baseline_loop=baseline_loop,
            thumbnail_path=thumbnail_path,
        )
        for mode in MODES
    }
    baseline = runs[DEFAULT_VISUAL_MODE]
    cinematic = runs[CINEMATIC_STORY_MODE]
    invariants = {
        "same_source": True,
        "same_narration": (
            baseline["narration_sha256"] == cinematic["narration_sha256"]
        ),
        "same_narration_plan": (
            baseline["narration_plan_sha256"]
            == cinematic["narration_plan_sha256"]
        ),
        "same_raw_audio": (
            baseline["raw_audio_sha256"] == cinematic["raw_audio_sha256"]
        ),
        "same_raw_chunks": (
            baseline["input_chunks_sha256"]
            == cinematic["input_chunks_sha256"]
        ),
        "same_final_audio": (
            baseline["final_audio_sha256"]
            == cinematic["final_audio_sha256"]
        ),
        "distinct_episode_plans": (
            baseline["episode_plan_sha256"]
            != cinematic["episode_plan_sha256"]
        ),
        "both_qa_pass": all(run["qa_status"] == "PASS" for run in runs.values()),
    }
    failed_invariants = [
        name for name, passed in invariants.items() if passed is not True
    ]
    if failed_invariants:
        raise FixtureError(
            "comparison invariants failed: " + ", ".join(failed_invariants),
        )

    candidate = {
        "version": 1,
        "status": "LOCAL_TECHNICAL_PASS",
        "candidate_id": CANDIDATE_ID,
        "format": "SAGA",
        "pillar": PILLAR_ID,
        "source_id": SOURCE_ID,
        "source_body_sha256": shared["source"]["body_sha256"],
        "narration_sha256": baseline["narration_sha256"],
        "raw_audio_sha256": baseline["raw_audio_sha256"],
        "raw_chunks_sha256": baseline["input_chunks_sha256"],
        "final_audio_sha256": baseline["final_audio_sha256"],
        "runs": runs,
        "invariants": invariants,
        "network_used": False,
        "publication_authorized": False,
    }
    candidate["candidate_sha256"] = canonical_hash(candidate)
    _write_json(output_dir / "candidate.json", candidate)

    comparison = {
        "version": 1,
        "status": "BLOCKED_PENDING_HUMAN",
        "technical_status": "PASS",
        "candidate_id": CANDIDATE_ID,
        "candidate_sha256": candidate["candidate_sha256"],
        "runs": runs,
        "invariants": invariants,
        "human_review": {
            check: "PENDING_HUMAN"
            for check in (
                "first_30_seconds",
                "source_clarity",
                "screen_fatigue",
                "scene_semantics",
                "voice",
                "brand",
            )
        },
        "synthetic_fixture": True,
        "network_used": False,
        "publication_authorized": False,
    }
    comparison["comparison_sha256"] = canonical_hash(comparison)
    _write_json(output_dir / "comparison-report.json", comparison)
    return comparison


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    try:
        report = build(args.output_dir)
    except Exception as exc:
        print(f"fixture failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
