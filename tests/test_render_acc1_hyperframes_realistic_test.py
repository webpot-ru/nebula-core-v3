import json
import tempfile
import unittest
from pathlib import Path

from scripts.render_acc1_hyperframes_realistic_test import (
    FORMAT_VISUAL_SYSTEM_V3_STYLE_PROFILE,
    brand_safe_caption_track,
    resolve_generated_storyboard,
    verify_paid_generation_receipt,
    write_srt,
)


class HyperFramesRealisticTestTests(unittest.TestCase):
    def test_resolves_only_exact_four_page_v3_storyboard(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            path = root / "storyboard-generated.json"
            payload = {
                "style_profile": FORMAT_VISUAL_SYSTEM_V3_STYLE_PROFILE,
                "publication_authorized": False,
                "slides": [
                    {"style_profile": FORMAT_VISUAL_SYSTEM_V3_STYLE_PROFILE}
                    for _ in range(4)
                ],
            }
            path.write_text(json.dumps(payload), encoding="utf-8")
            resolved, loaded = resolve_generated_storyboard(root)
        self.assertEqual(resolved.name, "storyboard-generated.json")
        self.assertEqual(loaded["style_profile"], FORMAT_VISUAL_SYSTEM_V3_STYLE_PROFILE)

    def test_rejects_old_visual_profile(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "storyboard-generated.json").write_text(
                json.dumps({
                    "style_profile": "cinematic_ink_webtoon_v1",
                    "publication_authorized": False,
                    "slides": [{"style_profile": "cinematic_ink_webtoon_v1"}] * 4,
                }),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(RuntimeError, "found 0"):
                resolve_generated_storyboard(root)

    def test_verifies_exact_four_call_receipt_without_retries(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            storyboard = root / "storyboard-generated.json"
            storyboard.write_text("{}", encoding="utf-8")
            journal = {
                "approved_call_cap": 4,
                "automatic_retries": 0,
                "attempts": [{"status": "complete"} for _ in range(4)],
            }
            (root / "paid-image-attempts.json").write_text(
                json.dumps(journal), encoding="utf-8",
            )
            verified = verify_paid_generation_receipt(storyboard)
        self.assertEqual(len(verified["attempts"]), 4)

    def test_brand_safe_captions_are_one_line_and_skip_insert_windows(self):
        track = {
            "cues": [
                {"start_sec": 0.0, "end_sec": 2.0, "text": "Первая строка"},
                {"start_sec": 5.0, "end_sec": 7.0, "text": "Скрытая строка"},
                {"start_sec": 9.0, "end_sec": 11.0, "text": "Последняя строка"},
            ],
        }
        filtered = brand_safe_caption_track(track, [(4.5, 8.0)])
        self.assertEqual([cue["text"] for cue in filtered["cues"]], [
            "Первая строка", "Последняя строка",
        ])
        with tempfile.TemporaryDirectory() as temp:
            output = write_srt(filtered, Path(temp) / "captions.srt")
            rendered = output.read_text(encoding="utf-8")
        self.assertIn("Первая строка", rendered)
        self.assertNotIn("Скрытая строка", rendered)


if __name__ == "__main__":
    unittest.main()
