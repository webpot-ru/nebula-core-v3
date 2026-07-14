import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_PATH = ROOT / ".github/workflows/acc1_daily_episode.yml"


class Acc1DailyWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workflow = WORKFLOW_PATH.read_text(encoding="utf-8")

    def test_is_manual_artifact_only_and_does_not_claim_view_guarantees(self):
        workflow = self.workflow
        self.assertIn("workflow_dispatch:", workflow)
        self.assertNotIn("schedule:", workflow)
        self.assertNotIn("cron:", workflow)
        self.assertNotIn("resume_run_id", workflow)
        self.assertNotIn("--resume-run-id", workflow)
        self.assertIn("cannot guarantee millions of views", workflow)
        self.assertIn("ACC1_RELEASE_CEILING: READY_FOR_HUMAN_REVIEW", workflow)
        self.assertNotIn("topic_mix", workflow)
        for forbidden in (
            "uploader.py",
            "YOUTUBE_",
            "youtube.upload",
            "published_history.json",
            "git push",
        ):
            self.assertNotIn(forbidden, workflow)

    def test_plan_job_has_no_provider_secrets_or_factory_calls(self):
        plan_job, build_job = self.workflow.split("\n  build:\n", 1)
        self.assertIn("\n  plan:\n", plan_job)
        self.assertNotIn("${{ secrets.", plan_job)
        self.assertNotIn("run_acc1_episode_factory.py", plan_job)
        self.assertIn("python acc1_daily_planner.py", plan_job)
        self.assertIn("--channels channels.json", plan_job)
        self.assertIn("DAILY_PLAN_PATH: build/acc1-daily/daily-plan.json", plan_job)
        self.assertNotIn("build/acc1-daily/episode-plan.json", plan_job)
        self.assertIn("acc1-daily-plan-${{ github.run_id }}", plan_job)
        self.assertIn("run_acc1_episode_factory.py", build_job)

    def test_job_level_env_never_uses_step_only_runner_context(self):
        build_job = self.workflow.split("\n  build:\n", 1)[1]
        job_env = build_job.split("\n    steps:\n", 1)[0]
        self.assertNotIn("${{ runner.", job_env)
        self.assertIn("WORKDIR: build/acc1-daily-episode", job_env)
        self.assertIn(
            "DAILY_PLAN_PATH: build/acc1-daily-episode/daily-plan.json",
            job_env,
        )
        self.assertEqual(
            self.workflow.splitlines().count(
                "          path: build/acc1-daily-episode"
            ),
            2,
        )
        self.assertIn(
            "path: build/acc1-daily-episode/spend-lease.json",
            self.workflow,
        )

    def test_one_daily_pilot_and_cross_date_reservation_concurrency_are_explicit(self):
        workflow = self.workflow
        self.assertIn("pilot_id:", workflow)
        self.assertIn("- auto", workflow)
        for pilot_number in range(1, 7):
            self.assertIn(f"- pilot_{pilot_number:02d}", workflow)
        self.assertNotIn("video_slot:", workflow)
        self.assertIn("group: acc1-paid-source-reservation", workflow)
        self.assertNotIn("group: acc1-${{ needs.plan.outputs.episode_key }}", workflow)
        self.assertIn("cross-date TOCTOU window", workflow)
        self.assertIn("cancel-in-progress: false", workflow)
        self.assertIn("timeout-minutes: 360", workflow)

    def test_every_external_provider_has_exact_confirmation_and_cap(self):
        for provider in ("reddit_read", "gemini_spend", "image_spend", "ai33_spend"):
            declaration = re.search(
                rf"^      confirm_{provider}:\n(?P<body>(?:        .+\n)+)",
                self.workflow,
                flags=re.MULTILINE,
            )
            self.assertIsNotNone(declaration, provider)
            self.assertIn("type: boolean", declaration.group("body"))
            self.assertIn("default: false", declaration.group("body"))

        for cap in ("reddit_request_cap", "gemini_call_cap", "image_call_cap", "ai33_call_cap"):
            self.assertIn(f"      {cap}:\n", self.workflow)
            self.assertIn(f'--{cap.replace("_", "-")} "$', self.workflow)
        self.assertRegex(
            self.workflow,
            r'ai33_call_cap:\n(?:        .+\n)+?        default: "96"',
        )

    def test_source_precedes_every_paid_stage_and_quality_ai_is_off(self):
        workflow = self.workflow
        replay_gate_index = workflow.index("Refuse replay of a spend-enabled dispatch")
        preflight_index = workflow.index("--stage preflight")
        cross_dispatch_scan_index = workflow.index(
            "Refuse an existing cross-dispatch paid spend lease"
        )
        source_index = workflow.index("--stage source")
        source_reservation_scan_index = workflow.index(
            "Refuse cross-date reserved-source overlap before paid stages"
        )
        paid_confirmation_index = workflow.index(
            "Require all paid-provider confirmations after source success"
        )
        paid_preflight_index = workflow.index(
            "Run source-dependent paid preflight before lease"
        )
        lease_create_index = workflow.index("Create exact source-bound paid spend lease")
        lease_upload_index = workflow.index(
            "Persist paid spend lease before the first paid request"
        )
        produce_index = workflow.index("--stage produce")
        self.assertLess(replay_gate_index, preflight_index)
        self.assertLess(preflight_index, cross_dispatch_scan_index)
        self.assertLess(cross_dispatch_scan_index, source_index)
        self.assertLess(source_index, source_reservation_scan_index)
        self.assertLess(source_reservation_scan_index, paid_confirmation_index)
        self.assertLess(paid_confirmation_index, paid_preflight_index)
        self.assertLess(paid_preflight_index, lease_create_index)
        self.assertLess(lease_create_index, lease_upload_index)
        self.assertLess(lease_upload_index, produce_index)
        self.assertIn("--stage paid-preflight", workflow)
        self.assertIn('--spend-lease "$WORKDIR/spend-lease.json"', workflow)
        self.assertIn('AI_QUALITY_CHECK: "0"', workflow)
        self.assertIn('AI_QUALITY_FAIL_OPEN: "0"', workflow)
        self.assertIn('--confirm-reddit-read "$CONFIRM_REDDIT_READ"', workflow)
        self.assertEqual(workflow.count('--plan "$DAILY_PLAN_PATH"'), 7)
        self.assertIn('test "$RUN_ATTEMPT" = "1"', workflow)
        self.assertNotIn("create a fresh workflow dispatch instead", workflow)
        self.assertIn("remains spend-locked for manual adjudication", workflow)

    def test_cross_dispatch_spend_lock_is_immutable_and_retained_for_90_days(self):
        workflow = self.workflow
        self.assertEqual(workflow.count("scripts/acc1_spend_lock.py scan"), 2)
        self.assertIn("scripts/acc1_spend_lock.py create", workflow)
        self.assertIn("acc1-paid-lease-${{ github.run_id }}", workflow)
        self.assertIn('test "$artifact_name" = "acc1-paid-lease-$owner_run_id"', workflow)
        self.assertIn('--workflow-path ".github/workflows/acc1_daily_episode.yml"', workflow)
        self.assertIn('--source-stage "$WORKDIR/source-stage.json"', workflow)
        self.assertIn('--candidate-pool "$WORKDIR/candidate-pool.json"', workflow)
        source_reservation_section = workflow.split(
            "- name: Refuse cross-date reserved-source overlap before paid stages", 1,
        )[1].split("- name: Require all paid-provider confirmations", 1)[0]
        for source_artifact in (
            "source-stage.json",
            "candidate-pool.json",
            "source-queue.json",
            "source-review.json",
        ):
            self.assertIn(source_artifact, source_reservation_section)
        self.assertIn('LEASE_SCAN_ROOT: ${{ runner.temp }}/acc1-paid-lease-scan', source_reservation_section)
        lease_section = workflow.split(
            "- name: Persist paid spend lease before the first paid request", 1,
        )[1].split("- name: Produce review-ready episode artifact", 1)[0]
        self.assertIn("uses: actions/upload-artifact@v4", lease_section)
        self.assertIn("if-no-files-found: error", lease_section)
        self.assertIn("retention-days: 90", lease_section)
        self.assertNotIn("continue-on-error", lease_section)

    def test_success_is_hash_bound_and_artifacts_upload_on_failure(self):
        workflow = self.workflow
        for required in (
            'result.get("status") != "READY_FOR_HUMAN_REVIEW"',
            'result.get("publication_authorized") is not False',
            '"episode_plan_sha256"',
            '"release_candidate_manifest_sha256"',
            'plan_path = result_path.parent / "episode-plan.json"',
            'manifest_path = result_path.parent / "release-candidate-manifest.json"',
            'separators=(",", ":")',
            "plan_hash_payload.pop",
            "manifest_hash_payload.pop",
            "canonical_json_sha256(plan_hash_payload)",
            '"release_candidate_manifest_sha256": canonical_json_sha256(',
            "if claimed != actual:",
            "if embedded_plan_hash != bindings",
            "if embedded_manifest_hash != bindings",
            '"video_sha256": root / "final-output.mp4"',
            '"audio_sha256": root / "tts" / "compilation_narration.mp3"',
            '"text_layout_report": root / "text-layout-report.json"',
            '"spend_lease": root / "spend-lease.json"',
            '"paid_preflight": root / "paid-preflight.json"',
            '"runtime_estimate_report": root / "runtime-estimate-report.json"',
            'manifest.get("artifact_sha256")',
            'manifest.get("evidence_sha256")',
            "actual = file_sha256(path)",
            'raise SystemExit(f"release manifest {label} hash mismatch: {field}")',
            'source_stage_payload.pop("source_stage_sha256"',
            'playoff_payload.pop("playoff_sha256"',
            'canonical_json_sha256(playoff_input)',
            "if: always()",
            "if-no-files-found: error",
        ):
            self.assertIn(required, workflow)

    def test_paid_produce_has_deadlines_and_artifact_upload_headroom(self):
        workflow = self.workflow
        produce_section = workflow.split(
            "- name: Produce review-ready episode artifact", 1,
        )[1].split("- name: Enforce hash-bound human-review ceiling", 1)[0]
        self.assertIn("AI33_TTS_DEADLINE_EPOCH", produce_section)
        self.assertIn("+ 14400", produce_section)
        self.assertIn(
            "timeout --signal=TERM --kill-after=60s 18000s",
            produce_section,
        )
        self.assertIn(
            'python scripts/run_acc1_episode_factory.py "${FACTORY_ARGS[@]}"',
            produce_section,
        )
        self.assertIn("timeout-minutes: 360", workflow)


if __name__ == "__main__":
    unittest.main()
