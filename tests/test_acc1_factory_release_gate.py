import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from acc1_episode_manifest import canonical_hash
from acc1_release_gate import (
    FACTORY_ARTIFACT_PATHS,
    FACTORY_EVIDENCE_PATHS,
    validate_factory_release,
)
from scripts.build_acc1_creative_review_template import checks_for_mode
from tests.test_acc1_release_gate import valid_payloads
from tests.test_acc1_rights_manifest import completed_rights, rights_inputs


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


def build_factory_fixture(root: Path):
    base = valid_payloads()
    plan, queue = rights_inputs()
    visual_mode = plan["visual_mode"]

    for field, relative in FACTORY_ARTIFACT_PATHS.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes((field + "\n").encode("utf-8"))
    artifact_hashes = {
        field: file_sha256(root / relative)
        for field, relative in FACTORY_ARTIFACT_PATHS.items()
    }

    evidence_payloads = {key: {"fixture": key} for key in FACTORY_EVIDENCE_PATHS}
    evidence_payloads.update({
        "source_queue": queue,
        "topic_playoff": base["topic_review"],
        "episode_greenlight": base["greenlight"],
        "episode_plan": plan,
        "thumbnail_manifest": {
            "status": "PASS",
            "episode_plan_sha256": plan["episode_plan_sha256"],
            "sha256": artifact_hashes["thumbnail_sha256"],
        },
        "media_qa": {
            "status": "PASS",
            "failures": [],
            "publication_authorized": False,
            "episode_plan_sha256": plan["episode_plan_sha256"],
            "visual_mode": visual_mode,
            "artifact_sha256": artifact_hashes,
            "pause_map_sha256": None,
            "audio_mix_report_sha256": None,
            "shot_plan_sha256": None,
            "caption_track_sha256": None,
            "caption_srt_sha256": None,
        },
    })
    for key, relative in FACTORY_EVIDENCE_PATHS.items():
        write_json(root / relative, evidence_payloads[key])
    evidence_hashes = {
        key: file_sha256(root / relative)
        for key, relative in FACTORY_EVIDENCE_PATHS.items()
    }

    release_manifest = {
        "version": 2,
        "status": "READY_FOR_HUMAN_REVIEW",
        "publication_authorized": False,
        "performance_outcome_guaranteed": False,
        "episode_key": plan["episode_key"],
        "pilot_id": plan["pilot_id"],
        "format": plan["format"],
        "pillar": plan["pillar"],
        "visual_mode": visual_mode,
        "narration_profile_id": plan["narration_profile_id"],
        "narration_profile_sha256": plan["narration_profile_sha256"],
        "episode_plan_sha256": plan["episode_plan_sha256"],
        "daily_plan_sha256": plan["daily_plan_sha256"],
        "artifact_sha256": artifact_hashes,
        "evidence_sha256": evidence_hashes,
        "pause_map_sha256": None,
        "audio_mix_report_sha256": None,
        "shot_plan_sha256": None,
        "caption_track_sha256": None,
        "caption_srt_sha256": None,
        "audio_sha256": artifact_hashes["audio_sha256"],
        "media_qa_status": "PASS",
        "creative_review_status": "BLOCKED_PENDING_HUMAN",
    }
    release_manifest["release_candidate_manifest_sha256"] = canonical_hash(release_manifest)
    write_json(root / "release-candidate-manifest.json", release_manifest)

    creative_review = {
        "version": 3,
        "status": "PASS",
        "publication_authorized": False,
        "decision_scope": "private_review_only",
        "human_attested": True,
        "episode_plan_sha256": plan["episode_plan_sha256"],
        "daily_plan_sha256": plan["daily_plan_sha256"],
        "visual_mode": visual_mode,
        "narration_profile_id": plan["narration_profile_id"],
        "narration_profile_sha256": plan["narration_profile_sha256"],
        "audio_sha256": artifact_hashes["audio_sha256"],
        "pause_map_sha256": None,
        "audio_mix_report_sha256": None,
        "shot_plan_sha256": None,
        "caption_track_sha256": None,
        "video_sha256": artifact_hashes["video_sha256"],
        "thumbnail_sha256": artifact_hashes["thumbnail_sha256"],
        "reviewer": "human-reviewer",
        "reviewed_at": "2026-07-17T11:00:00Z",
        "notes": "Exact fixture accepted for private review only.",
        "checks": {field: True for field in checks_for_mode(visual_mode)},
        "observations": [
            {"category": "first_30_seconds", "timecode_sec": 15, "observation": "Hook and disclosure pass.", "verdict": "PASS"},
            {"category": "visual", "timecode_sec": 35, "observation": "Text and rhythm pass.", "verdict": "PASS"},
            {"category": "audio", "timecode_sec": 50, "observation": "Voice and pauses pass.", "verdict": "PASS"},
        ],
    }
    rights, _, _ = completed_rights()
    return release_manifest, creative_review, rights


class Acc1FactoryReleaseGateTests(unittest.TestCase):
    def validate(self, root: Path, creative: dict, rights: dict):
        creative_path = root / "completed-creative.json"
        rights_path = root / "completed-rights.json"
        write_json(creative_path, creative)
        write_json(rights_path, rights)
        return validate_factory_release(
            artifact_root=root,
            creative_review=creative,
            creative_review_file_sha256=file_sha256(creative_path),
            rights_manifest=rights,
            rights_manifest_file_sha256=file_sha256(rights_path),
            source_run_id="12345",
        )

    def test_exact_completed_evidence_is_ready_only_for_private_review(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest, creative, rights = build_factory_fixture(root)
            report = self.validate(root, creative, rights)
            self.assertEqual(report["status"], "READY_FOR_PRIVATE_REVIEW")
            self.assertFalse(report["publication_authorized"])
            self.assertFalse(report["upload_authorized"])
            self.assertEqual(report["release_candidate_manifest_sha256"], manifest["release_candidate_manifest_sha256"])
            self.assertEqual(report["failures"], [])

    def test_tampered_video_blocks(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _, creative, rights = build_factory_fixture(root)
            (root / "final-output.mp4").write_bytes(b"tampered")
            report = self.validate(root, creative, rights)
            self.assertEqual(report["status"], "BLOCKED")
            self.assertTrue(any("video_sha256" in item for item in report["failures"]))

    def test_incomplete_human_review_blocks(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _, creative, rights = build_factory_fixture(root)
            creative = copy.deepcopy(creative)
            creative["human_attested"] = False
            report = self.validate(root, creative, rights)
            self.assertTrue(any("human_attested" in item for item in report["failures"]))

    def test_non_pass_timestamped_observation_blocks(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _, creative, rights = build_factory_fixture(root)
            creative = copy.deepcopy(creative)
            creative["observations"][1]["verdict"] = "CHANGE"
            report = self.validate(root, creative, rights)
            self.assertTrue(any("observation 1 must PASS" in item for item in report["failures"]))

    def test_rights_for_different_plan_block(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _, creative, rights = build_factory_fixture(root)
            rights = copy.deepcopy(rights)
            rights["episode_plan_sha256"] = "9" * 64
            rights["rights_manifest_sha256"] = canonical_hash({
                key: value for key, value in rights.items()
                if key != "rights_manifest_sha256"
            })
            report = self.validate(root, creative, rights)
            self.assertTrue(any("immutable episode plan" in item for item in report["failures"]))


if __name__ == "__main__":
    unittest.main()
