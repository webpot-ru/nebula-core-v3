import copy
import hashlib
import unittest

import acc1_episode_manifest


def exact_artifacts():
    body = "A complete Reddit source body with a preserved ending."
    body_sha256 = hashlib.sha256(body.encode("utf-8")).hexdigest()
    queue = {
        "channel_id": "acc1",
        "source_plan": {
            "pilot_id": "pilot_03",
            "format": "SAGA",
            "pillar": "strange_dark_unexplained",
        },
        "entries": [{
            "post_id": "post-1",
            "source_body": body,
            "source_body_sha256": body_sha256,
        }],
    }
    review = {
        "status": "review_ready",
        "source_sha256": "a" * 64,
        "review_sha256": "b" * 64,
        "top_topics": [{"post_id": "post-1"}],
    }
    greenlight = {
        "channel_id": "acc1",
        "pilot_id": "pilot_03",
        "format": "SAGA",
        "pillar": "strange_dark_unexplained",
        "publication_authorized": False,
        "source": {
            "post_id": "post-1",
            "source_body_sha256": body_sha256,
            "truth_mode": "fiction",
        },
    }
    config = {"channel_id": "acc1", "voice_role": "male_primary"}
    daily_plan = {
        "episode_key": "acc1/2026-07-14/pilot_03",
        "production_date": "2026-07-14",
        "pilot_id": "pilot_03",
        "format": "SAGA",
        "pillar": "strange_dark_unexplained",
        "publication_authorized": False,
    }
    providers = {
        "tts": {"provider": "ai33", "model_id": "eleven_v3", "voice_id": "voice-1"},
        "translation": {"provider": "vectorengine", "model": "gemini-3.5-flash"},
    }
    return queue, review, greenlight, config, daily_plan, providers


def valid_manifest():
    queue, review, greenlight, config, daily_plan, providers = exact_artifacts()
    manifest = acc1_episode_manifest.build_episode_manifest(
        episode_key="acc1/2026-07-14/pilot_03",
        episode_date="2026-07-14",
        pilot_id="pilot_03",
        format_id="SAGA",
        pillar="strange_dark_unexplained",
        source_queue=queue,
        topic_review=review,
        greenlight=greenlight,
        config=config,
        daily_plan=daily_plan,
        git_sha="1234567890abcdef1234567890abcdef12345678",
        provider_settings=providers,
    )
    return manifest, queue, review, greenlight, config, daily_plan


