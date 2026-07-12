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


if __name__ == "__main__":
    unittest.main()
