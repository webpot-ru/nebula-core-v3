import copy
import contextlib
import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from scripts.acc1_spend_lock import (
    LEASE_FILENAME,
    LEASE_RETENTION_DAYS,
    PROVIDER_CONTRACT,
    SpendLockError,
    build_lease,
    canonical_hash,
    main,
    scan_leases,
    self_hash,
    validate_lease_for_production,
)


REPOSITORY = "webpot-ru/nebula-core-v3"
WORKFLOW = ".github/workflows/acc1_daily_episode.yml"
HEAD_SHA = "a" * 40


def source_contract(
    episode_key="acc1/2026-07-14/pilot_01",
    candidate_count=5,
    source_prefix="post",
):
    production_date = episode_key.split("/")[1]
    pilot_id = episode_key.split("/")[2]
    plan = {
        "schema_version": "acc1_daily_episode_plan_v1",
        "status": "PLANNED_ARTIFACT_ONLY",
        "channel_id": "acc1",
        "production_date": production_date,
        "pilot_id": pilot_id,
        "episode_key": episode_key,
        "config_sha256": "1" * 64,
        "provider_spend_authorized": False,
        "publication_authorized": False,
    }
    queue = {
        "version": 1,
        "entries": [{"post_id": "post-1"}],
        "publication_authorized": False,
    }
    review = {
        "version": 1,
        "status": "review_ready",
        "publication_authorized": False,
    }
    candidates = []
    for index in range(candidate_count):
        source_id = f"{source_prefix}-{index}"
        body = f"Complete source body for {source_id}."
        candidates.append({
            "candidate_id": f"candidate-{index}",
            "sources": [{
                "source_id": source_id,
                "source_url": (
                    f"https://www.reddit.com/r/test/comments/{source_id}/story/"
                ),
                "body": body,
                "body_sha256": hashlib.sha256(body.encode("utf-8")).hexdigest(),
                "story_signature": f"signature-{source_id}",
            }],
        })
    pool = {
        "version": 1,
        "status": "SOURCE_FINALISTS_READY",
        "episode_key": episode_key,
        "daily_plan_sha256": canonical_hash(plan),
        "candidate_count": candidate_count,
        "candidates": candidates,
        "publication_authorized": False,
    }
    pool["candidate_pool_sha256"] = self_hash(pool, "candidate_pool_sha256")
    stage = {
        "version": 1,
        "status": "SOURCE_READY",
        "daily_plan_sha256": canonical_hash(plan),
        "source_queue_sha256": canonical_hash(queue),
        "source_review_sha256": canonical_hash(review),
        "candidate_pool_sha256": pool["candidate_pool_sha256"],
        "publication_authorized": False,
    }
    stage["source_stage_sha256"] = self_hash(stage, "source_stage_sha256")
    return plan, stage, pool, queue, review


def valid_lease(
    episode_key="acc1/2026-07-14/pilot_01",
    run_id=101,
    candidate_count=5,
    source_prefix="post",
):
    plan, stage, pool, queue, review = source_contract(
        episode_key, candidate_count, source_prefix,
    )
    return build_lease(
        plan=plan,
        source_stage=stage,
        candidate_pool=pool,
        source_queue=queue,
        source_review=review,
        repository=REPOSITORY,
        workflow_path=WORKFLOW,
        run_id=run_id,
        run_attempt=1,
        head_sha=HEAD_SHA,
        requested_caps={
            "reddit_request_cap": 24,
            "openai_call_cap": 64,
            "openai_token_cap": 1_000_000,
            "image_call_cap": 16,
            "ai33_call_cap": 96,
        },
        confirmations={
            "reddit_read": "true",
            "openai_spend": "true",
            "image_spend": "true",
            "ai33_spend": "true",
        },
        created_at="2026-07-14T12:00:00Z",
    )


def store_artifact(root: Path, lease, run_id=101, artifact_id=501):
    directory = root / f"{run_id}-{artifact_id}"
    directory.mkdir(parents=True)
    (directory / LEASE_FILENAME).write_text(
        json.dumps(lease, ensure_ascii=False), encoding="utf-8",
    )


