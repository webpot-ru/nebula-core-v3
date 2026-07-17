import copy
import hashlib
import unittest

import acc1_episode_manifest
import acc1_release_gate


DIGEST_A = "a" * 64
DIGEST_B = "b" * 64
DIGEST_C = "c" * 64
DIGEST_D = "d" * 64
DIGEST_E = "e" * 64
DIGEST_F = "f" * 64
DIGEST_1 = "1" * 64
DIGEST_2 = "2" * 64


def valid_payloads():
    source_body = "Complete source story with a preserved ending."
    source_body_sha256 = hashlib.sha256(source_body.encode("utf-8")).hexdigest()
    queue = {
        "channel_id": "acc1",
        "entries": [{
            "post_id": "post-1",
            "source_body": source_body,
            "source_body_sha256": source_body_sha256,
        }],
    }
    review = {"status": "review_ready", "top_topics": [{"post_id": "post-1"}]}
    raw_greenlight = {
        "channel_id": "acc1",
        "pilot_id": "pilot_01",
        "format": "SAGA",
        "pillar": "relationships_family",
        "publication_authorized": False,
        "artifact_bindings": {"source_sha256": DIGEST_A, "review_sha256": DIGEST_B},
        "source": {
            "post_id": "post-1",
            "source_body_sha256": source_body_sha256,
            "truth_mode": "unverified_personal_account",
        },
    }
    config = {"channel_id": "acc1", "automation_enabled": False}
    daily_plan = {
        "episode_key": "acc1/2026-07-14/pilot_01",
        "production_date": "2026-07-14",
        "pilot_id": "pilot_01",
        "format": "SAGA",
        "pillar": "relationships_family",
        "publication_authorized": False,
    }
    episode_plan = acc1_episode_manifest.build_episode_manifest(
        episode_key="acc1/2026-07-14/pilot_01",
        episode_date="2026-07-14",
        pilot_id="pilot_01",
        format_id="SAGA",
        pillar="relationships_family",
        source_queue=queue,
        topic_review=review,
        greenlight=raw_greenlight,
        config=config,
        daily_plan=daily_plan,
        git_sha="1234567890abcdef1234567890abcdef12345678",
        provider_settings={
            "tts": {"model_id": "eleven_v3", "voice_id": "voice-primary"},
            "translation": {"model": "gemini-3.5-flash"},
        },
    )
    plan_hash = episode_plan["episode_plan_sha256"]
    artifact_hashes = {
        "script_sha256": DIGEST_E,
        "audio_sha256": DIGEST_F,
        "metadata_sha256": DIGEST_1,
        "storyboard_sha256": DIGEST_2,
        "video_sha256": DIGEST_C,
        "thumbnail_sha256": DIGEST_D,
    }
    strategy = {
        "channel_strategy": {"status": "PASS"},
        "source_plan": {
            "status": "PASS", "pilot_id": "pilot_01",
            "format": "SAGA", "pillar": "relationships_family",
        },
    }
    greenlight = {
        "episode_greenlight": {
            "status": "PASS",
            "pilot_id": "pilot_01",
            "format": "SAGA",
            "pillar": "relationships_family",
            "publication_authorized": False,
            "artifact_bindings_verified": True,
            "selected_source_verified": True,
            "artifact_bindings": {
                "source_sha256": DIGEST_A,
                "review_sha256": DIGEST_B,
            },
        }
    }
    media = {
        "status": "PASS",
        "publication_authorized": False,
        "failures": [],
        "creative_status": "PASS",
        "expected_voice_id_checked": True,
        "episode_plan_sha256": plan_hash,
        "artifact_sha256": dict(artifact_hashes),
        "truth_disclosure_audible": True,
        "truth_disclosure_visible_in_metadata": True,
        "video_sha256": DIGEST_C,
        "thumbnail_sha256": DIGEST_D,
    }
    thumbnail = {
        "status": "PASS", "sha256": DIGEST_D, "dimensions": [1280, 720],
        "episode_plan_sha256": plan_hash,
    }
    creative = {
        "status": "PASS",
        "publication_authorized": False,
        "episode_plan_sha256": plan_hash,
        "video_sha256": DIGEST_C,
        "thumbnail_sha256": DIGEST_D,
        "reviewer": "operator",
        "reviewed_at": "2026-07-13T00:00:00Z",
        "notes": "Accepted for one unlisted review only.",
        "checks": {field: True for field in acc1_release_gate.REQUIRED_CREATIVE_CHECKS},
    }
    return {
        "strategy": strategy,
        "greenlight_report": greenlight,
        "source_queue": queue,
        "topic_review": review,
        "greenlight": raw_greenlight,
        "config": config,
        "episode_plan": episode_plan,
        "media": media,
        "thumbnail": thumbnail,
        "creative": creative,
        "artifact_hashes": artifact_hashes,
    }


