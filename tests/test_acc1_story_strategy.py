import copy
import hashlib
import json
import re
import unittest
from pathlib import Path

import acc1_story_strategy
from scripts import review_reddit_topics


ROOT = Path(__file__).resolve().parents[1]


def valid_greenlight():
    return {
        "channel_id": "acc1",
        "pilot_id": "pilot_03",
        "publication_authorized": False,
        "artifact_bindings": {
            "source_sha256": "a" * 64,
            "review_sha256": "b" * 64,
        },
        "format": "SAGA",
        "pillar": "strange_dark_unexplained",
        "source": {
            "post_id": "post-1",
            "source_body_sha256": "c" * 64,
            "source_word_count": 2600,
            "complete": True,
            "truth_mode": "fiction",
            "depends_on_screenshot_or_link": False,
            "fictional_as_real": False,
            "payoff_complete": True,
            "source_urls": ["https://www.reddit.com/r/nosleep/comments/abc/story/"],
            "primary_story_count": 1,
        },
        "packaging_options": [
            {
                "title": f"Концепция {index}",
                "thumbnail_concept": f"Сцена {index}",
                "first_screen_promise": f"Обещание {index}",
            }
            for index in range(1, 4)
        ],
        "cold_open": {"text": "Всё изменилось после одного сообщения.", "source_evidence": "Exact source line"},
        "story_beats": ["setup", "escalation", "payoff"],
        "originality_plan": {
            "editorial_framing": "Короткое авторское вступление и вопрос в финале.",
            "visual_beats": "Новые сцены на смысловых поворотах.",
            "sound_design": "Тихие акценты без непрерывного шума.",
        },
        "veto_flags": [],
        "scores": {
            "title_thumbnail": 22,
            "cold_open": 17,
            "arc_payoff": 17,
            "viewer_promise": 13,
            "source_truth": 9,
            "originality_visual": 8,
        },
    }


def valid_bound_saga():
    cold_evidence = "Everything changed after one message."
    payoff_evidence = "In the end, I blocked him and never heard from him again."
    source_body = " ".join([cold_evidence] + (["night"] * 2585) + [payoff_evidence])
    source_word_count = len(re.findall(r"[A-Za-z']+", source_body))
    source_body_sha256 = hashlib.sha256(source_body.encode("utf-8")).hexdigest()
    queue = {
        "channel_id": "acc1",
        "format_intent": "saga",
        "source_plan": {
            "pilot_id": "pilot_03",
            "format": "SAGA",
            "pillar": "strange_dark_unexplained",
            "topic_family": "dark_curiosity",
        },
        "entries": [{
            "post_id": "post-1",
            "url": "https://www.reddit.com/r/nosleep/comments/abc/story/",
            "source_body": source_body,
        }],
    }
    candidate = {
        "post_id": "post-1",
        "source_url": "https://www.reddit.com/r/nosleep/comments/abc/story/",
        "source_body_sha256": source_body_sha256,
        "source_word_count": source_word_count,
        "truth_mode": "fiction",
        "payoff_complete": True,
        "payoff_evidence": payoff_evidence,
        "depends_on_screenshot_or_link": False,
        "pillar_id": "strange_dark_unexplained",
        "blocking_reasons": [],
        "review_status": "SAGA_SOURCE_ELIGIBLE_FOR_GREENLIGHT",
    }
    review = review_reddit_topics.bind_artifact_hashes({
        "version": 2,
        "status": "review_ready",
        "review_mode": "deterministic_full_body_saga",
        "channel_id": "acc1",
        "production_authorized": False,
        "source_plan": queue["source_plan"],
        "top_topics": [candidate],
    }, queue)
    payload = valid_greenlight()
    payload["source"].update({
        "source_body_sha256": source_body_sha256,
        "source_word_count": source_word_count,
        "payoff_evidence": payoff_evidence,
    })
    payload["cold_open"]["source_evidence"] = cold_evidence
    payload["artifact_bindings"] = {
        "source_sha256": review["source_sha256"],
        "review_sha256": review["review_sha256"],
    }
    return payload, queue, review


