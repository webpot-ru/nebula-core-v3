import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "review_reddit_topics",
    ROOT / "scripts/review_reddit_topics.py",
)
review_reddit_topics = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(review_reddit_topics)


class RedditTopicReviewTests(unittest.TestCase):
    def entry(self, post_id, title, body, subreddit="r/nosleep", local_score=80):
        return {
            "post_id": post_id,
            "title": title,
            "subreddit": subreddit,
            "source_body": body,
            "local_score": local_score,
            "source_has_url": False,
            "source_has_markdown_link": False,
            "source_has_markdown_image": False,
        }

    def saga_queue(self, pillar, family, entries):
        pilot_by_pillar = {
            "relationships_family": "pilot_01",
            "work_money_justice": "pilot_02",
            "strange_dark_unexplained": "pilot_03",
        }
        subreddits_by_pillar = {
            "relationships_family": ["relationship_advice", "AmItheAsshole"],
            "work_money_justice": ["MaliciousCompliance", "prorevenge"],
            "strange_dark_unexplained": ["nosleep", "LetsNotMeet"],
        }
        return {
            "channel_id": "acc1",
            "format_intent": "saga",
            "source_plan": {
                "pilot_id": pilot_by_pillar[pillar],
                "format": "SAGA",
                "pillar": pillar,
                "topic_family": family,
                "subreddits": subreddits_by_pillar[pillar],
                "format_intent": "saga",
                "target_duration_minutes": [18, 30],
                "source_word_count": [2340, 3900],
                "words_per_minute": 130,
            },
            "entries": entries,
        }

    @staticmethod
    def saga_body(sentence, ending):
        passages = [
            f"{sentence} Detail{index} changed consequence{index} before event{index} and the next decision."
            for index in range(180)
        ]
        return " ".join(passages + [ending])

    def test_full_body_review_returns_diverse_top_topics(self):
        queue = {
            "channel_id": "acc1",
            "format_intent": "long",
            "entries": [
                self.entry(
                    "rule",
                    "My boss gave me one rule for the night shift",
                    "I worked maintenance at night. The rule said never open the door exactly at three. " * 80,
                ),
                self.entry(
                    "family",
                    "Our old family video should not exist",
                    "The tape showed my mother inside our childhood house before she was born. " * 80,
                ),
                self.entry(
                    "train",
                    "The last train did not stop at my station",
                    "The subway tunnel and empty station became a trap after the final train. " * 80,
                ),
            ],
        }
        review = review_reddit_topics.build_review(queue, 3)
        self.assertEqual(review["status"], "review_ready")
        self.assertEqual(review["candidate_count"], 3)
        self.assertEqual(len(review["top_topics"]), 3)
        self.assertFalse(review["production_authorized"])
        self.assertTrue(all(item["review_status"] == "SHORTLIST_FOR_RIGHTS_REVIEW" for item in review["top_topics"]))
        self.assertEqual(len({item["post_id"] for item in review["top_topics"]}), 3)
        self.assertTrue(all("best_candidate_score" in theme for theme in review["themes"]))

    def test_truth_and_dependency_risks_are_explicit(self):
        candidate = review_reddit_topics.analyze_entry(
            self.entry(
                "claim",
                "I met someone on the road",
                "I was driving down the road when a stranger appeared. https://example.com " * 60,
                subreddit="r/LetsNotMeet",
            ) | {"source_has_url": True}
        )
        self.assertEqual(candidate["truth_mode"], "unverified_personal_account")
        self.assertIn("unverified_claim", candidate["risks"])
        self.assertIn("external_dependency", candidate["risks"])
        self.assertIn("short_source_for_target_runtime", candidate["risks"])

    def test_incidental_body_words_do_not_override_title_theme(self):
        candidate = review_reddit_topics.analyze_entry(
            self.entry(
                "shift",
                "My boss gave me one rule for the night shift",
                "The house had a video screen, but my work rule was never to open the office door. " * 80,
            )
        )
        self.assertGreater(candidate["theme_scores"]["night_work_role"], 0)
        self.assertNotIn("family_home_anomaly", candidate["theme_scores"])
        self.assertNotIn("haunted_media_record", candidate["theme_scores"])

    def test_empty_queue_is_fail_closed_but_reportable(self):
        review = review_reddit_topics.build_review({}, 3)
        self.assertEqual(review["status"], "no_candidates")
        self.assertEqual(review["top_topics"], [])

    def test_missing_source_body_fails(self):
        with self.assertRaises(ValueError):
            review_reddit_topics.analyze_entry({"post_id": "missing", "title": "No body"})

    def test_broad_saga_review_covers_relationship_work_and_dark_pillars(self):
        cases = (
            (
                "relationships_family", "human_drama", "r/relationship_advice",
                "My husband and my family forced me to choose",
                "My husband argued with my family and our relationship changed forever.",
                "Finally, we broke up and I blocked him.",
            ),
            (
                "work_money_justice", "human_drama", "r/MaliciousCompliance",
                "My boss refused to pay me for my work",
                "My boss withheld my paycheck at work, so I reported the company.",
                "In the end, the company paid me and the manager was fired.",
            ),
            (
                "strange_dark_unexplained", "dark_curiosity", "r/nosleep",
                "One strange rule kept the night shift alive",
                "Every night the impossible shadow waited behind the locked door.",
                "That was the last night I saw the shadow, and I never went back.",
            ),
        )
        for index, (pillar, family, subreddit, title, sentence, ending) in enumerate(cases):
            with self.subTest(pillar=pillar):
                entry = self.entry(
                    f"saga-{index}", title, self.saga_body(sentence, ending), subreddit=subreddit,
                )
                entry["topic_family"] = family
                review = review_reddit_topics.build_review(
                    self.saga_queue(pillar, family, [entry]), 3,
                )
                self.assertEqual(review["status"], "review_ready", review)
                self.assertEqual(review["eligible_candidate_count"], 1)
                self.assertEqual(review["top_topics"][0]["pillar_id"], pillar)
                self.assertTrue(review["top_topics"][0]["runtime_fit"])
                self.assertTrue(review["top_topics"][0]["payoff_complete"])
                self.assertRegex(review["source_sha256"], r"^[0-9a-f]{64}$")
                self.assertRegex(review["review_sha256"], r"^[0-9a-f]{64}$")

    def test_saga_link_dependency_is_a_hard_block(self):
        body = self.saga_body(
            "My husband argued with my family and our relationship changed forever.",
            "Finally, we broke up and I blocked him.",
        )
        body += " [Read more](https://www.reddit.com/r/relationship_advice/comments/linked2/part_2/)"
        entry = self.entry(
            "linked",
            "My husband and my family forced me to choose",
            body,
            subreddit="r/relationship_advice",
        )
        entry.update({
            "topic_family": "human_drama",
            "source_has_url": True,
            "source_has_markdown_link": True,
        })
        review = review_reddit_topics.build_review(
            self.saga_queue("relationships_family", "human_drama", [entry]), 3,
        )
        self.assertEqual(review["status"], "no_eligible_saga_candidate")
        self.assertIn(
            "screenshot_or_link_dependent", review["candidate_reviews"][0]["blocking_reasons"],
        )

    def test_saga_reddit_author_profile_link_is_not_a_story_dependency(self):
        body = self.saga_body(
            "Every night the impossible shadow waited behind the locked door.",
            "The locked door opened behind me. The shadow smiled.",
        )
        body += " I learned [that](https://www.reddit.com/user/gamalfrank/)."
        entry = self.entry(
            "profile-link",
            "One strange rule kept the night shift alive",
            body,
            subreddit="r/nosleep",
        )
        entry.update({
            "topic_family": "dark_curiosity",
            "source_has_url": True,
            "source_has_markdown_link": True,
        })

        review = review_reddit_topics.build_review(
            self.saga_queue(
                "strange_dark_unexplained", "dark_curiosity", [entry],
            ),
            3,
        )

        self.assertEqual(review["status"], "review_ready", review)
        topic = review["candidate_reviews"][0]
        self.assertFalse(topic["depends_on_screenshot_or_link"])
        self.assertNotIn("screenshot_or_link_dependent", topic["blocking_reasons"])

    def test_profile_shaped_non_reddit_link_remains_a_dependency(self):
        entry = self.entry(
            "external-profile",
            "One strange rule kept the night shift alive",
            "The night ended. [author](https://example.com/user/gamalfrank/)",
        )
        entry.update({"source_has_url": True, "source_has_markdown_link": True})

        self.assertTrue(
            review_reddit_topics.source_depends_on_external(
                entry, entry["source_body"],
            )
        )

    def test_saga_machine_like_character_density_is_a_hard_block(self):
        body = " ".join(
            ["machinegeneratednarrationtoken"] * 2330
            + ["Finally", "we", "broke", "up", "and", "I", "blocked", "him."]
        )
        entry = self.entry(
            "dense",
            "My husband and my family forced me to choose",
            body,
            subreddit="r/relationship_advice",
        )
        entry["topic_family"] = "human_drama"
        review = review_reddit_topics.build_review(
            self.saga_queue("relationships_family", "human_drama", [entry]), 3,
        )
        self.assertEqual(review["status"], "no_eligible_saga_candidate")
        self.assertIn(
            "unnatural_source_character_density",
            review["candidate_reviews"][0]["blocking_reasons"],
        )

    def test_saga_high_confidence_pii_is_a_hard_block(self):
        body = self.saga_body(
            "My husband argued with my family and our relationship changed forever.",
            "Finally, we broke up and I blocked him. Contact me at private.person@example.com.",
        )
        entry = self.entry(
            "pii",
            "My husband and my family forced me to choose",
            body,
            subreddit="r/relationship_advice",
        )
        entry["topic_family"] = "human_drama"
        review = review_reddit_topics.build_review(
            self.saga_queue("relationships_family", "human_drama", [entry]), 3,
        )
        self.assertEqual(review["status"], "no_eligible_saga_candidate")
        self.assertIn(
            "unsafe_or_pii_source",
            review["candidate_reviews"][0]["blocking_reasons"],
        )

    def test_saga_native_reddit_media_is_a_hard_block(self):
        entry = self.entry(
            "gallery",
            "My husband and my family forced me to choose",
            self.saga_body(
                "My husband argued with my family and our relationship changed forever.",
                "Finally, we broke up and I blocked him.",
            ),
            subreddit="r/relationship_advice",
        )
        entry.update({
            "topic_family": "human_drama",
            "source_media": [{"kind": "image", "media_id": "gallery-1"}],
        })
        review = review_reddit_topics.build_review(
            self.saga_queue("relationships_family", "human_drama", [entry]), 3,
        )
        self.assertEqual(review["status"], "no_eligible_saga_candidate")
        self.assertTrue(review["candidate_reviews"][0]["depends_on_screenshot_or_link"])
        self.assertIn(
            "screenshot_or_link_dependent", review["candidate_reviews"][0]["blocking_reasons"],
        )

    def test_saga_open_ending_and_wrong_family_fail_closed(self):
        entry = self.entry(
            "open",
            "My boss refused to pay me for my work",
            self.saga_body(
                "My boss withheld my paycheck at work, so I reported the company.",
                "I am still waiting to find out what happens next.",
            ),
            subreddit="r/MaliciousCompliance",
        )
        entry["topic_family"] = "dark_curiosity"
        review = review_reddit_topics.build_review(
            self.saga_queue("work_money_justice", "human_drama", [entry]), 3,
        )
        blockers = review["candidate_reviews"][0]["blocking_reasons"]
        self.assertIn("wrong_source_family", blockers)
        self.assertIn("possible_open_ending", blockers)

    def test_saga_terminal_horror_ending_does_not_require_connective_marker(self):
        entry = self.entry(
            "terminal-horror",
            "One strange rule kept the night shift alive",
            self.saga_body(
                "Every night the impossible shadow waited behind the locked door.",
                "The locked door opened behind me. The shadow smiled.",
            ),
            subreddit="r/nosleep",
        )
        entry["topic_family"] = "dark_curiosity"

        review = review_reddit_topics.build_review(
            self.saga_queue("strange_dark_unexplained", "dark_curiosity", [entry]), 3,
        )

        self.assertEqual(review["status"], "review_ready", review)
        topic = review["top_topics"][0]
        self.assertTrue(topic["payoff_complete"])
        self.assertIn("The shadow smiled.", topic["payoff_evidence"])

    def test_saga_intent_without_source_plan_cannot_fall_back_to_legacy_review(self):
        entry = self.entry(
            "missing-plan",
            "My husband and family forced me to choose",
            self.saga_body(
                "My husband argued with my family and our relationship changed forever.",
                "Finally, we broke up and I blocked him.",
            ),
            subreddit="r/relationship_advice",
        )
        entry["topic_family"] = "human_drama"
        review = review_reddit_topics.build_review(
            {"channel_id": "acc1", "format_intent": "saga", "entries": [entry]}, 3,
        )
        self.assertEqual(review["status"], "blocked_invalid_source_plan")
        self.assertEqual(review["top_topics"], [])

    def test_noncanonical_saga_pilot_plan_fails_closed(self):
        entry = self.entry(
            "wrong-pilot",
            "My husband and family forced me to choose",
            self.saga_body(
                "My husband argued with my family and our relationship changed forever.",
                "Finally, we broke up and I blocked him.",
            ),
            subreddit="r/relationship_advice",
        )
        entry["topic_family"] = "human_drama"
        queue = self.saga_queue("relationships_family", "human_drama", [entry])
        queue["source_plan"]["pilot_id"] = "pilot_unknown"
        review = review_reddit_topics.build_review(queue, 3)
        self.assertEqual(review["status"], "blocked_invalid_source_plan")
        self.assertTrue(any("not canonical" in item for item in review["failures"]))


if __name__ == "__main__":
    unittest.main()
