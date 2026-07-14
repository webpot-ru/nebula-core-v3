import tempfile
import unittest
from pathlib import Path

from PIL import Image

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


if __name__ == "__main__":
    unittest.main()
