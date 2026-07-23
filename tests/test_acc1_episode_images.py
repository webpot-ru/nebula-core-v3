import tempfile
import unittest
import hashlib
import json
import copy
from pathlib import Path

from PIL import Image

from acc1_episode_images import (
    EpisodeImageError,
    _canonical_hash,
    generate_episode_images,
    image_plan,
)
from acc1_visual_contract import (
    ADULT_ANIMATION_WORK_STYLE_PROFILE,
    CINEMATIC_INK_WEBTOON_STYLE_PROFILE,
    CINEMATIC_STORY_MODE,
    EDITORIAL_MOTION_MODE,
    FORMAT_VISUAL_SYSTEM_V3_STYLE_PROFILE,
    INK_GOUACHE_STORY_PAGES_STYLE_PROFILE,
    select_format_visual_system_v3_panel_grammar,
)


def story(source_id: str, words: int = 80):
    body = ". ".join(f"Сцена {source_id} номер {index}" for index in range(words)) + "."
    return {
        "narration_ru": body,
        "source_snapshot": {"post_id": source_id},
    }


class EpisodeImageTests(unittest.TestCase):
    def test_format_allocations_are_bounded_and_deliberate(self):
        saga = {"episode_format": "SAGA", "stories": [story("one")]}
        bundle = {"episode_format": "BUNDLE", "stories": [story("a"), story("b")]}
        thread = {"episode_format": "THREAD", "stories": [story("p"), story("r1"), story("r2")]}
        self.assertEqual(len(image_plan(saga)), 5)
        self.assertEqual(len(image_plan(bundle)), 6)
        self.assertEqual(len(image_plan(thread)), 3)
        self.assertEqual({item["story_index"] for item in image_plan(thread)}, {0})

    def test_cinematic_mode_requests_full_screen_crop_safe_images(self):
        script = {
            "episode_format": "SAGA",
            "visual_mode": CINEMATIC_STORY_MODE,
            "stories": [story("one")],
        }
        prompt = image_plan(script)[0]["prompt"]
        self.assertIn("full-screen 16:9 composition", prompt)
        self.assertIn("subtle camera push and pan", prompt)
        self.assertNotIn("rightmost forty percent", prompt)
        self.assertNotIn("left and center-left", prompt)

    def test_default_image_prompt_remains_mascot_safe_baseline(self):
        prompt = image_plan({
            "episode_format": "SAGA",
            "stories": [story("one")],
        })[0]["prompt"]
        self.assertIn("rightmost forty percent", prompt)
        self.assertIn("left and center-left", prompt)

    def test_editorial_mode_plans_paired_source_bound_asset_packs(self):
        script = {
            "episode_format": "SAGA",
            "visual_mode": EDITORIAL_MOTION_MODE,
            "stories": [story("one")],
        }
        plan = image_plan(script)
        self.assertGreaterEqual(len(plan), 4)
        self.assertEqual(len(plan) % 2, 0)
        self.assertLessEqual(len(plan), 58)
        first_family = plan[0]["asset_family_id"]
        family = [item for item in plan if item["asset_family_id"] == first_family]
        self.assertEqual([item["layer_role"] for item in family], ["hero_plate", "detail_plate"])
        self.assertTrue(all(item["motion_module"] for item in family))
        self.assertIn("no text", plan[0]["prompt"])

    def test_editorial_mode_accepts_exact_storyboard_modules(self):
        source_story = story("one", words=25)
        source_story["visual_identity_contract"] = (
            "Same recurring adult woman with dark hair in a loose bun and olive blouse; "
            "same recurring adult man with salt-and-pepper hair, short beard and green sweater."
        )
        source_story["editorial_motion_modules"] = [
            "nested_collage_zoom", "dark_semantic_reveal",
        ]
        plan = image_plan({
            "episode_format": "SAGA",
            "visual_mode": EDITORIAL_MOTION_MODE,
            "stories": [source_story],
        })
        self.assertEqual(
            [item["motion_module"] for item in plan if item["layer_role"] == "hero_plate"],
            ["nested_collage_zoom", "dark_semantic_reveal"],
        )

    def test_ink_gouache_profile_binds_family_palette_and_unique_layout(self):
        source_story = story("one", words=25)
        source_story["visual_identity_contract"] = (
            "Same recurring adult woman with dark hair in a loose bun and olive blouse; "
            "same recurring adult man with salt-and-pepper hair, short beard and green sweater."
        )
        source_story["editorial_motion_families"] = ["work", "digital"]
        source_story["editorial_page_layouts"] = [
            "vertical_routine_triptych", "phone_portal_insets",
        ]
        plan = image_plan({
            "episode_format": "SAGA",
            "visual_mode": EDITORIAL_MOTION_MODE,
            "style_profile": INK_GOUACHE_STORY_PAGES_STYLE_PROFILE,
            "stories": [source_story],
        })
        heroes = [item for item in plan if item["layer_role"] == "hero_plate"]
        self.assertEqual(
            [(item["story_family"], item["page_layout"]) for item in heroes],
            [("work", "vertical_routine_triptych"), ("digital", "phone_portal_insets")],
        )
        self.assertIn("office green, paper cream and charcoal black", heroes[0]["prompt"])
        self.assertIn("electric cobalt-blue", heroes[1]["prompt"])
        self.assertNotIn("warm coral, butter yellow", heroes[0]["prompt"])

    def test_ink_gouache_profile_rejects_missing_family_contract(self):
        source_story = story("one", words=25)
        source_story["visual_identity_contract"] = (
            "Same recurring adult woman with dark hair in a loose bun and olive blouse; "
            "same recurring adult man with salt-and-pepper hair, short beard and green sweater."
        )
        with self.assertRaisesRegex(EpisodeImageError, "editorial_motion_families"):
            image_plan({
                "episode_format": "SAGA",
                "visual_mode": EDITORIAL_MOTION_MODE,
                "style_profile": INK_GOUACHE_STORY_PAGES_STYLE_PROFILE,
                "stories": [source_story],
            })

    def test_ink_gouache_profile_rejects_missing_identity_contract(self):
        source_story = story("one", words=25)
        source_story["editorial_motion_families"] = ["work", "digital"]
        source_story["editorial_page_layouts"] = [
            "vertical_routine_triptych", "phone_portal_insets",
        ]
        with self.assertRaisesRegex(EpisodeImageError, "visual_identity_contract"):
            image_plan({
                "episode_format": "SAGA",
                "visual_mode": EDITORIAL_MOTION_MODE,
                "style_profile": INK_GOUACHE_STORY_PAGES_STYLE_PROFILE,
                "stories": [source_story],
            })

    def test_cinematic_ink_webtoon_accepts_exact_68_image_release_plan(self):
        targets = (18, 18, 16, 16)
        stories = []
        for index, target in enumerate(targets, start=1):
            source_story = story(f"release-{index}", words=120)
            source_story["image_target"] = target
            source_story["visual_identity_contract"] = (
                f"Story {index} recurring adult cast keeps identical age, face, hair, body shape, "
                "wardrobe and props across every scene, without reusing identities from another story."
            )
            packs = target // 2
            source_story["editorial_motion_families"] = ["relationships"] * packs
            source_story["editorial_page_layouts"] = [
                "hero_left_details_right", "phone_portal_insets",
                "message_cascade", "vertical_routine_triptych",
                "evidence_slits", "rumor_table_wide",
                "corridor_false_claim", "empty_desk_release",
                "hero_left_details_right",
            ][:packs]
            stories.append(source_story)
        plan = image_plan({
            "episode_format": "BUNDLE",
            "visual_mode": EDITORIAL_MOTION_MODE,
            "style_profile": CINEMATIC_INK_WEBTOON_STYLE_PROFILE,
            "stories": stories,
        })
        self.assertEqual(len(plan), 68)
        self.assertEqual(
            [sum(item["story_index"] == index for item in plan) for index in range(4)],
            list(targets),
        )
        self.assertIn("premium adult cinematic ink webtoon", plan[0]["prompt"])

    def test_v3_bundle_prompt_uses_approved_drawn_format_grammar(self):
        source_story = story("v3-bundle", words=25)
        source_story["visual_identity_contract"] = (
            "Recurring adult woman with dark wavy hair, burgundy cardigan and black trousers; "
            "her face, age, body shape and wardrobe remain stable inside this mini-comic."
        )
        plan = image_plan({
            "episode_format": "BUNDLE",
            "visual_mode": EDITORIAL_MOTION_MODE,
            "style_profile": FORMAT_VISUAL_SYSTEM_V3_STYLE_PROFILE,
            "pillar": "relationships_family",
            "stories": [source_story],
        })
        prompt = plan[0]["prompt"]
        self.assertIn("BUNDLE grammar", prompt)
        self.assertIn("never photography", prompt)
        self.assertIn("Do not use an orange-dominated universal palette", prompt)
        self.assertIn("ivory, muted olive, dusty rose, burgundy and deep navy", prompt)
        self.assertEqual(plan[0]["page_layout"], "bundle_story_opener")

    def test_v3_panel_grammar_is_meaning_led_and_not_a_fixed_triptych(self):
        grammars = [
            select_format_visual_system_v3_panel_grammar("BUNDLE", index, 9)
            for index in range(1, 10)
        ]
        self.assertEqual(
            [item["panel_count"] for item in grammars],
            [1, 2, 3, 4, 5, 2, 3, 4, 1],
        )
        self.assertEqual(grammars[0]["beat_role"], "bundle_hook")
        self.assertEqual(grammars[4]["beat_role"], "bundle_turning_point")

    def test_v3_plan_binds_panel_grammar_to_each_generated_asset(self):
        source_story = story("v3-grammar", words=160)
        source_story["image_target"] = 18
        source_story["visual_identity_contract"] = (
            "Recurring adult woman with dark wavy hair, burgundy cardigan and black trousers; "
            "her face, age, body shape and wardrobe remain stable inside this mini-comic."
        )
        plan = image_plan({
            "episode_format": "BUNDLE",
            "visual_mode": EDITORIAL_MOTION_MODE,
            "style_profile": FORMAT_VISUAL_SYSTEM_V3_STYLE_PROFILE,
            "pillar": "relationships_family",
            "stories": [source_story],
        })
        heroes = [item for item in plan if item["layer_role"] == "hero_plate"]
        self.assertEqual(
            [item["panel_count"] for item in heroes],
            [1, 2, 3, 4, 5, 2, 3, 4, 1],
        )
        self.assertIn("Use exactly five asymmetrical panels", heroes[4]["prompt"])
        self.assertIn("without changing this exact panel count", heroes[4]["prompt"])

    def test_v3_saga_and_thread_have_different_page_grammars(self):
        saga_story = story("v3-saga", words=25)
        saga_story["visual_identity_contract"] = (
            "Recurring adult investigator with a dark bun, long black coat and leather shoulder bag; "
            "keep her face, age, wardrobe and apartment geography stable throughout the saga."
        )
        saga = image_plan({
            "episode_format": "SAGA", "visual_mode": EDITORIAL_MOTION_MODE,
            "style_profile": FORMAT_VISUAL_SYSTEM_V3_STYLE_PROFILE,
            "pillar": "strange_dark", "stories": [saga_story],
        })
        thread_stories = []
        for index in range(3):
            response = story(f"response-{index}", words=8)
            response["visual_identity_contract"] = (
                f"Response {index} uses one distinct believable adult in a unique contemporary setting; "
                "do not reuse this face, wardrobe, pose or environment for another response."
            )
            thread_stories.append(response)
        thread = image_plan({
            "episode_format": "THREAD", "visual_mode": EDITORIAL_MOTION_MODE,
            "style_profile": FORMAT_VISUAL_SYSTEM_V3_STYLE_PROFILE,
            "pillar": "confessions_taboo", "stories": thread_stories,
        })
        self.assertIn("SAGA grammar", saga[0]["prompt"])
        self.assertEqual(saga[0]["page_layout"], "saga_panorama")
        self.assertIn("THREAD grammar", thread[0]["prompt"])
        self.assertEqual(thread[0]["page_layout"], "thread_prompt_anchor")
        self.assertEqual({item["story_index"] for item in thread}, {0, 1, 2})
        self.assertEqual(len(thread), 6)

    def test_explicit_release_image_targets_must_be_even(self):
        source_story = story("odd-target", words=120)
        source_story["image_target"] = 17
        with self.assertRaisesRegex(EpisodeImageError, "even positive integer"):
            image_plan({
                "episode_format": "BUNDLE",
                "visual_mode": EDITORIAL_MOTION_MODE,
                "stories": [source_story],
            })

    def test_adult_animation_profile_selects_a_unique_source_bound_layout_sequence(self):
        source_story = story("work-source", words=25)
        source_story["visual_identity_contract"] = (
            "Same recurring adult warehouse dispatcher with short dark hair, blue work shirt, and round glasses; "
            "same recurring adult supervisor with a shaved head, olive jacket, and a paper clipboard."
        )
        plan = image_plan({
            "episode_format": "SAGA",
            "visual_mode": EDITORIAL_MOTION_MODE,
            "style_profile": ADULT_ANIMATION_WORK_STYLE_PROFILE,
            "stories": [source_story],
        })
        heroes = [item for item in plan if item["layer_role"] == "hero_plate"]
        layouts = [item["page_layout"] for item in heroes]
        self.assertEqual(len(layouts), len(set(layouts)))
        self.assertTrue(all(item["story_family"] == "adult_work" for item in heroes))
        self.assertIn("original adult 2D city-work comedy", heroes[0]["prompt"])
        self.assertNotIn("noir", heroes[0]["prompt"])

    def test_editorial_mode_rejects_thread_before_spend(self):
        with self.assertRaisesRegex(EpisodeImageError, "THREAD"):
            image_plan({
                "episode_format": "THREAD",
                "visual_mode": EDITORIAL_MOTION_MODE,
                "stories": [story("one")],
            })

    def test_spend_cap_blocks_before_generator_call(self):
        script = {"episode_format": "SAGA", "stories": [story("one")]}
        calls = []
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(EpisodeImageError, "requires 5"):
                generate_episode_images(
                    script,
                    Path(temp),
                    max_images=4,
                    generator=lambda **kwargs: calls.append(kwargs),
                )
        self.assertEqual(calls, [])

    def test_generated_assets_are_plan_bound(self):
        script = {
            "episode_format": "THREAD",
            "episode_plan_sha256": "a" * 64,
            "stories": [story("prompt"), story("response")],
        }

        def fake_generator(*, output_path, **_kwargs):
            Image.new("RGB", (1536, 864), "#314159").save(output_path)
            return output_path

        with tempfile.TemporaryDirectory() as temp:
            updated, assets = generate_episode_images(
                script,
                Path(temp),
                max_images=3,
                generator=fake_generator,
            )
        self.assertEqual(len(assets), 3)
        self.assertEqual(assets[0]["episode_plan_sha256"], "a" * 64)
        self.assertEqual(assets[0]["local_path"], "story-01-prompt-scene-01.png")
        self.assertRegex(assets[0]["sha256"], r"^[0-9a-f]{64}$")
        self.assertEqual(len(updated["stories"][0]["generated_media"]), 3)
        self.assertNotIn("generated_media", updated["stories"][1])

    def test_corrupt_nonempty_provider_file_is_rejected_immediately(self):
        script = {"episode_format": "SAGA", "stories": [story("one")]}
        calls = []

        def corrupt_generator(*, output_path, **_kwargs):
            calls.append(output_path)
            output_path.write_bytes(b"not-an-image")
            return output_path

        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(EpisodeImageError, "undecodable"):
                generate_episode_images(
                    script,
                    Path(temp),
                    max_images=5,
                    generator=corrupt_generator,
                )
        self.assertEqual(len(calls), 1)

    def test_wrong_provider_dimensions_are_rejected_immediately(self):
        script = {"episode_format": "SAGA", "stories": [story("one")]}

        def wrong_size_generator(*, output_path, **_kwargs):
            Image.new("RGB", (640, 360), "#314159").save(output_path)
            return output_path

        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(EpisodeImageError, "wrong dimensions"):
                generate_episode_images(
                    script,
                    Path(temp),
                    max_images=5,
                    generator=wrong_size_generator,
                )

    def test_large_near_ratio_provider_images_are_normalized_and_resumed(self):
        script = {
            "episode_format": "THREAD",
            "episode_plan_sha256": "a" * 64,
            "stories": [story("prompt"), story("response")],
        }
        attempts = []

        def provider(*, prompt, output_path, model, **_kwargs):
            Image.new("RGB", (1672, 941), "#314159").save(output_path)
            attempts.append({
                "index": len(attempts) + 1,
                "status": "COMPLETE",
                "request_sha256": _canonical_hash({
                    "prompt": prompt, "model": model,
                    "max_output_tokens": None, "voice_id": None,
                }),
                "output_sha256": hashlib.sha256(output_path.read_bytes()).hexdigest(),
            })
            return output_path

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            checkpoint = root / "scene-image-checkpoint.json"
            _updated, assets = generate_episode_images(
                script, root / "scene-images", artifact_root=root, max_images=3,
                generator=provider, provider_attempts=attempts,
                checkpoint_path=checkpoint,
            )
            self.assertEqual(len(attempts), 3)
            self.assertTrue(all(item["normalized_from_provider_size"] for item in assets))
            for item in assets:
                with Image.open(root / item["local_path"]) as image:
                    self.assertEqual(image.size, (1536, 864))
            resumed, resumed_assets = generate_episode_images(
                script, root / "scene-images", artifact_root=root, max_images=3,
                generator=lambda **_kwargs: self.fail("resumed image was regenerated"),
                provider_attempts=attempts, checkpoint_path=checkpoint,
            )
            self.assertEqual(len(resumed_assets), 3)
            self.assertEqual(len(resumed["stories"][0]["generated_media"]), 3)

            rebound_script = copy.deepcopy(script)
            rebound_script["episode_plan_sha256"] = "b" * 64
            _rebound, rebound_assets = generate_episode_images(
                rebound_script, root / "scene-images", artifact_root=root,
                max_images=3,
                generator=lambda **_kwargs: self.fail("rebound image was regenerated"),
                provider_attempts=attempts, checkpoint_path=checkpoint,
            )
            rebound_checkpoint = json.loads(checkpoint.read_text(encoding="utf-8"))
            self.assertEqual(len(rebound_assets), 3)
            self.assertEqual(rebound_checkpoint["episode_plan_sha256"], "b" * 64)
            self.assertEqual(
                rebound_checkpoint["rebound_from_episode_plan_sha256"], "a" * 64,
            )
            self.assertEqual(
                rebound_checkpoint["rebound_reason"],
                "exact_scene_request_hashes_revalidated",
            )

    def test_factory_scene_paths_are_relative_to_artifact_root(self):
        script = {
            "episode_format": "THREAD",
            "episode_plan_sha256": "a" * 64,
            "stories": [story("prompt"), story("response")],
        }

        def fake_generator(*, output_path, **_kwargs):
            Image.new("RGB", (1536, 864), "#314159").save(output_path)
            return output_path

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            _updated, assets = generate_episode_images(
                script,
                root / "scene-images",
                artifact_root=root,
                max_images=3,
                generator=fake_generator,
            )
            self.assertEqual(
                assets[0]["local_path"],
                "scene-images/story-01-prompt-scene-01.png",
            )
            self.assertTrue((root / assets[0]["local_path"]).is_file())

    def test_final_ambiguous_attempt_uses_local_fallback_without_retry(self):
        script = {
            "episode_format": "THREAD",
            "episode_plan_sha256": "a" * 64,
            "stories": [story("prompt"), story("response")],
        }
        attempts = []

        def provider(*, prompt, output_path, model, **_kwargs):
            Image.new("RGB", (1536, 864), "#314159").save(output_path)
            attempts.append({
                "index": len(attempts) + 1,
                "status": "COMPLETE",
                "request_sha256": _canonical_hash({
                    "prompt": prompt, "model": model,
                    "max_output_tokens": None, "voice_id": None,
                }),
                "output_sha256": hashlib.sha256(output_path.read_bytes()).hexdigest(),
            })
            return output_path

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            checkpoint = root / "scene-image-checkpoint.json"
            generate_episode_images(
                script, root / "scene-images", artifact_root=root, max_images=3,
                generator=provider, provider_attempts=attempts,
                checkpoint_path=checkpoint,
            )
            attempts[2] = {
                "index": 3,
                "status": "AMBIGUOUS_ERROR",
                "request_sha256": attempts[2]["request_sha256"],
                "error_type": "VectorEngineError",
            }
            checkpoint_payload = json.loads(checkpoint.read_text(encoding="utf-8"))
            checkpoint_payload["entries"] = checkpoint_payload["entries"][:2]
            checkpoint.write_text(json.dumps(checkpoint_payload), encoding="utf-8")

            updated, assets = generate_episode_images(
                script, root / "scene-images", artifact_root=root, max_images=3,
                generator=lambda **_kwargs: self.fail("ambiguous request was retried"),
                provider_attempts=attempts, checkpoint_path=checkpoint,
            )
            self.assertEqual(len(attempts), 3)
            self.assertEqual(assets[-1]["kind"], "local_continuity_fallback")
            self.assertEqual(
                assets[-1]["fallback_reason"],
                "ambiguous_provider_attempt_not_retried",
            )
            self.assertEqual(len(updated["stories"][0]["generated_media"]), 3)

    def test_outside_output_dir_is_blocked_before_generator_spend(self):
        script = {"episode_format": "SAGA", "stories": [story("one")]}
        calls = []
        with tempfile.TemporaryDirectory() as temp, tempfile.TemporaryDirectory() as outside:
            with self.assertRaisesRegex(EpisodeImageError, "output_dir"):
                generate_episode_images(
                    script,
                    Path(outside) / "scene-images",
                    artifact_root=Path(temp),
                    max_images=5,
                    generator=lambda **kwargs: calls.append(kwargs),
                )
        self.assertEqual(calls, [])

    def test_source_id_cannot_escape_planned_output_path(self):
        script = {
            "episode_format": "THREAD",
            "stories": [story("../../outside"), story("response")],
        }
        observed = []

        def fake_generator(*, output_path, **_kwargs):
            observed.append(output_path)
            Image.new("RGB", (1536, 864), "#314159").save(output_path)
            return output_path

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            _updated, assets = generate_episode_images(
                script,
                root / "scene-images",
                artifact_root=root,
                max_images=3,
                generator=fake_generator,
            )
            self.assertTrue(all(
                root.resolve() in path.resolve().parents for path in observed
            ))
            self.assertTrue(all(".." not in path.name for path in observed))
            self.assertTrue(all(
                asset["local_path"].startswith("scene-images/")
                for asset in assets
            ))


if __name__ == "__main__":
    unittest.main()
