import json
import tempfile
import unittest
from pathlib import Path

from scripts.recover_acc1_fixed_first_release import RecoveryError, validate_recovery_artifact


class FixedFirstReleaseRecoveryTests(unittest.TestCase):
    def _fixture(self, root: Path) -> None:
        (root / "provider-attempts").mkdir(parents=True)
        (root / "tts").mkdir()
        (root / "scene-images").mkdir()
        (root / "episode-script.json").write_text("{}", encoding="utf-8")
        (root / "youtube-thumbnail.png").write_bytes(b"png")
        for label, cap in (("image", 69), ("ai33", 61)):
            (root / f"provider-attempts/{label}.json").write_text(json.dumps({
                "provider": label, "cap": cap,
                "attempts": [{"status": "COMPLETE"}] * cap,
            }), encoding="utf-8")
        chunks = [{"status": "COMPLETE"}] * 60 + [{"status": "SUBMITTED", "task_id": "saved-task"}]
        (root / "tts/compilation_tts_state.json").write_text(
            json.dumps({"chunks": chunks}), encoding="utf-8",
        )
        for story, post, count in ((1, "1uw7804", 9), (2, "1v0l1ei", 9), (3, "1uy2j23", 8), (4, "1uviexk", 8)):
            for scene in range(1, count + 1):
                for role in ("hero_plate", "detail_plate"):
                    (root / "scene-images" / f"story-{story:02d}-{post}-scene-{scene:03d}-{role}.png").write_bytes(b"png")

    def test_exact_saved_state_passes_without_provider_calls(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self._fixture(root)
            report = validate_recovery_artifact(root)
        self.assertEqual(report["image_calls_reused"], 69)
        self.assertEqual(report["ai33_tasks_reused"], 61)
        self.assertEqual(report["new_image_calls_authorized"], 0)
        self.assertEqual(report["new_ai33_submissions_authorized"], 0)

    def test_any_ready_chunk_blocks_recovery(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self._fixture(root)
            state_path = root / "tts/compilation_tts_state.json"
            state = json.loads(state_path.read_text(encoding="utf-8"))
            state["chunks"][-1] = {"status": "READY"}
            state_path.write_text(json.dumps(state), encoding="utf-8")
            with self.assertRaises(RecoveryError):
                validate_recovery_artifact(root)


if __name__ == "__main__":
    unittest.main()
