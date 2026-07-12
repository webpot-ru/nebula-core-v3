import unittest

from compilation_narration import NarrationPreflightError, build_compilation_segments, narration_preflight


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

    def test_clock_time_has_deterministic_russian_spoken_form(self):
        result = narration_preflight("Нужно вымыть пол ровно в 3:15, а вернуться в 4:00.")
        self.assertEqual(result["status"], "PASS")
        self.assertIn("три часа пятнадцать минут", result["narration_text"])
        self.assertIn("четыре часа ровно", result["narration_text"])

    def test_builds_ordered_story_segments(self):
        compilation = {
            "intro_ru": "Три истории на ночь.",
            "stories": [
                {"source_snapshot": {"post_id": "a"}, "narration_ru": "Первая история.", "transition_after_ru": "Следующая история."},
                {"source_snapshot": {"post_id": "b"}, "narration_ru": "Вторая история."},
            ],
            "outro_ru": "Какая история напугала вас сильнее?",
        }
        segments = build_compilation_segments(compilation)
        self.assertEqual([item["segment_id"] for item in segments], ["intro", "story_a", "transition_01", "story_b", "outro"])
        self.assertTrue(all(item["required_model_id"] == "eleven_v3" for item in segments))

    def test_empty_story_blocks(self):
        with self.assertRaises(NarrationPreflightError):
            build_compilation_segments({"intro_ru": "Начало", "stories": [{"source_snapshot": {"post_id": "a"}, "narration_ru": ""}], "outro_ru": "Конец"})


if __name__ == "__main__":
    unittest.main()
