import hashlib
import unittest

import episode_contract


def valid_script():
    body = "The bell rang three times. I opened the basement door. The shadow left at dawn."
    narration = " ".join(["страх"] * 2000)
    snapshot = {
        "post_id": "abc123",
        "source_url": "https://reddit.com/r/nosleep/comments/abc123/example",
        "subreddit": "r/nosleep",
        "title": "The basement bell",
        "body": body,
        "body_sha256": hashlib.sha256(body.encode("utf-8")).hexdigest(),
        "truth_mode": "fiction",
        "source_media": [],
    }
    return {
        "rights_mode": "test_only_not_cleared",
        "publication_authorized": False,
        "revision_count": 0,
        "stories": [
            {
                "source_snapshot": snapshot | {"post_id": f"abc{index}"},
                "narration_ru": narration,
                "invented_factual_claims": [],
                "change_ledger": [],
                "ending_preserved_evidence": "The shadow left at dawn.",
                "disclosure": "This is a fiction story adapted from Reddit.",
                "editorial_review": {"verdict": "PASS", "issues": []},
            }
            for index in range(1, 4)
        ],
        "editorial_review": {"verdict": "PASS", "issues": []},
    }


class EpisodeContractTests(unittest.TestCase):
    def test_valid_long_form_fixture_passes(self):
        result = episode_contract.validate_compilation(valid_script())
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["story_count"], 3)
        self.assertGreaterEqual(result["estimated_minutes"], 45)

    def test_duplicate_post_blocks(self):
        script = valid_script()
        script["stories"][1]["source_snapshot"]["post_id"] = script["stories"][0]["source_snapshot"]["post_id"]
        result = episode_contract.validate_compilation(script)
        self.assertEqual(result["status"], "BLOCKED")
        self.assertTrue(any("duplicate post_id" in item for item in result["failures"]))

    def test_fiction_disclosure_is_required(self):
        script = valid_script()
        script["stories"][0]["disclosure"] = "Based on a Reddit post."
        result = episode_contract.validate_compilation(script)
        self.assertTrue(any("label the story as fiction" in item for item in result["failures"]))

    def test_third_revision_blocks(self):
        script = valid_script()
        script["revision_count"] = 3
        result = episode_contract.validate_compilation(script)
        self.assertTrue(any("revision_count" in item for item in result["failures"]))

    def test_invented_factual_claim_blocks(self):
        script = valid_script()
        script["stories"][1]["invented_factual_claims"] = ["Police confirmed the event"]
        result = episode_contract.validate_compilation(script)
        self.assertTrue(any("invented_factual_claims" in item for item in result["failures"]))

    def test_raw_url_in_narration_blocks(self):
        script = valid_script()
        script["stories"][0]["narration_ru"] += " https://example.com"
        result = episode_contract.validate_compilation(script)
        self.assertTrue(any("raw URL" in item for item in result["failures"]))


if __name__ == "__main__":
    unittest.main()
