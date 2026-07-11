import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pre_publish_qa
import translator_tts


ROOT = Path(__file__).resolve().parents[1]


class TtsModelContractTests(unittest.TestCase):
    def test_cli_defaults_fail_closed_on_eleven_v3(self):
        args = translator_tts.build_parser().parse_args([])
        self.assertEqual(args.model_id, "eleven_v3")
        self.assertEqual(args.require_model_id, "eleven_v3")
        self.assertEqual(args.request_metadata_output, "tts_request_metadata.json")

    def test_post_request_includes_explicit_model_id(self):
        response = SimpleNamespace(
            status_code=200,
            ok=True,
            text="",
            content=b"",
            headers={"content-type": "application/json"},
            json=lambda: {"success": True, "task_id": "safe-id"},
        )
        with patch.object(translator_tts.requests, "post", return_value=response) as mocked_post:
            translator_tts.post_tts_task(
                api_key="test-key",
                text="Short safe sample.",
                voice_id="elevenlabs_test",
                model_id="eleven_v3",
                voice_settings_json=None,
                speed=1.0,
                file_name="sample.mp3",
                with_transcript=True,
                context_chaining=False,
                receive_url=None,
                pronunciation_dictionary_id=None,
            )
        multipart = mocked_post.call_args.kwargs["files"]
        self.assertEqual(multipart["model_id"], (None, "eleven_v3"))
        self.assertEqual(mocked_post.call_args.args[0], "https://api.ai33.pro/v3/text-to-speech")

    def test_audit_metadata_records_requested_model_without_claiming_provider_confirmation(self):
        args = SimpleNamespace(
            model_id="eleven_v3",
            require_model_id="eleven_v3",
            voice_settings_json=None,
            speed=1.0,
        )
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "tts_request_metadata.json"
            data = translator_tts.write_tts_request_metadata(
                output_path=target,
                args=args,
                narrator_voice_id="elevenlabs_narrator",
                comment_voice_id="elevenlabs_comment",
                voice_mode="multi_voice",
                payloads=[{"success": True, "task_id": "safe-id"}],
            )
            saved = json.loads(target.read_text(encoding="utf-8"))
        self.assertEqual(data["requested_model_id"], "eleven_v3")
        self.assertEqual(saved["model_verification"], "provider_not_reported")
        self.assertEqual(saved["provider_reported_model_ids"], [])

    def test_provider_reported_model_mismatch_fails(self):
        args = SimpleNamespace(
            model_id="eleven_v3",
            require_model_id="eleven_v3",
            voice_settings_json=None,
            speed=1.0,
        )
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "tts_request_metadata.json"
            with self.assertRaisesRegex(translator_tts.Ai33Error, "reported model"):
                translator_tts.write_tts_request_metadata(
                    output_path=target,
                    args=args,
                    narrator_voice_id="elevenlabs_narrator",
                    comment_voice_id="elevenlabs_comment",
                    voice_mode="single_voice",
                    payloads=[{"data": {"model_id": "eleven_multilingual_v2"}}],
                )
            saved = json.loads(target.read_text(encoding="utf-8"))
        self.assertEqual(saved["model_verification"], "provider_mismatch")

    def test_pre_publish_model_status_reads_safe_audit(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "tts_request_metadata.json"
            target.write_text(
                json.dumps({
                    "requested_model_id": "eleven_v3",
                    "required_model_id": "eleven_v3",
                    "provider_reported_model_ids": [],
                    "model_verification": "provider_not_reported",
                }),
                encoding="utf-8",
            )
            status = pre_publish_qa.tts_model_status(target)
        self.assertEqual(status["requested_model_id"], "eleven_v3")
        self.assertEqual(status["model_verification"], "provider_not_reported")
        self.assertTrue(pre_publish_qa.tts_model_contract_passes(status, "eleven_v3"))
        mismatch = dict(status, model_verification="provider_mismatch")
        self.assertFalse(pre_publish_qa.tts_model_contract_passes(mismatch, "eleven_v3"))

    def test_workflows_explicitly_require_and_preserve_eleven_v3(self):
        for relative in (
            ".github/workflows/auto_publish.yml",
            ".github/workflows/video_dry_run.yml",
        ):
            workflow = (ROOT / relative).read_text(encoding="utf-8")
            self.assertIn("--model-id eleven_v3", workflow)
            self.assertIn("--require-model-id eleven_v3", workflow)
            self.assertIn("--require-tts-model eleven_v3", workflow)
            self.assertIn("tts_request_metadata.json", workflow)
        audit_workflow = (ROOT / ".github/workflows/audit_voice_youtube.yml").read_text(encoding="utf-8")
        self.assertIn("--model-id", audit_workflow)
        self.assertIn("--require-model-id eleven_v3", audit_workflow)


if __name__ == "__main__":
    unittest.main()
