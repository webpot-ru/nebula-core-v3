import copy
import hashlib
import json
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest import mock

import acc1_episode_factory as factory
from acc1_daily_planner import build_daily_plan
from openai_client import OpenAIJSONResult, OpenAIUsage
from scripts.acc1_spend_lock import build_lease, self_hash


ROOT = Path(__file__).resolve().parents[1]


class EpisodeFactoryTests(unittest.TestCase):
    def setUp(self):
        self.plan = build_daily_plan(
            ROOT / "channels.json",
            production_date="2026-07-14",
            pilot_override="pilot_01",
        )

    def _lease_source_contract(self, candidate_count=3):
        candidates = []
        queue_entries = []
        for index in range(candidate_count):
            source_id = f"source-{index + 1}"
            body = f"Complete source reservation fixture body number {index + 1}."
            source = {
                "source_id": source_id,
                "source_url": (
                    f"https://www.reddit.com/r/test/comments/{source_id}/fixture/"
                ),
                "body": body,
                "body_sha256": hashlib.sha256(body.encode("utf-8")).hexdigest(),
                "story_signature": f"fixture-signature-{index + 1}",
            }
            candidates.append({
                "candidate_id": f"candidate-{index}",
                "sources": [source],
            })
            queue_entries.append({"post_id": source_id})
        queue = {
            "version": 1,
            "entries": queue_entries,
            "publication_authorized": False,
        }
        review = {
            "version": 1,
            "status": "review_ready",
            "publication_authorized": False,
        }
        pool = {
            "version": 1,
            "status": "SOURCE_FINALISTS_READY",
            "episode_key": self.plan["episode_key"],
            "daily_plan_sha256": factory.canonical_hash(self.plan),
            "candidate_count": candidate_count,
            "candidates": candidates,
            "publication_authorized": False,
        }
        pool["candidate_pool_sha256"] = self_hash(pool, "candidate_pool_sha256")
        stage = {
            "version": 1,
            "status": "SOURCE_READY",
            "daily_plan_sha256": factory.canonical_hash(self.plan),
            "source_queue_sha256": factory.canonical_hash(queue),
            "source_review_sha256": factory.canonical_hash(review),
            "candidate_pool_sha256": pool["candidate_pool_sha256"],
            "publication_authorized": False,
        }
        stage["source_stage_sha256"] = self_hash(stage, "source_stage_sha256")
        return queue, review, pool, stage

    def test_daily_plan_is_rederived_not_trusted(self):
        report = factory.validate_daily_plan(self.plan, ROOT / "channels.json")
        self.assertEqual(report, self.plan)
        changed = json.loads(json.dumps(self.plan))
        changed["pillar"] = "work_money_justice"
        with self.assertRaisesRegex(factory.EpisodeFactoryError, "does not exactly match"):
            factory.validate_daily_plan(changed, ROOT / "channels.json")

    def test_canonical_auto_plan_rederives_without_becoming_manual_override(self):
        automatic = build_daily_plan(
            ROOT / "channels.json",
            production_date="2026-07-14",
        )
        self.assertEqual(automatic["selection"]["mode"], "canonical_daily_cycle")
        self.assertEqual(
            factory.validate_daily_plan(automatic, ROOT / "channels.json"),
            automatic,
        )
        tampered = copy.deepcopy(automatic)
        tampered["selection"]["mode"] = "forged_mode"
        with self.assertRaisesRegex(factory.EpisodeFactoryError, "selection mode is invalid"):
            factory.validate_daily_plan(tampered, ROOT / "channels.json")

    def test_preflight_calls_no_external_provider(self):
        with tempfile.TemporaryDirectory() as temp:
            report = factory.run_preflight(
                daily_plan=self.plan,
                workdir=Path(temp),
                channels_path=ROOT / "channels.json",
            )
            stored = json.loads((Path(temp) / "factory-preflight.json").read_text())
        self.assertEqual(report["status"], "PREFLIGHT_PASS")
        self.assertEqual(stored["would_call_reddit"], False)
        self.assertEqual(stored["would_upload_youtube"], False)
        self.assertFalse(stored["publication_authorized"])

    def test_source_cli_requires_exact_confirmation_before_client(self):
        with tempfile.TemporaryDirectory() as temp:
            plan_path = Path(temp) / "daily-plan.json"
            plan_path.write_text(json.dumps(self.plan), encoding="utf-8")
            with self.assertRaisesRegex(factory.EpisodeFactoryError, "confirm_reddit_read"):
                factory.main([
                    "--plan", str(plan_path),
                    "--workdir", temp,
                    "--channels", str(ROOT / "channels.json"),
                    "--stage", "source",
                ])

    def test_source_stage_uses_three_window_reserve_and_blocks_invalid_pool_before_ready(self):
        dark_plan = build_daily_plan(
            ROOT / "channels.json",
            production_date="2026-07-18",
            pilot_override="pilot_03",
        )
        captured = {}

        def fake_fetch(**kwargs):
            captured.update(kwargs)
            factory._atomic_json(Path(kwargs["producer_queue_output"]), {"entries": []})
            return {"post_id": "placeholder"}

        invalid_candidates = [
            {
                "candidate_id": f"invalid-{index}",
                "pilot_id": dark_plan["pilot_id"],
                "format": dark_plan["format"],
                "pillar": dark_plan["pillar"],
                "sources": [],
            }
            for index in range(3)
        ]
        fake_reddit = mock.Mock()
        fake_reddit._core._requestor.request_count = 1
        with (
            tempfile.TemporaryDirectory() as temp,
            mock.patch("scraper.AI_QUALITY_ENABLED", False),
            mock.patch("scraper.AI_QUALITY_FAIL_OPEN", False),
            mock.patch.object(factory, "fetch_best_story", side_effect=fake_fetch),
            mock.patch.object(
                factory, "build_review", return_value={"status": "review_ready"},
            ),
            mock.patch.object(
                factory, "_saga_candidates", return_value=invalid_candidates,
            ),
        ):
            workdir = Path(temp)
            exclusions = {
                "version": 1,
                "status": "VALIDATED_RESERVED_SOURCE_EXCLUSIONS",
                "inspected_leases": 1,
                "source_ids": ["old-source"],
                "story_signatures": ["old-signature"],
                "publication_authorized": False,
            }
            exclusions["reserved_source_exclusions_sha256"] = factory._self_hash(
                exclusions, "reserved_source_exclusions_sha256",
            )
            exclusions_path = workdir / "reserved-source-exclusions.json"
            factory._atomic_json(exclusions_path, exclusions)
            with self.assertRaisesRegex(factory.EpisodeFactoryError, "sources"):
                factory.run_source_stage(
                    daily_plan=dark_plan,
                    workdir=workdir,
                    channels_path=ROOT / "channels.json",
                    confirm_reddit_read=True,
                    reddit_request_cap=24,
                    reserved_source_exclusions_path=exclusions_path,
                    reddit_factory=lambda **_kwargs: fake_reddit,
                )
            self.assertFalse((workdir / "candidate-pool.json").exists())
            self.assertFalse((workdir / "source-stage.json").exists())
        self.assertEqual(captured["max_time_windows_per_topic"], 3)
        self.assertEqual(captured["excluded_source_ids"], {"old-source"})
        self.assertEqual(captured["excluded_story_signatures"], {"old-signature"})

    def test_thread_source_expands_bounded_prompt_pool_and_persists_failure_diagnostics(self):
        thread_plan = build_daily_plan(
            ROOT / "channels.json",
            production_date="2026-07-15",
            pilot_override="pilot_04",
        )
        captured = {}

        def fake_collect(*_args, **kwargs):
            captured.update(kwargs)
            return [({}, {})]

        candidates = [
            {"candidate_id": "thread-one", "sources": []},
            {"candidate_id": "thread-two", "sources": []},
        ]
        queue = {"version": 1, "entries": [{"post_id": "prompt-one"}]}
        review = {"version": 1, "status": "review_ready", "candidate_count": 2}
        fake_reddit = mock.Mock()
        fake_reddit._core._requestor.request_count = 17

        with (
            tempfile.TemporaryDirectory() as temp,
            mock.patch("scraper.AI_QUALITY_ENABLED", False),
            mock.patch("scraper.AI_QUALITY_FAIL_OPEN", False),
            mock.patch.object(
                factory,
                "collect_thread_source_candidates",
                side_effect=fake_collect,
            ),
            mock.patch.object(
                factory,
                "_thread_candidates",
                return_value=(candidates, queue, review),
            ),
        ):
            workdir = Path(temp)
            with self.assertRaisesRegex(factory.EpisodeFactoryError, "found 2"):
                factory.run_source_stage(
                    daily_plan=thread_plan,
                    workdir=workdir,
                    channels_path=ROOT / "channels.json",
                    confirm_reddit_read=True,
                    reddit_request_cap=24,
                    reddit_factory=lambda **_kwargs: fake_reddit,
                )
            diagnostics = json.loads(
                (workdir / "source-diagnostics.json").read_text(encoding="utf-8")
            )

        self.assertEqual(captured["candidate_limit"], 20)
        self.assertEqual(captured["response_scan_limit"], 60)
        self.assertEqual(diagnostics["candidate_count"], 2)
        self.assertEqual(diagnostics["reddit_http_requests_observed"], 17)
        self.assertEqual(
            diagnostics["status"], "BLOCKED_INSUFFICIENT_SOURCE_FINALISTS"
        )
        self.assertTrue(
            factory._verify_self_hash(
                diagnostics, "source_diagnostics_sha256"
            )
        )
        self.assertFalse(diagnostics["publication_authorized"])

    def test_bundle_selector_failure_persists_exact_source_diagnostics(self):
        bundle_plan = build_daily_plan(
            ROOT / "channels.json",
            production_date="2026-07-16",
            pilot_override="pilot_02",
        )
        queue = {
            "version": 1,
            "entries": [{"post_id": "one", "source_body": "complete body"}],
        }
        review = {
            "version": 1,
            "status": "review_ready",
            "candidate_reviews": [],
        }
        fake_reddit = mock.Mock()
        fake_reddit._core._requestor.request_count = 13

        def fake_fetch(**kwargs):
            Path(kwargs["producer_queue_output"]).write_text(
                json.dumps(queue), encoding="utf-8",
            )
            return {"post_id": "one"}

        with (
            tempfile.TemporaryDirectory() as temp,
            mock.patch("scraper.AI_QUALITY_ENABLED", False),
            mock.patch("scraper.AI_QUALITY_FAIL_OPEN", False),
            mock.patch.object(factory, "fetch_best_story", side_effect=fake_fetch),
            mock.patch.object(factory, "build_review", return_value=review),
            mock.patch.object(
                factory,
                "_bundle_candidates",
                side_effect=factory.EpisodeFactoryError(
                    "valid_subsets=1 eligible_candidates=5 rejected_candidates=14"
                ),
            ),
        ):
            workdir = Path(temp)
            with self.assertRaisesRegex(factory.EpisodeFactoryError, "valid_subsets=1"):
                factory.run_source_stage(
                    daily_plan=bundle_plan,
                    workdir=workdir,
                    channels_path=ROOT / "channels.json",
                    confirm_reddit_read=True,
                    reddit_request_cap=24,
                    reddit_factory=lambda **_kwargs: fake_reddit,
                )
            diagnostics = json.loads(
                (workdir / "source-diagnostics.json").read_text(encoding="utf-8")
            )

        self.assertEqual(diagnostics["status"], "BLOCKED_BUNDLE_FINALISTS")
        self.assertIn("valid_subsets=1", diagnostics["failure"])
        self.assertEqual(diagnostics["reddit_http_requests_observed"], 13)
        self.assertTrue(
            factory._verify_self_hash(diagnostics, "source_diagnostics_sha256")
        )
        self.assertFalse(diagnostics["publication_authorized"])

    def test_story_source_preserves_false_link_dependency_and_fails_closed_when_missing(self):
        body = "A complete self-contained story with a clear ending."
        entry = {
            "post_id": "self-contained",
            "title": "Self-contained story",
            "url": "https://www.reddit.com/r/test/comments/self-contained/story/",
            "source_body": body,
            "source_body_sha256": hashlib.sha256(body.encode("utf-8")).hexdigest(),
            "source_media": [],
        }
        reviewed = {
            "truth_mode": "unverified_personal_account",
            "complete": True,
            "payoff_complete": True,
            "depends_on_screenshot_or_link": False,
        }

        source = factory._story_source(entry, reviewed, self.plan)
        self.assertFalse(source["depends_on_screenshot_or_link"])

        unknown = factory._story_source(
            entry,
            {key: value for key, value in reviewed.items()
             if key != "depends_on_screenshot_or_link"},
            self.plan,
        )
        self.assertTrue(unknown["depends_on_screenshot_or_link"])

    def test_base_source_contract_failure_persists_exact_diagnostics(self):
        bundle_plan = build_daily_plan(
            ROOT / "channels.json",
            production_date="2026-07-16",
            pilot_override="pilot_02",
        )
        queue = {"version": 1, "entries": [{"post_id": "one"}]}
        review = {"version": 1, "status": "review_ready"}
        candidates = [{
            "candidate_id": f"candidate-{index}",
            "sources": [{
                "source_id": f"source-{index}",
                "body": "complete narrative source",
                "depends_on_screenshot_or_link": True,
            }],
        } for index in range(3)]
        fake_reddit = mock.Mock()
        fake_reddit._core._requestor.request_count = 9

        def fake_fetch(**kwargs):
            Path(kwargs["producer_queue_output"]).write_text(
                json.dumps(queue), encoding="utf-8",
            )
            return {"post_id": "one"}

        with (
            tempfile.TemporaryDirectory() as temp,
            mock.patch("scraper.AI_QUALITY_ENABLED", False),
            mock.patch("scraper.AI_QUALITY_FAIL_OPEN", False),
            mock.patch.object(factory, "fetch_best_story", side_effect=fake_fetch),
            mock.patch.object(factory, "build_review", return_value=review),
            mock.patch.object(
                factory, "_bundle_candidates", return_value=(candidates, {}),
            ),
            mock.patch.object(
                factory,
                "_validate_base_candidate_pool",
                side_effect=factory.EpisodeFactoryError("link-dependent fixture"),
            ),
        ):
            workdir = Path(temp)
            with self.assertRaisesRegex(factory.EpisodeFactoryError, "link-dependent fixture"):
                factory.run_source_stage(
                    daily_plan=bundle_plan,
                    workdir=workdir,
                    channels_path=ROOT / "channels.json",
                    confirm_reddit_read=True,
                    reddit_request_cap=24,
                    reddit_factory=lambda **_kwargs: fake_reddit,
                )
            diagnostics = json.loads(
                (workdir / "source-diagnostics.json").read_text(encoding="utf-8")
            )

        self.assertEqual(diagnostics["status"], "BLOCKED_BASE_SOURCE_CONTRACT")
        self.assertEqual(diagnostics["failure"], "link-dependent fixture")
        self.assertEqual(diagnostics["candidate_count"], 3)
        self.assertEqual(diagnostics["reddit_http_requests_observed"], 9)
        self.assertTrue(
            factory._verify_self_hash(diagnostics, "source_diagnostics_sha256")
        )
        self.assertFalse(diagnostics["publication_authorized"])

    def test_reddit_request_count_supports_current_praw_session_shape(self):
        current = mock.Mock()
        current._core.requestor.request_count = 23
        self.assertEqual(factory._reddit_request_count(current), 23)

        legacy_requestor = mock.Mock()
        legacy_requestor.request_count = 17
        legacy_core = type("LegacyCore", (), {"_requestor": legacy_requestor})()
        legacy = type("LegacyReddit", (), {"_core": legacy_core})()
        self.assertEqual(factory._reddit_request_count(legacy), 17)

    def test_call_budget_refuses_before_extra_provider_call(self):
        calls = []

        def provider(**kwargs):
            calls.append(kwargs)
            return {"ok": True}

        budget = factory.CallBudget(provider, cap=2, label="test")
        budget(prompt="one", model="m")
        budget(prompt="two", model="m")
        with self.assertRaisesRegex(factory.EpisodeFactoryError, "cap exhausted"):
            budget(prompt="three", model="m")
        self.assertEqual(len(calls), 2)
        self.assertEqual(len(budget.calls), 2)

    def test_paid_provider_budgets_disable_hidden_retries(self):
        for label in ("openai", "image"):
            with self.subTest(label=label):
                calls = []
                budget = factory.CallBudget(
                    lambda **kwargs: calls.append(kwargs), cap=1, label=label
                )
                budget(prompt="bounded request")
                self.assertEqual(calls[0]["retries"], 0)

    def test_candidate_prompts_define_weighted_score_ranges_and_link_dependency(self):
        candidate = {
            "candidate_id": "candidate-1",
            "sources": [{
                "source_id": "source-1",
                "role": "story",
                "title": "Complete story",
                "body": "A complete self-contained story with a clear ending.",
                "truth_mode": "unverified_personal_account",
                "source_url": "https://www.reddit.com/r/test/comments/source-1/story/",
                "payoff_complete": True,
                "depends_on_screenshot_or_link": False,
                "source_discovery_signals": {},
            }],
        }
        producer_prompt = factory._candidate_prompt(candidate, self.plan, "producer")
        self.assertIn("WEIGHTED POINTS, never percentages", producer_prompt)
        self.assertIn('"hook_specificity": 15', producer_prompt)
        self.assertIn('"renderability": 5', producer_prompt)
        self.assertIn("canonical Reddit source_url is provenance", producer_prompt)
        self.assertIn('"depends_on_screenshot_or_link": false', producer_prompt)

        candidate["producer_proposal"] = {"review": {"verdict": "PASS"}}
        critic_prompt = factory._candidate_prompt(candidate, self.plan, "critic")
        self.assertIn("WEIGHTED POINTS, never percentages", critic_prompt)
        self.assertIn("screenshot_or_link_dependent", critic_prompt)

    def test_candidate_prompts_keep_labeled_nosleep_fiction_inside_viewer_promise(self):
        candidate = {
            "candidate_id": "fiction-1",
            "sources": [{
                "source_id": "source-1",
                "role": "story",
                "title": "A complete horror story",
                "body": "A complete self-contained fictional story with a clear ending.",
                "truth_mode": "fiction",
                "source_url": "https://www.reddit.com/r/nosleep/comments/source-1/story/",
                "payoff_complete": True,
                "depends_on_screenshot_or_link": False,
                "source_discovery_signals": {},
            }],
        }

        prompt = factory._candidate_prompt(candidate, self.plan, "producer")

        self.assertIn("truth_mode=fiction IS inside the acc1 viewer promise", prompt)
        self.assertIn("Без выдуманных продолжений", prompt)
        self.assertIn("Это художественная история с Reddit.", prompt)
        self.assertIn(
            "Do not use fictional_as_real or viewer_promise_mismatch merely because a source is fiction",
            prompt,
        )

    def test_quote_only_repair_changes_evidence_without_changing_creative_claim(self):
        body = "The basement door opened and there was no human shadow behind it."
        candidate = {
            "candidate_id": "candidate-1",
            "sources": [{"source_id": "source-1", "body": body}],
            "cold_open": {
                "text": "В подвале у него не оказалось тени",
                "source_id": "source-1",
                "source_quote": "there was no shadow",
            },
            "reviews": [
                {"verdict": "PASS", "veto_flags": []},
                {"verdict": "PASS", "veto_flags": []},
            ],
        }
        preliminary = {
            "candidate_reviews": [{
                "candidate_id": "candidate-1",
                "failures": [
                    "candidates[0].cold_open.source_quote must be an exact quote from source_id"
                ],
            }],
        }

        class FakeOpenAI:
            def __init__(self):
                self.calls = []

            def __call__(self, **kwargs):
                self.calls.append(kwargs)
                return {"repairs": [{
                    "path": "cold_open.source_quote",
                    "source_id": "source-1",
                    "source_quote": body,
                }]}

        provider = FakeOpenAI()
        repaired, reports = factory._repair_quote_only_candidates(
            [candidate], preliminary, provider,
        )

        self.assertEqual(len(provider.calls), 1)
        self.assertEqual(repaired[0]["cold_open"]["source_quote"], body)
        self.assertEqual(repaired[0]["cold_open"]["text"], candidate["cold_open"]["text"])
        self.assertEqual(candidate["cold_open"]["source_quote"], "there was no shadow")
        self.assertEqual(reports[0]["status"], "EVIDENCE_ONLY_REPAIR_APPLIED")

    def test_translate_script_builds_truthful_deterministic_intro(self):
        sources = []
        for index in range(2):
            body = " ".join([f"source-{index + 1}"] + ["word"] * 1198 + ["payoff"])
            sources.append({
                "source_id": f"source-{index + 1}",
                "title": f"Story {index + 1}",
                "body": body,
                "role": "story",
                "truth_mode": "unverified_personal_account",
            })
        winner = {
            "cold_open": {
                "text": (
                    "Сначала семья услышала один вопрос, а затем привычный вечер "
                    "превратился в серьёзный конфликт."
                ),
                "source_id": "source-1",
                "source_quote": "source-1 word word word",
            },
            "sources": sources,
            "story_beats": [],
            "originality_plan": {},
        }
        translated = [
            {
                "title": "Первая история",
                "body": "Полный перевод первой истории. Развязка сохранена.",
                "translation_audit": {"revisions": 0},
            },
            {
                "title": "Вторая история",
                "body": "Полный перевод второй истории. Развязка сохранена.",
                "translation_audit": {"revisions": 0},
            },
        ]
        episode_plan = {
            "episode_plan_sha256": "a" * 64,
            "daily_plan_sha256": "b" * 64,
        }
        playoff = {"playoff_sha256": "c" * 64}
        with (
            tempfile.TemporaryDirectory() as temp,
            mock.patch.object(
                factory,
                "translate_and_review_story",
                side_effect=translated,
            ),
            mock.patch.object(
                factory,
                "validate_episode_script",
                return_value={"status": "PASS", "failures": []},
            ) as validate,
        ):
            script = factory._translate_script(
                winner,
                daily_plan=self.plan,
                episode_plan=episode_plan,
                playoff=playoff,
                openai=mock.Mock(),
                checkpoint_dir=Path(temp),
            )
        parts = {item["kind"]: item["text"] for item in script["intro_contract"]["parts"]}
        self.assertEqual(
            parts["episode_promise"],
            "Сегодня — две законченные истории с Reddit.",
        )
        self.assertEqual(
            parts["truth_disclosure"],
            "Это личные рассказы пользователей Reddit, не подтверждённые независимо.",
        )
        self.assertEqual(
            parts["support_thanks"],
            "Спасибо всем, кто помогает каналу расти.",
        )
        self.assertIn("Устраивайтесь поудобнее", parts["brand_sting"])
        self.assertNotIn("спонсор", script["intro_ru"].casefold())
        self.assertEqual(script["intro_ru"], script["intro_contract"]["intro_ru"])
        validate.assert_called_once()

    def test_malformed_structured_candidate_uses_reserve_without_aborting_transport(self):
        candidates = [
            {"candidate_id": f"candidate-{index}", "sources": []}
            for index in range(5)
        ]
        responses = [{}]
        for _index in range(4):
            responses.extend(({"review": {}}, {}))

        def provider(**_kwargs):
            return responses.pop(0)

        budget = factory.CallBudget(provider, cap=9, label="openai")
        enriched, producer_reports, critic_reports = factory._enrich_candidates(
            candidates, self.plan, budget,
        )
        self.assertEqual(len(enriched), 4)
        self.assertEqual(len(budget.calls), 9)
        self.assertEqual(
            producer_reports[0]["status"],
            "BLOCKED_INVALID_STRUCTURED_RESPONSE",
        )
        self.assertEqual(
            critic_reports[0]["status"],
            "NOT_RUN_INVALID_PRODUCER_RESPONSE",
        )

    def test_malformed_structured_candidate_blocks_when_only_two_reserves_remain(self):
        candidates = [
            {"candidate_id": f"candidate-{index}", "sources": []}
            for index in range(3)
        ]
        responses = [{}, {"review": {}}, {}, {"review": {}}, {}]
        budget = factory.CallBudget(
            lambda **_kwargs: responses.pop(0), cap=5, label="openai",
        )
        enriched, _producer_reports, _critic_reports = factory._enrich_candidates(
            candidates, self.plan, budget,
        )
        result = factory.run_playoff({
            "daily_plan": self.plan,
            "daily_plan_sha256": factory.canonical_hash(self.plan),
            "candidates": enriched,
        })
        self.assertEqual(len(enriched), 2)
        self.assertEqual(result["status"], "BLOCKED")
        self.assertIn("at least 3 finalists are required", result["failures"])

    @staticmethod
    def _runtime_script(word_count: int) -> dict:
        disclosure = (
            "Это личный рассказ пользователя Reddit, не подтверждённый независимо."
        )
        return {
            "truth_disclosure_ru": disclosure,
            "intro_ru": f"Сегодня читаем законченную историю. {disclosure}",
            "outro_ru": "Обсудим эту историю в комментариях.",
            "stories": [{
                "narration_ru": " ".join(["история"] * word_count),
                "source_snapshot": {
                    "post_id": "runtime-source",
                    "truth_mode": "unverified_personal_account",
                },
            }],
        }

    def test_pre_tts_runtime_estimate_uses_locked_daily_target(self):
        report = factory._validate_estimated_runtime(
            self._runtime_script(2350), self.plan,
        )
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["locked_target_minutes"], [18.0, 30.0])
        self.assertGreaterEqual(report["estimated_minutes"], 18.0)

    def test_pre_tts_runtime_estimate_blocks_short_translation(self):
        with self.assertRaisesRegex(factory.EpisodeFactoryError, "outside the pre-TTS"):
            factory._validate_estimated_runtime(
                self._runtime_script(100), self.plan,
            )

    def test_ambiguous_provider_attempt_is_journaled_and_not_resubmitted(self):
        with tempfile.TemporaryDirectory() as temp:
            journal = Path(temp) / "openai.json"
            calls = []

            def ambiguous_provider(**kwargs):
                calls.append(kwargs)
                raise RuntimeError("connection lost after submission")

            budget = factory.CallBudget(
                ambiguous_provider,
                cap=2,
                label="openai",
                journal_path=journal,
            )
            with self.assertRaises(RuntimeError):
                budget(prompt="one paid request")
            stored = json.loads(journal.read_text(encoding="utf-8"))
            self.assertEqual(stored["attempts"][0]["status"], "AMBIGUOUS_ERROR")
            self.assertEqual(stored["attempts"][0]["error_type"], "RuntimeError")
            with self.assertRaisesRegex(factory.EpisodeFactoryError, "unresolved paid attempt"):
                budget(prompt="must not resubmit in the same process")
            with self.assertRaisesRegex(factory.EpisodeFactoryError, "non-empty"):
                factory.CallBudget(
                    ambiguous_provider,
                    cap=2,
                    label="openai",
                    journal_path=journal,
                )
            self.assertEqual(len(calls), 1)

    def test_openai_budget_rejects_unproven_service_tier_and_accounts_usage(self):
        with tempfile.TemporaryDirectory() as temp:
            journal = Path(temp) / "openai.json"
            budget = factory.CallBudget(
                lambda **_kwargs: OpenAIJSONResult(
                    payload={"translated": True},
                    usage=OpenAIUsage(
                        input_tokens=2,
                        cached_input_tokens=1,
                        output_tokens=1,
                        total_tokens=3,
                        reasoning_tokens=0,
                    ),
                    service_tier="default",
                ),
                cap=1,
                label="openai",
                journal_path=journal,
                token_cap=1_000,
            )
            with self.assertRaisesRegex(
                factory.EpisodeFactoryError,
                "required Flex service tier",
            ):
                budget(
                    prompt="one translation",
                    model=factory.OPENAI_MODEL,
                    max_output_tokens=1,
                )
            stored = json.loads(journal.read_text(encoding="utf-8"))
            self.assertEqual(
                stored["attempts"][0]["status"],
                "BLOCKED_SERVICE_TIER_MISMATCH",
            )
            self.assertEqual(stored["attempts"][0]["service_tier"], "default")
            self.assertEqual(stored["usage_totals"], {
                "input_tokens": 2,
                "cached_input_tokens": 1,
                "output_tokens": 1,
                "total_tokens": 3,
                "reasoning_tokens": 0,
            })

    def test_ai33_inline_audio_response_is_journaled_without_serializing_bytes(self):
        with tempfile.TemporaryDirectory() as temp:
            journal = Path(temp) / "ai33.json"
            budget = factory.CallBudget(
                lambda **_kwargs: {"success": True, "audio_bytes": b"audio-data"},
                cap=1,
                label="ai33",
                journal_path=journal,
            )
            response = budget(
                text="hello",
                voice_id="voice",
                model_id="eleven_v3",
            )
            self.assertEqual(response["audio_bytes"], b"audio-data")
            journal_text = journal.read_text(encoding="utf-8")
            stored = json.loads(journal_text)
            self.assertEqual(stored["attempts"][0]["status"], "COMPLETE")
            self.assertRegex(
                stored["attempts"][0]["response_sha256"], r"^[0-9a-f]{64}$"
            )
            self.assertNotIn("audio-data", journal_text)

    def test_live_stage_functions_require_confirmations_at_the_core_boundary(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(factory.EpisodeFactoryError, "confirm_reddit_read"):
                factory.run_source_stage(
                    daily_plan=self.plan,
                    workdir=Path(temp),
                    channels_path=ROOT / "channels.json",
                    confirm_reddit_read=False,
                    reddit_request_cap=1,
                )
            with self.assertRaisesRegex(factory.EpisodeFactoryError, "confirm_openai_spend"):
                factory.run_produce_stage(
                    daily_plan=self.plan,
                    workdir=Path(temp),
                    channels_path=ROOT / "channels.json",
                    confirm_openai_spend=False,
                    openai_call_cap=96,
                    openai_token_cap=500_000,
                    confirm_image_spend=True,
                    image_call_cap=1,
                    confirm_ai33_spend=True,
                    ai33_call_cap=1,
                )

    def test_paid_preflight_blocks_missing_provider_secrets_before_lease(self):
        queue, review, pool, stage = self._lease_source_contract()
        cap_contract = {
            "openai_call_cap": 96,
            "openai_token_cap": 500_000,
            "image_call_cap": 16,
            "ai33_call_cap": 96,
            "required_openai_calls": 1,
            "required_image_calls": 1,
            "required_ai33_calls": 1,
        }
        cases = (
            (
                {
                    "GEMINI_PROVIDER": "vectorengine",
                    "OPENAI_API_KEY": "test-only",
                    "AI33_API_KEY": "test-only",
                },
                "image credentials",
            ),
            (
                {
                    "GEMINI_PROVIDER": "vectorengine",
                    "VECTORENGINE_API_KEY": "test-only",
                    "AI33_API_KEY": "test-only",
                },
                "OPENAI_API_KEY",
            ),
            (
                {
                    "GEMINI_PROVIDER": "vectorengine",
                    "VECTORENGINE_API_KEY": "test-only",
                    "OPENAI_API_KEY": "test-only",
                },
                "AI33_API_KEY",
            ),
        )
        for environment, expected_error in cases:
            with self.subTest(expected_error=expected_error), tempfile.TemporaryDirectory() as temp:
                workdir = Path(temp)
                with (
                    mock.patch.object(
                        factory,
                        "_source_artifacts",
                        return_value=(queue, review, pool, stage),
                    ),
                    mock.patch.object(
                        factory,
                        "_paid_candidate_cap_contract",
                        return_value=cap_contract,
                    ),
                    mock.patch.dict("os.environ", environment, clear=True),
                ):
                    with self.assertRaisesRegex(
                        factory.EpisodeFactoryError, expected_error,
                    ):
                        factory.run_paid_preflight(
                            daily_plan=self.plan,
                            workdir=workdir,
                            channels_path=ROOT / "channels.json",
                            confirm_openai_spend=True,
                            openai_call_cap=96,
                            openai_token_cap=500_000,
                            confirm_image_spend=True,
                            image_call_cap=16,
                            confirm_ai33_spend=True,
                            ai33_call_cap=96,
                        )
                self.assertFalse((workdir / "paid-preflight.json").exists())
                self.assertFalse((workdir / "spend-lease.json").exists())

    def test_paid_preflight_low_cap_blocks_before_credentials_or_lease(self):
        queue, review, pool, stage = self._lease_source_contract()
        pool = copy.deepcopy(pool)
        pool["candidates"] = [
            {
                "candidate_id": f"candidate-{index}",
                "sources": [{
                    "source_id": f"source-{index}",
                    "body": "A complete source narrative with a clear event and ending.",
                }],
            }
            for index in range(3)
        ]
        with tempfile.TemporaryDirectory() as temp:
            workdir = Path(temp)
            with (
                mock.patch.object(
                    factory,
                    "_source_artifacts",
                    return_value=(queue, review, pool, stage),
                ),
                mock.patch.object(factory, "_validate_source_narratability"),
                mock.patch.object(
                    factory,
                    "validate_base_candidate",
                    return_value={"status": "PASS", "failures": []},
                ),
                mock.patch.dict("os.environ", {}, clear=True),
            ):
                with self.assertRaisesRegex(factory.EpisodeFactoryError, "OpenAI cap"):
                    factory.run_paid_preflight(
                        daily_plan=self.plan,
                        workdir=workdir,
                        channels_path=ROOT / "channels.json",
                        confirm_openai_spend=True,
                        openai_call_cap=1,
                        openai_token_cap=500_000,
                        confirm_image_spend=True,
                        image_call_cap=16,
                        confirm_ai33_spend=True,
                        ai33_call_cap=96,
                    )
            self.assertFalse((workdir / "paid-preflight.json").exists())
            self.assertFalse((workdir / "spend-lease.json").exists())

    def test_paid_preflight_passes_without_provider_calls_or_lease_creation(self):
        queue, review, pool, stage = self._lease_source_contract()
        cap_contract = {
            "openai_call_cap": 96,
            "openai_token_cap": 500_000,
            "image_call_cap": 16,
            "ai33_call_cap": 96,
            "required_openai_calls": 96,
            "required_image_calls": 6,
            "required_ai33_calls": 8,
        }
        with tempfile.TemporaryDirectory() as temp:
            workdir = Path(temp)
            with (
                mock.patch.object(
                    factory,
                    "_source_artifacts",
                    return_value=(queue, review, pool, stage),
                ),
                mock.patch.object(
                    factory,
                    "_paid_candidate_cap_contract",
                    return_value=cap_contract,
                ),
                mock.patch.dict(
                    "os.environ",
                    {
                        "GEMINI_PROVIDER": "vectorengine",
                        "VECTORENGINE_API_KEY": "test-only",
                        "OPENAI_API_KEY": "test-only",
                        "AI33_API_KEY": "test-only",
                    },
                    clear=True,
                ),
            ):
                report = factory.run_paid_preflight(
                    daily_plan=self.plan,
                    workdir=workdir,
                    channels_path=ROOT / "channels.json",
                    confirm_openai_spend=True,
                    openai_call_cap=96,
                    openai_token_cap=500_000,
                    confirm_image_spend=True,
                    image_call_cap=16,
                    confirm_ai33_spend=True,
                    ai33_call_cap=96,
                )
            self.assertEqual(report["status"], "PAID_PREFLIGHT_PASS")
            self.assertFalse(report["would_call_openai"])
            self.assertFalse(report["would_call_image_provider"])
            self.assertFalse(report["would_call_ai33"])
            self.assertEqual(
                report["runtime_budget"]["workflow_timeout_minutes"], 360,
            )
            self.assertEqual(
                report["runtime_budget"]["produce_timeout_minutes"], 300,
            )
            self.assertEqual(
                report["runtime_budget"]["ai33_deadline_from_produce_start_minutes"],
                240,
            )
            self.assertEqual(
                report["runtime_budget"]["post_ai33_render_qa_reserve_minutes"],
                60,
            )
            self.assertFalse(report["runtime_budget"]["automatic_paid_resume"])
            self.assertTrue((workdir / "paid-preflight.json").is_file())
            self.assertFalse((workdir / "spend-lease.json").exists())

    def test_tampered_spend_lease_blocks_before_any_paid_provider(self):
        queue, review, pool, stage = self._lease_source_contract()
        lease = build_lease(
            plan=self.plan,
            source_stage=stage,
            candidate_pool=pool,
            source_queue=queue,
            source_review=review,
            repository="webpot-ru/nebula-core-v3",
            workflow_path=factory.SPEND_LOCK_WORKFLOW_PATH,
            run_id=101,
            run_attempt=1,
            head_sha="a" * 40,
            requested_caps={
                "reddit_request_cap": 24,
                "openai_call_cap": 96,
                "openai_token_cap": 500_000,
                "image_call_cap": 16,
                "ai33_call_cap": 96,
            },
            confirmations={
                "reddit_read": True,
                "openai_spend": True,
                "image_spend": True,
                "ai33_spend": True,
            },
            created_at="2026-07-14T12:00:00Z",
        )
        lease["requested_caps"]["openai_call_cap"] = 95
        lease["lease_sha256"] = self_hash(lease, "lease_sha256")
        paid_preflight = {
            "caps": {
                "openai_call_cap": 96,
                "openai_token_cap": 500_000,
                "image_call_cap": 16,
                "ai33_call_cap": 96,
            },
        }
        paid_calls = []
        with tempfile.TemporaryDirectory() as temp:
            workdir = Path(temp)
            factory._atomic_json(workdir / "spend-lease.json", lease)
            with (
                mock.patch.object(
                    factory,
                    "_paid_preflight_contract",
                    return_value=(queue, review, pool, stage, paid_preflight),
                ),
                mock.patch.dict("os.environ", {"GITHUB_ACTIONS": "false"}, clear=True),
            ):
                with self.assertRaisesRegex(
                    factory.EpisodeFactoryError, "exact production caps",
                ):
                    factory.run_produce_stage(
                        daily_plan=self.plan,
                        workdir=workdir,
                        channels_path=ROOT / "channels.json",
                        confirm_openai_spend=True,
                        openai_call_cap=96,
                        openai_token_cap=500_000,
                        confirm_image_spend=True,
                        image_call_cap=16,
                        confirm_ai33_spend=True,
                        ai33_call_cap=96,
                        reddit_request_cap=24,
                        spend_lease_path=workdir / "spend-lease.json",
                        openai_provider=lambda **kwargs: paid_calls.append(("openai", kwargs)),
                        image_provider=lambda **kwargs: paid_calls.append(("image", kwargs)),
                    )
        self.assertEqual(paid_calls, [])

    def test_reddit_urls_are_normalized_without_changing_path(self):
        expected = "https://www.reddit.com/r/test/comments/abc/topic/"
        self.assertEqual(factory._canonical_reddit_url("https://reddit.com/r/test/comments/abc/topic/"), expected)
        self.assertEqual(factory._canonical_reddit_url("/r/test/comments/abc/topic/"), expected)
        with self.assertRaises(factory.EpisodeFactoryError):
            factory._canonical_reddit_url("https://example.com/r/test")

    def test_thread_response_boundaries_do_not_consume_transition_tts_tasks(self):
        self.assertEqual(factory._transition_after("THREAD", 1, 16), "")
        self.assertEqual(
            factory._transition_after("BUNDLE", 1, 3),
            "А теперь — следующая полная история.",
        )
        self.assertEqual(factory._transition_after("BUNDLE", 3, 3), "")

    def test_saga_playoff_keeps_five_source_candidates_for_three_pass_reserve(self):
        entries = []
        reviewed = []
        for index in range(6):
            post_id = f"post-{index}"
            body = f"complete source body {index} with a preserved payoff"
            digest = hashlib.sha256(body.encode()).hexdigest()
            entries.append({
                "post_id": post_id,
                "title": f"Title {index}",
                "author": f"author-{index}",
                "subreddit": "nosleep",
                "url": f"https://www.reddit.com/r/nosleep/comments/{post_id}/topic/",
                "source_body": body,
                "source_body_sha256": digest,
                "story_signature": f"signature-{index}",
            })
            reviewed.append({
                "post_id": post_id,
                "source_body": body,
                "source_body_sha256": digest,
                "truth_mode": "fiction",
                "complete": True,
                "payoff_complete": True,
                "depends_on_screenshot_or_link": False,
            })
        candidates = factory._saga_candidates(
            {"entries": entries}, {"top_topics": reviewed},
            {"pilot_id": "pilot_03", "pillar": "strange_dark_unexplained"},
        )
        self.assertEqual([item["candidate_id"] for item in candidates], [
            "saga-post-0", "saga-post-1", "saga-post-2", "saga-post-3",
            "saga-post-4",
        ])

    def test_image_budget_includes_every_scene_and_thumbnail(self):
        self.assertEqual(factory._required_image_calls("SAGA", 1), 6)
        self.assertEqual(factory._required_image_calls("BUNDLE", 5), 16)
        self.assertEqual(factory._required_image_calls("THREAD", 16), 4)

    def test_minimum_tts_budget_is_known_before_paid_text_calls(self):
        self.assertEqual(factory._minimum_tts_calls("SAGA", 1), 3)
        self.assertEqual(factory._minimum_tts_calls("BUNDLE", 5), 11)
        self.assertEqual(factory._minimum_tts_calls("THREAD", 9), 11)

    def test_ai33_budget_covers_accepted_translation_expansion_before_gemini(self):
        # Sixteen 200-word sources remain inside the collector's 3,250-word
        # episode envelope while exercising the accepted character expansion.
        source_body = " ".join(["source"] * 200)
        candidates = [
            {
                "candidate_id": f"thread-{candidate_index}",
                "sources": [
                    {"body": source_body}
                    for _source_index in range(16)
                ],
            }
            for candidate_index in range(5)
        ]
        self.assertEqual(factory._required_ai33_calls(candidates, "THREAD"), 50)
        self.assertLessEqual(factory._required_ai33_calls(candidates, "THREAD"), 64)

    def test_ai33_cap_96_covers_every_source_format_character_envelope(self):
        eleven_character_word = "abcdefghijk"

        saga = [{
            "candidate_id": "saga",
            "sources": [{"body": " ".join([eleven_character_word] * 3900)}],
        }]
        self.assertEqual(factory._required_ai33_calls(saga, "SAGA"), 45)

        bundle = [{
            "candidate_id": "bundle",
            "sources": [
                {"body": " ".join([eleven_character_word] * 780)}
                for _ in range(5)
            ],
        }]
        self.assertEqual(factory._required_ai33_calls(bundle, "BUNDLE"), 56)

        thread = [{
            "candidate_id": "thread",
            "sources": [
                {"body": " ".join(["p" * 79] * 25), "role": "prompt"},
                *[
                    {"body": " ".join([eleven_character_word] * 216), "role": "response"}
                    for _ in range(15)
                ],
            ],
        }]
        self.assertLessEqual(factory._required_ai33_calls(thread, "THREAD"), 96)

    def test_ai33_ceiling_blocks_before_any_gemini_call(self):
        thread_plan = build_daily_plan(
            ROOT / "channels.json",
            production_date="2026-07-15",
            pilot_override="pilot_04",
        )
        def thread_source(source_index, role):
            if role == "prompt":
                body = "What professional experience changed how you understand your work?"
            else:
                body = " ".join(
                    (
                        f"During shift{source_index}x{step} I noticed clue{source_index}x{step}, "
                        f"asked witness{source_index}x{step}, checked record{source_index}x{step}, "
                        f"and explained outcome{source_index}x{step}."
                    )
                    for step in range(18)
                )
            source_id = f"source-{source_index}"
            return {
                "source_id": source_id,
                "body": body,
                "body_sha256": hashlib.sha256(body.encode()).hexdigest(),
                "source_url": f"https://www.reddit.com/r/AskReddit/comments/prompt/{source_id}/",
                "author": f"author-{source_index}",
                "story_signature": hashlib.sha256(source_id.encode()).hexdigest(),
                "truth_mode": "unverified_personal_account",
                "role": role,
                "pillar": thread_plan["pillar"],
                "complete": True,
                "payoff_complete": True,
                "depends_on_screenshot_or_link": False,
                "fictional_as_real": False,
            }
        candidates = [
            {
                "candidate_id": f"thread-{candidate_index}",
                "pilot_id": thread_plan["pilot_id"],
                "format": thread_plan["format"],
                "pillar": thread_plan["pillar"],
                "sources": [thread_source(0, "prompt")] + [
                    thread_source(source_index, "response")
                    for source_index in range(1, 12)
                ],
            }
            for candidate_index in range(5)
        ]
        with tempfile.TemporaryDirectory() as temp:
            workdir = Path(temp)
            gemini_calls = []
            with (
                mock.patch.object(
                    factory,
                    "_source_artifacts",
                    return_value=({}, {}, {"candidates": candidates}, {}),
                ),
                mock.patch.object(factory, "_channel_config", return_value={"id": "acc1"}),
                mock.patch.dict("os.environ", {"AI33_API_KEY": "test-only"}, clear=False),
            ):
                with self.assertRaisesRegex(factory.EpisodeFactoryError, "AI33 cap"):
                    factory.run_produce_stage(
                        daily_plan=thread_plan,
                        workdir=workdir,
                        channels_path=ROOT / "channels.json",
                        confirm_openai_spend=True,
                        openai_call_cap=96,
                        openai_token_cap=500_000,
                        confirm_image_spend=True,
                        image_call_cap=16,
                        confirm_ai33_spend=True,
                        ai33_call_cap=32,
                        openai_provider=lambda **kwargs: gemini_calls.append(kwargs),
                        image_provider=lambda **_kwargs: Path("unused"),
                    )
        self.assertEqual(gemini_calls, [])

    def test_missing_source_provenance_blocks_before_any_paid_review(self):
        body = " ".join(
            (
                f"At event{step} the narrator checked clue{step}, contacted witness{step}, "
                f"recorded outcome{step}, and finally explained consequence{step}."
            )
            for step in range(100)
        )

        def source(index):
            return {
                "source_id": f"source-{index}",
                "body": body.replace("event", f"event{index}x"),
                "source_url": f"https://www.reddit.com/r/test/comments/source{index}/story/",
                "author": f"author-{index}",
                "story_signature": f"signature-{index}",
                "truth_mode": "unverified_personal_account",
                "role": "story",
                "pillar": self.plan["pillar"],
                "complete": True,
                "payoff_complete": True,
                "depends_on_screenshot_or_link": False,
                "fictional_as_real": False,
            }

        for missing_field in ("author", "story_signature"):
            with self.subTest(missing_field=missing_field), tempfile.TemporaryDirectory() as temp:
                sources = [source(1), source(2)]
                for item in sources:
                    item["body_sha256"] = hashlib.sha256(item["body"].encode()).hexdigest()
                sources[0].pop(missing_field)
                candidates = [{
                    "candidate_id": f"candidate-{index}",
                    "pilot_id": self.plan["pilot_id"],
                    "format": self.plan["format"],
                    "pillar": self.plan["pillar"],
                    "sources": copy.deepcopy(sources),
                } for index in range(5)]
                gemini_calls = []
                with (
                    mock.patch.object(
                        factory,
                        "_source_artifacts",
                        return_value=({}, {}, {"candidates": candidates}, {}),
                    ),
                    mock.patch.object(factory, "_channel_config", return_value={"id": "acc1"}),
                    mock.patch.dict("os.environ", {"AI33_API_KEY": "test-only"}, clear=False),
                ):
                    with self.assertRaisesRegex(
                        factory.EpisodeFactoryError,
                        f"{missing_field}.*required",
                    ):
                        factory.run_produce_stage(
                            daily_plan=self.plan,
                            workdir=Path(temp),
                            channels_path=ROOT / "channels.json",
                            confirm_openai_spend=True,
                            openai_call_cap=96,
                            openai_token_cap=500_000,
                            confirm_image_spend=True,
                            image_call_cap=16,
                            confirm_ai33_spend=True,
                            ai33_call_cap=96,
                            openai_provider=lambda **kwargs: gemini_calls.append(kwargs),
                            image_provider=lambda **_kwargs: Path("unused"),
                        )
                self.assertEqual(gemini_calls, [])

    def test_text_budgets_cover_max_thread_fallback_before_first_call(self):
        candidates = [
            {
                "candidate_id": f"thread-{candidate_index}",
                "sources": [
                    {"body": f"response {source_index} with a complete short body"}
                    for source_index in range(16)
                ],
            }
            for candidate_index in range(5)
        ]
        self.assertEqual(factory._required_openai_calls(candidates), 112)

        for candidate in candidates:
            for source in candidate["sources"]:
                source["body"] = "First short paragraph.\n\nSecond one.\n\nThird one."
        self.assertEqual(factory._required_openai_calls(candidates), 112)

        for candidate in candidates:
            for source in candidate["sources"]:
                source["body"] = "First" + (" " * 20_000) + "short response."
        self.assertEqual(factory._required_openai_calls(candidates), 112)

    def test_self_hash_detects_release_manifest_tamper(self):
        manifest = {"status": "READY_FOR_HUMAN_REVIEW", "publication_authorized": False}
        manifest["release_candidate_manifest_sha256"] = factory._self_hash(
            manifest, "release_candidate_manifest_sha256",
        )
        self.assertTrue(factory._verify_self_hash(manifest, "release_candidate_manifest_sha256"))
        manifest["publication_authorized"] = True
        self.assertFalse(factory._verify_self_hash(manifest, "release_candidate_manifest_sha256"))

    def test_blocked_playoff_persists_paid_review_diagnostics(self):
        """A paid editorial rejection must retain its exact model evidence."""
        with tempfile.TemporaryDirectory() as temp:
            workdir = Path(temp)
            candidate = {"candidate_id": "candidate-1", "sources": [{"source_id": "s1"}]}
            paid_preflight = {
                "caps": {
                    "openai_call_cap": 96,
                    "openai_token_cap": 500_000,
                    "image_call_cap": 8,
                    "ai33_call_cap": 32,
                },
            }
            producer_reports = [{"candidate_id": "candidate-1", "status": "COMPLETE"}]
            critic_reports = [{"candidate_id": "candidate-1", "status": "COMPLETE"}]
            blocked = {
                "status": "BLOCKED",
                "failures": ["at least 3 finalists must independently PASS"],
                "publication_authorized": False,
            }
            with (
                mock.patch.object(
                    factory,
                    "_paid_preflight_contract",
                    return_value=({}, {}, {"candidates": [candidate]}, {}, paid_preflight),
                ),
                mock.patch.object(factory, "_validate_spend_lease_contract"),
                mock.patch.object(factory, "_channel_config", return_value={"id": "acc1"}),
                mock.patch.object(
                    factory,
                    "_enrich_candidates",
                    return_value=([candidate], producer_reports, critic_reports),
                ),
                mock.patch.object(factory, "run_playoff", return_value=blocked),
            ):
                with self.assertRaisesRegex(factory.EpisodeFactoryError, "independently PASS"):
                    factory.run_produce_stage(
                        daily_plan=self.plan,
                        workdir=workdir,
                        channels_path=ROOT / "channels.json",
                        confirm_openai_spend=True,
                        openai_call_cap=96,
                        openai_token_cap=500_000,
                        confirm_image_spend=True,
                        image_call_cap=8,
                        confirm_ai33_spend=True,
                        ai33_call_cap=32,
                        spend_lease_path=workdir / "spend-lease.json",
                    )
            self.assertEqual(
                json.loads((workdir / "producer-review.json").read_text())["results"],
                producer_reports,
            )
            self.assertEqual(
                json.loads((workdir / "critic-review.json").read_text())["results"],
                critic_reports,
            )
            self.assertEqual(
                json.loads((workdir / "topic-playoff.json").read_text()), blocked,
            )
            self.assertTrue((workdir / "topic-playoff-input.json").is_file())

    def test_produce_stage_passes_complete_tts_state_into_storyboard(self):
        """Exercise the orchestration seam without network or paid providers."""
        with tempfile.TemporaryDirectory() as temp:
            workdir = Path(temp)
            sources = []
            for source_index in range(1, 3):
                body = " ".join(
                    (
                        f"At moment{source_index}x{step} the narrator noticed clue{source_index}x{step}, "
                        f"contacted witness{source_index}x{step}, recorded outcome{source_index}x{step}, "
                        f"and finally explained consequence{source_index}x{step}."
                    )
                    for step in range(100)
                )
                sources.append({
                    "source_id": f"source-{source_index}",
                    "body": body,
                    "body_sha256": hashlib.sha256(body.encode()).hexdigest(),
                    "source_url": (
                        f"https://www.reddit.com/r/relationship_advice/comments/"
                        f"source{source_index}/story/"
                    ),
                    "author": f"author-{source_index}",
                    "story_signature": hashlib.sha256(
                        f"signature-{source_index}".encode()
                    ).hexdigest(),
                    "truth_mode": "unverified_personal_account",
                    "role": "story",
                    "pillar": self.plan["pillar"],
                    "complete": True,
                    "payoff_complete": True,
                    "depends_on_screenshot_or_link": False,
                    "fictional_as_real": False,
                })
            locked_options = [
                {
                    "youtube_title": f"Заголовок {index}",
                    "thumbnail_text": f"ТЕКСТ {index}",
                    "first_screen_promise": f"Обещание {index}",
                    "angle": f"angle-{index}",
                    "source_backing": "source quote",
                }
                for index in range(1, 4)
            ]
            candidates = [
                {
                    "candidate_id": f"candidate-{index}",
                    "pilot_id": self.plan["pilot_id"],
                    "format": self.plan["format"],
                    "pillar": self.plan["pillar"],
                    "sources": copy.deepcopy(sources),
                    "packaging_options": copy.deepcopy(locked_options),
                }
                for index in range(1, 6)
            ]
            pool = {
                "candidates": candidates,
                "candidate_pool_sha256": "8" * 64,
            }
            playoff = {
                "status": "READY_FOR_SCRIPTING",
                "playoff_sha256": "2" * 64,
                "winner": {
                    "candidate_id": "candidate-1",
                    "creative_plan_sha256": "6" * 64,
                },
            }
            episode_plan = {
                "episode_plan_sha256": "3" * 64,
                "daily_plan_sha256": "4" * 64,
            }
            script = {
                "episode_plan_sha256": episode_plan["episode_plan_sha256"],
                "daily_plan_sha256": episode_plan["daily_plan_sha256"],
                "title_ru": "Истории с Reddit",
                "truth_disclosure_ru": (
                    "Это личный рассказ пользователя Reddit, не подтверждённый независимо."
                ),
                "intro_ru": (
                    "Сегодня читаем историю. Это личный рассказ пользователя Reddit, "
                    "не подтверждённый независимо."
                ),
                "outro_ru": "Обсудим эту историю в комментариях.",
                "stories": [{
                    "title_ru": "Ночная история",
                    "narration_ru": "Автор рассказал законченную историю с ясным финалом.",
                    "source_snapshot": {
                        "post_id": "source-1",
                        "truth_mode": "unverified_personal_account",
                        "subreddit": "AskReddit",
                        "author": "source_author",
                    },
                }],
            }
            packaging = {
                "packaging_options": copy.deepcopy(locked_options),
                "selected_option_index": 0,
                "thumbnail_prompt": "source-bound scene",
            }
            tts_state = {
                "status": "COMPLETE",
                "episode_plan_sha256": episode_plan["episode_plan_sha256"],
                "daily_plan_sha256": episode_plan["daily_plan_sha256"],
            }
            order = []

            def fake_source_artifacts(*args, **kwargs):
                queue = {}
                review = {}
                source_stage = {"source_stage_sha256": "5" * 64}
                for path, payload in (
                    (workdir / "daily-plan.json", self.plan),
                    (workdir / "source-queue.json", queue),
                    (workdir / "source-review.json", review),
                    (workdir / "candidate-pool.json", pool),
                    (workdir / "source-stage.json", source_stage),
                ):
                    factory._atomic_json(path, payload)
                factory._atomic_json(
                    workdir / "spend-lease.json",
                    {"lease_sha256": "7" * 64, "publication_authorized": False},
                )
                return queue, review, pool, source_stage

            def fake_packaging(script_arg, playoff_arg, **kwargs):
                self.assertEqual(playoff_arg["winner_packaging_options"], locked_options)
                self.assertIsNot(playoff_arg["winner_packaging_options"], locked_options)
                self.assertNotIn("winner_packaging_options", playoff)
                return packaging

            def fake_packaging_validation(payload, script_arg, playoff_arg):
                self.assertEqual(playoff_arg["winner_packaging_options"], locked_options)
                return []

            def fake_playoff(playoff_input):
                result = copy.deepcopy(playoff)
                winner_candidate = playoff_input["candidates"][0]
                result["playoff_input_sha256"] = factory.canonical_hash(playoff_input)
                result["winner"]["candidate_contract_sha256"] = factory.canonical_hash(
                    winner_candidate
                )
                result["winner"]["packaging_options_sha256"] = factory.canonical_hash(
                    winner_candidate["packaging_options"]
                )
                result["playoff_sha256"] = factory._self_hash(
                    result, "playoff_sha256"
                )
                return result

            def image_provider(**kwargs):
                Path(kwargs["output_path"]).write_bytes(b"thumbnail-base")
                return Path(kwargs["output_path"])

            def fake_tts(*args, **kwargs):
                order.append("tts")
                self.assertEqual(Path(kwargs["artifact_root"]), workdir)
                audio = workdir / "tts" / "final.mp3"
                audio.parent.mkdir(parents=True, exist_ok=True)
                audio.write_bytes(b"audio")
                tts_state["final_audio_path"] = "tts/final.mp3"
                factory._atomic_json(
                    workdir / "tts" / "compilation_tts_state.json", tts_state
                )
                return tts_state

            def fake_storyboard(*args, **kwargs):
                order.append("storyboard")
                self.assertIs(kwargs.get("tts_state"), tts_state)
                return {"version": 2, "slides": [], "creative_manifest": {}}

            def fake_render(storyboard, artifact_root, output, **kwargs):
                order.append("render")
                Path(output).write_bytes(b"video")
                return {"status": "ok"}

            def fake_qa(*args, **kwargs):
                order.append("qa")
                return {"status": "PASS", "failures": []}

            def fake_overlay(base, output, text):
                Path(output).write_bytes(Path(base).read_bytes())
                return Path(output)

            def fake_images(script_arg, output_dir, **kwargs):
                self.assertEqual(Path(output_dir), workdir / "scene-images")
                self.assertEqual(Path(kwargs["artifact_root"]), workdir)
                return script_arg, []

            def fake_runtime_estimate(script_arg, plan_arg):
                self.assertIs(script_arg, script)
                self.assertIs(plan_arg, self.plan)
                return {
                    "version": 1,
                    "status": "PASS",
                    "estimated_minutes": 20.0,
                    "publication_authorized": False,
                }

            patchers = (
                mock.patch.object(factory, "_source_artifacts", side_effect=fake_source_artifacts),
                mock.patch.object(factory, "_channel_config", return_value={"id": "acc1"}),
                mock.patch.object(factory, "_enrich_candidates", return_value=(candidates, [], [])),
                mock.patch.object(factory, "run_playoff", side_effect=fake_playoff),
                mock.patch.object(factory, "_greenlight", return_value={}),
                mock.patch.object(
                    factory,
                    "_validate_spend_lease_contract",
                    return_value={"lease_sha256": "7" * 64},
                ),
                mock.patch.object(factory, "build_episode_manifest", return_value=episode_plan),
                mock.patch.object(factory, "_translate_script", return_value=script),
                mock.patch.object(factory, "_validate_estimated_runtime", side_effect=fake_runtime_estimate),
                mock.patch.object(factory, "generate_packaging", side_effect=fake_packaging),
                mock.patch.object(factory, "validate_packaging", side_effect=fake_packaging_validation),
                mock.patch.object(factory, "generate_episode_images", side_effect=fake_images),
                mock.patch.object(factory, "overlay_thumbnail_text", side_effect=fake_overlay),
                mock.patch.object(factory, "write_thumbnail_report", return_value={"status": "PASS"}),
                mock.patch.object(factory, "build_tts_chunks", return_value=[{"chunk_id": "one"}]),
                mock.patch.object(factory, "run_compilation_tts", side_effect=fake_tts),
                mock.patch.object(factory, "build_storyboard", side_effect=fake_storyboard),
                mock.patch.object(factory, "render_compilation", side_effect=fake_render),
                mock.patch.object(factory, "run_qa", side_effect=fake_qa),
                mock.patch.object(factory, "build_template", return_value={"status": "PENDING_HUMAN"}),
                mock.patch.dict(
                    "os.environ",
                    {
                        "GEMINI_PROVIDER": "vectorengine",
                        "VECTORENGINE_API_KEY": "test-only",
                        "OPENAI_API_KEY": "test-only",
                        "AI33_API_KEY": "test-only",
                    },
                    clear=False,
                ),
            )
            with ExitStack() as stack:
                for patcher in patchers:
                    stack.enter_context(patcher)
                result = factory.run_produce_stage(
                    daily_plan=self.plan,
                    workdir=workdir,
                    channels_path=ROOT / "channels.json",
                    confirm_openai_spend=True,
                    openai_call_cap=96,
                    openai_token_cap=500_000,
                    confirm_image_spend=True,
                    image_call_cap=16,
                    confirm_ai33_spend=True,
                    ai33_call_cap=96,
                    spend_lease_path=workdir / "spend-lease.json",
                    openai_provider=lambda **kwargs: {},
                    image_provider=image_provider,
                )

            self.assertEqual(order, ["tts", "storyboard", "render", "qa"])
            self.assertEqual(result["status"], "READY_FOR_HUMAN_REVIEW")
            self.assertFalse(result["publication_authorized"])
            self.assertTrue((workdir / "release-candidate-manifest.json").is_file())
            self.assertTrue((workdir / "factory-result.json").is_file())
            release = json.loads(
                (workdir / "release-candidate-manifest.json").read_text(encoding="utf-8")
            )
            self.assertEqual(len(release["artifact_sha256"]), 6)
            self.assertEqual(len(release["evidence_sha256"]), 24)
            self.assertIn("spend_lease", release["evidence_sha256"])
            self.assertIn("paid_preflight", release["evidence_sha256"])
            self.assertIn("runtime_estimate_report", release["evidence_sha256"])


if __name__ == "__main__":
    unittest.main()
