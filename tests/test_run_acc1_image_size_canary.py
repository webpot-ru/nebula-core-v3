import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from acc1_episode_images import EpisodeImageError
from scripts.run_acc1_image_size_canary import build_preflight, run_canary


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/acc1_panel_grammar_canary.yml"


class Acc1ImageSizeCanaryTests(unittest.TestCase):
    def test_registered_workflow_has_one_call_scope_without_ai33_or_youtube(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("confirm_exactly_one_image_size_canary", workflow)
        self.assertIn("exactly one bounded paid scope must be selected", workflow)
        self.assertIn("run_acc1_image_size_canary.py", workflow)
        self.assertIn("--confirm-exactly-one-image-call", workflow)
        self.assertNotIn("AI33_API_KEY", workflow)
        self.assertNotIn("YOUTUBE_", workflow)

    def test_preflight_uses_exact_first_production_prompt_without_provider(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp)
            report, first = build_preflight(output)
            self.assertEqual(report["status"], "IMAGE_SIZE_CANARY_PREFLIGHT_PASS")
            self.assertEqual(report["provider_requested_size"], "1536x1024")
            self.assertEqual(report["required_output_size"], "1536x864")
            self.assertEqual(report["approved_image_call_cap"], 1)
            self.assertEqual(report["new_image_calls"], 0)
            self.assertEqual(report["new_ai33_calls"], 0)
            self.assertFalse(report["youtube_called"])
            self.assertIn("centered 16:9 crop-safe area", first["prompt"])

    def test_canary_makes_one_call_without_retries_and_normalizes_landscape(self):
        calls = []

        def generator(*, output_path, size, retries, **_kwargs):
            calls.append({"size": size, "retries": retries})
            Image.new("RGB", (1536, 1024), "#314159").save(output_path)
            return output_path

        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp)
            result = run_canary(output, generator=generator)
            self.assertEqual(calls, [{"size": "1536x1024", "retries": 0}])
            self.assertEqual(result["status"], "IMAGE_SIZE_CANARY_PASS")
            self.assertEqual(result["new_image_calls"], 1)
            self.assertEqual(result["final_dimensions"], [1536, 864])
            journal = json.loads(
                (output / "provider-attempts" / "image.json").read_text(encoding="utf-8"),
            )
            self.assertEqual(len(journal["attempts"]), 1)
            self.assertEqual(journal["attempts"][0]["status"], "COMPLETE")

    def test_canary_records_and_rejects_portrait_provider_response(self):
        def generator(*, output_path, **_kwargs):
            Image.new("RGB", (1023, 1537), "#314159").save(output_path)
            return output_path

        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp)
            with self.assertRaisesRegex(EpisodeImageError, "unsafe crop"):
                run_canary(output, generator=generator)
            report = json.loads(
                (output / "image-size-canary-result.json").read_text(encoding="utf-8"),
            )
            self.assertEqual(report["status"], "BLOCKED_PROVIDER_DIMENSIONS")
            self.assertEqual(report["new_image_calls"], 1)
            self.assertEqual(report["new_ai33_calls"], 0)
            self.assertFalse(report["youtube_called"])


if __name__ == "__main__":
    unittest.main()
