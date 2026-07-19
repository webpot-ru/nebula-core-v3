import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path

from acc1_episode_contract import canonical_hash
from acc1_visual_contract import CINEMATIC_STORY_MODE, DEFAULT_VISUAL_MODE
from scripts.build_acc1_cinematic_fixture import build


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "ffmpeg/ffprobe required")
class Acc1CinematicFixtureTests(unittest.TestCase):
    def assert_fixture(self, root: Path, report: dict) -> None:
        self.assertEqual(report["status"], "BLOCKED_PENDING_HUMAN")
        self.assertEqual(report["technical_status"], "PASS")
        self.assertFalse(report["network_used"])
        self.assertFalse(report["publication_authorized"])
        self.assertEqual(
            report["comparison_sha256"],
            canonical_hash({
                key: value
                for key, value in report.items()
                if key != "comparison_sha256"
            }),
        )

        baseline = report["runs"][DEFAULT_VISUAL_MODE]
        cinematic = report["runs"][CINEMATIC_STORY_MODE]
        self.assertNotEqual(
            baseline["episode_plan_sha256"],
            cinematic["episode_plan_sha256"],
        )
        self.assertNotEqual(
            baseline["pause_map_sha256"],
            cinematic["pause_map_sha256"],
        )
        self.assertNotEqual(
            baseline["audio_mix_report_sha256"],
            cinematic["audio_mix_report_sha256"],
        )
        for field in (
            "narration_sha256",
            "narration_plan_sha256",
            "timing_contract_sha256",
            "raw_audio_sha256",
            "input_chunks_sha256",
            "final_audio_sha256",
        ):
            self.assertEqual(baseline[field], cinematic[field], field)

        self.assertTrue(all(report["invariants"].values()))
        self.assertTrue(all(
            verdict == "PENDING_HUMAN"
            for verdict in report["human_review"].values()
        ))
        for mode, run in report["runs"].items():
            mode_dir = root / "modes" / mode
            plan = json.loads((mode_dir / "episode-plan.json").read_text())
            qa = json.loads((mode_dir / "media-qa.json").read_text())
            mix = json.loads((mode_dir / "audio-mix-report.json").read_text())
            render = json.loads((mode_dir / "render-report.json").read_text())
            self.assertEqual(plan["visual_mode"], mode)
            self.assertEqual(plan["episode_plan_sha256"], run["episode_plan_sha256"])
            self.assertEqual(qa["status"], "PASS", qa["failures"])
            self.assertEqual(run["qa_status"], "PASS")
            self.assertTrue(mix["loudness"]["integrated_loudness_pass"])
            self.assertTrue(mix["loudness"]["true_peak_pass"])
            self.assertTrue((mode_dir / "final-output.mp4").is_file())
            self.assertTrue((mode_dir / "voice-only-mix.wav").is_file())
            self.assertFalse(Path(render["output"]).is_absolute())
            self.assertTrue((root / render["output"]).is_file())
            if mode == CINEMATIC_STORY_MODE:
                self.assertFalse(Path(render["caption_srt"]).is_absolute())
                self.assertTrue((root / render["caption_srt"]).is_file())
        self.assertTrue(Path(cinematic["paths"]["caption_srt"]).suffix == ".srt")
        self.assertTrue((root / cinematic["paths"]["caption_srt"]).is_file())

        candidate = json.loads((root / "candidate.json").read_text())
        self.assertEqual(candidate["status"], "LOCAL_TECHNICAL_PASS")
        self.assertEqual(
            candidate["candidate_sha256"],
            canonical_hash({
                key: value
                for key, value in candidate.items()
                if key != "candidate_sha256"
            }),
        )

    def test_builds_one_candidate_with_canonical_pipeline_artifacts(self):
        persistent = os.environ.get("ACC1_CINEMATIC_FIXTURE_OUTPUT")
        if persistent:
            root = Path(persistent)
            report = build(root)
            self.assert_fixture(root, report)
            return
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "fixture"
            report = build(root)
            self.assert_fixture(root, report)
