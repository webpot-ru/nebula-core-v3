import unittest

from scripts.select_acc1_pilots import PilotSelectionError, select_compilation


class Acc1PilotSelectionTests(unittest.TestCase):
    def setUp(self):
        self.queue = {"channel_id": "acc1", "entries": []}
        self.review = {"channel_id": "acc1", "top_topics": []}
        for index in range(1, 5):
            post_id = f"n{index}"
            self.queue["entries"].append({"post_id": post_id, "title": post_id, "subreddit": "r/nosleep", "url": f"https://reddit/{post_id}", "source_body": " ".join([f"complete-{post_id}"] * 2000), "source_media": []})
            self.review["top_topics"].append({"post_id": post_id, "truth_mode": "fiction", "risks": [], "shortlist_score": 10-index, "theme_id": f"theme-{index}"})

    def test_selects_three_distinct_internal_only_stories(self):
        compilation = select_compilation(self.queue, self.review, 3, "month", "nosleep")
        self.assertEqual([item["source_snapshot"]["post_id"] for item in compilation["stories"]], ["n1", "n2", "n3"])
        self.assertFalse(compilation["publication_authorized"])

    def test_open_ending_is_skipped(self):
        self.review["top_topics"][0]["risks"] = ["possible_open_ending"]
        compilation = select_compilation(self.queue, self.review, 3, "year", "nosleep")
        self.assertNotIn("n1", [item["source_snapshot"]["post_id"] for item in compilation["stories"]])

    def test_week_is_rejected(self):
        with self.assertRaises(PilotSelectionError):
            select_compilation(self.queue, self.review, 3, "week", "nosleep")


if __name__ == "__main__":
    unittest.main()
