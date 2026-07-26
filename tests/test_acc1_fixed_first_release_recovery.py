import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from acc1_pronunciation_dictionary import load_acc1_pronunciation_dictionary
from scripts.recover_acc1_fixed_first_release import (
    RecoveryError,
    _restore_intro_contract,
    validate_recovery_artifact,
)
from scripts.run_acc1_fixed_first_release import FIXED_COLD_OPEN_RU, STORY_CONFIG


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/acc1_fixed_first_release_recovery.yml"


class FixedFirstReleaseRecoveryTests(unittest.TestCase):
    @staticmethod
    def _fixed_script() -> dict:
        disclosure = "Это пересказ личных историй пользователей Reddit."
        return {
            "intro_ru": f"{FIXED_COLD_OPEN_RU} {disclosure}",
            "truth_disclosure_ru": disclosure,
            "stories": [{
                "title_ru": STORY_CONFIG[0]["title"],
                "source_snapshot": {
                    "source_id": STORY_CONFIG[0]["post_id"],
                    "title": STORY_CONFIG[0]["title"],
                },
            }],
        }

    def _fixture(self, root: Path, *, submitted_count: int = 1) -> None:
        (root / "provider-attempts").mkdir(parents=True)
        (root / "tts/segments").mkdir(parents=True)
        (root / "scene-images").mkdir()
        (root / "episode-script.json").write_text("{}", encoding="utf-8")
        (root / "youtube-thumbnail.png").write_bytes(b"png")
        for label, cap in (("image", 69), ("ai33", 61)):
            (root / f"provider-attempts/{label}.json").write_text(json.dumps({
                "provider": label, "cap": cap,
                "attempts": [{"status": "COMPLETE"}] * cap,
            }), encoding="utf-8")
        dictionary_sha256 = load_acc1_pronunciation_dictionary()["sha256"]
        complete_count = 61 - submitted_count
        chunks = []
        for index in range(complete_count):
            chunk_id = f"chunk-{index:03d}"
            audio = root / "tts/segments" / f"{chunk_id}.mp3"
            audio.write_bytes(f"audio-{index}".encode("utf-8"))
            chunks.append({
                "chunk_id": chunk_id,
                "status": "COMPLETE",
                "audio_sha256": hashlib.sha256(audio.read_bytes()).hexdigest(),
                "pronunciation_dictionary_id": 17,
                "pronunciation_dictionary_sha256": dictionary_sha256,
            })
        for index in range(submitted_count):
            chunks.append({
                "chunk_id": f"submitted-{index:03d}",
                "status": "SUBMITTED",
                "task_id": f"saved-task-{index}",
                "pronunciation_dictionary_id": 17,
                "pronunciation_dictionary_sha256": dictionary_sha256,
            })
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
        self.assertEqual(report["completed_audio_reused"], 60)
        self.assertEqual(report["existing_tasks_to_poll"], 1)
        self.assertEqual(report["new_image_calls_authorized"], 0)
        self.assertEqual(report["new_ai33_submissions_authorized"], 0)
        self.assertFalse(report["youtube_called"])

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

    def test_multiple_saved_tasks_are_safe_to_poll_without_resubmission(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self._fixture(root, submitted_count=9)
            report = validate_recovery_artifact(root)
        self.assertEqual(report["completed_audio_reused"], 52)
        self.assertEqual(report["existing_tasks_to_poll"], 9)
        self.assertEqual(len(report["existing_task_ids_sha256"]), 64)

    def test_duplicate_saved_task_id_blocks_recovery(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self._fixture(root, submitted_count=2)
            state_path = root / "tts/compilation_tts_state.json"
            state = json.loads(state_path.read_text(encoding="utf-8"))
            state["chunks"][-1]["task_id"] = state["chunks"][-2]["task_id"]
            state_path.write_text(json.dumps(state), encoding="utf-8")
            with self.assertRaisesRegex(RecoveryError, "duplicate"):
                validate_recovery_artifact(root)

    def test_restores_exact_source_bound_intro_without_changing_spoken_text(self):
        script = self._fixed_script()
        spoken = script["intro_ru"]

        self.assertTrue(_restore_intro_contract(script))
        self.assertEqual(script["intro_ru"], spoken)
        self.assertEqual(
            script["intro_contract"]["cold_open"],
            {
                "text": FIXED_COLD_OPEN_RU,
                "source_id": STORY_CONFIG[0]["post_id"],
                "source_quote": STORY_CONFIG[0]["title"],
            },
        )
        self.assertFalse(_restore_intro_contract(script))

    def test_intro_recovery_rejects_spoken_text_drift(self):
        script = self._fixed_script()
        script["intro_ru"] += " Новые неподтверждённые слова."
        with self.assertRaisesRegex(RecoveryError, "frozen cold open"):
            _restore_intro_contract(script)

    def test_registered_workflow_is_segmented_and_has_no_submission_secret(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn('default: "30102591330"', workflow)
        self.assertIn("acc1-fixed-first-release-source-30102591330", workflow)
        self.assertIn("--prepare-segmented", workflow)
        self.assertIn("--render-segment", workflow)
        self.assertIn("--assemble-segmented", workflow)
        self.assertIn("max-parallel: 8", workflow)
        self.assertIn("2 <= len(indices) <= 16", workflow)
        self.assertIn("new_image_calls\"] == 0", workflow)
        self.assertIn("new_ai33_task_submissions\"] == 0", workflow)
        self.assertEqual(workflow.count('intro_contract_restored"] is True'), 2)
        self.assertNotIn("VECTORENGINE_API_KEY", workflow)
        self.assertNotIn("YOUTUBE_", workflow)
        self.assertEqual(workflow.count("secrets.AI33_API_KEY"), 1)


if __name__ == "__main__":
    unittest.main()
