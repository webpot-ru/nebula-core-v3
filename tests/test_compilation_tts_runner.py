import json
import tempfile
import unittest
from pathlib import Path

from compilation_tts_runner import CompilationTtsError, build_tts_chunks, run_compilation_tts


def sample_compilation(body: str = "Первое предложение. Второе предложение."):
    return {
        "intro_ru": "Начало выпуска.",
        "stories": [{
            "source_snapshot": {"post_id": "abc"},
            "narration_ru": body,
        }],
        "outro_ru": "Конец выпуска.",
    }


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

    def test_task_id_is_saved_before_poll_and_resume_is_poll_only(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            posts = []
            polls = []

            def post(**kwargs):
                posts.append(kwargs["file_name"])
                return {"success": True, "task_id": f"task-{len(posts)}", "model_id": "eleven_v3"}

            def interrupting_poll(**kwargs):
                saved = json.loads((root / "compilation_tts_state.json").read_text())
                current = next(item for item in saved["chunks"] if item["task_id"] == kwargs["task_id"])
                self.assertEqual(current["status"], "SUBMITTED")
                raise RuntimeError("interrupted")

            with self.assertRaisesRegex(RuntimeError, "interrupted"):
                run_compilation_tts(sample_compilation(), output_dir=root, api_key="secret", voice_id="voice", post_task=post, poll_task=interrupting_poll)
            self.assertEqual(len(posts), 1)

            resumed_posts = []

            def resume_post(**kwargs):
                self.assertNotEqual(kwargs["file_name"], posts[0], "saved first task must not be resubmitted")
                resumed_posts.append(kwargs["file_name"])
                return {"success": True, "task_id": f"resume-{len(resumed_posts)}", "model_id": "eleven_v3"}

            def poll(**kwargs):
                polls.append(kwargs["task_id"])
                kwargs["output_path"].write_bytes(b"audio-" + kwargs["task_id"].encode())
                return {"success": True, "model_id": "eleven_v3"}

            def concat(paths, output):
                output.write_bytes(b"|".join(path.read_bytes() for path in paths))

            state = run_compilation_tts(sample_compilation(), output_dir=root, api_key="secret", voice_id="voice", post_task=resume_post, poll_task=poll, concat=concat)
            self.assertEqual(polls[0], "task-1")
            self.assertEqual(state["status"], "COMPLETE")

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

            first = run_compilation_tts(sample_compilation(), output_dir=root, api_key="secret", voice_id="voice", post_task=post, write_payload=write, concat=concat)
            post_count = len(posted)

            def no_post(**kwargs):
                self.fail("completed chunks must be reused")

            second = run_compilation_tts(sample_compilation(), output_dir=root, api_key="secret", voice_id="voice", post_task=no_post, write_payload=write, concat=concat)
            self.assertEqual(len(posted), post_count)
            self.assertEqual(concat_orders[0], concat_orders[1])
            self.assertEqual(first["final_audio_sha256"], second["final_audio_sha256"])

    def test_ambiguous_or_changed_state_never_submits(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            chunks = build_tts_chunks(sample_compilation(), voice_id="voice")
            state = {
                "version": 1,
                "required_model_id": "eleven_v3",
                "plan_sha256": "wrong",
                "chunks": chunks,
                "status": "IN_PROGRESS",
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


if __name__ == "__main__":
    unittest.main()
