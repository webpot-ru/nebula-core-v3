import json
import os
import shutil
import subprocess
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from acc1_narration_profiles import (
    NARRATION_PROFILES,
    STRANGE_DARK_UNEXPLAINED_PROFILE_ID,
)
from compilation_tts_runner import CompilationTtsError, build_tts_chunks, run_compilation_tts
from compilation_storyboard import build_storyboard
from translator_tts import Ai33Error


def fake_probe_duration(_path: Path) -> float:
    return 1.0


def sample_compilation(body: str = "Первое предложение. Второе предложение."):
    disclosure = "Это художественная история с Reddit."
    return {
        "episode_plan_sha256": "1" * 64,
        "daily_plan_sha256": "2" * 64,
        "publication_authorized": False,
        "truth_disclosure_ru": disclosure,
        "intro_ru": f"Начало выпуска. {disclosure}",
        "stories": [{
            "source_snapshot": {"post_id": "abc", "truth_mode": "fiction"},
            "narration_ru": body,
            "narration_role": "narrator",
        }],
        "outro_ru": "Конец выпуска.",
    }


def sample_role_compilation():
    compilation = sample_compilation()
    compilation["stories"].append({
        "source_snapshot": {"post_id": "reply", "truth_mode": "fiction"},
        "narration_ru": "Короткий ответ пользователя.",
        "narration_role": "comment",
    })
    compilation["stories"][0]["transition_after_ru"] = "Теперь ответ пользователя."
    disclosure = "Это художественные истории с Reddit."
    compilation["truth_disclosure_ru"] = disclosure
    compilation["intro_ru"] = f"Начало выпуска. {disclosure}"
    return compilation


