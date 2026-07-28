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
            3,
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

    def test_paid_resume_is_parent_bound_single_use_and_skips_new_source(self):
        workflow = self.workflow
        self.assertIn("resume_source_run_id:", workflow)
        self.assertIn("run-id: ${{ inputs.resume_source_run_id }}", workflow)
        self.assertIn("if: inputs.resume_source_run_id == ''", workflow)
        self.assertIn("Create one hash-bound paid resume lock", workflow)
        self.assertIn(
            "Confirm only an exact parent OpenAI Flex 429 rejection",
            workflow,
        )
        self.assertIn(
            "scripts/acc1_confirm_openai_flex_429.py",
            workflow,
        )
        self.assertIn(
            '--proof "$WORKDIR/openai-flex-429-rejection.json"',
            workflow,
        )
        self.assertIn(
            '--parent-resume-lease "$WORKDIR/resume-spend-lease.json"',
            workflow,
        )
        self.assertIn("acc1-resume-lease-${{ github.run_id }}", workflow)
        self.assertIn("scripts/acc1_resume_lock.py create", workflow)
        self.assertIn(
            '--openai-flex-rejection-proof "$WORKDIR/openai-flex-429-rejection.json"',
            workflow,
        )
        self.assertIn("parent-resume-spend-lease.json", workflow)
        self.assertIn('--ai33-journal "$WORKDIR/provider-attempts/ai33.json"', workflow)
        self.assertIn('--tts-state "$WORKDIR/tts/compilation_tts_state.json"', workflow)
        self.assertIn('--resume-reviewed-run-id "$RESUME_SOURCE_RUN_ID"', workflow)
        self.assertIn('--resume-lease "$WORKDIR/resume-spend-lease.json"', workflow)
        self.assertNotIn("uploader.py", workflow)

    def test_visual_mode_is_explicit_defaulted_and_forwarded_to_all_media_gates(self):
        workflow = self.workflow
        self.assertIn("      visual_mode:\n", workflow)
        self.assertIn("        default: editorial_motion_v1\n", workflow)
        self.assertIn("          - editorial_motion_v1\n", workflow)
        visual_input = workflow.split("      visual_mode:\n", 1)[1].split(
            "      confirm_reddit_read:\n",
            1,
        )[0]
        self.assertNotIn("reddit_pages", visual_input)
        self.assertNotIn("cinematic_story_v1", visual_input)
        self.assertIn("VISUAL_MODE: ${{ inputs.visual_mode }}", workflow)
        self.assertEqual(
            workflow.count('--visual-mode "$VISUAL_MODE"'),
            3,
        )
        source_section = workflow.split("--stage source", 1)[1].split(
            "Refuse cross-date reserved-source overlap", 1,
        )[0]
        self.assertNotIn("--visual-mode", source_section)

    def test_every_external_provider_has_exact_confirmation_and_cap(self):
        for provider in (
            "reddit_read",
            "openai_spend",
            "image_spend",
            "ai33_spend",
        ):
            declaration = re.search(
                rf"^      confirm_{provider}:\n(?P<body>(?:        .+\n)+)",
                self.workflow,
                flags=re.MULTILINE,
            )
            self.assertIsNotNone(declaration, provider)
            self.assertIn("type: boolean", declaration.group("body"))
            self.assertIn("default: false", declaration.group("body"))

        for cap in (
            "reddit_request_cap",
            "openai_call_cap",
            "openai_token_cap",
            "image_call_cap",
            "ai33_call_cap",
        ):
            self.assertIn(f"      {cap}:\n", self.workflow)
            self.assertIn(f'--{cap.replace("_", "-")} "$', self.workflow)
        self.assertRegex(
            self.workflow,
            r'ai33_call_cap:\n(?:        .+\n)+?        default: "96"',
        )
        self.assertIn(
            '      reddit_request_cap:\n'
            '        description: Hard cap for Reddit requests in this episode run\n'
            '        required: true\n'
            '        default: "24"\n'
            '        type: choice\n'
            '        options: ["8", "16", "24", "48"]\n',
            self.workflow,
        )
        self.assertIn(
            '      openai_call_cap:\n'
            '        description: Hard cap for all OpenAI calls in this episode run\n'
            '        required: true\n'
            '        default: "96"\n'
            '        type: choice\n'
            '        options: ["16", "24", "32", "48", "64", "96", "128", "160"]\n',
            self.workflow,
        )
        self.assertIn(
            '      openai_token_cap:\n'
            '        description: Hard cap for all OpenAI input and output tokens in this episode run\n'
            '        required: true\n'
            '        default: "500000"\n'
            '        type: choice\n'
            '        options: ["100000", "250000", "500000", "750000", "1000000"]\n',
            self.workflow,
        )
        self.assertIn(
            '      image_call_cap:\n'
            '        description: Hard cap for image-generation calls in this episode run\n'
            '        required: true\n'
            '        default: "16"\n'
            '        type: choice\n'
            '        options: ["8", "12", "16", "20", "41", "69"]\n',
            self.workflow,
        )

    def test_source_only_is_exact_green_no_spend_scope(self):
        workflow = self.workflow
        declaration = workflow.split("      source_only:\n", 1)[1].split(
            "      visual_mode:\n",
            1,
        )[0]
        self.assertIn("default: false", declaration)
        self.assertIn("type: boolean", declaration)
        scope = workflow.split(
            "- name: Validate exact source-only no-spend scope",
            1,
        )[1].split("- name:", 1)[0]
        self.assertIn("if: inputs.source_only", scope)
        self.assertIn('test -z "$RESUME_SOURCE_RUN_ID"', scope)
        self.assertIn('test "$CONFIRM_REDDIT_READ" = "true"', scope)
        for provider in ("OPENAI", "IMAGE", "AI33"):
            self.assertIn(
                f'test "$CONFIRM_{provider}_SPEND" = "false"',
                scope,
            )
        self.assertNotIn("${{ secrets.", scope)

        receipt = workflow.split(
            "- name: Seal successful source-only evidence",
            1,
        )[1].split("- name:", 1)[0]
        self.assertIn("if: inputs.source_only", receipt)
        self.assertIn("--stage source-receipt", receipt)
        self.assertIn('--run-id "$GITHUB_RUN_ID"', receipt)
        self.assertIn('--run-attempt "$GITHUB_RUN_ATTEMPT"', receipt)
        self.assertIn('--head-sha "$GITHUB_SHA"', receipt)
        self.assertIn("source-only-result.json", receipt)
        self.assertIn("OpenAI 0 / VectorEngine 0 / AI33 0", receipt)
        self.assertNotIn("${{ secrets.", receipt)

        paid_steps = {
            "Require all paid-provider confirmations after source success":
                "if: ${{ !inputs.source_only }}",
            "Run source-dependent paid preflight before lease":
                "if: ${{ !inputs.source_only }}",
            "Create exact source-bound paid spend lease":
                "if: ${{ !inputs.source_only && inputs.resume_source_run_id == '' }}",
            "Persist paid spend lease before the first paid request":
                "if: ${{ !inputs.source_only && inputs.resume_source_run_id == '' }}",
            "Create one hash-bound paid resume lock":
                "if: ${{ !inputs.source_only && inputs.resume_source_run_id != '' }}",
            "Persist paid resume lock before the first continuation request":
                "if: ${{ !inputs.source_only && inputs.resume_source_run_id != '' }}",
            "Produce review-ready episode artifact":
                "if: ${{ !inputs.source_only }}",
            "Enforce hash-bound human-review ceiling":
                "if: ${{ !inputs.source_only }}",
        }
        for step_name, exact_gate in paid_steps.items():
            with self.subTest(step=step_name):
                section = workflow.split(f"- name: {step_name}", 1)[1].split(
                    "- name:",
                    1,
                )[0]
                self.assertIn(exact_gate, section)

    def test_openai_secret_is_scoped_to_paid_preflight_and_produce(self):
        workflow = self.workflow
        secret_binding = "OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}"
        self.assertEqual(workflow.count(secret_binding), 2)

        plan_job, build_job = workflow.split("\n  build:\n", 1)
        self.assertNotIn("OPENAI_API_KEY", plan_job)
        source_section = build_job.split(
            "- name: Build source evidence before any paid stage", 1,
        )[1].split(
            "- name: Refuse cross-date reserved-source overlap before paid stages", 1,
        )[0]
        lease_section = build_job.split(
            "- name: Create exact source-bound paid spend lease", 1,
        )[1].split(
            "- name: Persist paid spend lease before the first paid request", 1,
        )[0]
        self.assertNotIn("OPENAI_API_KEY", source_section)
        self.assertNotIn("OPENAI_API_KEY", lease_section)

        for step_name in (
            "Run source-dependent paid preflight before lease",
            "Produce review-ready episode artifact",
        ):
            section = build_job.split(f"- name: {step_name}", 1)[1]
            self.assertIn(secret_binding, section.split("- name:", 1)[0])

        self.assertIn(
            '"openai_attempts": root / "provider-attempts" / "openai.json"',
            workflow,
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
        source_receipt_index = workflow.index(
            "Seal successful source-only evidence"
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
        self.assertLess(source_reservation_scan_index, source_receipt_index)
        self.assertLess(source_receipt_index, paid_confirmation_index)
        self.assertLess(paid_confirmation_index, paid_preflight_index)
        self.assertLess(paid_preflight_index, lease_create_index)
        self.assertLess(lease_create_index, lease_upload_index)
        self.assertLess(lease_upload_index, produce_index)
        self.assertIn("--stage paid-preflight", workflow)
        self.assertIn('--spend-lease "$WORKDIR/spend-lease.json"', workflow)
        self.assertIn('AI_QUALITY_CHECK: "0"', workflow)
        self.assertIn('AI_QUALITY_FAIL_OPEN: "0"', workflow)
        self.assertIn('--confirm-reddit-read "$CONFIRM_REDDIT_READ"', workflow)
        self.assertEqual(workflow.count('--plan "$DAILY_PLAN_PATH"'), 8)
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
            '"audio_sha256": root / "tts" / "compilation_voice_mix.wav"',
            '"text_layout_report": root / "text-layout-report.json"',
            '"spend_lease": root / "spend-lease.json"',
            '"paid_preflight": root / "paid-preflight.json"',
            '"runtime_estimate_report": root / "runtime-estimate-report.json"',
            '"pause_map": root / "tts" / "narration-pause-map.json"',
            '"audio_mix_report": root / "tts" / "audio-mix-report.json"',
            'if visual_mode == "cinematic_story_v1":',
            '"shot_plan": root / "shot-plan.json"',
            '"caption_track": root / "caption-track.json"',
            '"caption_srt": root / "final-output.srt"',
            'elif visual_mode == "editorial_motion_v1":',
            '"motion_plan": root / "motion-plan.json"',
            '"caption_srt": root / "editorial-motion-captions.srt"',
            'render_report.get("renderer") != "hyperframes_segmented"',
            'not 0 < float(segment_ceiling) <= 120',
            '"motion_plan_sha256": {"editorial_motion_v1"}',
            '"narration_profile_sha256"',
            '"audio_mix_report_sha256"',
            '"caption_srt_sha256"',
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
