import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = (ROOT / ".github/workflows/acc1_private_upload.yml").read_text(encoding="utf-8")


class Acc1PrivateUploadWorkflowTests(unittest.TestCase):
    def test_is_manual_private_only_and_has_no_paid_generation_secrets(self):
        self.assertIn("workflow_dispatch:", WORKFLOW)
        self.assertNotIn("schedule:", WORKFLOW)
        self.assertIn("--privacy-status private", WORKFLOW)
        self.assertNotIn("REDDIT_", WORKFLOW)
        self.assertNotIn("GEMINI_", WORKFLOW)
        self.assertNotIn("OPENAI_", WORKFLOW)
        self.assertNotIn("AI33_", WORKFLOW)

    def test_requires_exact_reviewed_factory_artifact(self):
        for token in (
            "confirm_private_upload",
            "expected_manifest_sha256",
            "acc1 Daily Episode Factory",
            "release_candidate_manifest_sha256",
            "READY_FOR_HUMAN_REVIEW",
            "media_qa_status",
            "video_sha256",
            "thumbnail_sha256",
            "metadata_sha256",
        ):
            self.assertIn(token, WORKFLOW)

    def test_keeps_account_mapping_and_post_upload_readback_fail_closed(self):
        self.assertIn("--check-channel-only --account-index 1", WORKFLOW)
        self.assertIn("YOUTUBE_REFRESH_TOKEN_ACC1", WORKFLOW)
        self.assertIn('receipt.get("privacy_status_readback") != "private"', WORKFLOW)
        self.assertIn('receipt.get("thumbnail_uploaded") is not True', WORKFLOW)
        self.assertNotIn("--skip-channel-check", WORKFLOW)
        self.assertNotIn("git push", WORKFLOW)


if __name__ == "__main__":
    unittest.main()