class Acc1ChannelStrategyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        config = json.loads((ROOT / "channels.json").read_text(encoding="utf-8"))
        cls.channel = next(item for item in config["channels"] if item["id"] == "acc1")

    def test_broad_strategy_and_six_pilot_matrix_pass(self):
        report = acc1_story_strategy.validate_channel_strategy(self.channel)
        self.assertEqual(report["status"], "PASS", report["failures"])
        self.assertEqual(report["pillar_count"], 5)
        self.assertEqual(report["pilot_count"], 6)
        self.assertEqual(
            report["pilot_cycle_order"],
            ["pilot_01", "pilot_04", "pilot_02", "pilot_05", "pilot_03", "pilot_06"],
        )

    def test_thread_contract_is_artifact_ready_but_not_live_verified(self):
        report = acc1_story_strategy.validate_channel_strategy(self.channel)
        self.assertTrue(report["thread_source_ready"])

    def test_automation_cannot_be_enabled_by_strategy_change(self):
        channel = copy.deepcopy(self.channel)
        channel["automation_enabled"] = True
        report = acc1_story_strategy.validate_channel_strategy(channel)
        self.assertEqual(report["status"], "BLOCKED")
        self.assertTrue(any("automation_enabled" in item for item in report["failures"]))

    def test_saga_bundle_and_thread_source_plans_are_exact(self):
        first = acc1_story_strategy.resolve_pilot_source_plan(self.channel, "pilot_01")
        second = acc1_story_strategy.resolve_pilot_source_plan(self.channel, "pilot_02")
        third = acc1_story_strategy.resolve_pilot_source_plan(self.channel, "pilot_03")
        fourth = acc1_story_strategy.resolve_pilot_source_plan(self.channel, "pilot_04")
        self.assertEqual(first["format"], "BUNDLE")
        self.assertEqual(first["topic_family"], "human_drama")
        self.assertEqual(first["story_count"], [2, 3])
        self.assertEqual(first["aggregate_source_word_count"], [2340, 3900])
        self.assertEqual(first["subreddits"][:2], ["relationship_advice", "AmItheAsshole"])
        self.assertEqual(first["franchise_id"], "aita_family_conflict")
        self.assertEqual(first["portfolio_role"], "core")
        self.assertFalse(first["production_ready"])
        self.assertEqual(second["story_count"], [3, 5])
        self.assertEqual(third["format"], "SAGA")
        self.assertEqual(third["topic_family"], "dark_curiosity")
        self.assertEqual(third["format_intent"], "saga")
        self.assertEqual(third["source_word_count"], [2340, 3900])
        self.assertEqual(fourth["format"], "THREAD")
        self.assertEqual(fourth["franchise_id"], "secrets_reveal_fallout_thread")
        self.assertEqual(fourth["portfolio_role"], "secondary")
        self.assertEqual(fourth["subreddits"], ["AskReddit"])
        self.assertEqual(fourth["target_duration_minutes"], [24, 30])
        self.assertEqual(fourth["response_count"], [13, 15])
        self.assertEqual(fourth["aggregate_response_word_count"], [3120, 3900])
        self.assertEqual(fourth["comic_page_count"], [16, 20])
        self.assertEqual(
            fourth["source_status"],
            "local_contract_ready_github_canary_required",
        )
        self.assertTrue(fourth["artifact_ready"])
        self.assertFalse(fourth["live_source_verified"])
        self.assertFalse(fourth["production_ready"])

    def test_missing_bundle_family_row_fails_closed(self):
        channel = copy.deepcopy(self.channel)
        channel["source_family_plan"] = [
            item for item in channel["source_family_plan"]
            if item.get("scraper_family") != "human_drama"
        ]
        with self.assertRaises(acc1_story_strategy.StrategyContractError):
            acc1_story_strategy.resolve_pilot_source_plan(channel, "pilot_01")

    def test_topic_mix_is_never_used_as_a_source_plan_fallback(self):
        channel = copy.deepcopy(self.channel)
        channel["topic_mix"] = [{"family": "unrelated_legacy_family", "weight": 1.0}]
        plan = acc1_story_strategy.resolve_pilot_source_plan(channel, "pilot_01")
        self.assertEqual(plan["topic_family"], "human_drama")

        channel["source_family_plan"] = []
        with self.assertRaises(acc1_story_strategy.StrategyContractError):
            acc1_story_strategy.resolve_pilot_source_plan(channel, "pilot_01")

    def test_missing_pilot_subreddit_fails_closed(self):
        channel = copy.deepcopy(self.channel)
        channel["subreddits"].remove("MaliciousCompliance")
        with self.assertRaises(acc1_story_strategy.StrategyContractError):
            acc1_story_strategy.resolve_pilot_source_plan(channel, "pilot_02")

    def test_thread_pilot_routes_but_remains_live_unverified(self):
        plan = acc1_story_strategy.resolve_pilot_source_plan(self.channel, "pilot_04")
        self.assertEqual(plan["collector_contract"], "bounded_top_level_full_body_v1")
        self.assertEqual(
            plan["search_queries"],
            [
                '"family secret" AND (discovered OR revealed OR exposed OR "found out")',
                '"dark secret" AND (discovered OR revealed OR exposed OR "found out")',
                "confession AND (aftermath OR fallout OR consequences OR changed)",
                "(secret OR confession) AND (discovered OR revealed OR exposed) "
                "AND (story OR experience OR happened)",
            ],
        )
        self.assertEqual(plan["search_sort"], "comments")
        self.assertEqual(plan["search_time_filter"], "year")
        self.assertTrue(plan["artifact_ready"])
        self.assertFalse(plan["live_source_verified"])
        self.assertFalse(plan["production_ready"])

    def test_pilot_06_uses_evergreen_unexplained_portfolio(self):
        plan = acc1_story_strategy.resolve_pilot_source_plan(
            self.channel, "pilot_06"
        )
        self.assertEqual(plan["franchise_id"], "matrix_unexplained_thread")
        self.assertEqual(plan["search_time_filter"], "all")
        self.assertEqual(plan["prompt_policy"], "unexplained_first_v1")
        self.assertEqual(
            plan["search_queries"],
            [
                "(unexplained OR unexplainable) "
                "AND (story OR experience OR happened OR witnessed)",
                "(paranormal OR supernatural) "
                "AND (story OR experience OR happened OR witnessed)",
                '("no proof" OR "no explanation") '
                "AND (story OR experience OR happened OR witnessed)",
                '("glitch in the matrix" OR "glitch in reality" OR "time slip" '
                'OR "lost time" OR "impossible coincidence") '
                "AND (story OR experience OR happened OR witnessed)",
            ],
        )

    def test_pilot_06_unexplained_first_policy_cannot_silently_drift(self):
        channel = copy.deepcopy(self.channel)
        pilot = next(
            item for item in channel["pilot_matrix"] if item["id"] == "pilot_06"
        )
        pilot["prompt_policy"] = "generic_scary_mix"
        with self.assertRaisesRegex(
            acc1_story_strategy.StrategyContractError,
            "prompt_policy must equal unexplained_first_v1",
        ):
            acc1_story_strategy.resolve_pilot_source_plan(channel, "pilot_06")

    def test_thread_search_portfolio_is_exact_and_cannot_silently_broaden(self):
        channel = copy.deepcopy(self.channel)
        pilot = next(
            item for item in channel["pilot_matrix"] if item["id"] == "pilot_04"
        )
        pilot["search_queries"][0] = "(confession OR secret)"
        with self.assertRaisesRegex(
            acc1_story_strategy.StrategyContractError,
            "canonical pillar portfolio",
        ):
            acc1_story_strategy.resolve_pilot_source_plan(channel, "pilot_04")

    def test_thread_time_window_is_exact_and_cannot_silently_drift(self):
        channel = copy.deepcopy(self.channel)
        pilot = next(
            item for item in channel["pilot_matrix"] if item["id"] == "pilot_06"
        )
        pilot["search_time_filter"] = "year"
        with self.assertRaisesRegex(
            acc1_story_strategy.StrategyContractError,
            "search_time_filter must equal all",
        ):
            acc1_story_strategy.resolve_pilot_source_plan(channel, "pilot_06")

    def test_franchise_role_and_packaging_cannot_drift(self):
        channel = copy.deepcopy(self.channel)
        pilot = next(
            item for item in channel["pilot_matrix"] if item["id"] == "pilot_05"
        )
        pilot["portfolio_role"] = "core"
        with self.assertRaisesRegex(
            acc1_story_strategy.StrategyContractError,
            "canonical franchise contract",
        ):
            acc1_story_strategy.resolve_pilot_source_plan(channel, "pilot_05")

    def test_narrative_saga_does_not_append_comments(self):
        plan = acc1_story_strategy.resolve_comment_plan("SAGA", "narrative_story")
        self.assertEqual(plan["mode"], "none")
        self.assertEqual(plan["count"], [0, 0])
        self.assertFalse(plan["use_comment_voice"])

    def test_question_saga_uses_small_selected_answer_coda(self):
        plan = acc1_story_strategy.resolve_comment_plan("SAGA", "question_prompt")
        self.assertEqual(plan["mode"], "selected_answers")
        self.assertEqual(plan["count"], [2, 4])
        self.assertTrue(plan["use_comment_voice"])

    def test_bundle_uses_narrative_sources_without_comments(self):
        plan = acc1_story_strategy.resolve_comment_plan("BUNDLE", "narrative_story")
        self.assertEqual(plan["mode"], "none")
        self.assertFalse(plan["required"])
        with self.assertRaises(acc1_story_strategy.StrategyContractError):
            acc1_story_strategy.resolve_comment_plan("BUNDLE", "question_prompt")

    def test_thread_requires_question_and_thirteen_to_fifteen_responses(self):
        plan = acc1_story_strategy.resolve_comment_plan("THREAD", "question_prompt")
        self.assertEqual(plan["mode"], "required_responses")
        self.assertEqual(plan["count"], [13, 15])
        with self.assertRaises(acc1_story_strategy.StrategyContractError):
            acc1_story_strategy.resolve_comment_plan("THREAD", "narrative_story")


