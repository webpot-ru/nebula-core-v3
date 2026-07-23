import json
import tempfile
import unittest
from pathlib import Path

from scripts.render_acc1_hyperframes_realistic_test import (
    CAPTION_MAX_CHARS,
    FORMAT_VISUAL_SYSTEM_V3_STYLE_PROFILE,
    brand_safe_caption_track,
    normalize_caption_track,
    resolve_generated_storyboard,
    split_caption_cue,
    subtitle_filter,
    verify_paid_generation_receipt,
    write_ass,
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

    def test_verifies_exact_five_call_receipt_without_retries(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            storyboard = root / "storyboard-generated.json"
            storyboard.write_text("{}", encoding="utf-8")
            journal = {
                "approved_call_cap": 5,
                "automatic_retries": 0,
                "attempts": [{"status": "complete"} for _ in range(5)],
            }
            (root / "paid-image-attempts.json").write_text(
                json.dumps(journal), encoding="utf-8",
            )
            verified = verify_paid_generation_receipt(
                storyboard, expected_page_count=5,
            )
        self.assertEqual(len(verified["attempts"]), 5)

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

    def test_splits_long_caption_into_contiguous_one_line_cues(self):
        source = {
            "start_sec": 12.0,
            "end_sec": 18.0,
            "text": (
                "Это намеренно длинная реплика для проверки аккуратного деления "
                "на несколько последовательных однострочных субтитров"
            ),
        }
        parts = split_caption_cue(source)
        self.assertGreater(len(parts), 1)
        self.assertEqual(parts[0]["start_sec"], source["start_sec"])
        self.assertEqual(parts[-1]["end_sec"], source["end_sec"])
        self.assertTrue(all(len(part["text"]) <= CAPTION_MAX_CHARS for part in parts))
        self.assertTrue(all("\n" not in part["text"] for part in parts))
        for left, right in zip(parts, parts[1:]):
            self.assertAlmostEqual(left["end_sec"], right["start_sec"])
        self.assertEqual(
            " ".join(part["text"] for part in parts),
            " ".join(source["text"].split()),
        )

    def test_normalized_track_writes_long_caption_without_overlap(self):
        track = {
            "cues": [{
                "start_sec": 1.0,
                "end_sec": 5.0,
                "text": (
                    "Одна очень длинная фраза теперь разбивается по словам и "
                    "остаётся однострочной на всём протяжении исходной реплики"
                ),
            }],
        }
        normalized = normalize_caption_track(track)
        self.assertEqual(normalized["cue_count"], len(normalized["cues"]))
        with tempfile.TemporaryDirectory() as temp:
            rendered = write_srt(
                normalized, Path(temp) / "captions.srt",
            ).read_text(encoding="utf-8")
        self.assertIn("00:00:01,000", rendered)
        self.assertIn("00:00:05,000", rendered)

    def test_ass_captions_pin_the_real_1080p_canvas(self):
        track = {"cues": [{"start_sec": 1.0, "end_sec": 2.0, "text": "Одна строка"}]}
        with tempfile.TemporaryDirectory() as temp:
            output = write_ass(track, Path(temp) / "captions.ass")
            rendered = output.read_text(encoding="utf-8")
        self.assertIn("PlayResX: 1920", rendered)
        self.assertIn("PlayResY: 1080", rendered)
        self.assertIn("Style: Caption,Arial,42", rendered)
        self.assertIn("Dialogue: 0,0:00:01.00,0:00:02.00", rendered)
        self.assertEqual(subtitle_filter(Path("captions.ass")), "ass=filename='captions.ass'")


if __name__ == "__main__":
    unittest.main()
