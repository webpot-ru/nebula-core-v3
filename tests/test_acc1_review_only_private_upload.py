import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from scripts.acc1_review_only_private_upload import (
    EXPECTED_ACC1_CHANNEL_ID,
    REVIEW_DESCRIPTION_PREFIX,
    REVIEW_TITLE_PREFIX,
    ReviewOnlyUploadError,
    canonical_hash,
    prepare_review_upload,
    verify_upload_receipt,
)


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = (
    ROOT / ".github/workflows/acc1_review_only_private_upload.yml"
).read_text(encoding="utf-8")


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def self_hashed(payload: dict, field: str) -> dict:
    output = dict(payload)
    output[field] = canonical_hash(output)
    return output


def build_fixture(root: Path) -> dict[str, Path]:
    artifact = root / "artifact"
    artifact.mkdir()
    video = artifact / "final-output.mp4"
    thumbnail = artifact / "youtube-thumbnail.png"
    metadata = artifact / "youtube-metadata.json"
    video.write_bytes(b"verified-video")
    thumbnail.write_bytes(b"verified-thumbnail")
    write_json(metadata, {
        "youtube_title": "Три истории, после которых семья уже не будет прежней",
        "youtube_description": "Три законченные истории Reddit на русском.",
        "tags": ["истории reddit", "семейные истории"],
        "hashtags": ["ИсторииReddit"],
        "language": "ru",
    })
    artifact_hashes = {
        "video_sha256": file_hash(video),
        "thumbnail_sha256": file_hash(thumbnail),
        "metadata_sha256": file_hash(metadata),
    }

    media_qa = {
        "status": "PASS",
        "failures": [],
        "publication_authorized": False,
        "artifact_sha256": artifact_hashes,
    }
    media_qa_path = artifact / "media-qa.json"
    write_json(media_qa_path, media_qa)

    plan = self_hashed({
        "version": 1,
        "episode_key": "2026-07-30:pilot_01",
    }, "episode_plan_sha256")
    write_json(artifact / "episode-plan.json", plan)

    manifest = self_hashed({
        "version": 2,
        "status": "READY_FOR_HUMAN_REVIEW",
        "publication_authorized": False,
        "performance_outcome_guaranteed": False,
        "media_qa_status": "PASS",
        "creative_review_status": "BLOCKED_PENDING_HUMAN",
        "episode_plan_sha256": plan["episode_plan_sha256"],
        "artifact_sha256": artifact_hashes,
        "evidence_sha256": {
            "media_qa": file_hash(media_qa_path),
        },
    }, "release_candidate_manifest_sha256")
    write_json(artifact / "release-candidate-manifest.json", manifest)
    write_json(artifact / "factory-result.json", {
        "version": 2,
        "status": "READY_FOR_HUMAN_REVIEW",
        "publication_authorized": False,
        "episode_plan_sha256": plan["episode_plan_sha256"],
        "release_candidate_manifest_sha256": (
            manifest["release_candidate_manifest_sha256"]
        ),
    })

    source_run = root / "source-run.json"
    write_json(source_run, {
        "workflowName": "acc1 Daily Episode Factory",
        "conclusion": "success",
        "event": "workflow_dispatch",
        "headBranch": "main",
        "headSha": "a" * 40,
    })
    channels = root / "channels.json"
    write_json(channels, {
        "channels": [{
            "id": "acc1",
            "handle": "@ChonkerTalksRussia",
            "videos_per_day": 0,
            "automation_enabled": False,
        }],
    })
    return {
        "artifact": artifact,
        "source_run": source_run,
        "channels": channels,
        "metadata_output": root / "review-metadata.json",
        "contract_output": root / "review-contract.json",
    }


class Acc1ReviewOnlyPrivateUploadWorkflowTests(unittest.TestCase):
    def test_workflow_is_manual_private_only_and_has_no_provider_path(self):
        self.assertIn("workflow_dispatch:", WORKFLOW)
        self.assertNotIn("schedule:", WORKFLOW)
        self.assertEqual(WORKFLOW.count("--privacy-status private"), 1)
        self.assertNotIn("--privacy-status public", WORKFLOW)
        self.assertNotIn("--privacy-status unlisted", WORKFLOW)
        for token in (
            "REDDIT_",
            "GEMINI_",
            "OPENAI_",
            "VECTORENGINE_",
            "AI33_",
        ):
            self.assertNotIn(token, WORKFLOW)
        self.assertNotIn("-r requirements.txt", WORKFLOW)
        self.assertNotIn("published_history", WORKFLOW)

    def test_workflow_is_exact_source_bound_and_duplicate_safe(self):
        for token in (
            "confirm_review_only_private_upload",
            'test "$RUN_ATTEMPT" = "1"',
            "acc1 Daily Episode Factory",
            "EXPECTED_SOURCE_BRANCH",
            "acc1-daily-episode-$SOURCE_RUN_ID",
            "prior-upload-artifacts.json",
            "duplicate YouTube upload blocked",
            "review-only-upload-contract.json",
        ):
            self.assertIn(token, WORKFLOW)

    def test_workflow_keeps_channel_and_readback_fail_closed(self):
        for token in (
            "YOUTUBE_REFRESH_TOKEN_ACC1",
            "check_channel_mapping",
            EXPECTED_ACC1_CHANNEL_ID,
            "verify-receipt",
            "review-only-upload-result.json",
            "youtube-review-only-upload.json",
        ):
            self.assertIn(token, WORKFLOW)
        self.assertNotIn("--skip-channel-check", WORKFLOW)
        self.assertNotIn("--caption-file", WORKFLOW)
        self.assertNotIn("gh workflow run", WORKFLOW)


