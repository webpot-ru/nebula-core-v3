import json
import unittest
from pathlib import Path

import scraper


ROOT = Path(__file__).resolve().parents[1]


class ChannelStrategyConfigTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = json.loads((ROOT / "channels.json").read_text(encoding="utf-8"))
        cls.channels = cls.config["channels"]

    def test_every_channel_has_one_unique_operational_promise(self):
        self.assertEqual(
            [channel["id"] for channel in self.channels],
            ["acc1", "acc2", "acc3", "acc4", "acc5", "acc6", "acc7"],
        )
        promises = [channel.get("viewer_promise", "").strip() for channel in self.channels]
        self.assertTrue(all(promises))
        self.assertEqual(len({promise.casefold() for promise in promises}), len(promises))

    def test_strategy_fields_are_complete_and_fail_closed(self):
        valid_lanes = {"reddit_fiction", "reddit_first_person", "evidence_dossier"}
        valid_readiness = {"ready", "pilot", "blocked"}
        for channel in self.channels:
            self.assertIs(channel.get("automation_enabled"), False, channel["id"])
            self.assertEqual(channel.get("videos_per_day"), 0, channel["id"])
            self.assertTrue(channel.get("strategy_status"), channel["id"])
            self.assertTrue(channel.get("evidence_policy"), channel["id"])
            self.assertTrue(channel.get("render_contract"), channel["id"])
            self.assertTrue(channel.get("forbidden_bets"), channel["id"])
            self.assertTrue(channel.get("cadence_plan"), channel["id"])
            bets = channel.get("owned_content_bets") or []
            self.assertGreaterEqual(len(bets), 3, channel["id"])
            for bet in bets:
                self.assertIn(bet.get("source_lane"), valid_lanes, channel["id"])
                self.assertIn(bet.get("readiness"), valid_readiness, channel["id"])

    def test_candidate_scouting_weights_still_sum_to_one(self):
        for channel in self.channels:
            weights = [float(item["weight"]) for item in channel.get("topic_mix") or []]
            self.assertTrue(weights, channel["id"])
            self.assertAlmostEqual(sum(weights), 1.0, places=6, msg=channel["id"])
            self.assertIn(
                channel.get("topic_mix_status"),
                {
                    "unvalidated_candidate_scouting_only",
                    "forced_family_validation_only",
                    "superseded_pending_rebuild",
                    "superseded_pending_evidence_lane",
                },
                channel["id"],
            )

    def test_owned_reddit_lanes_fail_closed_to_their_validation_family(self):
        expected = {
            "acc1": "dark_curiosity",
            "acc4": "human_drama",
            "acc5": "football_culture",
            "acc7": "visual_comedy",
        }
        for channel_id, family in expected.items():
            channel = next(item for item in self.channels if item["id"] == channel_id)
            self.assertEqual(channel["topic_mix_status"], "forced_family_validation_only")
            self.assertEqual(channel["topic_mix"], [{"family": family, "weight": 1.0}])

    def test_russian_channel_is_longform_first(self):
        channel = next(item for item in self.channels if item["id"] == "acc1")
        self.assertEqual(channel["primary_format"], "long")
        self.assertEqual(channel["shorts_role"], "trailer_after_long_only")
        self.assertEqual(channel["cadence_plan"]["mode"], "longform_first_unlisted_pilot")

    def test_channel_specific_producer_brief_overrides_language_default(self):
        channel = next(item for item in self.channels if item["id"] == "acc7")
        context = scraper.channel_producer_context(channel)
        self.assertEqual(context["audience_job"], channel["viewer_promise"])
        self.assertEqual(context["winning_bets"], channel["producer_brief"]["winning_bets"])
        self.assertNotIn("football identity", context["winning_bets"].lower())


class ChannelStrategyGuardTests(unittest.TestCase):
    def test_disabled_channel_requires_explicit_review_override(self):
        channel = {"id": "acc4", "automation_enabled": False, "strategy_status": "pilot"}
        with self.assertRaises(scraper.ChannelAutomationDisabledError):
            scraper.ensure_channel_automation_enabled(channel)
        scraper.ensure_channel_automation_enabled(channel, allow_disabled=True)

    def test_duplicate_guard_is_network_wide_by_default(self):
        history = {
            "version": 2,
            "posts": {
                "post-1": {
                    "channels": {"acc4": {}},
                    "story_signature": "story-signature",
                    "keyword_signature": "family dinner money conflict",
                }
            },
        }
        reason = scraper.history_duplicate_reason(
            history,
            "post-1",
            "story-signature",
            "acc7",
            "family dinner money conflict",
        )
        self.assertEqual(reason, "already_published_post_id")

        channel_only_reason = scraper.history_duplicate_reason(
            history,
            "post-1",
            "story-signature",
            "acc7",
            "family dinner money conflict",
            network_wide=False,
        )
        self.assertIsNone(channel_only_reason)


class SourceReviewEvidenceTests(unittest.TestCase):
    def test_queue_can_preserve_bounded_source_body_and_dependency_flags(self):
        class FakePost:
            subreddit = "OutOfTheLoop"
            id = "post-1"
            title = "What is happening?"
            permalink = "/r/OutOfTheLoop/comments/post-1/example/"
            score = 2000
            num_comments = 250
            selftext = "What happened here? [External answer](https://example.com/report)"

        candidate = {
            "post": FakePost(),
            "score": 55,
            "base_score": 50,
            "topic": {"family": "internet_lore", "label": "Internet lore"},
            "time_window": "week",
            "story_signature": "story-signature",
            "keyword_signature": "external answer happened",
            "velocity": {},
            "velocity_bonus": 0,
            "fatigue_penalty": 0,
        }
        entry = scraper.producer_queue_entry(
            candidate,
            1,
            {"verdict": "PUBLISH", "reason": "AI quality check disabled."},
            include_source_body=True,
        )
        self.assertEqual(entry["source_body"], FakePost.selftext)
        self.assertEqual(entry["source_body_chars"], len(FakePost.selftext))
        self.assertTrue(entry["source_has_url"])
        self.assertTrue(entry["source_has_markdown_link"])
        self.assertFalse(entry["source_has_markdown_image"])
        self.assertEqual(entry["source_question_count"], 1)

    def test_workflow_records_commit_config_and_review_scope(self):
        workflow = (ROOT / ".github/workflows/reddit_source_smoke.yml").read_text(encoding="utf-8")
        for required_text in (
            "review_label:",
            "topic_family:",
            "format_intent:",
            "max_subreddits_per_topic:",
            '--format-intent "${{ inputs.format_intent }}"',
            "format_intent=%s",
            "--include-source-body-in-queue",
            "git_sha=%s",
            "channels_sha256=%s",
            "channels-snapshot.json",
            "AI_QUALITY_CHECK: \"0\"",
        ):
            self.assertIn(required_text, workflow)


if __name__ == "__main__":
    unittest.main()
