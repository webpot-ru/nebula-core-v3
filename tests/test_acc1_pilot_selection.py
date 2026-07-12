import unittest

from scripts.select_acc1_pilots import PilotSelectionError, select_pilots


class Acc1PilotSelectionTests(unittest.TestCase):
    def setUp(self):
        self.queue = {"channel_id": "acc1", "entries": [
            {"post_id": "a", "title": "A", "subreddit": "nosleep", "url": "https://reddit/a", "source_body": "complete A"},
            {"post_id": "b", "title": "B", "subreddit": "LetsNotMeet", "url": "https://reddit/b", "source_body": "complete B"},
        ]}
        self.review = {"channel_id": "acc1", "top_topics": [
            {"post_id": "a", "truth_mode": "fiction", "risks": [], "shortlist_score": 9, "theme_id": "one"},
            {"post_id": "b", "truth_mode": "unverified_personal_account", "risks": [], "shortlist_score": 8, "theme_id": "two"},
        ]}

    def test_selects_two_distinct_internal_only_pilots(self):
        pilots = select_pilots(self.queue, self.review, 2, "month")
        self.assertEqual([item["source_snapshot"]["post_id"] for item in pilots], ["a", "b"])
        self.assertTrue(all(not item["publication_authorized"] for item in pilots))

    def test_open_ending_is_skipped(self):
        self.review["top_topics"][0]["risks"] = ["possible_open_ending"]
        self.assertEqual(select_pilots(self.queue, self.review, 1, "year")[0]["source_snapshot"]["post_id"], "b")

    def test_week_is_rejected(self):
        with self.assertRaises(PilotSelectionError):
            select_pilots(self.queue, self.review, 1, "week")


if __name__ == "__main__":
    unittest.main()
