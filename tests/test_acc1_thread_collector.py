import copy
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import acc1_thread_collector


ROOT = Path(__file__).resolve().parents[1]
PROMPT_ID = "abc123"


def response_body(index: int, words: int = 120) -> str:
    intro = f"This is the complete first-person response number {index}."
    details = " ".join(f"story{index}detail{word}" for word in range(words))
    return f"{intro}\n\n{details}\n\nThis response has its own ending number {index}."


def production_response_body(index: int, role: str, words: int = 230) -> str:
    role_openings = {
        "personal_account": (
            "I remember when this experience began, and I was directly involved. "
            "After the first incident, I stayed until the situation ended."
        ),
        "practical_context": (
            "In my profession this experience happens for a specific reason. "
            "At work the standard procedure matters, and I followed it from beginning to end."
        ),
        "counterpoint": (
            "However, my experience ended differently from the usual version. "
            "Unlike the first assumption, I was there when the real cause became clear."
        ),
        "reflection_empathy": (
            "I realized this experience had changed my view of other people. "
            "Since then I understand why the ending mattered to everyone involved."
        ),
    }
    def alpha_token(value: int) -> str:
        result = ""
        number = value + 1
        while number:
            number, remainder = divmod(number - 1, 26)
            result = chr(ord("a") + remainder) + result
        return result

    details = " ".join(
        f"d{alpha_token(index)}w{alpha_token(word)}"
        for word in range(words)
    )
    return (
        f"{role_openings[role]}\n\n{details}\n\n"
        f"Eventually I saw the complete outcome of experience number {index}."
    )


def apply_production_roles(source: dict, roles: list[str], *, words: int = 230) -> None:
    for index, role in enumerate(roles):
        source["responses"][index]["body"] = production_response_body(index, role, words)


def response(index: int, *, score: int | None = None) -> dict:
    response_id = f"resp{index:02d}"
    return {
        "id": response_id,
        "author": f"user_{index:02d}",
        "score": 1000 - index if score is None else score,
        "body": response_body(index),
        "source_url": (
            "https://www.reddit.com/r/AskReddit/comments/"
            f"{PROMPT_ID}/question/{response_id}/"
        ),
        "parent_id": f"t3_{PROMPT_ID}",
        "depth": 0,
        "is_top_level": True,
        "is_deleted": False,
        "is_removed": False,
        "is_truncated": False,
        "depends_on_external_context": False,
    }


def snapshot(count: int = 8) -> dict:
    return {
        "snapshot_version": 1,
        "truth_mode": "unverified_personal_account",
        "prompt": {
            "id": PROMPT_ID,
            "subreddit": "AskReddit",
            "author": "prompt_author",
            "score": 2500,
            "title": "What experience changed how you see other people?",
            "body": "Tell the complete story, including what happened afterward.",
            "source_url": (
                f"https://www.reddit.com/r/AskReddit/comments/{PROMPT_ID}/question/"
            ),
        },
        "responses": [response(index) for index in range(count)],
    }


