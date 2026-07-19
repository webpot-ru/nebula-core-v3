import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = (ROOT / ".github/workflows/acc1_release_review.yml").read_text(encoding="utf-8")


class Acc1ReleaseReviewWorkflowTests(unittest.TestCase):
    def test_is_manual_no_provider_no_upload(self):
        self.assertIn("workflow_dispatch:", WORKFLOW)
        self.assertNotIn("schedule:", WORKFLOW)
        self.assertNotIn("uploader.py", WORKFLOW)
        self.assertNotIn("YOUTUBE_", WORKFLOW)
        self.assertNotIn("GEMINI_", WORKFLOW)
        self.assertNotIn("AI33_", WORKFLOW)

    def test_requires_exact_factory_human_and_rights_evidence(self):
        for token in (
            "confirm_release_review",
            "source_run_id",
            "expected_manifest_sha256",
            "release-reviews/acc1/",
            "creative-review.json",
            "rights-manifest.json",
            "acc1 Daily Episode Factory",
            "--factory-artifact-root",
            "--factory-creative-review",
            "--rights-manifest",
            "READY_FOR_PRIVATE_REVIEW",
            "release_gate_sha256",
            "acc1-release-gate-${{ github.run_id }}",
        ):
            self.assertIn(token, WORKFLOW)

    def test_release_gate_preserves_no_upload_no_publication_ceiling(self):
        self.assertIn('report.get("publication_authorized") is not False', WORKFLOW)
        self.assertIn('report.get("upload_authorized") is not False', WORKFLOW)
        self.assertIn("if-no-files-found: error", WORKFLOW)


if __name__ == "__main__":
    unittest.main()
