import hashlib
import json
import unittest
from pathlib import Path

from PIL import Image

import uploader


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_PATH = (
    ROOT / ".github/workflows/acc1_fixed_first_release_private_upload.yml"
)
PACKAGE_ROOT = ROOT / "release-packages/acc1/fixed-first-release-v1"
WORKFLOW = WORKFLOW_PATH.read_text(encoding="utf-8")


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class FixedFirstReleasePrivateUploadWorkflowTests(unittest.TestCase):
    def test_is_manual_one_attempt_private_only_and_has_no_provider_surface(self):
        self.assertIn("workflow_dispatch:", WORKFLOW)
        self.assertNotIn("schedule:", WORKFLOW)
        self.assertIn('test "$SOURCE_RUN_ID" = "30187749091"', WORKFLOW)
        self.assertIn('test "$CONFIRM_PRIVATE_UPLOAD" = "true"', WORKFLOW)
        self.assertIn('test "$RUN_ATTEMPT" = "1"', WORKFLOW)
        self.assertIn("--privacy-status private", WORKFLOW)
        self.assertNotIn("--privacy-status public", WORKFLOW)
        self.assertNotIn("--privacy-status unlisted", WORKFLOW)
        for forbidden in (
            "REDDIT_",
            "VECTORENGINE_",
            "AI33_",
            "GEMINI_",
            "OPENAI_",
            "git push",
        ):
            self.assertNotIn(forbidden, WORKFLOW)

    def test_binds_exact_reviewed_run_package_and_artifact_hashes(self):
        for token in (
            "expected_package_manifest_sha256",
            "acc1-fixed-first-release-v1",
            "acc1 Fixed First Release Recovery",
            "acc1-captioned-recovery-$SOURCE_RUN_ID",
            "source-run.json",
            "captioned_video_sha256",
            "caption_srt_sha256",
            "caption_ass_sha256",
            "caption_report_sha256",
            "caption_cue_count",
            "captions_burned",
            "ffprobe",
            "READY_FOR_HUMAN_REVIEW",
            "publication_authorized",
            "youtube_called",
        ):
            self.assertIn(token, WORKFLOW)

    def test_blocks_duplicate_and_keeps_channel_readback_fail_closed(self):
        self.assertIn("Refuse a duplicate upload receipt", WORKFLOW)
        self.assertIn(
            "acc1-fixed-private-upload-source-${{ inputs.source_run_id }}",
            WORKFLOW,
        )
        self.assertIn("get_youtube_oauth_scopes", WORKFLOW)
        self.assertIn("youtube.force-ssl", WORKFLOW)
        self.assertIn("check_channel_mapping", WORKFLOW)
        self.assertIn("UCNSxg53AGM4WstRjGiQdS8w", WORKFLOW)
        self.assertIn("YOUTUBE_REFRESH_TOKEN_ACC1", WORKFLOW)
        self.assertIn('receipt.get("privacy_status_readback") != "private"', WORKFLOW)
        self.assertIn(
            'receipt.get("channel_id") != package["channel"]["youtube_channel_id"]',
            WORKFLOW,
        )
        self.assertIn('receipt.get("thumbnail_uploaded") is not True', WORKFLOW)
        self.assertIn('receipt.get("caption_uploaded") is not True', WORKFLOW)
        self.assertIn('receipt.get("caption_language_readback") != "ru"', WORKFLOW)
        self.assertIn("--caption-file", WORKFLOW)
        self.assertNotIn("--skip-channel-check", WORKFLOW)


class FixedFirstReleasePackageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = json.loads(
            (PACKAGE_ROOT / "release-package.json").read_text(encoding="utf-8")
        )
        cls.metadata = json.loads(
            (PACKAGE_ROOT / "youtube-metadata.json").read_text(encoding="utf-8")
        )

    def test_package_is_private_review_only_and_bound_to_verified_master(self):
        self.assertEqual(
            self.manifest["status"],
            "PRIVATE_REVIEW_PACKAGE_READY",
        )
        self.assertEqual(self.manifest["source_run"]["run_id"], "30187749091")
        self.assertEqual(
            self.manifest["source_run"]["artifact_name"],
            "acc1-captioned-recovery-30187749091",
        )
        self.assertEqual(
            self.manifest["media"]["video_sha256"],
            "933337045776fe86cb8aef2ddad37e09a752525fc99c1b4bd8e6d71aad846f33",
        )
        self.assertEqual(self.manifest["media"]["caption_cue_count"], 263)
        self.assertTrue(self.manifest["media"]["captions_burned"])
        self.assertTrue(self.manifest["media"]["selectable_caption_upload"])
        self.assertEqual(
            self.manifest["media"]["selectable_caption_language"],
            "ru",
        )
        self.assertFalse(self.manifest["boundaries"]["private_upload_authorized"])
        self.assertFalse(self.manifest["boundaries"]["publication_authorized"])
        self.assertFalse(self.manifest["boundaries"]["youtube_called"])
        self.assertFalse(self.manifest["boundaries"]["public_or_unlisted_path"])
        self.assertEqual(
            self.manifest["review"]["rights_status"],
            "not_verified_for_publication",
        )

    def test_metadata_hash_schema_chapters_sources_and_disclosure(self):
        metadata_info = self.manifest["metadata"]
        metadata_path = PACKAGE_ROOT / metadata_info["file"]
        self.assertEqual(file_sha256(metadata_path), metadata_info["sha256"])

        title, description, tags, language = uploader.load_upload_metadata(
            metadata_file=str(metadata_path),
            story_file=str(PACKAGE_ROOT / "missing-story.json"),
        )
        self.assertEqual(title, self.manifest["variants"][0]["title"])
        self.assertLessEqual(len(title), 100)
        self.assertLessEqual(len(description), 5000)
        self.assertEqual(language, "ru")
        self.assertGreaterEqual(len(tags), 12)

        for token in (
            "00:00 ",
            "00:10 ",
            "04:07 ",
            "07:41 ",
            "10:59 ",
            "14:20 ",
            "не подтверждены независимо",
            "reddit.com/r/relationship_advice/comments/1uw7804/",
            "reddit.com/r/offmychest/comments/1v0l1ei/",
            "reddit.com/r/relationship_advice/comments/1uy2j23/",
            "reddit.com/r/AmItheAsshole/comments/1uviexk/",
            "#ИсторииReddit",
            "#СемейныеИстории",
            "#ИсторииНаРусском",
        ):
            self.assertIn(token, description)

    def test_three_paired_variants_have_exact_upload_safe_images(self):
        variants = self.manifest["variants"]
        metadata_variants = self.metadata["ab_test_variants"]
        self.assertEqual([item["id"] for item in variants], ["A", "B", "C"])
        self.assertEqual(
            [
                (item["id"], item["title"], item["thumbnail"])
                for item in variants
            ],
            [
                (item["id"], item["title"], item["thumbnail"])
                for item in metadata_variants
            ],
        )
        self.assertEqual(len({item["title"] for item in variants}), 3)

        for item in variants:
            self.assertLessEqual(len(item["title"]), 100)
            thumbnail = PACKAGE_ROOT / item["thumbnail"]
            self.assertTrue(thumbnail.is_file())
            self.assertEqual(file_sha256(thumbnail), item["thumbnail_sha256"])
            self.assertEqual(thumbnail.stat().st_size, item["thumbnail_size_bytes"])
            self.assertLess(thumbnail.stat().st_size, 2 * 1024 * 1024)
            with Image.open(thumbnail) as image:
                self.assertEqual(image.size, (1280, 720))
                self.assertEqual(image.format, "JPEG")


if __name__ == "__main__":
    unittest.main()
