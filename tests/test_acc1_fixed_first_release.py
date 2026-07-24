import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from scripts.run_acc1_fixed_first_release import _validate_segment_plan


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/acc1_fixed_first_release.yml"


class FixedFirstReleaseTests(unittest.TestCase):
    def test_entrypoint_uses_segmented_renderer_and_baked_thumbnail_text(self):
        source = (ROOT / "scripts/run_acc1_fixed_first_release.py").read_text(encoding="utf-8")
        self.assertIn("from chrome_guided_webtoon_renderer import", source)
        self.assertIn("build_chrome_guided_segment_plan(", source)
        self.assertIn("render_chrome_guided_segment(", source)
        self.assertIn("assemble_chrome_guided_segments(", source)
        self.assertNotIn("render_chrome_guided_webtoon(", source)
        self.assertNotIn("from compilation_renderer import", source)
        self.assertNotIn("overlay_thumbnail_text", source)
        self.assertIn("СЕМЬЯ ТРЕБУЕТ ПРОСТИТЬ", source)
        self.assertIn("size=PROVIDER_LANDSCAPE_SIZE", source)
        self.assertIn("output_size=SIZE", source)
        self.assertIn("normalize_editorial_provider_image(", source)

        renderer = (ROOT / "compilation_editorial_motion_renderer.py").read_text(
            encoding="utf-8",
        )
        self.assertIn("Cinematic Webtoon v2", renderer)
        self.assertIn("_cinematic_webtoon_scene_tweens", renderer)
        self.assertIn("complete pages, never collage parts", renderer)

    def test_workflow_has_exact_spend_and_no_publish_surface(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("confirm_69_image_calls", workflow)
        self.assertIn("confirm_61_ai33_tasks", workflow)
        self.assertIn("publication_authorized", workflow)
        self.assertNotIn("REDDIT_CLIENT", workflow)
        self.assertNotIn("GEMINI", workflow)
        self.assertNotIn("OPENAI", workflow)
        self.assertNotIn("YOUTUBE_", workflow)
        self.assertNotIn("uploader.py", workflow)

    def test_workflow_requires_prepare_matrix_render_and_assembly(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("\n  prepare:\n", workflow)
        self.assertIn("\n  render:\n", workflow)
        self.assertIn("\n  assemble:\n", workflow)
        self.assertIn("--prepare-segmented", workflow)
        self.assertIn("--render-segment", workflow)
        self.assertIn("--assemble-segmented", workflow)
        self.assertIn("matrix: ${{ fromJSON(needs.prepare.outputs.matrix) }}", workflow)
        self.assertIn("max-parallel: 8", workflow)
        self.assertIn("2 <= len(indices) <= 16", workflow)
        self.assertIn("ceiling <= 120.0", workflow)
        self.assertIn("merge-multiple: true", workflow)
        self.assertIn("Assemble segments without re-encoding video", workflow)
        self.assertIn('"hyperframes_segmented_matrix"', workflow)
        self.assertNotIn("--produce", workflow)

        render_job = workflow.split("\n  render:\n", 1)[1].split("\n  assemble:\n", 1)[0]
        assemble_job = workflow.split("\n  assemble:\n", 1)[1]
        for no_spend_job in (render_job, assemble_job):
            self.assertNotIn("VECTORENGINE_API_KEY", no_spend_job)
            self.assertNotIn("AI33_API_KEY", no_spend_job)
            self.assertNotIn("YOUTUBE_", no_spend_job)

    def test_dry_run_locks_exact_provider_counts(self):
        with tempfile.TemporaryDirectory() as temp:
            subprocess.run(
                [
                    "python3", str(ROOT / "scripts/run_acc1_fixed_first_release.py"),
                    "--output-dir", temp,
                ],
                cwd=ROOT,
                check=True,
                capture_output=True,
                text=True,
            )
            report = json.loads(
                (Path(temp) / "fixed-input-preflight.json").read_text(encoding="utf-8"),
            )
        self.assertEqual(report["scene_image_calls"], 68)
        self.assertEqual(report["thumbnail_calls"], 1)
        self.assertEqual(report["image_call_cap"], 69)
        self.assertEqual(report["ai33_task_submissions"], 61)
        self.assertEqual(report["ai33_task_cap"], 61)
        self.assertEqual(report["provider_allowlist"], ["image", "ai33"])
        self.assertFalse(report["publication_authorized"])

    def test_segment_contract_accepts_nine_bounded_parts(self):
        plan = {
            "renderer": "hyperframes_segmented",
            "max_duration_sec": 120.0,
            "segments": [
                {"index": index, "duration_sec": 100.0 + index}
                for index in range(1, 10)
            ],
        }
        plan["segment_count"] = len(plan["segments"])
        self.assertEqual(_validate_segment_plan(plan), list(range(1, 10)))

    def test_segment_contract_rejects_monolithic_or_oversized_render(self):
        with self.assertRaisesRegex(RuntimeError, "bounded render segments"):
            _validate_segment_plan({
                "renderer": "hyperframes_segmented",
                "segment_count": 1,
                "max_duration_sec": 120.0,
                "segments": [{"index": 1, "duration_sec": 110.0}],
            })
        with self.assertRaisesRegex(RuntimeError, "oversized"):
            _validate_segment_plan({
                "renderer": "hyperframes_segmented",
                "segment_count": 2,
                "max_duration_sec": 120.0,
                "segments": [
                    {"index": 1, "duration_sec": 121.0},
                    {"index": 2, "duration_sec": 80.0},
                ],
            })


if __name__ == "__main__":
    unittest.main()
