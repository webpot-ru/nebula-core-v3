import tempfile
import unittest
from pathlib import Path

from scripts.build_acc1_creative_review_template import CHECKS, build_template


class Acc1CreativeReviewTemplateTests(unittest.TestCase):
    def test_template_is_checksum_bound_and_fail_closed(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            video = root / "video.mp4"
            thumbnail = root / "thumbnail.png"
            video.write_bytes(b"video")
            thumbnail.write_bytes(b"thumbnail")
            payload = build_template(video, thumbnail)
        self.assertEqual(payload["status"], "BLOCKED")
        self.assertFalse(payload["publication_authorized"])
        self.assertEqual(len(payload["video_sha256"]), 64)
        self.assertEqual(len(payload["thumbnail_sha256"]), 64)
        self.assertEqual(payload["checks"], {field: False for field in CHECKS})

    def test_missing_artifact_fails(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            video = root / "missing.mp4"
            thumbnail = root / "missing.png"
            with self.assertRaises(FileNotFoundError):
                build_template(video, thumbnail)


if __name__ == "__main__":
    unittest.main()