class Acc1EpisodeManifestTests(unittest.TestCase):
    def test_builds_self_verifying_immutable_plan(self):
        manifest, queue, review, greenlight, config, daily_plan = valid_manifest()
        report = acc1_episode_manifest.validate_episode_manifest(
            manifest,
            source_queue=queue,
            topic_review=review,
            greenlight=greenlight,
            config=config,
            daily_plan=daily_plan,
        )
        self.assertEqual(report["status"], "PASS", report["failures"])
        self.assertFalse(report["publication_authorized"])
        self.assertEqual(
            manifest["sources"][0]["required_disclosure"],
            "Это художественная история с Reddit.",
        )
        self.assertTrue(
            manifest["truth_disclosure_contract"]["metadata_visible_once_per_episode"]
        )
        self.assertEqual(manifest["episode_key"], "acc1/2026-07-14/pilot_03")
        self.assertEqual(
            manifest["daily_plan_sha256"], acc1_episode_manifest.canonical_hash(daily_plan)
        )

    def test_builder_emits_v2_cinematic_contracts_without_downstream_hashes(self):
        queue, review, greenlight, config, daily_plan, providers = exact_artifacts()
        manifest = acc1_episode_manifest.build_episode_manifest(
            episode_key="acc1/2026-07-14/pilot_03",
            episode_date="2026-07-14",
            pilot_id="pilot_03",
            format_id="SAGA",
            pillar="strange_dark_unexplained",
            source_queue=queue,
            topic_review=review,
            greenlight=greenlight,
            config=config,
            daily_plan=daily_plan,
            git_sha="1234567890abcdef1234567890abcdef12345678",
            provider_settings=providers,
            visual_mode="cinematic_story_v1",
        )
        self.assertEqual(manifest["version"], 2)
        self.assertEqual(manifest["visual_mode"], "cinematic_story_v1")
        self.assertEqual(
            manifest["narration_profile_id"],
            "acc1_strange_dark_unexplained_v1",
        )
        self.assertRegex(manifest["narration_profile_sha256"], r"^[0-9a-f]{64}$")
        self.assertTrue(manifest["shot_plan_contract"]["required"])
        self.assertTrue(manifest["caption_track_contract"]["required"])
        self.assertTrue(manifest["audio_mix_contract"]["required"])
        serialized = repr(manifest)
        self.assertNotIn("shot_plan_sha256", serialized)
        self.assertNotIn("caption_track_sha256", serialized)
        self.assertNotIn("audio_mix_sha256", serialized)
        report = acc1_episode_manifest.validate_episode_manifest(manifest)
        self.assertEqual(report["status"], "PASS", report["failures"])

    def test_historical_v1_remains_self_verifying_without_mutation(self):
        manifest, *_ = valid_manifest()
        legacy = copy.deepcopy(manifest)
        for field in (
            "visual_mode",
            "narration_profile_id",
            "narration_profile_sha256",
            "shot_plan_contract",
            "caption_track_contract",
            "audio_mix_contract",
        ):
            legacy.pop(field)
        legacy["version"] = 1
        legacy["episode_plan_sha256"] = acc1_episode_manifest.canonical_hash({
            key: value for key, value in legacy.items()
            if key != "episode_plan_sha256"
        })
        expected_hash = legacy["episode_plan_sha256"]
        snapshot = copy.deepcopy(legacy)
        report = acc1_episode_manifest.validate_episode_manifest(legacy)
        self.assertEqual(report["status"], "PASS", report["failures"])
        self.assertEqual(report["episode_plan_sha256"], expected_hash)
        self.assertEqual(legacy, snapshot)

    def test_v2_contract_tampering_blocks_without_rewriting_manifest(self):
        manifest, *_ = valid_manifest()
        manifest["audio_mix_contract"]["required"] = False
        manifest["episode_plan_sha256"] = acc1_episode_manifest.canonical_hash({
            key: value for key, value in manifest.items()
            if key != "episode_plan_sha256"
        })
        report = acc1_episode_manifest.validate_episode_manifest(manifest)
        self.assertEqual(report["status"], "BLOCKED")
        self.assertTrue(any("audio_mix_contract" in item for item in report["failures"]))

    def test_v2_requires_explicit_mode_and_profile_even_with_valid_self_hash(self):
        for missing_field in ("visual_mode", "narration_profile_id"):
            with self.subTest(missing_field=missing_field):
                manifest, *_ = valid_manifest()
                manifest.pop(missing_field)
                manifest["episode_plan_sha256"] = (
                    acc1_episode_manifest.canonical_hash({
                        key: value for key, value in manifest.items()
                        if key != "episode_plan_sha256"
                    })
                )
                report = acc1_episode_manifest.validate_episode_manifest(manifest)
                self.assertEqual(report["status"], "BLOCKED")
                self.assertTrue(
                    any(missing_field in item for item in report["failures"]),
                    report["failures"],
                )

    def test_builder_fails_closed_for_unknown_or_cross_pillar_contract_values(self):
        queue, review, greenlight, config, daily_plan, providers = exact_artifacts()
        common = {
            "episode_key": "acc1/2026-07-14/pilot_03",
            "episode_date": "2026-07-14",
            "pilot_id": "pilot_03",
            "format_id": "SAGA",
            "pillar": "strange_dark_unexplained",
            "source_queue": queue,
            "topic_review": review,
            "greenlight": greenlight,
            "config": config,
            "daily_plan": daily_plan,
            "git_sha": "1234567890abcdef1234567890abcdef12345678",
            "provider_settings": providers,
        }
        with self.assertRaises(acc1_episode_manifest.EpisodeManifestError):
            acc1_episode_manifest.build_episode_manifest(
                **common, visual_mode="unknown_visual_mode"
            )
        with self.assertRaises(acc1_episode_manifest.EpisodeManifestError):
            acc1_episode_manifest.build_episode_manifest(
                **common,
                narration_profile_id="acc1_relationships_family_v1",
            )
        broken_pillar = dict(common, pillar="unknown_pillar")
        with self.assertRaises(acc1_episode_manifest.EpisodeManifestError):
            acc1_episode_manifest.build_episode_manifest(**broken_pillar)

    def test_manifest_content_tamper_breaks_self_hash(self):
        manifest, *_ = valid_manifest()
        manifest["pillar"] = "relationships_family"
        report = acc1_episode_manifest.validate_episode_manifest(manifest)
        self.assertEqual(report["status"], "BLOCKED")
        self.assertTrue(any("episode_plan_sha256" in item for item in report["failures"]))

    def test_exact_upstream_artifact_tamper_blocks(self):
        manifest, queue, review, greenlight, config, daily_plan = valid_manifest()
        tampered_queue = copy.deepcopy(queue)
        tampered_queue["entries"][0]["source_body"] += " tampered"
        report = acc1_episode_manifest.validate_episode_manifest(
            manifest,
            source_queue=tampered_queue,
            topic_review=review,
            greenlight=greenlight,
            config=config,
            daily_plan=daily_plan,
        )
        self.assertEqual(report["status"], "BLOCKED")
        self.assertTrue(any("queue_sha256" in item for item in report["failures"]))
        self.assertTrue(any("source body checksum" in item for item in report["failures"]))

    def test_greenlight_source_identity_cannot_change(self):
        manifest, queue, review, greenlight, config, daily_plan = valid_manifest()
        changed = copy.deepcopy(greenlight)
        changed["source"]["post_id"] = "different-post"
        report = acc1_episode_manifest.validate_episode_manifest(
            manifest,
            source_queue=queue,
            topic_review=review,
            greenlight=changed,
            config=config,
            daily_plan=daily_plan,
        )
        self.assertEqual(report["status"], "BLOCKED")
        self.assertTrue(any("greenlight" in item for item in report["failures"]))

    def test_exact_daily_plan_tamper_blocks(self):
        manifest, queue, review, greenlight, config, daily_plan = valid_manifest()
        changed = copy.deepcopy(daily_plan)
        changed["pilot_id"] = "pilot_04"
        report = acc1_episode_manifest.validate_episode_manifest(
            manifest,
            source_queue=queue,
            topic_review=review,
            greenlight=greenlight,
            config=config,
            daily_plan=changed,
        )
        self.assertEqual(report["status"], "BLOCKED")
        self.assertTrue(any("daily_plan_sha256" in item for item in report["failures"]))

    def test_mixed_source_truth_modes_block(self):
        manifest, *_ = valid_manifest()
        second = copy.deepcopy(manifest["sources"][0])
        second.update({
            "post_id": "post-2",
            "truth_mode": "unverified_personal_account",
            "required_disclosure": (
                "Это личный рассказ пользователя Reddit, не подтверждённый независимо."
            ),
        })
        manifest["sources"].append(second)
        manifest["episode_plan_sha256"] = acc1_episode_manifest.canonical_hash(
            {key: value for key, value in manifest.items() if key != "episode_plan_sha256"}
        )
        report = acc1_episode_manifest.validate_episode_manifest(manifest)
        self.assertTrue(any("one truth_mode" in item for item in report["failures"]))

    def test_provider_settings_allow_benign_token_budget_fields(self):
        queue, review, greenlight, config, daily_plan, providers = exact_artifacts()
        providers["translation"].update({
            "max_output_tokens": 16_384,
            "max_input_tokens": 32_768,
        })
        manifest = acc1_episode_manifest.build_episode_manifest(
            episode_key="acc1/2026-07-14/pilot_03",
            episode_date="2026-07-14",
            pilot_id="pilot_03",
            format_id="SAGA",
            pillar="strange_dark_unexplained",
            source_queue=queue,
            topic_review=review,
            greenlight=greenlight,
            config=config,
            daily_plan=daily_plan,
            git_sha="1234567890abcdef1234567890abcdef12345678",
            provider_settings=providers,
        )
        report = acc1_episode_manifest.validate_episode_manifest(manifest)
        self.assertEqual(report["status"], "PASS", report["failures"])

    def test_provider_settings_refuse_secret_fields_and_close_variants(self):
        secret_keys = (
            "api_key",
            "apikey",
            "accessToken",
            "refresh-token",
            "bearer_token",
            "idToken",
            "auth-token",
            "Cookie",
            "password",
            "client_secret",
            "clientSecrets",
            "privateKey",
            "privateKeys",
            "credentials",
            "access_tokens",
            "apiKeys",
        )
        for secret_key in secret_keys:
            with self.subTest(secret_key=secret_key):
                queue, review, greenlight, config, daily_plan, providers = exact_artifacts()
                providers["tts"][secret_key] = "must-not-enter-a-manifest"
                with self.assertRaisesRegex(
                    acc1_episode_manifest.EpisodeManifestError, "secrets"
                ):
                    acc1_episode_manifest.build_episode_manifest(
                        episode_key="acc1/2026-07-14/pilot_03",
                        episode_date="2026-07-14",
                        pilot_id="pilot_03",
                        format_id="SAGA",
                        pillar="strange_dark_unexplained",
                        source_queue=queue,
                        topic_review=review,
                        greenlight=greenlight,
                        config=config,
                        daily_plan=daily_plan,
                        git_sha="1234567890abcdef1234567890abcdef12345678",
                        provider_settings=providers,
                    )

    def test_validation_does_not_mutate_inputs(self):
        manifest, queue, review, greenlight, config, daily_plan = valid_manifest()
        inputs = (manifest, queue, review, greenlight, config, daily_plan)
        snapshots = copy.deepcopy(inputs)
        report = acc1_episode_manifest.validate_episode_manifest(
            manifest,
            source_queue=queue,
            topic_review=review,
            greenlight=greenlight,
            config=config,
            daily_plan=daily_plan,
        )
        self.assertEqual(report["status"], "PASS", report["failures"])
        self.assertEqual(inputs, snapshots)

    def test_bind_episode_plan_does_not_mutate_payload(self):
        manifest, *_ = valid_manifest()
        payload = {"status": "PASS"}
        bound = acc1_episode_manifest.bind_episode_plan(payload, manifest)
        self.assertNotIn("episode_plan_sha256", payload)
        self.assertNotIn("daily_plan_sha256", payload)
        self.assertEqual(bound["episode_plan_sha256"], manifest["episode_plan_sha256"])
        self.assertEqual(bound["daily_plan_sha256"], manifest["daily_plan_sha256"])


if __name__ == "__main__":
    unittest.main()