class CompilationTtsRunnerTests(unittest.TestCase):
    def test_always_chunks_single_narrator_in_order(self):
        body = " ".join(["Длинное предложение."] * 100)
        chunks = build_tts_chunks(sample_compilation(body), voice_id="voice", max_chars=500)
        ids = [item["chunk_id"] for item in chunks]
        self.assertEqual(ids[0], "intro__001")
        self.assertGreater(len([value for value in ids if value.startswith("story_abc__")]), 1)
        self.assertEqual(ids[-1], "outro__001")

    def test_model_and_request_checksum_are_fail_closed(self):
        with self.assertRaisesRegex(CompilationTtsError, "required model"):
            build_tts_chunks(sample_compilation(), voice_id="voice", model_id="eleven_v2")
        first = build_tts_chunks(sample_compilation(), voice_id="voice")[0]["request_sha256"]
        changed = build_tts_chunks(sample_compilation(), voice_id="other")[0]["request_sha256"]
        self.assertNotEqual(first, changed)

    def test_pronunciation_dictionary_is_hash_bound_and_forwarded(self):
        digest = "a" * 64
        first = build_tts_chunks(
            sample_compilation(), voice_id="voice",
            pronunciation_dictionary_id=17,
            pronunciation_dictionary_sha256=digest,
        )[0]
        self.assertEqual(first["pronunciation_dictionary_id"], 17)
        with self.assertRaisesRegex(CompilationTtsError, "supplied together"):
            build_tts_chunks(
                sample_compilation(), voice_id="voice",
                pronunciation_dictionary_id=17,
            )

    def test_comment_role_requires_distinct_voice_and_is_routed(self):
        compilation = sample_role_compilation()
        with self.assertRaisesRegex(CompilationTtsError, "comment_voice_id is required"):
            build_tts_chunks(compilation, voice_id="narrator")
        with self.assertRaisesRegex(CompilationTtsError, "must not fall back"):
            build_tts_chunks(
                compilation, voice_id="same", comment_voice_id="same",
            )
        chunks = build_tts_chunks(
            compilation, voice_id="narrator", comment_voice_id="comment",
        )
        story_voices = {
            item["logical_segment_id"]: (item["voice_role"], item["voice_id"])
            for item in chunks if item["logical_segment_id"].startswith("story_")
        }
        self.assertEqual(story_voices["story_abc"], ("narrator", "narrator"))
        self.assertEqual(story_voices["story_reply"], ("comment", "comment"))
        self.assertTrue(all(item["episode_plan_sha256"] == "1" * 64 for item in chunks))

    def test_task_id_is_saved_before_poll_and_resume_is_poll_only(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            posts = []
            polls = []
            expected_chunks = len(build_tts_chunks(sample_compilation(), voice_id="voice"))

            def post(**kwargs):
                posts.append(kwargs["file_name"])
                return {"success": True, "task_id": f"task-{len(posts)}", "model_id": "eleven_v3"}

            def interrupting_poll(**kwargs):
                saved = json.loads((root / "compilation_tts_state.json").read_text())
                self.assertEqual(len(posts), expected_chunks)
                self.assertTrue(all(item["status"] == "SUBMITTED" for item in saved["chunks"]))
                self.assertTrue(all(item.get("task_id") for item in saved["chunks"]))
                current = next(item for item in saved["chunks"] if item["task_id"] == kwargs["task_id"])
                self.assertEqual(current["status"], "SUBMITTED")
                raise RuntimeError("interrupted")

            with self.assertRaisesRegex(CompilationTtsError, "interrupted"):
                run_compilation_tts(
                    sample_compilation(), output_dir=root, api_key="secret",
                    voice_id="voice", post_task=post, poll_task=interrupting_poll,
                    poll_concurrency=2,
                )
            self.assertEqual(len(posts), expected_chunks)

            def resume_post(**kwargs):
                self.fail(f"saved task must not be resubmitted: {kwargs['file_name']}")

            def poll(**kwargs):
                polls.append(kwargs["task_id"])
                kwargs["output_path"].write_bytes(b"audio-" + kwargs["task_id"].encode())
                return {"success": True, "model_id": "eleven_v3"}

            def concat(paths, output):
                output.write_bytes(b"|".join(path.read_bytes() for path in paths))

            state = run_compilation_tts(
                sample_compilation(), output_dir=root, api_key="secret", voice_id="voice",
                post_task=resume_post, poll_task=poll, concat=concat,
                probe_duration=fake_probe_duration, poll_concurrency=2,
            )
            self.assertEqual(set(polls), {f"task-{index}" for index in range(1, expected_chunks + 1)})
            self.assertEqual(state["status"], "COMPLETE")

    def test_submit_transport_ambiguity_is_durable_and_never_reposted(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            attempts = []

            def ambiguous_post(**kwargs):
                attempts.append(kwargs["file_name"])
                raise RuntimeError("connection closed after request body")

            with self.assertRaisesRegex(RuntimeError, "connection closed"):
                run_compilation_tts(
                    sample_compilation(), output_dir=root, api_key="secret",
                    voice_id="voice", post_task=ambiguous_post,
                )
            saved = json.loads((root / "compilation_tts_state.json").read_text())
            self.assertEqual(saved["chunks"][0]["status"], "SUBMITTING")
            self.assertEqual(len(attempts), 1)

            with self.assertRaisesRegex(CompilationTtsError, "ambiguous prior submit"):
                run_compilation_tts(
                    sample_compilation(), output_dir=root, api_key="secret",
                    voice_id="voice",
                    post_task=lambda **_: self.fail(
                        "ambiguous submission must not be repeated"
                    ),
                )
            self.assertEqual(len(attempts), 1)

    def test_duplicate_provider_task_id_blocks_before_any_poll(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            polls = []

            def post(**kwargs):
                return {
                    "success": True,
                    "task_id": "same-provider-task",
                    "model_id": "eleven_v3",
                }

            with self.assertRaisesRegex(CompilationTtsError, "duplicate task_id"):
                run_compilation_tts(
                    sample_compilation(), output_dir=root, api_key="secret",
                    voice_id="voice", post_task=post,
                    poll_task=lambda **kwargs: polls.append(kwargs),
                )

            saved = json.loads((root / "compilation_tts_state.json").read_text())
        self.assertEqual(polls, [])
        self.assertEqual(saved["chunks"][0]["status"], "SUBMITTED")
        self.assertEqual(saved["chunks"][1]["status"], "SUBMITTING")

    def test_all_chunks_submit_before_bounded_parallel_polling(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            events = []
            timeouts = []
            lock = threading.Lock()
            first_wave = threading.Barrier(2)
            active = 0
            maximum_active = 0

            def post(**kwargs):
                events.append(("post", kwargs["file_name"]))
                return {
                    "success": True,
                    "task_id": f"task-{len(events)}",
                    "model_id": "eleven_v3",
                }

            def poll(**kwargs):
                nonlocal active, maximum_active
                with lock:
                    active += 1
                    maximum_active = max(maximum_active, active)
                    ordinal = len(timeouts) + 1
                    timeouts.append(kwargs["timeout_seconds"])
                    events.append(("poll", kwargs["task_id"]))
                if ordinal <= 2:
                    first_wave.wait(timeout=1)
                time.sleep(0.02)
                kwargs["output_path"].write_bytes(kwargs["task_id"].encode())
                with lock:
                    active -= 1
                return {"success": True, "model_id": "eleven_v3"}

            def concat(paths, output):
                output.write_bytes(b"|".join(path.read_bytes() for path in paths))

            state = run_compilation_tts(
                sample_compilation(), output_dir=root, api_key="secret",
                voice_id="voice", post_task=post, poll_task=poll, concat=concat,
                probe_duration=fake_probe_duration, poll_concurrency=2,
                overall_timeout_seconds=9,
            )

        event_kinds = [kind for kind, _ in events]
        self.assertLess(max(index for index, kind in enumerate(event_kinds) if kind == "post"),
                        min(index for index, kind in enumerate(event_kinds) if kind == "poll"))
        self.assertEqual(maximum_active, 2)
        self.assertTrue(all(1 <= value <= 9 for value in timeouts))
        self.assertEqual(state["status"], "COMPLETE")

    def test_env_absolute_deadline_is_shared_by_all_saved_task_polls(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            received_timeouts = []

            def post(**kwargs):
                return {
                    "success": True,
                    "task_id": kwargs["file_name"],
                    "model_id": "eleven_v3",
                }

            def poll(**kwargs):
                received_timeouts.append(kwargs["timeout_seconds"])
                kwargs["output_path"].write_bytes(b"audio")
                return {"success": True, "model_id": "eleven_v3"}

            def concat(paths, output):
                output.write_bytes(b"final")

            with patch.dict(os.environ, {"AI33_TTS_DEADLINE_EPOCH": "1006"}):
                state = run_compilation_tts(
                    sample_compilation(), output_dir=root, api_key="secret",
                    voice_id="voice", post_task=post, poll_task=poll, concat=concat,
                    probe_duration=fake_probe_duration,
                    monotonic=lambda: 50.0, wall_clock=lambda: 1000.0,
                )

        self.assertTrue(received_timeouts)
        self.assertTrue(all(value == 6 for value in received_timeouts))
        self.assertEqual(state["status"], "COMPLETE")

    def test_retry_backoff_cannot_reset_the_shared_deadline(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            clock = [100.0]
            posts = []
            received_timeouts = []

            def post(**kwargs):
                posts.append(kwargs["file_name"])
                return {
                    "success": True,
                    "task_id": f"task-{len(posts)}",
                    "model_id": "eleven_v3",
                }

            def poll(**kwargs):
                received_timeouts.append(kwargs["timeout_seconds"])
                raise Ai33Error('AI33 task polling failed (500): {"retryable":true}')

            def sleep_and_advance(seconds):
                clock[0] += seconds

            with self.assertRaisesRegex(CompilationTtsError, "deadline expired"):
                run_compilation_tts(
                    sample_compilation(), output_dir=root, api_key="secret",
                    voice_id="voice", post_task=post, poll_task=poll,
                    poll_concurrency=1, overall_timeout_seconds=6,
                    monotonic=lambda: clock[0], sleeper=sleep_and_advance,
                )

            saved = json.loads((root / "compilation_tts_state.json").read_text())
        self.assertEqual(len(posts), len(saved["chunks"]))
        self.assertTrue(all(item["status"] == "SUBMITTED" for item in saved["chunks"]))
        self.assertEqual(received_timeouts[:2], [6, 1])

    def test_completed_chunks_are_reused_and_concat_order_is_stable(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            posted = []
            concat_orders = []

            def post(**kwargs):
                posted.append(kwargs["file_name"])
                kwargs_path = root / "segments" / kwargs["file_name"]
                return {"success": True, "audio_bytes": b"x", "model_id": "eleven_v3", "_path": str(kwargs_path)}

            def write(payload, path, api_key):
                path.write_bytes(path.name.encode())
                return True

            def concat(paths, output):
                concat_orders.append([path.name for path in paths])
                output.write_bytes(b"final")

            first = run_compilation_tts(
                sample_compilation(), output_dir=root, api_key="secret", voice_id="voice",
                post_task=post, write_payload=write, concat=concat,
                probe_duration=fake_probe_duration,
            )
            post_count = len(posted)

            def no_post(**kwargs):
                self.fail("completed chunks must be reused")

            second = run_compilation_tts(
                sample_compilation(), output_dir=root, api_key="secret", voice_id="voice",
                post_task=no_post, write_payload=write, concat=concat,
                probe_duration=fake_probe_duration,
            )
            self.assertEqual(len(posted), post_count)
            self.assertEqual(concat_orders[0], concat_orders[1])
            self.assertEqual(first["final_audio_sha256"], second["final_audio_sha256"])
            self.assertEqual(second["timing_contract_version"], 1)
            self.assertEqual(second["final_audio_duration_sec"], 1.0)
            self.assertEqual(second["final_audio_path"], "compilation_narration.mp3")
            self.assertTrue(all(
                not Path(item["audio_path"]).is_absolute()
                for item in second["chunks"]
            ))
            self.assertTrue(all(item["word_timings"] for item in second["chunks"]))
            self.assertTrue(all(
                item["timing_source"] == "estimated_from_audio_duration"
                for item in second["chunks"]
            ))
            saved_path = root / "compilation_tts_state.json"
            saved = json.loads(saved_path.read_text(encoding="utf-8"))
            saved["chunks"][0]["word_timings"][0]["end"] += 0.1
            saved_path.write_text(json.dumps(saved), encoding="utf-8")
            with self.assertRaisesRegex(CompilationTtsError, "word timing checksum"):
                run_compilation_tts(
                    sample_compilation(), output_dir=root, api_key="secret",
                    voice_id="voice", post_task=no_post, write_payload=write,
                    concat=concat, probe_duration=fake_probe_duration,
                )

    def test_embedded_ai33_word_alignment_is_preserved_and_bound(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)

            def post(**kwargs):
                tokens = kwargs["text"].split()
                return {
                    "success": True,
                    "model_id": "eleven_v3",
                    "words": [
                        {"word": token.rstrip(".!?,"), "start": index, "end": index + 0.8}
                        for index, token in enumerate(tokens)
                    ],
                }

            def write(payload, path, api_key):
                path.write_bytes(b"audio")
                return True

            def concat(paths, output):
                output.write_bytes(b"final")

            state = run_compilation_tts(
                sample_compilation(), output_dir=root, api_key="secret", voice_id="voice",
                post_task=post, write_payload=write, concat=concat,
                probe_duration=lambda path: 20.0 if path.name != "compilation_narration.mp3" else 60.0,
            )

        self.assertTrue(all(item["timing_source"] == "ai33" for item in state["chunks"]))
        self.assertRegex(state["timing_contract_sha256"], r"^[0-9a-f]{64}$")
        self.assertEqual(state["raw_chunk_duration_sec"], 60.0)
        self.assertEqual(state["timeline_scale"], 1.0)

    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "ffmpeg required")
    def test_real_ffprobe_durations_drive_complete_storyboard_timeline(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            tone = root / "tone.mp3"
            subprocess.run([
                "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                "-f", "lavfi", "-i", "sine=frequency=440:duration=1.2",
                "-c:a", "libmp3lame", str(tone),
            ], check=True)

            def post(**kwargs):
                return {"success": True, "model_id": "eleven_v3"}

            def write(payload, path, api_key):
                path.write_bytes(tone.read_bytes())
                return True

            compilation = sample_compilation()
            state = run_compilation_tts(
                compilation, output_dir=root, api_key="secret", voice_id="voice",
                post_task=post, write_payload=write,
            )
            storyboard = build_storyboard(compilation, root, tts_state=state)

        self.assertAlmostEqual(
            storyboard["timeline_duration_sec"], state["final_audio_duration_sec"], places=3,
        )
        self.assertEqual(storyboard["creative_manifest"]["audio_timing_coverage"], 1.0)
        self.assertEqual(
            storyboard["creative_manifest"]["timing_sources"],
            ["actual_audio_duration_estimate"],
        )

    def test_retryable_poll_500_retries_same_saved_task_without_resubmit(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            posts = []
            polls = []
            sleeps = []
            def post(**kwargs):
                posts.append(kwargs["file_name"])
                return {"task_id": f"task-{len(posts)}", "model_id": "eleven_v3"}
            def poll(**kwargs):
                polls.append(kwargs["task_id"])
                if len(polls) == 1:
                    raise Ai33Error('AI33 task polling failed (500): {"retryable":true}')
                kwargs["output_path"].write_bytes(b"audio")
                return {"success": True, "model_id": "eleven_v3"}
            def concat(paths, output):
                output.write_bytes(b"final")
            state = run_compilation_tts(sample_compilation(), output_dir=root, api_key="secret",
                voice_id="voice", post_task=post, poll_task=poll, concat=concat,
                sleeper=sleeps.append, probe_duration=fake_probe_duration,
                poll_concurrency=1)
        self.assertEqual(polls[:2], ["task-1", "task-1"])
        self.assertEqual(len(posts), len(state["chunks"]))
        self.assertEqual(sleeps, [5])

    def test_retryable_poll_429_retries_same_saved_task_without_resubmit(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            posts = []
            polls = []
            sleeps = []
            def post(**kwargs):
                posts.append(kwargs["file_name"])
                return {"task_id": f"task-{len(posts)}", "model_id": "eleven_v3"}
            def poll(**kwargs):
                polls.append(kwargs["task_id"])
                if len(polls) == 1:
                    raise Ai33Error(
                        'AI33 task polling failed (429): '
                        '{"success":false,"message":"Task polling temporarily busy"}'
                    )
                kwargs["output_path"].write_bytes(b"audio")
                return {"success": True, "model_id": "eleven_v3"}
            def concat(paths, output):
                output.write_bytes(b"final")
            state = run_compilation_tts(
                sample_compilation(), output_dir=root, api_key="secret",
                voice_id="voice", post_task=post, poll_task=poll, concat=concat,
                sleeper=sleeps.append, probe_duration=fake_probe_duration,
                poll_concurrency=1,
            )
        self.assertEqual(polls[:2], ["task-1", "task-1"])
        self.assertEqual(len(posts), len(state["chunks"]))
        self.assertEqual(sleeps, [5])

    def test_ambiguous_or_changed_state_never_submits(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            chunks = build_tts_chunks(sample_compilation(), voice_id="voice")
            state = {
                "version": 3,
                "required_model_id": "eleven_v3",
                "episode_plan_sha256": "1" * 64,
                "daily_plan_sha256": "2" * 64,
                "plan_sha256": "wrong",
                "narration_plan_sha256": "wrong",
                "chunks": chunks,
                "status": "IN_PROGRESS",
                "publication_authorized": False,
            }
            (root / "compilation_tts_state.json").write_text(json.dumps(state), encoding="utf-8")
            with self.assertRaisesRegex(CompilationTtsError, "plan changed"):
                run_compilation_tts(sample_compilation(), output_dir=root, api_key="secret", voice_id="voice", post_task=lambda **_: self.fail("must not post"))

    def test_reported_model_mismatch_blocks_completion(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)

            def post(**kwargs):
                return {"success": True, "audio_bytes": b"x", "model_id": "eleven_v2"}

            def write(payload, path, api_key):
                path.write_bytes(b"audio")
                return True

            with self.assertRaisesRegex(CompilationTtsError, "unexpected model"):
                run_compilation_tts(sample_compilation(), output_dir=root, api_key="secret", voice_id="voice", post_task=post, write_payload=write)

    def test_profile_chunks_persist_effective_contract_and_semantic_boundaries(self):
        compilation = sample_compilation(
            "Первый смысловой абзац.\n\nВторой смысловой абзац.",
        )
        compilation["pillar"] = "strange_dark_unexplained"
        compilation["narration_profile_id"] = STRANGE_DARK_UNEXPLAINED_PROFILE_ID
        compilation["stories"][0]["story_beats"] = [
            "Первый смысловой абзац.",
            "Второй смысловой абзац.",
        ]
        chunks = build_tts_chunks(
            compilation,
            voice_id="voice",
            narration_profile_id=STRANGE_DARK_UNEXPLAINED_PROFILE_ID,
        )
        self.assertEqual(
            chunks,
            build_tts_chunks(compilation, voice_id="voice"),
        )
        story_chunks = [
            item for item in chunks
            if item["logical_segment_id"] == "story_abc"
        ]
        profile = NARRATION_PROFILES[STRANGE_DARK_UNEXPLAINED_PROFILE_ID]
        self.assertEqual(
            [item["text"] for item in story_chunks],
            ["Первый смысловой абзац.", "Второй смысловой абзац."],
        )
        self.assertTrue(all(item["is_last_in_beat"] for item in story_chunks))
        self.assertFalse(story_chunks[0]["is_last_in_segment"])
        self.assertTrue(story_chunks[1]["is_last_in_segment"])
        self.assertTrue(all(
            item["narration_profile_sha256"] == profile["profile_sha256"]
            for item in chunks
        ))
        self.assertTrue(all(
            item["effective_speed"] == profile["speed"]
            and item["effective_voice_settings_json"] == profile["voice_settings_json"]
            and item["effective_with_transcript"] is True
            and item["effective_context_chaining"] is False
            for item in chunks
        ))
        legacy = build_tts_chunks(
            sample_compilation(), voice_id="voice",
        )
        self.assertTrue(all("narration_profile_id" not in item for item in legacy))

    def test_profile_run_uses_effective_provider_values_and_writes_pause_map(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            compilation = sample_compilation()
            compilation["pillar"] = "strange_dark_unexplained"
            posted = []

            def post(**kwargs):
                posted.append(kwargs)
                return {
                    "success": True,
                    "audio_bytes": b"x",
                    "model_id": "eleven_v3",
                }

            def write(_payload, path, _api_key):
                path.write_bytes(path.name.encode())
                return True

            def concat(_paths, output):
                output.write_bytes(b"final")

            state = run_compilation_tts(
                compilation,
                output_dir=root,
                api_key="secret",
                voice_id="voice",
                narration_profile_id=STRANGE_DARK_UNEXPLAINED_PROFILE_ID,
                post_task=post,
                write_payload=write,
                concat=concat,
                probe_duration=fake_probe_duration,
            )
            pause_map = json.loads(
                (root / "narration-pause-map.json").read_text(encoding="utf-8"),
            )

        profile = NARRATION_PROFILES[STRANGE_DARK_UNEXPLAINED_PROFILE_ID]
        self.assertTrue(posted)
        self.assertTrue(all(item["speed"] == profile["speed"] for item in posted))
        self.assertTrue(all(
            item["voice_settings_json"] == profile["voice_settings_json"]
            for item in posted
        ))
        self.assertEqual(state["pause_map_sha256"], pause_map["pause_map_sha256"])
        self.assertEqual(state["narration_profile_sha256"], profile["profile_sha256"])
        self.assertRegex(state["narration_plan_sha256"], r"^[0-9a-f]{64}$")

    def test_profile_request_overrides_fail_closed(self):
        compilation = sample_compilation()
        compilation["pillar"] = "strange_dark_unexplained"
        with self.assertRaisesRegex(CompilationTtsError, "speed override conflicts"):
            build_tts_chunks(
                compilation,
                voice_id="voice",
                narration_profile_id=STRANGE_DARK_UNEXPLAINED_PROFILE_ID,
                speed=1.2,
            )
        with self.assertRaisesRegex(
            CompilationTtsError, "voice_settings_json conflicts",
        ):
            build_tts_chunks(
                compilation,
                voice_id="voice",
                narration_profile_id=STRANGE_DARK_UNEXPLAINED_PROFILE_ID,
                voice_settings_json='{"stability":0.1}',
            )


if __name__ == "__main__":
    unittest.main()
