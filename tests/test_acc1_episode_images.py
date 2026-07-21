import tempfile
import unittest
from pathlib import Path

from PIL import Image

from acc1_visual_contract import (
    ADULT_ANIMATION_WORK_STYLE_PROFILE,
    CINEMATIC_INK_WEBTOON_STYLE_PROFILE,
    CINEMATIC_STORY_MODE,
    EDITORIAL_MOTION_MODE,
    INK_GOUACHE_STORY_PAGES_STYLE_PROFILE,
)
from acc1_episode_images import EpisodeImageError, generate_episode_images, image_plan


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

    def test_editorial_provider_size_is_preserved_and_normalized(self):
        script = {
            "episode_format": "SAGA",
            "visual_mode": EDITORIAL_MOTION_MODE,
            "stories": [story("one")],
        }

        def provider_size_generator(*, output_path, **_kwargs):
            Image.new("RGB", (1672, 941), "#314159").save(output_path)
            return output_path

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            _updated, assets = generate_episode_images(
                script,
                root,
                max_images=58,
                generator=provider_size_generator,
            )
            normalized = root / assets[0]["local_path"]
            original = root / assets[0]["normalization"]["provider_original_path"]
            with Image.open(normalized) as image:
                self.assertEqual(image.size, (1536, 864))
            with Image.open(original) as image:
                self.assertEqual(image.size, (1672, 941))
            self.assertEqual(
                assets[0]["normalization"]["provider_original_dimensions"],
                [1672, 941],
            )
            self.assertRegex(
                assets[0]["normalization"]["provider_original_sha256"],
                r"^[0-9a-f]{64}$",
            )

    def test_editorial_unsafe_provider_crop_is_rejected(self):
        script = {
            "episode_format": "SAGA",
            "visual_mode": EDITORIAL_MOTION_MODE,
            "stories": [story("one")],
        }

        def portrait_generator(*, output_path, **_kwargs):
            Image.new("RGB", (1800, 1200), "#314159").save(output_path)
            return output_path

        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(EpisodeImageError, "unsafe crop"):
                generate_episode_images(
                    script,
                    Path(temp),
                    max_images=58,
                    generator=portrait_generator,
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
