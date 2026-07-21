import json
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/acc1_fixed_first_release.yml"


class FixedFirstReleaseTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
