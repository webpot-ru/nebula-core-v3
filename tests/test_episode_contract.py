import hashlib
import unittest

import episode_contract


def valid_script():
    body = "The bell rang three times. I opened the basement door. The shadow left at dawn."
    narration = " ".join(["страх"] * 650)
    return {
        "source_snapshot": {
            "post_id": "abc123",
            "source_url": "https://reddit.com/r/nosleep/comments/abc123/example",
            "subreddit": "nosleep",
            "title": "The basement bell",
            "body": body,
            "body_sha256": hashlib.sha256(body.encode("utf-8")).hexdigest(),
            "truth_mode": "fiction",
        },
        "disclosure": "This is a fiction story adapted from Reddit.",
        "revision_count": 0,
        "scenes": [
            {
                "scene_id": f"scene-{index:02d}",
                "narration_ru": narration,
                "source_anchors": ["The bell rang three times."],
                "invented_factual_claims": [],
                "change_ledger": [],
                "visual_beats": ["dark basement"],
            }
            for index in range(1, 7)
        ],
        "editorial_review": {"verdict": "PASS", "issues": []},
    }


class EpisodeContractTests(unittest.TestCase):
    def test_valid_long_form_fixture_passes(self):
        result = episode_contract.validate_episode_script(valid_script())
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["scene_count"], 6)
        self.assertGreaterEqual(result["estimated_minutes"], 30)

    def test_bad_anchor_blocks(self):
        script = valid_script()
        script["scenes"][0]["source_anchors"] = ["Something not in the source"]
        result = episode_contract.validate_episode_script(script)
        self.assertEqual(result["status"], "BLOCKED")
        self.assertTrue(any("anchor not found" in item for item in result["failures"]))

    def test_fiction_disclosure_is_required(self):
        script = valid_script()
        script["disclosure"] = "Based on a Reddit post."
        result = episode_contract.validate_episode_script(script)
        self.assertTrue(any("label the story as fiction" in item for item in result["failures"]))

    def test_third_revision_blocks(self):
        script = valid_script()
        script["revision_count"] = 3
        result = episode_contract.validate_episode_script(script)
        self.assertTrue(any("revision_count" in item for item in result["failures"]))

    def test_invented_factual_claim_blocks(self):
        script = valid_script()
        script["scenes"][1]["invented_factual_claims"] = ["Police confirmed the event"]
        result = episode_contract.validate_episode_script(script)
        self.assertTrue(any("invented_factual_claims" in item for item in result["failures"]))


if __name__ == "__main__":
    unittest.main()
