import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import acc1_episode_factory as factory
from acc1_daily_planner import build_daily_plan


ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = "webpot-ru/nebula-core-v3"
WORKFLOW = ".github/workflows/acc1_daily_episode.yml"
HEAD_SHA = "a" * 40


def _source(
    *,
    source_id: str,
    role: str,
    body: str,
    pillar: str,
) -> dict:
    digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
    return {
        "source_id": source_id,
        "post_id": source_id,
        "title": f"Fixture {source_id}",
        "body": body,
        "source_body": body,
        "body_sha256": digest,
        "source_body_sha256": digest,
        "source_url": (
            f"https://www.reddit.com/r/AskReddit/comments/{source_id}/fixture/"
        ),
        "author": f"author-{source_id}",
        "subreddit": "AskReddit",
        "story_signature": f"signature-{source_id}",
        "truth_mode": "unverified_personal_account",
        "role": role,
        "source_role": role,
        "pillar": pillar,
        "complete": True,
        "payoff_complete": True,
        "depends_on_screenshot_or_link": False,
        "fictional_as_real": False,
    }


def _thread_contract(plan: dict, *, response_count: int = 13) -> tuple:
    candidates = []
    queue_entries = []
    manifests = []
    for candidate_index in range(3):
        prompt_id = f"prompt-{candidate_index}"
        prompt = _source(
            source_id=prompt_id,
            role="prompt",
            body=f"Полный вопрос для кандидата {candidate_index}.",
            pillar=plan["pillar"],
        )
        responses = []
        manifest_responses = []
        for response_index in range(response_count):
            response_id = f"response-{candidate_index}-{response_index}"
            body = " ".join(
                f"слово{candidate_index}а{response_index}б{word_index}"
                for word_index in range(240)
            )
            response = _source(
                source_id=response_id,
                role="response",
                body=body,
                pillar=plan["pillar"],
            )
            responses.append(response)
            manifest_responses.append(
                {
                    "id": response_id,
                    "body": body,
                    "word_count": 240,
                }
            )
        aggregate_words = response_count * 240
        manifest = {
            "schema_version": 2,
            "status": "READY",
            "channel_id": "acc1",
            "format": "THREAD",
            "prompt": {"id": prompt_id},
            "response_count": response_count,
            "aggregate_response_word_count": aggregate_words,
            "responses": manifest_responses,
            "publication_authorized": False,
        }
        manifest["manifest_sha256"] = factory.canonical_hash(manifest)
        manifests.append(manifest)
        sources = [prompt, *responses]
        candidates.append(
            {
                "candidate_id": f"thread-{prompt_id}",
                "pilot_id": plan["pilot_id"],
                "format": plan["format"],
                "pillar": plan["pillar"],
                "sources": sources,
                "thread_manifest_sha256": manifest["manifest_sha256"],
            }
        )
        queue_entries.extend(
            {
                "post_id": source["post_id"],
                "source_body": source["body"],
                "source_body_sha256": source["body_sha256"],
            }
            for source in sources
        )

    plan_sha256 = factory.canonical_hash(plan)
    queue = {
        "version": 1,
        "entries": queue_entries,
        "daily_plan_sha256": plan_sha256,
        "publication_authorized": False,
    }
    review = {
        "version": 1,
        "status": "review_ready",
        "candidate_count": len(candidates),
        "thread_manifests": manifests,
        "daily_plan_sha256": plan_sha256,
        "publication_authorized": False,
    }
    pool = {
        "version": 1,
        "status": "SOURCE_FINALISTS_READY",
        "channel_id": "acc1",
        "episode_key": plan["episode_key"],
        "pilot_id": plan["pilot_id"],
        "format": plan["format"],
        "pillar": plan["pillar"],
        "daily_plan_sha256": plan_sha256,
        "candidates": candidates,
        "candidate_count": len(candidates),
        "paid_review_candidate_count": len(candidates),
        "production_authorized": False,
        "publication_authorized": False,
    }
    pool["candidate_pool_sha256"] = factory._self_hash(
        pool,
        "candidate_pool_sha256",
    )
    stage = {
        "version": 1,
        "status": "SOURCE_READY",
        "network_accessed": True,
        "network_mode": "bounded_read_only_reddit",
        "reddit_http_request_cap": 24,
        "reddit_http_requests_observed": 22,
        "daily_plan_sha256": plan_sha256,
        "source_queue_sha256": factory.canonical_hash(queue),
        "source_review_sha256": factory.canonical_hash(review),
        "candidate_pool_sha256": pool["candidate_pool_sha256"],
        "candidate_count": len(candidates),
        "publication_authorized": False,
    }
    stage["source_stage_sha256"] = factory._self_hash(
        stage,
        "source_stage_sha256",
    )
    return stage, pool, queue, review


