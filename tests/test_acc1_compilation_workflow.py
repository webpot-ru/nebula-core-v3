import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class Acc1CompilationWorkflowTests(unittest.TestCase):
    def test_workflow_is_artifact_only_and_fail_closed(self):
        workflow = (ROOT / ".github/workflows/acc1_compilation_pilot.yml").read_text(encoding="utf-8")
        for required in (
            "permissions:\n  contents: read", "confirm_provider_spend", "AI_QUALITY_CHECK: \"0\"",
            "--no-save-history", "GEMINI_TRANSLATION_MAX_OUTPUT_TOKENS: \"16384\"",
            "--model gpt-image-2", "--model-id eleven_v3", "compilation_qa.py", "if: always()",
        ):
            self.assertIn(required, workflow)
        for forbidden in ("uploader.py", "YOUTUBE_REFRESH_TOKEN", "youtube.upload", "git push", "published_history.json"):
            self.assertNotIn(forbidden, workflow)


if __name__ == "__main__":
    unittest.main()
