import json
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "specs/acc1-video-style-v2.json"
VALIDATOR = ROOT / "scripts/validate_acc1_video_style_v2.py"


class Acc1VideoStyleV2Tests(unittest.TestCase):
    def test_contract_locks_comic_subtitle_and_brand_rules(self):
        contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
        self.assertEqual(contract["style_id"], "chonker_cinematic_webtoon_v2")
        self.assertEqual(contract["renderer"]["required_id"], "chrome_guided_webtoon_v2")
        self.assertEqual(
            contract["renderer"]["production_render_strategy"],
            "bounded_segments_then_assembly",
        )
        self.assertEqual(
            contract["renderer"]["canary_render_strategy"],
            "hyperframes_segmented_matrix",
        )
        self.assertEqual(contract["renderer"]["canary_segment_count_min"], 2)
        self.assertEqual(contract["renderer"]["canary_segment_count_max"], 5)
        self.assertEqual(
            contract["renderer"]["canary_frozen_media"],
            {
                "pages": {
                    "run_id": "30063115374",
                    "artifact": "acc1-panel-grammar-canary-30063115374",
                    "page_count": 5,
                },
                "audio": {
                    "run_id": "29975009888",
                    "artifact": "acc1-format-v3-canary-29975009888",
                },
            },
        )
        self.assertEqual(contract["renderer"]["segment_max_duration_sec"], 120)
        self.assertEqual(contract["renderer"]["matrix_max_parallel"], 4)
        self.assertIn(
            "render_chrome_guided_webtoon(",
            contract["renderer"]["forbidden_imports"],
        )
        self.assertEqual(contract["subtitles"]["line_count"], 1)
        self.assertEqual(contract["subtitles"]["vertical_alignment"], "center")
        self.assertEqual(contract["subtitles"]["band"]["height"], 130)
        self.assertEqual(
            contract["subtitles"]["visibility_during_brand_inserts"],
            {
                "intro": "visible",
                "subscribe_cta": "visible",
                "outro": "visible",
            },
        )
        self.assertEqual(contract["thumbnail"]["text_mode"], "imagen_baked_in")
        self.assertFalse(contract["approval_gate"]["provider_calls_before_approval"])
        self.assertEqual(set(contract["brand_inserts"]), {"intro", "subscribe_cta", "outro"})

    def test_approved_production_contract_is_ready(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "report.json"
            completed = subprocess.run(
                ["python3", str(VALIDATOR), "--output", str(output)],
                cwd=ROOT,
                check=True,
                capture_output=True,
                text=True,
            )
            self.assertTrue(completed.stdout)
            report = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(report["status"], "PRODUCTION_READY")
        self.assertEqual(report["blockers"], [])
        self.assertEqual(
            report["approved_preview_sha256"],
            "61c037374b3972da149296de3b72de58359579f9ca783aba86da0c144962ac3f",
        )
        self.assertEqual(set(report["brand_assets"]), {"intro", "subscribe_cta", "outro"})
        self.assertEqual(
            report["render_strategy"],
            "bounded_segments_then_assembly",
        )
        self.assertEqual(
            report["canary_render_strategy"],
            "hyperframes_segmented_matrix",
        )
        self.assertEqual(report["segment_max_duration_sec"], 120)
        self.assertEqual(report["matrix_max_parallel"], 4)
        self.assertTrue(report["github_canary_required"])
        self.assertFalse(report["provider_calls_authorized"])

    def test_paid_gate_accepts_approved_renderer(self):
        completed = subprocess.run(
            ["python3", str(VALIDATOR), "--require-production-ready"],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr + completed.stdout)
        self.assertIn('"status": "PRODUCTION_READY"', completed.stdout)


if __name__ == "__main__":
    unittest.main()
