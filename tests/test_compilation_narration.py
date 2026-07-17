import unittest

from acc1_narration_profiles import (
    STRANGE_DARK_UNEXPLAINED_PROFILE_ID,
)
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

    def test_emergency_911_is_spoken_digit_by_digit(self):
        result = narration_preflight("Диспетчер 911 ответил на звонок.")
        self.assertEqual(result["status"], "PASS")
        self.assertIn("девять один один", result["narration_text"])
        self.assertNotIn("девятьсот одиннадцать", result["narration_text"])

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

    def test_profile_semantic_units_follow_exact_story_beats(self):
        disclosure = "Это художественная история с Reddit."
        compilation = {
            "pillar": "strange_dark_unexplained",
            "truth_disclosure_ru": disclosure,
            "intro_ru": f"Начало. {disclosure}",
            "stories": [{
                "source_snapshot": {"post_id": "a", "truth_mode": "fiction"},
                "narration_ru": "Первый абзац.\n\nВторой абзац.",
                "story_beats": ["Первый абзац.", "Второй абзац."],
            }],
            "outro_ru": "Конец.",
        }
        segments = build_compilation_segments(
            compilation,
            narration_profile_id=STRANGE_DARK_UNEXPLAINED_PROFILE_ID,
        )
        story = next(item for item in segments if item["kind"] == "story")
        self.assertEqual(
            [item["boundary_source"] for item in story["semantic_units"]],
            ["explicit_story_beat", "explicit_story_beat"],
        )
        self.assertEqual(
            " ".join(item["text"] for item in story["semantic_units"]),
            "Первый абзац. Второй абзац.",
        )
        self.assertEqual(
            story["narration_profile_id"],
            STRANGE_DARK_UNEXPLAINED_PROFILE_ID,
        )

    def test_profile_packs_short_reddit_paragraphs_before_tts(self):
        disclosure = "Это художественная история с Reddit."
        paragraph = (
            "Мы медленно шли по тёмной тропе, прислушиваясь к ветру "
            "и далёкой воде."
        )
        narration = "\n\n".join([paragraph] * 80)
        compilation = {
            "pillar": "strange_dark_unexplained",
            "truth_disclosure_ru": disclosure,
            "intro_ru": f"Начало. {disclosure}",
            "stories": [{
                "source_snapshot": {"post_id": "a", "truth_mode": "fiction"},
                "narration_ru": narration,
            }],
            "outro_ru": "Конец.",
        }
        segments = build_compilation_segments(
            compilation,
            narration_profile_id=STRANGE_DARK_UNEXPLAINED_PROFILE_ID,
        )
        story = next(item for item in segments if item["kind"] == "story")
        units = story["semantic_units"]
        self.assertLess(len(units), 10)
        self.assertTrue(all(len(item["text"]) <= 1_650 for item in units))
        self.assertTrue(all(item["boundary_source"] == "paragraph" for item in units))
        self.assertEqual(
            " ".join("\n\n".join(item["text"] for item in units).split()),
            " ".join(narration.split()),
        )

    def test_profile_selection_fails_on_unknown_pillar_or_changed_beats(self):
        disclosure = "Это художественная история с Reddit."
        compilation = {
            "pillar": "unknown",
            "truth_disclosure_ru": disclosure,
            "intro_ru": f"Начало. {disclosure}",
            "stories": [{
                "source_snapshot": {"post_id": "a", "truth_mode": "fiction"},
                "narration_ru": "Первый абзац. Второй абзац.",
            }],
            "outro_ru": "Конец.",
        }
        with self.assertRaisesRegex(NarrationPreflightError, "pillar must be"):
            build_compilation_segments(
                compilation,
                narration_profile_id=STRANGE_DARK_UNEXPLAINED_PROFILE_ID,
            )
        compilation["pillar"] = "strange_dark_unexplained"
        compilation["stories"][0]["story_beats"] = [
            "Первый абзац.", "Изменённый финал.",
        ]
        with self.assertRaisesRegex(
            NarrationPreflightError, "preserve exact sanitized narration",
        ):
            build_compilation_segments(
                compilation,
                narration_profile_id=STRANGE_DARK_UNEXPLAINED_PROFILE_ID,
            )


if __name__ == "__main__":
    unittest.main()
