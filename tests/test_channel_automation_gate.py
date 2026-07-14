import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from scripts.check_channel_automation import check_channel_automation


ROOT = Path(__file__).resolve().parents[1]


class ChannelAutomationGateTests(unittest.TestCase):
    def test_explicit_disabled_flag_blocks(self):
        config = {"channels": [{
            "id": "acc1", "automation_enabled": False, "videos_per_day": 2,
        }]}
        with self.assertRaisesRegex(ValueError, "automation_enabled=false"):
            check_channel_automation(config, "acc1")

    def test_zero_videos_blocks_even_without_flag(self):
        config = {"channels": [{"id": "acc1", "videos_per_day": 0}]}
        with self.assertRaisesRegex(ValueError, "greater than zero"):
            check_channel_automation(config, "acc1")

    def test_legacy_enabled_channel_remains_compatible(self):
        result = check_channel_automation(
            {"channels": [{"id": "acc2", "videos_per_day": 2}]}, "acc2",
        )
        self.assertTrue(result["automation_allowed"])

    def test_current_acc1_config_fails_before_legacy_publish(self):
        completed = subprocess.run(
            [
                "python3", "scripts/check_channel_automation.py",
                "--channels", "channels.json", "--channel", "acc1",
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
        )
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("automation_enabled=false", completed.stderr)

    def test_cli_allows_enabled_fixture(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "channels.json"
            path.write_text(json.dumps({
                "channels": [{"id": "acc2", "videos_per_day": 1}],
            }), encoding="utf-8")
            completed = subprocess.run(
                [
                    "python3", "scripts/check_channel_automation.py",
                    "--channels", str(path), "--channel", "acc2",
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
            )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn('"automation_allowed": true', completed.stdout)

    def test_legacy_workflow_runs_gate_before_token_or_reddit_steps(self):
        workflow = (ROOT / ".github/workflows/auto_publish.yml").read_text(
            encoding="utf-8",
        )
        gate = workflow.index("Enforce channel automation gate")
        token = workflow.index("Verify YouTube channel token")
        reddit = workflow.index("Fetch viral story from Reddit")
        self.assertLess(gate, token)
        self.assertLess(gate, reddit)
        self.assertIn("scripts/check_channel_automation.py", workflow)


if __name__ == "__main__":
    unittest.main()
