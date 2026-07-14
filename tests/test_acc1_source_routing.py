import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import scraper


ROOT = Path(__file__).resolve().parents[1]


class Acc1SourceRoutingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        config = json.loads((ROOT / "channels.json").read_text(encoding="utf-8"))
        cls.channel = next(item for item in config["channels"] if item["id"] == "acc1")

    def test_superseded_default_mix_fails_closed(self):
        with self.assertRaises(scraper.TopicSourcePlanError):
            scraper.resolve_topic_source_request(self.channel)

    def test_pilot_resolves_exact_family_and_bundle_contract(self):
        family, plan = scraper.resolve_topic_source_request(self.channel, pilot_id="pilot_02")
        self.assertEqual(family, "human_drama")
        self.assertEqual(plan["pillar"], "work_money_justice")
        self.assertEqual(plan["format_intent"], "bundle")
        self.assertEqual(plan["story_count"], [3, 5])
        self.assertEqual(plan["aggregate_source_word_count"], [2340, 3900])
        sources = scraper.build_topic_sources(
            self.channel["subreddits"],
            "auto",
            self.channel,
            family,
            planned_subreddits=plan["subreddits"],
        )
        self.assertEqual(sources[0]["subreddits"][:2], ["MaliciousCompliance", "prorevenge"])

    def test_conflicting_explicit_family_fails(self):
        with self.assertRaises(scraper.TopicSourcePlanError):
            scraper.resolve_topic_source_request(
                self.channel, pilot_id="pilot_03", topic_family="human_drama",
            )

    def test_saga_reserve_can_explicitly_scan_week_month_and_year(self):
        family, plan = scraper.resolve_topic_source_request(
            self.channel, pilot_id="pilot_03",
        )
        default_sources = scraper.build_topic_sources(
            self.channel["subreddits"],
            "auto",
            self.channel,
            family,
            planned_subreddits=plan["subreddits"],
        )
        reserve_sources = scraper.build_topic_sources(
            self.channel["subreddits"],
            "auto",
            self.channel,
            family,
            planned_subreddits=plan["subreddits"],
            max_time_windows_per_topic=3,
        )
        self.assertEqual(default_sources[0]["time_windows"], ["week", "month"])
        self.assertEqual(
            reserve_sources[0]["time_windows"], ["week", "month", "year"],
        )

    def test_unknown_family_fails_instead_of_legacy_fallback(self):
        with self.assertRaises(scraper.TopicSourcePlanError):
            scraper.build_topic_sources(
                self.channel["subreddits"], "month", self.channel, "unknown_family",
            )

    def test_thread_pilot_fails_before_reddit(self):
        with mock.patch.object(scraper, "get_reddit") as get_reddit:
            with self.assertRaises(scraper.TopicSourcePlanError):
                scraper.fetch_best_story(
                    self.channel["subreddits"],
                    channel_id="acc1",
                    channel_config=self.channel,
                    pilot_id="pilot_04",
                )
        get_reddit.assert_not_called()

    def test_saga_word_runtime_is_enforced(self):
        self.assertIsNone(
            scraper.format_length_skip_reason(20_000, "saga", word_count=2340)
        )
        self.assertIn(
            "too_short", scraper.format_length_skip_reason(20_000, "saga", word_count=2339)
        )
        self.assertIn(
            "too_long", scraper.format_length_skip_reason(20_000, "saga", word_count=3901)
        )


class SourceOnlySelectionTests(unittest.TestCase):
    def test_disabled_ai_is_unreviewed_but_selection_eligible(self):
        original = scraper.AI_QUALITY_ENABLED
        scraper.AI_QUALITY_ENABLED = False
        try:
            result = scraper.ai_quality_check("Title", "Body", {})
        finally:
            scraper.AI_QUALITY_ENABLED = original
        self.assertEqual(result["verdict"], "UNREVIEWED")
        self.assertTrue(result["selection_eligible"])
        self.assertEqual(scraper.producer_quality_score(71, result), 71.0)

    def test_source_only_queue_is_explicitly_unreviewed(self):
        entry = {
            "post_id": "source-only",
            "producer_score": 71.0,
            "verdict": "UNREVIEWED",
            "selection_eligible": True,
        }
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "queue.json"
            scraper.write_producer_queue(
                str(output),
                channel_id="acc1",
                format_intent="saga",
                candidates_total=1,
                ai_budget=1,
                skip_rank=0,
                entries=[entry],
                chosen_entry=entry,
                source_plan={"pilot_id": "pilot_01", "format": "SAGA"},
            )
            payload = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(payload["quality_review_status"], "UNREVIEWED")
        self.assertEqual(payload["entries"][0]["verdict"], "UNREVIEWED")
        self.assertTrue(payload["entries"][0]["selection_eligible"])


if __name__ == "__main__":
    unittest.main()
