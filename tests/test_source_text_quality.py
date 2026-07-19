import unittest

import acc1_episode_factory as factory
from acc1_thread_collector import _editorial_evidence
from scripts.review_reddit_topics import source_narration_blockers
from source_text_quality import source_text_quality_blockers


class SourceTextQualityTests(unittest.TestCase):
    def test_natural_narrative_passes(self):
        text = " ".join(
            f"When the evening began, witness{index} described event{index} and consequence{index} calmly."
            for index in range(1, 30)
        )
        self.assertEqual(source_text_quality_blockers(text), [])

    def test_numeric_flood_is_blocked_in_review_and_factory(self):
        text = " ".join(["1234567890"] * 2340 + [
            "finally the family reported the incident and never heard from him again"
        ])
        blockers = source_narration_blockers(text)
        self.assertIn("excessive_numeric_token_share", blockers)
        with self.assertRaisesRegex(factory.EpisodeFactoryError, "lexical narration quality"):
            factory._validate_source_narratability(
                text, source_id="numeric-flood", role="story",
            )

    def test_repeated_word_flood_is_blocked_in_review_and_thread(self):
        text = " ".join(["word"] * 2340 + [
            "finally the family reported the incident and never heard from him again"
        ])
        blockers = source_narration_blockers(text)
        self.assertIn("dominant_source_token_repetition", blockers)
        evidence = _editorial_evidence(
            {"score": 500},
            text,
            {"title": "What happened to you?", "body": "Share the complete experience."},
            len(text.split()),
        )
        self.assertFalse(evidence["narration_envelope"]["passed"])
        self.assertIn(
            "dominant_source_token_repetition",
            evidence["narration_envelope"]["blocking_reasons"],
        )

    def test_unique_alphanumeric_digit_flood_is_blocked(self):
        text = " ".join(f"a{index:010d}" for index in range(2340))
        blockers = source_text_quality_blockers(text)
        self.assertIn("excessive_source_digit_character_share", blockers)
        self.assertIn("insufficient_word_like_token_share", blockers)

    def test_short_natural_thread_prompt_is_not_penalized_for_variety(self):
        self.assertEqual(
            source_text_quality_blockers(
                "What experience changed how you understand your profession?"
            ),
            [],
        )


if __name__ == "__main__":
    unittest.main()