def _write_contract(root: Path, plan: dict, contract: tuple) -> None:
    stage, pool, queue, review = contract
    for filename, payload in (
        ("daily-plan.json", plan),
        ("source-stage.json", stage),
        ("candidate-pool.json", pool),
        ("source-queue.json", queue),
        ("source-review.json", review),
    ):
        (root / filename).write_text(
            json.dumps(payload, ensure_ascii=False),
            encoding="utf-8",
        )


class Acc1SourceOnlyTests(unittest.TestCase):
    def setUp(self):
        self.plan = build_daily_plan(
            ROOT / "channels.json",
            production_date="2026-07-27",
            pilot_override="pilot_04",
        )

    def test_seals_hash_bound_thread_source_without_paid_authority(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            _write_contract(root, self.plan, _thread_contract(self.plan))
            with mock.patch.object(factory, "_validate_base_candidate_pool"):
                result = factory.run_source_only_receipt(
                    daily_plan=self.plan,
                    workdir=root,
                    channels_path=ROOT / "channels.json",
                    reddit_request_cap=24,
                    repository=REPOSITORY,
                    workflow_path=WORKFLOW,
                    run_id=301,
                    run_attempt=1,
                    head_sha=HEAD_SHA,
                )
            stored = json.loads(
                (root / "source-only-result.json").read_text(encoding="utf-8")
            )

        self.assertEqual(result, stored)
        self.assertEqual(result["status"], "SOURCE_ONLY_READY")
        self.assertEqual(result["candidate_count"], 3)
        self.assertEqual(result["reddit_http_requests_observed"], 22)
        self.assertEqual(
            [item["response_count"] for item in result["candidate_metrics"]],
            [13, 13, 13],
        )
        self.assertEqual(
            [
                item["aggregate_response_word_count"]
                for item in result["candidate_metrics"]
            ],
            [3120, 3120, 3120],
        )
        self.assertEqual(
            result["paid_provider_calls_submitted"],
            {"openai": 0, "vectorengine": 0, "ai33": 0},
        )
        self.assertFalse(result["youtube_called"])
        self.assertFalse(result["production_authorized"])
        self.assertFalse(result["publication_authorized"])
        self.assertTrue(
            factory._verify_self_hash(
                result,
                "source_only_result_sha256",
            )
        )

    def test_rejects_resealed_thread_below_production_response_envelope(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            _write_contract(
                root,
                self.plan,
                _thread_contract(self.plan, response_count=12),
            )
            with (
                mock.patch.object(factory, "_validate_base_candidate_pool"),
                self.assertRaisesRegex(
                    factory.EpisodeFactoryError,
                    "runtime contract mismatch",
                ),
            ):
                factory.run_source_only_receipt(
                    daily_plan=self.plan,
                    workdir=root,
                    channels_path=ROOT / "channels.json",
                    reddit_request_cap=24,
                    repository=REPOSITORY,
                    workflow_path=WORKFLOW,
                    run_id=302,
                    run_attempt=1,
                    head_sha=HEAD_SHA,
                )
            self.assertFalse((root / "source-only-result.json").exists())

    def test_refuses_replayed_run_identity_before_sealing(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            _write_contract(root, self.plan, _thread_contract(self.plan))
            with self.assertRaisesRegex(
                factory.EpisodeFactoryError,
                "refuses replayed",
            ):
                factory.run_source_only_receipt(
                    daily_plan=self.plan,
                    workdir=root,
                    channels_path=ROOT / "channels.json",
                    reddit_request_cap=24,
                    repository=REPOSITORY,
                    workflow_path=WORKFLOW,
                    run_id=303,
                    run_attempt=2,
                    head_sha=HEAD_SHA,
                )


if __name__ == "__main__":
    unittest.main()
