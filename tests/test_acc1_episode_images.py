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
from acc1_visual_contract import CINEMATIC_STORY_MODE


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
