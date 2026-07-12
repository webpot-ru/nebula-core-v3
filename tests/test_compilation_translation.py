import unittest
import tempfile
from pathlib import Path

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
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


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

    def test_truncated_json_provider_error_triggers_chunk_fallback(self):
        provider = QueueProvider([
            RuntimeError('Gemini did not return JSON: {"title":"Дверь","body":"обрыв'),
            {"translated_title": "Дверь", "glossary": {}, "continuity": "first person"},
            {"body": "Я услышал стук. Я спрятался в коридоре. На рассвете дверь была открыта.", "complete": True},
        ])
        reviewer = QueueProvider([{"verdict": "PASS", "issues": [], "ending_preserved": True}])
        result = translate_and_review_story(STORY, provider=provider, reviewer=reviewer, config=TranslationConfig(chunk_chars=1000))
        self.assertTrue(result["translation_audit"]["chunk_fallback"])

    def test_chunk_fallback_resumes_without_repeating_saved_calls(self):
        story = {"title": "Door", "body": "First part.\n\nSecond part.\n\nThird part."}
        with tempfile.TemporaryDirectory() as temp:
            checkpoint = Path(temp) / "chunks.json"
            interrupted = QueueProvider([
                RuntimeError('Gemini did not return JSON: {"body":"cut'),
                {"translated_title": "Дверь", "glossary": {}, "continuity": "first person"},
                {"body": "Первая часть.", "complete": True},
                RuntimeError("temporary provider interruption"),
            ])
            with self.assertRaisesRegex(RuntimeError, "interruption"):
                translate_and_review_story(story, provider=interrupted,
                    config=TranslationConfig(chunk_chars=12, min_length_ratio=0.1),
                    chunk_checkpoint_path=checkpoint)
            resumed = QueueProvider([
                {"body": "Вторая часть.", "complete": True},
                {"body": "Третья часть.", "complete": True},
                {"verdict": "PASS", "issues": [], "ending_preserved": True},
            ])
            result = translate_and_review_story(story, provider=resumed,
                config=TranslationConfig(chunk_chars=12, min_length_ratio=0.1),
                chunk_checkpoint_path=checkpoint)
        self.assertTrue(result["translation_audit"]["chunk_fallback"])
        self.assertEqual(len(resumed.calls), 3)

    def test_auth_error_does_not_trigger_paid_fallback(self):
        provider = QueueProvider([RuntimeError("Google Gemini HTTP 401: invalid key")])
        with self.assertRaisesRegex(RuntimeError, "401"):
            translate_and_review_story(STORY, provider=provider)
        self.assertEqual(len(provider.calls), 1)

    def test_reviewer_can_request_two_revisions_then_pass(self):
        translation = {"title": "Дверь", "body": "Я услышал стук. Я спрятался в коридоре. На рассвете дверь была открыта.", "complete": True, "ending_preserved": True}
        provider = QueueProvider([translation])
        reviewer = QueueProvider([
            {"verdict": "REVISE", "issues": [{"kind": "tone", "source_quote": "I heard a knock.", "translation_quote": "Я услышал стук.", "replacement": "Я услышал громкий стук."}], "ending_preserved": True},
            {"verdict": "REVISE", "issues": [{"kind": "place", "source_quote": "I hid in the hall.", "translation_quote": "Я спрятался в коридоре.", "replacement": "Я затаился в коридоре."}], "ending_preserved": True},
            {"verdict": "PASS", "issues": [], "ending_preserved": True},
        ])
        result = translate_and_review_story(STORY, provider=provider, reviewer=reviewer)
        self.assertEqual(result["translation_audit"]["revisions"], 2)
        self.assertIn("громкий стук", result["body"])
        self.assertEqual(len(provider.calls), 1)

    def test_third_revision_is_blocked(self):
        translation = {"title": "Дверь", "body": "Я услышал стук. Я спрятался в коридоре. На рассвете дверь была открыта.", "complete": True, "ending_preserved": True}
        provider = QueueProvider([translation])
        reviewer = QueueProvider([
            {"verdict": "REVISE", "issues": [{"kind": "one", "source_quote": "I heard a knock.", "translation_quote": "Я услышал стук.", "replacement": "Я услышал громкий стук."}], "ending_preserved": True},
            {"verdict": "REVISE", "issues": [{"kind": "two", "source_quote": "I hid in the hall.", "translation_quote": "Я спрятался в коридоре.", "replacement": "Я затаился в коридоре."}], "ending_preserved": True},
            {"verdict": "REVISE", "issues": [{"kind": "three", "source_quote": "At dawn", "translation_quote": "На рассвете", "replacement": "С рассветом"}], "ending_preserved": True},
        ])
        with self.assertRaisesRegex(TranslationError, "maximum"):
            translate_and_review_story(STORY, provider=provider, reviewer=reviewer)

    def test_invalid_reviewer_verdict_fails_closed(self):
        provider = QueueProvider([{"title": "Дверь", "body": "Я услышал стук. Я спрятался в коридоре. На рассвете дверь была открыта.", "complete": True, "ending_preserved": True}])
        reviewer = QueueProvider([{"verdict": "MAYBE", "ending_preserved": True}])
        with self.assertRaisesRegex(TranslationError, "unsafe verdict"):
            translate_and_review_story(STORY, provider=provider, reviewer=reviewer)

    def test_review_failure_checkpoint_preserves_decisions(self):
        translation = {"title": "Дверь", "body": "Я услышал стук. Я спрятался в коридоре. На рассвете дверь была открыта.", "complete": True, "ending_preserved": True}
        provider = QueueProvider([translation])
        reviewer = QueueProvider([
            {"verdict": "REVISE", "issues": [{"kind": "one", "source_quote": "I heard a knock.", "translation_quote": "Я услышал стук.", "replacement": "Я услышал громкий стук."}], "ending_preserved": True},
            {"verdict": "REVISE", "issues": [{"kind": "two", "source_quote": "I hid in the hall.", "translation_quote": "Я спрятался в коридоре.", "replacement": "Я затаился в коридоре."}], "ending_preserved": True},
            {"verdict": "REVISE", "issues": [{"kind": "three", "source_quote": "At dawn", "translation_quote": "На рассвете", "replacement": "С рассветом"}], "ending_preserved": True},
        ])
        with tempfile.TemporaryDirectory() as temp:
            checkpoint = Path(temp) / "review.json"
            with self.assertRaisesRegex(TranslationError, "maximum"):
                translate_and_review_story(STORY, provider=provider, reviewer=reviewer,
                    review_checkpoint_path=checkpoint)
            saved = __import__("json").loads(checkpoint.read_text())
        self.assertEqual(saved["revisions_completed"], 2)
        self.assertEqual(len(saved["review_history"]), 3)
        self.assertEqual(saved["schema_version"], 2)
        self.assertIn("громкий стук", saved["current_translation"]["body"])


if __name__ == "__main__":
    unittest.main()
