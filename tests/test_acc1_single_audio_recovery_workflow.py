import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/acc1_single_audio_recovery.yml"


class SingleAudioRecoveryWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workflow = WORKFLOW.read_text(encoding="utf-8")

    def test_uses_segment_matrix_and_separate_assembly(self):
        self.assertIn("  prepare:\n", self.workflow)
        self.assertIn("  render:\n", self.workflow)
        self.assertIn("  assemble:\n", self.workflow)
        self.assertIn("max-parallel: 8", self.workflow)
        self.assertIn("--prepare-segmented", self.workflow)
        self.assertIn("--render-segment", self.workflow)
        self.assertIn("--assemble-segmented", self.workflow)

    def test_preparation_installs_ffprobe_before_audio_validation(self):
        prepare = self.workflow.split("\n  render:\n", 1)[0]
        install = prepare.index("sudo apt-get install -y ffmpeg")
        poll = prepare.index("Poll existing AI33 task")
        self.assertLess(install, poll)
        self.assertIn("ffprobe -version", prepare)

    def test_render_does_not_run_project_scoped_info_before_workspace_exists(self):
        render = self.workflow.split("\n  render:\n", 1)[1].split("\n  assemble:\n", 1)[0]
        self.assertNotIn("hyperframes@0.7.61 info", render)
        self.assertIn("@puppeteer/browsers install chrome-headless-shell@stable", render)
        self.assertIn("--render-segment", render)

    def test_provider_key_is_available_only_during_saved_task_poll(self):
        prepare, render = self.workflow.split("\n  render:\n", 1)
        render, assemble = render.split("\n  assemble:\n", 1)
        self.assertIn("AI33_API_KEY", prepare)
        self.assertNotIn("AI33_API_KEY", render)
        self.assertNotIn("AI33_API_KEY", assemble)
        self.assertNotIn("VECTORENGINE", self.workflow.upper())
        self.assertNotIn("YOUTUBE_CLIENT", self.workflow.upper())
        self.assertNotIn("YOUTUBE_TOKEN", self.workflow.upper())

    def test_never_uploads_complete_workspace_or_failure_cache(self):
        self.assertNotIn("if: always()", self.workflow)
        self.assertNotIn(
            "path: ${{ env.WORKDIR }}\n          if-no-files-found",
            self.workflow,
        )
        self.assertIn("render-segments/segment-*.mp4", self.workflow)
        self.assertIn("final-output-single-audio.mp4", self.workflow)
        self.assertIn("retention-days: 1", self.workflow)


if __name__ == "__main__":
    unittest.main()
