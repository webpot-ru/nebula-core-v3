import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock
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
            "--caption-file", "captions.srt",
            "--caption-language", "ru",
            "--caption-name", "Русский",
            "--result", "receipt.json",
        ])
        self.assertEqual(args.privacy_status, "private")
        self.assertEqual(args.metadata_file, "metadata.json")
        self.assertEqual(args.thumbnail_file, "thumbnail.png")
        self.assertEqual(args.caption_file, "captions.srt")
        self.assertEqual(args.caption_language, "ru")
        self.assertEqual(args.caption_name, "Русский")
        self.assertEqual(args.result, "receipt.json")

    def test_uploads_and_reads_back_selectable_caption_track(self):
        class Executable:
            def __init__(self, payload):
                self.payload = payload

            def execute(self):
                return self.payload

        class InsertRequest:
            def next_chunk(self):
                return None, {"id": "video-123"}

        class Videos:
            def insert(self, **_kwargs):
                return InsertRequest()

        class Thumbnails:
            def set(self, **_kwargs):
                return Executable({"items": [{"default": {}}]})

        class Captions:
            def insert(self, **_kwargs):
                return Executable({"id": "caption-123"})

            def list(self, **_kwargs):
                return Executable({
                    "items": [{
                        "id": "caption-123",
                        "snippet": {
                            "videoId": "video-123",
                            "language": "ru",
                        },
                    }],
                })

        class YouTube:
            def videos(self):
                return Videos()

            def thumbnails(self):
                return Thumbnails()

            def captions(self):
                return Captions()

        googleapiclient = types.ModuleType("googleapiclient")
        googleapiclient_http = types.ModuleType("googleapiclient.http")
        googleapiclient_http.MediaFileUpload = lambda *args, **kwargs: {
            "args": args,
            "kwargs": kwargs,
        }

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            video = root / "video.mp4"
            thumbnail = root / "thumbnail.jpg"
            caption = root / "captions.srt"
            receipt = root / "receipt.json"
            video.write_bytes(b"video")
            thumbnail.write_bytes(b"thumbnail")
            caption.write_text(
                "1\n00:00:00,000 --> 00:00:01,000\nТест\n",
                encoding="utf-8",
            )
            expected_caption_sha256 = uploader._sha256_file(caption)
            with (
                mock.patch.dict(sys.modules, {
                    "googleapiclient": googleapiclient,
                    "googleapiclient.http": googleapiclient_http,
                }),
                mock.patch.object(
                    uploader,
                    "get_youtube_service",
                    return_value=YouTube(),
                ),
                mock.patch.object(
                    uploader,
                    "read_video_metadata",
                    return_value={
                        "snippet": {"channelId": "channel-123"},
                        "status": {"privacyStatus": "private"},
                    },
                ),
            ):
                uploader.upload_video(
                    str(video),
                    "Заголовок",
                    "Описание",
                    privacy_status="private",
                    language="ru",
                    verify_channel=False,
                    thumbnail_file=str(thumbnail),
                    caption_file=str(caption),
                    caption_language="ru",
                    caption_name="Русский",
                    result_path=str(receipt),
                )
            state = json.loads(receipt.read_text(encoding="utf-8"))

        self.assertEqual(state["status"], "COMPLETE")
        self.assertTrue(state["thumbnail_uploaded"])
        self.assertTrue(state["caption_uploaded"])
        self.assertEqual(state["caption_id"], "caption-123")
        self.assertEqual(state["caption_language_readback"], "ru")
        self.assertEqual(state["caption_sha256"], expected_caption_sha256)

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