class Acc1GreenlightTests(unittest.TestCase):
    def test_valid_saga_passes(self):
        payload, queue, review = valid_bound_saga()
        report = acc1_story_strategy.validate_greenlight(
            payload, source_queue=queue, topic_review=review,
        )
        self.assertEqual(report["status"], "PASS", report["failures"])
        self.assertGreaterEqual(report["score"], 75)
        self.assertTrue(report["selected_source_verified"])

    def test_artifact_bindings_are_required(self):
        payload, queue, review = valid_bound_saga()
        payload["artifact_bindings"]["review_sha256"] = "not-a-hash"
        report = acc1_story_strategy.validate_greenlight(
            payload, source_queue=queue, topic_review=review,
        )
        self.assertEqual(report["status"], "BLOCKED")
        self.assertTrue(any("review_sha256" in item for item in report["failures"]))

    def test_artifact_bindings_verify_actual_queue_and_review(self):
        payload, queue, review = valid_bound_saga()
        report = acc1_story_strategy.validate_greenlight(
            payload, source_queue=queue, topic_review=review,
        )
        self.assertEqual(report["status"], "PASS", report["failures"])
        self.assertTrue(report["artifact_bindings_verified"])

    def test_artifact_binding_tamper_fails_closed(self):
        payload, queue, review = valid_bound_saga()
        tampered_queue = {**queue, "selected_post_id": "tampered"}
        report = acc1_story_strategy.validate_greenlight(
            payload, source_queue=tampered_queue, topic_review=review,
        )
        self.assertEqual(report["status"], "BLOCKED")
        self.assertFalse(report["artifact_bindings_verified"])
        self.assertTrue(any("source queue" in item for item in report["failures"]))

    def test_greenlight_cannot_bind_a_different_reviewed_post(self):
        payload, queue, review = valid_bound_saga()
        payload["source"]["post_id"] = "other-post"
        report = acc1_story_strategy.validate_greenlight(
            payload, source_queue=queue, topic_review=review,
        )
        self.assertEqual(report["status"], "BLOCKED")
        self.assertFalse(report["selected_source_verified"])
        self.assertTrue(any("top_topics" in item for item in report["failures"]))

    def test_greenlight_without_exact_artifacts_blocks(self):
        report = acc1_story_strategy.validate_greenlight(valid_greenlight())
        self.assertEqual(report["status"], "BLOCKED")
        self.assertFalse(report["artifact_bindings_verified"])

    def test_unknown_pillar_blocks(self):
        payload = valid_greenlight()
        payload["pillar"] = "random_viral_topic"
        report = acc1_story_strategy.validate_greenlight(payload)
        self.assertEqual(report["status"], "BLOCKED")

    def test_link_dependent_source_blocks(self):
        payload = valid_greenlight()
        payload["source"]["depends_on_screenshot_or_link"] = True
        report = acc1_story_strategy.validate_greenlight(payload)
        self.assertTrue(any("screenshot" in item for item in report["failures"]))

    def test_fictional_as_real_blocks(self):
        payload = valid_greenlight()
        payload["source"]["fictional_as_real"] = True
        report = acc1_story_strategy.validate_greenlight(payload)
        self.assertTrue(any("fictional_as_real" in item for item in report["failures"]))

    def test_thread_needs_complete_diverse_responses(self):
        payload = valid_greenlight()
        payload["format"] = "THREAD"
        payload["source"].pop("primary_story_count")
        payload["source"].update({"response_count": 12, "responses_are_diverse": False})
        report = acc1_story_strategy.validate_greenlight(payload)
        self.assertEqual(report["status"], "BLOCKED")
        self.assertTrue(any("13-15" in item for item in report["failures"]))

    def test_thread_greenlight_accepts_the_local_collector_contract(self):
        payload = valid_greenlight()
        payload["format"] = "THREAD"
        payload["pillar"] = "confessions_awkward_taboo"
        payload["source"].pop("primary_story_count")
        payload["source"].update({"response_count": 13, "responses_are_diverse": True})
        config = json.loads((ROOT / "channels.json").read_text(encoding="utf-8"))
        channel = next(item for item in config["channels"] if item["id"] == "acc1")
        report = acc1_story_strategy.validate_greenlight(payload, channel=channel)
        self.assertEqual(report["status"], "BLOCKED")
        self.assertFalse(any("collector is not ready" in item for item in report["failures"]))

    def test_weak_total_score_blocks(self):
        payload = valid_greenlight()
        payload["scores"] = {key: 1 for key in acc1_story_strategy.GREENLIGHT_SCORE_MAX}
        report = acc1_story_strategy.validate_greenlight(payload)
        self.assertTrue(any("at least 75" in item for item in report["failures"]))


if __name__ == "__main__":
    unittest.main()
