import unittest

from compilation_translation import (
    DEFAULT_MAX_OUTPUT_TOKENS, TranslationConfig, TranslationError,
    translate_and_review_story,
)


STORY = {"title": "Door", "body": "I heard a knock.\n\nI hid in the hall.\n\nAt dawn, the door was open."}


class QueueProvider:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def __call__(self, **kwargs):
        self.calls.append(kwargs)
        return self.responses.pop(0)


class CompilationTranslationTests(unittest.TestCase):
    def test_full_story_first_uses_16384_and_independent_review(self):
        translator = QueueProvider([{"title": "Дверь", "body": "Я услышал стук. Я спрятался в коридоре. На рассвете дверь была открыта.", "complete": True, "ending_preserved": True}])
        reviewer = QueueProvider([{"verdict": "PASS", "issues": [], "ending_preserved": True}])
        result = translate_and_review_story(STORY, provider=translator, reviewer=reviewer)
        self.assertEqual(translator.calls[0]["max_output_tokens"], DEFAULT_MAX_OUTPUT_TOKENS)
        self.assertIn(STORY["body"], translator.calls[0]["prompt"])
        self.assertTrue(result["translation_audit"]["full_story_first"])
        self.assertFalse(result["translation_audit"]["chunk_fallback"])
        self.assertEqual(len(reviewer.calls), 1)

    def test_incomplete_full_response_alone_triggers_chunk_fallback(self):
        provider = QueueProvider([
            {"title": "Д", "body": "обрыв", "complete": False, "ending_preserved": False},
            {"translated_title": "Дверь", "glossary": {"door": "дверь"}, "continuity": "first person"},
            {"body": "Я услышал стук. Я спрятался в коридоре. На рассвете дверь была открыта.", "complete": True},
        ])
        reviewer = QueueProvider([{"verdict": "PASS", "issues": [], "ending_preserved": True}])
        result = translate_and_review_story(STORY, provider=provider, reviewer=reviewer,
            config=TranslationConfig(chunk_chars=1000))
        self.assertTrue(result["translation_audit"]["chunk_fallback"])
        self.assertIn("continuity glossary", provider.calls[1]["prompt"])

    def test_reviewer_can_request_two_revisions_then_pass(self):
        translation = {"title": "Дверь", "body": "Я услышал стук. Я спрятался в коридоре. На рассвете дверь была открыта.", "complete": True, "ending_preserved": True}
        provider = QueueProvider([translation, translation, translation])
        reviewer = QueueProvider([
            {"verdict": "REVISE", "issues": [{"kind": "tone"}], "ending_preserved": True},
            {"verdict": "REVISE", "issues": [{"kind": "number"}], "ending_preserved": True},
            {"verdict": "PASS", "issues": [], "ending_preserved": True},
        ])
        result = translate_and_review_story(STORY, provider=provider, reviewer=reviewer)
        self.assertEqual(result["translation_audit"]["revisions"], 2)

    def test_third_revision_is_blocked(self):
        translation = {"title": "Дверь", "body": "Я услышал стук. Я спрятался в коридоре. На рассвете дверь была открыта.", "complete": True, "ending_preserved": True}
        provider = QueueProvider([translation, translation, translation])
        reviewer = QueueProvider([{"verdict": "REVISE", "issues": [], "ending_preserved": True}] * 3)
        with self.assertRaisesRegex(TranslationError, "maximum"):
            translate_and_review_story(STORY, provider=provider, reviewer=reviewer)

    def test_invalid_reviewer_verdict_fails_closed(self):
        provider = QueueProvider([{"title": "Дверь", "body": "Я услышал стук. Я спрятался в коридоре. На рассвете дверь была открыта.", "complete": True, "ending_preserved": True}])
        reviewer = QueueProvider([{"verdict": "MAYBE", "ending_preserved": True}])
        with self.assertRaisesRegex(TranslationError, "unsafe verdict"):
            translate_and_review_story(STORY, provider=provider, reviewer=reviewer)


if __name__ == "__main__":
    unittest.main()
