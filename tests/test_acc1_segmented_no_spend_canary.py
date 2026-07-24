import unittest
from pathlib import Path

from scripts.run_acc1_segmented_no_spend_canary import (
    choose_canary_segment_ceiling,
    validate_segment_plan,
)


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/acc1_single_audio_recovery.yml"
SCRIPT = ROOT / "scripts/run_acc1_segmented_no_spend_canary.py"


class Acc1SegmentedNoSpendCanaryTests(unittest.TestCase):
    def test_dynamic_ceiling_forces_more_than_one_scene_group(self):
        ceiling = choose_canary_segment_ceiling([24.0, 26.0, 23.0, 25.0])
        self.assertGreaterEqual(ceiling, 26.0)
        self.assertLess(ceiling, sum([24.0, 26.0, 23.0, 25.0]))

    def test_plan_requires_multiple_contiguous_bounded_segments(self):
        plan = {
            "renderer": "hyperframes_segmented",
            "segment_count": 3,
            "max_duration_sec": 40.0,
            "segments": [
                {"index": 1, "duration_sec": 31.0},
                {"index": 2, "duration_sec": 35.0},
                {"index": 3, "duration_sec": 32.0},
            ],
        }
        self.assertEqual(validate_segment_plan(plan), [1, 2, 3])
        with self.assertRaisesRegex(RuntimeError, "2-4"):
            validate_segment_plan({
                **plan,
                "segment_count": 1,
                "segments": [{"index": 1, "duration_sec": 98.0}],
            })

    def test_workflow_is_a_real_no_spend_matrix(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("\n  segmented_prepare:\n", workflow)
        self.assertIn("\n  segmented_render:\n", workflow)
        self.assertIn("\n  segmented_assemble:\n", workflow)
        self.assertIn(
            "matrix: ${{ fromJSON(needs.segmented_prepare.outputs.matrix) }}",
            workflow,
        )
        self.assertIn("--render-segment", workflow)
        self.assertIn("--assemble", workflow)
        self.assertIn("2 <= len(indices) <= 4", workflow)
        self.assertIn("merge-multiple: true", workflow)
        no_spend_jobs = workflow.split("\n  segmented_prepare:\n", 1)[1]
        for forbidden in (
            "VECTORENGINE_API_KEY",
            "AI33_API_KEY",
            "A133_API_KEY",
            "YOUTUBE_",
            "confirm-image-ai33-spend",
        ):
            self.assertNotIn(forbidden, no_spend_jobs)

    def test_script_uses_the_production_segmented_facade(self):
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertIn("build_chrome_guided_segment_plan(", source)
        self.assertIn("render_chrome_guided_segment(", source)
        self.assertIn("assemble_chrome_guided_segments(", source)
        self.assertNotIn("render_chrome_guided_webtoon(", source)
        self.assertNotIn("call_image_generation", source)
        self.assertNotIn("post_tts_task", source)


if __name__ == "__main__":
    unittest.main()
