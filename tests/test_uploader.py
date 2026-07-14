import json
import tempfile
import unittest
from pathlib import Path
import uploader


class UploaderTests(unittest.TestCase):
    def test_metadata_can_be_loaded_from_exact_artifact_path(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "metadata.json"
            path.write_text(json.dumps({
                "youtube_title": "Exact title",
                "youtube_description": "Exact description",
                "tags": ["reddit", "истории"],
                "language": "ru",
            }), encoding="utf-8")
            title, description, tags, language = uploader.load_upload_metadata(
                metadata_file=str(path),
                story_file=str(Path(temp) / "missing.json"),
            )
        self.assertEqual(title, "Exact title")
        self.assertEqual(description, "Exact description")
        self.assertEqual(tags, ["reddit", "истории"])
        self.assertEqual(language, "ru")

    def test_cli_passes_private_thumbnail_and_receipt_paths(self):
        args = uploader.parse_args([
            "video.mp4", "1", "--privacy-status", "private",
            "--metadata-file", "metadata.json",
            "--thumbnail-file", "thumbnail.png",
            "--result", "receipt.json",
        ])
        self.assertEqual(args.privacy_status, "private")
        self.assertEqual(args.metadata_file, "metadata.json")
        self.assertEqual(args.thumbnail_file, "thumbnail.png")
        self.assertEqual(args.result, "receipt.json")

    def test_upload_state_is_atomic_and_contains_no_credentials(self):
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / "receipt.json"
            uploader._write_upload_state(target, {
                "status": "VIDEO_CREATED",
                "video_id": "abc123",
                "privacy_status_requested": "private",
            })
            payload = json.loads(target.read_text(encoding="utf-8"))
        self.assertEqual(payload["video_id"], "abc123")
        self.assertEqual(payload["privacy_status_requested"], "private")


if __name__ == "__main__":
    unittest.main()
