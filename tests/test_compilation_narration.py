import unittest

from compilation_narration import (
    NarrationPreflightError,
    build_compilation_segments,
    narration_preflight,
    truth_disclosure_text,
)


class CompilationNarrationTests(unittest.TestCase):
    def test_links_and_simple_numbers_are_spoken_safely(self):
        result = narration_preflight("На экране https://reddit.com/x, 100% и 6500+ зрителей.")
        self.assertEqual(result["status"], "PASS")
        self.assertNotIn("https://", result["narration_text"])
        self.assertIn("сто процентов", result["narration_text"])
        self.assertIn("более чем шесть тысяч пятьсот", result["narration_text"])

    def test_context_sensitive_numbers_block(self):
        for text in ("Это было в 2024 году", "В 25:99", "Цена $50", "Около 2.5 метров"):
            with self.subTest(text=text):
                self.assertEqual(narration_preflight(text)["status"], "BLOCKED")

    def test_genitive_year_does_not_match_shorter_year_pattern(self):
        result = narration_preflight(
            "Дарственная от 1968 года. Был поздний осенний день 1975 года."
        )
        self.assertNotIn(
            "contextual_year",
            {item["kind"] for item in result["issues"]},
        )

    def test_clock_time_has_deterministic_russian_spoken_form(self):
        result = narration_preflight("Нужно вымыть пол ровно в 3:15, а вернуться в 4:00.")
        self.assertEqual(result["status"], "PASS")
        self.assertIn("три часа пятнадцать минут", result["narration_text"])
        self.assertIn("четыре часа ровно", result["narration_text"])

    def test_builds_ordered_story_segments(self):
        disclosure = "Это художественные истории с Reddit."
        compilation = {
            "truth_disclosure_ru": disclosure,
            "intro_ru": f"Три истории на ночь. {disclosure}",
            "stories": [
                {"source_snapshot": {"post_id": "a", "truth_mode": "fiction"}, "narration_ru": "Первая история.", "transition_after_ru": "Следующая история."},
                {"source_snapshot": {"post_id": "b", "truth_mode": "fiction"}, "narration_ru": "Вторая история.", "narration_role": "comment"},
            ],
            "outro_ru": "Какая история напугала вас сильнее?",
        }
        segments = build_compilation_segments(compilation)
        self.assertEqual(
            [item["segment_id"] for item in segments],
            ["intro", "story_a", "transition_01", "story_b", "outro"],
        )
        self.assertEqual(segments[0]["truth_disclosure_text"], disclosure)
        self.assertEqual([item["voice_role"] for item in segments], [
            "narrator", "narrator", "narrator", "comment", "narrator",
        ])
        self.assertEqual(" ".join(item["text"] for item in segments).count(disclosure), 1)
        self.assertTrue(all(item["required_model_id"] == "eleven_v3" for item in segments))

    def test_empty_story_blocks(self):
        with self.assertRaises(NarrationPreflightError):
            build_compilation_segments({
                "truth_disclosure_ru": "Это художественная история с Reddit.",
                "intro_ru": "Начало. Это художественная история с Reddit.",
                "stories": [{"source_snapshot": {"post_id": "a", "truth_mode": "fiction"}, "narration_ru": ""}],
                "outro_ru": "Конец",
            })

    def test_missing_truth_mode_blocks_before_tts(self):
        story = {"source_snapshot": {"post_id": "a"}, "narration_ru": "История."}
        with self.assertRaisesRegex(NarrationPreflightError, "truth_mode"):
            truth_disclosure_text(story)

    def test_mixed_truth_modes_and_duplicate_disclosure_block(self):
        disclosure = "Это художественная история с Reddit."
        mixed = {
            "truth_disclosure_ru": disclosure,
            "intro_ru": f"Начало. {disclosure}",
            "stories": [
                {"source_snapshot": {"post_id": "a", "truth_mode": "fiction"}, "narration_ru": "Один."},
                {"source_snapshot": {"post_id": "b", "truth_mode": "unverified_personal_account"}, "narration_ru": "Два."},
            ],
            "outro_ru": "Конец.",
        }
        with self.assertRaisesRegex(NarrationPreflightError, "must not mix"):
            build_compilation_segments(mixed)
        duplicated = dict(mixed)
        duplicated["stories"] = [mixed["stories"][0]]
        duplicated["outro_ru"] = f"Конец. {disclosure}"
        with self.assertRaisesRegex(NarrationPreflightError, "exactly once per episode"):
            build_compilation_segments(duplicated)


if __name__ == "__main__":
    unittest.main()