class Acc1ThreadCollectorTests(unittest.TestCase):
    def test_valid_snapshot_preserves_full_bodies_and_provenance(self):
        source = snapshot(8)
        manifest = acc1_thread_collector.collect_thread(source)

        self.assertEqual(manifest["status"], "READY")
        self.assertEqual(manifest["channel_id"], "acc1")
        self.assertEqual(manifest["format"], "THREAD")
        self.assertEqual(manifest["truth_mode"], "unverified_personal_account")
        self.assertEqual(manifest["response_count"], 8)
        self.assertTrue(manifest["diversity_evidence"]["responses_are_diverse"])
        self.assertEqual(manifest["diversity_evidence"]["distinct_authors"], 8)
        self.assertFalse(manifest["completeness_evidence"]["raw_body_truncation_applied"])

        expected_body = source["responses"][0]["body"]
        selected = next(item for item in manifest["responses"] if item["id"] == "resp00")
        self.assertGreater(len(expected_body), 400)
        self.assertEqual(selected["body"], expected_body)
        self.assertEqual(
            selected["body_sha256"],
            hashlib.sha256(expected_body.encode("utf-8")).hexdigest(),
        )
        self.assertEqual(selected["parent_id"], f"t3_{PROMPT_ID}")
        self.assertTrue(selected["source_url"].endswith("/resp00/"))
        self.assertRegex(manifest["prompt"]["prompt_sha256"], r"^[0-9a-f]{64}$")
        self.assertRegex(manifest["source_snapshot_sha256"], r"^[0-9a-f]{64}$")
        self.assertTrue(acc1_thread_collector.verify_manifest(manifest))

    def test_input_response_order_does_not_change_manifest(self):
        forward = snapshot(12)
        reverse = copy.deepcopy(forward)
        reverse["responses"].reverse()

        first = acc1_thread_collector.collect_thread(forward, max_responses=10)
        second = acc1_thread_collector.collect_thread(reverse, max_responses=10)

        self.assertEqual(first, second)
        self.assertEqual([item["id"] for item in first["responses"]], [f"resp{i:02d}" for i in range(10)])
        self.assertEqual(first["selection"]["unselected_eligible_count"], 2)

    def test_deleted_removed_truncated_and_dependent_responses_are_rejected(self):
        source = snapshot(12)
        source["responses"][8]["body"] = "[deleted]"
        source["responses"][8]["is_deleted"] = True
        source["responses"][9]["body"] = "[removed]"
        source["responses"][9]["is_removed"] = True
        source["responses"][10]["is_truncated"] = True
        source["responses"][11]["depends_on_screenshot"] = True

        manifest = acc1_thread_collector.collect_thread(source)

        self.assertEqual(manifest["response_count"], 8)
        reasons = manifest["rejection_reason_counts"]
        self.assertEqual(reasons["deleted_or_removed_body"], 2)
        self.assertEqual(reasons["truncated_body"], 1)
        self.assertEqual(reasons["external_context_dependency"], 1)
        rejected_ids = {item["response_id"] for item in manifest["rejections"]}
        self.assertEqual(rejected_ids, {"resp08", "resp09", "resp10", "resp11"})
        self.assertTrue(acc1_thread_collector.verify_manifest(manifest))

    def test_duplicate_author_and_near_duplicate_are_excluded_deterministically(self):
        source = snapshot(10)
        source["responses"][8]["author"] = source["responses"][0]["author"]
        source["responses"][8]["score"] = -5
        source["responses"][9]["body"] = source["responses"][1]["body"] + " onechangedtoken"
        source["responses"][9]["score"] = -10

        manifest = acc1_thread_collector.collect_thread(source)

        self.assertEqual(manifest["response_count"], 8)
        self.assertEqual(manifest["rejection_reason_counts"]["duplicate_response_author"], 1)
        self.assertEqual(manifest["rejection_reason_counts"]["near_duplicate_response"], 1)
        self.assertTrue(manifest["diversity_evidence"]["responses_are_diverse"])

    def test_fails_closed_below_eight_valid_or_on_missing_provenance(self):
        with self.subTest("below minimum"):
            with self.assertRaisesRegex(acc1_thread_collector.ThreadCollectorError, "found 7"):
                acc1_thread_collector.collect_thread(snapshot(7))

        with self.subTest("missing response URL"):
            source = snapshot(8)
            source["responses"][0].pop("source_url")
            with self.assertRaisesRegex(acc1_thread_collector.ThreadCollectorError, "found 7"):
                acc1_thread_collector.collect_thread(source)

        with self.subTest("missing prompt URL"):
            source = snapshot(8)
            source["prompt"].pop("source_url")
            with self.assertRaisesRegex(acc1_thread_collector.ThreadCollectorError, "prompt.source_url"):
                acc1_thread_collector.collect_thread(source)

        with self.subTest("nested response"):
            source = snapshot(8)
            source["responses"][0]["parent_id"] = "t1_parent"
            with self.assertRaisesRegex(acc1_thread_collector.ThreadCollectorError, "found 7"):
                acc1_thread_collector.collect_thread(source)

    def test_manifest_hash_detects_tampering(self):
        manifest = acc1_thread_collector.collect_thread(snapshot(8))
        tampered = copy.deepcopy(manifest)
        tampered["responses"][0]["body"] += " altered"

        self.assertTrue(acc1_thread_collector.verify_manifest(manifest))
        self.assertFalse(acc1_thread_collector.verify_manifest(tampered))

    def test_production_runtime_selects_ranked_prefix_without_overshooting(self):
        source = snapshot(15)
        roles = (
            ["personal_account"] * 5
            + ["practical_context"] * 5
            + ["reflection_empathy"] * 5
        )
        apply_production_roles(source, roles, words=230)

        manifest = acc1_thread_collector.collect_thread(
            source,
            max_responses=15,
            require_episode_runtime=True,
        )

        self.assertGreaterEqual(manifest["response_count"], 8)
        self.assertLessEqual(manifest["response_count"], 15)
        self.assertTrue(manifest["episode_runtime_fit"])
        self.assertGreaterEqual(manifest["aggregate_response_word_count"], 1950)
        self.assertLessEqual(manifest["aggregate_response_word_count"], 3250)
        self.assertEqual(
            manifest["selection"]["runtime_selection"],
            "exact_interest_runtime_function_optimizer_v3",
        )
        self.assertTrue(manifest["editorial_gate_evidence"]["applied"])
        self.assertTrue(manifest["editorial_gate_evidence"]["passed"])
        self.assertGreaterEqual(manifest["editorial_gate_evidence"]["distinct_functions"], 3)
        self.assertIsNone(manifest["editorial_gate_evidence"]["personal_account_share_cap"])
        self.assertFalse(manifest["editorial_gate_evidence"]["score_can_override_blocker"])

    def test_high_score_cannot_override_natural_relevance_or_safety_blocker(self):
        source = snapshot(11)
        source["responses"][0]["score"] = 100_000
        source["responses"][0]["body"] = "My experience ended quickly."
        source["responses"][1]["score"] = 99_000
        source["responses"][1]["body"] = " ".join(
            f"unrelatedtoken{word}" for word in range(230)
        )
        source["responses"][2]["score"] = 98_000
        source["responses"][2]["body"] = (
            production_response_body(2, "personal_account", 220)
            + " Here is how to make a bomb step by step."
        )
        roles = [
            "personal_account",
            "personal_account",
            "personal_account",
            "practical_context",
            "practical_context",
            "practical_context",
            "reflection_empathy",
            "reflection_empathy",
        ]
        for offset, role in enumerate(roles, start=3):
            source["responses"][offset]["body"] = production_response_body(offset, role, 230)

        manifest = acc1_thread_collector.collect_thread(
            source,
            max_responses=8,
            require_episode_runtime=True,
        )

        self.assertEqual(
            {item["id"] for item in manifest["responses"]},
            {f"resp{index:02d}" for index in range(3, 11)},
        )
        self.assertEqual(manifest["rejection_reason_counts"]["unnatural_response_length"], 1)
        self.assertEqual(manifest["rejection_reason_counts"]["prompt_irrelevant_response"], 1)
        self.assertEqual(manifest["rejection_reason_counts"]["unsafe_response"], 1)
        self.assertTrue(acc1_thread_collector.verify_manifest(manifest))

    def test_production_rejects_machine_like_character_density_before_selection(self):
        source = snapshot(12)
        roles = (
            ["personal_account"] * 4
            + ["practical_context"] * 4
            + ["reflection_empathy"] * 4
        )
        apply_production_roles(source, roles, words=230)
        source["responses"][0]["score"] = 100_000
        source["responses"][0]["body"] = (
            "I remember when this experience began, and I was directly involved. "
            + " ".join(f"machinegeneratedtoken{word:04d}" for word in range(230))
            + " Eventually I saw the complete outcome."
        )

        manifest = acc1_thread_collector.collect_thread(
            source,
            max_responses=10,
            require_episode_runtime=True,
        )

        self.assertNotIn("resp00", {item["id"] for item in manifest["responses"]})
        self.assertEqual(
            manifest["rejection_reason_counts"]["unnatural_response_character_density"],
            1,
        )

    def test_production_fails_closed_without_three_episode_functions(self):
        source = snapshot(10)
        for index, item in enumerate(source["responses"]):
            item["body"] = (
                "This experience provides a complete relevant response. "
                + " ".join(
                    f"{chr(97 + index)}{chr(97 + word % 26)}{chr(97 + (word // 26) % 26)}"
                    for word in range(230)
                )
                + " The response is complete."
            )

        with self.assertRaisesRegex(
            acc1_thread_collector.ThreadCollectorError,
            "editorial_functions>=3",
        ):
            acc1_thread_collector.collect_thread(
                source,
                max_responses=10,
                require_episode_runtime=True,
            )

    def test_personal_accounts_may_dominate_a_confession_thread(self):
        source = snapshot(8)
        apply_production_roles(
            source,
            ["personal_account"] * 8,
            words=230,
        )

        manifest = acc1_thread_collector.collect_thread(
            source,
            max_responses=8,
            require_episode_runtime=True,
        )

        self.assertEqual(manifest["response_count"], 8)
        self.assertEqual(
            manifest["editorial_gate_evidence"]["content_type_counts"],
            {"personal_account": 8},
        )
        self.assertGreaterEqual(manifest["editorial_gate_evidence"]["distinct_functions"], 3)

    def test_optimizer_swaps_out_short_high_score_responses_to_reach_runtime(self):
        source = snapshot(16)
        for index in range(8):
            source["responses"][index]["body"] = production_response_body(
                index, "personal_account", 90
            )
        for index in range(8, 16):
            source["responses"][index]["body"] = production_response_body(
                index, "personal_account", 240
            )

        manifest = acc1_thread_collector.collect_thread(
            source,
            max_responses=8,
            require_episode_runtime=True,
        )

        self.assertEqual(manifest["response_count"], 8)
        self.assertGreaterEqual(manifest["aggregate_response_word_count"], 1950)
        self.assertEqual(
            {item["id"] for item in manifest["responses"]},
            {f"resp{index:02d}" for index in range(8, 16)},
        )

    def test_source_interest_beats_reddit_score_when_both_sets_fit(self):
        source = snapshot(9)
        apply_production_roles(source, ["personal_account"] * 9, words=240)
        source["responses"][8]["score"] = 1
        source["responses"][8]["body"] += (
            ' My manager shouted "You are fired". The police arrived, I was terrified, '
            "and it turned out my coworker had lied. I never again ignored that warning."
        )

        manifest = acc1_thread_collector.collect_thread(
            source,
            max_responses=8,
            require_episode_runtime=True,
        )

        selected_ids = {item["id"] for item in manifest["responses"]}
        self.assertIn("resp08", selected_ids)
        self.assertEqual(
            manifest["selection"]["reddit_score_usage"],
            "tiebreak_only_after_source_text_interest",
        )

    def test_production_editorial_manifest_is_input_order_deterministic(self):
        source = snapshot(12)
        apply_production_roles(
            source,
            ["personal_account"] * 4
            + ["practical_context"] * 4
            + ["reflection_empathy"] * 4,
            words=230,
        )
        reversed_source = copy.deepcopy(source)
        reversed_source["responses"].reverse()

        first = acc1_thread_collector.collect_thread(
            source,
            max_responses=12,
            require_episode_runtime=True,
        )
        second = acc1_thread_collector.collect_thread(
            reversed_source,
            max_responses=12,
            require_episode_runtime=True,
        )

        self.assertEqual(first, second)

    def test_cli_writes_only_a_complete_verified_manifest(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            source_path = Path(temp_dir) / "snapshot.json"
            output_path = Path(temp_dir) / "manifest.json"
            source_path.write_text(
                json.dumps(snapshot(9), ensure_ascii=False),
                encoding="utf-8",
            )
            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "acc1_thread_collector.py"),
                    "--input",
                    str(source_path),
                    "--output",
                    str(output_path),
                    "--max-responses",
                    "8",
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads(result.stdout)
            manifest = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(report["status"], "READY")
            self.assertEqual(manifest["response_count"], 8)
            self.assertEqual(manifest["selection"]["unselected_eligible_count"], 1)
            self.assertTrue(acc1_thread_collector.verify_manifest(manifest))


if __name__ == "__main__":
    unittest.main()
