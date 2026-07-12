import tempfile
import unittest
from pathlib import Path

from compilation_pipeline import translate_manifest


class Provider:
    def __init__(self):
        self.calls = 0
    def __call__(self, **kwargs):
        self.calls += 1
        if "Independently compare" in kwargs["prompt"]:
            return {"verdict": "PASS", "issues": [], "ending_preserved": True}
        return {"title": "Русская история", "body": " ".join(["страх"] * 2000), "complete": True, "ending_preserved": True}


def manifest():
    return {
        "rights_mode": "test_only_not_cleared", "publication_authorized": False,
        "source_mode": "nosleep", "stories": [{
            "source_snapshot": {
                "post_id": str(index), "source_url": f"https://reddit/{index}",
                "subreddit": "r/nosleep", "title": f"Story {index}",
                "body": " ".join(["source"] * 2000),
                "body_sha256": __import__("hashlib").sha256(" ".join(["source"] * 2000).encode()).hexdigest(),
                "truth_mode": "fiction", "source_media": [],
            }
        } for index in range(1, 4)],
    }


class CompilationPipelineTests(unittest.TestCase):
    def test_completed_story_checkpoints_are_reused(self):
        provider = Provider()
        with tempfile.TemporaryDirectory() as temp:
            first = translate_manifest(manifest(), provider, checkpoint_dir=Path(temp))
            call_count = provider.calls
            second = translate_manifest(manifest(), provider, checkpoint_dir=Path(temp))
        self.assertEqual(first["contract_validation"]["status"], "PASS")
        self.assertEqual(second["contract_validation"]["status"], "PASS")
        self.assertEqual(provider.calls, call_count)


if __name__ == "__main__":
    unittest.main()
