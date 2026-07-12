import hashlib
import tempfile
import unittest
from pathlib import Path

from compilation_qa import run_qa


def fixture_compilation():
    stories = []
    for index in range(1, 4):
        body = f"Source body {index}. Ending {index}."
        stories.append({
            "title_ru": f"История {index}",
            "narration_ru": " ".join(["страх"] * 2000),
            "disclosure": "This is fiction from Reddit.",
            "ending_preserved_evidence": f"Ending {index}.",
            "change_ledger": [],
            "invented_factual_claims": [],
            "editorial_review": {"verdict": "PASS", "issues": []},
            "source_snapshot": {
                "post_id": str(index), "source_url": f"https://reddit/{index}",
                "subreddit": "r/nosleep", "title": f"Story {index}", "body": body,
                "body_sha256": hashlib.sha256(body.encode()).hexdigest(),
                "truth_mode": "fiction", "source_media": [],
            },
        })
    return {
        "rights_mode": "test_only_not_cleared", "publication_authorized": False,
        "revision_count": 0, "stories": stories,
        "editorial_review": {"verdict": "PASS", "issues": []},
    }


class CompilationQaTests(unittest.TestCase):
    def test_passes_complete_artifact_contract(self):
        compilation = fixture_compilation()
        metadata = {
            "packaging_options": [
                {"youtube_title": f"Title {i}", "thumbnail_text": f"Text {i}", "angle": f"angle-{i}"}
                for i in range(3)
            ],
            "youtube_description": " ".join(f"https://reddit/{i}" for i in range(1, 4)),
            "language": "ru",
        }
        chunks = [{"status": "COMPLETE", "model_id": "eleven_v3", "audio_sha256": "a" * 64}]
        tts = {"status": "COMPLETE", "required_model_id": "eleven_v3", "chunks": chunks, "final_audio_sha256": "b" * 64}
        storyboard = {"format": "compilation_16x9", "resolution": [1920, 1080], "slides": [{"slide_id": "intro", "kind": "title"}]}
        report = {"status": "ok", "resolution": [1920, 1080], "audio_merged": True, "duration_sec": 3000, "audio_duration_sec": 3000}
        with tempfile.TemporaryDirectory() as temp:
            result = run_qa(compilation, metadata, tts, storyboard, report, artifact_root=Path(temp))
        self.assertEqual(result["status"], "PASS", result["failures"])

    def test_blocks_wrong_model_and_missing_source_url(self):
        compilation = fixture_compilation()
        metadata = {"packaging_options": [], "youtube_description": "", "language": "ru"}
        tts = {"status": "COMPLETE", "required_model_id": "eleven_v2", "chunks": [], "final_audio_sha256": ""}
        storyboard = {"format": "compilation_16x9", "resolution": [1920, 1080], "slides": [{"slide_id": "intro", "kind": "title"}]}
        report = {"status": "failed"}
        with tempfile.TemporaryDirectory() as temp:
            result = run_qa(compilation, metadata, tts, storyboard, report, artifact_root=Path(temp))
        self.assertEqual(result["status"], "BLOCKED")
        self.assertTrue(any("eleven_v3" in item for item in result["failures"]))


if __name__ == "__main__":
    unittest.main()
