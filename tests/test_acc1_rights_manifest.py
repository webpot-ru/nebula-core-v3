import copy
import unittest

from acc1_episode_manifest import canonical_hash
from acc1_rights_manifest import build_rights_template, validate_rights_manifest
from tests.test_acc1_release_gate import valid_payloads


EVIDENCE_SHA256 = "8" * 64


def rights_inputs():
    payloads = valid_payloads()
    queue = copy.deepcopy(payloads["source_queue"])
    queue["entries"][0].update({
        "author": "example_author",
        "source_url": "https://www.reddit.com/r/example/comments/post-1/story/",
    })
    plan = copy.deepcopy(payloads["episode_plan"])
    plan["artifact_bindings"]["queue_sha256"] = canonical_hash(queue)
    plan["episode_plan_sha256"] = canonical_hash({
        key: value for key, value in plan.items() if key != "episode_plan_sha256"
    })
    return plan, queue


def completed_rights():
    plan, queue = rights_inputs()
    manifest = build_rights_template(plan, queue)
    manifest.update({
        "status": "PASS",
        "reviewer": "rights-operator",
        "reviewed_at": "2026-07-17T10:00:00Z",
        "notes": "Permission evidence checked for one private YouTube review.",
    })
    manifest["sources"][0].update({
        "rightsholder_name": "example_author",
        "rights_status": "submitted_with_permission",
        "evidence_locator": "rights-vault://acc1/post-1/permission",
        "evidence_sha256": EVIDENCE_SHA256,
        "commercial_use_allowed": True,
        "translation_allowed": True,
        "adaptation_allowed": True,
        "narration_allowed": True,
        "audiovisual_sync_allowed": True,
        "youtube_distribution_allowed": True,
        "youtube_scopes": ["private"],
        "territory": "worldwide",
        "term": "perpetual",
        "exclusivity": "non_exclusive",
        "payment_terms": "no fee",
        "required_credit": "Credit source author in description.",
        "cleared_by": "rights-operator",
        "cleared_at": "2026-07-17T10:00:00Z",
    })
    manifest["rights_manifest_sha256"] = canonical_hash({
        key: value for key, value in manifest.items()
        if key != "rights_manifest_sha256"
    })
    return manifest, plan, queue


class Acc1RightsManifestTests(unittest.TestCase):
    def test_template_is_checksum_bound_and_fail_closed(self):
        plan, queue = rights_inputs()
        manifest = build_rights_template(plan, queue)
        report = validate_rights_manifest(
            manifest, episode_plan=plan, source_queue=queue,
        )
        self.assertEqual(report["status"], "BLOCKED")
        self.assertFalse(report["publication_authorized"])

    def test_completed_exact_rights_pass_only_for_private_scope(self):
        manifest, plan, queue = completed_rights()
        report = validate_rights_manifest(
            manifest, episode_plan=plan, source_queue=queue,
        )
        self.assertEqual(report["status"], "PASS")
        self.assertFalse(report["publication_authorized"])
        self.assertEqual(report["failures"], [])

    def test_missing_permission_blocks(self):
        manifest, plan, queue = completed_rights()
        manifest["sources"][0]["translation_allowed"] = False
        manifest["rights_manifest_sha256"] = canonical_hash({
            key: value for key, value in manifest.items()
            if key != "rights_manifest_sha256"
        })
        report = validate_rights_manifest(
            manifest, episode_plan=plan, source_queue=queue,
        )
        self.assertTrue(any("translation_allowed" in item for item in report["failures"]))

    def test_tamper_without_rehash_blocks(self):
        manifest, plan, queue = completed_rights()
        manifest["sources"][0]["rightsholder_name"] = "someone else"
        report = validate_rights_manifest(
            manifest, episode_plan=plan, source_queue=queue,
        )
        self.assertTrue(any("does not match manifest content" in item for item in report["failures"]))

    def test_public_scope_is_not_inferred_from_private_permission(self):
        manifest, plan, queue = completed_rights()
        report = validate_rights_manifest(
            manifest,
            episode_plan=plan,
            source_queue=queue,
            required_youtube_scope="public",
        )
        self.assertEqual(report["status"], "BLOCKED")
        self.assertTrue(any("YouTube public" in item for item in report["failures"]))


if __name__ == "__main__":
    unittest.main()
