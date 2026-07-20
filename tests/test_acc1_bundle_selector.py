import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

import acc1_bundle_selector
import acc1_story_strategy


ROOT = Path(__file__).resolve().parents[1]


def source_candidate(
    index: int,
    word_count: int,
    *,
    pillar: str = "relationships_family",
    truth_mode: str = "unverified_personal_account",
) -> dict:
    payoff = f"ended{index}"
    body = " ".join(([f"word{index}"] * (word_count - 1)) + [payoff])
    return {
        "post_id": f"p{index}",
        "title": f"Story {index}",
        "subreddit": "r/relationship_advice",
        "author": f"u/author{index}",
        "source_url": f"https://www.reddit.com/r/example/comments/p{index}/story/",
        "story_signature": f"signature-{index}",
        "pillar_id": pillar,
        "truth_mode": truth_mode,
        "review_status": "BUNDLE_COMPONENT_ELIGIBLE",
        "source_body": body,
        "source_body_sha256": hashlib.sha256(body.encode("utf-8")).hexdigest(),
        "source_word_count": word_count,
        "complete": True,
        "self_contained": True,
        "payoff_complete": True,
        "payoff_evidence": payoff,
        "depends_on_screenshot_or_link": False,
        "blocking_reasons": [],
    }


class Acc1BundleSelectorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        config = json.loads((ROOT / "channels.json").read_text(encoding="utf-8"))
        cls.channel = next(item for item in config["channels"] if item["id"] == "acc1")
        cls.pilot_01 = acc1_story_strategy.resolve_pilot_source_plan(cls.channel, "pilot_01")
        cls.pilot_02 = acc1_story_strategy.resolve_pilot_source_plan(cls.channel, "pilot_02")

    def test_selects_complete_pair_nearest_runtime_midpoint(self):
        candidates = [source_candidate(1, 1400), source_candidate(2, 1700), source_candidate(3, 900)]
        manifest = acc1_bundle_selector.select_bundle(candidates, source_plan=self.pilot_01)
        self.assertEqual(manifest["status"], "BUNDLE_SOURCE_SELECTED_UNREVIEWED")
        self.assertEqual([item["post_id"] for item in manifest["stories"]], ["p1", "p2"])
        self.assertEqual(manifest["aggregate_source_word_count"], 3100)
        self.assertEqual(manifest["story_count"], 2)
        self.assertFalse(manifest["production_authorized"])
        self.assertFalse(manifest["publication_authorized"])
        self.assertTrue(acc1_bundle_selector.verify_manifest(manifest))

    def test_selection_and_hash_are_input_order_invariant(self):
        candidates = [source_candidate(1, 1400), source_candidate(2, 1700), source_candidate(3, 900)]
        forward = acc1_bundle_selector.select_bundle(candidates, source_plan=self.pilot_01)
        reverse = acc1_bundle_selector.select_bundle(list(reversed(candidates)), source_plan=self.pilot_01)
        self.assertEqual(forward, reverse)

    def test_pilot_01_builds_three_materially_distinct_reviewed_finalists(self):
        candidates = [source_candidate(index, 1200) for index in range(1, 5)]
        forward = acc1_bundle_selector.select_bundle_finalists(
            candidates,
            source_plan=self.pilot_01,
        )
        reverse = acc1_bundle_selector.select_bundle_finalists(
            list(reversed(candidates)),
            source_plan=self.pilot_01,
        )
        self.assertEqual(forward, reverse)
        self.assertEqual(
            forward["status"],
            "BUNDLE_SOURCE_FINALISTS_READY_FOR_TOPIC_PLAYOFF",
        )
        self.assertEqual(forward["finalist_count"], 3)
        self.assertTrue(acc1_bundle_selector.verify_finalists_manifest(forward))
        source_sets = [set(item["source_post_ids"]) for item in forward["finalists"]]
        self.assertEqual(len({frozenset(item) for item in source_sets}), 3)
        for index, left in enumerate(source_sets):
            for right in source_sets[index + 1:]:
                self.assertTrue(left - right)
                self.assertTrue(right - left)
        self.assertEqual(
            len({item["finalist_sha256"] for item in forward["finalists"]}),
            3,
        )
        self.assertFalse(forward["production_authorized"])
        self.assertFalse(forward["publication_authorized"])

    def test_pilot_02_builds_three_valid_finalists(self):
        candidates = [
            source_candidate(index, 800, pillar="work_money_justice")
            for index in range(1, 6)
        ]
        manifest = acc1_bundle_selector.select_bundle_finalists(
            candidates,
            source_plan=self.pilot_02,
        )
        self.assertEqual(manifest["finalist_count"], 3)
        self.assertTrue(acc1_bundle_selector.verify_finalists_manifest(manifest))
        for finalist in manifest["finalists"]:
            self.assertGreaterEqual(finalist["story_count"], 3)
            self.assertLessEqual(finalist["story_count"], 5)
            self.assertGreaterEqual(finalist["aggregate_source_word_count"], 2340)
            self.assertLessEqual(finalist["aggregate_source_word_count"], 3900)

    def test_finalists_require_three_alternatives_from_reviewed_sources(self):
        with self.assertRaises(acc1_bundle_selector.BundleSelectionError):
            acc1_bundle_selector.select_bundle_finalists(
                [source_candidate(1, 1200), source_candidate(2, 1200)],
                source_plan=self.pilot_01,
            )

        unreviewed = [source_candidate(index, 1200) for index in range(1, 5)]
        for candidate in unreviewed:
            candidate["review_status"] = "UNREVIEWED"
        with self.assertRaises(acc1_bundle_selector.BundleSelectionError):
            acc1_bundle_selector.select_bundle_finalists(
                unreviewed,
                source_plan=self.pilot_01,
            )

    def test_nested_finalist_hash_binding_detects_rehashed_outer_tamper(self):
        manifest = acc1_bundle_selector.select_bundle_finalists(
            [source_candidate(index, 1200) for index in range(1, 5)],
            source_plan=self.pilot_01,
        )
        tampered = copy.deepcopy(manifest)
        tampered["finalists"][0]["stories"][0]["title"] = "Changed"
        unhashed = copy.deepcopy(tampered)
        unhashed.pop("manifest_sha256", None)
        tampered["manifest_sha256"] = acc1_bundle_selector.content_hash(unhashed)
        self.assertTrue(acc1_bundle_selector.verify_manifest(tampered))
        self.assertFalse(acc1_bundle_selector.verify_finalists_manifest(tampered))

    def test_pilot_02_requires_at_least_three_stories(self):
        candidates = [
            source_candidate(1, 1000, pillar="work_money_justice"),
            source_candidate(2, 1000, pillar="work_money_justice"),
            source_candidate(3, 1120, pillar="work_money_justice"),
        ]
        manifest = acc1_bundle_selector.select_bundle(candidates, source_plan=self.pilot_02)
        self.assertEqual(manifest["story_count"], 3)
        self.assertEqual(manifest["aggregate_source_word_count"], 3120)

    def test_incomplete_candidate_is_rejected_even_when_it_would_fit(self):
        incomplete = source_candidate(1, 1600)
        incomplete["complete"] = False
        candidates = [incomplete, source_candidate(2, 1400), source_candidate(3, 1700)]
        manifest = acc1_bundle_selector.select_bundle(candidates, source_plan=self.pilot_01)
        self.assertEqual([item["post_id"] for item in manifest["stories"]], ["p2", "p3"])
        rejection = manifest["selection_contract"]["rejections"][0]
        self.assertIn("source_not_complete", rejection["reasons"])

    def test_each_duplicate_identity_dimension_blocks_the_only_pair(self):
        for field in ("post_id", "source_url", "source_body", "story_signature", "author"):
            with self.subTest(field=field):
                first = source_candidate(1, 1500)
                second = source_candidate(2, 1600)
                second[field] = first[field]
                if field == "source_body":
                    second["source_body_sha256"] = hashlib.sha256(
                        second["source_body"].encode("utf-8")
                    ).hexdigest()
                    second["source_word_count"] = 1500
                    second["payoff_evidence"] = first["payoff_evidence"]
                with self.assertRaises(acc1_bundle_selector.BundleSelectionError):
                    acc1_bundle_selector.select_bundle([first, second], source_plan=self.pilot_01)

    def test_mixed_truth_modes_cannot_form_a_bundle(self):
        candidates = [
            source_candidate(1, 1500),
            source_candidate(2, 1600, truth_mode="fiction"),
        ]
        with self.assertRaises(acc1_bundle_selector.BundleSelectionError):
            acc1_bundle_selector.select_bundle(candidates, source_plan=self.pilot_01)

    def test_aggregate_runtime_envelope_is_fail_closed(self):
        for counts in ((500, 600), (2100, 2100)):
            with self.subTest(counts=counts):
                candidates = [source_candidate(1, counts[0]), source_candidate(2, counts[1])]
                with self.assertRaises(acc1_bundle_selector.BundleSelectionError):
                    acc1_bundle_selector.select_bundle(candidates, source_plan=self.pilot_01)

    def test_wrong_pillar_dependency_and_hash_mismatch_are_rejected(self):
        invalid_rows = []
        wrong_pillar = source_candidate(1, 1500, pillar="work_money_justice")
        invalid_rows.append(wrong_pillar)
        dependent = source_candidate(2, 1600)
        dependent["depends_on_screenshot_or_link"] = True
        invalid_rows.append(dependent)
        mismatched = source_candidate(3, 1500)
        mismatched["source_body_sha256"] = "0" * 64
        invalid_rows.append(mismatched)
        with self.assertRaises(acc1_bundle_selector.BundleSelectionError):
            acc1_bundle_selector.select_bundle(invalid_rows, source_plan=self.pilot_01)

    def test_manifest_tamper_is_detected(self):
        manifest = acc1_bundle_selector.select_bundle(
            [source_candidate(1, 1500), source_candidate(2, 1600)],
            source_plan=self.pilot_01,
        )
        tampered = copy.deepcopy(manifest)
        tampered["stories"][0]["title"] = "Changed"
        self.assertFalse(acc1_bundle_selector.verify_manifest(tampered))

    def test_manifest_verifier_fails_closed_for_malformed_hash_or_payload(self):
        manifest = acc1_bundle_selector.select_bundle(
            [source_candidate(1, 1500), source_candidate(2, 1600)],
            source_plan=self.pilot_01,
        )
        malformed_hash = copy.deepcopy(manifest)
        malformed_hash["manifest_sha256"] = "z" * 64
        self.assertFalse(acc1_bundle_selector.verify_manifest(malformed_hash))
        noncanonical_payload = copy.deepcopy(manifest)
        noncanonical_payload["unexpected"] = {"not", "json"}
        self.assertFalse(acc1_bundle_selector.verify_manifest(noncanonical_payload))

    def test_non_bundle_plan_is_rejected(self):
        saga = acc1_story_strategy.resolve_pilot_source_plan(self.channel, "pilot_03")
        with self.assertRaises(acc1_bundle_selector.BundleSelectionError):
            acc1_bundle_selector.select_bundle([], source_plan=saga)

    def test_forged_bundle_pilot_contract_is_rejected(self):
        forged = copy.deepcopy(self.pilot_01)
        forged["story_count"] = [2, 5]
        with self.assertRaises(acc1_bundle_selector.BundleSelectionError):
            acc1_bundle_selector.select_bundle_finalists(
                [source_candidate(index, 1200) for index in range(1, 5)],
                source_plan=forged,
            )

    def test_cli_accepts_topic_review_candidate_reviews(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            input_path = root / "topic-review.json"
            output_path = root / "bundle-source-manifest.json"
            input_path.write_text(
                json.dumps({
                    "candidate_reviews": [
                        source_candidate(1, 1500),
                        source_candidate(2, 1600),
                    ],
                }),
                encoding="utf-8",
            )
            result = acc1_bundle_selector.main([
                "--channels", str(ROOT / "channels.json"),
                "--pilot-id", "pilot_01",
                "--input", str(input_path),
                "--output", str(output_path),
            ])
            manifest = json.loads(output_path.read_text(encoding="utf-8"))
        self.assertEqual(result, 0)
        self.assertEqual(manifest["status"], "BUNDLE_SOURCE_SELECTED_UNREVIEWED")


if __name__ == "__main__":
    unittest.main()
