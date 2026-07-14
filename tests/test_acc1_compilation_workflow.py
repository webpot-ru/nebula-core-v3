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
            "thumbnail_generator.py", "--base-image", "--report build/acc1-pilot/thumbnail-report.json",
            "--thumbnail build/acc1-pilot/youtube-thumbnail.png", "--expected-voice-id \"$VOICE_ID\"",
            "build_acc1_creative_review_template.py", "visuals_per_story:",
            "--images-per-story '${{ inputs.visuals_per_story }}'",
            "assets/acc1/video/chonker-reading-loop-v1.mp4",
            "--background-video build/acc1-pilot/chonker-reading-loop-v1.mp4",
        ):
            self.assertIn(required, workflow)
        for forbidden in ("uploader.py", "YOUTUBE_REFRESH_TOKEN", "youtube.upload", "git push", "published_history.json"):
            self.assertNotIn(forbidden, workflow)

    def test_registered_source_workflow_can_carry_branch_pilot(self):
        workflow = (ROOT / ".github/workflows/reddit_source_smoke.yml").read_text(encoding="utf-8")
        for required in (
            "run_compilation_pilot:", "confirm_provider_spend:",
            "resume_artifact_run_id:", "Restore compatible translation checkpoints",
            "if: inputs.run_compilation_pilot", "--model gpt-image-2",
            "--model-id eleven_v3", "compilation_qa.py",
            "thumbnail_generator.py", "--thumbnail /tmp/reddit-source-smoke/youtube-thumbnail.png",
            "--expected-voice-id \"$VOICE_ID\"", "build_acc1_creative_review_template.py",
            "acc1_visuals_per_story:",
            "--images-per-story \"${{ inputs.acc1_visuals_per_story }}\"",
            "assets/acc1/video/chonker-reading-loop-v1.mp4",
            "--background-video /tmp/reddit-source-smoke/chonker-reading-loop-v1.mp4",
            "Require compatible acc1 horror compilation scope",
            "test '${{ inputs.topic_family }}' = 'dark_curiosity'",
            "test '${{ inputs.format_intent }}' = 'long'",
            "test '${{ inputs.acc1_pilot_id }}' = 'none'",
            "Build acc1 horror compilation manifest",
        ):
            self.assertIn(required, workflow)
        self.assertNotIn("if: always() && inputs.channel == 'acc1'", workflow)


if __name__ == "__main__":
    unittest.main()
