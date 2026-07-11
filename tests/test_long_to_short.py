import unittest
from pathlib import Path

import scraper
import story_adapter


ROOT = Path(__file__).resolve().parents[1]


class LongToShortContractTests(unittest.TestCase):
    def test_source_profile_accepts_complete_long_story_only(self):
        self.assertIsNone(scraper.format_length_skip_reason(4000, "shorts_from_long"))
        self.assertIn("too_short", scraper.format_length_skip_reason(2400, "shorts_from_long"))
        self.assertIn("too_long", scraper.format_length_skip_reason(26000, "shorts_from_long"))

    def test_adapter_requires_source_backed_setup_escalation_and_payoff(self):
        story = {
            "title": "The night rule",
            "body": (
                "The caretaker gave me one rule: never open the red door. "
                "At midnight, someone behind it began using my own voice. "
                "I escaped when the sunrise made the knocking stop."
            ),
            "comments": [],
            "format_intent": "shorts_from_long",
        }
        payload = {
            "safe_to_publish": True,
            "adapted_title": "The one rule at the red door",
            "adapted_body": story["body"],
            "hook_evidence": [{"field": "body", "quote": "never open the red door"}],
            "story_beat_evidence": [
                {"beat": "setup", "quote": "The caretaker gave me one rule: never open the red door."},
                {"beat": "escalation", "quote": "At midnight, someone behind it began using my own voice."},
                {"beat": "payoff", "quote": "I escaped when the sunrise made the knocking stop."},
            ],
            "facts_not_in_source": [],
        }
        failures = story_adapter.validate_adaptation(
            story,
            payload,
            strict_evidence=True,
            max_expansion_ratio=1.15,
            max_body_chars=2200,
            long_to_short=True,
        )
        self.assertEqual(failures, [])

        payload["story_beat_evidence"][2]["quote"] = "A monster vanished in the sunrise."
        failures = story_adapter.validate_adaptation(
            story,
            payload,
            strict_evidence=True,
            max_expansion_ratio=1.15,
            max_body_chars=2200,
            long_to_short=True,
        )
        self.assertTrue(any("setup, escalation, and payoff" in failure for failure in failures))

    def test_only_acc1_short_workflow_uses_long_source_adapter(self):
        for relative in (
            ".github/workflows/auto_publish.yml",
            ".github/workflows/video_dry_run.yml",
        ):
            workflow = (ROOT / relative).read_text(encoding="utf-8")
            self.assertIn('= "acc1"', workflow)
            self.assertIn("--format-intent shorts_from_long", workflow)
            self.assertIn("--long-to-short --max-body-chars 2200", workflow)

    def test_acc1_auto_and_scheduled_routes_are_longform_first(self):
        auto_publish = (ROOT / ".github/workflows/auto_publish.yml").read_text(encoding="utf-8")
        dry_run = (ROOT / ".github/workflows/video_dry_run.yml").read_text(encoding="utf-8")
        self.assertIn('if [ "$CH" = "acc1" ]; then FORMAT="long"', auto_publish)
        self.assertIn('"channel":"acc1","slot":"1","time_filter":"auto","privacy_status":"unlisted","content_format":"long"', auto_publish)
        self.assertIn('if [ "$CHANNEL_ID" = "acc1" ]; then CONTENT_FORMAT="long"', dry_run)


if __name__ == "__main__":
    unittest.main()