class Acc1SpendLockTests(unittest.TestCase):
    def test_cli_create_uses_exact_artifact_inputs(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            plan, stage, pool, queue, review = source_contract()
            paths = {}
            for name, payload in {
                "plan": plan,
                "stage": stage,
                "pool": pool,
                "queue": queue,
                "review": review,
            }.items():
                path = root / f"{name}.json"
                path.write_text(json.dumps(payload), encoding="utf-8")
                paths[name] = path
            output = root / LEASE_FILENAME
            with contextlib.redirect_stdout(io.StringIO()):
                result = main([
                    "create",
                    "--plan", str(paths["plan"]),
                    "--source-stage", str(paths["stage"]),
                    "--candidate-pool", str(paths["pool"]),
                    "--source-queue", str(paths["queue"]),
                    "--source-review", str(paths["review"]),
                    "--output", str(output),
                    "--repository", REPOSITORY,
                    "--workflow-path", WORKFLOW,
                    "--run-id", "101",
                    "--run-attempt", "1",
                    "--head-sha", HEAD_SHA,
                    "--reddit-request-cap", "24",
                    "--openai-call-cap", "64",
                    "--openai-token-cap", "1000000",
                    "--image-call-cap", "16",
                    "--ai33-call-cap", "96",
                    "--confirm-reddit-read", "true",
                    "--confirm-openai-spend", "true",
                    "--confirm-image-spend", "true",
                    "--confirm-ai33-spend", "true",
                    "--created-at", "2026-07-14T12:00:00Z",
                ])
            stored = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(result, 0)
        self.assertEqual(stored["lease_sha256"], self_hash(stored, "lease_sha256"))

    def test_cli_post_source_scan_uses_all_bound_source_artifacts(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            leases_root = root / "leases"
            leases_root.mkdir()
            store_artifact(leases_root, valid_lease(), run_id=101)
            plan, stage, pool, queue, review = source_contract(
                "acc1/2026-07-15/pilot_04",
            )
            paths = {}
            for name, payload in {
                "plan": plan,
                "source-stage": stage,
                "candidate-pool": pool,
                "source-queue": queue,
                "source-review": review,
            }.items():
                path = root / f"{name}.json"
                path.write_text(json.dumps(payload), encoding="utf-8")
                paths[name] = path
            with self.assertRaisesRegex(SpendLockError, "overlaps paid source reservation"):
                main([
                    "scan",
                    "--plan", str(paths["plan"]),
                    "--leases-root", str(leases_root),
                    "--repository", REPOSITORY,
                    "--workflow-path", WORKFLOW,
                    "--current-run-id", "202",
                    "--source-stage", str(paths["source-stage"]),
                    "--candidate-pool", str(paths["candidate-pool"]),
                    "--source-queue", str(paths["source-queue"]),
                    "--source-review", str(paths["source-review"]),
                ])

    def test_lease_binds_source_caps_models_and_never_publication(self):
        lease = valid_lease()
        self.assertEqual(lease["schema_version"], "acc1_paid_spend_lease_v5")
        self.assertEqual(lease["retention_days"], LEASE_RETENTION_DAYS)
        self.assertEqual(lease["provider_contract"], PROVIDER_CONTRACT)
        self.assertEqual(lease["requested_caps"]["openai_call_cap"], 64)
        self.assertEqual(lease["requested_caps"]["openai_token_cap"], 1_000_000)
        self.assertEqual(lease["provider_contract"]["openai"], {
            "provider": "openai",
            "model": "gpt-5.4-2026-03-05",
            "reasoning_effort": "none",
            "max_output_tokens": 16_384,
            "automatic_retries": 0,
            "service_tier": "flex",
            "prompt_cache_key": "acc1-translation-json-v1",
            "request_timeout_seconds": 900,
        })
        self.assertEqual(lease["confirmations"], {
            "ai33_spend": True,
            "image_spend": True,
            "openai_spend": True,
            "reddit_read": True,
        })
        self.assertFalse(lease["publication_authorized"])
        self.assertEqual(lease["lease_sha256"], self_hash(lease, "lease_sha256"))
        self.assertEqual(len(lease["reserved_sources"]), 5)
        self.assertTrue(all(
            item["source_reservation_sha256"]
            == canonical_hash({
                field: item[field]
                for field in (
                    "source_id", "source_url", "body_sha256", "story_signature",
                )
            })
            for item in lease["reserved_sources"]
        ))
        self.assertEqual(set(lease["source_bindings"]), {
            "daily_plan_sha256",
            "config_sha256",
            "source_stage_sha256",
            "candidate_pool_sha256",
            "source_queue_sha256",
            "source_review_sha256",
        })

    def test_openai_caps_are_required_and_fail_closed_above_exact_maxima(self):
        plan, stage, pool, queue, review = source_contract()
        base = {
            "plan": plan,
            "source_stage": stage,
            "candidate_pool": pool,
            "source_queue": queue,
            "source_review": review,
            "repository": REPOSITORY,
            "workflow_path": WORKFLOW,
            "run_id": 101,
            "run_attempt": 1,
            "head_sha": HEAD_SHA,
            "requested_caps": {
                "reddit_request_cap": 24,
                "openai_call_cap": 64,
                "openai_token_cap": 1_000_000,
                "image_call_cap": 16,
                "ai33_call_cap": 96,
            },
            "confirmations": {
                "reddit_read": True,
                "openai_spend": True,
                "image_spend": True,
                "ai33_spend": True,
            },
            "created_at": "2026-07-14T12:00:00Z",
        }
        for field, value, expected in (
            ("openai_call_cap", 257, "between 1 and 256"),
            ("openai_token_cap", 1_000_001, "between 1 and 1000000"),
        ):
            with self.subTest(field=field):
                arguments = copy.deepcopy(base)
                arguments["requested_caps"][field] = value
                with self.assertRaisesRegex(SpendLockError, expected):
                    build_lease(**arguments)

        missing_cap = copy.deepcopy(base)
        missing_cap["requested_caps"].pop("openai_token_cap")
        with self.assertRaisesRegex(SpendLockError, "caps are incomplete"):
            build_lease(**missing_cap)

        missing_confirmation = copy.deepcopy(base)
        missing_confirmation["confirmations"].pop("openai_spend")
        with self.assertRaisesRegex(SpendLockError, "confirmations are incomplete"):
            build_lease(**missing_confirmation)

    def test_same_episode_other_run_is_blocked(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            store_artifact(root, valid_lease(), run_id=101)
            plan = source_contract()[0]
            with self.assertRaisesRegex(SpendLockError, "already protected"):
                scan_leases(
                    plan=plan,
                    leases_root=root,
                    repository=REPOSITORY,
                    workflow_path=WORKFLOW,
                    current_run_id=202,
                )

    def test_different_episode_passes(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            store_artifact(root, valid_lease(), run_id=101)
            plan = source_contract("acc1/2026-07-15/pilot_04")[0]
            exclusions_path = root / "reserved-source-exclusions.json"
            report = scan_leases(
                plan=plan,
                leases_root=root,
                repository=REPOSITORY,
                workflow_path=WORKFLOW,
                current_run_id=202,
                reserved_source_exclusions_output=exclusions_path,
            )
            exclusions = json.loads(exclusions_path.read_text(encoding="utf-8"))
        self.assertEqual(report["status"], "SPEND_LOCK_CLEAR")
        self.assertEqual(report["inspected_leases"], 1)
        self.assertEqual(report["prior_reserved_source_count"], 5)
        self.assertEqual(len(exclusions["source_ids"]), 5)
        self.assertEqual(len(exclusions["story_signatures"]), 5)
        self.assertEqual(
            exclusions["reserved_source_exclusions_sha256"],
            report["reserved_source_exclusions_sha256"],
        )
        self.assertFalse(report["source_reservation_checked"])
        self.assertFalse(report["publication_authorized"])

    def test_same_reserved_source_on_a_different_date_is_blocked_before_paid_spend(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            store_artifact(root, valid_lease(), run_id=101)
            plan, stage, pool, queue, review = source_contract(
                "acc1/2026-07-15/pilot_04",
            )
            with self.assertRaisesRegex(SpendLockError, "overlaps paid source reservation"):
                scan_leases(
                    plan=plan,
                    leases_root=root,
                    repository=REPOSITORY,
                    workflow_path=WORKFLOW,
                    current_run_id=202,
                    source_stage=stage,
                    candidate_pool=pool,
                    source_queue=queue,
                    source_review=review,
                )

    def test_disjoint_reserved_sources_on_a_different_date_pass(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            store_artifact(root, valid_lease(source_prefix="old"), run_id=101)
            plan, stage, pool, queue, review = source_contract(
                "acc1/2026-07-15/pilot_04", source_prefix="new",
            )
            report = scan_leases(
                plan=plan,
                leases_root=root,
                repository=REPOSITORY,
                workflow_path=WORKFLOW,
                current_run_id=202,
                source_stage=stage,
                candidate_pool=pool,
                source_queue=queue,
                source_review=review,
            )
        self.assertEqual(report["status"], "SPEND_LOCK_CLEAR")
        self.assertTrue(report["source_reservation_checked"])
        self.assertEqual(report["current_reserved_source_count"], 5)

    def test_body_hash_or_story_signature_overlap_blocks_even_when_ids_and_urls_change(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            prior = valid_lease(source_prefix="old")
            store_artifact(root, prior, run_id=101)
            plan, stage, pool, queue, review = source_contract(
                "acc1/2026-07-15/pilot_04", source_prefix="new",
            )
            prior_source = prior["reserved_sources"][0]
            current_source = pool["candidates"][0]["sources"][0]
            current_source["body"] = "Complete source body for old-0."
            current_source["body_sha256"] = prior_source["body_sha256"]
            current_source["story_signature"] = prior_source["story_signature"]
            pool["candidate_pool_sha256"] = self_hash(pool, "candidate_pool_sha256")
            stage["candidate_pool_sha256"] = pool["candidate_pool_sha256"]
            stage["source_stage_sha256"] = self_hash(stage, "source_stage_sha256")
            with self.assertRaisesRegex(
                SpendLockError, "body_sha256, story_signature",
            ):
                scan_leases(
                    plan=plan,
                    leases_root=root,
                    repository=REPOSITORY,
                    workflow_path=WORKFLOW,
                    current_run_id=202,
                    source_stage=stage,
                    candidate_pool=pool,
                    source_queue=queue,
                    source_review=review,
                )

    def test_missing_or_tampered_reserved_source_identity_blocks_fail_closed(self):
        plan = source_contract("acc1/2026-07-15/pilot_04")[0]
        for mutation, expected in (
            (lambda lease: lease.pop("reserved_sources"), "fields are incomplete"),
            (
                lambda lease: lease["reserved_sources"][0].__setitem__(
                    "source_id", "tampered-source",
                ),
                "self hash mismatch",
            ),
        ):
            with self.subTest(expected=expected), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                lease = copy.deepcopy(valid_lease())
                mutation(lease)
                lease["lease_sha256"] = self_hash(lease, "lease_sha256")
                store_artifact(root, lease, run_id=101)
                with self.assertRaisesRegex(SpendLockError, expected):
                    scan_leases(
                        plan=plan,
                        leases_root=root,
                        repository=REPOSITORY,
                        workflow_path=WORKFLOW,
                        current_run_id=202,
                    )

    def test_incomplete_current_source_evidence_blocks_reservation_scan(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with self.assertRaisesRegex(SpendLockError, "requires source-stage"):
                scan_leases(
                    plan=source_contract()[0],
                    leases_root=root,
                    repository=REPOSITORY,
                    workflow_path=WORKFLOW,
                    current_run_id=202,
                    candidate_pool=source_contract()[2],
                )

    def test_tampered_lease_blocks_even_for_a_different_episode(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            lease = valid_lease()
            lease["requested_caps"]["image_call_cap"] = 20
            store_artifact(root, lease, run_id=101)
            plan = source_contract("acc1/2026-07-15/pilot_04")[0]
            with self.assertRaisesRegex(SpendLockError, "self hash mismatch"):
                scan_leases(
                    plan=plan,
                    leases_root=root,
                    repository=REPOSITORY,
                    workflow_path=WORKFLOW,
                    current_run_id=202,
                )

    def test_unknown_schema_blocks_even_with_a_recomputed_hash(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            lease = copy.deepcopy(valid_lease())
            lease["schema_version"] = "future_unknown_schema"
            lease["lease_sha256"] = self_hash(lease, "lease_sha256")
            store_artifact(root, lease, run_id=101)
            plan = source_contract("acc1/2026-07-15/pilot_04")[0]
            with self.assertRaisesRegex(SpendLockError, "schema is unknown"):
                scan_leases(
                    plan=plan,
                    leases_root=root,
                    repository=REPOSITORY,
                    workflow_path=WORKFLOW,
                    current_run_id=202,
                )

    def test_unreadable_or_missing_lease_artifact_blocks(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            artifact = root / "101-501"
            artifact.mkdir()
            (artifact / LEASE_FILENAME).write_text("not-json", encoding="utf-8")
            with self.assertRaisesRegex(SpendLockError, "unreadable"):
                scan_leases(
                    plan=source_contract()[0],
                    leases_root=root,
                    repository=REPOSITORY,
                    workflow_path=WORKFLOW,
                    current_run_id=202,
                )

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "101-501").mkdir()
            with self.assertRaisesRegex(SpendLockError, "exactly one"):
                scan_leases(
                    plan=source_contract()[0],
                    leases_root=root,
                    repository=REPOSITORY,
                    workflow_path=WORKFLOW,
                    current_run_id=202,
                )

    def test_source_binding_tamper_blocks_lease_creation(self):
        plan, stage, pool, queue, review = source_contract()
        queue["entries"].append({"post_id": "unexpected"})
        with self.assertRaisesRegex(SpendLockError, "source_queue_sha256"):
            build_lease(
                plan=plan,
                source_stage=stage,
                candidate_pool=pool,
                source_queue=queue,
                source_review=review,
                repository=REPOSITORY,
                workflow_path=WORKFLOW,
                run_id=101,
                run_attempt=1,
                head_sha=HEAD_SHA,
                requested_caps={
                    "reddit_request_cap": 24,
                    "openai_call_cap": 64,
                    "openai_token_cap": 1_000_000,
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

    def test_candidate_reserve_pool_accepts_three_and_five_but_blocks_two_and_six(self):
        for candidate_count in (3, 5):
            with self.subTest(candidate_count=candidate_count):
                self.assertEqual(
                    valid_lease(candidate_count=candidate_count)["source_bindings"][
                        "candidate_pool_sha256"
                    ],
                    source_contract(candidate_count=candidate_count)[2][
                        "candidate_pool_sha256"
                    ],
                )
        for candidate_count in (2, 6):
            with self.subTest(candidate_count=candidate_count):
                plan, stage, pool, queue, review = source_contract(
                    candidate_count=candidate_count,
                )
                with self.assertRaisesRegex(SpendLockError, "3-5"):
                    build_lease(
                        plan=plan,
                        source_stage=stage,
                        candidate_pool=pool,
                        source_queue=queue,
                        source_review=review,
                        repository=REPOSITORY,
                        workflow_path=WORKFLOW,
                        run_id=101,
                        run_attempt=1,
                        head_sha=HEAD_SHA,
                        requested_caps={
                            "reddit_request_cap": 24,
                            "openai_call_cap": 64,
                            "openai_token_cap": 1_000_000,
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

    def test_production_validation_accepts_exact_three_and_five_candidate_leases(self):
        for candidate_count in (3, 5):
            with self.subTest(candidate_count=candidate_count):
                plan, stage, pool, queue, review = source_contract(
                    candidate_count=candidate_count,
                )
                validate_lease_for_production(
                    valid_lease(candidate_count=candidate_count),
                    plan=plan,
                    source_stage=stage,
                    candidate_pool=pool,
                    source_queue=queue,
                    source_review=review,
                    repository=REPOSITORY,
                    workflow_path=WORKFLOW,
                    requested_caps={
                        "reddit_request_cap": 24,
                        "openai_call_cap": 64,
                        "openai_token_cap": 1_000_000,
                        "image_call_cap": 16,
                        "ai33_call_cap": 96,
                    },
                    confirmations={
                        "reddit_read": True,
                        "openai_spend": True,
                        "image_spend": True,
                        "ai33_spend": True,
                    },
                    provider_contract=PROVIDER_CONTRACT,
                    run_id=101,
                    run_attempt=1,
                    head_sha=HEAD_SHA,
                )

    def test_production_validation_blocks_exact_source_cap_and_confirmation_drift(self):
        plan, stage, pool, queue, review = source_contract()
        lease = valid_lease()
        shared = {
            "plan": plan,
            "source_stage": stage,
            "candidate_pool": pool,
            "source_queue": queue,
            "source_review": review,
            "repository": REPOSITORY,
            "workflow_path": WORKFLOW,
            "requested_caps": {
                "reddit_request_cap": 24,
                "openai_call_cap": 64,
                "openai_token_cap": 1_000_000,
                "image_call_cap": 16,
                "ai33_call_cap": 96,
            },
            "confirmations": {
                "reddit_read": True,
                "openai_spend": True,
                "image_spend": True,
                "ai33_spend": True,
            },
            "provider_contract": PROVIDER_CONTRACT,
        }

        cap_drift = copy.deepcopy(shared)
        cap_drift["requested_caps"]["openai_call_cap"] = 63
        with self.assertRaisesRegex(SpendLockError, "exact production caps"):
            validate_lease_for_production(lease, **cap_drift)

        confirmation_drift = copy.deepcopy(shared)
        confirmation_drift["confirmations"]["ai33_spend"] = False
        with self.assertRaisesRegex(SpendLockError, "exact true"):
            validate_lease_for_production(lease, **confirmation_drift)

        source_drift = copy.deepcopy(shared)
        source_drift["source_queue"]["entries"].append({"post_id": "new-source"})
        source_drift["source_stage"]["source_queue_sha256"] = canonical_hash(
            source_drift["source_queue"]
        )
        source_drift["source_stage"]["source_stage_sha256"] = self_hash(
            source_drift["source_stage"], "source_stage_sha256",
        )
        with self.assertRaisesRegex(SpendLockError, "exact source artifacts"):
            validate_lease_for_production(lease, **source_drift)


if __name__ == "__main__":
    unittest.main()