class Acc1ReleaseGateTests(unittest.TestCase):
    def validate(self, payloads):
        return acc1_release_gate.validate_release(
            strategy_report=payloads["strategy"],
            greenlight_report=payloads["greenlight_report"],
            source_queue=payloads["source_queue"],
            topic_review=payloads["topic_review"],
            greenlight=payloads["greenlight"],
            config=payloads["config"],
            episode_plan=payloads["episode_plan"],
            media_qa=payloads["media"],
            thumbnail_manifest=payloads["thumbnail"],
            creative_review=payloads["creative"],
            artifact_sha256=payloads["artifact_hashes"],
        )

    def test_valid_evidence_is_ready_only_for_unlisted_review(self):
        report = self.validate(valid_payloads())
        self.assertEqual(report["status"], "READY_FOR_UNLISTED_REVIEW")
        self.assertFalse(report["publication_authorized"])
        self.assertEqual(report["failures"], [])

    def test_missing_source_binding_blocks(self):
        payloads = valid_payloads()
        payloads["greenlight_report"]["episode_greenlight"]["artifact_bindings"].pop("source_sha256")
        report = self.validate(payloads)
        self.assertEqual(report["status"], "BLOCKED")
        self.assertTrue(any("source_sha256" in item for item in report["failures"]))

    def test_thumbnail_checksum_mismatch_blocks(self):
        payloads = valid_payloads()
        payloads["thumbnail"]["sha256"] = "9" * 64
        report = self.validate(payloads)
        self.assertTrue(any("thumbnail checksum" in item for item in report["failures"]))

    def test_creative_review_must_match_final_video(self):
        payloads = valid_payloads()
        payloads["creative"]["video_sha256"] = "9" * 64
        report = self.validate(payloads)
        self.assertTrue(any("final video" in item for item in report["failures"]))

    def test_media_qa_must_match_final_video(self):
        payloads = valid_payloads()
        payloads["media"]["video_sha256"] = "9" * 64
        report = self.validate(payloads)
        self.assertTrue(any("media QA" in item and "final video" in item for item in report["failures"]))

    def test_unverified_greenlight_chain_blocks(self):
        payloads = valid_payloads()
        payloads["greenlight_report"]["episode_greenlight"]["artifact_bindings_verified"] = False
        report = self.validate(payloads)
        self.assertEqual(report["status"], "BLOCKED")
        self.assertTrue(any("exact artifacts" in item for item in report["failures"]))

    def test_each_creative_check_is_fail_closed(self):
        for field in acc1_release_gate.REQUIRED_CREATIVE_CHECKS:
            with self.subTest(field=field):
                payloads = valid_payloads()
                payloads["creative"]["checks"][field] = False
                report = self.validate(payloads)
                self.assertTrue(any(field in item for item in report["failures"]))

    def test_release_gate_never_authorizes_publication(self):
        payloads = valid_payloads()
        payloads["creative"]["publication_authorized"] = True
        report = self.validate(payloads)
        self.assertEqual(report["status"], "BLOCKED")
        self.assertFalse(report["publication_authorized"])

    def test_exact_queue_tamper_breaks_episode_plan_chain(self):
        payloads = valid_payloads()
        payloads["source_queue"] = copy.deepcopy(payloads["source_queue"])
        payloads["source_queue"]["entries"][0]["source_body"] += " tampered"
        report = self.validate(payloads)
        self.assertEqual(report["status"], "BLOCKED")
        self.assertTrue(any("episode plan" in item and "queue_sha256" in item for item in report["failures"]))

    def test_media_plan_hash_mismatch_blocks(self):
        payloads = valid_payloads()
        payloads["media"]["episode_plan_sha256"] = "9" * 64
        report = self.validate(payloads)
        self.assertTrue(any("media QA" in item and "episode plan" in item for item in report["failures"]))

    def test_each_exact_artifact_checksum_is_fail_closed(self):
        for field in acc1_release_gate.ARTIFACT_HASH_FIELDS:
            with self.subTest(field=field):
                payloads = valid_payloads()
                payloads["media"]["artifact_sha256"][field] = "9" * 64
                report = self.validate(payloads)
                self.assertTrue(any(field in item for item in report["failures"]))

    def test_truth_disclosure_evidence_is_required(self):
        payloads = valid_payloads()
        payloads["media"]["truth_disclosure_audible"] = False
        report = self.validate(payloads)
        self.assertTrue(any("audible truth disclosure" in item for item in report["failures"]))


if __name__ == "__main__":
    unittest.main()