class Acc1ReviewOnlyPrivateUploadContractTests(unittest.TestCase):
    def prepare(self, root: Path) -> tuple[dict, dict[str, Path]]:
        paths = build_fixture(root)
        contract = prepare_review_upload(
            artifact_root=paths["artifact"],
            source_run_path=paths["source_run"],
            source_run_id="30518556386",
            expected_branch="main",
            channels_path=paths["channels"],
            metadata_output=paths["metadata_output"],
            contract_output=paths["contract_output"],
        )
        return contract, paths

    def test_prepares_marked_metadata_and_non_publication_contract(self):
        with tempfile.TemporaryDirectory() as directory:
            contract, paths = self.prepare(Path(directory))
            metadata = json.loads(
                paths["metadata_output"].read_text(encoding="utf-8")
            )

        self.assertEqual(
            contract["status"],
            "READY_FOR_REVIEW_ONLY_PRIVATE_UPLOAD",
        )
        self.assertTrue(contract["review_only"])
        self.assertFalse(contract["publication_authorized"])
        self.assertFalse(contract["scheduling_authorized"])
        self.assertFalse(contract["provider_calls_authorized"])
        self.assertEqual(
            contract["target"]["youtube_channel_id"],
            EXPECTED_ACC1_CHANNEL_ID,
        )
        self.assertEqual(contract["target"]["privacy_status"], "private")
        self.assertTrue(metadata["youtube_title"].startswith(REVIEW_TITLE_PREFIX))
        self.assertTrue(
            metadata["youtube_description"].startswith(REVIEW_DESCRIPTION_PREFIX)
        )
        self.assertTrue(metadata["review_only"])
        self.assertFalse(metadata["publication_authorized"])

    def test_tampered_video_is_blocked(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = build_fixture(root)
            (paths["artifact"] / "final-output.mp4").write_bytes(b"tampered")
            with self.assertRaisesRegex(
                ReviewOnlyUploadError,
                "video_sha256",
            ):
                prepare_review_upload(
                    artifact_root=paths["artifact"],
                    source_run_path=paths["source_run"],
                    source_run_id="30518556386",
                    expected_branch="main",
                    channels_path=paths["channels"],
                    metadata_output=paths["metadata_output"],
                    contract_output=paths["contract_output"],
                )

    def test_private_receipt_is_verified_and_public_receipt_is_blocked(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            contract, paths = self.prepare(root)
            receipt_path = root / "receipt.json"
            result_path = root / "result.json"
            receipt = {
                "status": "COMPLETE",
                "video_id": "abc123XYZ_0",
                "privacy_status_requested": "private",
                "privacy_status_readback": "private",
                "channel_id": EXPECTED_ACC1_CHANNEL_ID,
                "thumbnail_uploaded": True,
                "caption_uploaded": False,
                "video_sha256": contract["artifact_sha256"]["video_sha256"],
                "thumbnail_sha256": (
                    contract["artifact_sha256"]["thumbnail_sha256"]
                ),
            }
            write_json(receipt_path, receipt)
            result = verify_upload_receipt(
                contract_path=paths["contract_output"],
                receipt_path=receipt_path,
                upload_run_id="999999",
                result_output=result_path,
            )
            self.assertEqual(result["status"], "PRIVATE_REVIEW_UPLOAD_VERIFIED")
            self.assertEqual(result["privacy_status"], "private")
            self.assertFalse(result["publication_authorized"])

            receipt["privacy_status_readback"] = "public"
            write_json(receipt_path, receipt)
            with self.assertRaisesRegex(
                ReviewOnlyUploadError,
                "readback is not private",
            ):
                verify_upload_receipt(
                    contract_path=paths["contract_output"],
                    receipt_path=receipt_path,
                    upload_run_id="999999",
                    result_output=result_path,
                )


if __name__ == "__main__":
    unittest.main()
